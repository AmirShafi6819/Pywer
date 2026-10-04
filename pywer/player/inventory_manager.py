# ---------------------------------------------------------------- server-authoritative inventory actions
"""Server-authoritative ItemStackRequest execution and inventory transaction validator."""

from .inventory import item_tuple, MAX_STACK
from .recipes import match_recipe
from ..event import PlayerDropItemEvent
from ..event import manager as events
from ..world.blocks import item_key_for_id

# ItemStackRequestAction types (BedrockProtocol ItemStackRequestActionType)
ACTION_TAKE = 0
ACTION_PLACE = 1
ACTION_SWAP = 2
ACTION_DROP = 3
ACTION_DESTROY = 4
ACTION_CONSUME = 5
ACTION_CREATE_OUTPUT = 6
ACTION_MINE_BLOCK = 11
ACTION_CREATIVE_CREATE = 14


class InventoryError(Exception):
    """Raised when a requested inventory change is not allowed; the request is rejected."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class InventoryManager:
    """Applies ItemStackRequests to a player's containers and reports resulting changes."""

    def __init__(self, session):
        self.session = session

    # -- container helpers -------------------------------------------------
    def _check_stack_id(self, ref, client_stack_id):
        """PocketMine ItemStackRequestExecutor::matchItemStack."""
        r = self.session.resolve_slot(ref[0], ref[1])
        if r is None:
            raise InventoryError("unknown slot container=%d slot=%d" % (ref[0], ref[1]))
        cid, _lst, slot = r
        if not self.session.predictions.matches_client_stack_id(cid, slot, client_stack_id):
            info = self.session.predictions.info(cid, slot)
            raise InventoryError(
                "stack id mismatch on container %s slot %d (client %d, server stack %s, last request %s)"
                % (
                    str(cid),
                    slot,
                    client_stack_id,
                    info.stack_id if info else "unknown",
                    info.request_id if info and info.request_id is not None else "none",
                )
            )

    def _resolve(self, ref):
        """(container_id, slot) -> (backing list, core index) or None."""
        r = self.session.resolve_slot(ref[0], ref[1])
        if r is None:
            return None
        _cid, lst, idx = r
        return (lst, idx) if 0 <= idx < len(lst) else (lst, -1)

    # -- actions -----------------------------------------------------------
    def _transfer(self, count, src, dst):
        """TAKE / PLACE: move `count` from src to dst, merging when stacks match."""
        ra = self._resolve(src)
        rb = self._resolve(dst)
        if ra is None or rb is None:
            raise InventoryError("unknown slot")
        (la, ia), (lb, ib) = ra, rb
        if ia < 0 or ib < 0:
            raise InventoryError("slot out of range")
        a = la[ia]
        b = lb[ib]
        if count < 1 or count > a[1]:
            raise InventoryError("not enough items")
        if b[1] > 0 and (a[0] != b[0] or a[2] != b[2]):
            raise InventoryError("stacks do not match")
        if MAX_STACK - b[1] < count:
            raise InventoryError("destination is full")
        la[ia] = item_tuple(a[0], a[1] - count, a[2])
        lb[ib] = item_tuple(a[0], b[1] + count, a[2])
        return {(id(la), ia), (id(lb), ib)}

    def _swap(self, a, b):
        ra = self._resolve(a)
        rb = self._resolve(b)
        if ra is None or rb is None:
            raise InventoryError("unknown slot")
        (la, ia), (lb, ib) = ra, rb
        if ia < 0 or ib < 0:
            raise InventoryError("slot out of range")
        la[ia], lb[ib] = lb[ib], la[ia]
        return {(id(la), ia), (id(lb), ib)}

    def _drop(self, count, src):
        r = self._resolve(src)
        if r is None:
            raise InventoryError("unknown slot")
        lst, i = r
        if i < 0:
            raise InventoryError("slot out of range")
        item = lst[i]
        if count < 1 or count > item[1]:
            raise InventoryError("not enough items")
        key = item_key_for_id(item[0])
        if key is None:
            raise InventoryError("unknown item")
        # Dispatched before anything is moved, so a cancelled drop leaves the slot exactly
        # as it was and the rejected request makes the client resynchronise.
        ev = events.call(PlayerDropItemEvent(self.session, (item[0], count, item[2])))
        if ev.is_cancelled:
            raise InventoryError("drop cancelled by plugin")
        if not self.session.srv.drop_item(self.session.feet(), key, count):
            raise InventoryError("cannot drop item")
        lst[i] = item_tuple(item[0], item[1] - count, item[2])
        return {(id(lst), i)}

    def _destroy(self, count, src):
        r = self._resolve(src)
        if r is None:
            raise InventoryError("unknown slot")
        lst, i = r
        if i < 0:
            raise InventoryError("slot out of range")
        item = lst[i]
        if count < 1 or count > item[1]:
            raise InventoryError("not enough items")
        lst[i] = item_tuple(item[0], item[1] - count, item[2])
        return {(id(lst), i)}

    def _evaluate_crafting(self, snapshot):
        c3 = self.session.containers.complex.get("crafting3x3")
        c2 = self.session.containers.complex.get("crafting2x2")
        if c3:
            res = match_recipe(c3.items)
            if res is not None:
                return res
        if c2:
            res = match_recipe(c2.items)
            if res is not None:
                return res
        if c3:
            snap3 = snapshot.get(id(c3.items))
            if snap3:
                res = match_recipe(snap3)
                if res is not None:
                    return res
        if c2:
            snap2 = snapshot.get(id(c2.items))
            if snap2:
                res = match_recipe(snap2)
                if res is not None:
                    return res
        return None

    # -- entry point -------------------------------------------------------
    def apply_request(self, request_id, actions):
        """Apply one request atomically. Returns set of changed (id(list), index) pairs."""
        all_lists = list(self.session.containers.items.values())
        if hasattr(self.session.containers, "complex"):
            all_lists.extend(c.items for c in self.session.containers.complex.values())
        snapshot = {id(lst): list(lst) for lst in all_lists}
        touched = set()
        try:
            for act in actions:
                typ = act[0]
                if typ in (ACTION_TAKE, ACTION_PLACE):
                    _, count, src, dst = act
                    self._check_stack_id((src[0], src[1]), src[2])
                    self._check_stack_id((dst[0], dst[1]), dst[2])
                    touched |= self._transfer(count, (src[0], src[1]), (dst[0], dst[1]))
                elif typ == ACTION_SWAP:
                    _, a, b = act
                    self._check_stack_id((a[0], a[1]), a[2])
                    self._check_stack_id((b[0], b[1]), b[2])
                    touched |= self._swap((a[0], a[1]), (b[0], b[1]))
                elif typ == ACTION_DROP:
                    _, count, src, _rnd = act
                    touched |= self._drop(count, (src[0], src[1]))
                elif typ == ACTION_DESTROY:
                    _, count, src = act
                    touched |= self._destroy(count, (src[0], src[1]))
                elif typ == ACTION_CONSUME:
                    _, count, src = act[:3]
                    self._check_stack_id((src[0], src[1]), src[2])
                    touched |= self._destroy(count, (src[0], src[1]))
                elif typ == ACTION_CREATE_OUTPUT:
                    res = self._evaluate_crafting(snapshot)
                    if res is None:
                        raise InventoryError("no matching recipe")
                    out_cont = self.session.containers.complex["created_output"]
                    out_cont.items[0] = item_tuple(res[0], res[1], res[2])
                    touched.add((id(out_cont.items), 0))
                elif typ == ACTION_CREATIVE_CREATE:
                    if not self.session.gamemode_is_creative():
                        raise InventoryError("creative create not allowed in survival")
                    item_id = act[1]
                    count = act[2] if len(act) > 2 and act[2] > 0 else 64
                    out_cont = self.session.containers.complex["created_output"]
                    out_cont.items[0] = item_tuple(item_id, count, 0)
                    touched.add((id(out_cont.items), 0))
                elif typ == ACTION_MINE_BLOCK:
                    continue
                else:
                    raise InventoryError("unsupported action %d" % typ)
        except (InventoryError, ValueError, TypeError, IndexError, KeyError) as e:
            for lst_id, snap in snapshot.items():
                for lst in all_lists:
                    if id(lst) == lst_id:
                        lst[:] = snap
                        break
            if not isinstance(e, InventoryError):
                raise InventoryError("malformed action: %r" % (e,))
            raise
        return touched
# ---------------------------------------------------------------- client prediction tracking
# The Bedrock client predicts inventory changes locally. The server must therefore know what
# the client *believes* each slot will become, so it can stay silent when the guess was right
# and correct it when it was wrong. PocketMine tracks this with three per-slot structures;
# so does pywer, in pywer/player/prediction.py.
#
#   predictions[slot]  - ItemStack the client has already predicted for this slot
#   item_stack_infos[slot] - ItemStackInfo(request_id, stack_id): server-known stack state
#   pending_syncs[slot]    - ItemStack queued for correction, flushed at the end of the tick

AIR = (0, 0, 0)

class ItemStackInfo:
    """Server-known state of one slot.

    request_id attributes the last change to the ItemStackRequest that caused it. The client
    refers to items by a *negative* id meaning "the state you told me about for request N", so
    without this the server cannot match the client's view and every request is rejected.
    """

    __slots__ = ("request_id", "stack_id")

    def __init__(self, request_id=None, stack_id=0):
        self.request_id = request_id
        self.stack_id = stack_id

    def __repr__(self):
        return "ItemStackInfo(request_id=%r, stack_id=%d)" % (self.request_id, self.stack_id)

def stacks_equal(left, right):
    """PocketMine ItemStacks::itemStacksEqual - id, meta, block runtime id, count."""
    if left is None or right is None:
        return left is right
    return (left[0], left[2], left[1]) == (right[0], right[2], right[1])

class PredictionTracker:
    """Per-container prediction state, mirroring PocketMine's InventoryManagerEntry."""

    def __init__(self, session):
        self.session = session
        self.predictions = {}        # (container_id, slot) -> ItemStack
        self.item_stack_infos = {}   # (container_id, slot) -> ItemStackInfo
        self.pending_syncs = {}      # (container_id, slot) -> ItemStack
        self.full_sync_requested = False

    # -- stack ids ---------------------------------------------------------
    def new_stack_id(self):
        sid = self.session.next_stack_id
        self.session.next_stack_id += 1
        return sid

    def track_item_stack(self, container_id, slot, item, request_id=None):
        """Register a new stack id for a slot. Air always keeps id 0, like PocketMine."""
        stack_id = 0 if (item is None or item[0] == 0) else self.new_stack_id()
        self.item_stack_infos[(container_id, slot)] = ItemStackInfo(request_id, stack_id)
        return self.item_stack_infos[(container_id, slot)]

    def info(self, container_id, slot):
        return self.item_stack_infos.get((container_id, slot))

    def matches_client_stack_id(self, container_id, slot, client_stack_id):
        """PocketMine ItemStackRequestExecutor::matchItemStack.

        A negative client id refers to a past *request*; anything else is a server stack id.
        """
        info = self.info(container_id, slot)
        if info is None or info.stack_id == 0:
            return client_stack_id <= 0
        if client_stack_id < 0:
            return info.request_id == client_stack_id
        return info.stack_id == client_stack_id

    # -- prediction --------------------------------------------------------
    def predict(self, container_id, slot, item):
        self.predictions[(container_id, slot)] = item

    def on_slot_change(self, container_id, slot, current, current_request_id):
        """Mirror BaseInventory::onSlotChange -> InventoryManager::onSlotChange."""
        key = (container_id, slot)
        predicted = self.predictions.get(key)
        if predicted is None or not stacks_equal(current, predicted):
            # no prediction, or a wrong one: do not attribute this to the active request
            self.track_item_stack(container_id, slot, current, None)
            self.pending_syncs[key] = current
        else:
            # correctly predicted: attribute it to the request that caused it
            self.track_item_stack(container_id, slot, current, current_request_id)
        self.predictions.pop(key, None)

    def sync_mismatched_predictions(self):
        """Any prediction still present was never applied, so the client is out of date."""
        for key in list(self.predictions.keys()):
            container_id, slot = key
            lst = self.session.containers.get(container_id)
            if lst is None or slot < 0 or slot >= len(lst):
                continue
            self.pending_syncs[key] = lst[slot]
        self.predictions.clear()

    # -- flushing ----------------------------------------------------------
    def request_full_sync(self):
        self.full_sync_requested = True

    def flush(self):
        """Called once per tick. A full sync suppresses pending per-slot corrections."""
        if self.full_sync_requested:
            self.full_sync_requested = False
            self.session.sync_inventory()
            return
        if not self.pending_syncs:
            return
        for (container_id, slot), item in sorted(self.pending_syncs.items()):
            self.session.sync_slot(container_id, slot)
        self.pending_syncs.clear()
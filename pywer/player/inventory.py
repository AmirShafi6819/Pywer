# ---------------------------------------------------------------- player inventory model
# Slots 0..8 are the hotbar, 9..35 the main inventory (Bedrock's player inventory layout).
HOTBAR_SIZE = 9
INVENTORY_SIZE = 36
MAX_STACK = 64

ITEM_AIR = (0, 0, 0)

def item_tuple(item_id, count=0, meta=0):
    return (int(item_id), int(count), int(meta)) if count > 0 else ITEM_AIR

def stack_room(item):
    """How many more of `item` fit in a slot holding it (0 when the slot is empty)."""
    return MAX_STACK if item[1] <= 0 else max(0, MAX_STACK - item[1])

def can_merge(a, b):
    """True when a stack of `a` may be merged into a slot holding `b`."""
    return b[1] <= 0 or (a[0] == b[0] and a[2] == b[2])

def first_empty_slot(inventory, start=0):
    for i in range(start, len(inventory)):
        if inventory[i][1] <= 0: return i
    return None

def first_slot_with(inventory, item_id, meta=0):
    for i, st in enumerate(inventory):
        if st[1] > 0 and st[0] == item_id and st[2] == meta: return i
    return None

def add_item(inventory, item):
    """Insert `item` into the inventory the way PocketMine fills stacks.

    Returns the number that did not fit (0 when everything was inserted). Merging happens
    before empty slots so partial stacks are topped up first.
    """
    item_id, count, meta = item
    if item_id <= 0 or count <= 0: return 0
    left = count
    for i, st in enumerate(inventory):
        if left <= 0: break
        if st[1] > 0 and st[0] == item_id and st[2] == meta:
            take = min(left, MAX_STACK - st[1])
            if take > 0:
                inventory[i] = item_tuple(item_id, st[1] + take, meta); left -= take
    for i, st in enumerate(inventory):
        if left <= 0: break
        if st[1] <= 0:
            take = min(left, MAX_STACK)
            inventory[i] = item_tuple(item_id, take, meta); left -= take
    return left

def remove_item(inventory, item_id, count, meta=0):
    """Remove up to `count` of an item. Returns how many were actually removed."""
    left = count
    for i, st in enumerate(inventory):
        if left <= 0: break
        if st[1] > 0 and st[0] == item_id and st[2] == meta:
            take = min(left, st[1])
            inventory[i] = item_tuple(item_id, st[1] - take, meta); left -= take
    return count - left
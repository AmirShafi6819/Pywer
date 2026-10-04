# ---------------------------------------------------------------- inventory transaction decoding
"""InventoryTransactionPacket decoder and interaction payload parsers."""

from ..util.serializer import ByteReader
from .item_stack import read_item_stack_wrapper

# InventoryTransactionPacket transaction types
TX_NORMAL = 0
TX_MISMATCH = 1
TX_USE_ITEM = 2
TX_USE_ITEM_ON_ENTITY = 3
TX_RELEASE_ITEM = 4

# UseItemTransactionData action types
ACTION_CLICK_BLOCK = 0
ACTION_CLICK_AIR = 1
ACTION_BREAK_BLOCK = 2

# UseItemOnEntityTransactionData action types
ACTION_INTERACT = 0
ACTION_ATTACK = 1
ACTION_ITEM_INTERACT = 2

# NetworkInventoryAction source types
SOURCE_CONTAINER = 0
SOURCE_WORLD = 2
SOURCE_CREATIVE = 3
SOURCE_TODO = 99999

# NetworkInventoryAction magic inventory slots
ACTION_MAGIC_SLOT_DROP_ITEM = 0


def read_signed_block_pos(r):
    # PacketSerializer::getSignedBlockPosition()
    return (r.read_varint32(), r.read_varint32(), r.read_varint32())


def read_block_pos(r):
    # PacketSerializer::getBlockPosition() - Y is written unsigned (signInt applied afterwards)
    x = r.read_varint32()
    y = r.read_varuint32()
    if y >= 0x80000000:
        y -= 0x100000000
    z = r.read_varint32()
    return (x, y, z)


def read_vec3(r):
    return (r.read_float(), r.read_float(), r.read_float())


def read_network_inventory_action(r):
    """NetworkInventoryAction::read().

    Every layout uses the same getItemStackWrapper reader. Reading it differently desynchronises packets.
    """
    source = r.read_varuint32()
    window = 0
    if source in (SOURCE_CONTAINER, SOURCE_TODO):
        window = r.read_varint32()
    elif source == SOURCE_WORLD:
        r.read_varuint32()  # sourceFlags
    elif source != SOURCE_CREATIVE:
        raise ValueError("unknown inventory action source %d" % source)
    slot = r.read_varuint32()  # inventorySlot
    return {
        "source": source,
        "window": window,
        "slot": slot,
        "old": read_item_stack_wrapper(r),
        "new": read_item_stack_wrapper(r),
    }


def read_item_interaction_data(r):
    """ItemInteractionData::read() - tail of PlayerAuthInputPacket when PERFORM_ITEM_INTERACTION is set."""
    request_id = r.read_varint32()
    if request_id != 0:
        for _ in range(r.read_varuint32()):  # InventoryTransactionChangedSlotsHack
            r.read_u8()
            for _ in range(r.read_varuint32()):
                r.read_u8()
    r.read_varuint32()  # action count (UseItem always 0)
    return read_use_item_transaction(r)


def read_use_item_transaction(r):
    """UseItemTransactionData::decodeData - CLICK_BLOCK here means block placement."""
    action = r.read_varint32()
    return {
        "action": action,
        "trigger": r.read_u8(),
        "pos": read_signed_block_pos(r),
        "face": r.read_u8(),
        "hotbar": r.read_varint32(),
        "item": read_item_stack_wrapper(r),
        "player_pos": read_vec3(r),
        "click_pos": read_vec3(r),
        "block_runtime_id": r.read_varuint32(),
        "prediction": r.read_u8(),
        "cooldown": r.read_u8(),
    }


def read_use_item_on_entity_transaction(r):
    """UseItemOnEntityTransactionData::decodeData - player vs entity attacks."""
    return {
        "target_rid": r.read_varuint64(),
        "action": r.read_varint32(),
        "hotbar": r.read_varint32(),
        "item": read_item_stack_wrapper(r),
        "player_pos": read_vec3(r),
        "click_pos": read_vec3(r),
    }


def read_release_item_transaction(r):
    """ReleaseItemTransactionData::decodeData."""
    return {
        "action": r.read_varint32(),
        "hotbar": r.read_varint32(),
        "item": read_item_stack_wrapper(r),
        "head_pos": read_vec3(r),
    }


def read_normal_transaction(r):
    """NormalTransactionData::decodeData - drop item transactions."""
    n = r.read_varuint32()
    actions = []
    for _ in range(n):
        actions.append(read_network_inventory_action(r))
    return {"actions": actions}


def parse_inventory_transaction(body):
    """InventoryTransactionPacket::decodePayload for every transaction type pywer acts on."""
    r = ByteReader(body)
    request_id = r.read_varint32()  # requestId (legacy stack request id)
    if request_id != 0:  # requestChangedSlots present only when nonzero
        for _ in range(r.read_varuint32()):
            r.read_u8()  # containerId
            for _ in range(r.read_varuint32()):
                r.read_u8()
    tx_type = r.read_varuint32()
    if tx_type == TX_USE_ITEM:
        return [(tx_type, read_use_item_transaction(r))]
    if tx_type == TX_USE_ITEM_ON_ENTITY:
        return [(tx_type, read_use_item_on_entity_transaction(r))]
    if tx_type == TX_RELEASE_ITEM:
        return [(tx_type, read_release_item_transaction(r))]
    if tx_type == TX_NORMAL:
        return [(tx_type, read_normal_transaction(r))]
    # Mismatch / unknown: no transaction data pywer handles.
    return [(tx_type, None)]
# ---------------------------------------------------------------- inventory protocol (PocketMine 5.22 / BedrockProtocol 35.0.3 subset)
"""Inventory network protocol constants, packet encoders, and stack request parsers."""

from ..util.serializer import ByteReader, ByteWriter
from .item_stack import EMPTY_ITEM_EXTRA
from ..world.blocks import item_key_for_id, BLOCK_RUNTIME

# ContainerUIIds (serverbound stack request container-interface ids)
UI_ANVIL_INPUT = 0
UI_ANVIL_MATERIAL = 1
UI_SMITHING_TABLE_INPUT = 3
UI_SMITHING_TABLE_MATERIAL = 4
UI_ARMOR = 6
UI_LEVEL_ENTITY = 7
UI_BEACON_PAYMENT = 8
UI_BREWING_STAND_INPUT = 9
UI_BREWING_STAND_RESULT = 10
UI_BREWING_STAND_FUEL = 11
UI_COMBINED = 12
UI_CRAFTING_INPUT = 13
UI_ENCHANTING_INPUT = 22
UI_ENCHANTING_MATERIAL = 23
UI_FURNACE_FUEL = 24
UI_FURNACE_INGREDIENT = 25
UI_FURNACE_RESULT = 26
UI_HORSE_EQUIP = 27
UI_HOTBAR = 28
UI_INVENTORY = 29
UI_SHULKER_BOX = 30
UI_TRADE_INGREDIENT1 = 31
UI_TRADE_INGREDIENT2 = 32
UI_OFFHAND = 34
UI_COMPOUND_CREATOR_INPUT = 35
UI_MATERIAL_REDUCER_INPUT = 38
UI_MATERIAL_REDUCER_OUTPUT = 39
UI_LAB_TABLE_INPUT = 40
UI_LOOM_INPUT = 41
UI_LOOM_DYE = 42
UI_LOOM_MATERIAL = 43
UI_BLAST_FURNACE_INGREDIENT = 45
UI_SMOKER_INGREDIENT = 46
UI_TRADE2_INGREDIENT1 = 47
UI_TRADE2_INGREDIENT2 = 48
UI_GRINDSTONE_INPUT = 50
UI_GRINDSTONE_ADDITIONAL = 51
UI_STONECUTTER_INPUT = 53
UI_CARTOGRAPHY_INPUT = 55
UI_CARTOGRAPHY_ADDITIONAL = 56
UI_BARREL = 58
UI_CURSOR = 59
UI_CREATED_OUTPUT = 60
UI_SMITHING_TABLE_TEMPLATE = 61

# UI container ids that live in shared ContainerIds::UI (124) slot space
UI_SPACE_IDS = frozenset(
    (
        UI_ANVIL_INPUT,
        UI_ANVIL_MATERIAL,
        UI_SMITHING_TABLE_INPUT,
        UI_SMITHING_TABLE_MATERIAL,
        UI_BEACON_PAYMENT,
        UI_COMPOUND_CREATOR_INPUT,
        UI_CRAFTING_INPUT,
        UI_CREATED_OUTPUT,
        UI_CURSOR,
        UI_ENCHANTING_INPUT,
        UI_ENCHANTING_MATERIAL,
        UI_GRINDSTONE_INPUT,
        UI_GRINDSTONE_ADDITIONAL,
        UI_LAB_TABLE_INPUT,
        UI_LOOM_DYE,
        UI_LOOM_INPUT,
        UI_LOOM_MATERIAL,
        UI_MATERIAL_REDUCER_INPUT,
        UI_MATERIAL_REDUCER_OUTPUT,
        UI_SMITHING_TABLE_TEMPLATE,
        UI_STONECUTTER_INPUT,
        UI_TRADE2_INGREDIENT1,
        UI_TRADE2_INGREDIENT2,
        UI_TRADE_INGREDIENT1,
        UI_TRADE_INGREDIENT2,
        UI_CARTOGRAPHY_INPUT,
        UI_CARTOGRAPHY_ADDITIONAL,
    )
)

# UI container ids that address a block-container window
BLOCK_CONTAINER_IDS = frozenset(
    (
        UI_BARREL,
        UI_BLAST_FURNACE_INGREDIENT,
        UI_BREWING_STAND_FUEL,
        UI_BREWING_STAND_INPUT,
        UI_BREWING_STAND_RESULT,
        UI_FURNACE_FUEL,
        UI_FURNACE_INGREDIENT,
        UI_FURNACE_RESULT,
        UI_HORSE_EQUIP,
        UI_LEVEL_ENTITY,
        UI_SHULKER_BOX,
        UI_SMOKER_INGREDIENT,
    )
)

# ContainerIds (BedrockProtocol)
CONTAINER_ID_NONE = -1
CONTAINER_ID_INVENTORY = 0
CONTAINER_ID_FIRST = 1
CONTAINER_ID_LAST = 100
CONTAINER_ID_OFFHAND = 119
CONTAINER_ID_ARMOR = 120
CONTAINER_ID_UI = 124

# WindowTypes (BedrockProtocol)
WINDOW_NONE = -9
WINDOW_INVENTORY = -1
WINDOW_CONTAINER = 0


def item_stack_id(item):
    """Stable server-side stack ID calculation."""
    if item[1] <= 0:
        return 0
    return ((item[0] * 257 + item[2]) & 0x7FFFFFFF) or 1


def build_inventory_stack(item, stack_id=0):
    if item[1] <= 0:
        return b"\x00"
    item_id, count, meta = item
    key = item_key_for_id(item_id)
    block_rid = (BLOCK_RUNTIME.get(key, 0) if key not in (None, "air", "water") else 0) & 0xFFFFFFFF
    w = ByteWriter()
    w.write_varint32(item_id)
    w.write_u16_le(count)
    w.write_varuint32(meta)
    w.write_bool(stack_id != 0)
    if stack_id:
        w.write_varint32(stack_id)
    w.write_varint32(block_rid)
    w.write_string(EMPTY_ITEM_EXTRA)
    return w.get()


def build_full_container_name(container_id, dynamic_id=None):
    w = ByteWriter()
    w.write_u8(container_id)
    if dynamic_id is None:
        w.write_bool(False)
    else:
        w.write_bool(True)
        w.write_i32(dynamic_id)
    return w.get()


def build_inventory_content(window_id, items, container_id=UI_COMBINED, stack_ids=None):
    """InventoryContentPacket: windowId, count+wrappers, FullContainerName, storage wrapper."""
    w = ByteWriter()
    w.write_varuint32(window_id)
    w.write_varuint32(len(items))
    for i, item in enumerate(items):
        w.write_bytes(build_inventory_stack(item, (stack_ids or {}).get(i, 0)))
    w.write_bytes(build_full_container_name(container_id))
    w.write_bytes(b"\x00")
    return w.get()


def build_inventory_slot(window_id, slot, item, container_id=UI_COMBINED, stack_id=0):
    """InventorySlotPacket: windowId, slot, container name, storage, item (protocol 766 order)."""
    w = ByteWriter()
    w.write_varuint32(window_id)
    w.write_varuint32(slot)
    w.write_bytes(build_full_container_name(container_id))
    w.write_bytes(b"\x00")
    w.write_bytes(build_inventory_stack(item, stack_id))
    return w.get()


def build_stack_response_ok(request_id, changed):
    """ItemStackResponsePacket: one response containing all changed container slots.

    `changed` maps ContainerUIIds -> [(net_slot, item, server_stack_id)].
    """
    w = ByteWriter()
    w.write_varuint32(1)
    w.write_u8(0)
    w.write_varint32(request_id)
    w.write_varuint32(len(changed))
    for container_id, slots in changed.items():
        w.write_u8(container_id)
        w.write_bool(False)
        w.write_varuint32(len(slots))
        for slot, item, sid in slots:
            cnt = item[1]
            w.write_u8(slot)
            w.write_u8(slot)
            w.write_u8(cnt)
            w.write_varint32(sid)
            w.write_string("")
            w.write_string("")
            w.write_varint32(0)
    return w.get()


def build_stack_response_error(request_id):
    w = ByteWriter()
    w.write_varuint32(1)
    w.write_u8(1)
    w.write_varint32(request_id)
    return w.get()


def read_stack_slot(r):
    """ItemStackRequestSlotInfo::read: FullContainerName, byte slot, zigzag stack id."""
    cid = r.read_u8()
    dynamic = r.read_bool()
    if dynamic:
        r.read_i32()
    slot = r.read_u8()
    stack_id = r.read_varint32()
    return cid, slot, stack_id


def parse_item_stack_request(body):
    """ItemStackRequestPacket::decodePayload.

    Every action type must consume exactly its own payload: an unknown action cannot be
    skipped safely, so it raises instead of corrupting the rest of the packet.
    """
    r = ByteReader(body)
    n = r.read_varuint32()
    reqs = []
    for _ in range(n):
        reqid = r.read_varint32()
        ac = r.read_varuint32()
        acts = []
        for _ in range(ac):
            typ = r.read_u8()
            if typ in (0, 1):  # TAKE / PLACE
                count = r.read_u8()
                src = read_stack_slot(r)
                dst = read_stack_slot(r)
                acts.append((typ, count, src, dst))
            elif typ == 2:  # SWAP
                a = read_stack_slot(r)
                b = read_stack_slot(r)
                acts.append((typ, a, b))
            elif typ == 3:  # DROP
                count = r.read_u8()
                src = read_stack_slot(r)
                rnd = r.read_bool()
                acts.append((typ, count, src, rnd))
            elif typ == 4:  # DESTROY
                count = r.read_u8()
                src = read_stack_slot(r)
                acts.append((typ, count, src))
            elif typ == 5:  # CRAFTING_CONSUME_INPUT
                count = r.read_u8()
                src = read_stack_slot(r)
                acts.append((typ, count, src))
            elif typ == 6:  # CRAFTING_CREATE_SPECIFIC_RESULT
                acts.append((typ, r.read_u8()))
            elif typ == 9:  # LAB_TABLE_COMBINE
                acts.append((typ,))
            elif typ == 10:  # BEACON_PAYMENT
                acts.append((typ, r.read_varint32(), r.read_varint32()))
            elif typ == 11:  # MINE_BLOCK
                hotbar = r.read_varint32()
                durability = r.read_varint32()
                sid = r.read_varint32()
                acts.append((typ, hotbar, durability, sid))
            elif typ == 12:  # CRAFTING_RECIPE
                recipe = r.read_varuint32()
                reps = r.read_u8()
                acts.append((typ, recipe, reps))
            elif typ == 13:  # CRAFTING_RECIPE_AUTO
                raise ValueError("CRAFTING_RECIPE_AUTO is not supported")
            elif typ == 14:  # CREATIVE_CREATE
                acts.append((typ, r.read_varuint32(), r.read_u8()))
            else:
                # We deliberately reject unknown schemas instead of desynchronising the packet.
                raise ValueError("unsupported ItemStackRequest action %d" % typ)
        fs = r.read_varuint32()
        for _ in range(fs):
            r.read_string()
        r.read_i32()
        reqs.append((reqid, acts))
    return reqs


def build_container_open(window_id, window_type, actor_rid):
    """ContainerOpenPacket: byte window id, byte window type, block position, actor unique id."""
    w = ByteWriter()
    w.write_u8(window_id & 0xFF)
    w.write_u8(window_type & 0xFF)
    w.write_varint32(0).write_varuint32(0).write_varint32(0)  # position unused for entity inventories
    # ContainerOpenPacket::encodePayload writes actor with signed (zigzag) varlong
    w.write_varint64(actor_rid)
    return w.get()


def build_container_close(window_id, window_type, server=False):
    """ContainerClosePacket: byte window id, byte window type, bool server."""
    w = ByteWriter()
    w.write_u8(window_id & 0xFF)
    w.write_u8(window_type & 0xFF)
    w.write_bool(server)
    return w.get()

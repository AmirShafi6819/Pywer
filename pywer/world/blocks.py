# ---------------------------------------------------------------- blocks, terrain, chunks
# Block network ids: StartGame sets "blockNetworkIdsAreHashes" (field exists since 1.19.80, see BedrockProtocol
# StartGamePacket). The runtime id of a block is then FNV-1a-32 over the little-endian NBT of
# {name, states(sorted by key)} - independent of the palette order of any particular game version.
# State names/types below were checked against PocketMine-MP 5.22.0 (protocol 766)
# BlockObjectToStateSerializer / BlockStateNames and against canonical_block_states.nbt.
import math

from ..util.nbt import T_BYTE, T_INT, T_STR, block_state_hash
from ..data.item_table import item_runtime_id

BLOCK_DEFS = {}      # key -> (identifier, states)
BLOCK_RUNTIME = {}   # key -> network block id (signed)
BLOCK_KEYS = []      # index -> key (used by the chunk builder)
BLOCK_INDEX = {}     # key -> index

def register_block(key, identifier=None, states=None):
    """Add a block to the server. states example: {"pillar_axis": (T_STR, "y"), "persistent_bit": (T_BYTE, 0)}"""
    identifier = identifier or ("minecraft:" + key); states = dict(states or {})
    BLOCK_DEFS[key] = (identifier, states); BLOCK_RUNTIME[key] = block_state_hash(identifier, states)
    if key not in BLOCK_INDEX: BLOCK_INDEX[key] = len(BLOCK_KEYS); BLOCK_KEYS.append(key)

for _k in ("air", "stone", "grass_block", "dirt", "coarse_dirt", "sand", "gravel", "cobblestone", "oak_planks", "sandstone"):
    register_block(_k)
register_block("bedrock", states={"infiniburn_bit": (T_BYTE, 0)})
register_block("water", states={"liquid_depth": (T_INT, 0)})
register_block("oak_log", states={"pillar_axis": (T_STR, "y")})
register_block("oak_leaves", states={"persistent_bit": (T_BYTE, 0), "update_bit": (T_BYTE, 0)})

# ---------------------------------------------------------------- tools
# BlockToolType (PocketMine bit values)
TOOL_NONE = 0
TOOL_SWORD = 1 << 0
TOOL_SHOVEL = 1 << 1
TOOL_PICKAXE = 1 << 2
TOOL_AXE = 1 << 3
TOOL_SHEARS = 1 << 4
TOOL_HOE = 1 << 5

# block key -> (required tool type, required harvest level)
BLOCK_TOOL = {
    "stone": (TOOL_PICKAXE, 1), "cobblestone": (TOOL_PICKAXE, 1),
    "sandstone": (TOOL_PICKAXE, 1), "bedrock": (TOOL_PICKAXE, 7),
    "dirt": (TOOL_SHOVEL, 0), "coarse_dirt": (TOOL_SHOVEL, 0), "grass_block": (TOOL_SHOVEL, 0),
    "sand": (TOOL_SHOVEL, 0), "gravel": (TOOL_SHOVEL, 0),
    "oak_log": (TOOL_AXE, 0), "oak_planks": (TOOL_AXE, 0),
    "oak_leaves": (TOOL_NONE, 0), "water": (TOOL_NONE, 0), "air": (TOOL_NONE, 0),
}

# ToolTier: item-name prefix -> (harvest level, mining speed)
TOOL_TIERS = {
    "wooden": (1, 2), "stone": (2, 4), "iron": (3, 6), "diamond": (4, 8), "netherite": (5, 9),
}

# item key -> (tool type, harvest level, mining speed)
TOOLS = {}
for _kind, _bit in (("pickaxe", TOOL_PICKAXE), ("axe", TOOL_AXE), ("shovel", TOOL_SHOVEL)):
    for _tier, (_lvl, _speed) in TOOL_TIERS.items():
        TOOLS["%s_%s" % (_tier, _kind)] = (_bit, _lvl, _speed)
TOOLS["shears"] = (TOOL_SHEARS, 1, 15)

# ---------------------------------------------------------------- items, drops, hardness, sounds
# Runtime item ids come from the generated item type dictionary (pmmp/BedrockData
# required_item_list.json 2.15.0+bedrock-1.21.50) so they can never drift from the
# version of the game this server implements.
ITEM_RUNTIME = {k: item_runtime_id(k) for k in
                ("air", "stone", "grass_block", "dirt", "coarse_dirt", "sand", "gravel",
                 "cobblestone", "sandstone", "oak_planks", "oak_log", "oak_leaves",
                 "bedrock", "water", "stick", "flint", "shears")}
ITEM_RUNTIME.update({k: v for k, v in ((name, item_runtime_id(name)) for name in TOOLS) if v is not None})
ITEM_RUNTIME = {k: v for k, v in ITEM_RUNTIME.items() if v is not None}

RUNTIME_TO_KEY = {}    # network block id (unsigned) -> block key
ITEM_TO_KEY = {}       # legacy numeric item id -> item key
for _k, _rid in BLOCK_RUNTIME.items():
    RUNTIME_TO_KEY.setdefault(_rid & 0xFFFFFFFF, _k)
for _k, _iid in ITEM_RUNTIME.items():
    ITEM_TO_KEY.setdefault(_iid, _k)
    ITEM_TO_KEY.setdefault(_iid & 0xFFFF, _k)      # item ids travel as signed 16-bit

# Vanilla-style drops. oak_leaves is intentionally absent: it drops nothing without shears.
DROP_FOR_BLOCK = {
    "stone": [("cobblestone", 1)], "cobblestone": [("cobblestone", 1)],
    "dirt": [("dirt", 1)], "grass_block": [("dirt", 1)], "coarse_dirt": [("dirt", 1)],
    "sand": [("sand", 1)], "gravel": [("gravel", 1)], "sandstone": [("sandstone", 1)],
    "oak_log": [("oak_log", 1)], "oak_planks": [("oak_planks", 1)],
}
# Vanilla secondary drops: a matching tool has a chance of a bonus.
SECONDARY_DROP = {"coal_ore": [("coal", 1)], "iron_ore": [("iron_ingot", 1)]}

# Vanilla sound event ids per block material: (dig/break, step, place).
BLOCK_SOUND = {
    "stone": ("dig.stone", "step.stone", "place.stone"),
    "cobblestone": ("dig.stone", "step.stone", "place.stone"),
    "bedrock": ("dig.stone", "step.stone", "place.stone"),
    "dirt": ("dig.dirt", "step.dirt", "place.dirt"),
    "coarse_dirt": ("dig.dirt", "step.dirt", "place.dirt"),
    "grass_block": ("dig.grass", "step.grass", "place.grass"),
    "sand": ("dig.sand", "step.sand", "place.sand"),
    "gravel": ("dig.gravel", "step.gravel", "place.gravel"),
    "sandstone": ("dig.stone", "step.stone", "place.stone"),
    "oak_log": ("dig.wood", "step.wood", "place.wood"),
    "oak_planks": ("dig.wood", "step.wood", "place.wood"),
    "oak_leaves": ("dig.grass", "step.grass", "place.grass"),
    "water": ("dig.water", "step.water", "place.water"),
    "air": ("dig.grass", "step.grass", "place.grass"),
}
def block_sound(key, index):
    return (BLOCK_SOUND.get(key) or BLOCK_SOUND["air"])[index]

SOUND_BREAK, SOUND_STEP, SOUND_PLACE = 0, 1, 2

# PocketMine's BlockBreakInfo is authoritative for break timing. Infinity means unbreakable.
BLOCK_HARDNESS = {
    "stone": 1.5, "cobblestone": 2.0, "dirt": 0.5, "grass_block": 0.6,
    "coarse_dirt": 0.75, "sand": 0.5, "gravel": 0.6, "sandstone": 0.8,
    "oak_log": 2.0, "oak_leaves": 0.2, "bedrock": float("inf"), "water": float("inf"), "air": 0.0,
}

# PocketMine's BlockBreakInfo: hardness * 1.5 with the right tool, hardness * 5 with the wrong
# one, then divided by the tool's mining efficiency.
COMPATIBLE_TOOL_MULTIPLIER = 1.5
INCOMPATIBLE_TOOL_MULTIPLIER = 5.0

def tool_info(item_id):
    """(tool type, harvest level, mining speed) for an item id, or None for bare hands."""
    return TOOLS.get(item_key_for_id(item_id))

def tool_compatible(key, item_id):
    """PocketMine BlockBreakInfo::isToolCompatible - tool type and harvest level must both match."""
    required_type, required_level = BLOCK_TOOL.get(key, (TOOL_NONE, 0))
    if required_type == TOOL_NONE or required_level == 0:
        return True
    info = tool_info(item_id)
    if info is None: return False
    tool_type, harvest_level, _speed = info
    return bool(tool_type & required_type) and harvest_level >= required_level

def break_seconds(key, item_id=0, on_ground=True, flying=False, underwater=False):
    """Seconds to break `key` while holding `item_id`, exactly as PocketMine computes it.

    Returns None when the block cannot be broken at all, 0.0 when it breaks instantly.
    """
    hardness = BLOCK_HARDNESS.get(key)
    if hardness is None or hardness < 0 or not math.isfinite(hardness): return None
    if hardness == 0.0: return 0.0
    if tool_compatible(key, item_id):
        base = hardness * COMPATIBLE_TOOL_MULTIPLIER
    else:
        base = hardness * INCOMPATIBLE_TOOL_MULTIPLIER
    info = tool_info(item_id)
    if info is not None:
        required_type, _lvl = BLOCK_TOOL.get(key, (TOOL_NONE, 0))
        # getMiningEfficiency(compatible) - the wrong tool type gets no speed bonus.
        base /= info[2] if (required_type == TOOL_NONE or (info[0] & required_type)) else 1
    # SurvivalBlockBreakHandler penalties: mining airborne or underwater is much slower.
    if not on_ground and not flying: base *= 5.0
    if underwater: base *= 5.0
    return base

def drops_for(key, item_id=0):
    """Drops for a block, honouring the tool requirement like PocketMine's Block::getDrops."""
    if key in ("air", "water", "bedrock"): return []
    drops = list(DROP_FOR_BLOCK.get(key, []))
    extra = SECONDARY_DROP.get(key, [])
    if extra and tool_compatible(key, item_id): drops += extra
    required_type, required_level = BLOCK_TOOL.get(key, (TOOL_NONE, 0))
    if required_type != TOOL_NONE and required_level > 0 and not tool_compatible(key, item_id):
        return []
    return drops

def item_key_for_id(item_id):
    if item_id <= 0: return None
    return ITEM_TO_KEY.get(item_id if item_id <= 0x7FFF else item_id & 0xFFFF)

def block_key_from_runtime(runtime_id):
    """Reverse lookup for the runtime block id the client sends in placement transactions.

    The client's ItemStackDescriptor often has id == 0 and only carries the block runtime id,
    so the id alone is not enough to tell which block is being placed.
    """
    return RUNTIME_TO_KEY.get(runtime_id & 0xFFFFFFFF)

def item_key_from_id(item_id):
    """Reverse lookup for legacy numeric item ids."""
    key = item_key_for_id(item_id)
    return key if key in BLOCK_RUNTIME else None
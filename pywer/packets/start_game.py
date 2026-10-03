# ---------------------------------------------------------------- StartGamePacket
import struct, uuid
from .. import config
from ..util.serializer import ByteWriter
from ..util.nbt import EMPTY_NBT
from ..data.item_table import ITEM_TABLE
from ..world.terrain import SPAWN

def build_start_game(runtime_id):
    """Field order follows BedrockProtocol StartGamePacket for 1.21.50 (see README for confidence notes)."""
    w = ByteWriter()
    w.write_varint64(runtime_id)                 # actorUniqueId
    w.write_varuint64(runtime_id)                # actorRuntimeId
    w.write_varint32(config.GAMEMODE)            # player gamemode
    for v in (SPAWN[0] + 0.5, SPAWN[1] + 1.62, SPAWN[2] + 0.5): w.write_float(v)
    w.write_float(0.0).write_float(0.0)          # pitch, yaw
    # --- LevelSettings
    w.b += struct.pack("<q", -1)                 # seed
    w.write_u16_le(0).write_string("").write_varint32(0)   # SpawnSettings: biomeType, biomeName, dimension(overworld)
    w.write_varint32(1)                          # generator (infinite)
    w.write_varint32(config.GAMEMODE)            # world gamemode
    w.write_bool(False)                          # hardcore
    w.write_varint32(1)                          # difficulty
    w.write_varint32(SPAWN[0]).write_varuint32(SPAWN[1]).write_varint32(SPAWN[2])  # spawn block pos
    w.write_bool(True)                           # achievements disabled
    w.write_varint32(0)                          # editor world type
    w.write_bool(False).write_bool(False)        # createdInEditor, exportedFromEditor
    w.write_varint32(6000)                       # time
    w.write_varint32(0)                          # edu edition offer
    w.write_bool(False)                          # edu features
    w.write_string("")                           # edu product uuid
    w.write_float(0.0).write_float(0.0)          # rain, lightning
    w.write_bool(False)                          # confirmed platform locked content
    w.write_bool(True)                           # isMultiplayerGame
    w.write_bool(True)                           # LAN broadcast
    w.write_varint32(4).write_varint32(4)        # xbox / platform broadcast mode
    w.write_bool(True)                           # commands enabled
    w.write_bool(False)                          # texture packs required
    w.write_varuint32(0)                         # game rules
    w.write_u32_le(0).write_bool(False)          # experiments (count, previouslyToggled)
    w.write_bool(False).write_bool(False)        # bonus chest, start with map
    w.write_varint32(1)                          # default player permission (member)
    w.write_i32(4)                               # server chunk tick radius
    for _ in range(4): w.write_bool(False)       # locked BP, locked RP, from locked template, msa gamertags only
    for _ in range(2): w.write_bool(False)       # from world template, template option locked
    w.write_bool(False)                          # only spawn v1 villagers
    w.write_bool(False).write_bool(False)        # disabling personas, disabling custom skins
    w.write_bool(False)                          # mute emote announcements
    w.write_string(config.GAME_VERSION)          # vanilla version
    w.write_i32(0).write_i32(0)                  # limited world width/length
    w.write_bool(True)                           # new nether
    w.write_string("").write_string("")          # edu shared uri resource
    w.write_bool(False)                          # experimental gameplay override (optional absent)
    w.write_u8(0)                                # chat restriction level
    w.write_bool(False)                          # disable player interactions
    w.write_string("").write_string("").write_string("")   # serverIdentifier, worldIdentifier, scenarioIdentifier (1.21.50)
    # --- rest of StartGame
    w.write_string("minimal-level-id")           # level id
    w.write_string(config.SERVER_TITLE)          # world name
    w.write_string("")                           # premium world template id
    w.write_bool(False)                          # is trial
    w.write_varint32(1).write_varint32(0).write_bool(True)    # PlayerMovementSettings: SERVER_AUTHORITATIVE_V2 = 1, rewindHistorySize = 0,
    # serverAuthoritativeBlockBreaking = true. MUST be true or the client never sends
    # PlayerBlockAction START_BREAK/CONTINUE_DESTROY_BLOCK and breaking never completes.
    w.b += struct.pack("<q", 0)                  # current tick
    w.write_varint32(0)                          # enchantment seed
    w.write_varuint32(0)                         # block palette (empty, client uses built-in)
    w.write_varuint32(len(ITEM_TABLE))           # item type dictionary
    for _name, _rid, _cb in ITEM_TABLE:
        w.write_string(_name).write_i16(_rid).write_bool(_cb)
    w.write_string("")                           # multiplayer correlation id
    w.write_bool(True)                           # new inventory system
    w.write_string("pywer-v0.9.1dev") # server software version
    w.write_bytes(EMPTY_NBT)                     # player actor properties
    w.b += struct.pack("<Q", 0)                  # block palette checksum
    w.write_uuid(uuid.UUID(int=0))               # world template id
    w.write_bool(False)                          # client side chunk generation
    w.write_bool(config.USE_BLOCK_HASHES and config.TERRAIN)   # block network ids are hashes
    w.write_bool(False)                          # network permissions: disableClientSounds (false = client sounds on)
    return w.get()
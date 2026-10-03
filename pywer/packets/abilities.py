# ---------------------------------------------------------------- UpdateAbilitiesPacket / PlayerHotbarPacket
"""Player abilities bitmasks and UpdateAbilitiesPacket / PlayerHotbarPacket builders."""

from .. import config
from ..util.serializer import ByteWriter

# AbilitiesLayer ability bits (protocol 766)
ABILITY_BUILD = 0
ABILITY_MINE = 1
ABILITY_DOORS_AND_SWITCHES = 2
ABILITY_OPEN_CONTAINERS = 3
ABILITY_ATTACK_PLAYERS = 4
ABILITY_ATTACK_MOBS = 5
ABILITY_OPERATOR = 6
ABILITY_TELEPORT = 7
ABILITY_INVULNERABLE = 8
ABILITY_FLYING = 9
ABILITY_ALLOW_FLIGHT = 10
ABILITY_INFINITE_RESOURCES = 11
ABILITY_LIGHTNING = 12
ABILITY_FLY_SPEED = 13
ABILITY_WALK_SPEED = 14
ABILITY_MUTED = 15
ABILITY_WORLD_BUILDER = 16
ABILITY_NO_CLIP = 17
ABILITY_PRIVILEGED_BUILDER = 18


def ability_bits(gamemode=None, flying=False):
    """Enabled-ability bitmask for a player.

    PocketMine's comment on its own base layer: "ALL of these need to be set for the base
    layer, otherwise the client will cry". Leaving ABILITY_MINE unset makes the client refuse
    to break blocks and cancel the break immediately.
    """
    gamemode = config.GAMEMODE if gamemode is None else gamemode
    creative = gamemode in (1, 6)
    spectator = gamemode == 6
    bits = 0
    for ability in (
        ABILITY_BUILD,
        ABILITY_MINE,
        ABILITY_DOORS_AND_SWITCHES,
        ABILITY_OPEN_CONTAINERS,
        ABILITY_ATTACK_PLAYERS,
        ABILITY_ATTACK_MOBS,
    ):
        if not spectator:
            bits |= 1 << ability
    bits |= 1 << ABILITY_TELEPORT
    if creative:
        bits |= (1 << ABILITY_INVULNERABLE) | (1 << ABILITY_INFINITE_RESOURCES)
    if gamemode in (1, 6):
        bits |= (1 << ABILITY_ALLOW_FLIGHT) | (1 << ABILITY_NO_CLIP)
    if flying:
        bits |= 1 << ABILITY_FLYING
    return bits


def build_abilities_payload(unique_id, gamemode=None, flying=False, walk_speed=0.1, fly_speed=0.05):
    """AbilitiesData + one base layer (PlayerPermission::MEMBER, CommandPermission::NORMAL)."""
    bits = ability_bits(gamemode, flying)
    set_abilities = bits | (1 << ABILITY_FLY_SPEED) | (1 << ABILITY_WALK_SPEED)
    w = ByteWriter()
    w.write_i64(unique_id)
    w.write_u8(1).write_u8(0)  # command permission (operator), player permission (member)
    w.write_u8(1)  # one ability layer
    w.write_u16_le(1)  # LAYER_BASE
    w.write_u32_le(set_abilities).write_u32_le(set_abilities)
    w.write_float(fly_speed).write_float(walk_speed)
    return w.get()


def build_update_abilities(unique_id, **kw):
    """Sent separately on join: AddPlayer also carries abilities but only reaches other players."""
    return build_abilities_payload(unique_id, **kw)


def build_player_hotbar(slot, window_id=0, select=False):
    return ByteWriter().write_varuint32(slot).write_u8(window_id).write_bool(select).get()


def build_update_adventure_settings(
    no_attacking_mobs=False,
    no_attacking_players=False,
    world_immutable=False,
    show_name_tags=True,
    auto_jump=False,
):
    """UpdateAdventureSettingsPacket - PocketMine's syncAdventureSettings() values."""
    w = ByteWriter()
    for v in (no_attacking_mobs, no_attacking_players, world_immutable, show_name_tags, auto_jump):
        w.write_bool(v)
    return w.get()

# ---------------------------------------------------------------- AddPlayerPacket
"""AddPlayerPacket builder for spawning player actors in Bedrock clients."""

from .. import config
from ..util.serializer import ByteWriter, write_vec3
from .metadata import entity_metadata, write_metadata
from .abilities import build_abilities_payload


def build_add_player(p):
    w = ByteWriter()
    w.write_uuid(p.uuid)
    w.write_string(p.name)
    w.write_varuint64(p.rid)
    w.write_string("")
    # AddPlayerPacket carries the *feet* position, not eye position
    write_vec3(w, p.feet())
    write_vec3(w, (0.0, 0.0, 0.0))
    w.write_float(p.pitch)
    w.write_float(p.yaw)
    w.write_float(p.head_yaw)
    w.write_varint32(0)  # held item: air
    gamemode = getattr(p, "gamemode", config.GAMEMODE)
    if gamemode not in config.VALID_GAMEMODES:
        gamemode = 0
    w.write_varint32(gamemode)
    write_metadata(w, entity_metadata(p))  # flags, scale, bounding box
    w.write_varuint32(0)
    w.write_varuint32(0)  # synced properties (int, float)
    # abilities (UpdateAbilitiesPacket payload) - the *other* players see this player's
    # gamemode and flight state, so both come from the session, never from the config
    # default, or a restored creative player is rendered as survival by everyone else.
    w.write_bytes(
        build_abilities_payload(
            p.rid,
            gamemode=gamemode,
            flying=getattr(p, "flying", False),
            allow_flight=getattr(p, "allow_flight", None),
        )
    )
    w.write_varuint32(0)  # entity links
    w.write_string(str(p.client_data.get("DeviceId", "")))
    w.write_i32(int(p.client_data.get("DeviceOS", 0) or 0))
    return w.get()
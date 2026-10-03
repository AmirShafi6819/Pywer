# ---------------------------------------------------------------- AddPlayerPacket
from .. import config
from ..util.serializer import ByteWriter, write_vec3
from .metadata import entity_metadata, write_metadata
from .abilities import build_abilities_payload

def build_add_player(p):
    w = ByteWriter()
    w.write_uuid(p.uuid).write_string(p.name).write_varuint64(p.rid).write_string("")
    # AddPlayerPacket carries the *feet* position (Human::getOffsetPosition is only applied
    # by MovePlayer), not the eye position stored in p.pos.
    write_vec3(w, p.feet()); write_vec3(w, (0.0, 0.0, 0.0))
    w.write_float(p.pitch).write_float(p.yaw).write_float(p.head_yaw)
    w.write_varint32(0)                                         # held item: air
    w.write_varint32(config.GAMEMODE)
    write_metadata(w, entity_metadata(p))                       # flags (sneak/sprint/...), scale, bounding box
    w.write_varuint32(0).write_varuint32(0)                     # synced properties (int, float)
    # abilities (UpdateAbilitiesPacket payload)
    w.write_bytes(build_abilities_payload(p.rid))
    w.write_varuint32(0)                                        # entity links
    w.write_string(str(p.client_data.get("DeviceId", ""))).write_i32(int(p.client_data.get("DeviceOS", 0) or 0))
    return w.get()
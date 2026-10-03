# ---------------------------------------------------------------- entity movement / attribute packets
"""Movement, animation, attribute, and actor event packet builders."""

from ..util.serializer import ByteWriter, write_vec3
from ..player.movement import MODE_NORMAL, MODE_TELEPORT, MOVE_FLAG_GROUND, NETWORK_EYE_OFFSET


def build_move_player(p, feet=None, mode=MODE_NORMAL, tick=0):
    """MovePlayerPacket: PM sends feet position through Human::getOffsetPosition (+1.621Y)."""
    f = feet if feet is not None else p.feet()
    pos = (f[0], f[1] + NETWORK_EYE_OFFSET, f[2])
    w = ByteWriter()
    w.write_varuint64(p.rid)
    write_vec3(w, pos)
    w.write_float(p.pitch)
    w.write_float(p.yaw)
    w.write_float(p.head_yaw)
    w.write_u8(mode)
    w.write_bool(p.on_ground)
    w.write_varuint64(0)  # riding runtime id
    if mode == MODE_TELEPORT:
        w.write_i32(0)
        w.write_i32(0)  # teleport cause, source item type
    w.write_varuint64(tick)
    return w.get()


def _rot_byte(deg):
    return int(deg / (360 / 256)) & 0xFF


def build_move_actor_absolute(p):
    """Entity::broadcastMovement: player actors use feet/body position, not eye position."""
    w = ByteWriter()
    w.write_varuint64(p.rid)
    w.write_u8(MOVE_FLAG_GROUND if p.on_ground else 0)
    write_vec3(w, p.feet())
    w.write_u8(_rot_byte(p.pitch))
    w.write_u8(_rot_byte(p.yaw))
    w.write_u8(_rot_byte(p.head_yaw))
    return w.get()


def build_level_event(event_id, event_data, pos):
    w = ByteWriter()
    w.write_varint32(event_id)
    write_vec3(w, pos)
    w.write_varint32(event_data)
    return w.get()


def build_update_attributes(p):
    """PocketMine AttributeFactory/StandardEntityEventBroadcaster: default movement + health attributes."""
    entries = [
        ("minecraft:movement", 0.0, 3.402823466e38, 0.10, 0.0, 3.402823466e38, 0.10),
        ("minecraft:health", 0.0, 20.0, max(0.0, min(20.0, p.health)), 0.0, 20.0, 20.0),
        ("minecraft:knockback_resistance", 0.0, 1.0, 0.0, 0.0, 1.0, 0.0),
        ("minecraft:underwater_movement", 0.0, 3.402823466e38, 0.02, 0.0, 3.402823466e38, 0.02),
    ]
    w = ByteWriter()
    w.write_varuint64(p.rid)
    w.write_varuint32(len(entries))
    for ident, mn, mx, cur, dmn, dmx, default in entries:
        for v in (mn, mx, cur, dmn, dmx, default):
            w.write_float(v)
        w.write_string(ident)
        w.write_varuint32(0)
    w.write_varuint64(0)
    return w.get()


def build_animate(rid, action):
    """AnimatePacket: varint action *then* actor runtime id (protocol 766 order)."""
    w = ByteWriter()
    w.write_varint32(action)
    w.write_varuint64(rid)
    return w.get()


def build_actor_event(rid, event_id, data=0):
    """ActorEventPacket: runtime id, byte event id, varint data."""
    w = ByteWriter()
    w.write_varuint64(rid)
    w.write_u8(event_id)
    w.write_varint32(data)
    return w.get()


def build_set_actor_motion(rid, motion, tick=0):
    """SetActorMotionPacket: runtime id, motion vector, then the tick as an unsigned varlong."""
    w = ByteWriter()
    w.write_varuint64(rid)
    write_vec3(w, motion)
    w.write_varuint64(tick)
    return w.get()


def build_move_entity(rid, pos, flags=0):
    """MoveActorAbsolutePacket for a non-player actor (used by dropped item entities)."""
    w = ByteWriter()
    w.write_varuint64(rid)
    w.write_u8(flags)
    write_vec3(w, pos)
    w.write_u8(0)
    w.write_u8(0)
    w.write_u8(0)  # pitch, yaw, head yaw
    return w.get()


def build_mob_equipment(rid, item, inventory_slot, hotbar_slot, window_id, stack_id=0):
    """MobEquipmentPacket (server -> client hotbar sync), matching PocketMine syncSelectedHotbarSlot."""
    from ..protocol.inventory import build_inventory_stack

    w = ByteWriter()
    w.write_varuint64(rid)
    w.write_bytes(build_inventory_stack(item, stack_id))
    w.write_u8(inventory_slot)
    w.write_u8(hotbar_slot)
    w.write_u8(window_id)
    return w.get()

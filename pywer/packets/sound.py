# ---------------------------------------------------------------- PlaySoundPacket
"""PlaySoundPacket and LevelSoundEventPacket builders for Bedrock protocol 766."""

from ..util.serializer import ByteWriter, write_vec3


def build_play_sound(sound_name, pos, volume=1.0, pitch=1.0):
    """PlaySoundPacket for protocol 766 (bedrock-protocol 35.0.0).

    String sound event, block position, volume, pitch. Block position is x8 with
    an unsigned Y varint (PacketSerializer::putBlockPosition).
    """
    w = ByteWriter()
    w.write_string(sound_name)
    w.write_varint32(int(pos[0]) * 8)
    w.write_varuint32(int(pos[1]) * 8)
    w.write_varint32(int(pos[2]) * 8)
    w.write_float(volume)
    w.write_float(pitch)
    return w.get()


def build_level_sound_event(sound_id, pos, extra_data=-1, entity_type=":", disable_relative_volume=False):
    """LevelSoundEventPacket (protocol 766): numeric sound id, position, extra data, entity type."""
    w = ByteWriter()
    w.write_varuint32(sound_id)
    write_vec3(w, pos)
    w.write_varint32(extra_data)
    w.write_string(entity_type)
    w.write_bool(False)  # isBabyMob
    w.write_bool(disable_relative_volume)
    return w.get()

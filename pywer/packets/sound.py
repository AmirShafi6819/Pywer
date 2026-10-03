# ---------------------------------------------------------------- PlaySoundPacket
from ..util.serializer import ByteWriter, write_vec3

def build_play_sound(sound_name, pos, volume=1.0, pitch=1.0):
    """PlaySoundPacket for protocol 766 (bedrock-protocol 35.0.0).

    string sound event, block position, volume, pitch - and nothing else. The optional
    server sound handle only exists in later protocol versions; writing it here desyncs
    the client's batch parser and gets the player kicked.
    Block position is x8 with an *unsigned* Y varint (PacketSerializer::putBlockPosition).
    """
    w = ByteWriter()
    w.write_string(sound_name)
    w.write_varint32(int(pos[0]) * 8)
    w.write_varuint32(int(pos[1]) * 8)
    w.write_varint32(int(pos[2]) * 8)
    w.write_float(volume).write_float(pitch)
    return w.get()

def build_level_sound_event(sound_id, pos, extra_data=-1, entity_type=":", disable_relative_volume=False):
    """LevelSoundEventPacket (protocol 766): numeric sound id, position, extra data, entity type.

    This is what PocketMine plays while mining (LevelSoundEvent::HIT with the target block's
    network id), which is separate from the PlaySoundPacket used for the break itself.
    """
    w = ByteWriter()
    w.write_varuint32(sound_id)
    write_vec3(w, pos)
    w.write_varint32(extra_data)
    w.write_string(entity_type)
    w.write_bool(False)                                # isBabyMob
    w.write_bool(disable_relative_volume)
    return w.get()

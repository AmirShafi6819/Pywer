# ---------------------------------------------------------------- PlayerListPacket (add/remove)
from ..util.serializer import ByteWriter

def build_player_list_add(players):
    w = ByteWriter(); w.write_u8(0).write_varuint32(len(players))
    for p in players:
        w.write_uuid(p.uuid).write_varint64(p.rid).write_string(p.name).write_string("").write_string("")
        w.write_i32(int(p.client_data.get("DeviceOS", 0) or 0))
        w.write_bytes(p.skin_bytes)
        w.write_bool(False).write_bool(False).write_bool(False)   # teacher, host, sub client
    for _ in players: w.write_bool(True)                            # skin verified
    return w.get()

def build_player_list_remove(players):
    w = ByteWriter(); w.write_u8(1).write_varuint32(len(players))
    for p in players: w.write_uuid(p.uuid)
    return w.get()
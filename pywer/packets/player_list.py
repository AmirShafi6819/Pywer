# ---------------------------------------------------------------- PlayerListPacket (add/remove)
"""PlayerListPacket builders for adding and removing players from tab-list."""

from ..util.serializer import ByteWriter


def build_player_list_add(players):
    w = ByteWriter()
    w.write_u8(0)
    w.write_varuint32(len(players))
    for p in players:
        w.write_uuid(p.uuid)
        w.write_varint64(p.rid)
        w.write_string(p.name)
        w.write_string("")
        w.write_string("")
        w.write_i32(int(p.client_data.get("DeviceOS", 0) or 0))
        w.write_bytes(p.skin_bytes)
        w.write_bool(False)
        w.write_bool(False)
        w.write_bool(False)  # teacher, host, sub client
    for _ in players:
        w.write_bool(True)  # skin verified
    return w.get()


def build_player_list_remove(players):
    w = ByteWriter()
    w.write_u8(1)
    w.write_varuint32(len(players))
    for p in players:
        w.write_uuid(p.uuid)
    return w.get()
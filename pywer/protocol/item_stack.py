# ---------------------------------------------------------------- ItemStackWrapper (PacketSerializer)
from ..util.serializer import ByteWriter

def read_item_stack_wrapper(r):
    """PacketSerializer::getItemStackWrapper(), reduced to fields needed by pywer."""
    item_id = r.read_varint32()
    if item_id == 0:
        return {"id": 0, "count": 0, "meta": 0}
    count = r.read_u16_le(); meta = r.read_varuint32()
    has_net_id = r.read_bool()
    if has_net_id: r.read_varint32()
    block_runtime = r.read_varint32()
    raw_extra = r.read_string()
    return {"id": item_id, "count": count, "meta": meta, "block_runtime": block_runtime, "raw_extra": raw_extra}

def build_item_stack_descriptor(item_id, count=1, meta=0, block_runtime_id=0):
    # PacketSerializer::putItemStackWrapper() for a legacy item stack.
    w = ByteWriter(); w.write_varint32(item_id); w.write_u16_le(count); w.write_varuint32(meta)
    w.write_bool(False)
    w.write_varint32(block_runtime_id & 0xFFFFFFFF)
    w.write_string("")
    return w.get()
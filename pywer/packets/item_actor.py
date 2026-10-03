# ---------------------------------------------------------------- AddItemActorPacket (dropped items)
from ..util.serializer import ByteWriter, write_vec3
from ..world.blocks import ITEM_RUNTIME, BLOCK_RUNTIME
from ..protocol.item_stack import build_item_stack_descriptor

def build_add_item_actor(runtime_id, item_key, count, pos, velocity=(0.0, 0.0, 0.0)):
    item_id = ITEM_RUNTIME[item_key]
    block_runtime = BLOCK_RUNTIME.get(item_key, 0)
    w = ByteWriter(); w.write_varint64(runtime_id); w.write_varuint64(runtime_id)
    w.write_bytes(build_item_stack_descriptor(item_id, count, 0, block_runtime))
    write_vec3(w, pos); write_vec3(w, velocity)
    w.write_varuint32(0)  # ItemEntity network metadata is empty in this implementation
    w.write_bool(False)
    return w.get()
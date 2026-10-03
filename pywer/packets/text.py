# ---------------------------------------------------------------- TextPacket / chat sanitising
from ..util.serializer import ByteWriter

def build_text(ttype, source, message):
    w = ByteWriter(); w.write_u8(ttype).write_bool(False)
    if ttype in (1, 7, 8): w.write_string(source)
    w.write_string(message).write_string("").write_string("").write_string(message)
    return w.get()

def sanitize_chat(m):
    m = "".join(c for c in str(m) if c.isprintable() or c == " ")[:256].strip()
    return m
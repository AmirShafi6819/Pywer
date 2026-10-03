# ---------------------------------------------------------------- serializers
import struct, uuid

class ByteReader:
    def __init__(self, data, pos=0):
        self.d = data; self.p = pos
    def left(self): return len(self.d) - self.p
    def read_bytes(self, n):
        if n < 0 or self.p + n > len(self.d): raise ValueError("short read")
        b = self.d[self.p:self.p + n]; self.p += n; return b
    def _u(self, fmt, n): return struct.unpack(fmt, self.read_bytes(n))[0]
    def read_u8(self): return self._u("<B", 1)
    def read_i8(self): return self._u("<b", 1)
    def read_u16_le(self): return self._u("<H", 2)
    def read_u16_be(self): return self._u(">H", 2)
    def read_u24_le(self): return int.from_bytes(self.read_bytes(3), "little")
    def read_u32_le(self): return self._u("<I", 4)
    def read_u32_be(self): return self._u(">I", 4)
    def read_u64_le(self): return self._u("<Q", 8)
    def read_u64_be(self): return self._u(">Q", 8)
    def read_i32(self): return self._u("<i", 4)
    def read_i32_be(self): return self._u(">i", 4)
    def read_i16(self): return self._u("<h", 2)
    def read_i64(self): return self._u("<q", 8)
    def read_bool(self): return self.read_u8() != 0
    def read_float(self): return self._u("<f", 4)
    def read_double(self): return self._u("<d", 8)
    def read_varuint(self, maxbits):
        v = 0; s = 0
        while True:
            b = self.read_u8(); v |= (b & 0x7F) << s
            if not b & 0x80: return v
            s += 7
            if s >= maxbits + 7: raise ValueError("varint too long")
    def read_varuint32(self): return self.read_varuint(32)
    def read_varuint64(self): return self.read_varuint(64)
    def read_varint32(self):
        v = self.read_varuint32(); return (v >> 1) ^ -(v & 1)
    def read_varint64(self):
        v = self.read_varuint64(); return (v >> 1) ^ -(v & 1)
    def read_string(self): return self.read_bytes(self.read_varuint32()).decode("utf-8", "replace")
    def read_uuid(self):
        b = self.read_bytes(16)
        return uuid.UUID(bytes=b[:8][::-1] + b[8:][::-1])  # Bedrock: two LE u64

    def rest(self): return self.read_bytes(self.left())

class ByteWriter:
    def __init__(self): self.b = bytearray()
    def get(self): return bytes(self.b)
    def write_u8(self, v): self.b.append(v & 0xFF); return self
    def write_bool(self, v): return self.write_u8(1 if v else 0)
    def write_u16_le(self, v): self.b += struct.pack("<H", v); return self
    def write_u16_be(self, v): self.b += struct.pack(">H", v); return self
    def write_u24_le(self, v): self.b += (v & 0xFFFFFF).to_bytes(3, "little"); return self
    def write_u32_le(self, v): self.b += struct.pack("<I", v); return self
    def write_u32_be(self, v): self.b += struct.pack(">I", v); return self
    def write_u64_le(self, v): self.b += struct.pack("<Q", v); return self
    def write_u64_be(self, v): self.b += struct.pack(">Q", v); return self
    def write_i16(self, v): self.b += struct.pack("<h", v); return self
    def write_i64(self, v): self.b += struct.pack("<q", v); return self
    def write_i32(self, v): self.b += struct.pack("<i", v); return self
    def write_i32_be(self, v): self.b += struct.pack(">i", v); return self
    def write_float(self, v): self.b += struct.pack("<f", v); return self
    def write_varuint32(self, v):
        v &= 0xFFFFFFFF
        while True:
            if v < 0x80: self.b.append(v); return self
            self.b.append((v & 0x7F) | 0x80); v >>= 7
    def write_varuint64(self, v):
        v &= 0xFFFFFFFFFFFFFFFF
        while True:
            if v < 0x80: self.b.append(v); return self
            self.b.append((v & 0x7F) | 0x80); v >>= 7
    def write_varint32(self, v): return self.write_varuint32(((v << 1) ^ (v >> 31)) & 0xFFFFFFFF)
    def write_varint64(self, v): return self.write_varuint64(((v << 1) ^ (v >> 63)) & 0xFFFFFFFFFFFFFFFF)
    def write_string(self, s):
        if isinstance(s, str): s = s.encode("utf-8")
        self.write_varuint32(len(s)); self.b += s; return self
    def write_uuid(self, u):
        b = u.bytes; self.b += b[:8][::-1] + b[8:][::-1]; return self
    def write_bytes(self, d): self.b += d; return self

def write_vec3(w, v):
    for c in v: w.write_float(c)
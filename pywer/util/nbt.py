# ---------------------------------------------------------------- little-endian NBT (network variant)
"""Little-endian NBT encoder (network variant) and block state hashing."""

import struct

EMPTY_NBT = b"\x0a\x00\x00"  # network NBT: TAG_Compound, name "", TAG_End
T_BYTE, T_INT, T_STR = 1, 3, 8


def _le_str(s):
    b = s.encode("utf-8")
    return struct.pack("<H", len(b)) + b


def _le_value(t, v):
    if t == T_BYTE:
        return struct.pack("<b", v)
    if t == T_INT:
        return struct.pack("<i", v)
    if t == T_STR:
        return _le_str(v)
    raise ValueError("unsupported nbt tag %r" % t)


def block_state_hash(identifier, states):
    """Network block id (signed int32) of a block state, same algorithm as Dragonfly / CloudburstMC."""
    out = bytearray(b"\x0a\x00\x00")  # root compound, empty name
    out += bytes([T_STR]) + _le_str("name") + _le_str(identifier)
    out += bytes([10]) + _le_str("states")
    for k in sorted(states):
        t, v = states[k]
        out += bytes([t]) + _le_str(k) + _le_value(t, v)
    out += b"\x00\x00"  # end of states, end of root
    h = 0x811C9DC5
    for byte in out:
        h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
    return h - (1 << 32) if h >= (1 << 31) else h
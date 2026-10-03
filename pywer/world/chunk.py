# ---- chunk building / block update packets
from .. import config
from ..util.serializer import ByteWriter
from .blocks import BLOCK_INDEX, BLOCK_RUNTIME, BLOCK_KEYS
from .terrain import tree_blocks, column_layers
from .state import EDITS, CHUNK_CACHE

def _pack_storage(cells, palette):
    """One paletted block storage (network format). palette = list of signed runtime ids, cells index into it."""
    w = ByteWriter()
    if len(palette) == 1:
        w.write_u8(1); w.write_varint32(palette[0]); return w.get()    # bits=0: single entry, no words
    bits = next(b for b in (1, 2, 3, 4, 5, 6, 8, 16) if (1 << b) >= len(palette))
    per = 32 // bits; words = [0] * (-(-4096 // per))
    for i, v in enumerate(cells):
        if v: words[i // per] |= v << ((i % per) * bits)
    w.write_u8((bits << 1) | 1)
    for x in words: w.write_u32_le(x)
    w.write_varint32(len(palette))
    for rid in palette: w.write_varint32(rid)
    return w.get()

def build_chunk(cx, cz):
    if not config.TERRAIN: return build_empty_chunk(cx, cz)
    pkt = CHUNK_CACHE.get((cx, cz))
    if pkt is not None: return pkt
    overlay = {}                                                          # (lx, y, lz) -> key
    for (wx, y, wz), key in tree_blocks(cx, cz).items(): overlay[(wx & 15, y, wz & 15)] = key
    overlay.update(EDITS.get((cx, cz), {}))
    cols = {}; top = config.SEA_LEVEL
    for lx in range(16):
        for lz in range(16):
            cols[(lx, lz)] = column_layers(cx * 16 + lx, cz * 16 + lz); top = max(top, cols[(lx, lz)][-1][1])
    if overlay: top = max(top, max(y for (_, y, _) in overlay))
    top_sub = min(top, config.MAX_Y) >> 4
    air = BLOCK_INDEX["air"]; sub = bytearray()
    for sy in range(-4, top_sub + 1):
        base = sy * 16; cells = [air] * 4096
        for (lx, lz), layers in cols.items():
            col = (lx << 8) | (lz << 4)
            for y0, y1, key in layers:                                    # later layers overwrite earlier ones
                a = max(y0, base); b = min(y1, base + 15)
                if a <= b: i = BLOCK_INDEX[key]; cells[col + a - base:col + b - base + 1] = [i] * (b - a + 1)
        for (lx, y, lz), key in overlay.items():
            if (y >> 4) == sy: cells[(lx << 8) | (lz << 4) | (y & 15)] = BLOCK_INDEX[key]
        used = sorted(set(cells)); remap = {g: n for n, g in enumerate(used)}
        if len(used) > 1: cells = [remap[c] for c in cells]
        sub += b"\x08\x01" + _pack_storage(cells, [BLOCK_RUNTIME[BLOCK_KEYS[g]] for g in used])
    payload = bytearray(sub)
    for _ in range(24): payload += b"\x01" + bytes([config.PLAINS_BIOME << 1])  # biome palettes -4..19 (single entry, zigzag)
    payload.append(0)                                                    # border blocks
    w = ByteWriter(); w.write_varint32(cx).write_varint32(cz).write_varint32(0)
    w.write_varuint32(top_sub + 4 + 1).write_bool(False).write_string(bytes(payload))
    pkt = w.get()
    if len(CHUNK_CACHE) > 3000: CHUNK_CACHE.pop(next(iter(CHUNK_CACHE)))
    CHUNK_CACHE[(cx, cz)] = pkt
    return pkt

def build_update_block(x, y, z, key):
    """UpdateBlockPacket: signed x/z, *unsigned* y, unsigned runtime id (BedrockProtocol UpdateBlockPacket.php)."""
    w = ByteWriter(); w.write_varint32(x).write_varuint32(y & 0xFFFFFFFF).write_varint32(z)
    w.write_varuint32(BLOCK_RUNTIME[key] & 0xFFFFFFFF).write_varuint32(2).write_varuint32(0)   # flags=NETWORK, layer 0
    return w.get()

def build_empty_chunk(x, z):
    payload = bytearray()
    for _ in range(24):                          # overworld -4..19, all biomes must be written
        payload += b"\x01" + bytes([0 << 1])    # bits=0 (runtime flag), single palette entry: biome 0 (zigzag)
    payload.append(0)                            # border block count
    w = ByteWriter(); w.write_varint32(x).write_varint32(z).write_varint32(0)   # pos, dimension
    w.write_varuint32(0)                         # subchunk count: none (all air)
    w.write_bool(False)                          # cache disabled
    w.write_string(bytes(payload))
    return w.get()
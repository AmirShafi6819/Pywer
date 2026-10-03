# ---------------------------------------------------------------- entity network metadata (SetActorData)
from ..util.serializer import ByteWriter
from ..protocol.flags import (MF_NAMETAG, MF_ALWAYS_NAMETAG, MF_BREATHING, MF_COLLISION, MF_GRAVITY,
                              MF_SNEAKING, MF_SPRINTING, MF_GLIDING, MF_SWIMMING, MF_CRAWLING)
from ..player.movement import player_size

def entity_metadata_empty():
    return b"\\x00"

def entity_flags(p):
    """FLAGS (key 0) + FLAGS2 (key 92) of a player, as Entity/Living::syncNetworkData sets them."""
    lo = 0; hi = 0
    for bit, on in ((MF_NAMETAG, True), (MF_ALWAYS_NAMETAG, False), (MF_BREATHING, True), (MF_COLLISION, True), (MF_GRAVITY, True),
                    (MF_SNEAKING, p.sneaking), (MF_SPRINTING, p.sprinting), (MF_GLIDING, p.gliding), (MF_SWIMMING, p.swimming),
                    (MF_CRAWLING, p.crawling)):
        if on:
            if bit >= 64: hi |= 1 << (bit - 64)
            else: lo |= 1 << bit
    return lo, hi

def entity_metadata(p):
    """[(key, type, value)] - types: 3 float, 4 string, 7 long. Includes the bounding box that
    changes with sneak/swim/glide and the nametag.

    Keys must be sent in ascending numeric order: since 1.18.10 the client reacts
    differently to the same data in a different order (StandardEntityEventBroadcaster
    ksorts for exactly this reason - sending HEIGHT before FLAGS while unsetting the
    SWIMMING flag gives the player a hitbox glitch).
    """
    lo, hi = entity_flags(p); w, h = player_size(p)
    md = [(0, 7, lo), (4, 4, p.name), (38, 3, 1.0), (53, 3, w), (54, 3, h)]
    if hi: md.append((92, 7, hi))
    return sorted(md, key=lambda e: e[0])

def write_metadata(w, md):
    w.write_varuint32(len(md))
    for key, typ, val in md:
        w.write_varuint32(key).write_varuint32(typ)
        if typ == 7: w.write_varint64(val)
        elif typ == 3: w.write_float(val)
        elif typ == 4: w.write_string(val)
    return w

def build_set_actor_data(p):
    w = ByteWriter(); w.write_varuint64(p.rid); write_metadata(w, entity_metadata(p))
    w.write_varuint32(0).write_varuint32(0)               # synced properties (int, float)
    w.write_varuint64(0)                                  # tick
    return w.get()
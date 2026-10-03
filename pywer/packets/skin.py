# ---------------------------------------------------------------- player skin / PlayerList packets
"""Player skin data decoder and serializer for PlayerSkinPacket / PlayerListPacket."""

import base64
import uuid
from ..util.serializer import ByteWriter
from ..log import log


def _b64(v):
    try:
        v = str(v or "")
        return base64.b64decode(v + "=" * (-len(v) % 4))
    except Exception:
        return b""


def _img(w, h, data):
    return ByteWriter().write_i32(int(w)).write_i32(int(h)).write_string(data).get()


def build_skin(cd):
    """SkinData wire format (PacketSerializer::putSkin, 1.21.50) built from the clientData JWT."""
    w = ByteWriter()
    try:
        sd = _b64(cd.get("SkinData"))
        sw = int(cd.get("SkinImageWidth", 0))
        sh = int(cd.get("SkinImageHeight", 0))
        if not sd or sw * sh * 4 != len(sd):
            raise ValueError("bad skin image")
        w.write_string(str(cd.get("SkinId", "")))
        w.write_string(str(cd.get("PlayFabId", "")))
        w.write_string(_b64(cd.get("SkinResourcePatch")))
        w.write_bytes(_img(sw, sh, sd))
        anims = cd.get("AnimatedImageData") or []
        w.write_i32(len(anims))
        for a in anims:
            w.write_bytes(_img(a.get("ImageWidth", 0), a.get("ImageHeight", 0), _b64(a.get("Image"))))
            w.write_i32(int(a.get("Type", 0)))
            w.write_float(float(a.get("Frames", 0)))
            w.write_i32(int(a.get("AnimationExpression", 0)))
        w.write_bytes(_img(cd.get("CapeImageWidth", 0), cd.get("CapeImageHeight", 0), _b64(cd.get("CapeData"))))
        w.write_string(_b64(cd.get("SkinGeometryData")))
        w.write_string(_b64(cd.get("SkinGeometryDataEngineVersion")))
        w.write_string(_b64(cd.get("SkinAnimationData")))
        w.write_string(str(cd.get("CapeId", "")))
        w.write_string(str(uuid.uuid4()))  # full skin id
        w.write_string(str(cd.get("ArmSize", "wide")))
        w.write_string(str(cd.get("SkinColor", "#0")))
        pieces = cd.get("PersonaPieces") or []
        w.write_i32(len(pieces))
        for p in pieces:
            w.write_string(str(p.get("PieceId", "")))
            w.write_string(str(p.get("PieceType", "")))
            w.write_string(str(p.get("PackId", "")))
            w.write_bool(bool(p.get("IsDefault", False)))
            w.write_string(str(p.get("ProductId", "")))
        tints = cd.get("PieceTintColors") or []
        w.write_i32(len(tints))
        for t in tints:
            w.write_string(str(t.get("PieceType", "")))
            cols = t.get("Colors") or []
            w.write_i32(len(cols))
            for c in cols:
                w.write_string(str(c))
        w.write_bool(bool(cd.get("PremiumSkin", False)))
        w.write_bool(bool(cd.get("PersonaSkin", False)))
        w.write_bool(bool(cd.get("CapeOnClassicSkin", False)))
        w.write_bool(True)
        w.write_bool(bool(cd.get("OverrideSkin", True)))
        return w.get()
    except Exception as e:
        log("Player", "skin fallback (%r)" % e)
        w = ByteWriter()
        w.write_string("Standard_Custom")
        w.write_string("")
        w.write_string('{"geometry":{"default":"geometry.humanoid.custom"}}')
        w.write_bytes(_img(64, 64, b"\x80\x80\x80\xff" * (64 * 64)))
        w.write_i32(0)
        w.write_bytes(_img(0, 0, b""))
        w.write_string("")
        w.write_string("")
        w.write_string("")
        w.write_string("")
        w.write_string(str(uuid.uuid4()))
        w.write_string("wide")
        w.write_string("#0")
        w.write_i32(0)
        w.write_i32(0)
        for v in (False, False, False, True, True):
            w.write_bool(v)
        return w.get()
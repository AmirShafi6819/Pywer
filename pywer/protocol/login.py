# ---------------------------------------------------------------- LoginPacket decoding
"""LoginPacket decoder, Mojang certificate chain extraction, and client data parser."""

import json
from ..util.serializer import ByteReader
from ..crypto.jwt import jwt_parse
from ..log import log


def sanitize_name(n):
    n = "".join(c for c in str(n) if c.isprintable() and c not in "\r\n\t")[:16].strip()
    return n or "Player"


def parse_login(body):
    """Decode LoginPacket payload (after the packet ID)."""
    r = ByteReader(body)
    proto = r.read_i32_be()
    blob = ByteReader(r.read_bytes(r.read_varuint32()))
    chain_json = blob.read_bytes(blob.read_u32_le()).decode("utf-8", "replace")
    client_jwt = blob.read_bytes(blob.read_u32_le()).decode("utf-8", "replace")

    root = json.loads(chain_json)
    if "Certificate" in root:
        root = json.loads(root["Certificate"])
    chain = root.get("chain", [])

    info = {
        "protocol": proto,
        "name": "Player",
        "xuid": "",
        "identity": None,
        "identity_key": None,
        "client_key": None,
        "client_data": {},
    }

    for tok in chain:
        try:
            _h, p = jwt_parse(tok)
        except Exception:
            continue
        if "identityPublicKey" in p:
            info["identity_key"] = p["identityPublicKey"]
        ed = p.get("extraData")
        if isinstance(ed, dict):
            info["name"] = ed.get("displayName", info["name"])
            info["xuid"] = ed.get("XUID", "")
            info["identity"] = ed.get("identity")

    try:
        h, cd = jwt_parse(client_jwt)
        info["client_data"] = cd
        info["client_key"] = h.get("x5u")
    except Exception as e:
        log("Login", "clientData JWT parse failed: %r" % e)

    info["name"] = sanitize_name(info["name"])
    return info
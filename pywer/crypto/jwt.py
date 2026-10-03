# ---------------------------------------------------------------- JWT / base64url helpers
"""JSON Web Token (JWT) encode and decode helpers using base64url and ES384."""

import base64
import json
from .ec import es384_sign


def b64u_enc(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def jwt_parse(tok):
    h, p, _s = tok.split(".")
    return json.loads(b64u_dec(h)), json.loads(b64u_dec(p))


def jwt_make_es384(d, header, payload):
    header_json = json.dumps(header, separators=(",", ":")).encode()
    payload_json = json.dumps(payload, separators=(",", ":")).encode()
    si = b64u_enc(header_json) + "." + b64u_enc(payload_json)
    signature = es384_sign(d, si.encode())
    return si + "." + b64u_enc(signature)
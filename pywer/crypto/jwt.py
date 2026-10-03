# ---------------------------------------------------------------- JWT / base64url helpers
import base64, json
from .ec import es384_sign

def b64u_enc(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def b64u_dec(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
def jwt_parse(tok):
    h, p, _s = tok.split(".")
    return json.loads(b64u_dec(h)), json.loads(b64u_dec(p))
def jwt_make_es384(d, header, payload):
    si = (b64u_enc(json.dumps(header, separators=(",", ":")).encode()) + "." +
          b64u_enc(json.dumps(payload, separators=(",", ":")).encode()))
    return si + "." + b64u_enc(es384_sign(d, si.encode()))
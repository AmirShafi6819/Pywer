# ---------------------------------------------------------------- NIST P-384 / ECDH / ES384
import hashlib, secrets

# NIST P-384
P384_P = 2 ** 384 - 2 ** 128 - 2 ** 96 + 2 ** 32 - 1
P384_A = P384_P - 3
P384_B = 0xb3312fa7e23ee7e4988e056be3f82d19181d9c6efe8141120314088f5013875ac656398d8a2ed19d2a85c8edd3ec2aef
P384_N = 0xffffffffffffffffffffffffffffffffffffffffffffffffc7634d81f4372ddf581a0db248b0a77aecec196accc52973
P384_G = (0xaa87ca22be8b05378eb1c71ef320ad746e1d3b628ba79b9859f741e082542a385502f25dbf55296c3a545e3872760ab7,
          0x3617de4a96262c6f5d9e98bf9292dc29f8f41dbd289a147ce9da3113b5f0b8c00a60b1ce1d7e819d7a431d7c90ea0e5f)
SPKI_P384_PREFIX = bytes.fromhex("3076301006072a8648ce3d020106052b81040022036200")

def _inv(x, m): return pow(x, m - 2, m)
def ec_on_curve(Pt):
    x, y = Pt; return (y * y - (x * x * x + P384_A * x + P384_B)) % P384_P == 0
def ec_add(A, B):
    if A is None: return B
    if B is None: return A
    x1, y1 = A; x2, y2 = B
    if x1 == x2:
        if (y1 + y2) % P384_P == 0: return None
        l = (3 * x1 * x1 + P384_A) * _inv(2 * y1, P384_P) % P384_P
    else:
        l = (y2 - y1) * _inv(x2 - x1, P384_P) % P384_P
    x3 = (l * l - x1 - x2) % P384_P
    return (x3, (l * (x1 - x3) - y1) % P384_P)
def ec_mul(k, Pt):
    R = None
    while k:
        if k & 1: R = ec_add(R, Pt)
        Pt = ec_add(Pt, Pt); k >>= 1
    return R
def ec_keygen():
    d = secrets.randbelow(P384_N - 1) + 1
    return d, ec_mul(d, P384_G)
def pub_to_spki(Pt): return SPKI_P384_PREFIX + b"\x04" + Pt[0].to_bytes(48, "big") + Pt[1].to_bytes(48, "big")
def spki_to_pub(der):
    if len(der) != 120 or not der.startswith(SPKI_P384_PREFIX) or der[23] != 4: raise ValueError("not a P-384 SPKI key")
    Pt = (int.from_bytes(der[24:72], "big"), int.from_bytes(der[72:120], "big"))
    if not ec_on_curve(Pt): raise ValueError("point not on curve")
    return Pt
def ecdh(d, Pub): return ec_mul(d, Pub)[0].to_bytes(48, "big")
def es384_sign(d, msg):
    z = int.from_bytes(hashlib.sha384(msg).digest(), "big")
    while True:
        k = secrets.randbelow(P384_N - 1) + 1
        r = ec_mul(k, P384_G)[0] % P384_N
        if r == 0: continue
        s = _inv(k, P384_N) * (z + r * d) % P384_N
        if s: return r.to_bytes(48, "big") + s.to_bytes(48, "big")
def es384_verify(Pub, msg, sig):
    r = int.from_bytes(sig[:48], "big"); s = int.from_bytes(sig[48:], "big")
    if not (0 < r < P384_N and 0 < s < P384_N): return False
    z = int.from_bytes(hashlib.sha384(msg).digest(), "big"); w = _inv(s, P384_N)
    Pt = ec_add(ec_mul(z * w % P384_N, P384_G), ec_mul(r * w % P384_N, Pub))
    return Pt is not None and Pt[0] % P384_N == r
# ---------------------------------------------------------------- NIST P-384 / ECDH / ES384
"""Pure-Python implementation of NIST P-384 elliptic curve cryptography.

Provides ECDH key agreement and ES384 digital signature creation / verification.
"""

import hashlib
import secrets

# NIST P-384 parameters
P384_P = 2**384 - 2**128 - 2**96 + 2**32 - 1
P384_A = P384_P - 3
P384_B = 0xB3312FA7E23EE7E4988E056BE3F82D19181D9C6EFE8141120314088F5013875AC656398D8A2ED19D2A85C8EDD3EC2AEF
P384_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFC7634D81F4372DDF581A0DB248B0A77AECEC196ACCC52973
P384_G = (
    0xAA87CA22BE8B05378EB1C71EF320AD746E1D3B628BA79B9859F741E082542A385502F25DBF55296C3A545E3872760AB7,
    0x3617DE4A96262C6F5D9E98BF9292DC29F8F41DBD289A147CE9DA3113B5F0B8C00A60B1CE1D7E819D7A431D7C90EA0E5F,
)
SPKI_P384_PREFIX = bytes.fromhex("3076301006072a8648ce3d020106052b81040022036200")


def _inv(x, m):
    return pow(x, m - 2, m)


def ec_on_curve(point):
    if point is None:
        return False
    x, y = point
    return (y * y - (x * x * x + P384_A * x + P384_B)) % P384_P == 0


def ec_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P384_P == 0:
            return None
        slope = (3 * x1 * x1 + P384_A) * _inv(2 * y1, P384_P) % P384_P
    else:
        slope = (y2 - y1) * _inv(x2 - x1, P384_P) % P384_P
    x3 = (slope * slope - x1 - x2) % P384_P
    y3 = (slope * (x1 - x3) - y1) % P384_P
    return (x3, y3)


def ec_mul(k, point):
    result = None
    while k:
        if k & 1:
            result = ec_add(result, point)
        point = ec_add(point, point)
        k >>= 1
    return result


def ec_keygen():
    d = secrets.randbelow(P384_N - 1) + 1
    return d, ec_mul(d, P384_G)


def pub_to_spki(point):
    return SPKI_P384_PREFIX + b"\x04" + point[0].to_bytes(48, "big") + point[1].to_bytes(48, "big")


def spki_to_pub(der):
    if len(der) != 120 or not der.startswith(SPKI_P384_PREFIX) or der[23] != 4:
        raise ValueError("not a P-384 SPKI key")
    point = (int.from_bytes(der[24:72], "big"), int.from_bytes(der[72:120], "big"))
    if not ec_on_curve(point):
        raise ValueError("point not on curve")
    return point


def ecdh(d, pub):
    shared_point = ec_mul(d, pub)
    return shared_point[0].to_bytes(48, "big")


def es384_sign(d, msg):
    z = int.from_bytes(hashlib.sha384(msg).digest(), "big")
    while True:
        k = secrets.randbelow(P384_N - 1) + 1
        r = ec_mul(k, P384_G)[0] % P384_N
        if r == 0:
            continue
        s = _inv(k, P384_N) * (z + r * d) % P384_N
        if s:
            return r.to_bytes(48, "big") + s.to_bytes(48, "big")


def es384_verify(pub, msg, sig):
    r = int.from_bytes(sig[:48], "big")
    s = int.from_bytes(sig[48:], "big")
    if not (0 < r < P384_N and 0 < s < P384_N):
        return False
    z = int.from_bytes(hashlib.sha384(msg).digest(), "big")
    w = _inv(s, P384_N)
    point = ec_add(ec_mul(z * w % P384_N, P384_G), ec_mul(r * w % P384_N, pub))
    return point is not None and point[0] % P384_N == r
# ---------------------------------------------------------------- AES-256 (encrypt-only) + CTR mode
"""Pure-Python AES-256 cipher (encrypt-only) and AES-CTR mode."""


def _rotl(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _build_sbox():
    sbox = [0] * 256
    p = 1
    q = 1
    while True:
        p = (p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q = (q ^ (q << 1)) & 0xFF
        q = (q ^ (q << 2)) & 0xFF
        q = (q ^ (q << 4)) & 0xFF
        if q & 0x80:
            q ^= 0x09
        sbox[p] = (q ^ _rotl(q, 1) ^ _rotl(q, 2) ^ _rotl(q, 3) ^ _rotl(q, 4) ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


SBOX = _build_sbox()


def _xt(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else (a << 1)


class AES256:
    def __init__(self, key):
        assert len(key) == 32
        w = [list(key[i : i + 4]) for i in range(0, 32, 4)]
        rcon = 1
        for i in range(8, 60):
            t = list(w[i - 1])
            if i % 8 == 0:
                t = t[1:] + t[:1]
                t = [SBOX[x] for x in t]
                t[0] ^= rcon
                rcon = _xt(rcon)
            elif i % 8 == 4:
                t = [SBOX[x] for x in t]
            w.append([a ^ b for a, b in zip(w[i - 8], t)])
        self.rk = [sum(w[r * 4 : r * 4 + 4], []) for r in range(15)]

    def encrypt_block(self, blk):
        s = [a ^ b for a, b in zip(blk, self.rk[0])]
        for r in range(1, 15):
            s = [SBOX[x] for x in s]
            s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]  # ShiftRows (column-major)
            if r != 14:
                o = []
                for c in range(0, 16, 4):
                    a0, a1, a2, a3 = s[c : c + 4]
                    o += [
                        _xt(a0) ^ _xt(a1) ^ a1 ^ a2 ^ a3,
                        a0 ^ _xt(a1) ^ _xt(a2) ^ a2 ^ a3,
                        a0 ^ a1 ^ _xt(a2) ^ _xt(a3) ^ a3,
                        _xt(a0) ^ a0 ^ a1 ^ a2 ^ _xt(a3),
                    ]
                s = o
            s = [a ^ b for a, b in zip(s, self.rk[r])]
        return bytes(s)


class AESCTR:
    def __init__(self, key, iv16):
        self.aes = AES256(key)
        self.ctr = int.from_bytes(iv16, "big")
        self.ks = b""

    def process(self, data):
        out = bytearray()
        for byte in data:
            if not self.ks:
                self.ks = self.aes.encrypt_block(self.ctr.to_bytes(16, "big"))
                self.ctr = (self.ctr + 1) & ((1 << 128) - 1)
            out.append(byte ^ self.ks[0])
            self.ks = self.ks[1:]
        return bytes(out)
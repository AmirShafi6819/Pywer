# ---------------------------------------------------------------- crypto (pure python)
import hashlib, struct
from .aes import AESCTR

class BedrockCipher:
    """Bedrock encryption: key=sha256(salt+secret); AES-256-CTR, iv=key[:12]+00000002;
    each batch gets 8-byte checksum sha256(counter_le64 + plaintext + key)[:8]."""
    def __init__(self, salt, secret):
        self.key = hashlib.sha256(salt + secret).digest()
        iv = self.key[:12] + b"\x00\x00\x00\x02"
        self.enc = AESCTR(self.key, iv); self.dec = AESCTR(self.key, iv)
        self.sc = 0; self.rc = 0
    def _cs(self, counter, data):
        return hashlib.sha256(struct.pack("<Q", counter) + data + self.key).digest()[:8]
    def encrypt(self, data):
        out = self.enc.process(data + self._cs(self.sc, data)); self.sc += 1; return out
    def decrypt(self, data):
        if len(data) < 9: raise ValueError("encrypted payload too short")
        pt = self.dec.process(data); body, cs = pt[:-8], pt[-8:]
        if cs != self._cs(self.rc, body): raise ValueError("bad checksum")
        self.rc += 1; return body
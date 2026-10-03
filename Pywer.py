#!/usr/bin/env python3
# Minecraft Bedrock 1.21.50 (protocol 766) minimal server - STAGE 1
# RakNet + NetworkSettings + Login(offline) + encrypted handshake + PlayStatus(LoginSuccess)
# Python standard library only.
import socket, struct, zlib, hashlib, base64, json, time, random, secrets, select, sys, uuid, math

DEBUG = False          # connection-level debug (hex of important packets)
DEBUG_PACKETS = False  # packet tracing disabled by default; only protocol errors are logged
MAX_PLAYERS = 8
PORT = 19132
PROTOCOL = 766
GAME_VERSION = "1.21.50"
SERVER_TITLE = "§epywer-v0.9.1dev"
ENCRYPTION = True
COMPRESSION_THRESHOLD = 256
SPAWN = (0, 100, 0)
GAMEMODE = 0                 # 0 survival, 1 creative
MAX_RADIUS = 4               # chunk radius streamed around each player
CHUNKS_PER_TICK = 4          # new chunks sent per movement packet while streaming
TERRAIN = True              # False = old behaviour (empty world, spawn 0,100,0) - use it to check if a problem comes from the terrain
USE_BLOCK_HASHES = True      # network block ids = FNV-1a hash of the block state (see blocks section)
SEND_ACTOR_IDS = False       # needs real data files (not in the PocketMine zip); try True later
SEND_BIOME_DEFS = False      # needs real biome_definitions.nbt; try True later
SEND_CREATIVE = False        # needs real creative items; try True later
EMPTY_NBT = b"\x0a\x00\x00"   # network NBT: TAG_Compound, name "", TAG_End
RAKNET_MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")

def log(tag, msg):
    print("[INFO] [%s] %s" % (tag, msg), flush=True)

def dbg(tag, msg, data=None):
    if DEBUG:
        extra = ""
        if data is not None:
            extra = " len=%d %s%s" % (len(data), data[:48].hex(), "..." if len(data) > 48 else "")
        print("[DEBUG] [%s] %s%s" % (tag, msg, extra), flush=True)

# ---------------------------------------------------------------- serializers
class ByteReader:
    def __init__(self, data, pos=0):
        self.d = data; self.p = pos
    def left(self): return len(self.d) - self.p
    def read_bytes(self, n):
        if n < 0 or self.p + n > len(self.d): raise ValueError("short read")
        b = self.d[self.p:self.p + n]; self.p += n; return b
    def _u(self, fmt, n): return struct.unpack(fmt, self.read_bytes(n))[0]
    def read_u8(self): return self._u("<B", 1)
    def read_i8(self): return self._u("<b", 1)
    def read_u16_le(self): return self._u("<H", 2)
    def read_u16_be(self): return self._u(">H", 2)
    def read_u24_le(self): return int.from_bytes(self.read_bytes(3), "little")
    def read_u32_le(self): return self._u("<I", 4)
    def read_u32_be(self): return self._u(">I", 4)
    def read_u64_le(self): return self._u("<Q", 8)
    def read_u64_be(self): return self._u(">Q", 8)
    def read_i32(self): return self._u("<i", 4)
    def read_i32_be(self): return self._u(">i", 4)
    def read_i64(self): return self._u("<q", 8)
    def read_bool(self): return self.read_u8() != 0
    def read_float(self): return self._u("<f", 4)
    def read_double(self): return self._u("<d", 8)
    def read_varuint(self, maxbits):
        v = 0; s = 0
        while True:
            b = self.read_u8(); v |= (b & 0x7F) << s
            if not b & 0x80: return v
            s += 7
            if s >= maxbits + 7: raise ValueError("varint too long")
    def read_varuint32(self): return self.read_varuint(32)
    def read_varuint64(self): return self.read_varuint(64)
    def read_varint32(self):
        v = self.read_varuint32(); return (v >> 1) ^ -(v & 1)
    def read_varint64(self):
        v = self.read_varuint64(); return (v >> 1) ^ -(v & 1)
    def read_string(self): return self.read_bytes(self.read_varuint32()).decode("utf-8", "replace")
    def read_uuid(self):
        b = self.read_bytes(16); return uuid.UUID(bytes=b[8:][::-1] + b[:8][::-1])  # Bedrock: two LE u64
    def rest(self): return self.read_bytes(self.left())

class ByteWriter:
    def __init__(self): self.b = bytearray()
    def get(self): return bytes(self.b)
    def write_u8(self, v): self.b.append(v & 0xFF); return self
    def write_bool(self, v): return self.write_u8(1 if v else 0)
    def write_u16_le(self, v): self.b += struct.pack("<H", v); return self
    def write_u16_be(self, v): self.b += struct.pack(">H", v); return self
    def write_u24_le(self, v): self.b += (v & 0xFFFFFF).to_bytes(3, "little"); return self
    def write_u32_le(self, v): self.b += struct.pack("<I", v); return self
    def write_u32_be(self, v): self.b += struct.pack(">I", v); return self
    def write_u64_le(self, v): self.b += struct.pack("<Q", v); return self
    def write_u64_be(self, v): self.b += struct.pack(">Q", v); return self
    def write_i32(self, v): self.b += struct.pack("<i", v); return self
    def write_i32_be(self, v): self.b += struct.pack(">i", v); return self
    def write_float(self, v): self.b += struct.pack("<f", v); return self
    def write_varuint32(self, v):
        v &= 0xFFFFFFFF
        while True:
            if v < 0x80: self.b.append(v); return self
            self.b.append((v & 0x7F) | 0x80); v >>= 7
    def write_varuint64(self, v):
        v &= 0xFFFFFFFFFFFFFFFF
        while True:
            if v < 0x80: self.b.append(v); return self
            self.b.append((v & 0x7F) | 0x80); v >>= 7
    def write_varint32(self, v): return self.write_varuint32(((v << 1) ^ (v >> 31)) & 0xFFFFFFFF)
    def write_varint64(self, v): return self.write_varuint64(((v << 1) ^ (v >> 63)) & 0xFFFFFFFFFFFFFFFF)
    def write_string(self, s):
        if isinstance(s, str): s = s.encode("utf-8")
        self.write_varuint32(len(s)); self.b += s; return self
    def write_uuid(self, u):
        b = u.bytes; self.b += b[:8][::-1] + b[8:][::-1]; return self
    def write_bytes(self, d): self.b += d; return self

# ---------------------------------------------------------------- crypto (pure python)
def _build_sbox():
    sbox = [0] * 256; p = q = 1
    rotl = lambda x, n: ((x << n) | (x >> (8 - n))) & 0xFF
    while True:
        p = (p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q = (q ^ (q << 1)) & 0xFF; q = (q ^ (q << 2)) & 0xFF; q = (q ^ (q << 4)) & 0xFF
        if q & 0x80: q ^= 0x09
        sbox[p] = (q ^ rotl(q, 1) ^ rotl(q, 2) ^ rotl(q, 3) ^ rotl(q, 4) ^ 0x63) & 0xFF
        if p == 1: break
    sbox[0] = 0x63
    return sbox
SBOX = _build_sbox()
def _xt(a): return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1

class AES256:
    def __init__(self, key):
        assert len(key) == 32
        w = [list(key[i:i + 4]) for i in range(0, 32, 4)]; rcon = 1
        for i in range(8, 60):
            t = list(w[i - 1])
            if i % 8 == 0:
                t = t[1:] + t[:1]; t = [SBOX[x] for x in t]; t[0] ^= rcon; rcon = _xt(rcon)
            elif i % 8 == 4:
                t = [SBOX[x] for x in t]
            w.append([a ^ b for a, b in zip(w[i - 8], t)])
        self.rk = [sum(w[r * 4:r * 4 + 4], []) for r in range(15)]
    def encrypt_block(self, blk):
        s = [a ^ b for a, b in zip(blk, self.rk[0])]
        for r in range(1, 15):
            s = [SBOX[x] for x in s]
            s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]  # ShiftRows (column-major)
            if r != 14:
                o = []
                for c in range(0, 16, 4):
                    a0, a1, a2, a3 = s[c:c + 4]
                    o += [_xt(a0) ^ _xt(a1) ^ a1 ^ a2 ^ a3, a0 ^ _xt(a1) ^ _xt(a2) ^ a2 ^ a3,
                          a0 ^ a1 ^ _xt(a2) ^ _xt(a3) ^ a3, _xt(a0) ^ a0 ^ a1 ^ a2 ^ _xt(a3)]
                s = o
            s = [a ^ b for a, b in zip(s, self.rk[r])]
        return bytes(s)

class AESCTR:
    def __init__(self, key, iv16):
        self.aes = AES256(key); self.ctr = int.from_bytes(iv16, "big"); self.ks = b""
    def process(self, data):
        out = bytearray()
        for byte in data:
            if not self.ks:
                self.ks = self.aes.encrypt_block(self.ctr.to_bytes(16, "big"))
                self.ctr = (self.ctr + 1) & ((1 << 128) - 1)
            out.append(byte ^ self.ks[0]); self.ks = self.ks[1:]
        return bytes(out)

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

def b64u_enc(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def b64u_dec(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
def jwt_parse(tok):
    h, p, _s = tok.split(".")
    return json.loads(b64u_dec(h)), json.loads(b64u_dec(p))
def jwt_make_es384(d, header, payload):
    si = (b64u_enc(json.dumps(header, separators=(",", ":")).encode()) + "." +
          b64u_enc(json.dumps(payload, separators=(",", ":")).encode()))
    return si + "." + b64u_enc(es384_sign(d, si.encode()))

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

# ---------------------------------------------------------------- Bedrock packet ids (protocol 766)
PID_ADD_ITEM_ACTOR = 15; PID_TAKE_ITEM_ACTOR = 17; PID_INVENTORY_TRANSACTION = 30; PID_UPDATE_ATTRIBUTES = 29; PID_INVENTORY_CONTENT = 49; PID_INVENTORY_SLOT = 50; PID_MOB_EQUIPMENT = 31; PID_ITEM_STACK_REQUEST = 147; PID_ITEM_STACK_RESPONSE = 148; PID_LEVEL_EVENT = 25; PID_LOGIN = 1; PID_PLAY_STATUS = 2; PID_S2C_HANDSHAKE = 3; PID_C2S_HANDSHAKE = 4
PID_DISCONNECT = 5; PID_PACKS_INFO = 6; PID_PACK_STACK = 7; PID_PACK_RESPONSE = 8; PID_CACHE_STATUS = 129; PID_START_GAME = 11; PID_SET_TIME = 10; PID_CHUNK = 58; PID_REQ_RADIUS = 69; PID_RADIUS_UPDATED = 70; PID_INITIALIZED = 113; PID_ACTOR_IDS = 119; PID_PUBLISHER = 121; PID_BIOME_DEFS = 122; PID_CREATIVE = 145; PID_TEXT = 9; PID_UPDATE_BLOCK = 21; PID_ADD_PLAYER = 12; PID_REMOVE_ACTOR = 14; PID_MOVE_PLAYER = 19; PID_PLAYER_LIST = 63; PID_AUTH_INPUT = 144; PID_NETWORK_SETTINGS = 143; PID_REQUEST_NETWORK_SETTINGS = 193
PLAY_LOGIN_SUCCESS = 0; PLAY_FAILED_CLIENT = 1; PLAY_FAILED_SERVER = 2

def sanitize_name(n):
    n = "".join(c for c in str(n) if c.isprintable() and c not in "\r\n\t")[:16].strip()
    return n or "Player"

def parse_login(body):
    """body = Login packet payload after the packet id."""
    r = ByteReader(body)
    proto = r.read_i32_be()
    blob = ByteReader(r.read_bytes(r.read_varuint32()))
    chain_json = blob.read_bytes(blob.read_u32_le()).decode("utf-8", "replace")
    client_jwt = blob.read_bytes(blob.read_u32_le()).decode("utf-8", "replace")
    root = json.loads(chain_json)
    if "Certificate" in root: root = json.loads(root["Certificate"])
    chain = root.get("chain", [])
    info = {"protocol": proto, "name": "Player", "xuid": "", "identity": None, "identity_key": None,
            "client_key": None, "client_data": {}}
    for tok in chain:
        try:
            _h, p = jwt_parse(tok)
        except Exception:
            continue
        if "identityPublicKey" in p: info["identity_key"] = p["identityPublicKey"]
        ed = p.get("extraData")
        if isinstance(ed, dict):
            info["name"] = ed.get("displayName", info["name"]); info["xuid"] = ed.get("XUID", "")
            info["identity"] = ed.get("identity")
    try:
        h, cd = jwt_parse(client_jwt); info["client_data"] = cd; info["client_key"] = h.get("x5u")
    except Exception as e:
        log("Login", "clientData JWT parse failed: %r" % e)
    info["name"] = sanitize_name(info["name"])
    return info


def build_start_game(runtime_id):
    """Field order follows BedrockProtocol StartGamePacket for 1.21.50 (see README for confidence notes)."""
    w = ByteWriter()
    w.write_varint64(runtime_id)                 # actorUniqueId
    w.write_varuint64(runtime_id)                # actorRuntimeId
    w.write_varint32(GAMEMODE)                   # player gamemode
    for v in (SPAWN[0] + 0.5, SPAWN[1] + 1.62, SPAWN[2] + 0.5): w.write_float(v)
    w.write_float(0.0).write_float(0.0)          # pitch, yaw
    # --- LevelSettings
    w.b += struct.pack("<q", -1)                 # seed
    w.write_u16_le(0).write_string("").write_varint32(0)   # SpawnSettings: biomeType, biomeName, dimension(overworld)
    w.write_varint32(1)                          # generator (infinite)
    w.write_varint32(GAMEMODE)                   # world gamemode
    w.write_bool(False)                          # hardcore
    w.write_varint32(1)                          # difficulty
    w.write_varint32(SPAWN[0]).write_varuint32(SPAWN[1]).write_varint32(SPAWN[2])  # spawn block pos
    w.write_bool(True)                           # achievements disabled
    w.write_varint32(0)                          # editor world type
    w.write_bool(False).write_bool(False)        # createdInEditor, exportedFromEditor
    w.write_varint32(6000)                       # time
    w.write_varint32(0)                          # edu edition offer
    w.write_bool(False)                          # edu features
    w.write_string("")                           # edu product uuid
    w.write_float(0.0).write_float(0.0)          # rain, lightning
    w.write_bool(False)                          # confirmed platform locked content
    w.write_bool(True)                           # isMultiplayerGame
    w.write_bool(True)                           # LAN broadcast
    w.write_varint32(4).write_varint32(4)        # xbox / platform broadcast mode
    w.write_bool(True)                           # commands enabled
    w.write_bool(False)                          # texture packs required
    w.write_varuint32(0)                         # game rules
    w.write_u32_le(0).write_bool(False)          # experiments (count, previouslyToggled)
    w.write_bool(False).write_bool(False)        # bonus chest, start with map
    w.write_varint32(1)                          # default player permission (member)
    w.write_i32(4)                               # server chunk tick radius
    for _ in range(4): w.write_bool(False)       # locked BP, locked RP, from locked template, msa gamertags only
    for _ in range(2): w.write_bool(False)       # from world template, template option locked
    w.write_bool(False)                          # only spawn v1 villagers
    w.write_bool(False).write_bool(False)        # disabling personas, disabling custom skins
    w.write_bool(False)                          # mute emote announcements
    w.write_string(GAME_VERSION)                 # vanilla version
    w.write_i32(0).write_i32(0)                  # limited world width/length
    w.write_bool(True)                           # new nether
    w.write_string("").write_string("")          # edu shared uri resource
    w.write_bool(False)                          # experimental gameplay override (optional absent)
    w.write_u8(0)                                # chat restriction level
    w.write_bool(False)                          # disable player interactions
    w.write_string("").write_string("").write_string("")   # serverIdentifier, worldIdentifier, scenarioIdentifier (1.21.50)
    # --- rest of StartGame
    w.write_string("minimal-level-id")           # level id
    w.write_string(SERVER_TITLE)                 # world name
    w.write_string("")                           # premium world template id
    w.write_bool(False)                          # is trial
    w.write_varint32(1).write_varint32(0).write_bool(False)   # movement: SERVER_AUTHORITATIVE_V2 = 1, rewind 0, block breaking
    w.b += struct.pack("<q", 0)                  # current tick
    w.write_varint32(0)                          # enchantment seed
    w.write_varuint32(0)                         # block palette (empty, client uses built-in)
    w.write_varuint32(0)                         # item table (empty - see README)
    w.write_string("")                           # multiplayer correlation id
    w.write_bool(True)                           # new inventory system
    w.write_string("pywer-v0.9.1dev") # server software version
    w.write_bytes(EMPTY_NBT)                     # player actor properties
    w.b += struct.pack("<Q", 0)                  # block palette checksum
    w.write_uuid(uuid.UUID(int=0))               # world template id
    w.write_bool(False)                          # client side chunk generation
    w.write_bool(USE_BLOCK_HASHES and TERRAIN)             # block network ids are hashes
    w.write_bool(True)                           # network permissions: disable client sounds
    return w.get()


# ---------------------------------------------------------------- players / chat / world builders
def _b64(v):
    try:
        v = str(v or ""); return base64.b64decode(v + "=" * (-len(v) % 4))
    except Exception:
        return b""

def _img(w, h, data):
    return ByteWriter().write_i32(int(w)).write_i32(int(h)).write_string(data).get()

def build_skin(cd):
    """SkinData wire format (PacketSerializer::putSkin, 1.21.50) built from the clientData JWT."""
    w = ByteWriter()
    try:
        sd = _b64(cd.get("SkinData")); sw = int(cd.get("SkinImageWidth", 0)); sh = int(cd.get("SkinImageHeight", 0))
        if not sd or sw * sh * 4 != len(sd): raise ValueError("bad skin image")
        w.write_string(str(cd.get("SkinId", "")))
        w.write_string(str(cd.get("PlayFabId", "")))
        w.write_string(_b64(cd.get("SkinResourcePatch")))
        w.write_bytes(_img(sw, sh, sd))
        anims = cd.get("AnimatedImageData") or []
        w.write_i32(len(anims))
        for a in anims:
            w.write_bytes(_img(a.get("ImageWidth", 0), a.get("ImageHeight", 0), _b64(a.get("Image"))))
            w.write_i32(int(a.get("Type", 0))); w.write_float(float(a.get("Frames", 0))); w.write_i32(int(a.get("AnimationExpression", 0)))
        w.write_bytes(_img(cd.get("CapeImageWidth", 0), cd.get("CapeImageHeight", 0), _b64(cd.get("CapeData"))))
        w.write_string(_b64(cd.get("SkinGeometryData")))
        w.write_string(_b64(cd.get("SkinGeometryDataEngineVersion")))
        w.write_string(_b64(cd.get("SkinAnimationData")))
        w.write_string(str(cd.get("CapeId", "")))
        w.write_string(str(uuid.uuid4()))                      # full skin id
        w.write_string(str(cd.get("ArmSize", "wide")))
        w.write_string(str(cd.get("SkinColor", "#0")))
        pieces = cd.get("PersonaPieces") or []
        w.write_i32(len(pieces))
        for p in pieces:
            w.write_string(str(p.get("PieceId", ""))); w.write_string(str(p.get("PieceType", "")))
            w.write_string(str(p.get("PackId", ""))); w.write_bool(bool(p.get("IsDefault", False)))
            w.write_string(str(p.get("ProductId", "")))
        tints = cd.get("PieceTintColors") or []
        w.write_i32(len(tints))
        for t in tints:
            w.write_string(str(t.get("PieceType", ""))); cols = t.get("Colors") or []
            w.write_i32(len(cols))
            for c in cols: w.write_string(str(c))
        w.write_bool(bool(cd.get("PremiumSkin", False))); w.write_bool(bool(cd.get("PersonaSkin", False)))
        w.write_bool(bool(cd.get("CapeOnClassicSkin", False))); w.write_bool(True); w.write_bool(bool(cd.get("OverrideSkin", True)))
        return w.get()
    except Exception as e:
        log("Player", "skin fallback (%r)" % e)
        w = ByteWriter()
        w.write_string("Standard_Custom").write_string("")
        w.write_string('{"geometry":{"default":"geometry.humanoid.custom"}}')
        w.write_bytes(_img(64, 64, b"\x80\x80\x80\xff" * (64 * 64)))
        w.write_i32(0); w.write_bytes(_img(0, 0, b""))
        w.write_string("").write_string("").write_string("").write_string("")
        w.write_string(str(uuid.uuid4())).write_string("wide").write_string("#0")
        w.write_i32(0).write_i32(0)
        for v in (False, False, False, True, True): w.write_bool(v)
        return w.get()

def build_player_list_add(players):
    w = ByteWriter(); w.write_u8(0).write_varuint32(len(players))
    for p in players:
        w.write_uuid(p.uuid).write_varint64(p.rid).write_string(p.name).write_string("").write_string("")
        w.write_i32(int(p.client_data.get("DeviceOS", 0) or 0))
        w.write_bytes(p.skin_bytes)
        w.write_bool(False).write_bool(False).write_bool(False)   # teacher, host, sub client
    for _ in players: w.write_bool(True)                            # skin verified
    return w.get()

def build_player_list_remove(players):
    w = ByteWriter(); w.write_u8(1).write_varuint32(len(players))
    for p in players: w.write_uuid(p.uuid)
    return w.get()

def _vec3(w, v):
    for c in v: w.write_float(c)

def build_add_player(p):
    w = ByteWriter()
    w.write_uuid(p.uuid).write_string(p.name).write_varuint64(p.rid).write_string("")
    _vec3(w, p.pos); _vec3(w, (0.0, 0.0, 0.0))
    w.write_float(p.pitch).write_float(p.yaw).write_float(p.head_yaw)
    w.write_varint32(0)                                         # held item: air
    w.write_varint32(GAMEMODE)
    write_metadata(w, entity_metadata(p))                       # flags (sneak/sprint/...), scale, bounding box
    w.write_varuint32(0).write_varuint32(0)                     # synced properties (int, float)
    # abilities (UpdateAbilitiesPacket payload)
    w.b += struct.pack("<q", p.rid); w.write_u8(1).write_u8(0).write_u8(1)
    w.write_u16_le(1)                                           # base layer
    on = (1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)              # doors, containers, attack players/mobs
    w.write_u32_le(on | (1 << 13) | (1 << 14)).write_u32_le(on)
    w.write_float(0.05).write_float(0.1)
    w.write_varuint32(0)                                        # entity links
    w.write_string(str(p.client_data.get("DeviceId", ""))).write_i32(int(p.client_data.get("DeviceOS", 0) or 0))
    return w.get()

def build_text(ttype, source, message):
    w = ByteWriter(); w.write_u8(ttype).write_bool(False)
    if ttype in (1, 7, 8): w.write_string(source)
    w.write_string(message).write_string("").write_string("").write_string(message)
    return w.get()

def sanitize_chat(m):
    m = "".join(c for c in str(m) if c.isprintable() or c == " ")[:256].strip()
    return m

# ---------------------------------------------------------------- blocks, terrain, chunks
# Block network ids: StartGame sets "blockNetworkIdsAreHashes" (field exists since 1.19.80, see BedrockProtocol
# StartGamePacket). The runtime id of a block is then FNV-1a-32 over the little-endian NBT of
# {name, states(sorted by key)} - independent of the palette order of any particular game version.
# State names/types below were checked against PocketMine-MP 5.22.0 (protocol 766)
# BlockObjectToStateSerializer / BlockStateNames and against canonical_block_states.nbt.
T_BYTE, T_INT, T_STR = 1, 3, 8
MIN_Y, MAX_Y = -64, 319          # overworld height range of 1.21.50 (sub chunks -4..19)
SEA_LEVEL = 62
SEED = 1337
TREES = True
PLAINS_BIOME = 1                 # biome_id_map.json: plains = 1

def _le_str(s):
    b = s.encode("utf-8"); return struct.pack("<H", len(b)) + b
def _le_value(t, v):
    if t == T_BYTE: return struct.pack("<b", v)
    if t == T_INT: return struct.pack("<i", v)
    if t == T_STR: return _le_str(v)
    raise ValueError("unsupported nbt tag %r" % t)
def block_state_hash(identifier, states):
    """Network block id (signed int32) of a block state, same algorithm as Dragonfly / CloudburstMC."""
    out = bytearray(b"\x0a\x00\x00")                                  # root compound, empty name
    out += bytes([T_STR]) + _le_str("name") + _le_str(identifier)
    out += bytes([10]) + _le_str("states")
    for k in sorted(states):
        t, v = states[k]; out += bytes([t]) + _le_str(k) + _le_value(t, v)
    out += b"\x00\x00"                                                # end of states, end of root
    h = 0x811C9DC5
    for byte in out: h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
    return h - (1 << 32) if h >= (1 << 31) else h

BLOCK_DEFS = {}      # key -> (identifier, states)
BLOCK_RUNTIME = {}   # key -> network block id (signed)
BLOCK_KEYS = []      # index -> key (used by the chunk builder)
BLOCK_INDEX = {}     # key -> index
def register_block(key, identifier=None, states=None):
    """Add a block to the server. states example: {"pillar_axis": (T_STR, "y"), "persistent_bit": (T_BYTE, 0)}"""
    identifier = identifier or ("minecraft:" + key); states = dict(states or {})
    BLOCK_DEFS[key] = (identifier, states); BLOCK_RUNTIME[key] = block_state_hash(identifier, states)
    if key not in BLOCK_INDEX: BLOCK_INDEX[key] = len(BLOCK_KEYS); BLOCK_KEYS.append(key)

for _k in ("air", "stone", "grass_block", "dirt", "coarse_dirt", "sand", "gravel", "cobblestone", "oak_planks", "sandstone"):
    register_block(_k)
register_block("bedrock", states={"infiniburn_bit": (T_BYTE, 0)})
register_block("water", states={"liquid_depth": (T_INT, 0)})
register_block("oak_log", states={"pillar_axis": (T_STR, "y")})
register_block("oak_leaves", states={"persistent_bit": (T_BYTE, 0), "update_bit": (T_BYTE, 0)})

# BedrockData required_item_list.json (1.21.50) runtime item IDs used by AddItemActor.
# These are deliberately sourced from the uploaded BedrockData, not guessed legacy IDs.
ITEM_RUNTIME = {
    "dirt": 3, "grass_block": 2, "stone": 1, "cobblestone": 4,
    "sand": 12, "gravel": 13, "oak_log": 17, "oak_leaves": 18,
    "oak_planks": 5, "stick": 352, "flint": 318,
}
DROP_FOR_BLOCK = {
    "dirt": [("dirt", 1)], "grass_block": [("dirt", 1)],
    "stone": [("cobblestone", 1)], "cobblestone": [("cobblestone", 1)],
    "sand": [("sand", 1)], "gravel": [("gravel", 1)],
    "oak_log": [("oak_log", 1)], "oak_planks": [("oak_planks", 1)],
}
# PocketMine 5.22 BlockBreakInfo hardness values for the blocks implemented by pywer.
# Bare hand uses the incompatible-tool multiplier (5.0); compatible tool values are
# intentionally not faked until an actual server-side inventory/tool state exists.
BLOCK_HARDNESS = {
    "dirt": 0.5, "grass_block": 0.6, "sand": 0.5, "gravel": 0.6,
    "stone": 1.5, "cobblestone": 2.0, "oak_log": 2.0, "oak_planks": 2.0,
    "oak_leaves": 0.2, "bedrock": -1.0,
}

# ---- terrain (deterministic value noise, so every chunk agrees with its neighbours)
def _hash2(x, z, salt):
    n = (x * 374761393 + z * 668265263 + (SEED + salt) * 144665) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return (n ^ (n >> 16)) / 4294967296.0
def _vnoise(x, z, salt):
    x0 = math.floor(x); z0 = math.floor(z); fx = x - x0; fz = z - z0
    sx = fx * fx * (3 - 2 * fx); sz = fz * fz * (3 - 2 * fz)
    a = _hash2(x0, z0, salt); b = _hash2(x0 + 1, z0, salt); c = _hash2(x0, z0 + 1, salt); d = _hash2(x0 + 1, z0 + 1, salt)
    return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sz

_HEIGHT = {}
def terrain_height(x, z):
    """Y of the top solid block of column (x, z)."""
    k = (x, z); h = _HEIGHT.get(k)
    if h is None:
        v = 64 + (_vnoise(x / 96.0, z / 96.0, 1) - 0.5) * 40 + (_vnoise(x / 32.0, z / 32.0, 2) - 0.5) * 14 \
            + (_vnoise(x / 12.0, z / 12.0, 3) - 0.5) * 4
        h = int(v)
        if len(_HEIGHT) > 400000: _HEIGHT.clear()
        _HEIGHT[k] = h
    return h

def tree_at(x, z):
    """Trunk height if an oak tree is rooted at column (x, z), else 0."""
    if not TREES or terrain_height(x, z) <= SEA_LEVEL + 1: return 0
    r = _hash2(x, z, 7)
    return 4 + int(r * 1000) % 3 if r < 0.012 else 0

def column_layers(x, z):
    """Bottom-to-top list of (y0, y1, block key) for one column, without trees."""
    h = terrain_height(x, z); layers = [(MIN_Y, MIN_Y, "bedrock")]
    stone_top = h - 4
    layers.append((MIN_Y + 1, stone_top, "stone"))
    for i, y in enumerate((MIN_Y + 1, MIN_Y + 2, MIN_Y + 3), 1):         # ragged bedrock floor (drawn over the stone)
        if _hash2(x, z, 20 + i) < 0.6 - 0.2 * i: layers.append((y, y, "bedrock"))
    if h < SEA_LEVEL - 4:   layers += [(h - 3, h, "gravel")]
    elif h <= SEA_LEVEL + 1: layers += [(h - 3, h, "sand")]
    else:                    layers += [(h - 3, h - 1, "dirt"), (h, h, "grass_block")]
    if h < SEA_LEVEL: layers.append((h + 1, SEA_LEVEL, "water"))
    return layers

def tree_blocks(cx, cz):
    """{(world x, y, z): key} of every tree block that falls inside chunk (cx, cz) (trees may overhang by 2)."""
    out = {}; x0 = cx * 16; z0 = cz * 16
    for wx in range(x0 - 2, x0 + 18):
        for wz in range(z0 - 2, z0 + 18):
            th = tree_at(wx, wz)
            if not th: continue
            base = terrain_height(wx, wz)
            for dy in range(1, th + 1): out[(wx, base + dy, wz)] = "oak_log"
            for dy, rad in ((th - 1, 2), (th, 2), (th + 1, 1), (th + 2, 1)):
                for dx in range(-rad, rad + 1):
                    for dz in range(-rad, rad + 1):
                        if abs(dx) == rad and abs(dz) == rad and (rad == 2 or dy == th + 2): continue   # round the corners
                        if dx == 0 and dz == 0 and dy <= th: continue                                    # trunk
                        out[(wx + dx, base + dy, wz + dz)] = "oak_leaves"
    return {k: v for k, v in out.items() if x0 <= k[0] < x0 + 16 and z0 <= k[2] < z0 + 16 and MIN_Y <= k[1] <= MAX_Y}

def find_spawn():
    for r in range(0, 200):
        for x in range(-r, r + 1):
            for z in range(-r, r + 1):
                if max(abs(x), abs(z)) != r: continue
                h = terrain_height(x, z)
                if h > SEA_LEVEL + 1 and not any(tree_at(x + a, z + b) for a in range(-3, 4) for b in range(-3, 4)):
                    return (x, h + 1, z)
    return (0, SEA_LEVEL + 10, 0)
if TERRAIN: SPAWN = find_spawn()

# ---- runtime edits (set_block) are kept per chunk and overlaid on the generated terrain
EDITS = {}           # (cx, cz) -> {(lx, y, lz): key}
CHUNK_CACHE = {}     # (cx, cz) -> LevelChunk packet body

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
    if not TERRAIN: return build_empty_chunk(cx, cz)
    pkt = CHUNK_CACHE.get((cx, cz))
    if pkt is not None: return pkt
    overlay = {}                                                          # (lx, y, lz) -> key
    for (wx, y, wz), key in tree_blocks(cx, cz).items(): overlay[(wx & 15, y, wz & 15)] = key
    overlay.update(EDITS.get((cx, cz), {}))
    cols = {}; top = SEA_LEVEL
    for lx in range(16):
        for lz in range(16):
            cols[(lx, lz)] = column_layers(cx * 16 + lx, cz * 16 + lz); top = max(top, cols[(lx, lz)][-1][1])
    if overlay: top = max(top, max(y for (_, y, _) in overlay))
    top_sub = min(top, MAX_Y) >> 4
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
    for _ in range(24): payload += b"\x01" + bytes([PLAINS_BIOME << 1])  # biome palettes -4..19 (single entry, zigzag)
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

# ---------------------------------------------------------------- player movement (PocketMine-MP 5.22.0 port)
# Reverse engineered from: InGamePacketHandler::handlePlayerAuthInput, Player::handleMovement /
# actuallyHandleMovement / processMostRecentMovements / revertMovement / toggle*, NetworkSession::syncMovement,
# Entity::broadcastMovement + BedrockProtocol PlayerAuthInputPacket / PlayerAuthInputFlags / MovePlayerPacket /
# MoveActorAbsolutePacket / SetActorDataPacket (1.21.50, protocol 766).
PID_MOVE_ACTOR_ABSOLUTE = 18; PID_SET_ACTOR_DATA = 39
PID_SET_ACTOR_MOTION = 40; PID_ANIMATE = 44
EYE_HEIGHT = 1.62
NETWORK_EYE_OFFSET = 1.621  # Human::getOffsetPosition() in PocketMine-MP 5.22.0
MOVES_PER_TICK = 2; MOVE_BACKLOG_SIZE = 100 * MOVES_PER_TICK       # Player.php: rate limit (100 ticks backlog)
MAX_MOVE_DISTANCE_SQ = 225                                         # 15 blocks, Player::actuallyHandleMovement
ALLOW_FLIGHT = GAMEMODE in (1, 6)                                  # creative / spectator, like Player::$allowFlight
MODE_NORMAL, MODE_RESET, MODE_TELEPORT = 0, 1, 2                   # MovePlayerPacket::MODE_*
MOVE_FLAG_GROUND = 0x01                                            # MoveActorAbsolutePacket::FLAG_GROUND

# PlayerAuthInputFlags (bit numbers inside the 65 bit BitSet)
F_JUMPING = 6; F_SNEAKING = 8; F_SPRINTING = 20
F_START_SPRINTING, F_STOP_SPRINTING = 25, 26
F_START_SNEAKING, F_STOP_SNEAKING = 27, 28
F_START_SWIMMING, F_STOP_SWIMMING = 29, 30
F_START_JUMPING = 31
F_START_GLIDING, F_STOP_GLIDING = 32, 33
F_PERFORM_ITEM_INTERACTION, F_PERFORM_BLOCK_ACTIONS, F_PERFORM_ITEM_STACK_REQUEST = 34, 35, 36
F_HANDLED_TELEPORT = 37; F_MISSED_SWING = 39
F_START_CRAWLING, F_STOP_CRAWLING = 40, 41
F_START_FLYING, F_STOP_FLYING = 42, 43

# EntityMetadataFlags (EntityMetadataFlags.php)
MF_SNEAKING = 1; MF_SPRINTING = 3; MF_NAMETAG = 14; MF_ALWAYS_NAMETAG = 15; MF_BREATHING = 35
MF_GLIDING = 32; MF_COLLISION = 48; MF_GRAVITY = 49; MF_SWIMMING = 57; MF_CRAWLING = 114   # >=64 lives in FLAGS2

def _read_item_stack_wrapper(r):
    """PacketSerializer::getItemStackWrapper(), reduced to fields needed by pywer."""
    item_id = r.read_varint32()
    if item_id == 0:
        return {"id": 0, "count": 0, "meta": 0}
    count = r.read_u16_le(); meta = r.read_varuint32()
    has_net_id = r.read_bool()
    if has_net_id: r.read_varint32()
    block_runtime = r.read_varint32()
    raw_extra = r.read_string()
    return {"id": item_id, "count": count, "meta": meta, "block_runtime": block_runtime, "raw_extra": raw_extra}

def _read_signed_block_pos(r):
    # PacketSerializer::getSignedBlockPosition()
    return (r.read_varint32(), r.read_varint32(), r.read_varint32())

def parse_auth_input(body):
    """BedrockProtocol 35.0.3 PlayerAuthInputPacket wire order.

    Unlike the old pywer parser, this consumes block actions after delta when
    PERFORM_BLOCK_ACTIONS is set. That is essential: START/CONTINUE/STOP_BREAK
    are part of this packet in server-authoritative block breaking.
    """
    r = ByteReader(body)
    d = {"pitch": r.read_float(), "yaw": r.read_float()}
    d["pos"] = (r.read_float(), r.read_float(), r.read_float())
    d["move_x"] = r.read_float(); d["move_z"] = r.read_float(); d["head_yaw"] = r.read_float()
    d["flags"] = r.read_varuint(70)
    d["input_mode"] = r.read_varuint32(); d["play_mode"] = r.read_varuint32(); d["interaction_mode"] = r.read_varuint32()
    d["interact_rot"] = (r.read_float(), r.read_float())
    d["tick"] = r.read_varuint64()
    d["delta"] = (r.read_float(), r.read_float(), r.read_float())
    d["item_use"] = None; d["stack_request"] = None; d["block_actions"] = []

    # PlayerAuthInputFlags::PERFORM_ITEM_INTERACTION = 34
    if flag_set(d["flags"], F_PERFORM_ITEM_INTERACTION):
        req_id = r.read_varint32()
        actions = []
        if req_id != 0:
            n = r.read_varuint32()
            for _ in range(n):
                source = r.read_u8(); container = r.read_varuint32(); m = r.read_varuint32()
                slots = [r.read_u8() for _ in range(m)]
                actions.append((source, container, slots))
        tx_type = r.read_varuint32()
        tx = {"request_id": req_id, "actions": actions, "type": tx_type}
        # UseItemOnEntityTransactionData is type 3. Decode only its stable 1.21.50 fields.
        if tx_type == 3:
            tx["target_rid"] = r.read_varuint64(); tx["action"] = r.read_varuint32(); tx["hotbar"] = r.read_varint32()
            tx["item"] = _read_item_stack_wrapper(r)
            tx["player_pos"] = (r.read_float(), r.read_float(), r.read_float())
            tx["click_pos"] = (r.read_float(), r.read_float(), r.read_float())
        d["item_use"] = tx

    # Item stack requests are used when server-authoritative block breaking is enabled.
    if flag_set(d["flags"], F_PERFORM_ITEM_STACK_REQUEST):
        req_id = r.read_varint32(); n = r.read_varuint32(); acts=[]
        for _ in range(n):
            at = r.read_u8()
            if at == 11:  # MineBlockStackRequestAction
                acts.append((at, r.read_varint32(), r.read_varint32(), r.read_varint32()))
            else:
                # Unknown action cannot be safely skipped without its schema. Stop parsing this optional tail.
                raise ValueError("unsupported ItemStackRequest action %d" % at)
        d["stack_request"] = (req_id, acts)

    # PlayerBlockActions follow delta when PERFORM_BLOCK_ACTIONS is present.
    if flag_set(d["flags"], F_PERFORM_BLOCK_ACTIONS):
        count = r.read_varuint32()
        if count > 100: raise ValueError("too many block actions")
        for _ in range(count):
            action = r.read_varuint32()
            if action == 2:  # STOP_BREAK: PlayerBlockActionStopBreak has no payload
                d["block_actions"].append((action, None, 0))
            else:
                pos = _read_signed_block_pos(r); face = r.read_varint32()
                d["block_actions"].append((action, pos, face))
    return d

def flag_set(flags, bit): return (flags >> bit) & 1 == 1
def resolve_on_off(flags, start, stop):
    """InGamePacketHandler::resolveOnOffInputFlags: True/False, or None when neither or both flags are set."""
    on, off = flag_set(flags, start), flag_set(flags, stop)
    return on if on != off else None

def _finite(*vals): return all(not (math.isnan(v) or math.isinf(v)) for v in vals)

# ---- block lookup (collision): edits > trees > terrain layers
_TREE_CACHE = {}
def get_block(x, y, z):
    if y < MIN_Y or y > MAX_Y: return "air"
    cx, cz = x >> 4, z >> 4
    k = EDITS.get((cx, cz), {}).get((x & 15, y, z & 15))
    if k is not None: return k
    if TREES:
        tb = _TREE_CACHE.get((cx, cz))
        if tb is None:
            if len(_TREE_CACHE) > 512: _TREE_CACHE.clear()
            tb = _TREE_CACHE[(cx, cz)] = tree_blocks(cx, cz)
        k = tb.get((x, y, z))
        if k is not None: return k
    key = "air"
    for y0, y1, bk in column_layers(x, z):
        if y0 <= y <= y1: key = bk
    return key
def is_solid(x, y, z): return get_block(x, y, z) not in ("air", "water")

def player_size(p):
    """Living::recalculateSize: (width, height)."""
    if p.swimming or p.gliding: return 0.6, 0.6
    if p.sneaking: return 0.6, 1.8 * 0.75
    return 0.6, 1.8

# PocketMine-style entity collision -------------------------------------------------
# Entity::move() resolves Y first, then X, then Z against block AABBs. Player has a
# 0.6 x 1.8 collision box and a 0.6 step height. This is deliberately kept local
# and deterministic because our world blocks are all unit cubes.
PLAYER_STEP_HEIGHT = 0.6

def _block_collision_boxes(bb_min_x, bb_min_y, bb_min_z, bb_max_x, bb_max_y, bb_max_z):
    """Yield unit-cube AABBs for solid blocks intersecting the swept region."""
    if not TERRAIN:
        return []
    x0 = math.floor(bb_min_x); x1 = math.floor(bb_max_x - 1e-9)
    y0 = math.floor(bb_min_y); y1 = math.floor(bb_max_y - 1e-9)
    z0 = math.floor(bb_min_z); z1 = math.floor(bb_max_z - 1e-9)
    out = []
    # Keep the search bounded. Entity::move() in PM asserts each requested delta <= 20.
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                if is_solid(x, y, z):
                    out.append((x, y, z, x + 1.0, y + 1.0, z + 1.0))
    return out

def _calc_y_offset(box, dy, other):
    minx,miny,minz,maxx,maxy,maxz = box; ox0,oy0,oz0,ox1,oy1,oz1 = other
    if ox1 <= minx or ox0 >= maxx or oz1 <= minz or oz0 >= maxz: return dy
    if dy > 0.0 and maxy <= oy0 + 1e-12:
        d = oy0 - maxy
        if d < dy: dy = d
    elif dy < 0.0 and miny >= oy1 - 1e-12:
        d = oy1 - miny
        if d > dy: dy = d
    return dy

def _calc_x_offset(box, dx, other):
    minx,miny,minz,maxx,maxy,maxz = box; ox0,oy0,oz0,ox1,oy1,oz1 = other
    if oy1 <= miny or oy0 >= maxy or oz1 <= minz or oz0 >= maxz: return dx
    if dx > 0.0 and maxx <= ox0 + 1e-12:
        d = ox0 - maxx
        if d < dx: dx = d
    elif dx < 0.0 and minx >= ox1 - 1e-12:
        d = ox1 - minx
        if d > dx: dx = d
    return dx

def _calc_z_offset(box, dz, other):
    minx,miny,minz,maxx,maxy,maxz = box; ox0,oy0,oz0,ox1,oy1,oz1 = other
    if ox1 <= minx or ox0 >= maxx or oy1 <= miny or oy0 >= maxy: return dz
    if dz > 0.0 and maxz <= oz0 + 1e-12:
        d = oz0 - maxz
        if d < dz: dz = d
    elif dz < 0.0 and minz >= oz1 - 1e-12:
        d = oz1 - minz
        if d > dz: dz = d
    return dz

def _offset_box(box, dx, dy, dz):
    a,b,c,d,e,f = box
    return (a+dx,b+dy,c+dz,d+dx,e+dy,f+dz)

def _move_with_collision(p, wanted_dx, wanted_dy, wanted_dz):
    """Port of Entity::move() for Player-sized unit-block terrain."""
    w,h = player_size(p); hw = w / 2.0
    fx,fy,fz = p.feet()
    box = (fx-hw, fy, fz-hw, fx+hw, fy+h, fz+hw)

    # PM expands the queried collision region by the requested movement, then
    # resolves vertical, horizontal-X, and horizontal-Z independently.
    sx0 = min(box[0], box[0] + wanted_dx); sx1 = max(box[3], box[3] + wanted_dx)
    sy0 = min(box[1], box[1] + wanted_dy); sy1 = max(box[4], box[4] + wanted_dy)
    sz0 = min(box[2], box[2] + wanted_dz); sz1 = max(box[5], box[5] + wanted_dz)
    boxes = _block_collision_boxes(sx0, sy0, sz0, sx1, sy1, sz1)

    dx,dy,dz = wanted_dx,wanted_dy,wanted_dz
    for b in boxes: dy = _calc_y_offset(box, dy, b)
    box = _offset_box(box, 0, dy, 0)
    falling = p.on_ground or (dy != wanted_dy and wanted_dy < 0.0)

    for b in boxes: dx = _calc_x_offset(box, dx, b)
    box = _offset_box(box, dx, 0, 0)
    for b in boxes: dz = _calc_z_offset(box, dz, b)
    box = _offset_box(box, 0, 0, dz)

    # Player::move() attempts a step-up when grounded/falling and horizontal
    # motion was blocked. It keeps whichever path travels farther horizontally.
    if PLAYER_STEP_HEIGHT > 0 and falling and (wanted_dx != dx or wanted_dz != dz):
        cx,cy,cz = dx,dy,dz
        sbox = (fx-hw, fy, fz-hw, fx+hw, fy+h, fz+hw)
        sdx,sdy,sdz = wanted_dx,PLAYER_STEP_HEIGHT,wanted_dz
        ssx0=min(sbox[0],sbox[0]+sdx); ssx1=max(sbox[3],sbox[3]+sdx)
        ssy0=min(sbox[1],sbox[1]+sdy); ssy1=max(sbox[4],sbox[4]+sdy)
        ssz0=min(sbox[2],sbox[2]+sdz); ssz1=max(sbox[5],sbox[5]+sdz)
        step_boxes=_block_collision_boxes(ssx0,ssy0,ssz0,ssx1,ssy1,ssz1)
        for b in step_boxes: sdy=_calc_y_offset(sbox,sdy,b)
        sbox=_offset_box(sbox,0,sdy,0)
        for b in step_boxes: sdx=_calc_x_offset(sbox,sdx,b)
        sbox=_offset_box(sbox,sdx,0,0)
        for b in step_boxes: sdz=_calc_z_offset(sbox,sdz,b)
        sbox=_offset_box(sbox,0,0,sdz)
        reverse_dy=-sdy
        for b in step_boxes: reverse_dy=_calc_y_offset(sbox,reverse_dy,b)
        sdy += reverse_dy
        sbox=_offset_box(sbox,0,reverse_dy,0)
        if cx*cx + cz*cz < sdx*sdx + sdz*sdz:
            dx,dy,dz = sdx,sdy,sdz
            box=sbox

    new_feet=( (box[0]+box[3])/2.0, box[1], (box[2]+box[5])/2.0 )
    collided_y = (wanted_dy != dy)
    # PocketMine re-checks a thin box around the new position to determine onGround,
    # including horizontal movement across a flat surface (important when dy == 0).
    ground_box = (box[0], box[1] - 0.20, box[2], box[3], box[1] + 0.20, box[5])
    grounded = False
    for b in _block_collision_boxes(*ground_box):
        if b[4] > box[1] - 1e-6 and b[4] <= box[1] + 0.20 + 1e-6 and b[0] < box[3] and b[3] > box[0] and b[2] < box[5] and b[5] > box[2]:
            grounded = True; break
    p.on_ground = bool((collided_y and wanted_dy < 0.0) or grounded)
    return new_feet, (dx,dy,dz)

# ---------------------------------------------------------------- block breaking / item drops
# PocketMine's BlockBreakInfo is authoritative for break timing. These hardness values cover the
# blocks that exist in pywer's current generated world; the rest intentionally do not invent drops.
BLOCK_HARDNESS = {
    "stone": 1.5, "cobblestone": 2.0, "dirt": 0.5, "grass_block": 0.6,
    "coarse_dirt": 0.75, "sand": 0.5, "gravel": 0.6, "sandstone": 0.8,
    "oak_log": 2.0, "oak_leaves": 0.2, "bedrock": float("inf"), "water": float("inf"), "air": 0.0,
}
# Legacy numeric item IDs are used here because the current pywer protocol already serializes
# legacy network item stacks in its transaction parser. These are the vanilla IDs for the basic
# blocks represented by this world.
BLOCK_DROP_ITEM_ID = {
    "stone": 1, "cobblestone": 4, "dirt": 3, "grass_block": 3,
    "coarse_dirt": 3, "sand": 12, "gravel": 13, "sandstone": 24,
    "oak_log": 17,
}

def block_break_time(key, creative=False):
    h = BLOCK_HARDNESS.get(key, float("inf"))
    if creative: return 0.0
    if not math.isfinite(h) or h <= 0: return float("inf") if h else 0.0
    # PocketMine BlockBreakInfo: base time is hardness*5 for an incompatible/hand tool;
    # this is the no-tool path used by pywer (no inventory/tool state yet).
    return h * 5.0

def build_item_stack_descriptor(item_id, count=1, meta=0, block_runtime_id=0):
    # PacketSerializer::putItemStackWrapper() for a legacy item stack.
    w = ByteWriter(); w.write_varint32(item_id); w.write_u16_le(count); w.write_varuint32(meta)
    w.write_bool(False)
    w.write_varint32(block_runtime_id & 0xFFFFFFFF)
    w.write_string("")
    return w.get()

def build_add_item_actor(runtime_id, item_key, count, pos, velocity=(0.0, 0.0, 0.0)):
    item_id = ITEM_RUNTIME[item_key]
    block_runtime = BLOCK_RUNTIME.get(item_key, 0)
    w = ByteWriter(); w.write_varint64(runtime_id); w.write_varuint64(runtime_id)
    w.write_bytes(build_item_stack_descriptor(item_id, count, 0, block_runtime))
    _vec3(w, pos); _vec3(w, velocity)
    w.write_varuint32(0)  # ItemEntity network metadata is empty in this implementation
    w.write_bool(False)
    return w.get()

def break_target_reachable(p, pos):
    # PocketMine validates block interaction by distance to block centre, not a server raycast.
    cx, cy, cz = pos[0] + 0.5, pos[1] + 0.5, pos[2] + 0.5
    eye = p.pos
    max_reach = 7.0 if GAMEMODE == 0 else 13.0
    return (cx-eye[0])**2 + (cy-eye[1])**2 + (cz-eye[2])**2 <= max_reach * max_reach

def begin_break(p, pos, face):
    key = get_block(*pos)
    if key in ("air", "water") or not is_solid(*pos): return False
    if key == "bedrock" or not break_target_reachable(p, pos): return False
    p.break_target = pos; p.break_started = time.time(); p.break_last = p.break_started
    p.break_face = face; p.break_progress = 0.0
    if GAMEMODE == 1:
        return finish_break(p)
    return True

def continue_break(p, pos, face):
    if p.break_target != pos: return False
    if not break_target_reachable(p, pos): return False
    t = block_break_time(get_block(*pos), GAMEMODE == 1)
    if not math.isfinite(t): return False
    p.break_last = time.time()
    p.break_progress = min(1.0, (p.break_last - p.break_started) / max(t, 1e-6))
    if p.break_progress >= 1.0: return finish_break(p)
    return True

def stop_break(p, pos=None):
    if pos is None or p.break_target == pos:
        p.break_target = None; p.break_started = p.break_last = 0.0; p.break_progress = 0.0

def finish_break(p):
    pos = p.break_target
    if pos is None: return False
    key = get_block(*pos)
    if key in ("air", "water", "bedrock") or not break_target_reachable(p, pos):
        stop_break(p, pos); return False
    ok = p.srv.break_block(p, *pos, key)
    stop_break(p, pos)
    return ok

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
    """[(key, type, value)] - types: 3 float, 7 long. Includes the bounding box that changes with sneak/swim/glide."""
    lo, hi = entity_flags(p); w, h = player_size(p)
    md = [(0, 7, lo)]
    if hi: md.append((92, 7, hi))
    md += [(38, 3, 1.0), (53, 3, w), (54, 3, h)]
    return md

def write_metadata(w, md):
    w.write_varuint32(len(md))
    for key, typ, val in md:
        w.write_varuint32(key).write_varuint32(typ)
        if typ == 7: w.write_varint64(val)
        elif typ == 3: w.write_float(val)
    return w

def build_set_actor_data(p):
    w = ByteWriter(); w.write_varuint64(p.rid); write_metadata(w, entity_metadata(p))
    w.write_varuint32(0).write_varuint32(0)               # synced properties (int, float)
    w.write_varuint64(0)                                  # tick
    return w.get()

def build_move_player(p, feet=None, mode=MODE_NORMAL, tick=0):
    """MovePlayerPacket: PM sends feet position through Human::getOffsetPosition (+1.621Y)."""
    f = feet if feet is not None else p.feet()
    pos = (f[0], f[1] + NETWORK_EYE_OFFSET, f[2])
    w = ByteWriter(); w.write_varuint64(p.rid); _vec3(w, pos)
    w.write_float(p.pitch).write_float(p.yaw).write_float(p.head_yaw)
    w.write_u8(mode).write_bool(p.on_ground).write_varuint64(0)          # riding runtime id
    if mode == MODE_TELEPORT: w.write_i32(0).write_i32(0)                # teleport cause, source item type
    w.write_varuint64(tick)
    return w.get()

def _rot_byte(deg): return int(deg / (360 / 256)) & 0xFF
def build_move_actor_absolute(p):
    """Entity::broadcastMovement: player actors use feet/body position, not eye position."""
    w = ByteWriter(); w.write_varuint64(p.rid)
    w.write_u8(MOVE_FLAG_GROUND if p.on_ground else 0); _vec3(w, p.feet())
    w.write_u8(_rot_byte(p.pitch)).write_u8(_rot_byte(p.yaw)).write_u8(_rot_byte(p.head_yaw))
    return w.get()

def build_level_event(event_id, event_data, pos):
    w=ByteWriter(); w.write_varint32(event_id); _vec3(w, pos); w.write_varint32(event_data); return w.get()

def build_update_attributes(p):
    """PocketMine AttributeFactory/StandardEntityEventBroadcaster: default movement + health attributes."""
    entries = [
        ("minecraft:movement", 0.0, 3.402823466e38, 0.10, 0.0, 3.402823466e38, 0.10),
        ("minecraft:health", 0.0, 20.0, max(0.0, min(20.0, p.health)), 0.0, 20.0, 20.0),
        ("minecraft:knockback_resistance", 0.0, 1.0, 0.0, 0.0, 1.0, 0.0),
        ("minecraft:underwater_movement", 0.0, 3.402823466e38, 0.02, 0.0, 3.402823466e38, 0.02),
    ]
    w=ByteWriter(); w.write_varuint64(p.rid); w.write_varuint32(len(entries))
    for ident, mn, mx, cur, dmn, dmx, default in entries:
        for v in (mn,mx,cur,dmn,dmx,default): w.write_float(v)
        w.write_string(ident); w.write_varuint32(0)
    w.write_varuint64(0)
    return w.get()

def parse_use_item_on_entity_attack(body):
    """Decode the 1.21.50 UseItemOnEntityTransactionData attack fields."""
    r = ByteReader(body)
    request_id = r.read_varint32()
    if request_id != 0:
        # We don't need prediction-slot reconciliation for attack validation.
        n = r.read_varuint32()
        for _ in range(n):
            r.read_u8(); r.read_varuint32()
            m = r.read_varuint32()
            for _ in range(m): r.read_u8()
    typ = r.read_varuint32()
    if typ != 3: return None
    rid = r.read_varuint64()
    action = r.read_varuint32()
    hotbar = r.read_varint32()
    # ItemStackWrapper / PacketSerializer::getItemStackWrapper()
    item_id = r.read_varint32()
    if item_id != 0:
        r.read_u16_le()          # count
        r.read_varuint32()       # meta
        has_net_id = r.read_bool()
        if has_net_id: r.read_varint32()
        r.read_varint32()         # block runtime ID
        raw_extra = r.read_string()
    player_pos = (r.read_float(), r.read_float(), r.read_float())
    click_pos = (r.read_float(), r.read_float(), r.read_float())
    return rid, action, player_pos, click_pos

# ---------------------------------------------------------------- RakNet session
def enc_addr(ip, port):
    return bytes([4]) + bytes((~int(x)) & 0xFF for x in ip.split(".")) + struct.pack(">H", port)


# ---------------------------------------------------------------- authoritative player inventory (PocketMine 5.22 / BedrockProtocol 35.0.3 subset)
# UI container IDs are taken directly from BedrockProtocol ContainerUIIds.
UI_COMBINED = 12; UI_HOTBAR = 28; UI_INVENTORY = 29; UI_CURSOR = 59
ITEM_AIR = (0, 0, 0)

def item_tuple(item_id, count=0, meta=0):
    return (int(item_id), int(count), int(meta)) if count > 0 else ITEM_AIR

def item_stack_id(item):
    # Stable server-side stack ID. PM uses monotonically tracked IDs; this is sufficient for
    # prediction matching because every authoritative sync receives a fresh ID.
    return 0 if item[1] <= 0 else ((item[0] * 257 + item[2]) & 0x7fffffff) or 1

def build_inventory_stack(item):
    if item[1] <= 0: return b"\x00"
    item_id,count,meta=item
    w=ByteWriter(); w.write_varint32(item_id); w.write_u16_le(count); w.write_varuint32(meta)
    w.write_bool(False); w.write_varint32(0); w.write_string("")
    return w.get()

def build_full_container_name(container_id, dynamic_id=None):
    w=ByteWriter(); w.write_u8(container_id)
    if dynamic_id is None: w.write_bool(False)
    else: w.write_bool(True); w.write_i32(dynamic_id)
    return w.get()

def build_inventory_content(window_id, items, container_id=UI_COMBINED):
    # InventoryContentPacket: windowId, count+wrappers, FullContainerName, storage wrapper.
    w=ByteWriter(); w.write_varuint32(window_id); w.write_varuint32(len(items))
    for item in items: w.write_bytes(build_inventory_stack(item))
    w.write_bytes(build_full_container_name(container_id)); w.write_bytes(b"\x00")
    return w.get()

def build_inventory_slot(window_id, slot, item, container_id=UI_COMBINED):
    # InventorySlotPacket: windowId, slot, wrapper, full container name.
    w=ByteWriter(); w.write_varuint32(window_id); w.write_varuint32(slot); w.write_bytes(build_inventory_stack(item))
    w.write_bytes(build_full_container_name(container_id)); return w.get()

def build_stack_response_ok(request_id, changed):
    # ItemStackResponsePacket: one response containing all changed container slots.
    w=ByteWriter(); w.write_varuint32(1); w.write_u8(0); w.write_varint32(request_id); w.write_varuint32(len(changed))
    for container_id, slots in changed.items():
        w.write_u8(container_id); w.write_bool(False); w.write_varuint32(len(slots))
        for slot,item in slots:
            cnt=item[1]; sid=item_stack_id(item)
            w.write_u8(slot); w.write_u8(slot); w.write_u8(cnt); w.write_varint32(sid)
            w.write_string(""); w.write_string(""); w.write_varint32(0)
    return w.get()

def build_stack_response_error(request_id):
    w=ByteWriter(); w.write_varuint32(1); w.write_u8(1); w.write_varint32(request_id); return w.get()

def read_stack_slot(r):
    cid=r.read_u8(); dynamic=r.read_bool()
    if dynamic: r.read_i32()
    slot=r.read_u8(); stack_id=r.read_varint32()
    return cid,slot,stack_id

def parse_item_stack_request(body):
    r=ByteReader(body); n=r.read_varuint32(); reqs=[]
    for _ in range(n):
        reqid=r.read_varint32(); ac=r.read_varuint32(); acts=[]
        for _ in range(ac):
            typ=r.read_u8()
            if typ in (0,1):
                count=r.read_u8(); src=read_stack_slot(r); dst=read_stack_slot(r); acts.append((typ,count,src,dst))
            elif typ==2:
                a=read_stack_slot(r); b=read_stack_slot(r); acts.append((typ,a,b))
            elif typ==3:
                count=r.read_u8(); src=read_stack_slot(r); rnd=r.read_bool(); acts.append((typ,count,src,rnd))
            elif typ==5:
                acts.append((typ,))
            else:
                # We deliberately reject unknown schemas instead of desynchronising the packet.
                raise ValueError("unsupported ItemStackRequest action %d" % typ)
        fs=r.read_varuint32()
        for _ in range(fs): r.read_string()
        r.read_i32()
        reqs.append((reqid,acts))
    return reqs

class Session:
    RESEND_AFTER = 1.0
    def __init__(self, srv, addr, mtu, guid):
        self.srv = srv; self.addr = addr; self.mtu = mtu; self.guid = guid
        self.state = "RAKNET_CONNECTING"
        self.seen_seq = set(); self.ack_q = []; self.nack_q = []; self.max_seq = -1
        self.seen_rel = set(); self.order_next = {}; self.order_buf = {}; self.splits = {}
        self.send_seq = 0; self.rel_idx = 0; self.ord_idx = 0; self.split_id = 0
        self.pending = {}; self.last_rx = time.time()
        self.compress = False; self.cipher = None; self.player = None
        self.pending_cipher = None
        self.rid = srv.next_rid; srv.next_rid += 1
        self.pos = (SPAWN[0] + 0.5, SPAWN[1] + 1.62, SPAWN[2] + 0.5); self.yaw = 0.0; self.pitch = 0.0; self.head_yaw = 0.0
        self.sent_chunks = set(); self.chunk_queue = []; self.center = None; self.radius = 0
        self.sneaking = self.sprinting = self.swimming = self.gliding = self.crawling = self.flying = False
        self.on_ground = False; self.fall_distance = 0.0; self.last_fall = 0.0; self.jumps = 0; self.allow_flight = ALLOW_FLIGHT
        self.force_move_sync = False; self.last_input_pos = None; self.last_input_rot = (None, None); self.meta_dirty = False
        self.move_tokens = 10.0 * MOVES_PER_TICK; self.last_move_proc = None; self.last_loc = self.loc()
        self.mtick = 0; self.spawned = False; self.name = "Player"; self.uuid = uuid.uuid4(); self.client_data = {}; self.skin_bytes = b""; self.seen_unknown = set()
        self.break_target = None; self.break_started = 0.0; self.break_last = 0.0; self.break_face = 0; self.break_progress = 0.0
        # Entity/Living state used by the server-side simulation.
        self.motion = (0.0, 0.0, 0.0); self.health = 20.0; self.max_health = 20.0
        self.attack_time = 0; self.hurt_time = 0; self.dead = False
        self.inventory = [ITEM_AIR for _ in range(36)]  # 0..8 hotbar, 9..35 main inventory
        self.cursor = ITEM_AIR; self.selected_slot = 0; self.inventory_window_id = 0
        self.inventory_revision = 1

    def sync_inventory(self):
        # PocketMine sends the authoritative player inventory after spawning.
        self.send_packet(PID_INVENTORY_CONTENT, build_inventory_content(self.inventory_window_id, self.inventory, UI_COMBINED))
        
    def sync_inventory_slots(self, slots):
        pk=[]
        for slot in sorted(set(slots)):
            if 0 <= slot < len(self.inventory):
                pk.append(self._pk(PID_INVENTORY_SLOT, build_inventory_slot(self.inventory_window_id, slot, self.inventory[slot], UI_COMBINED)))
        if pk: self.send_packets(pk)

    def _container_slot(self, cid, slot):
        # PocketMine maps HOTBAR and INVENTORY UI IDs to PlayerInventory slots.
        if cid in (UI_HOTBAR, UI_INVENTORY, UI_COMBINED):
            if 0 <= slot < 36: return slot
        return None

    def _apply_stack_requests(self, body):
        reqs=parse_item_stack_request(body); responses=[]
        for reqid,acts in reqs:
            changed={}; touched=set(); ok=True
            for act in acts:
                typ=act[0]
                if typ in (0,1):
                    _,count,src,dst=act; sc,ss,_=src; dc,ds,_=dst
                    si=self._container_slot(sc,ss); di=self._container_slot(dc,ds)
                    if si is None or di is None or count < 1: ok=False; break
                    a=self.inventory[si]; b=self.inventory[di]
                    if a[1] < count: ok=False; break
                    if typ==0: # TAKE: move from source to destination
                        if b[1] and (b[0],b[2]) != (a[0],a[2]): ok=False; break
                        maxadd=64-b[1]
                        if maxadd < count: ok=False; break
                        self.inventory[si]=item_tuple(a[0],a[1]-count,a[2]); self.inventory[di]=item_tuple(a[0],b[1]+count,a[2]); touched|={si,di}
                    else: # PLACE: protocol source/destination semantics are the same stack transfer
                        if b[1] and (b[0],b[2]) != (a[0],a[2]): ok=False; break
                        maxadd=64-b[1]
                        if maxadd < count: ok=False; break
                        self.inventory[si]=item_tuple(a[0],a[1]-count,a[2]); self.inventory[di]=item_tuple(a[0],b[1]+count,a[2]); touched|={si,di}
                elif typ==2:
                    _,a,b=act; ac,aslot,_=a; bc,bslot,_=b; ai=self._container_slot(ac,aslot); bi=self._container_slot(bc,bslot)
                    if ai is None or bi is None: ok=False; break
                    self.inventory[ai],self.inventory[bi]=self.inventory[bi],self.inventory[ai]; touched|={ai,bi}
                elif typ==3:
                    _,count,src,_rnd=act; cid,slot,_=src; si=self._container_slot(cid,slot)
                    if si is None or count<1 or self.inventory[si][1]<count: ok=False; break
                    item=self.inventory[si]; self.inventory[si]=item_tuple(item[0],item[1]-count,item[2]); touched.add(si)
                    key=next((k for k,v in ITEM_RUNTIME.items() if v==item[0]),None)
                    if key: self.srv.drop_item(self.feet(),key,count)
                elif typ==5:
                    continue
            if ok:
                for slot in touched: changed.setdefault(UI_COMBINED,[]).append((slot,self.inventory[slot]))
                responses.append(build_stack_response_ok(reqid,changed)); self.sync_inventory_slots(touched)
            else:
                responses.append(build_stack_response_error(reqid)); self.sync_inventory()
        if responses:
            # Each call above already builds a complete one-response packet; emit them separately to keep wire framing valid.
            for response in responses: self.send_packet(PID_ITEM_STACK_RESPONSE, response)

    # ---- raw send
    def _udp(self, data): self.srv.sock.sendto(data, self.addr)
    def _send_datagram(self, frames):
        seq = self.send_seq; self.send_seq += 1
        self._udp(b"\x84" + seq.to_bytes(3, "little") + b"".join(frames))
        self.pending[seq] = (time.time(), frames)
    def _frame(self, payload, split=None):
        f = bytes([(3 << 5) | (0x10 if split else 0)]) + struct.pack(">H", len(payload) * 8)
        f += self.rel_idx.to_bytes(3, "little"); self.rel_idx += 1
        return f, split
    def send_rak(self, payload):
        """Reliable-ordered, channel 0, with splitting."""
        maxp = self.mtu - 28 - 4 - 24
        chunks = [payload[i:i + maxp] for i in range(0, len(payload), maxp)] or [b""]
        oi = self.ord_idx; self.ord_idx += 1
        sid = self.split_id; self.split_id = (self.split_id + 1) & 0xFFFF
        frames = []
        for i, c in enumerate(chunks):
            sp = len(chunks) > 1
            f = bytes([(3 << 5) | (0x10 if sp else 0)]) + struct.pack(">H", len(c) * 8)
            f += self.rel_idx.to_bytes(3, "little"); self.rel_idx += 1
            f += oi.to_bytes(3, "little") + b"\x00"
            if sp: f += struct.pack(">IHI", len(chunks), sid, i)
            frames.append(f + c)
        cur = []; size = 0; limit = self.mtu - 28 - 4
        for f in frames:
            if cur and size + len(f) > limit:
                self._send_datagram(cur); cur = []; size = 0
            cur.append(f); size += len(f)
        if cur: self._send_datagram(cur)

    # ---- bedrock send
    def send_packets(self, pkts):
        w = ByteWriter()
        for p in pkts: w.write_varuint32(len(p)); w.write_bytes(p)
        batch = w.get()
        if self.compress:
            if len(batch) >= COMPRESSION_THRESHOLD:
                co = zlib.compressobj(6, zlib.DEFLATED, -15)
                batch = b"\x00" + co.compress(batch) + co.flush()
            else:
                batch = b"\xff" + batch
        if self.cipher: batch = self.cipher.encrypt(batch)
        self.send_rak(b"\xfe" + batch)
    def send_packet(self, pid, body=b""):
        w = ByteWriter(); w.write_varuint32(pid); w.write_bytes(body); self.send_packets([w.get()])
    def play_status(self, status): self.send_packet(PID_PLAY_STATUS, struct.pack(">i", status))

    # ---- receive
    def on_datagram(self, data):
        self.last_rx = time.time(); flags = data[0]
        if flags & 0x40: return self._on_ack(data)
        if flags & 0x20: return self._on_nack(data)
        r = ByteReader(data, 1); seq = r.read_u24_le()
        if seq in self.seen_seq: return
        self.seen_seq.add(seq); self.ack_q.append(seq)
        for s in range(self.max_seq + 1, seq):
            if s not in self.seen_seq: self.nack_q.append(s)
        self.max_seq = max(self.max_seq, seq)
        if len(self.seen_seq) > 8192: self.seen_seq = set(s for s in self.seen_seq if s > self.max_seq - 4096)
        while r.left() > 0:
            fl = r.read_u8(); rel = fl >> 5; split = bool(fl & 0x10)
            ln = (r.read_u16_be() + 7) // 8
            ridx = r.read_u24_le() if rel in (2, 3, 4, 6, 7) else None
            if rel in (1, 4): r.read_u24_le()
            oidx = ch = None
            if rel in (1, 3, 4, 7): oidx = r.read_u24_le(); ch = r.read_u8()
            sp = None
            if split: sp = (r.read_u32_be(), r.read_u16_be(), r.read_u32_be())
            payload = r.read_bytes(ln)
            if ridx is not None:
                if ridx in self.seen_rel: continue
                self.seen_rel.add(ridx)
                if len(self.seen_rel) > 8192: self.seen_rel = set(x for x in self.seen_rel if x > ridx - 4096)
            if sp:
                cnt, sid, idx = sp
                ent = self.splits.setdefault(sid, {"cnt": cnt, "parts": {}}); ent["parts"][idx] = payload
                if len(ent["parts"]) < ent["cnt"]: continue
                payload = b"".join(ent["parts"][i] for i in range(ent["cnt"])); del self.splits[sid]
            if oidx is not None and rel in (3, 7):
                nxt = self.order_next.get(ch, 0); buf = self.order_buf.setdefault(ch, {})
                if oidx < nxt: continue
                buf[oidx] = payload
                while nxt in buf:
                    self.on_rak_payload(buf.pop(nxt)); nxt += 1
                self.order_next[ch] = nxt
            else:
                self.on_rak_payload(payload)
    def _records(self, data):
        r = ByteReader(data, 1); n = r.read_u16_be(); out = []
        for _ in range(n):
            if r.read_u8():
                out.append(r.read_u24_le())
            else:
                a = r.read_u24_le(); b = r.read_u24_le(); out.extend(range(a, min(b, a + 4096) + 1))
        return out
    def _on_ack(self, data):
        for s in self._records(data): self.pending.pop(s, None)
    def _on_nack(self, data):
        for s in self._records(data):
            ent = self.pending.pop(s, None)
            if ent: self._send_datagram(ent[1])
    def tick(self, now):
        if self.spawned:
            self.process_movement(now)
            self.tick_break(now)
            if self.break_target is not None and now - self.break_last >= 0.05:
                try: continue_break(self, self.break_target, self.break_face)
                except Exception as e: dbg("World", "break tick error: %r" % e)
            if self.attack_time > 0: self.attack_time -= 1
            if self.hurt_time > 0: self.hurt_time -= 1
            self.srv.tick_item_pickups(self)
        if self.ack_q:
            self._udp(self._ackpkt(0xC0, self.ack_q)); self.ack_q = []
        if self.nack_q:
            self._udp(self._ackpkt(0xA0, self.nack_q)); self.nack_q = []
        for s, (t, frames) in list(self.pending.items()):
            if now - t > self.RESEND_AFTER:
                del self.pending[s]; dbg("RakNet", "resend seq %d" % s); self._send_datagram(frames)
    @staticmethod
    def _ackpkt(pid, seqs):
        seqs = sorted(set(seqs)); recs = []; i = 0
        while i < len(seqs):
            j = i
            while j + 1 < len(seqs) and seqs[j + 1] == seqs[j] + 1: j += 1
            if i == j: recs.append(b"\x01" + seqs[i].to_bytes(3, "little"))
            else: recs.append(b"\x00" + seqs[i].to_bytes(3, "little") + seqs[j].to_bytes(3, "little"))
            i = j + 1
        return bytes([pid]) + struct.pack(">H", len(recs)) + b"".join(recs)

    def on_rak_payload(self, p):
        if not p: return
        pid = p[0]
        if pid == 0x09:
            r = ByteReader(p, 1); _guid = r.read_u64_be(); t = r.read_u64_be()
            w = ByteWriter(); w.write_u8(0x10).write_bytes(enc_addr(*self.addr)).write_u16_be(0)
            for _ in range(10): w.write_bytes(enc_addr("255.255.255.255", 19132))
            w.write_u64_be(t).write_u64_be(int(time.time() * 1000) & 0xFFFFFFFFFFFFFFFF)
            self.send_rak(w.get()); log("RakNet", "Connection request accepted for %s:%d" % self.addr)
        elif pid == 0x13:
            self.state = "WAIT_NETWORK_SETTINGS"; log("RakNet", "RakNet connected")
        elif pid == 0x00:
            t = ByteReader(p, 1).read_u64_be()
            self.send_rak(b"\x03" + struct.pack(">Q", t) + struct.pack(">Q", int(time.time() * 1000) & 0xFFFFFFFFFFFFFFFF))
        elif pid == 0x15:
            log("RakNet", "Client disconnected"); self.state = "CLOSED"
        elif pid == 0xFE:
            self.on_game(p[1:])
        else:
            dbg("RakNet", "unhandled connected id 0x%02x" % pid, p)

    def on_game(self, data):
        try:
            if self.cipher: data = self.cipher.decrypt(data)
            if self.compress:
                h = data[0]
                if h == 0: data = zlib.decompress(data[1:], -15)
                elif h == 0xFF: data = data[1:]
                else: raise ValueError("unsupported compression header %d" % h)
            r = ByteReader(data); pkts = []
            while r.left() > 0: pkts.append(r.read_bytes(r.read_varuint32()))
        except Exception as e:
            log("Bedrock", "bad batch (%r) - ignored" % e); return
        for pk in pkts:
            try:
                rr = ByteReader(pk); pid = rr.read_varuint32() & 0x3FF
                self.on_packet(pid, rr.rest())
            except Exception as e:
                log("Bedrock", "packet handler error: %r" % e)

    def on_packet(self, pid, body):
        if DEBUG_PACKETS and pid != PID_AUTH_INPUT: dbg("Bedrock", "packet id=%d" % pid, body)
        if pid == PID_REQUEST_NETWORK_SETTINGS:
            proto = struct.unpack(">i", body[:4])[0]
            log("Bedrock", "NetworkSettings requested (client protocol %d)" % proto)
            if proto != PROTOCOL:
                self.play_status(PLAY_FAILED_CLIENT if proto < PROTOCOL else PLAY_FAILED_SERVER)
                log("Bedrock", "protocol mismatch, rejected"); return
            w = ByteWriter(); w.write_u16_le(COMPRESSION_THRESHOLD).write_u16_le(0)  # 0 = zlib
            w.write_bool(False).write_u8(0).write_float(0.0)
            self.send_packet(PID_NETWORK_SETTINGS, w.get())
            self.compress = True; self.state = "WAIT_LOGIN"
        elif pid == PID_LOGIN:
            info = parse_login(body); self.player = info
            log("Login", "Login received: name=%s protocol=%s" % (info["name"], info["protocol"]))
            if info["protocol"] != PROTOCOL:
                self.play_status(PLAY_FAILED_CLIENT if info["protocol"] < PROTOCOL else PLAY_FAILED_SERVER); return
            info["uuid"] = uuid.uuid5(uuid.NAMESPACE_DNS, "offline:" + info["name"])
            self.name = info["name"]; self.uuid = info["uuid"]; self.client_data = info["client_data"] or {}
            self.skin_bytes = build_skin(self.client_data)
            log("Login", "Offline login accepted: %s (uuid %s)" % (info["name"], info["uuid"]))
            if ENCRYPTION:
                self.state = "ENCRYPTION_HANDSHAKE"
                client_pub = spki_to_pub(base64.b64decode(info["client_key"] or info["identity_key"]))
                d, pub = self.srv.key; salt = secrets.token_bytes(16)
                spki = base64.b64encode(pub_to_spki(pub)).decode()
                jwt = jwt_make_es384(d, {"alg": "ES384", "x5u": spki}, {"salt": base64.b64encode(salt).decode()})
                self.send_packet(PID_S2C_HANDSHAKE, ByteWriter().write_string(jwt).get())
                self.cipher = BedrockCipher(salt, ecdh(d, client_pub))  # applies from the next outgoing packet
            else:
                self.play_status(PLAY_LOGIN_SUCCESS); self.stage1_done()
        elif pid == PID_C2S_HANDSHAKE:
            log("Handshake", "Encryption handshake complete")
            self.play_status(PLAY_LOGIN_SUCCESS); self.stage1_done()
        elif pid == PID_CACHE_STATUS:
            log("Bedrock", "ClientCacheStatus: enabled=%s" % bool(body[:1] and body[0]))
        elif pid == PID_PACK_RESPONSE:
            r = ByteReader(body); status = r.read_u8(); n = r.read_u16_le()
            log("Bedrock", "ResourcePackClientResponse status=%d (%d packs)" % (status, n))
            if status == 3:      # HAVE_ALL_PACKS -> send stack
                w = ByteWriter(); w.write_bool(False)             # mustAccept
                w.write_varuint32(0).write_varuint32(0)           # behavior packs, resource packs
                w.write_string(GAME_VERSION)                      # base game version
                w.write_u32_le(0)                                 # experiments
                w.write_bool(False).write_bool(False)             # previouslyToggled, hasEditorPacks
                self.send_packet(PID_PACK_STACK, w.get()); log("Bedrock", "ResourcePackStack sent (no packs)")
            elif status == 4:    # COMPLETED
                self.state = "START_GAME"
                log("Bedrock", "Resource pack negotiation COMPLETE")
                sg = build_start_game(self.rid); dbg("World", "StartGame payload", sg); self.send_packet(PID_START_GAME, sg); log("World", "StartGame sent (%d bytes)" % len(sg))
                if SEND_ACTOR_IDS: self.send_packet(PID_ACTOR_IDS, EMPTY_NBT)
                if SEND_BIOME_DEFS: self.send_packet(PID_BIOME_DEFS, EMPTY_NBT)
                if SEND_CREATIVE: self.send_packet(PID_CREATIVE, b"\x00")
                self.send_packet(PID_SET_TIME, ByteWriter().write_varint32(6000).get())
                self.state = "WORLD_LOADING"; log("World", "Waiting for RequestChunkRadius")
            elif status == 1:
                log("Bedrock", "client REFUSED resource packs")
        elif pid == PID_MOB_EQUIPMENT:
            if self.spawned:
                try:
                    r=ByteReader(body); actor=r.read_varuint64(); item=_read_item_stack_wrapper(r); inv_slot=r.read_u8(); hotbar=r.read_u8(); window=r.read_u8()
                    if actor == self.rid and window == 0 and 0 <= hotbar < 9:
                        self.selected_slot = hotbar
                except Exception as e: dbg("Inventory", "bad MobEquipment: %r" % e)
        elif pid == PID_ITEM_STACK_REQUEST:
            if self.spawned:
                try: self._apply_stack_requests(body)
                except Exception as e: dbg("Inventory", "invalid ItemStackRequest: %r" % e)
        elif pid == PID_INVENTORY_TRANSACTION:
            if self.spawned:
                try:
                    hit = parse_use_item_on_entity_attack(body)
                    if hit is not None:
                        target_rid, action, player_pos, click_pos = hit
                        if action == 1:
                            self.srv.handle_entity_attack(self, target_rid, player_pos, click_pos)
                except Exception as e:
                    dbg("Combat", "bad InventoryTransaction: %r" % e)
        elif pid == PID_REQ_RADIUS:
            r = ByteReader(body); want = r.read_varint32()
            rad = max(1, min(want, MAX_RADIUS)); log("World", "RequestChunkRadius %d -> using %d" % (want, rad))
            self.send_packet(PID_RADIUS_UPDATED, ByteWriter().write_varint32(rad).get())
            self.radius = rad; self.center = (SPAWN[0] >> 4, SPAWN[2] >> 4)
            self.send_publisher(SPAWN)
            self.queue_chunks()
            batch = self.chunk_queue[:(2 * rad + 1) ** 2]; self.chunk_queue = self.chunk_queue[len(batch):]
            for i in range(0, len(batch), 9):          # small batches (like PocketMine), not one 200 KB blob
                self.send_packets([self._pk(PID_CHUNK, build_chunk(x, z)) for x, z in batch[i:i + 9]])
            self.sent_chunks.update(batch)
            log("World", "Terrain chunks sent (%d)" % len(batch))
            self.play_status(3); log("Player", "PlayStatus(PLAYER_SPAWN) sent, waiting for SetLocalPlayerAsInitialized")
        elif pid == PID_INITIALIZED:
            self.state = "SPAWNED"; log("Player", "Client entered world (SetLocalPlayerAsInitialized)")
            self.spawned = True; self.force_move_sync = False; self.last_input_pos = None; self.on_ground = is_solid(math.floor(self.pos[0]), math.floor(self.pos[1]-EYE_HEIGHT)-1, math.floor(self.pos[2])); self.srv.on_join(self)
            self.sync_inventory()
            self.send_packet(PID_UPDATE_ATTRIBUTES, build_update_attributes(self))
        elif pid == PID_AUTH_INPUT:
            if self.spawned: self.handle_auth_input(body)
        elif pid == PID_TEXT:
            r = ByteReader(body); ttype = r.read_u8(); r.read_bool()
            if ttype == 1:
                r.read_string(); msg = sanitize_chat(r.read_string())
                if msg.startswith("!") and self.spawned: self.srv.command(self, msg[1:]); return
                if msg and self.spawned:
                    log("Chat", "<%s> %s" % (self.name, msg))
                    self.srv.broadcast([self._pk(PID_TEXT, build_text(1, self.name, msg))])
        else:
            if pid not in self.seen_unknown:
                self.seen_unknown.add(pid); log("Bedrock", "ignored packet id %d (further ones not logged)" % pid)

    # ---- movement (see the movement section above for the PocketMine sources this is ported from)
    def feet(self): return (self.pos[0], self.pos[1] - EYE_HEIGHT, self.pos[2])
    def _set_feet(self, f): self.pos = (f[0], f[1] + EYE_HEIGHT, f[2])
    def loc(self): f = self.feet(); return (f[0], f[1], f[2], self.yaw, self.pitch)

    def _toggle(self, attr, value, allowed=True):
        """Player::toggleSprint/Sneak/Swim/Glide/Flight. Returns False when the change is refused."""
        if value == getattr(self, attr): return True
        if not allowed: return False
        setattr(self, attr, value); self.meta_dirty = True; return True

    def _tick_entity_motion(self):
        """PocketMine Entity::onUpdate/tryChangeMovement equivalent for server-applied motion.
        Client-authoritative position packets are still validated by handle_movement; this path is for
        knockback and other server-side impulses, so it never blindly trusts a client coordinate.
        """
        mx, my, mz = self.motion
        if abs(mx) < 1e-5 and abs(my) < 1e-5 and abs(mz) < 1e-5:
            return
        if not self.flying and not self.gliding:
            my -= 0.08
        friction = 0.91 if not self.on_ground else 0.60
        mx *= friction; mz *= friction
        resolved, actual = _move_with_collision(self, mx, my, mz)
        self._set_feet(resolved)
        self.update_fall_state(actual[1], self.on_ground)
        self.motion = (0.0 if abs(actual[0]) < 1e-4 else mx,
                       0.0 if self.on_ground or abs(actual[1]) < 1e-4 else my,
                       0.0 if abs(actual[2]) < 1e-4 else mz)
        if any(abs(v) > 1e-4 for v in actual):
            self.srv.broadcast([self._pk(PID_MOVE_ACTOR_ABSOLUTE, build_move_actor_absolute(self))], exclude=self)

    def apply_knockback(self, x, z, force=0.4, vertical=0.4):
        f = math.sqrt(x*x + z*z)
        if f <= 1e-9: return
        mx, my, mz = self.motion
        self.motion = (mx * 0.5 + x / f * force,
                       min(vertical, my * 0.5 + vertical),
                       mz * 0.5 + z / f * force)
        self.send_packets([self._pk(PID_SET_ACTOR_MOTION, ByteWriter().write_varuint64(self.rid).write_float(self.motion[0]).write_float(self.motion[1]).write_float(self.motion[2]).get())])

    def damage(self, amount, attacker=None):
        if self.dead or self.hurt_time > 0: return False
        self.health = max(0.0, self.health - max(0.0, float(amount)))
        self.hurt_time = 10
        if attacker is not None:
            dx = self.feet()[0] - attacker.feet()[0]; dz = self.feet()[2] - attacker.feet()[2]
            self.apply_knockback(dx, dz)
        # Entity hurt animation (generic, no weapon/item simulation).
        self.srv.broadcast([self._pk(PID_ANIMATE, ByteWriter().write_varuint64(self.rid).write_u8(1).write_float(0.0).get())])
        if self.health <= 0:
            self.dead = True
            self.health = 0.0
            self.teleport(SPAWN[0] + 0.5, SPAWN[1] + 1.0, SPAWN[2] + 0.5)
            self.health = self.max_health; self.dead = False
        return True

    def send_data(self, to_all=False):
        """Entity::sendData: SetActorData with flags + bounding box (to everybody, or only to this player)."""
        pk = self._pk(PID_SET_ACTOR_DATA, build_set_actor_data(self))
        if to_all: self.srv.broadcast([pk])
        else: self.send_packets([pk])

    def sync_movement(self, pos_eye, mode):
        """NetworkSession::syncMovement: MovePlayer to the owner and lock input until it acknowledges (forceMoveSync)."""
        self.send_packets([self._pk(PID_MOVE_PLAYER, build_move_player(self, pos_eye, mode))])
        self.force_move_sync = True

    def revert_movement(self, old_feet):
        self._set_feet(old_feet); self.sync_movement(self.feet(), MODE_RESET)

    def update_fall_state(self, dy, on_ground):
        """Entity::updateFallState (+ Player: flying never accumulates fall distance)."""
        if self.flying: self.fall_distance = 0.0; return
        if dy < self.fall_distance: self.fall_distance -= dy
        else: self.fall_distance = 0.0
        if on_ground and self.fall_distance > 0:
            if self.fall_distance >= 3: dbg("Move", "%s landed after falling %.1f blocks" % (self.name, self.fall_distance))
            self.last_fall = self.fall_distance; self.fall_distance = 0.0

    def handle_movement(self, new_feet):
        """Player::handleMovement / actuallyHandleMovement."""
        self.move_tokens -= 1
        if self.move_tokens < 0: return                                   # rate limit exceeded: drop it
        old = self.feet()
        dsq = sum((new_feet[i] - old[i]) ** 2 for i in range(3))
        revert = False
        if dsq > MAX_MOVE_DISTANCE_SQ:                                    # safety check, not anti-cheat (see Player.php)
            dbg("Move", "%s moved too fast (%.1f blocks), reverting" % (self.name, math.sqrt(dsq))); revert = True
        elif (math.floor(new_feet[0]) >> 4, math.floor(new_feet[2]) >> 4) not in self.sent_chunks:
            revert = True; self.center = None                             # not in loaded terrain -> re-run chunk order
        if not revert and dsq != 0:
            wanted = (new_feet[0] - old[0], new_feet[1] - old[1], new_feet[2] - old[2])
            resolved, actual = _move_with_collision(self, *wanted)
            self._set_feet(resolved)
            self.update_fall_state(actual[1], self.on_ground)
        if revert: self.revert_movement(old)

    def process_movement(self, now):
        """Player::processMostRecentMovements - once per 50 ms: refill the rate limit, broadcast the newest position."""
        if self.last_move_proc is not None and now - self.last_move_proc < 0.05: return
        mult = (now - self.last_move_proc) * 20 if self.last_move_proc is not None else 1
        exceeded = self.move_tokens < 0
        self.move_tokens = min(MOVE_BACKLOG_SIZE, max(0, self.move_tokens) + MOVES_PER_TICK * mult)
        self.last_move_proc = now
        cur = self.loc(); last = self.last_loc
        d = sum((cur[i] - last[i]) ** 2 for i in range(3)); ang = abs(last[3] - cur[3]) + abs(last[4] - cur[4])
        if d > 0.0001 or ang > 1.0:
            self.last_loc = cur
            self.srv.broadcast([self._pk(PID_MOVE_ACTOR_ABSOLUTE, build_move_actor_absolute(self))], exclude=self)
        if exceeded:
            dbg("Move", "%s exceeded the movement rate limit, resetting" % self.name); self.sync_movement(self.feet(), MODE_RESET)

    def handle_auth_input(self, body):
        """InGamePacketHandler::handlePlayerAuthInput."""
        try: d = parse_auth_input(body)
        except Exception as e: dbg("Move", "bad PlayerAuthInput: %r" % e); return
        raw = d["pos"]
        if not _finite(*raw, d["yaw"], d["head_yaw"], d["pitch"]) or any(abs(v) > 1e7 for v in raw):
            dbg("Move", "invalid movement received (NaN/INF/huge)"); return
        if (d["yaw"], d["pitch"]) != self.last_input_rot:                 # rotation: fmod 360, yaw made positive
            self.last_input_rot = (d["yaw"], d["pitch"])
            yaw = math.fmod(d["yaw"], 360); self.pitch = math.fmod(d["pitch"], 360)
            self.yaw = yaw + 360 if yaw < 0 else yaw
        hy = math.fmod(d["head_yaw"], 360); self.head_yaw = hy + 360 if hy < 0 else hy
        has_moved = self.last_input_pos is None or self.last_input_pos != raw
        new_feet = (round(raw[0], 4), round(raw[1] - EYE_HEIGHT, 4), round(raw[2], 4))
        if self.force_move_sync and has_moved:
            cur = self.feet()
            if sum((new_feet[i] - cur[i]) ** 2 for i in range(3)) > 1: return       # outdated pre-teleport input
            self.force_move_sync = False                                  # close enough = teleport acknowledged
        flags = d["flags"]
        sneaking = flag_set(flags, F_SNEAKING)
        if self.sneaking == sneaking: sneaking = None
        sprinting = resolve_on_off(flags, F_START_SPRINTING, F_STOP_SPRINTING)
        swimming = resolve_on_off(flags, F_START_SWIMMING, F_STOP_SWIMMING)
        gliding = resolve_on_off(flags, F_START_GLIDING, F_STOP_GLIDING)
        flying = resolve_on_off(flags, F_START_FLYING, F_STOP_FLYING)
        crawling = resolve_on_off(flags, F_START_CRAWLING, F_STOP_CRAWLING)   # not in PM 5.22, flags exist in the protocol
        mismatch = False
        if sneaking is not None: mismatch |= not self._toggle("sneaking", sneaking)
        if sprinting is not None: mismatch |= not self._toggle("sprinting", sprinting)
        if swimming is not None: mismatch |= not self._toggle("swimming", swimming)
        if gliding is not None: mismatch |= not self._toggle("gliding", gliding)
        if flying is not None: mismatch |= not self._toggle("flying", flying, self.allow_flight)
        if crawling is not None: mismatch |= not self._toggle("crawling", crawling)
        if self.meta_dirty: self.meta_dirty = False; self.send_data(to_all=True)
        if mismatch: self.send_data()                                      # refused: tell the client the real state
        if flag_set(flags, F_START_JUMPING): self.jumps += 1; dbg("Move", "%s jumped" % self.name)
        if not self.force_move_sync and has_moved:
            self.last_input_pos = raw; self.handle_movement(new_feet)

        # PocketMine processes PlayerBlockActions from the same PlayerAuthInput tick,
        # preserving ordering with movement and item prediction.
        for action, bpos, face in d.get("block_actions", []):
            if action == 0: self.start_break(bpos, face)       # START_BREAK
            elif action == 27: self.continue_break(bpos, face) # CONTINUE_DESTROY_BLOCK
            elif action == 18: self.continue_break(bpos, face) # CRACK_BREAK
            elif action == 26: self.finish_break(bpos)         # PREDICT_DESTROY_BLOCK
            elif action in (1,2): self.stop_break(bpos)        # ABORT/STOP_BREAK
        self.mtick += 1
        self.stream_chunks()

    def _block_reach_ok(self, pos):
        f=self.feet(); dx=(pos[0]+0.5)-f[0]; dy=(pos[1]+0.5)-(f[1]+1.62); dz=(pos[2]+0.5)-f[2]
        return dx*dx+dy*dy+dz*dz <= 36.0  # matches survival interaction reach used by PM (6 blocks squared)

    def start_break(self, pos, face):
        if not self._block_reach_ok(pos): return False
        key=get_block(*pos)
        hardness=BLOCK_HARDNESS.get(key, -1.0)
        if key == "air" or hardness < 0: return False
        if hardness == 0:
            return self.finish_break(pos)
        self.break_target=tuple(pos); self.break_face=face; self.break_started=time.time(); self.break_last=self.break_started; self.break_progress=0.0
        self.break_speed=1.0/(hardness*5.0*20.0)
        # PM starts the crack FX on the server; pywer sends a lightweight LevelEvent equivalent.
        self.srv.broadcast([self._pk(PID_LEVEL_EVENT, build_level_event(3600, int(65535*self.break_speed), pos))])
        return True

    def continue_break(self,pos,face):
        if self.break_target == tuple(pos): self.break_face=face; return True
        return False

    def stop_break(self,pos):
        if self.break_target is None: return True
        if tuple(pos)!=self.break_target: self.break_target=None; return True
        self.break_target=None; return True

    def tick_break(self, now):
        if self.break_target is None: return
        if not self._block_reach_ok(self.break_target): self.break_target=None; return
        key=get_block(*self.break_target); hardness=BLOCK_HARDNESS.get(key,-1.0)
        if hardness < 0: self.break_target=None; return
        self.break_progress += max(0.0, now-self.break_last) * (1.0/(hardness*5.0))
        self.break_last=now
        if self.break_progress >= 1.0:
            pos=self.break_target; self.break_target=None; self.finish_break(pos)

    def finish_break(self,pos):
        if not self._block_reach_ok(pos): return False
        key=get_block(*pos)
        if key in ("air","bedrock") or key not in BLOCK_RUNTIME: return False
        drops=DROP_FOR_BLOCK.get(key,[])
        self.srv.set_block(pos[0],pos[1],pos[2],"air")
        for item_key,count in drops:
            self.srv.drop_item(pos,item_key,count)
        return True

    def teleport(self, x, y, z, yaw=None, pitch=None):
        """Player::teleport: x/y/z are the feet position. Loads the target area first, then moves the client."""
        if yaw is not None: self.yaw = yaw % 360
        if pitch is not None: self.pitch = pitch
        self._set_feet((x, y, z)); self.fall_distance = 0.0; self.on_ground = False
        self.center = None; self.stream_chunks()
        while self.chunk_queue: self.stream_chunks()                      # send the whole area before the client arrives
        self.sync_movement(self.feet(), MODE_TELEPORT)
        self.last_loc = self.loc()
        self.srv.broadcast([self._pk(PID_MOVE_ACTOR_ABSOLUTE, build_move_actor_absolute(self))], exclude=self)

    def send_publisher(self, pos):
        w = ByteWriter(); w.write_varint32(int(pos[0])).write_varint32(int(pos[1])).write_varint32(int(pos[2]))
        w.write_varuint32(self.radius * 16).write_u32_le(0)
        self.send_packet(PID_PUBLISHER, w.get())
    def queue_chunks(self):
        cx, cz = self.center; r = self.radius
        want = [(x, z) for x in range(cx - r, cx + r + 1) for z in range(cz - r, cz + r + 1)
                if (x, z) not in self.sent_chunks]
        self.chunk_queue = sorted(want, key=lambda c: (c[0] - cx) ** 2 + (c[1] - cz) ** 2)
    def stream_chunks(self):
        """Called on every movement packet: follow the player and send a few missing chunks per call."""
        c = (math.floor(self.pos[0]) >> 4, math.floor(self.pos[2]) >> 4)
        if c != self.center:
            self.center = c; self.send_publisher(self.pos); self.queue_chunks()
            keep = {(x, z) for x in range(c[0] - self.radius - 2, c[0] + self.radius + 3) for z in range(c[1] - self.radius - 2, c[1] + self.radius + 3)}
            self.sent_chunks &= keep                                  # chunks far away are forgotten by the client
        if self.chunk_queue:
            batch = self.chunk_queue[:CHUNKS_PER_TICK]; self.chunk_queue = self.chunk_queue[CHUNKS_PER_TICK:]
            self.send_packets([self._pk(PID_CHUNK, build_chunk(x, z)) for x, z in batch]); self.sent_chunks.update(batch)
    def chat_to(self, msg):
        self.send_packets([self._pk(PID_TEXT, build_text(0, "", msg))])

    @staticmethod
    def _pk(pid, body):
        return ByteWriter().write_varuint32(pid).write_bytes(body).get()

    def stage1_done(self):
        self.state = "RESOURCE_PACKS"
        w = ByteWriter(); w.write_bool(False).write_bool(False).write_bool(False)  # mustAccept, hasAddons, hasScripts
        w.write_uuid(uuid.UUID(int=0)).write_string("").write_u16_le(0)           # worldTemplate id/version, 0 packs
        self.send_packet(PID_PACKS_INFO, w.get())
        log("Bedrock", "PlayStatus(LoginSuccess) + ResourcePacksInfo (0 packs) sent")

# ---------------------------------------------------------------- server
class Server:
    def __init__(self, port=PORT, bind="0.0.0.0"):
        self.guid = random.getrandbits(63); self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((bind, port)); self.sock.setblocking(False)
        self.sessions = {}; self.key = ec_keygen(); self.next_rid = 1; self.item_entities = {}
        self.motd = "MCPE;pywer-v0.9.1dev;%d;%s;0;1;%d;Minimal;Creative;1;%d;%d;" % (
            PROTOCOL, GAME_VERSION, self.guid, port, port + 1)
    def banner(self):
        print("Minecraft Bedrock %s pywer-v0.9.1dev Server\nProtocol: %d\nRakNet UDP: %d\nOffline mode: ON\n"
              "World: generated terrain (seed %d)\nMovement: ENABLED (PocketMine-derived) | Mining: PocketMine-style block actions/drops" % (GAME_VERSION, PROTOCOL, self.port, SEED), flush=True)
        log("Server", "Listening on 0.0.0.0:%d" % self.port)
    def unconnected(self, data, addr):
        pid = data[0]
        if pid in (0x01, 0x02):
            t = data[1:9]; ms = self.motd.encode()
            self.sock.sendto(b"\x1c" + t + struct.pack(">Q", self.guid) + RAKNET_MAGIC + struct.pack(">H", len(ms)) + ms, addr)
        elif pid == 0x05:
            if data[1:17] != RAKNET_MAGIC: return
            mtu = max(576, min(len(data) + 28, 1492))
            self.sock.sendto(b"\x06" + RAKNET_MAGIC + struct.pack(">QBH", self.guid, 0, mtu), addr)
        elif pid == 0x07:
            r = ByteReader(data, 17)
            if r.read_u8() == 4: r.read_bytes(6)
            else: r.read_bytes(28)
            mtu = r.read_u16_be(); cguid = r.read_u64_be(); mtu = max(576, min(mtu, 1492))
            if addr not in self.sessions and len(self.sessions) >= MAX_PLAYERS:
                log("RakNet", "server full, ignoring %s:%d" % addr); return
            old = self.sessions.pop(addr, None)
            if old: self.on_leave(old)
            self.sessions[addr] = Session(self, addr, mtu, cguid)
            log("RakNet", "RakNet connection from %s (MTU %d)" % (addr[0], mtu))
            self.sock.sendto(b"\x08" + RAKNET_MAGIC + struct.pack(">Q", self.guid) + enc_addr(*addr) + struct.pack(">HB", mtu, 0), addr)
    def playing(self, exclude=None):
        return [s for s in self.sessions.values() if s.spawned and s is not exclude]
    def broadcast(self, pkts, exclude=None):
        for s in self.playing(exclude):
            try: s.send_packets(pkts)
            except Exception as e: log("Player", "send error: %r" % e)
    def handle_entity_attack(self, attacker, target_rid, player_pos, click_pos):
        """PocketMine Player::attackEntity-style validation for player-vs-player hits.
        This keeps combat generic: no item/weapon simulation is performed here.
        """
        target = None
        for s in self.playing():
            if s.rid == target_rid:
                target = s; break
        if target is None or target is attacker or target.dead: return False
        if attacker.attack_time > 0: return False
        dx = target.feet()[0] - attacker.feet()[0]; dy = (target.feet()[1] + 0.9) - (attacker.feet()[1] + 1.62); dz = target.feet()[2] - attacker.feet()[2]
        dist2 = dx*dx + dy*dy + dz*dz
        if dist2 > 16.0: return False  # conservative entity interaction reach
        # Sanity-check the client supplied attacker position; it must be close to the server position.
        af = attacker.feet()
        if sum((player_pos[i] - (af[i] + (0.0 if i != 1 else NETWORK_EYE_OFFSET)))**2 for i in range(3)) > 4.0:
            return False
        attacker.attack_time = 10
        target.damage(1.0, attacker)
        return True

    def break_block(self, p, x, y, z, old_key=None):
        """PocketMine World::useBreakOn subset for pywer's implemented blocks.

        The event/drop chain is deliberately explicit: validate target, remove block,
        then create the block's source-derived drops. Inventory insertion is not faked
        because pywer has no authoritative inventory implementation yet.
        """
        key = old_key or get_block(x, y, z)
        if key in ("air", "water", "bedrock") or get_block(x, y, z) != key:
            return False
        if not self.set_block(x, y, z, "air"):
            return False
        if GAMEMODE == 0:
            for item_key, count in DROP_FOR_BLOCK.get(key, []):
                self.drop_item((x + 0.5, y + 0.5, z + 0.5), item_key, count)
        return True

    def drop_item(self, pos, item_key, count=1):
        """PocketMine World::dropItem equivalent using AddItemActorPacket.

        PocketMine uses a small random X/Z impulse and Y=0.2. The item stack IDs
        come from the uploaded BedrockData required_item_list.json for 1.21.50.
        """
        if item_key not in ITEM_RUNTIME:
            return False
        eid = self.next_rid; self.next_rid += 1
        motion = (random.random() * 0.2 - 0.1, 0.2, random.random() * 0.2 - 0.1)
        self.item_entities[eid] = {"key":item_key, "count":int(count), "pos":tuple(pos), "motion":motion, "age":0.0}
        pkt = Session._pk(PID_ADD_ITEM_ACTOR, build_add_item_actor(eid, item_key, count, pos, motion))
        self.broadcast([pkt])
        return True

    def tick_item_pickups(self, player):
        if not self.item_entities: return
        pf=player.feet(); remove=[]
        for eid,e in list(self.item_entities.items()):
            x,y,z=e["pos"]; dx=x-pf[0]; dy=y-(pf[1]+0.9); dz=z-pf[2]
            if dx*dx+dy*dy+dz*dz > 2.25: continue
            key=e["key"]; item_id=ITEM_RUNTIME.get(key)
            if item_id is None: continue
            left=e["count"]
            # PocketMine-style addItem: fill matching stacks first, then empty slots.
            for i,st in enumerate(player.inventory):
                if left<=0: break
                if st[1] and st[0]==item_id and st[2]==0:
                    take=min(left,64-st[1]); player.inventory[i]=item_tuple(item_id,st[1]+take,0); left-=take
            for i,st in enumerate(player.inventory):
                if left<=0: break
                if st[1]==0:
                    take=min(left,64); player.inventory[i]=item_tuple(item_id,take,0); left-=take
            if left != e["count"]:
                taken=e["count"]-left; e["count"]=left
                player.sync_inventory()
                if left<=0:
                    remove.append(eid)
                    self.broadcast([Session._pk(PID_TAKE_ITEM_ACTOR, ByteWriter().write_varuint64(eid).write_varuint64(player.rid).get())])
                else:
                    # Re-spawn remaining stack to keep the client authoritative.
                    self.broadcast([Session._pk(PID_ADD_ITEM_ACTOR, build_add_item_actor(eid,key,left,e["pos"],(0,0,0)))])
        for eid in remove: self.item_entities.pop(eid,None)

    def set_block(self, x, y, z, key):
        """Change one block for everybody (also stored, so later chunk loads see it)."""
        if key not in BLOCK_RUNTIME: raise KeyError(key)
        if not (MIN_Y <= y <= MAX_Y): return False
        cx, cz = x >> 4, z >> 4
        EDITS.setdefault((cx, cz), {})[(x & 15, y, z & 15)] = key; CHUNK_CACHE.pop((cx, cz), None)
        self.broadcast([Session._pk(PID_UPDATE_BLOCK, build_update_block(x, y, z, key))]); return True
    def command(self, p, line):
        a = line.split()
        try:
            if a and a[0] == "blocks": p.chat_to("blocks: " + ", ".join(BLOCK_KEYS[1:]))
            elif a and a[0] == "setblock" and len(a) == 5:
                def co(v, cur): return math.floor(cur) + int(v[1:] or 0) if v.startswith("~") else int(v)
                x, y, z = co(a[1], p.pos[0]), co(a[2], p.pos[1] - 1.62), co(a[3], p.pos[2])
                ok = self.set_block(x, y, z, a[4]); p.chat_to("setblock %d %d %d %s %s" % (x, y, z, a[4], "ok" if ok else "out of range"))
            elif a and a[0] == "pos":
                f = p.feet(); p.chat_to("pos %.2f %.2f %.2f yaw %.1f pitch %.1f ground=%s fall=%.1f" % (f + (p.yaw, p.pitch, p.on_ground, p.fall_distance)))
            elif a and a[0] == "tp" and len(a) == 4:
                f = p.feet(); t = [(f[i] + float(v[1:] or 0)) if v.startswith("~") else float(v) for i, v in enumerate(a[1:4])]
                p.teleport(*t); p.chat_to("teleported to %.1f %.1f %.1f" % tuple(t))
            else: p.chat_to("!blocks | !setblock <x|~> <y|~> <z|~> <block> | !tp <x|~> <y|~> <z|~> | !pos")
        except KeyError: p.chat_to("unknown block (see !blocks)")
        except ValueError: p.chat_to("bad coordinates")
    def on_join(self, p):
        others = self.playing(exclude=p)
        p.send_packets([Session._pk(PID_PLAYER_LIST, build_player_list_add(others + [p]))] +
                       [Session._pk(PID_ADD_PLAYER, build_add_player(o)) for o in others])
        for o in others:
            o.send_packets([Session._pk(PID_PLAYER_LIST, build_player_list_add([p])), Session._pk(PID_ADD_PLAYER, build_add_player(p))])
        msg = "\u00a7e%s joined the game" % p.name
        self.broadcast([Session._pk(PID_TEXT, build_text(0, "", msg))])
        log("Player", "%s joined (%d online)" % (p.name, len(others) + 1))
    def on_leave(self, p):
        if not p.spawned: return
        p.spawned = False
        self.broadcast([Session._pk(PID_PLAYER_LIST, build_player_list_remove([p])),
                        Session._pk(PID_REMOVE_ACTOR, ByteWriter().write_varint64(p.rid).get()),
                        Session._pk(PID_TEXT, build_text(0, "", "\u00a7e%s left the game" % p.name))])
        log("Player", "%s left" % p.name)
    def step(self, timeout=0.02):
        rl, _, _ = select.select([self.sock], [], [], timeout)
        if rl:
            for _ in range(256):
                try: data, addr = self.sock.recvfrom(4096)
                except (BlockingIOError, InterruptedError): break
                except OSError: break
                if not data: continue
                try:
                    if data[0] & 0x80:
                        s = self.sessions.get(addr)
                        if s: s.on_datagram(data)
                    else:
                        self.unconnected(data, addr)
                except Exception as e:
                    log("RakNet", "error handling packet from %s: %r" % (addr, e))
        now = time.time()
        for a, s in list(self.sessions.items()):
            try: s.tick(now)
            except Exception as e: log("RakNet", "tick error: %r" % e)
            if s.state == "CLOSED" or now - s.last_rx > 30:
                del self.sessions[a]; self.on_leave(s)
    def run(self, stop=None):
        while not (stop and stop.is_set()): self.step()

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    srv = Server(port); srv.banner()
    try: srv.run()
    except KeyboardInterrupt: print("bye")

if __name__ == "__main__":
    main()

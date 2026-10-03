# ---------------------------------------------------------------- RakNet transport constants
import struct

RAKNET_MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")

def enc_addr(ip, port):
    return bytes([4]) + bytes((~int(x)) & 0xFF for x in ip.split(".")) + struct.pack(">H", port)
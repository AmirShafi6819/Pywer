# ---------------------------------------------------------------- RakNet transport constants
"""RakNet offline message constants and address serialization."""

import struct

RAKNET_MAGIC = bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")


def enc_addr(ip, port):
    """Encode an IPv4 address and port for RakNet datagrams."""
    octets = bytes((~int(x)) & 0xFF for x in ip.split("."))
    return bytes([4]) + octets + struct.pack(">H", port)
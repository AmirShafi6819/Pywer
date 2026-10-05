"""Regression tests for the unconnected (ping / discovery) path.

A Bedrock client lists a server only when the pong parses as the 12-field `;`-delimited
reply it expects, and joins only when the RakNet control packets use the flag bits every
other implementation uses. Both failures are invisible from inside Pywer: a swapped
ACK/NACK pair still round-trips between two Pywer ends, and a malformed pong simply
makes the entry disappear from the client's server list.

`unconnected()` only needs four members of its server, so the path is driven through a
duck-typed recorder instead of binding a real socket.
"""

import struct
import unittest

from pywer import config
from pywer.net.raknet import RAKNET_MAGIC
from pywer.server.server import Server, build_motd


class PingRecorder:
    def __init__(self, guid=0x0123456789ABCDEF, port=19132):
        self.guid = guid
        self.port = port
        self.sessions = {}
        self.sent = []

    def send(self, data, addr):
        self.sent.append((addr, data))
        return True


def unconnected_ping(pid=0x01, when=b"\x11\x22\x33\x44\x55\x66\x77\x88"):
    return bytes([pid]) + when + b"\x00" * 40


def ping_fields(reply):
    """The 12 payload fields of a pong, as the client splits them."""
    return reply[35:].decode("utf-8").split(";")


class TestUnconnectedPong(unittest.TestCase):
    def test_pong_layout_matches_the_raknet_unconnected_pong(self):
        srv = PingRecorder()
        addr = ("10.0.0.9", 50000)
        Server.unconnected(srv, unconnected_ping(), addr)
        self.assertEqual(len(srv.sent), 1)
        reply = srv.sent[0][1]
        sent_to, _ = srv.sent[0]
        self.assertEqual(sent_to, addr)
        self.assertEqual(reply[0], 0x1C)
        self.assertEqual(reply[1:9], b"\x11\x22\x33\x44\x55\x66\x77\x88")
        self.assertEqual(reply[9:17], struct.pack(">Q", srv.guid))
        self.assertEqual(reply[17:33], RAKNET_MAGIC)
        size = struct.unpack(">H", reply[33:35])[0]
        self.assertEqual(size, len(reply) - 35)

    def test_pong_has_the_canonical_twelve_fields(self):
        srv = PingRecorder()
        Server.unconnected(srv, unconnected_ping(), ("10.0.0.9", 50000))
        fields = ping_fields(srv.sent[0][1])
        self.assertEqual(len(fields), 13, "12 payload fields plus the trailing ';'")
        self.assertEqual(fields[0], "MCPE")
        self.assertEqual(fields[2], str(config.PROTOCOL))
        self.assertEqual(fields[3], config.GAME_VERSION)
        self.assertEqual(fields[10], "19132")

    def test_pong_reports_the_live_session_table(self):
        srv = PingRecorder()
        srv.sessions = {("10.0.0.1", 1): object(), ("10.0.0.2", 2): object()}
        Server.unconnected(srv, unconnected_ping(), ("10.0.0.9", 50000))
        self.assertEqual(ping_fields(srv.sent[0][1])[4], "2")

    def test_open_connections_ping_is_answered_like_a_plain_ping(self):
        plain, opened = PingRecorder(), PingRecorder()
        Server.unconnected(plain, unconnected_ping(0x01), ("10.0.0.9", 50000))
        Server.unconnected(opened, unconnected_ping(0x02), ("10.0.0.9", 50000))
        self.assertEqual(plain.sent[0][1][1:], opened.sent[0][1][1:])


class TestTruncatedUnconnectedPackets(unittest.TestCase):
    """Anything shorter than the packet it claims to be is dropped, not guessed at."""

    def test_ping_without_a_full_time_field_is_dropped(self):
        # The 8-byte time is echoed back verbatim and matched by the client; a shorter
        # one used to be padded by Python's slicing and answered with a pong no client
        # could pair with the ping it sent.
        for raw in (b"\x01", b"\x01\x00", b"\x01" + b"\x00" * 7, b"\x02" + b"\x00" * 7):
            srv = PingRecorder()
            Server.unconnected(srv, raw, ("10.0.0.9", 50000))
            self.assertEqual(srv.sent, [], "truncated ping answered: %r" % raw)

    def test_ocr1_without_the_magic_is_dropped(self):
        srv = PingRecorder()
        Server.unconnected(srv, b"\x05" + b"\x00" * 20, ("10.0.0.9", 50000))
        self.assertEqual(srv.sent, [])

    def test_ocr2_without_an_address_is_dropped_without_raising(self):
        # ByteReader raises "short read" past the end of the packet. Upstream that
        # exception was caught per datagram and logged, so a single-byte 0x07 was a
        # ready-made log-flood.
        for raw in (b"\x07", b"\x07" + b"\x00" * 16, b"\x07" + RAKNET_MAGIC + b"\x04"):
            srv = PingRecorder()
            srv.next_rid = 1
            srv.on_leave = lambda s: None
            Server.unconnected(srv, raw, ("10.0.0.9", 50000))
            self.assertEqual(srv.sent, [])
            self.assertEqual(srv.sessions, {})

    def test_ocr2_address_without_trailing_mtu_and_guid_is_dropped(self):
        srv = PingRecorder()
        srv.next_rid = 1
        srv.on_leave = lambda s: None
        # 0x04 + 4 octets + 2 port bytes present, MTU and client GUID missing.
        Server.unconnected(srv, b"\x07" + RAKNET_MAGIC + b"\x04" + b"\x00" * 6, ("10.0.0.9", 50000))
        self.assertEqual(srv.sent, [])
        self.assertEqual(srv.sessions, {})


class TestMotdTitle(unittest.TestCase):
    def _title(self, value):
        original = config.SERVER_TITLE
        try:
            config.SERVER_TITLE = value
            return build_motd(1, 19132).split(";")
        finally:
            config.SERVER_TITLE = original

    def test_server_title_is_the_advertised_name(self):
        # server.properties calls this key "motd" and documents it as the name shown in
        # the client's server list, so it has to reach the pong instead of the version
        # string that was hardcoded into it.
        fields = self._title("My Epic Server")
        self.assertEqual(fields[1], "My Epic Server")

    def test_title_cannot_smash_the_field_separator(self):
        fields = self._title("two;parts\nand\rnewlines")
        self.assertEqual(len(fields), 13, "the title split the pong into extra fields")
        for char in ";\r\n":
            self.assertNotIn(char, fields[1])

    def test_title_is_bounded(self):
        fields = self._title("x" * 5000)
        self.assertLessEqual(len(fields[1]), 128)

    def test_empty_title_falls_back_to_the_versioned_name(self):
        from pywer import __version__

        fields = self._title("   ")
        self.assertEqual(fields[1], "pywer-v%s" % __version__)


if __name__ == "__main__":
    unittest.main()

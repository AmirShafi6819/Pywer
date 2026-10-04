"""Regression tests for the RakNet reliability layer.

These cover the transport invariants the rest of the server depends on: the ACK/NACK
direction on both the receive and transmit side, retransmission reusing its original
sequence number, 24-bit counter wrap, and the resource ceilings that keep a single
peer from growing server state without bound.
"""

import struct
import time
import unittest

from pywer.player.session import Session


class FakeServer:
    next_rid = 1

    def __init__(self):
        self.sent = []

    def send(self, data, addr):
        self.sent.append(data)
        return True


def make_session():
    srv = FakeServer()
    s = Session(srv, ("127.0.0.1", 19132), 1492, 42)
    return s, srv


def data_datagram(seq, frames):
    return b"\x84" + (seq & 0xFFFFFF).to_bytes(3, "little") + b"".join(frames)


def reliable_frame(payload, ridx):
    """RELIAble (unsequenced) frame: flags, length in bits, reliable index."""
    return (
        bytes([2 << 5])
        + struct.pack(">H", len(payload) * 8)
        + (ridx & 0xFFFFFF).to_bytes(3, "little")
        + payload
    )


def ordered_frame(payload, ridx, oidx, ch=0):
    """RELIABLE_ORDERED frame: flags, length, reliable index, order index, channel."""
    return (
        bytes([3 << 5])
        + struct.pack(">H", len(payload) * 8)
        + (ridx & 0xFFFFFF).to_bytes(3, "little")
        + (oidx & 0xFFFFFF).to_bytes(3, "little")
        + bytes([ch])
        + payload
    )


def split_frame(payload, ridx, oidx, cnt, sid, idx, ch=0):
    return (
        bytes([(3 << 5) | 0x10])
        + struct.pack(">H", len(payload) * 8)
        + (ridx & 0xFFFFFF).to_bytes(3, "little")
        + (oidx & 0xFFFFFF).to_bytes(3, "little")
        + bytes([ch])
        + struct.pack(">IHI", cnt, sid, idx)
        + payload
    )


def record_packet(pid, seqs):
    """ACK/NACK packet built independently of the code under test."""
    recs = b"".join(
        b"\x01" + (s & 0xFFFFFF).to_bytes(3, "little") for s in seqs
    )
    return bytes([pid]) + struct.pack(">H", len(seqs)) + recs


def wire_seq(datagram):
    return int.from_bytes(datagram[1:4], "little")


class TestAckNackDirection(unittest.TestCase):
    def test_ack_does_not_retransmit(self):
        s, srv = make_session()
        s._send_datagram([b"frame"])
        s.on_datagram(record_packet(0xA0, [0]))
        self.assertEqual(s.pending, {})
        s.tick(time.time())
        self.assertEqual(srv.sent, [data_datagram(0, [b"frame"])])

    def test_nack_retransmits_original_sequence(self):
        s, srv = make_session()
        s._send_datagram([b"first"])
        s._send_datagram([b"second"])
        s.on_datagram(record_packet(0xC0, [0]))
        self.assertIn(0, s.pending)
        self.assertIn(1, s.pending)
        self.assertEqual(srv.sent[-1], data_datagram(0, [b"first"]))

    def test_tick_reports_received_as_ack_and_gaps_as_nack(self):
        s, srv = make_session()
        s.on_datagram(data_datagram(0, [reliable_frame(b"a", 0)]))
        s.on_datagram(data_datagram(3, [reliable_frame(b"b", 1)]))
        s.tick(time.time())
        acks = [d for d in srv.sent if d[0] == 0xA0]
        nacks = [d for d in srv.sent if d[0] == 0xC0]
        self.assertEqual(len(acks), 1)
        self.assertEqual(len(nacks), 1)
        self.assertEqual(sorted(Session._records(None, acks[0])), [0, 3])
        self.assertEqual(Session._records(None, nacks[0]), [1, 2])

    def test_duplicate_datagram_is_acknowledged_but_processed_once(self):
        s, srv = make_session()
        seen = []
        s.on_rak_payload = seen.append
        pkt = data_datagram(0, [reliable_frame(b"a", 0)])
        s.on_datagram(pkt)
        s.on_datagram(pkt)
        self.assertEqual(seen, [b"a"])
        self.assertIn(0, s.ack_q)

    def test_timer_resend_keeps_pending_entry(self):
        s, srv = make_session()
        s._send_datagram([b"frame"])
        future = time.time() + s.RESEND_AFTER + 0.5
        s.tick(future)
        self.assertIn(0, s.pending)
        self.assertEqual(srv.sent[-1], data_datagram(0, [b"frame"]))
        before = len(srv.sent)
        s.tick(future + s.RESEND_AFTER + 0.5)
        self.assertGreater(len(srv.sent), before)


class TestSequenceWrap(unittest.TestCase):
    def test_incoming_wrap_extends_monotonically(self):
        s, _ = make_session()
        s.max_seq = 0xFFFFFF
        s.on_datagram(data_datagram(0, [reliable_frame(b"a", 0)]))
        self.assertEqual(s.max_seq, 0x1000000)

    def test_outgoing_counters_wrap_without_error(self):
        s, srv = make_session()
        s.send_seq = 0xFFFFFF
        s.rel_idx = 0xFFFFFF
        s.ord_idx = 0xFFFFFF
        s.send_rak(b"\xfe\x00")
        self.assertEqual(wire_seq(srv.sent[-1]), 0xFFFFFF)
        self.assertIn(0xFFFFFF, s.pending)
        s.send_rak(b"\xfe\x00")
        self.assertEqual(wire_seq(srv.sent[-1]), 0)
        self.assertIn(0x1000000, s.pending)

    def test_ack_across_wrap_clears_original_pending(self):
        s, srv = make_session()
        s.send_seq = 0x1000001
        s.pending[0xFFFFFF] = (time.time(), [b"frame"])
        s.on_datagram(record_packet(0xA0, [0xFFFFFF]))
        self.assertNotIn(0xFFFFFF, s.pending)

    def test_ackpkt_never_straddles_the_wrap(self):
        pkt = Session._ackpkt(0xA0, [0xFFFFFF, 0x1000000, 0x1000001])
        self.assertEqual(sorted(Session._records(None, pkt)), [0, 1, 0xFFFFFF])

    def test_ordering_delivers_across_wrap(self):
        s, _ = make_session()
        seen = []
        s.on_rak_payload = seen.append
        s.order_next[0] = 0xFFFFFF
        s.on_datagram(data_datagram(0, [ordered_frame(b"a", 0, 0xFFFFFF)]))
        s.on_datagram(data_datagram(1, [ordered_frame(b"b", 1, 0x000000)]))
        self.assertEqual(seen, [b"a", b"b"])
        self.assertEqual(s.order_next[0], 0x1000001)

    def test_reliable_index_dedup_wraps(self):
        s, _ = make_session()
        seen = []
        s.on_rak_payload = seen.append
        s.max_rel = 0xFFFFFF
        s.on_datagram(data_datagram(0, [reliable_frame(b"a", 0xFFFFFF)]))
        s.on_datagram(data_datagram(1, [reliable_frame(b"b", 0x000000)]))
        self.assertEqual(seen, [b"a", b"b"])


class TestResourceCeilings(unittest.TestCase):
    def test_unacknowledged_peer_is_dropped(self):
        s, _ = make_session()
        s.pending = {i: (time.time(), [b"x"]) for i in range(s.MAX_PENDING)}
        s.send_rak(b"\xfe\x00")
        self.assertEqual(s.state, "CLOSED")
        self.assertEqual(s.pending[s.MAX_PENDING - 1][1], [b"x"])

    def test_closed_session_stops_sending(self):
        s, srv = make_session()
        s.state = "CLOSED"
        s.send_rak(b"\xfe\x00")
        self.assertEqual(srv.sent, [])
        s.on_datagram(data_datagram(0, [reliable_frame(b"a", 0)]))
        self.assertEqual(srv.sent, [])

    def test_ack_and_nack_queues_are_bounded(self):
        s, _ = make_session()
        s.on_rak_payload = lambda p: None
        for seq in range(s.MAX_QUEUE + 16):
            s.on_datagram(data_datagram(seq, [reliable_frame(b"p", seq)]))
        self.assertLessEqual(len(s.ack_q), s.MAX_QUEUE)
        self.assertLessEqual(len(s.nack_q), s.MAX_QUEUE)

    def test_gap_window_is_bounded(self):
        s, _ = make_session()
        s.on_rak_payload = lambda p: None
        s.on_datagram(data_datagram(s.MAX_GAP * 4, [reliable_frame(b"a", 0)]))
        self.assertLessEqual(len(s.nack_q), s.MAX_QUEUE)

    def test_split_part_count_is_validated(self):
        s, _ = make_session()
        s.on_datagram(
            data_datagram(0, [split_frame(b"p", 0, 0, 0, 1, 0)])
        )
        self.assertEqual(s.state, "CLOSED")

    def test_concurrent_splits_are_bounded(self):
        s, _ = make_session()
        for sid in range(s.MAX_SPLITS):
            s.on_datagram(
                data_datagram(sid, [split_frame(b"p", sid, 0, 2, sid, 0)])
            )
        self.assertNotEqual(s.state, "CLOSED")
        s.on_datagram(
            data_datagram(
                s.MAX_SPLITS, [split_frame(b"p", 4096, 0, 2, 999, 0)]
            )
        )
        self.assertEqual(s.state, "CLOSED")

    def test_stale_splits_are_discarded(self):
        s, _ = make_session()
        s.on_datagram(data_datagram(0, [split_frame(b"p", 0, 0, 2, 7, 0)]))
        self.assertIn(7, s.splits)
        s.tick(time.time() + s.SPLIT_TTL + 1)
        self.assertNotIn(7, s.splits)

    def test_ordering_window_overflow_closes_session(self):
        s, _ = make_session()
        s.on_datagram(
            data_datagram(0, [ordered_frame(b"a", 0, s.MAX_ORDER_WINDOW + 1)])
        )
        self.assertEqual(s.state, "CLOSED")


if __name__ == "__main__":
    unittest.main()

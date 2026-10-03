"""Unit tests for the 6-priority event bus, cancellation, and fault isolation."""

import unittest
from pywer.event import (
    Event,
    Cancellable,
    EventPriority,
    Listener,
    listen,
    EventManager,
)
from pywer.event.player import PlayerChatEvent, PlayerJoinEvent, PlayerMoveEvent
from pywer.event.block import BlockBreakEvent
from pywer.event.entity import EntityDamageEvent


class TestEventSystem(unittest.TestCase):
    def test_priority_ordering(self):
        bus = EventManager()
        order = []

        class OrderedListener(Listener):
            @listen(priority=EventPriority.MONITOR)
            def on_monitor(self, event):
                order.append("MONITOR")

            @listen(priority=EventPriority.LOWEST)
            def on_lowest(self, event):
                order.append("LOWEST")

            @listen(priority=EventPriority.NORMAL)
            def on_normal(self, event):
                order.append("NORMAL")

            @listen(priority=EventPriority.HIGHEST)
            def on_highest(self, event):
                order.append("HIGHEST")

            @listen(priority=EventPriority.LOW)
            def on_low(self, event):
                order.append("LOW")

            @listen(priority=EventPriority.HIGH)
            def on_high(self, event):
                order.append("HIGH")

        bus.register_listener(OrderedListener())
        event = PlayerJoinEvent(None, "Welcome")
        bus.call(event)
        self.assertEqual(
            order, ["LOWEST", "LOW", "NORMAL", "HIGH", "HIGHEST", "MONITOR"]
        )

    def test_cancellation_and_ignore_cancelled(self):
        bus = EventManager()
        saw_chat = []

        class CancelListener(Listener):
            @listen(priority=EventPriority.LOW)
            def on_low(self, event):
                event.cancel()

            @listen(priority=EventPriority.NORMAL, ignore_cancelled=True)
            def on_normal(self, event):
                saw_chat.append("NORMAL")

            @listen(priority=EventPriority.HIGH, ignore_cancelled=False)
            def on_high(self, event):
                saw_chat.append("HIGH")

            @listen(priority=EventPriority.MONITOR)
            def on_monitor(self, event):
                saw_chat.append("MONITOR")

        bus.register_listener(CancelListener())
        event = PlayerChatEvent(None, "bad word")
        bus.call(event)
        self.assertTrue(event.is_cancelled)
        self.assertEqual(saw_chat, ["HIGH", "MONITOR"])

    def test_fault_isolation(self):
        bus = EventManager()
        order = []

        class BuggyListener(Listener):
            @listen(priority=EventPriority.LOW)
            def on_low(self, event):
                order.append("LOW")
                raise RuntimeError("Explosion in plugin listener!")

            @listen(priority=EventPriority.NORMAL)
            def on_normal(self, event):
                order.append("NORMAL")

        bus.register_listener(BuggyListener())
        event = PlayerJoinEvent(None, "Test")
        # Calling event must NOT raise RuntimeError
        bus.call(event)
        self.assertEqual(order, ["LOW", "NORMAL"])

    def test_functional_subscription(self):
        bus = EventManager()
        results = []

        def handle_break(event):
            results.append((event.x, event.y, event.z, event.block_key))

        bus.subscribe(BlockBreakEvent, handle_break, priority=EventPriority.NORMAL)
        bus.call(BlockBreakEvent(None, 10, 64, 10, "stone"))
        self.assertEqual(results, [(10, 64, 10, "stone")])

    def test_unregister_by_plugin(self):
        bus = EventManager()
        order = []
        dummy_plugin = object()

        class PluginListener(Listener):
            @listen()
            def on_move(self, event):
                order.append("MOVED")

        bus.register_listener(PluginListener(), plugin=dummy_plugin)
        bus.call(PlayerMoveEvent(None, (0, 64, 0), (1, 64, 0)))
        self.assertEqual(order, ["MOVED"])

        # Unregister
        bus.unregister_by_plugin(dummy_plugin)
        bus.call(PlayerMoveEvent(None, (1, 64, 0), (2, 64, 0)))
        self.assertEqual(order, ["MOVED"])  # No new calls


if __name__ == "__main__":
    unittest.main()

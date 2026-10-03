"""Sample Pywer Plugin demonstrating complete PluginBase capabilities."""

from typing import List

from pywer.command import Command, CommandSender
from pywer.event import EventPriority, Listener, listen
from pywer.event.player import PlayerChatEvent, PlayerJoinEvent
from pywer.plugin.base import PluginBase

from .utils.banner import make_welcome_banner


class PingCommand(Command):
    """Simple ping command returning pong with optional echo."""

    def __init__(self, plugin: "SamplePlugin") -> None:
        super().__init__(
            name="ping",
            description="Checks server responsiveness",
            usage="/ping [message]",
            aliases=["p", "pong"],
        )
        self.plugin = plugin

    def execute(self, sender: CommandSender, args: List[str]) -> bool:
        extra = f" ({' '.join(args)})" if args else ""
        sender.send_message(f"§aPong!{extra}")
        return True


class SamplePlugin(PluginBase, Listener):
    """Core plugin class managing event listeners and background scheduled tasks."""

    def __init__(self) -> None:
        super().__init__()
        self.joins_received = 0
        self.chat_messages = []
        self.heartbeat_ticks = 0

    def on_load(self) -> None:
        self.logger.info("SamplePlugin loaded into virtual memory!")

    def on_enable(self) -> None:
        self.logger.info(f"Enabling SamplePlugin v{self.version}...")

        # Initialize config defaults
        if not self.config.get("motd"):
            self.config.set("motd", "Pywer Bedrock Server")
            self.config.save()

        # Register event listeners
        self.register_listener(self)

        # Register custom commands
        self.register_command(PingCommand(self))

        # Schedule repeating heartbeat task every 20 ticks (1 second)
        self.run_repeating(1, 20, self._on_heartbeat)

        self.logger.info("SamplePlugin enabled successfully!")

    def on_disable(self) -> None:
        self.logger.info("SamplePlugin disabled cleanly.")

    def _on_heartbeat(self) -> None:
        self.heartbeat_ticks += 1

    @listen(priority=EventPriority.NORMAL)
    def on_player_join(self, event: PlayerJoinEvent) -> None:
        self.joins_received += 1
        motd = self.config.get("motd", "Pywer Bedrock Server")
        banner = make_welcome_banner(
            event.player.name if event.player else "Adventurer", motd
        )
        if event.player and hasattr(event.player, "chat_to"):
            event.player.chat_to(banner)

    @listen(priority=EventPriority.HIGH)
    def on_player_chat(self, event: PlayerChatEvent) -> None:
        self.chat_messages.append(
            (event.player.name if event.player else "Unknown", event.message)
        )
        # Filter forbidden words
        if "badword" in event.message.lower():
            event.cancel()
            if event.player and hasattr(event.player, "chat_to"):
                event.player.chat_to(
                    "§cYour message was blocked by SamplePlugin profanity filter."
                )

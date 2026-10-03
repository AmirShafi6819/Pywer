"""Player-related event classes."""

from typing import Any, Optional, Tuple
from .base import Event, Cancellable


class PlayerEvent(Event):
    """Base class for events initiated by or concerning a player."""

    def __init__(self, player: Any, **kwargs: Any) -> None:
        super().__init__()
        self.player = player
        self.__dict__.update(kwargs)


class PlayerJoinEvent(PlayerEvent):
    """Fired when a player completes authentication and enters the world."""

    def __init__(self, player: Any, message: Optional[str] = None) -> None:
        super().__init__(player)
        self.message = message


class PlayerQuitEvent(PlayerEvent):
    """Fired when a player disconnects from the server."""

    def __init__(self, player: Any, message: Optional[str] = None) -> None:
        super().__init__(player)
        self.message = message


class PlayerChatEvent(Cancellable, PlayerEvent):
    """Fired when a player sends a public in-game chat message."""

    def __init__(self, player: Any, message: str, chat_format: str = "<%s> %s") -> None:
        super().__init__(player)
        self.message = message
        self.format = chat_format


class PlayerCommandPreprocessEvent(Cancellable, PlayerEvent):
    """Fired before a command string starting with '/' or '!' is executed."""

    def __init__(self, player: Any, message: str) -> None:
        super().__init__(player)
        self.message = message

    @property
    def command(self) -> str:
        return self.message

    @command.setter
    def command(self, val: str) -> None:
        self.message = val


class PlayerMoveEvent(Cancellable, PlayerEvent):
    """Fired when a player moves between positions."""

    def __init__(
        self,
        player: Any,
        from_pos: Tuple[float, float, float],
        to_pos: Tuple[float, float, float],
    ) -> None:
        super().__init__(player)
        self.from_pos = from_pos
        self.to_pos = to_pos


class PlayerInteractEvent(Cancellable, PlayerEvent):
    """Fired when a player clicks a block or uses an item in air."""

    def __init__(
        self,
        player: Any,
        item: Any,
        action: int,
        block_pos: Optional[Tuple[int, int, int]] = None,
        face: Optional[int] = None,
    ) -> None:
        super().__init__(player)
        self.item = item
        self.action = action
        self.block_pos = block_pos
        self.face = face


class PlayerDropItemEvent(Cancellable, PlayerEvent):
    """Fired when a player drops an item into the world."""

    def __init__(self, player: Any, item: Any) -> None:
        super().__init__(player)
        self.item = item


class PlayerDeathEvent(PlayerEvent):
    """Fired when a player dies."""

    def __init__(
        self,
        player: Any,
        death_message: Optional[str] = None,
        keep_inventory: bool = False,
    ) -> None:
        super().__init__(player)
        self.death_message = death_message
        self.keep_inventory = keep_inventory


class PlayerRespawnEvent(PlayerEvent):
    """Fired when a dead player respawns."""

    def __init__(self, player: Any, respawn_pos: Tuple[float, float, float]) -> None:
        super().__init__(player)
        self.respawn_pos = respawn_pos

"""Command sender abstractions and concrete implementations for players and console."""

import abc
from typing import Any, Optional


class CommandSender(abc.ABC):
    """Abstract entity capable of executing commands and receiving messages."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Name of the command sender."""
        pass

    @property
    @abc.abstractmethod
    def is_player(self) -> bool:
        """Whether this sender is an active in-game player."""
        pass

    @property
    @abc.abstractmethod
    def is_op(self) -> bool:
        """Whether this sender has operator / administrator permissions."""
        pass

    @abc.abstractmethod
    def send_message(self, message: str) -> None:
        """Sends a message back to the sender."""
        pass

    def has_permission(self, permission: Optional[str]) -> bool:
        """Checks if sender has the specified permission node."""
        if not permission:
            return True
        return self.is_op


class PlayerCommandSender(CommandSender):
    """Command sender representing an active player Session."""

    def __init__(self, session: Any) -> None:
        self._session = session

    @property
    def session(self) -> Any:
        return self._session

    @property
    def player(self) -> Any:
        return self._session

    @property
    def name(self) -> str:
        return getattr(self._session, "name", "Player")

    @property
    def is_player(self) -> bool:
        return True

    @property
    def is_op(self) -> bool:
        if hasattr(self._session, "is_op"):
            return bool(self._session.is_op)
        if hasattr(self._session, "gamemode_is_creative"):
            return self._session.gamemode_is_creative()
        return True

    def send_message(self, message: str) -> None:
        if hasattr(self._session, "chat_to"):
            self._session.chat_to(message)


class ConsoleCommandSender(CommandSender):
    """Command sender representing the server console."""

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "CONSOLE"

    @property
    def is_player(self) -> bool:
        return False

    @property
    def is_op(self) -> bool:
        return True

    def send_message(self, message: str) -> None:
        print(f"[Console] {message}")
        try:
            from ..log import log
            log("Console", message)
        except Exception:
            pass

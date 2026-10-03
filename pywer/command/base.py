"""Base class for server and plugin commands."""

from typing import Any, List, Optional
from .sender import CommandSender


class Command:
    """Represents an executable command in the Pywer server."""

    def __init__(
        self,
        name: str,
        description: str = "",
        usage: str = "",
        aliases: Optional[List[str]] = None,
        permission: Optional[str] = None,
    ) -> None:
        self.name = name.lower()
        self.description = description
        self.usage = usage or f"/{self.name}"
        self.aliases = [a.lower() for a in (aliases or [])]
        self.permission = permission
        self.plugin: Optional[Any] = None

    def execute(self, sender: CommandSender, args: List[str]) -> bool:
        """Executes the command. Returns True on success, or False if usage help should be displayed."""
        raise NotImplementedError

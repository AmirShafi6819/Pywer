"""Server lifecycle and plugin management event classes."""

from typing import Any
from .base import Event


class ServerEvent(Event):
    """Base class for server-wide lifecycle events."""

    def __init__(self, server: Any) -> None:
        super().__init__()
        self.server = server


class ServerLoadEvent(ServerEvent):
    """Fired when the server has finished world loading and network initialization."""

    pass


class ServerStopEvent(ServerEvent):
    """Fired when the server is beginning its shutdown process."""

    pass


class PluginEvent(Event):
    """Base class for events concerning plugin activation/deactivation."""

    def __init__(self, plugin: Any) -> None:
        super().__init__()
        self.plugin = plugin


class PluginEnableEvent(PluginEvent):
    """Fired when a plugin has been successfully enabled."""

    pass


class PluginDisableEvent(PluginEvent):
    """Fired when a plugin has been disabled."""

    pass

"""Pywer Command Subsystem.

Provides unified command dispatching, permission checks, sender abstractions
(PlayerCommandSender, ConsoleCommandSender), and plugin command registration.
"""

from .base import Command
from .manager import CommandManager
from .sender import CommandSender, ConsoleCommandSender, PlayerCommandSender

__all__ = [
    "Command",
    "CommandSender",
    "PlayerCommandSender",
    "ConsoleCommandSender",
    "CommandManager",
]

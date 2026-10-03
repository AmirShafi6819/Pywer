"""Pywer Event Subsystem.

Provides 6-priority event dispatch, cancellation mechanics, listener decorators,
and comprehensive Minecraft Bedrock player, entity, block, and server events.
"""

from .base import Cancellable, Event, EventPriority, Listener, listen
from .manager import EventManager
from .player import (
    PlayerChatEvent,
    PlayerCommandPreprocessEvent,
    PlayerDeathEvent,
    PlayerDropItemEvent,
    PlayerEvent,
    PlayerInteractEvent,
    PlayerJoinEvent,
    PlayerMoveEvent,
    PlayerQuitEvent,
    PlayerRespawnEvent,
)
from .block import BlockBreakEvent, BlockEvent, BlockInteractEvent, BlockPlaceEvent
from .entity import (
    EntityDamageByEntityEvent,
    EntityDamageEvent,
    EntityDespawnEvent,
    EntityEvent,
    EntitySpawnEvent,
    ProjectileHitEvent,
)
from .server import (
    PluginDisableEvent,
    PluginEnableEvent,
    PluginEvent,
    ServerEvent,
    ServerLoadEvent,
    ServerStopEvent,
)

manager = EventManager()

__all__ = [
    "Event",
    "Cancellable",
    "EventPriority",
    "Listener",
    "listen",
    "EventManager",
    "manager",
    "PlayerEvent",
    "PlayerJoinEvent",
    "PlayerQuitEvent",
    "PlayerChatEvent",
    "PlayerCommandPreprocessEvent",
    "PlayerMoveEvent",
    "PlayerInteractEvent",
    "PlayerDropItemEvent",
    "PlayerDeathEvent",
    "PlayerRespawnEvent",
    "BlockEvent",
    "BlockBreakEvent",
    "BlockPlaceEvent",
    "BlockInteractEvent",
    "EntityEvent",
    "EntityDamageEvent",
    "EntityDamageByEntityEvent",
    "EntitySpawnEvent",
    "EntityDespawnEvent",
    "ProjectileHitEvent",
    "ServerEvent",
    "ServerLoadEvent",
    "ServerStopEvent",
    "PluginEvent",
    "PluginEnableEvent",
    "PluginDisableEvent",
]

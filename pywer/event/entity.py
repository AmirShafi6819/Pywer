"""Entity-related event classes."""

from typing import Any, Optional, Tuple
from .base import Event, Cancellable


class EntityEvent(Event):
    """Base class for events concerning a world entity."""

    def __init__(self, entity: Any) -> None:
        super().__init__()
        self.entity = entity


class EntityDamageEvent(Cancellable, EntityEvent):
    """Fired when an entity takes damage."""

    def __init__(self, entity: Any, amount: float, cause: str = "generic") -> None:
        super().__init__(entity)
        self.amount = float(amount)
        self.cause = cause


class EntityDamageByEntityEvent(EntityDamageEvent):
    """Fired when an entity is damaged by another entity (mob attack, projectile, player)."""

    def __init__(self, entity: Any, damager: Any, amount: float, cause: str = "entity_attack") -> None:
        super().__init__(entity, amount, cause)
        self.damager = damager


class EntitySpawnEvent(Cancellable, EntityEvent):
    """Fired when an entity is spawned into the world."""

    def __init__(self, entity: Any, pos: Tuple[float, float, float]) -> None:
        super().__init__(entity)
        self.pos = pos


class EntityDespawnEvent(EntityEvent):
    """Fired when an entity is despawned or removed from the world."""

    def __init__(self, entity: Any) -> None:
        super().__init__(entity)


class ProjectileHitEvent(Cancellable, EntityEvent):
    """Fired when a projectile hits a block or living entity."""

    def __init__(self, projectile: Any, hit_type: str, hit_target: Any, hit_pos: Tuple[float, float, float]) -> None:
        super().__init__(projectile)
        self.hit_type = hit_type
        self.hit_target = hit_target
        self.hit_pos = hit_pos

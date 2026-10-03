"""Core event definitions, priority levels, and listener decorators."""

from enum import IntEnum
from typing import Callable, Any


class EventPriority(IntEnum):
    """Execution priority levels for event handlers (runs 0 -> 5)."""

    LOWEST = 0
    LOW = 1
    NORMAL = 2
    HIGH = 3
    HIGHEST = 4
    MONITOR = 5


class Cancellable:
    """Mixin for events that can be prevented by event listeners."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cancelled = False

    def cancel(self) -> None:
        """Cancels the event."""
        self._cancelled = True

    def uncancel(self) -> None:
        """Un-cancels the event."""
        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        """Returns True if the event has been cancelled."""
        return self._cancelled


class Event:
    """Base class for all world and server events."""

    def __init__(self) -> None:
        pass

    @property
    def event_name(self) -> str:
        """Name of the event class."""
        return self.__class__.__name__


class Listener:
    """Marker class for event listener containers."""

    pass


def listen(
    event_or_priority: Any = None,
    priority: EventPriority = EventPriority.NORMAL,
    ignore_cancelled: bool = True,
) -> Callable:
    """Decorator to mark a method on a Listener class as an event handler."""
    event_cls = None
    if isinstance(event_or_priority, type) and issubclass(event_or_priority, Event):
        event_cls = event_or_priority
    elif isinstance(event_or_priority, (EventPriority, int)):
        priority = EventPriority(event_or_priority)

    def decorator(fn: Callable) -> Callable:
        fn._listener_meta = {
            "event_cls": event_cls,
            "priority": EventPriority(priority),
            "ignore_cancelled": bool(ignore_cancelled),
        }
        return fn

    return decorator

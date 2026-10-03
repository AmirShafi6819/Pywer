"""Event manager with 6-level priority dispatch, cancellation semantics, and fault isolation."""

import inspect
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from .base import Cancellable, Event, EventPriority, Listener


class EventManager:
    """Central event bus supporting priority-based dispatch and plugin lifecycle scoping."""

    def __init__(self) -> None:
        # event_cls -> list of (priority, ignore_cancelled, handler, plugin)
        self._handlers: Dict[
            Type[Event], List[Tuple[EventPriority, bool, Callable, Any]]
        ] = {}

    def subscribe(
        self,
        event_cls: Type[Event],
        handler: Callable[[Any], None],
        priority: EventPriority = EventPriority.NORMAL,
        ignore_cancelled: bool = True,
        plugin: Any = None,
    ) -> Callable:
        """Subscribes a functional callback to an event type."""
        priority = EventPriority(priority)
        entries = self._handlers.setdefault(event_cls, [])
        entries.append((priority, bool(ignore_cancelled), handler, plugin))
        # Keep sorted ascending by priority (0=LOWEST ... 5=MONITOR)
        entries.sort(key=lambda item: int(item[0]))
        return handler

    def register_listener(
        self, listener: Listener, plugin: Any = None
    ) -> int:
        """Inspects and registers all @listen decorated methods on a Listener instance."""
        registered_count = 0
        for name in dir(listener):
            if name.startswith("_"):
                continue
            val = getattr(listener, name, None)
            if not callable(val):
                continue

            meta = getattr(val, "_listener_meta", None)
            if meta is None:
                continue

            event_cls = meta.get("event_cls")
            if event_cls is None:
                # Infer from type annotation or method name
                event_cls = self._infer_event_cls(val, name)

            if event_cls is not None and issubclass(event_cls, Event):
                self.subscribe(
                    event_cls,
                    val,
                    priority=meta.get("priority", EventPriority.NORMAL),
                    ignore_cancelled=meta.get("ignore_cancelled", True),
                    plugin=plugin,
                )
                registered_count += 1

        return registered_count

    def _infer_event_cls(self, fn: Callable, method_name: str) -> Type[Event]:
        """Infers the Event class from method signature annotations or method name."""
        try:
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())
            for param in params:
                if param.name in ("self", "cls"):
                    continue
                if (
                    param.annotation != inspect.Parameter.empty
                    and isinstance(param.annotation, type)
                    and issubclass(param.annotation, Event)
                ):
                    return param.annotation
        except Exception:
            pass

        # Match by snake_case name (e.g., on_player_chat -> PlayerChatEvent, or on_move -> PlayerMoveEvent)
        clean_name = method_name
        if clean_name.startswith("on_"):
            clean_name = clean_name[3:]

        for known_cls in self._all_event_classes():
            snake = _to_snake(known_cls.__name__)
            # Check exact match e.g. player_chat_event or player_chat
            if clean_name in (snake, snake.replace("_event", "")):
                return known_cls
            # Check token match e.g. on_move -> "move" in ["player", "move"]
            tokens = snake.replace("_event", "").split("_")
            if clean_name in tokens:
                return known_cls

        return Event

    def _all_event_classes(self) -> List[Type[Event]]:
        """Returns all currently imported Event subclasses."""
        result = []
        stack = [Event]
        while stack:
            curr = stack.pop()
            for sub in curr.__subclasses__():
                result.append(sub)
                stack.append(sub)
        return result

    def unregister_by_plugin(self, plugin: Any) -> int:
        """Detaches all handlers registered by the specified plugin."""
        removed = 0
        for event_cls in list(self._handlers.keys()):
            original = self._handlers[event_cls]
            filtered = [item for item in original if item[3] is not plugin]
            removed += len(original) - len(filtered)
            if filtered:
                self._handlers[event_cls] = filtered
            else:
                del self._handlers[event_cls]
        return removed

    def call(self, event: Event) -> Event:
        """Dispatches an event through all matching handlers in strict priority order."""
        event_cls = type(event)
        # Collect handlers for event_cls and all superclasses (e.g. PlayerEvent, Event)
        matching_handlers: List[Tuple[EventPriority, bool, Callable, Any]] = []

        for cls in event_cls.__mro__:
            if issubclass(cls, Event) and cls in self._handlers:
                matching_handlers.extend(self._handlers[cls])

        if not matching_handlers:
            return event

        # Sort combined handlers by priority (0=LOWEST to 5=MONITOR)
        matching_handlers.sort(key=lambda item: int(item[0]))

        is_cancellable = isinstance(event, Cancellable)

        for priority, ignore_cancelled, handler, plugin in matching_handlers:
            if is_cancellable and event.is_cancelled:
                # MONITOR priority always executes; other handlers skip if ignore_cancelled is True
                if priority != EventPriority.MONITOR and ignore_cancelled:
                    continue

            try:
                handler(event)
            except Exception as e:
                self._log_handler_error(event, handler, plugin, e)

        return event

    def _log_handler_error(
        self, event: Event, handler: Callable, plugin: Any, exc: Exception
    ) -> None:
        """Logs an unhandled listener exception without interrupting dispatch."""
        plugin_name = getattr(plugin, "name", None) or getattr(
            getattr(plugin, "manifest", None), "name", "Core"
        )
        handler_name = getattr(handler, "__qualname__", getattr(handler, "__name__", str(handler)))
        err_msg = (
            f"[ERROR] [Event] Handler '{handler_name}' (Plugin: {plugin_name}) "
            f"raised exception while handling '{event.event_name}': {exc!r}"
        )
        print(err_msg)
        try:
            from ..log import log
            log("Event", err_msg)
        except Exception:
            pass


def _to_snake(name: str) -> str:
    """Converts PascalCase to snake_case."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)

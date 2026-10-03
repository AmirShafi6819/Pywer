# ---------------------------------------------------------------- PocketMine-like event hooks
class Event:
    """Base class for everything passed to a handler."""
    def __init__(self):
        self.cancelled = False
    def cancel(self): self.cancelled = True
    @property
    def is_cancelled(self): return self.cancelled

class PlayerEvent(Event):
    def __init__(self, player, **kw):
        super().__init__()
        self.player = player
        self.__dict__.update(kw)

class PlayerJoinEvent(PlayerEvent):
    """Fired after a player entered the world. Set joined_message to None to stay quiet."""
    def __init__(self, player, message=None):
        super().__init__(player)
        self.message = message

class PlayerQuitEvent(PlayerEvent):
    def __init__(self, player, message=None):
        super().__init__(player)
        self.message = message

class PlayerChatEvent(PlayerEvent):
    def __init__(self, player, message):
        super().__init__(player)
        self.message = message
        self.format = "<%s> %s"

class BlockEvent(Event):
    def __init__(self, player, x, y, z, block_key, **kw):
        super().__init__()
        self.player = player; self.x = x; self.y = y; self.z = z; self.block_key = block_key
        self.__dict__.update(kw)

class BlockBreakEvent(BlockEvent):
    """Fired before a block is destroyed. Cancelling keeps the block."""

class BlockPlaceEvent(BlockEvent):
    """Fired before a block is placed. Cancelling refuses the placement."""

class PluginManager:
    """Tiny synchronous event bus, modelled on PocketMine's PluginManager.

    Handlers run in registration order; an exception in one handler is logged and does
    not stop the others, so a broken handler can never take the server down.
    """
    def __init__(self):
        self.handlers = {}
        self.event_log = []

    def register(self, event_class, handler, priority=1000):
        self.handlers.setdefault(event_class, []).append((priority, handler))
        self.handlers[event_class].sort(key=lambda p: -p[0])
        return handler

    def register_class(self, namespace, event_class, priority=1000):
        """Register every callable named like `on_<snake_case_event>` found on `namespace`."""
        prefix = "on_" + _snake(event_class.__name__)
        found = 0
        for name in dir(namespace):
            if name == prefix or (name.startswith(prefix + "_") and callable(getattr(namespace, name))):
                self.register(event_class, getattr(namespace, name), priority); found += 1
        return found

    def call(self, event):
        self.event_log.append(type(event).__name__)
        for _priority, handler in self.handlers.get(type(event), ()):
            try: handler(event)
            except Exception as e: _log_handler_error(type(event).__name__, handler, e)
        return event

def _snake(name):
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i: out.append("_")
        out.append(ch.lower())
    return "".join(out)

def _log_handler_error(event_name, handler, exc):
    from .log import log
    log("Event", "handler %s for %s raised %r" % (getattr(handler, "__name__", handler), event_name, exc))

manager = PluginManager()
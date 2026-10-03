# Milestone 4 Design Spec: Event System & Plugin Architecture

**Date:** 2026-10-03  
**Status:** Approved  
**Author:** Antigravity & Pywer Team  

---

## 1. Executive Summary

Milestone 4 introduces an extensible, production-grade Plugin and Event Architecture for the Pywer Minecraft Bedrock server (Protocol 766 / v1.21.50). 

Key design pillars:
1. **Strict Compiled `.pywer` Format:** Plugins are packaged as self-contained `.pywer` archives (ZIP containers containing `plugin.json` manifest, Python packages, and default assets).
2. **In-Memory Loading:** Plugins are loaded directly into memory using a custom `importlib.abc` virtual loader (`PywerZipLoader`) without extracting temporary folders to disk.
3. **Built-in Compiler Tooling:** A dedicated packaging tool (`tools/pywer_pack.py` / `python -m pywer pack`) validates manifests, checks Python syntax with `ast.parse` to report syntax errors at compile-time with line numbers, and bundles the `.pywer` archive.
4. **Full 6-Level Priority Event Pipeline:** Follows Bukkit/PocketMine standard priorities (`LOWEST`, `LOW`, `NORMAL`, `HIGH`, `HIGHEST`, `MONITOR`) with `Cancellable` support, `ignore_cancelled` semantics, and class-based (`@listen`) plus functional listener registration.
5. **Fault Isolation:** Uncaught listener exceptions are trapped and logged without crashing the server or interrupting subsequent listeners.
6. **Comprehensive Plugin API:** Unified `CommandManager` (player & console sender abstraction), `ServerScheduler` (tick-synchronized delayed, repeating, and main-thread-safe async worker tasks), persistent JSON `PluginConfig`, and high-level server/world helpers.
7. **Clean Lifecycle & Resource Unregistration:** Full `on_load`, `on_enable`, and `on_disable` lifecycle. Disabling or reloading a plugin cleanly detaches all its commands, event listeners, and scheduled tasks.

---

## 2. Directory Structure

```
pywer/
├── event/
│   ├── __init__.py           # Exports Event, Listener, listen, EventPriority, Cancellable
│   ├── base.py               # Core Event, Cancellable, EventPriority enum
│   ├── manager.py            # Priority dispatch, exception containment, registration
│   ├── player.py             # PlayerJoin, Quit, Chat, CommandPreprocess, Move, Interact, DropItem, Death
│   ├── block.py              # BlockBreak, BlockPlace, BlockInteract
│   ├── entity.py             # EntityDamage, EntityDamageByEntity, EntitySpawn, ProjectileHit
│   └── server.py             # ServerLoad, ServerStop, PluginEnable, PluginDisable
├── plugin/
│   ├── __init__.py           # Exports PluginBase, PluginManager
│   ├── base.py               # PluginBase, PluginConfig, PluginLogger
│   ├── manager.py            # Scans plugins/*.pywer, dependency resolution, lifecycle
│   ├── loader.py             # PywerZipFinder & PywerZipLoader (importlib.abc.MetaPathFinder/Loader)
│   └── compiler.py           # AST validation, manifest verification, .pywer packaging CLI
├── command/
│   ├── __init__.py           # Exports CommandManager, Command, CommandSender
│   ├── base.py               # Command, CommandSender, PlayerCommandSender, ConsoleCommandSender
│   ├── manager.py            # Command parsing, permissions, /help, /plugins, /reload
│   └── defaults.py           # Built-in commands (help, plugins, reload, stop, tp, gamemode, give, op, deop)
└── scheduler/
    ├── __init__.py           # Exports Task, ServerScheduler
    └── scheduler.py          # Delayed, repeating, and main-thread-safe async tasks
```

---

## 3. The `.pywer` Package Format & Compiler Tooling

### 3.1 Manifest Specification (`plugin.json`)
Every `.pywer` file must contain a `plugin.json` at its root:
```json
{
  "name": "Essentials",
  "version": "1.0.0",
  "main": "essentials.main:EssentialsPlugin",
  "api_version": "1.0.0",
  "description": "Core commands and player utilities",
  "author": "PywerTeam",
  "dependencies": [],
  "commands": {
    "spawn": {
      "description": "Teleport to spawn",
      "permission": "essentials.command.spawn",
      "usage": "/spawn"
    }
  },
  "permissions": {
    "essentials.command.spawn": {
      "default": "true",
      "description": "Allows teleporting to spawn"
    }
  }
}
```

### 3.2 Compiler CLI (`pywer/plugin/compiler.py` & `tools/pywer_pack.py`)
- Invocation:
  ```bash
  python tools/pywer_pack.py <plugin_directory> [output.pywer]
  ```
- **Verification steps:**
  1. Validates `plugin.json` presence and required fields (`name`, `version`, `main`, `api_version`).
  2. Inspects all `.py` files inside the source directory using `ast.parse` to detect syntax errors before packaging, displaying file path and line number if compilation fails.
  3. Verifies that the entrypoint class specified in `"main"` (e.g. `essentials.main:EssentialsPlugin`) can be found in the tree.
  4. Bundles code and resources (e.g. default `config.json`) into a compressed `.pywer` ZIP archive.

---

## 4. The Event System & Priority Dispatch

### 4.1 Event Priority Hierarchy
The 6 priority levels execute in ascending numerical order:
1. `LOWEST` (0): Pre-processing and early observation.
2. `LOW` (1): Early customization.
3. `NORMAL` (2): Default priority for standard handlers.
4. `HIGH` (3): High-priority modifications.
5. `HIGHEST` (4): Final authority on outcomes and cancellations.
6. `MONITOR` (5): Read-only observation (analytics, audit logs). Always receives outcome; cannot modify event state.

### 4.2 Cancellation Semantics
- Events inheriting from `Cancellable` implement `cancel()`, `uncancel()`, and property `is_cancelled: bool`.
- `@listen(priority=EventPriority.NORMAL, ignore_cancelled=True)`:
  - If `ignore_cancelled=True` (default), the handler is skipped if the event is already cancelled.
  - If `ignore_cancelled=False`, the handler receives cancelled events.
  - `MONITOR` priority handlers always run regardless of cancellation state.

### 4.3 Registration Patterns
1. **Class-Based Listeners:**
   ```python
   from pywer.event import Listener, listen, EventPriority
   from pywer.event.player import PlayerChatEvent

   class ChatFilter(Listener):
       @listen(priority=EventPriority.HIGH, ignore_cancelled=True)
       def on_chat(self, event: PlayerChatEvent):
           if "spam" in event.message:
               event.cancel()
   ```
2. **Functional Subscriptions:**
   ```python
   self.server.events.subscribe(PlayerJoinEvent, on_join, priority=EventPriority.NORMAL)
   ```

### 4.4 Fault Isolation
- When an event handler raises an unhandled exception:
  - `EventManager.call()` catches the error.
  - Formats traceback with plugin identity and handler name: `[ERROR] [Event] Handler on_chat in Essentials raised ZeroDivisionError`.
  - Propagation continues uninterrupted to subsequent handlers.
  - The server never crashes due to a buggy plugin listener.

---

## 5. Plugin Base Class & Lifecycle Management

### 5.1 `PluginBase` Interface
```python
class PluginBase:
    def __init__(self, server: Server, manifest: dict, data_folder: str):
        self.server = server
        self.manifest = manifest
        self.data_folder = data_folder
        self.config = PluginConfig(data_folder)
        self.logger = PluginLogger(manifest["name"])
        self.enabled = False

    def on_load(self):
        """Called when plugin is loaded into memory."""
        pass

    def on_enable(self):
        """Called when plugin is activated."""
        pass

    def on_disable(self):
        """Called when plugin is deactivated."""
        pass

    def register_events(self, listener: Listener):
        """Registers a Listener class and binds it to this plugin."""
        self.server.events.register_listener(listener, plugin=self)

    def register_command(self, name: str, handler: Callable, **meta):
        """Registers a command bound to this plugin."""
        self.server.commands.register(name, handler, plugin=self, **meta)

    def save_default_config(self):
        """Copies default config.json from .pywer archive if missing from disk."""
        ...
```

### 5.2 In-Memory Virtual Loader (`PywerZipLoader`)
- Uses Python standard library `importlib.abc.MetaPathFinder` and `Loader`.
- Appends `PywerZipFinder` to `sys.meta_path`.
- When importing `pywer_plugins.<plugin_name>.*`, byte streams are read directly from the `.pywer` zip archive without unpacking files to disk.
- Resolves submodule imports and package hierarchy cleanly.

### 5.3 Lifecycle & Resource Cleanup
- `PluginManager.load_plugins()`: Scans `plugins/*.pywer`, reads manifests, sorts dependencies, loads modules into memory, and executes `on_load()`.
- `PluginManager.enable_plugins()`: Iterates loaded plugins and executes `on_enable()`.
- `PluginManager.disable_plugin(plugin)`:
  - Invokes `plugin.on_disable()`.
  - Automatically unregisters all event listeners registered by `plugin`.
  - Unregisters all commands registered by `plugin`.
  - Cancels all pending or repeating scheduler tasks owned by `plugin`.

---

## 6. Plugin API Surface: Commands, Scheduler, and World Access

### 6.1 Unified Command System
- **`CommandSender` Hierarchy:**
  - `CommandSender`: `name: str`, `send_message(text)`, `has_permission(node: str) -> bool`, `is_player: bool`, `is_op: bool`.
  - `PlayerCommandSender`: Wraps `Session`. Adds `player`, `teleport(pos)`, `give_item(key, count)`.
  - `ConsoleCommandSender`: Server terminal sender (always has full permissions).
- **Execution Pipeline:**
  - Player chat starting with `/` triggers `PlayerCommandPreprocessEvent` (cancellable).
  - Parses tokens: `/spawn player1 100` -> command `"spawn"`, args `["player1", "100"]`.
  - Verifies permission node from manifest or registration.
  - Executes handler: `handler(sender: CommandSender, args: list[str])`.
  - Built-in commands provided: `/help`, `/plugins` (`/pl`), `/reload`, `/stop`, `/tp`, `/gamemode`, `/give`, `/op`, `/deop`.

### 6.2 The Server Scheduler (`ServerScheduler`)
- Synchronized to Pywer's main tick loop (`0.05s` / 20 TPS):
  - `run_later(delay_ticks, callback, *args, **kwargs) -> Task`: Executes after $N$ ticks.
  - `run_repeating(delay_ticks, period_ticks, callback, *args, **kwargs) -> Task`: Executes every $P$ ticks.
  - `run_async(worker_fn, on_done_callback=None) -> Task`: Dispatches `worker_fn` to `WorkerPool`, then posts `on_done_callback` back to the main thread during the next tick.
  - `task.cancel()`: Safely stops repeating or pending execution.

### 6.3 Server & World API
- Online player lookup: `server.get_player(name_or_uuid)`.
- Player list: `server.online_players`.
- Broadcasts: `server.broadcast_message(text)`, `server.broadcast_popup(text)`.
- Block queries/mutations: `server.get_block(x, y, z)`, `server.set_block(x, y, z, key)`.
- Entity manager access: `server.spawn_entity(cls, pos, ...)`, `server.get_entities_near(pos, radius)`.

---

## 7. Verification & Testing Strategy

1. **`tests/test_event_system.py`**:
   - 6-priority dispatch sequence (`LOWEST` to `MONITOR`).
   - `Cancellable` logic and `ignore_cancelled` compliance.
   - Exception containment (raising listener does not halt subsequent listeners or crash).
   - `@listen` decorator discovery on `Listener` subclasses.
2. **`tests/test_plugin_compiler.py`**:
   - Compiling source folder into `.pywer` archive.
   - Validation failures on missing manifest or Python syntax errors with line numbers.
3. **`tests/test_plugin_lifecycle.py`**:
   - In-memory archive loading and `on_load`/`on_enable`/`on_disable` calls.
   - Config extraction to `plugins_data/<PluginName>/config.json`.
   - Complete unregistration of listeners, commands, and tasks on disable.
4. **`tests/test_command_system.py`**:
   - Command registration, execution, and argument parsing.
   - Permission node checking.
   - `PlayerCommandPreprocessEvent` cancellation.
   - Built-in commands (`/help`, `/plugins`, `/reload`).
5. **`tests/test_scheduler.py`**:
   - Delayed task execution (`run_later`).
   - Repeating task execution (`run_repeating`).
   - Async task completion posting safely to main thread (`run_async`).
   - Task cancellation.
6. **End-to-End Smoke Test (`tools/smoke_test_plugins.py`)**:
   - Automated compile, load, event intercept, command dispatch, scheduler verify, and teardown cycle.

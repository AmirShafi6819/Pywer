# Milestone 4: Event System & Plugin Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade, extensible Event System and Plugin Architecture for Pywer, featuring strict compiled `.pywer` packages, in-memory virtual zip loading, a 6-priority event bus (`LOWEST` to `MONITOR`), unified command management, tick scheduler, and automated compiler tooling.

**Architecture:** Plugins are authored as modular folders and compiled into single-file `.pywer` packages via `tools/pywer_pack.py`. The server mounts `.pywer` packages directly into memory via `importlib.abc` (`PywerZipLoader`) without temporary disk extraction. Events follow Bukkit/PocketMine 6-level priority dispatch with `Cancellable` support, error containment, and dual listener registration (class `@listen` + functional). `PluginBase` provides unified access to commands, persistent JSON configs, schedulers, and world APIs, with automatic resource unregistration on reload.

**Tech Stack:** Pure Python standard library (`zipfile`, `importlib.abc`, `ast`, `json`, `pathlib`, `typing`), Protocol 766 / Bedrock v1.21.50.

**Spec:** [`docs/superpowers/specs/2026-10-03-event-and-plugin-architecture-design.md`](file:///c:/Users/Mani/Desktop/Pywer/docs/superpowers/specs/2026-10-03-event-and-plugin-architecture-design.md)

## Global Constraints
- Pure Python 3.10+ standard library only (no pip dependencies).
- Strict compiled `.pywer` format only (plugins in `plugins/` must be `.pywer` files).
- Zero disk pollution: `.pywer` files are loaded in-memory via `sys.meta_path` finder/loader.
- Event priority sequence: `LOWEST = 0`, `LOW = 1`, `NORMAL = 2`, `HIGH = 3`, `HIGHEST = 4`, `MONITOR = 5`.
- Fault isolation: Uncaught listener exceptions are trapped and logged without crashing the server.
- Full TDD: Each task implements tests first (Red), implements code (Green), and commits.

---

### Task 1: Full 6-Priority Event System & Cancellable Hierarchy (`pywer.event.*`)

**Files:**
- Create: `pywer/event/__init__.py`
- Create: `pywer/event/base.py`
- Create: `pywer/event/manager.py`
- Create: `pywer/event/player.py`
- Create: `pywer/event/block.py`
- Create: `pywer/event/entity.py`
- Create: `pywer/event/server.py`
- Modify: `pywer/event.py` (backward-compatibility alias pointing to `pywer.event`)
- Test: `tests/test_event_system.py`

**Interfaces:**
- Produces:
  - `Event`: Base event class with `event_name`
  - `Cancellable`: Mixin with `cancel()`, `uncancel()`, `is_cancelled: bool`
  - `EventPriority`: Enum with `LOWEST = 0`, `LOW = 1`, `NORMAL = 2`, `HIGH = 3`, `HIGHEST = 4`, `MONITOR = 5`
  - `Listener`: Base marker class for listener implementations
  - `@listen(priority=EventPriority.NORMAL, ignore_cancelled=True)`: Decorator for handler methods
  - `EventManager`:
    - `register_listener(listener, plugin=None)`: Registers all `@listen` methods on listener
    - `subscribe(event_cls, handler, priority=EventPriority.NORMAL, ignore_cancelled=True, plugin=None)`: Functional registration
    - `call(event) -> event`: Priority-ordered dispatch with error containment
    - `unregister_by_plugin(plugin)`: Detaches all handlers owned by a plugin

- [ ] **Step 1: Write failing unit tests for event priorities, cancellation, and error isolation**

```python
# tests/test_event_system.py
import unittest
from pywer.event import Event, Cancellable, EventPriority, Listener, listen, EventManager
from pywer.event.player import PlayerChatEvent, PlayerJoinEvent

class TestEventSystem(unittest.TestCase):
    def test_priority_ordering(self):
        bus = EventManager()
        order = []

        class OrderedListener(Listener):
            @listen(priority=EventPriority.MONITOR)
            def on_monitor(self, event):
                order.append("MONITOR")

            @listen(priority=EventPriority.LOWEST)
            def on_lowest(self, event):
                order.append("LOWEST")

            @listen(priority=EventPriority.NORMAL)
            def on_normal(self, event):
                order.append("NORMAL")

            @listen(priority=EventPriority.HIGHEST)
            def on_highest(self, event):
                order.append("HIGHEST")

        bus.register_listener(OrderedListener())
        event = PlayerJoinEvent(None, "Welcome")
        bus.call(event)
        self.assertEqual(order, ["LOWEST", "NORMAL", "HIGHEST", "MONITOR"])

    def test_cancellation_and_ignore_cancelled(self):
        bus = EventManager()
        saw_chat = []

        class CancelListener(Listener):
            @listen(priority=EventPriority.LOW)
            def on_low(self, event):
                event.cancel()

            @listen(priority=EventPriority.NORMAL, ignore_cancelled=True)
            def on_normal(self, event):
                saw_chat.append("NORMAL")

            @listen(priority=EventPriority.HIGH, ignore_cancelled=False)
            def on_high(self, event):
                saw_chat.append("HIGH")

            @listen(priority=EventPriority.MONITOR)
            def on_monitor(self, event):
                saw_chat.append("MONITOR")

        bus.register_listener(CancelListener())
        event = PlayerChatEvent(None, "bad word")
        bus.call(event)
        self.assertTrue(event.is_cancelled)
        self.assertEqual(saw_chat, ["HIGH", "MONITOR"])

    def test_fault_isolation(self):
        bus = EventManager()
        order = []

        class BuggyListener(Listener):
            @listen(priority=EventPriority.LOW)
            def on_low(self, event):
                order.append("LOW")
                raise RuntimeError("Explosion in plugin listener!")

            @listen(priority=EventPriority.NORMAL)
            def on_normal(self, event):
                order.append("NORMAL")

        bus.register_listener(BuggyListener())
        event = PlayerJoinEvent(None, "Test")
        # Calling event must NOT raise RuntimeError
        bus.call(event)
        self.assertEqual(order, ["LOW", "NORMAL"])
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m unittest tests/test_event_system.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement `pywer/event/base.py`, `pywer/event/manager.py`, and event definitions**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_event_system.py -v`
Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add pywer/event/ pywer/event.py tests/test_event_system.py
git commit -m "feat: implement 6-priority event bus with cancellation and fault isolation"
```

---

### Task 2: `.pywer` Compiler & Packaging Tooling (`pywer.plugin.compiler`, `tools/pywer_pack.py`)

**Files:**
- Create: `pywer/plugin/compiler.py`
- Create: `tools/pywer_pack.py`
- Test: `tests/test_plugin_compiler.py`

**Interfaces:**
- Produces:
  - `compile_plugin(source_dir: str, output_path: str = None) -> str`: Compiles folder to `.pywer`
  - `validate_manifest(manifest: dict) -> None`: Validates required fields (`name`, `version`, `main`, `api_version`)
  - `validate_python_syntax(source_dir: str) -> None`: Uses `ast.parse` to report syntax errors with line numbers
  - CLI executable `tools/pywer_pack.py <source_dir> [output.pywer]`

- [ ] **Step 1: Write failing unit test for `.pywer` compiler and syntax validator**

```python
# tests/test_plugin_compiler.py
import unittest
import tempfile
import os
import json
import zipfile
from pywer.plugin.compiler import compile_plugin, PluginCompilationError

class TestPluginCompiler(unittest.TestCase):
    def test_compile_valid_plugin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                "name": "TestPlugin",
                "version": "1.0.0",
                "main": "test_plugin.main:TestPlugin",
                "api_version": "1.0.0"
            }
            with open(os.path.join(tmpdir, "plugin.json"), "w") as f:
                json.dump(manifest, f)
            src_dir = os.path.join(tmpdir, "src", "test_plugin")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "__init__.py"), "w") as f:
                f.write("")
            with open(os.path.join(src_dir, "main.py"), "w") as f:
                f.write("class TestPlugin:\n    pass\n")

            out_pywer = os.path.join(tmpdir, "TestPlugin.pywer")
            res_path = compile_plugin(tmpdir, out_pywer)
            self.assertTrue(os.path.exists(res_path))

            # Verify zip archive content
            with zipfile.ZipFile(res_path, "r") as z:
                names = z.namelist()
                self.assertIn("plugin.json", names)
                self.assertIn("test_plugin/main.py", names)

    def test_compiler_rejects_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(PluginCompilationError):
                compile_plugin(tmpdir)

    def test_compiler_catches_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {"name": "Broken", "version": "1.0", "main": "broken.main:B", "api_version": "1.0"}
            with open(os.path.join(tmpdir, "plugin.json"), "w") as f:
                json.dump(manifest, f)
            src_dir = os.path.join(tmpdir, "src", "broken")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "main.py"), "w") as f:
                f.write("def broken_func(:\n    pass\n")  # Syntax error

            with self.assertRaises(PluginCompilationError) as cm:
                compile_plugin(tmpdir)
            self.assertIn("Syntax error", str(cm.exception))
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m unittest tests/test_plugin_compiler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.plugin.compiler'`.

- [ ] **Step 3: Implement `pywer/plugin/compiler.py` and `tools/pywer_pack.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_plugin_compiler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```bash
git add pywer/plugin/compiler.py tools/pywer_pack.py tests/test_plugin_compiler.py
git commit -m "feat: implement .pywer plugin compiler and AST syntax verification"
```

---

### Task 3: In-Memory Virtual Plugin Loader & `PluginBase` (`pywer.plugin.loader`, `pywer.plugin.base`)

**Files:**
- Create: `pywer/plugin/__init__.py`
- Create: `pywer/plugin/loader.py`
- Create: `pywer/plugin/base.py`
- Test: `tests/test_plugin_loader.py`

**Interfaces:**
- Produces:
  - `PywerZipFinder` (inherits `importlib.abc.MetaPathFinder`): Locates modules in `.pywer` files under namespace `pywer_plugins.<plugin_name>.*`
  - `PywerZipLoader` (inherits `importlib.abc.Loader`): Loads module code directly from zip without disk extraction
  - `PluginBase`:
    - `on_load()`, `on_enable()`, `on_disable()`
    - `save_default_config()`, `reload_config()`, `save_config()`
    - `register_events(listener)`
    - `register_command(name, handler, ...)`
  - `PluginConfig`: JSON dictionary wrapper with `.get()`, `.set()`, `.save()`
  - `PluginLogger`: Prefixes logs with `[<PluginName>]`

- [ ] **Step 1: Write failing unit test for in-memory zip loading and PluginBase**

```python
# tests/test_plugin_loader.py
import unittest
import tempfile
import os
import json
from unittest.mock import MagicMock
from pywer.plugin.compiler import compile_plugin
from pywer.plugin.loader import load_pywer_archive
from pywer.plugin.base import PluginBase

class TestPluginLoader(unittest.TestCase):
    def test_in_memory_load_and_instantiation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                "name": "Greeter",
                "version": "1.0.0",
                "main": "greeter.main:GreeterPlugin",
                "api_version": "1.0.0"
            }
            with open(os.path.join(tmpdir, "plugin.json"), "w") as f:
                json.dump(manifest, f)
            with open(os.path.join(tmpdir, "config.json"), "w") as f:
                json.dump({"greeting": "Hello, world!"}, f)

            src_dir = os.path.join(tmpdir, "src", "greeter")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "__init__.py"), "w") as f:
                f.write("")
            with open(os.path.join(src_dir, "main.py"), "w") as f:
                f.write("""from pywer.plugin import PluginBase

class GreeterPlugin(PluginBase):
    def on_enable(self):
        self.save_default_config()
        self.greet_count = 1
""")

            pkg_path = os.path.join(tmpdir, "Greeter.pywer")
            compile_plugin(tmpdir, pkg_path)

            # In-memory load
            srv = MagicMock()
            plugin_instance = load_pywer_archive(pkg_path, srv, data_folder=os.path.join(tmpdir, "data"))
            self.assertIsInstance(plugin_instance, PluginBase)
            self.assertEqual(plugin_instance.manifest["name"], "Greeter")

            # Test lifecycle & config
            plugin_instance.on_enable()
            self.assertEqual(plugin_instance.greet_count, 1)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "data", "config.json")))
            self.assertEqual(plugin_instance.config.get("greeting"), "Hello, world!")
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m unittest tests/test_plugin_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.plugin.loader'`.

- [ ] **Step 3: Implement `pywer/plugin/loader.py` and `pywer/plugin/base.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_plugin_loader.py -v`
Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add pywer/plugin/__init__.py pywer/plugin/loader.py pywer/plugin/base.py tests/test_plugin_loader.py
git commit -m "feat: implement in-memory .pywer virtual package loader and PluginBase"
```

---

### Task 4: Server Scheduler & Task Management (`pywer.scheduler.*`, `pywer.server.server`)

**Files:**
- Create: `pywer/scheduler/__init__.py`
- Create: `pywer/scheduler/scheduler.py`
- Modify: `pywer/server/server.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Produces:
  - `Task`: Holds `task_id`, `owner_plugin`, `is_cancelled`, `cancel()`
  - `ServerScheduler`:
    - `run_later(delay_ticks, callback, *args, **kwargs, plugin=None) -> Task`
    - `run_repeating(delay_ticks, period_ticks, callback, *args, **kwargs, plugin=None) -> Task`
    - `run_async(worker_fn, on_done_callback=None, plugin=None) -> Task`
    - `cancel_by_plugin(plugin)`
    - `tick()`: Advances tick counter and executes expired tasks
- Integrates:
  - `Server.scheduler`: Initialized in `Server.__init__`
  - In `Server.tick`: executes `self.scheduler.tick()`

- [ ] **Step 1: Write failing unit test for ServerScheduler**

```python
# tests/test_scheduler.py
import unittest
from unittest.mock import MagicMock
from pywer.scheduler import ServerScheduler

class TestScheduler(unittest.TestCase):
    def test_run_later(self):
        sched = ServerScheduler()
        calls = []
        task = sched.run_later(3, lambda: calls.append("fired"))

        sched.tick() # tick 1
        self.assertEqual(calls, [])
        sched.tick() # tick 2
        self.assertEqual(calls, [])
        sched.tick() # tick 3
        self.assertEqual(calls, ["fired"])

    def test_run_repeating_and_cancel(self):
        sched = ServerScheduler()
        calls = []
        task = sched.run_repeating(1, 2, lambda: calls.append("tick"))

        sched.tick() # tick 1: fires
        self.assertEqual(len(calls), 1)
        sched.tick() # tick 2: wait
        self.assertEqual(len(calls), 1)
        sched.tick() # tick 3: fires
        self.assertEqual(len(calls), 2)

        task.cancel()
        sched.tick() # tick 4
        sched.tick() # tick 5
        self.assertEqual(len(calls), 2)
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m unittest tests/test_scheduler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.scheduler'`.

- [ ] **Step 3: Implement `pywer/scheduler/scheduler.py` and modify `pywer/server/server.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_scheduler.py -v`
Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```bash
git add pywer/scheduler/ pywer/server/server.py tests/test_scheduler.py
git commit -m "feat: implement tick-synchronized and async server scheduler"
```

---

### Task 5: Unified Command System & Senders (`pywer.command.*`, `pywer.player.session`)

**Files:**
- Create: `pywer/command/__init__.py`
- Create: `pywer/command/base.py`
- Create: `pywer/command/manager.py`
- Create: `pywer/command/defaults.py`
- Modify: `pywer/player/session.py`
- Modify: `pywer/server/server.py`
- Test: `tests/test_command_system.py`

**Interfaces:**
- Produces:
  - `CommandSender`: Abstract sender (`send_message`, `has_permission`, `is_player`, `is_op`)
  - `PlayerCommandSender`: Wraps `Session` (`player.teleport`, `player.give_item`)
  - `ConsoleCommandSender`: Terminal console sender
  - `Command`: Stores `name`, `handler`, `description`, `permission`, `aliases`, `plugin`
  - `CommandManager`:
    - `register(name, handler, ...)`
    - `unregister_by_plugin(plugin)`
    - `execute(sender, command_line: str) -> bool`
  - Default commands: `/help`, `/plugins` (`/pl`), `/reload`, `/stop`, `/tp`, `/gamemode`

- [ ] **Step 1: Write failing unit test for CommandManager and permission dispatch**

```python
# tests/test_command_system.py
import unittest
from unittest.mock import MagicMock
from pywer.command import CommandManager, CommandSender, PlayerCommandSender

class TestCommandSystem(unittest.TestCase):
    def test_command_registration_and_execution(self):
        mgr = CommandManager()
        executed = []

        def handle_hello(sender, args):
            sender.send_message("Hello, " + (args[0] if args else "world"))
            executed.append(True)
            return True

        mgr.register("hello", handle_hello, description="Says hello")
        sender = MagicMock(spec=CommandSender)
        res = mgr.execute(sender, "/hello Steve")
        self.assertTrue(res)
        self.assertTrue(executed)
        sender.send_message.assert_called_with("Hello, Steve")

    def test_permission_denial(self):
        mgr = CommandManager()
        mgr.register("admincmd", lambda s, a: True, permission="pywer.admin")

        sender = MagicMock(spec=CommandSender)
        sender.has_permission.return_value = False
        res = mgr.execute(sender, "/admincmd")
        self.assertTrue(res)
        sender.send_message.assert_called()
        self.assertIn("permission", sender.send_message.call_args[0][0].lower())
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m unittest tests/test_command_system.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.command'`.

- [ ] **Step 3: Implement `pywer/command/base.py`, `pywer/command/manager.py`, `pywer/command/defaults.py` and hook into `pywer/player/session.py` and `pywer/server/server.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_command_system.py -v`
Expected: PASS.

- [ ] **Step 5: Commit Task 5**

```bash
git add pywer/command/ pywer/player/session.py pywer/server/server.py tests/test_command_system.py
git commit -m "feat: implement unified command manager and permission checking"
```

---

### Task 6: PluginManager, Server Integration & Lifecycle Cleanups (`pywer.plugin.manager`, `pywer.server.server`)

**Files:**
- Create: `pywer/plugin/manager.py`
- Modify: `pywer/server/server.py`
- Test: `tests/test_plugin_lifecycle.py`

**Interfaces:**
- Produces:
  - `PluginManager(server)`:
    - `load_plugins(plugins_dir="plugins")`: Discovers all `.pywer` files, sorts by dependencies, loads into memory, calls `on_load()`
    - `enable_plugins()`: Calls `on_enable()` on all loaded plugins
    - `disable_plugin(plugin)`: Calls `on_disable()`, unregisters events, unregisters commands, cancels tasks
    - `reload_plugins()`: Cleans up and reloads `.pywer` packages from disk

- [ ] **Step 1: Write failing unit test for PluginManager full lifecycle and clean unregistration**

```python
# tests/test_plugin_lifecycle.py
import unittest
import tempfile
import os
import json
from unittest.mock import MagicMock
from pywer.plugin.compiler import compile_plugin
from pywer.plugin.manager import PluginManager
from pywer.server.server import Server

class TestPluginLifecycle(unittest.TestCase):
    def test_plugin_manager_lifecycle_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = os.path.join(tmpdir, "plugins")
            os.makedirs(plugins_dir)

            # Create test plugin
            manifest = {
                "name": "Sample",
                "version": "1.0.0",
                "main": "sample.main:SamplePlugin",
                "api_version": "1.0.0"
            }
            p_src = os.path.join(tmpdir, "sample_src")
            os.makedirs(os.path.join(p_src, "src", "sample"))
            with open(os.path.join(p_src, "plugin.json"), "w") as f:
                json.dump(manifest, f)
            with open(os.path.join(p_src, "src", "sample", "__init__.py"), "w") as f:
                f.write("")
            with open(os.path.join(p_src, "src", "sample", "main.py"), "w") as f:
                f.write("""from pywer.plugin import PluginBase
from pywer.event import Listener, listen
from pywer.event.player import PlayerChatEvent

class MyListener(Listener):
    @listen()
    def on_chat(self, event):
        event.cancel()

class SamplePlugin(PluginBase):
    def on_enable(self):
        self.register_events(MyListener())
        self.register_command("testcmd", lambda s, a: True)
""")
            # Compile to plugins/Sample.pywer
            compile_plugin(p_src, os.path.join(plugins_dir, "Sample.pywer"))

            # Server setup
            srv = Server.__new__(Server)
            srv.events = MagicMock()
            srv.commands = MagicMock()
            srv.scheduler = MagicMock()
            srv.playing = MagicMock(return_value=[])

            pm = PluginManager(srv, plugins_dir=plugins_dir, data_dir=os.path.join(tmpdir, "data"))
            pm.load_plugins()
            self.assertEqual(len(pm.plugins), 1)
            sample_plugin = pm.plugins["Sample"]

            pm.enable_plugins()
            self.assertTrue(sample_plugin.enabled)

            # Disable
            pm.disable_plugin(sample_plugin)
            self.assertFalse(sample_plugin.enabled)
            srv.events.unregister_by_plugin.assert_called_with(sample_plugin)
            srv.commands.unregister_by_plugin.assert_called_with(sample_plugin)
            srv.scheduler.cancel_by_plugin.assert_called_with(sample_plugin)
```

- [ ] **Step 2: Run test to verify failure**

Run: `python -m unittest tests/test_plugin_lifecycle.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pywer.plugin.manager'`.

- [ ] **Step 3: Implement `pywer/plugin/manager.py` and modify `pywer/server/server.py`**

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_plugin_lifecycle.py -v`
Expected: PASS.

- [ ] **Step 5: Commit Task 6**

```bash
git add pywer/plugin/manager.py pywer/server/server.py tests/test_plugin_lifecycle.py
git commit -m "feat: implement PluginManager lifecycle and automatic resource unregistration"
```

---

### Task 7: End-to-End Verification & Plugin Smoke Test (`tools/smoke_test_plugins.py`)

**Files:**
- Create: `tools/smoke_test_plugins.py`
- Create: `examples/test_plugin/` (source project for verification)
- Run: Full test suite

- [ ] **Step 1: Write and run end-to-end smoke test**

Automated verification covering:
1. Compiling `examples/test_plugin/` into `plugins/TestPlugin.pywer` using `tools/pywer_pack.py`.
2. Initializing `Server` with event bus, command manager, and scheduler.
3. Loading and enabling `TestPlugin.pywer` in memory without extracting files.
4. Verifying default `config.json` is generated into `plugins_data/TestPlugin/config.json`.
5. Firing `PlayerChatEvent` and verifying listener cancellation / message modification.
6. Executing custom plugin command (`/spawn` and `/stats`).
7. Simulating scheduler ticks (verifying delayed and repeating tasks).
8. Executing `/reload` and verifying clean plugin shutdown, unregistration, and reload.

- [ ] **Step 2: Run complete project test suite**

Run: `python -m unittest discover -s tests -v`
Expected: ALL unit tests PASS.

- [ ] **Step 3: Commit Task 7**

```bash
git add tools/smoke_test_plugins.py examples/
git commit -m "test: add end-to-end plugin compiler, lifecycle, and event smoke test"
```

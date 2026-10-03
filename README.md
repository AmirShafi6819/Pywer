<p align="center">
  <img src="docs/file_00000000e384820a930746c2663502fb.png" width="220" alt="Pywer Logo">
</p>

<h1 align="center">Pywer</h1>

<p align="center">
  A lightweight, high-performance Minecraft Bedrock server software written entirely in pure Python with zero external dependencies.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Bedrock-1.21.50-3CB371?style=for-the-badge">
  <img src="https://img.shields.io/badge/Protocol-766-blue?style=for-the-badge">
  <img src="https://img.shields.io/badge/Status-Milestone%204%20Complete-brightgreen?style=for-the-badge">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge">
</p>

---

## ⚡ Overview

**Pywer** is a pure-Python Minecraft Bedrock server (Protocol 766 / v1.21.50) designed from the ground up for simplicity, speed, and clean modularity. 

Built exclusively on the Python standard library, Pywer delivers asynchronous UDP networking, server-authoritative inventory, physics-driven entity simulation, a 6-priority event bus, and an in-memory compiled plugin architecture that runs seamlessly on desktops, VPS servers, and mobile devices (Android Termux / Pydroid).

---

## ✨ Key Features

- **Pure Python & Zero External Dependencies:** Runs anywhere Python 3.10+ is installed using standard library modules only (`socket`, `select`, `importlib`, `hashlib`, `concurrent.futures`, `struct`).
- **Compiled `.pywer` Plugin Architecture:**
  - Strict distributable `.pywer` zip format with built-in AST pre-compilation validation.
  - **Zero Disk Extraction:** Loads directly into isolated virtual namespaces (`_pywer_plugins.<Plugin>.*`) using `importlib.abc` meta-path finders.
  - Topological dependency resolution (DFS) and full auto-cleanup of listeners, commands, and tasks on disable/reload.
  - Live plugin reloading without server restarts.
- **PocketMine/Bukkit-Grade Event System:**
  - 6 execution priorities (`LOWEST`, `LOW`, `NORMAL`, `HIGH`, `HIGHEST`, `MONITOR`).
  - `Cancellable` event mechanics with `ignore_cancelled` control.
  - Class-based listeners (`@listen`) and functional callbacks.
  - Fault-isolated dispatching (broken plugin handlers cannot crash server ticks).
- **Tick-Aligned Server Scheduler:**
  - 20 TPS tick-synchronized one-shot (`run_later`) and repeating (`run_repeating`) tasks.
  - Multithreaded background workers (`run_async`) with thread-safe main-thread callback queues.
- **Unified Command Framework:**
  - Dual senders: `PlayerCommandSender` (in-game player session) and `ConsoleCommandSender` (server terminal).
  - Prefix support for both `/` and `!` syntax with case-insensitive primary and alias resolution.
  - `PlayerCommandPreprocessEvent` for pre-command inspection and cancellation.
- **Server-Authoritative Inventory & Containers:**
  - 36-slot player inventory, hotbar, and client prediction synchronization.
  - Container interactions: Small Chests, Double Chests, 2x2 player crafting, and 3x3 Workbenches.
  - Full crafting engine supporting shaped and shapeless recipes.
- **Entity Engine & 3D Physics:**
  - Spatial bucketing grid ($32 \times 32 \times 32$ block voxels) and simulation distance culling.
  - Continuous raycasting and AABB intersection collision detection.
  - Ballistic projectiles: Arrows (damage, stick into blocks) and Snowballs (knockback, shatter).
  - Dropped item entities with gravity, drag, ground bounce, despawning, and automatic item stack merging.
  - Hostile mob AI (Zombies targeting survival players) and passive mobs (Cows).
- **Cross-Platform & Mobile Ready:** Windows, Linux, macOS, and Android (Termux / Pydroid 3).

---

## 🚀 Quick Start

### Running the Server

Clone the repository and launch directly:

```bash
git clone https://github.com/EXBYPIXEL/Pywer.git
cd Pywer
python run.py
```

Or run via module execution:

```bash
python -m pywer
```

The server binds to `0.0.0.0:19132` (UDP) by default and is immediately ready to accept Bedrock v1.21.50 clients.

---

## 🐕 Running behind WaterdogPE

```
python -m pywer 19133 --proxy --bind 127.0.0.1 --no-encryption
```

WaterdogPE `config.yml` (key names may vary slightly between versions):

```yaml
servers:
  pywer:
    address: 127.0.0.1:19133
online_mode: false
use_login_extras: false
```

Pywer is always offline (it never verifies the login chain), so no `xbox-auth` switch is needed.
Players must use protocol 766 (1.21.50). Env vars: `PYWER_PROXY=1`, `PYWER_BIND`, `PYWER_ENCRYPTION=0`.

---

## 🧩 Plugin Development Guide

Pywer features an API designed for ease of use, strict typing, and high performance.

### 1. Plugin Structure

Author your plugin in a regular folder:

```
MyPlugin/
├── plugin.json       # Manifest metadata
├── config.json       # (Optional) Bundled default configuration
├── main.py           # Main entry point (inherits PluginBase)
└── utils/            # Submodules and helper files
    └── __init__.py
```

### 2. Manifest (`plugin.json`)

```json
{
  "name": "MyPlugin",
  "version": "1.0.0",
  "main": "main:MyPlugin",
  "api_version": "1.0.0",
  "author": "YourName",
  "description": "An example Pywer plugin",
  "dependencies": []
}
```

### 3. Plugin Implementation (`main.py`)

```python
from pywer.plugin.base import PluginBase
from pywer.event import Listener, listen, EventPriority
from pywer.event.player import PlayerJoinEvent, PlayerChatEvent
from pywer.command import Command, CommandSender


class PingCommand(Command):
    def __init__(self):
        super().__init__(
            name="ping",
            description="Responds with pong",
            usage="/ping",
            aliases=["p"]
        )

    def execute(self, sender: CommandSender, args: list) -> bool:
        sender.send_message("§aPong!")
        return True


class MyPlugin(PluginBase, Listener):
    def on_load(self) -> None:
        self.logger.info("Plugin loaded into virtual memory!")

    def on_enable(self) -> None:
        self.logger.info("Enabling MyPlugin...")
        
        # Register events & commands
        self.register_listener(self)
        self.register_command(PingCommand())

        # Schedule repeating task every 20 ticks (1 second)
        self.run_repeating(1, 20, self.heartbeat)

    def on_disable(self) -> None:
        self.logger.info("Plugin disabled cleanly.")

    def heartbeat(self) -> None:
        pass

    @listen(priority=EventPriority.NORMAL)
    def on_join(self, event: PlayerJoinEvent) -> None:
        if event.player:
            event.player.chat_to(f"§eWelcome to the server, {event.player.name}!")

    @listen(priority=EventPriority.HIGH)
    def on_chat(self, event: PlayerChatEvent) -> None:
        if "badword" in event.message.lower():
            event.cancel()
            event.player.chat_to("§cProfanity is not permitted.")
```

### 4. Compiling into `.pywer`

Compile your plugin using the built-in packaging tool:

```bash
python tools/pywer_pack.py MyPlugin -o plugins/MyPlugin.pywer
```

The packager validates Python syntax across all `.py` files using AST parsing before creating the archive. Drop the generated `.pywer` package into `plugins/` and start or reload the server!

---

## 🛠️ Built-in Commands

Pywer supports unified command dispatching through both `/` and `!` syntax:

| Command | Aliases | Description |
|---------|---------|-------------|
| `/help [page]` | `/?` | Lists all available registered server and plugin commands |
| `/plugins` | `/pl` | Displays all loaded and active plugins |
| `/version` | `/ver`, `/about` | Displays Pywer version and Bedrock protocol info |
| `/pos` | — | Displays feet position, yaw, pitch, ground state, and fall distance |
| `/tp <x> <y> <z>` | `/teleport` | Teleports player to relative (`~`) or absolute coordinates |
| `/give <item> [n] [slot]` | — | Gives an item stack to the player's inventory |
| `/setblock <x> <y> <z> <block>` | — | Sets a block at coordinates (supports `~` relative coords) |
| `/inv` | — | Prints contents of active inventory slots |
| `/blocks` | — | Lists all registered block palette keys |
| `/items` | — | Lists all registered item keys |
| `/tools` | — | Gives a full set of starter wooden tools |

---

## 📊 Implementation Status

| Subsystem | Components | Status |
|-----------|------------|:------:|
| **Networking** | RakNet, Offline Ping/Pong, Encryption (ECDH P-384 / AES-CTR), Zlib, Batched Packet Bundler | ✅ Complete |
| **Protocol** | Protocol 766 (Bedrock v1.21.50), Handshake, StartGame, CreativeContent, Chunk Sending | ✅ Complete |
| **World** | Chunks, Palettes, Block Storage, Async Chunk Generation Pipeline, Persistence | ✅ Complete |
| **Player** | Authentication, Session, Movement & Eye Offsets, Fall Distance, Health, Knockback | ✅ Complete |
| **Inventory** | Server-Authoritative 36-slot, Containers (Chests, Workbenches), Crafting 2x2 & 3x3, Predictions | ✅ Complete |
| **Entities** | Spatial Bucketing Grid, 3D Raycasting, AABB, Items (Drag/Bounce/Merge), Projectiles (Arrow/Snowball), Mobs (Zombie/Cow) | ✅ Complete |
| **Event System** | 6 Execution Priorities (`LOWEST` to `MONITOR`), `Cancellable`, `@listen`, Fault Isolation | ✅ Complete |
| **Plugin API** | Compiled `.pywer` Format, AST Validation CLI, In-Memory Virtual Loader (`importlib.abc`), `PluginBase`, `PluginConfig` | ✅ Complete |
| **Scheduler** | 20 TPS Tick-Aligned `run_later`, `run_repeating`, Multithreaded `run_async` with Main-Thread Queues | ✅ Complete |
| **Commands** | Unified `CommandManager`, `PlayerCommandSender`, `ConsoleCommandSender`, `/` and `!` Prefixes | ✅ Complete |

---

## 🧪 Verification & Testing

Pywer includes automated unit test suites and end-to-end smoke test harnesses:

```bash
# Run complete unit test suite (80+ tests)
python -m unittest discover tests/ -v

# Run Milestone 4 Event & Plugin Architecture Smoke Test
python tools/smoke_test_plugins.py

# Run Milestone 3 Entity & Physics Smoke Test
python tools/smoke_test_entities.py

# Run Milestone 2 Inventory & Container Smoke Test
python tools/smoke_test_inventory.py
```

---

## 📱 Supported Platforms

| Platform | Runtime | Status |
|----------|---------|:------:|
| **Windows** | Python 3.10+ | ✅ Verified |
| **Linux** (Ubuntu / Debian / Arch) | Python 3.10+ | ✅ Verified |
| **macOS** | Python 3.10+ | ✅ Verified |
| **Android** | Termux / Pydroid 3 | ✅ Verified |

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

<!-- یه ایرانی اینو ساخته! البته وایبکدشده به کسی نگیا -->

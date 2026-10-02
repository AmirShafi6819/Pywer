<p align="center">
  <img src="docs/logo (1).png" width="220" alt="Pywer Logo">
</p>

<h1 align="center">Pywer</h1>

<p align="center">
  A lightweight, high-performance Minecraft Bedrock server software written entirely in Python.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Bedrock-1.21.50-3CB371?style=for-the-badge">
  <img src="https://img.shields.io/badge/Status-Development-orange?style=for-the-badge">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge">
</p>

---

# Overview

**Pywer** is an experimental Minecraft Bedrock server implementation written entirely in **Python**.

The project focuses on delivering a clean, maintainable and high-performance server architecture while remaining lightweight enough to run on both desktop and mobile environments.

Unlike traditional server software, Pywer is distributed as a single Python package and can be installed directly using **pip**.

Current protocol support:

**Minecraft Bedrock 1.21.50**

> **Status:** Active Development

---

# Features

- High-performance asynchronous networking
- Pure Python implementation
- Single-file architecture
- Installable through `pip`
- Android compatible (Termux / Pydroid)
- Cross-platform
- Lightweight and easy to deploy
- Designed for future extensibility

---

# Installation

## Install from PyPI

```bash
pip install pywer
```

Run the server:

```bash
pywer
```

---

## Install from Releases

The latest compiled releases can also be downloaded directly from the GitHub Releases page.

---

# Implementation Status

## Networking

- ✅ RakNet
- ✅ Packet System
- ✅ Login Sequence
- ✅ Encryption
- ✅ Compression
- ✅ Tick System
- ✅ StartGame

---

## World

- ✅ World Loading
- ✅ Chunk Generation
- ✅ Chunk Sending
- ✅ Runtime IDs
- ✅ Block Updates

---

## Player

- ✅ Player Spawn
- ✅ Player Movement
- ✅ Teleportation
- ✅ Gamemode
- ❌ Health
- ❌ Hunger
- ❌ Permissions

---

## Inventory

- ✅ Inventory
- ✅ Hotbar
- ✅ Equipment
- ✅ Containers
- ✅ Item Transactions

---

## Items

- ✅ Item System
- ✅ Item Serialization
- ✅ Item Components

---

## Commands

- ❌ Command Framework
- ✅ Built-in Commands

---

## Not Yet Implemented

### API

- ❌ Plugin API
- ❌ Event System
- ❌ Scheduler
- ❌ Permissions API

### Entities

- ❌ Entity System
- ❌ Mob AI
- ❌ Animals
- ❌ Monsters
- ❌ NPCs

### Gameplay

- 🚧 Crafting
- 🚧 Redstone
- 🚧 Weather
- 🚧 Time
- 🚧 Scoreboard
- 🚧 Boss Bars

---

# Architecture

Pywer is designed around a modern asynchronous architecture with a strong emphasis on simplicity and maintainability.

Core design goals include:

- Clean codebase
- Minimal dependencies
- High performance
- Low memory usage
- Cross-platform compatibility
- Mobile support
- Easy future expansion

---

# Supported Platforms

| Platform | Status |
|----------|:------:|
| Windows | ✅ |
| Linux | ✅ |
| macOS | ✅ |
| Android | ✅ |

---

# Roadmap

Upcoming milestones include:

- Plugin API
- Event System
- Entity Engine
- Mob AI
- Scoreboard
- Redstone Simulation
- Crafting System
- World Persistence Improvements
- Performance Optimizations

---

# Contributing

Contributions, suggestions and bug reports are always welcome.

If you would like to contribute to the project, feel free to open an Issue or submit a Pull Request.

---

# License

This project is released under the **MIT License**.

یه ایرانی اینو ساخته! البته وایبکدشده به کسی نگیا

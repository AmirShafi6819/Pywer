# Repository Layout, Packaging, and PEP 8 Formatting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish standard Python packaging, repository organization, and PEP 8 formatting/spacing across all Pywer modules while preserving 100% protocol and runtime integrity.

**Architecture:** Add standard packaging (`pyproject.toml`, `LICENSE`, `tools/`, `tests/`), then systematically expand and format the codebase by logical batches (Foundations/Utils -> Crypto -> Networking/Protocol -> Packets -> World/Storage -> Player/Server), validating each batch with automated tests and AST compilation.

**Tech Stack:** Python 3.10+ standard library, `unittest`, `py_compile`.

**Spec:** `docs/superpowers/specs/2026-10-03-repository-layout-and-formatting-design.md`

## Global Constraints

- Pure Python standard library only (no third-party runtime dependencies).
- Zero semantic modifications to network structs, packet IDs, crypto math, or world generation algorithms.
- Full PEP 8 compliance: multi-line compound statements, no semicolons, 2 blank lines between top-level definitions, 1 blank line between methods.

---

### Task 1: Repository Structure & Packaging Metadata

**Files:**
- Create: `pyproject.toml`
- Create: `LICENSE`
- Move: `script_1.py` -> `tools/concat_codebase.py`
- Modify: `docs/logo.png` (rename from `docs/logo (1).png`)
- Modify: `README.md` (update logo link if needed)

**Interfaces:**
- Produces: Standard pip-installable packaging configuration with `pywer = pywer.server.main:main` console entry point.

- [ ] **Step 1: Create `pyproject.toml`**
  Write valid standard packaging configuration:
  ```toml
  [build-system]
  requires = ["setuptools>=61.0"]
  build-backend = "setuptools.build_meta"

  [project]
  name = "pywer"
  version = "0.9.1.dev0"
  description = "Pure Python standard library Minecraft Bedrock 1.21.50 (protocol 766) server"
  readme = "README.md"
  requires-python = ">=3.10"
  license = { text = "MIT" }
  authors = [
      { name = "EXBY" },
      { name = "ManiTheFerfri" },
  ]
  keywords = ["minecraft", "bedrock", "server", "pure-python", "raknet"]
  classifiers = [
      "Development Status :: 3 - Alpha",
      "Intended Audience :: Developers",
      "License :: OSI Approved :: MIT License",
      "Programming Language :: Python :: 3",
      "Programming Language :: Python :: 3.10",
      "Programming Language :: Python :: 3.11",
      "Programming Language :: Python :: 3.12",
  ]

  [project.scripts]
  pywer = "pywer.server.main:main"

  [tool.setuptools.packages.find]
  where = ["."]
  include = ["pywer*"]
  ```

- [ ] **Step 2: Create `LICENSE` file**
  Add standard MIT License text for Pywer contributors.

- [ ] **Step 3: Move `script_1.py` to `tools/concat_codebase.py` and rename logo**
  Move `script_1.py` to `tools/concat_codebase.py` using git mv, and rename `docs/logo (1).png` to `docs/logo.png`.

- [ ] **Step 4: Verify editable build capability**
  Run: `python -m py_compile pyproject.toml` (or syntax validation check).

- [ ] **Step 5: Commit**
  ```bash
  git add pyproject.toml LICENSE tools/ docs/
  git commit -m "chore: setup standard pyproject.toml, LICENSE, and tools directory"
  ```

---

### Task 2: Test Suite Scaffolding

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_serializers.py`
- Create: `tests/test_crypto.py`
- Create: `tests/test_imports.py`

**Interfaces:**
- Consumes: `pywer.util.serializer`, `pywer.crypto.aes`, `pywer.crypto.ec`, all `pywer.*` packages.
- Produces: Automated verification suite to run after formatting each module batch.

- [ ] **Step 1: Write `tests/test_serializers.py`**
  Cover `ByteReader` and `ByteWriter` varuint, varint, u16/u32/u64, float, double, string, and UUID round-trip tests.

- [ ] **Step 2: Write `tests/test_crypto.py`**
  Test AES-256 CTR encryption/decryption idempotency and P-384 ECDH key generation / curve verification.

- [ ] **Step 3: Write `tests/test_imports.py`**
  Iterate over all `.py` files in `pywer/` and verify they import cleanly.

- [ ] **Step 4: Run unit tests**
  Run: `python -m unittest discover -s tests -v`
  Expected: All tests PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add tests/
  git commit -m "test: add test suite for serializers, crypto, and module imports"
  ```

---

### Task 3: Batch 1 - Core Utilities & Logging Formatting

**Files:**
- Modify: `pywer/config.py`
- Modify: `pywer/log.py`
- Modify: `pywer/event.py`
- Modify: `pywer/util/serializer.py`
- Modify: `pywer/util/nbt.py`

**Interfaces:**
- Consumes: Standard library `struct`, `uuid`, `time`, `sys`.
- Produces: Cleanly spaced, PEP 8 compliant `ByteReader`, `ByteWriter`, `log`, `dbg`, and event managers.

- [ ] **Step 1: Format `pywer/log.py` and `pywer/config.py`**
  Expand inline statements, add PEP 8 spacing and docstrings.

- [ ] **Step 2: Format `pywer/event.py`**
  Expand event classes, handlers, and event manager registration into proper multi-line blocks.

- [ ] **Step 3: Format `pywer/util/serializer.py` and `pywer/util/nbt.py`**
  Split all one-line reader/writer methods into multi-line methods with proper spacing, indentation, and docstrings.

- [ ] **Step 4: Run serializer and import tests**
  Run: `python -m unittest discover -s tests -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add pywer/config.py pywer/log.py pywer/event.py pywer/util/
  git commit -m "style: format core utilities, serializers, and event system to PEP 8"
  ```

---

### Task 4: Batch 2 - Cryptography Formatting

**Files:**
- Modify: `pywer/crypto/aes.py`
- Modify: `pywer/crypto/ec.py`
- Modify: `pywer/crypto/jwt.py`
- Modify: `pywer/crypto/bedrock.py`

**Interfaces:**
- Consumes: Standard library `hashlib`, `secrets`, `json`, `base64`.
- Produces: Formatted `AES256`, `AESCTR`, `BedrockCipher`, ECDH curve functions, and JWT helpers.

- [ ] **Step 1: Format `pywer/crypto/aes.py`**
  Convert `_build_sbox` rotl lambda into a helper function, un-golf S-box generation and round key generation, and split multi-statement lines.

- [ ] **Step 2: Format `pywer/crypto/ec.py`**
  Expand `_inv`, `ec_on_curve`, `ec_add`, `ec_mul`, `ec_keygen`, `spki_to_pub`, `es384_sign`, and `es384_verify`.

- [ ] **Step 3: Format `pywer/crypto/jwt.py` and `pywer/crypto/bedrock.py`**
  Expand JWT header parsing and BedrockCipher encrypt/decrypt methods.

- [ ] **Step 4: Run crypto unit tests**
  Run: `python -m unittest tests/test_crypto.py -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add pywer/crypto/
  git commit -m "style: format cryptography modules (AES, P-384 ECC, JWT) to PEP 8"
  ```

---

### Task 5: Batch 3 - Networking & Protocol Codecs Formatting

**Files:**
- Modify: `pywer/net/raknet.py`
- Modify: `pywer/protocol/packet_ids.py`
- Modify: `pywer/protocol/flags.py`
- Modify: `pywer/protocol/names.py`
- Modify: `pywer/protocol/item_stack.py`
- Modify: `pywer/protocol/login.py`
- Modify: `pywer/protocol/auth_input.py`
- Modify: `pywer/protocol/inventory.py`
- Modify: `pywer/protocol/transaction.py`

**Interfaces:**
- Consumes: `pywer.util.serializer`, `pywer.crypto.*`.
- Produces: Fully formatted protocol parsers and serializers with clean multi-line logic.

- [ ] **Step 1: Format `pywer/net/raknet.py` and `pywer/protocol/packet_ids.py`, `flags.py`, `names.py`**
  Expand magic constants, packet tables, flag decoders, and RakNet address encoders.

- [ ] **Step 2: Format `pywer/protocol/login.py`, `auth_input.py`, `item_stack.py`**
  Expand single-line parsing routines, loops, and bitfield extraction.

- [ ] **Step 3: Format `pywer/protocol/inventory.py` and `transaction.py`**
  Un-golf inventory transaction parsers, container builders, and item stack response generators.

- [ ] **Step 4: Verify compilation and tests**
  Run: `python -m py_compile pywer/net/*.py pywer/protocol/*.py` && `python -m unittest discover -s tests -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add pywer/net/ pywer/protocol/
  git commit -m "style: format RakNet networking and protocol codecs to PEP 8"
  ```

---

### Task 6: Batch 4 - Packet Builders Formatting

**Files:**
- Modify: `pywer/packets/abilities.py`
- Modify: `pywer/packets/entity.py`
- Modify: `pywer/packets/item_actor.py`
- Modify: `pywer/packets/metadata.py`
- Modify: `pywer/packets/player_list.py`
- Modify: `pywer/packets/skin.py`
- Modify: `pywer/packets/sound.py`
- Modify: `pywer/packets/spawn.py`
- Modify: `pywer/packets/start_game.py`
- Modify: `pywer/packets/text.py`

**Interfaces:**
- Consumes: `ByteWriter`, packet IDs.
- Produces: Formatted Bedrock packet construction functions with proper argument lists and indentation.

- [ ] **Step 1: Format metadata, sound, text, and abilities packets**
  Expand `build_set_actor_data`, `build_text`, `build_play_sound`, `build_update_abilities`.

- [ ] **Step 2: Format player_list, skin, spawn, item_actor, and entity packets**
  Expand entity movement, player list add/remove, skin serialization, and actor spawn builders.

- [ ] **Step 3: Format start_game packet builder**
  Clean up world parameters, game rules, and item table encoding in `build_start_game`.

- [ ] **Step 4: Verify compilation and tests**
  Run: `python -m py_compile pywer/packets/*.py` && `python -m unittest discover -s tests -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add pywer/packets/
  git commit -m "style: format Bedrock packet builder modules to PEP 8"
  ```

---

### Task 7: Batch 5 - World, Terrain & Storage Formatting

**Files:**
- Modify: `pywer/storage.py`
- Modify: `pywer/world/state.py`
- Modify: `pywer/world/query.py`
- Modify: `pywer/world/blocks.py`
- Modify: `pywer/world/chunk.py`
- Modify: `pywer/world/terrain.py`
- Modify: `pywer/world/item_entity.py`

**Interfaces:**
- Consumes: `pywer.config`, `pywer.storage`.
- Produces: Well-spaced noise math in `terrain.py`, clean chunk subchunk paletting in `chunk.py`, block drop lookup, and JSON persistence.

- [ ] **Step 1: Format `pywer/storage.py`, `state.py`, and `query.py`**
  Expand world and player storage load/save routines, block query functions, and chunk dirty tracking.

- [ ] **Step 2: Format `pywer/world/terrain.py`**
  Expand `_hash2`, `_vnoise`, `terrain_height`, `tree_at`, `column_layers`, and `tree_blocks` into readable, well-spaced functions without single-line semicolons.

- [ ] **Step 3: Format `pywer/world/blocks.py`, `chunk.py`, and `item_entity.py`**
  Un-golf sub-chunk builder, runtime block mapping, dropped item physics, and pickup logic.

- [ ] **Step 4: Verify compilation and tests**
  Run: `python -m py_compile pywer/world/*.py pywer/storage.py` && `python -m unittest discover -s tests -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add pywer/storage.py pywer/world/
  git commit -m "style: format terrain generation, chunk serialization, and storage to PEP 8"
  ```

---

### Task 8: Batch 6 - Player, Session & Server Formatting

**Files:**
- Modify: `pywer/player/containers.py`
- Modify: `pywer/player/inventory.py`
- Modify: `pywer/player/inventory_manager.py`
- Modify: `pywer/player/movement.py`
- Modify: `pywer/player/prediction.py`
- Modify: `pywer/player/session.py`
- Modify: `pywer/server/main.py`
- Modify: `pywer/server/server.py`
- Modify: `pywer.py`, `pywer/__main__.py`, `pywer/__init__.py`

**Interfaces:**
- Consumes: All `pywer.*` subsystems.
- Produces: Fully un-golfed, readable `Session` (1,294 lines expanded with proper structure) and `Server` event loop.

- [ ] **Step 1: Format player inventory, containers, movement, and prediction**
  Format `containers.py`, `inventory.py`, `inventory_manager.py`, `movement.py`, and `prediction.py`.

- [ ] **Step 2: Format `pywer/player/session.py`**
  Systematically expand all semicolon-chained initialization lines, multi-statement event handlers, packet decoders, and window management routines into clean PEP 8 Python blocks.

- [ ] **Step 3: Format `pywer/server/server.py`, `main.py`, `pywer.py`, and `__main__.py`**
  Format UDP `Server` event loop, command dispatcher, join/leave handlers, and main launcher.

- [ ] **Step 4: Verify complete test suite**
  Run: `python -m unittest discover -s tests -v`
  Expected: PASS.

- [ ] **Step 5: Commit**
  ```bash
  git add pywer/player/ pywer/server/ pywer.py pywer/__main__.py pywer/__init__.py
  git commit -m "style: format player session simulation and server engine to PEP 8"
  ```

---

### Task 9: End-to-End Verification & Server Smoke Test

**Files:**
- Verify: Full repository syntax and test suite.

- [ ] **Step 1: Run comprehensive compilation check**
  Run: `python -m py_compile pywer.py tools/concat_codebase.py`
  Verify all files under `pywer/` compile with 0 syntax warnings.

- [ ] **Step 2: Run all unit tests**
  Run: `python -m unittest discover -s tests -v`
  Verify 100% test pass rate.

- [ ] **Step 3: Run server smoke test**
  Launch `python pywer.py 19133` in background, verify banner and listening socket initialization, then terminate cleanly.

- [ ] **Step 4: Push all changes to remote**
  Run `git push origin main`.

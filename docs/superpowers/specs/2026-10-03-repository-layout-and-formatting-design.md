# Design Spec: Repository Layout, Packaging, and PEP 8 Formatting

- **Status:** Approved
- **Date:** 2026-10-03
- **Project:** Pywer (Minecraft Bedrock 1.21.50 Protocol 766 Dedicated Server)

---

## 1. Objectives

1. Transform Pywer from an un-packaged, minified/code-golfed repository into a clean, well-spaced, standard Python project.
2. Establish proper Python packaging metadata (`pyproject.toml`, `LICENSE`, `tools/`, `tests/`).
3. Expand and format all 50+ Python modules under `pywer/` according to standard PEP 8 conventions:
   - Split all semicolon-chained statements onto individual lines.
   - Expand all single-line compound statements (`if`, `while`, `for`, `try/except`, `def`) into multi-line indented blocks.
   - Enforce proper vertical spacing (2 blank lines between module-level definitions, 1 blank line between methods).
   - Format operator and argument spacing.
4. Guarantee 100% semantic and runtime preservation:
   - Zero modifications to protocol byte representations, packet structures, cryptographic calculations, or world generation algorithms.
   - Full verification via automated AST compilation and module import checks.

---

## 2. Repository Layout & Structural Changes

### 2.1 File Reorganization
- **`pyproject.toml` (New):**
  - Modern PEP 517/621 configuration using `setuptools.build_meta`.
  - Package name: `pywer`
  - Version: `0.9.1.dev0`
  - Python requirement: `>=3.10`
  - Dependencies: None (pure Python standard library).
  - Entry point: `pywer = pywer.server.main:main`
- **`LICENSE` (New):** Standard MIT License naming EXBY / Pywer Contributors.
- **`tools/` (New directory):**
  - Move root script `script_1.py` to `tools/concat_codebase.py` and document its usage.
- **`tests/` (New directory):**
  - Add basic test suite to verify core components:
    - `tests/test_serializers.py`: `ByteReader` and `ByteWriter` roundtrips (varints, integers, floats, strings, UUIDs).
    - `tests/test_crypto.py`: P-384 ECDH point addition/multiplication and AES-256 CTR stream encryption.
    - `tests/test_imports.py`: Verifies every module in `pywer/` imports cleanly without syntax errors or missing dependencies.
- **Asset naming:**
  - Rename `docs/logo (1).png` to `docs/logo.png`.
  - Update any markdown references to match.

---

## 3. Code Formatting & Spacing Guidelines

Each module under `pywer/` will be systematically updated following strict rules:

1. **No Semicolons:**
   ```python
   # Before:
   self.guid = random.getrandbits(63); self.port = port
   # After:
   self.guid = random.getrandbits(63)
   self.port = port
   ```
2. **Multi-line Compound Statements:**
   ```python
   # Before:
   if not (MIN_Y <= y <= MAX_Y): return False
   # After:
   if not (MIN_Y <= y <= MAX_Y):
       return False
   ```
3. **Multi-line Exception Handling:**
   ```python
   # Before:
   try: self.sock.setsockopt(...) \n except OSError: pass
   # After:
   try:
       self.sock.setsockopt(...)
   except OSError:
       pass
   ```
4. **Function Definitions & Returns:**
   ```python
   # Before:
   def left(self): return len(self.d) - self.p
   # After:
   def left(self):
       return len(self.d) - self.p
   ```
5. **Operator & Math Spacing:**
   - Add spaces around binary operators (`+`, `-`, `*`, `/`, `^`, `&`, `|`, `==`, `!=`).
   - Add spaces after commas in tuples, lists, and parameter lists.
6. **Preservation of Protocol Integrity:**
   - Do NOT alter any hex values, bitmasks, network structs, packet IDs, or endianness settings.
   - Do NOT rename public APIs or methods.

---

## 4. Execution Sequence & Module Batches

Formatting will be applied and validated across logical batches:
1. **Packaging & Directory Structure:** `pyproject.toml`, `LICENSE`, `tools/`, `tests/`.
2. **Batch 1 - Foundations & Utilities:**
   - `pywer/config.py`
   - `pywer/log.py`
   - `pywer/event.py`
   - `pywer/util/serializer.py`
   - `pywer/util/nbt.py`
3. **Batch 2 - Cryptography:**
   - `pywer/crypto/aes.py`
   - `pywer/crypto/ec.py`
   - `pywer/crypto/jwt.py`
   - `pywer/crypto/bedrock.py`
4. **Batch 3 - Networking & Protocol:**
   - `pywer/net/raknet.py`
   - `pywer/protocol/*.py` (packet IDs, flags, item stack, names, auth input, login, inventory, transaction)
5. **Batch 4 - Packets:**
   - `pywer/packets/*.py` (abilities, entity, item_actor, metadata, player_list, skin, sound, spawn, start_game, text)
6. **Batch 5 - World & Storage:**
   - `pywer/storage.py`
   - `pywer/world/*.py` (blocks, chunk, item_entity, query, state, terrain)
7. **Batch 6 - Player & Server:**
   - `pywer/player/containers.py`
   - `pywer/player/inventory.py`
   - `pywer/player/inventory_manager.py`
   - `pywer/player/movement.py`
   - `pywer/player/prediction.py`
   - `pywer/player/session.py`
   - `pywer/server/main.py`
   - `pywer/server/server.py`
   - `pywer.py`, `pywer/__main__.py`, `pywer/__init__.py`

---

## 5. Verification Plan

1. **Compilation Check:** Run `python -m py_compile` across all formatted files to verify syntax.
2. **Automated Unit Tests:** Execute `python -m unittest discover -s tests` to verify:
   - Serializer byte encoding and decoding.
   - ECDH curve math and AES-256 CTR encryption matching expected vectors.
   - Clean imports of all modules.
3. **Server Smoke Test:** Run `python pywer.py 19132` in a subprocess with timeout to verify the banner prints and the server initializes listening on UDP without errors.

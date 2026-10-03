# ---------------------------------------------------------------- server
import math, random, select, socket, struct, time
from .. import config
from ..storage import WorldStorage, PlayerStorage, SAVE_INTERVAL
from ..log import log
from ..util.serializer import ByteReader, ByteWriter
from ..crypto.ec import ec_keygen
from ..net.raknet import RAKNET_MAGIC, enc_addr
from ..protocol.inventory import CONTAINER_ID_FIRST, CONTAINER_ID_LAST
from ..protocol.packet_ids import (PID_ADD_ITEM_ACTOR, PID_ADD_PLAYER, PID_MOVE_ACTOR_ABSOLUTE,
                                   PID_PLAYER_LIST, PID_REMOVE_ACTOR, PID_TEXT, PID_UPDATE_BLOCK)
from ..world.chunk import build_update_block
from ..world.blocks import BLOCK_KEYS, BLOCK_RUNTIME, ITEM_RUNTIME, drops_for
from ..data.item_table import ITEM_TABLE
ITEM_NAME = {rid: name.split(':')[-1] for name, rid, _ in ITEM_TABLE}
from ..world.query import get_block, is_solid
from ..world.state import CHUNK_CACHE, EDITS, mark_dirty, load_edits
from ..world import item_entity as ie
from ..player.inventory import add_item, item_tuple, first_empty_slot
from ..packets.item_actor import build_add_item_actor
from ..packets.entity import build_move_entity
from ..packets.player_list import build_player_list_add, build_player_list_remove
from ..packets.spawn import build_add_player
from ..packets.text import build_text
from ..player.movement import NETWORK_EYE_OFFSET
from ..player.inventory import item_tuple
from ..player.session import Session
from ..event import manager as events, PlayerJoinEvent, PlayerQuitEvent

class Server:
    SEND_TIMEOUT = 2.0
    def __init__(self, port=config.PORT, bind="0.0.0.0"):
        self.guid = random.getrandbits(63); self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        except OSError: pass
        self.sock.bind((bind, port)); self.sock.setblocking(False)
        self.sessions = {}; self.key = ec_keygen(); self.next_rid = 1; self.item_entities = {}
        self._last_tick = 0.0
        self.world_storage = WorldStorage()
        self.player_storage = PlayerStorage()
        self._last_save = time.time()
        self._window_id = CONTAINER_ID_FIRST
        self.load_world()
        self.motd = "MCPE;pywer-v0.9.1dev;%d;%s;0;1;%d;Minimal;Creative;1;%d;%d;" % (
            config.PROTOCOL, config.GAME_VERSION, self.guid, port, port + 1)
    def send(self, data, addr):
        """UDP send that survives a full kernel send buffer.

        The socket is non-blocking, so a burst (e.g. the initial 81 chunks per player)
        can fill the buffer and make sendto() raise BlockingIOError. Dropping that
        datagram silently desyncs clients, so wait for writability instead of losing it.
        """
        deadline = time.time() + self.SEND_TIMEOUT
        while True:
            try:
                self.sock.sendto(data, addr); return True
            except (BlockingIOError, InterruptedError):
                if time.time() >= deadline:
                    log("RakNet", "send buffer still full, dropped %d bytes to %s" % (len(data), addr)); return False
                select.select([], [self.sock], [], 0.02)
            except OSError as e:
                log("RakNet", "send error to %s: %r" % (addr, e)); return False
    def next_window_id(self):
        """PocketMine InventoryManager::getNewWindowId - cycles inside ContainerIds::FIRST..LAST."""
        self._window_id = max(CONTAINER_ID_FIRST,
                             (self._window_id + 1) % CONTAINER_ID_LAST)
        return self._window_id

    def container_id(self):
        """The FullContainerName id for inventory contents.

        PocketMine always uses lastInventoryNetworkId here - a plain inventory id in
        1..100. It must NOT be a ContainerUIIds value: those are UI container ids, and using
        one here makes the client's inventory screen read the wrong container.
        """
        return self._window_id

    def load_world(self):
        """Restore the saved level, or start a fresh generated one."""
        had_file = self.world_storage.load()
        self.player_storage.load()
        saved = self.world_storage.loaded_edits()
        if had_file:
            load_edits(saved)
            meta = self.world_storage.meta
            if isinstance(meta.get("seed"), int):
                config.SEED = meta["seed"]
            self.world_note = (("seed %d, %d changed chunk(s) restored from %s"
                                % (config.SEED, len(saved), self.world_storage.path))
                               if saved else
                               ("loaded %s (seed %d), no blocks changed yet"
                                % (self.world_storage.path, config.SEED)))
        else:
            self.world_note = "no saved world at %s, generating terrain with seed %d" % (
                self.world_storage.path, config.SEED)
        # terrain.py computed SPAWN at import time from the default seed; recompute if needed
        if config.TERRAIN:
            from ..world.terrain import find_spawn
            from ..world import terrain as _terrain
            _terrain.SPAWN = find_spawn()

    def save_all(self, force=False):
        """Persist the world and every online player."""
        self.world_storage.save(meta={"seed": config.SEED, "version": config.GAME_VERSION},
                                edits=EDITS if EDITS else None)
        for p in self.playing():
            self.player_storage.put(p.uuid, p.to_dict())
        self.player_storage.save(force=force)
        self._last_save = time.time()
        self._window_id = CONTAINER_ID_FIRST

    def save_player(self, p):
        self.player_storage.put(p.uuid, p.to_dict())
        self.player_storage.save()

    def banner(self):
        print("Minecraft Bedrock %s pywer-v0.9.1dev Server\nProtocol: %d\nRakNet UDP: %d\nOffline mode: ON\n"
              "World: generated terrain (seed %d)\nMovement: ENABLED (PocketMine-derived) | Mining: PocketMine-style block actions/drops" % (config.GAME_VERSION, config.PROTOCOL, self.port, config.SEED), flush=True)
        log("Server", "Listening on 0.0.0.0:%d" % self.port)
        log("World", self.world_note)
    def unconnected(self, data, addr):
        pid = data[0]
        if pid in (0x01, 0x02):
            t = data[1:9]; ms = self.motd.encode()
            self.send(b"\x1c" + t + struct.pack(">Q", self.guid) + RAKNET_MAGIC + struct.pack(">H", len(ms)) + ms, addr)
        elif pid == 0x05:
            if data[1:17] != RAKNET_MAGIC: return
            mtu = max(576, min(len(data) + 28, 1492))
            self.send(b"\x06" + RAKNET_MAGIC + struct.pack(">QBH", self.guid, 0, mtu), addr)
        elif pid == 0x07:
            r = ByteReader(data, 17)
            if r.read_u8() == 4: r.read_bytes(6)
            else: r.read_bytes(28)
            mtu = r.read_u16_be(); cguid = r.read_u64_be(); mtu = max(576, min(mtu, 1492))
            if addr not in self.sessions and len(self.sessions) >= config.MAX_PLAYERS:
                log("RakNet", "server full, ignoring %s:%d" % addr); return
            old = self.sessions.pop(addr, None)
            if old: self.on_leave(old)
            self.sessions[addr] = Session(self, addr, mtu, cguid)
            log("RakNet", "RakNet connection from %s (MTU %d)" % (addr[0], mtu))
            self.send(b"\x08" + RAKNET_MAGIC + struct.pack(">Q", self.guid) + enc_addr(*addr) + struct.pack(">HB", mtu, 0), addr)
    def playing(self, exclude=None):
        return [s for s in self.sessions.values() if s.spawned and s is not exclude]
    def broadcast(self, pkts, exclude=None):
        for s in self.playing(exclude):
            try: s.send_packets(pkts)
            except Exception as e: log("Player", "send error: %r" % e)
    def handle_entity_attack(self, attacker, target_rid, player_pos, click_pos):
        """PocketMine Player::attackEntity-style validation for player-vs-player hits.
        This keeps combat generic: no item/weapon simulation is performed here.
        """
        target = None
        for s in self.playing():
            if s.rid == target_rid:
                target = s; break
        if target is None or target is attacker or target.dead: return False
        if attacker.attack_time > 0: return False
        dx = target.feet()[0] - attacker.feet()[0]; dy = (target.feet()[1] + 0.9) - (attacker.feet()[1] + 1.62); dz = target.feet()[2] - attacker.feet()[2]
        dist2 = dx*dx + dy*dy + dz*dz
        # Player::MAX_REACH_DISTANCE_ENTITY_INTERACTION = 8
        if dist2 > 64.0: return False
        # Sanity-check the client supplied attacker position; it must be close to the server position.
        af = attacker.feet()
        if sum((player_pos[i] - (af[i] + (0.0 if i != 1 else NETWORK_EYE_OFFSET)))**2 for i in range(3)) > 4.0:
            return False
        attacker.attack_time = 10
        target.damage(1.0, attacker)
        return True

    def break_block(self, p, x, y, z, old_key=None):
        """PocketMine World::useBreakOn subset for pywer's implemented blocks.

        Drops come from world.blocks.drops_for() so the held tool decides both the drop table
        and the count, and creative drops nothing at all.
        """
        key = old_key or get_block(x, y, z)
        if key in ("air", "water", "bedrock") or get_block(x, y, z) != key:
            return False
        if not self.set_block(x, y, z, "air"):
            return False
        held = p.held_item_id() if p is not None else 0
        drops = drops_for(key, held)
        if p is not None and not p.gamemode_is_creative():
            for item_key, count in drops:
                self.drop_item((x + 0.5, y + 1.0, z + 0.5), item_key, count)
        elif p is None:
            for item_key, count in drops:
                self.drop_item((x + 0.5, y + 1.0, z + 0.5), item_key, count)
        if not drops: dbg("World", "no drops for %s at %d,%d,%d (tool %s)" % (key, x, y, z, held))
        return True

    def drop_item(self, pos, item_key, count=1, motion=None, now=None):
        now = time.time() if now is None else now
        """PocketMine World::dropItem equivalent using AddItemActorPacket.

        PocketMine uses a small random X/Z impulse and Y=0.2. Item stacks that land on top of
        an existing identical stack within MERGE_RANGE are merged instead of spawning a new
        entity, exactly like vanilla.
        """
        if item_key not in ITEM_RUNTIME:
            return False
        count = int(count)
        if count <= 0: return False
        px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
        for e in self.item_entities.values():
            if e["key"] != item_key: continue
            ex, ey, ez = e["pos"]
            if (ex - px) ** 2 + (ey - py) ** 2 + (ez - pz) ** 2 <= ie.MERGE_RANGE ** 2:
                e["count"] += count
                e["age"] = 0.0
                e["spawned_at"] = now
                e["pickup_at"] = now + ie.PICKUP_DELAY
                return True
        motion = motion or (random.random() * 0.2 - 0.1, 0.2, random.random() * 0.2 - 0.1)
        eid = self.next_rid; self.next_rid += 1
        self.item_entities[eid] = {"key": item_key, "count": count, "pos": (px, py, pz),
                                    "motion": tuple(float(v) for v in motion), "age": 0.0,
                                    "spawned_at": now, "pickup_delay": ie.PICKUP_DELAY,
                                    "pickup_at": now + ie.PICKUP_DELAY}
        pkt = Session._pk(PID_ADD_ITEM_ACTOR, build_add_item_actor(eid, item_key, count, (px, py, pz), motion))
        self.broadcast([pkt])
        return True

    def remove_item_entity(self, eid):
        """Despawn an item entity and tell every client to drop it."""
        e = self.item_entities.pop(eid, None)
        if e is None: return False
        self.broadcast([Session._pk(PID_REMOVE_ACTOR, ByteWriter().write_varint64(eid).get())])
        return True

    def tick_item_entities(self, now, dt):
        """Gravity, movement, pickup and despawn for every dropped item.

        Moved entities are broadcast each tick so the client sees them fall rather than
        teleport; without that the client keeps rendering them at their spawn point.
        """
        if not self.item_entities: return
        for eid in list(self.item_entities.keys()):
            e = self.item_entities.get(eid)
            if e is None: continue                       # already picked up this tick
            # Age comes from the wall clock, not accumulated dt, so despawn is exact
            # however irregularly the tick loop runs.
            e["age"] = now - e.get("spawned_at", now)
            if e["age"] >= ie.LIFETIME:
                self.remove_item_entity(eid); continue
            if ie.step_item(e, is_solid):
                self.broadcast([Session._pk(PID_MOVE_ACTOR_ABSOLUTE,
                                           build_move_entity(eid, e["pos"]))])
            for p in self.playing():
                if not ie.can_pickup(e, p.feet(), now, is_solid): continue
                item_id = ITEM_RUNTIME.get(e["key"])
                if item_id is None: break
                if first_empty_slot(p.inventory) is None: continue   # full: leave it lying there
                left = add_item(p.inventory, item_tuple(item_id, e["count"], 0))
                if left > 0: continue                              # nothing fitted, keep the entity
                taken = e["count"]
                e["count"] = 0
                p.sync_inventory()
                self.remove_item_entity(eid)
                log("World", "%s picked up %d %s" % (p.name, taken, e["key"]))
                break

    def set_block(self, x, y, z, key):
        """Change one block for everybody (also stored, so later chunk loads see it)."""
        if key not in BLOCK_RUNTIME: raise KeyError(key)
        if not (config.MIN_Y <= y <= config.MAX_Y): return False
        cx, cz = x >> 4, z >> 4
        EDITS.setdefault((cx, cz), {})[(x & 15, y, z & 15)] = key
        CHUNK_CACHE.pop((cx, cz), None)
        mark_dirty(cx, cz)
        self.broadcast([Session._pk(PID_UPDATE_BLOCK, build_update_block(x, y, z, key))]); return True
    def give(self, p, key, count=1, slot=None):
        """Put `count` of a block/item into the player's inventory (first empty hotbar slot)."""
        item_id = ITEM_RUNTIME.get(key)
        if item_id is None or key in ("air", "water", "bedrock"):
            p.chat_to("unknown item: %s (see !items)" % key); return False
        target = slot if slot is not None else self._first_free_slot(p)
        if target is None: p.chat_to("inventory is full"); return False
        held = p.inventory[target]
        if held[1] and held[0] == item_id: p.inventory[target] = item_tuple(item_id, held[1] + count, 0)
        else: p.inventory[target] = item_tuple(item_id, count, 0)
        p.sync_inventory_slots([target])
        p.chat_to("gave %d %s (slot %d)" % (count, key, target))
        return True

    def give_tools(self, p):
        """Hand out a full tool set so tool-dependent drops can be tested."""
        from ..world.blocks import TOOLS
        given = 0
        for slot, name in enumerate(("wooden_pickaxe", "stone_pickaxe", "iron_pickaxe",
                                     "diamond_pickaxe", "wooden_axe", "iron_axe",
                                     "wooden_shovel", "iron_shovel", "shears")):
            if slot >= 36: break
            if name not in TOOLS: continue
            item_id = ITEM_RUNTIME.get(name)
            if item_id is None: continue
            p.inventory[slot] = item_tuple(item_id, 1, 0); given += 1
        if given: p.sync_inventory_slots(range(min(given, 36)))
        p.chat_to("gave %d tools" % given)

    def _first_free_slot(self, p):
        """First empty slot, hotbar first so new items are reachable without switching."""
        for i in range(len(p.inventory)):
            if p.inventory[i][1] <= 0: return i
        return None

    def command(self, p, line):
        a = line.split()
        try:
            if a and a[0] == "blocks": p.chat_to("blocks: " + ", ".join(BLOCK_KEYS[1:]))
            elif a and a[0] == "items": p.chat_to("items: " + ", ".join(sorted(k for k in ITEM_RUNTIME if k not in ("air", "water", "bedrock"))))
            elif a and a[0] == "tools":
                self.give_tools(p)
            elif a and a[0] == "give" and len(a) >= 2:
                self.give(p, a[1], int(a[2]) if len(a) > 2 else 1,
                          int(a[3]) if len(a) > 3 else None)
            elif a and a[0] == "inv": p.chat_to("inv: " + " ".join("%d:%s x%d" % (i, ITEM_NAME.get(s[0], s[0]), s[1]) for i, s in enumerate(p.inventory) if s[1]))
            elif a and a[0] == "setblock" and len(a) == 5:
                def co(v, cur): return math.floor(cur) + int(v[1:] or 0) if v.startswith("~") else int(v)
                x, y, z = co(a[1], p.pos[0]), co(a[2], p.pos[1] - 1.62), co(a[3], p.pos[2])
                ok = self.set_block(x, y, z, a[4]); p.chat_to("setblock %d %d %d %s %s" % (x, y, z, a[4], "ok" if ok else "out of range"))
            elif a and a[0] == "pos":
                f = p.feet(); p.chat_to("pos %.2f %.2f %.2f yaw %.1f pitch %.1f ground=%s fall=%.1f" % (f + (p.yaw, p.pitch, p.on_ground, p.fall_distance)))
            elif a and a[0] == "tp" and len(a) == 4:
                f = p.feet(); t = [(f[i] + float(v[1:] or 0)) if v.startswith("~") else float(v) for i, v in enumerate(a[1:4])]
                p.teleport(*t); p.chat_to("teleported to %.1f %.1f %.1f" % tuple(t))
            else: p.chat_to("!blocks | !items | !tools | !give <item> [n] [slot] | !inv | !setblock <x|~> <y|~> <z|~> <block> | !tp <x|~> <y|~> <z|~> | !pos")
        except KeyError: p.chat_to("unknown block (see !blocks)")
        except ValueError: p.chat_to("bad coordinates")
    def on_join(self, p):
        others = self.playing(exclude=p)
        p.send_packets([Session._pk(PID_PLAYER_LIST, build_player_list_add(others + [p]))] +
                       [Session._pk(PID_ADD_PLAYER, build_add_player(o)) for o in others])
        for o in others:
            o.send_packets([Session._pk(PID_PLAYER_LIST, build_player_list_add([p])), Session._pk(PID_ADD_PLAYER, build_add_player(p))])
        msg = "§e%s joined the game" % p.name
        ev = events.call(PlayerJoinEvent(p, msg))
        if ev.message: self.broadcast([Session._pk(PID_TEXT, build_text(0, "", ev.message))])
        log("Player", "%s joined (%d online)" % (p.name, len(others) + 1))
    def on_leave(self, p):
        if not p.spawned: return
        p.spawned = False
        try: p.close_main_inventory()
        except Exception: pass
        ev = events.call(PlayerQuitEvent(p, "§e%s left the game" % p.name))
        pkts = [Session._pk(PID_PLAYER_LIST, build_player_list_remove([p])),
                Session._pk(PID_REMOVE_ACTOR, ByteWriter().write_varint64(p.rid).get())]
        if ev.message: pkts.append(Session._pk(PID_TEXT, build_text(0, "", ev.message)))
        self.broadcast(pkts)
        try: self.save_player(p)
        except Exception as e: log("Storage", "could not save %s: %r" % (p.name, e))
        log("Player", "%s left" % p.name)
    def step(self, timeout=0.02):
        rl, _, _ = select.select([self.sock], [], [], timeout)
        if rl:
            for _ in range(256):
                try: data, addr = self.sock.recvfrom(4096)
                except (BlockingIOError, InterruptedError): break
                except OSError: break
                if not data: continue
                try:
                    if data[0] & 0x80:
                        s = self.sessions.get(addr)
                        if s: s.on_datagram(data)
                    else:
                        self.unconnected(data, addr)
                except Exception as e:
                    log("RakNet", "error handling packet from %s: %r" % (addr, e))
        now = time.time()
        if now - self._last_save >= SAVE_INTERVAL: self.save_all()
        dt = min(0.1, max(0.0, now - self._last_tick)) if self._last_tick else 0.0
        self._last_tick = now
        self.tick_item_entities(now, dt)
        for a, s in list(self.sessions.items()):
            try: s.tick(now)
            except Exception as e: log("RakNet", "tick error: %r" % e)
            if s.state == "CLOSED" or now - s.last_rx > 30:
                del self.sessions[a]; self.on_leave(s)
    def run(self, stop=None):
        while not (stop and stop.is_set()): self.step()
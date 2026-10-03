"""End-to-end smoke test for Milestone 3: Entity Architecture & Physics.

Verifies:
1. Spawning Zombie, Cow, Arrow, Snowball, and ItemEntity into EntityManager.
2. Arrow flight simulation, discrete raycasting, and damage against Zombie.
3. Snowball throwing and impact shattering against Cow.
4. Hostile Zombie AI detecting and pathing towards a survival player.
5. ItemEntity gravity, spatial bucketing, and automatic player inventory pickup.
6. Entity death and PID_REMOVE_ACTOR network despawn packet broadcast.
"""

import sys
from unittest.mock import MagicMock

from pywer.server.server import Server
from pywer.player.session import Session
from pywer.entity.manager import EntityManager
from pywer.entity.mob import Zombie, Cow
from pywer.entity.projectile import Arrow, Snowball
from pywer.entity.item import ItemEntity
from pywer.protocol.packet_ids import PID_REMOVE_ACTOR
from pywer.world.blocks import ITEM_RUNTIME


def run_smoke_test():
    print("=" * 60)
    print("Starting Milestone 3 Entity Architecture & Physics Smoke Test")
    print("=" * 60)

    # 1. Setup Server, Session, and EntityManager
    srv = Server.__new__(Server)
    srv.next_rid = 1000
    srv.key = (MagicMock(), MagicMock())
    srv.broadcast = MagicMock()

    sess = Session(srv, ("127.0.0.1", 19132), 1400, 100)
    sess.send_packet = MagicMock()
    sess._set_feet((0.0, 64.0, 0.0))
    sess.gamemode_is_creative = lambda: False
    sess.name = "TestPlayer"

    srv.playing = MagicMock(return_value=[sess])
    mgr = EntityManager(srv)
    srv.entity_mgr = mgr

    # Step 1: Spawn entities into EntityManager
    zombie = mgr.spawn(Zombie, pos=(5.0, 64.0, 0.0))
    cow = mgr.spawn(Cow, pos=(0.0, 64.0, 5.0))
    arrow = mgr.spawn(Arrow, shooter_rid=sess.rid, pos=(0.0, 64.0, 0.0), motion=(0.0, 0.0, 0.0))
    snowball = mgr.spawn(Snowball, shooter_rid=sess.rid, pos=(0.0, 64.0, 0.0), motion=(0.0, 0.0, 0.0))
    item = mgr.spawn(ItemEntity, "oak_log", 1, pos=(0.2, 64.0, 0.2), spawned_at=0.0)

    assert zombie.rid in mgr.entities, "Zombie not in entity manager"
    assert cow.rid in mgr.entities, "Cow not in entity manager"
    assert arrow.rid in mgr.entities, "Arrow not in entity manager"
    assert snowball.rid in mgr.entities, "Snowball not in entity manager"
    assert item.rid in mgr.entities, "Item not in entity manager"
    print("[1] Successfully spawned Zombie, Cow, Arrow, Snowball, and ItemEntity into EntityManager")

    # Step 2: Projectile flight, raycast collision, and damage against Zombie
    # Position Zombie at (5.0, 64.0, 0.0), launch Arrow from (0.0, 64.0, 0.0) with vx=5.0
    combat_arrow = mgr.spawn(
        Arrow, shooter_rid=sess.rid, pos=(0.0, 64.0, 0.0), motion=(5.0, 0.0, 0.0), damage=4.0
    )
    initial_health = zombie.health
    world_is_solid = lambda x, y, z: y <= 63

    # Tick projectile
    combat_arrow.tick(now=1.0, dt=0.05, world_is_solid=world_is_solid)
    assert zombie.health < initial_health, f"Zombie took no damage! Health={zombie.health}"
    assert combat_arrow.dead, "Arrow should be consumed/dead after hitting entity"
    print(f"[2] Successfully simulated Arrow flight and collision on Zombie (Health: {initial_health} -> {zombie.health})")

    # Step 3: Snowball impact on Cow
    throw_snowball = mgr.spawn(
        Snowball, shooter_rid=sess.rid, pos=(0.0, 64.0, 0.0), motion=(0.0, 0.0, 5.0)
    )
    throw_snowball.tick(now=1.0, dt=0.05, world_is_solid=world_is_solid)
    assert throw_snowball.dead, "Snowball should shatter/despawn upon entity impact"
    print("[3] Successfully simulated Snowball impact on Cow (shattered on hit)")

    # Step 4: Hostile Zombie AI targeting survival player within 16 blocks
    mgr.update_entity_pos(zombie, (8.0, 64.0, 0.0))
    zombie.tick_living()
    zombie.tick(now=2.0, dt=0.05, world_is_solid=world_is_solid)
    assert zombie.ai_state == "TARGET", f"Zombie failed to target player! State={zombie.ai_state}"
    assert zombie.pos[0] < 8.0, f"Zombie did not move towards player! Pos={zombie.pos}"
    print(f"[4] Successfully verified hostile Zombie AI targeting survival player (Pos moved to {zombie.pos[0]:.2f})")

    # Step 5: ItemEntity player pickup and inventory merging
    item.pickup_at = 0.0  # Instant pickup ready
    sess.inventory[0] = (0, 0, 0)  # Empty slot 0
    mgr.tick(now=5.0, dt=0.05, world_is_solid=world_is_solid)
    log_id = ITEM_RUNTIME["oak_log"]
    assert sess.inventory[0][0] == log_id, f"Player did not receive item in inventory! Slot 0={sess.inventory[0]}"
    assert item.rid not in mgr.entities, "Picked up item entity was not removed from EntityManager"
    print(f"[5] Successfully verified ItemEntity player pickup into inventory slot 0 (Item ID {log_id})")

    # Step 6: Entity despawn and PID_REMOVE_ACTOR packet broadcast
    srv.broadcast.reset_mock()
    zombie.hurt_time = 0
    zombie.damage(999.0, source_rid=sess.rid)
    assert zombie.dead, "Zombie should be dead after lethal damage"
    mgr.tick(now=6.0, dt=0.05, world_is_solid=world_is_solid)
    assert zombie.rid not in mgr.entities, "Dead zombie not purged from EntityManager"
    srv.broadcast.assert_called()
    all_broadcasts = [call[0][0] for call in srv.broadcast.call_args_list]
    has_remove_pkt = any(
        any(pkt[0] == PID_REMOVE_ACTOR for pkt in batch) for batch in all_broadcasts
    )
    assert has_remove_pkt, "PID_REMOVE_ACTOR packet was not broadcast upon entity despawn"
    print("[6] Successfully verified entity death, removal, and PID_REMOVE_ACTOR broadcast")

    print("=" * 60)
    print("ALL MILESTONE 3 SMOKE TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        run_smoke_test()
    except Exception as e:
        print(f"\nSMOKE TEST FAILED: {e!r}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

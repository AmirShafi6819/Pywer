"""End-to-end smoke test for crafting, creative create, workbenches, and chests."""

import sys
from unittest.mock import MagicMock

from pywer.player.session import Session
from pywer.server.server import Server
from pywer.player.containers import (
    CONTAINER_INVENTORY,
    CONTAINER_UI,
    UI_CREATED_OUTPUT_SLOT,
)
from pywer.player.inventory_manager import (
    ACTION_TAKE,
    ACTION_CONSUME,
    ACTION_CREATE_OUTPUT,
    ACTION_CREATIVE_CREATE,
)
from pywer.player.recipes import (
    ID_LOG,
    ID_PLANKS,
    ID_CRAFTING_TABLE,
)
from pywer.protocol.inventory import WINDOW_WORKBENCH, WINDOW_CONTAINER

ITEM_AIR = (0, 0, 0)


def run_smoke_test():
    print("=" * 60)
    print("Starting Milestone 2 Inventory & Container Smoke Test")
    print("=" * 60)

    # 1. Setup Server & Session
    srv = Server.__new__(Server)
    srv.next_rid = 1
    srv.key = (MagicMock(), MagicMock())
    srv._window_id = 1
    srv.chests = {}
    srv.next_window_id = lambda: 10
    srv.container_id = lambda: 10
    srv.set_block = MagicMock(return_value=True)
    srv.drop_item = MagicMock(return_value=True)
    srv.playing = MagicMock(return_value=[])

    sess = Session(srv, ("127.0.0.1", 19132), 1400, 100)
    sess.send_packet = MagicMock()
    sess._set_feet((0.0, 64.0, 0.0))

    # Give player 1 oak log in hotbar slot 0
    sess.inventory[0] = (ID_LOG, 1, 0)
    log_info = sess.predictions.track_item_stack(CONTAINER_INVENTORY, 0, sess.inventory[0])
    print("[1] Player spawned with 1 Oak Log in hotbar slot 0")

    # 2. Craft Oak Log into 4 Planks in 2x2 grid
    craft2x2 = sess.containers.complex["crafting2x2"]
    craft2x2.items[0] = sess.inventory[0]
    sess.inventory[0] = ITEM_AIR
    sess.predictions.track_item_stack(CONTAINER_INVENTORY, 0, ITEM_AIR)
    grid_log_info = sess.predictions.track_item_stack("ui:28", 0, craft2x2.items[0])

    craft_log_req = [
        (ACTION_CONSUME, 1, (CONTAINER_UI, 28, grid_log_info.stack_id)),
        (ACTION_CREATE_OUTPUT, 0),
        (ACTION_TAKE, 4, (CONTAINER_UI, UI_CREATED_OUTPUT_SLOT, 0), (CONTAINER_INVENTORY, 0, 0)),
    ]
    touched = sess.inv_manager.apply_request(101, craft_log_req)
    assert sess.inventory[0] == (ID_PLANKS, 4, 0), f"Expected 4 planks, got {sess.inventory[0]}"
    assert craft2x2.items[0] == ITEM_AIR, "Crafting grid should be empty"
    print("[2] Successfully crafted 1 Oak Log -> 4 Oak Planks in 2x2 grid")

    # 3. Craft 4 Planks into 1 Crafting Table in 2x2 grid
    plank_infos = []
    for i in range(4):
        craft2x2.items[i] = (ID_PLANKS, 1, 0)
        plank_infos.append(sess.predictions.track_item_stack(f"ui:{28 + i}", i, craft2x2.items[i]))
    sess.inventory[0] = ITEM_AIR
    sess.predictions.track_item_stack(CONTAINER_INVENTORY, 0, ITEM_AIR)

    craft_table_req = [
        (ACTION_CONSUME, 1, (CONTAINER_UI, 28, plank_infos[0].stack_id)),
        (ACTION_CONSUME, 1, (CONTAINER_UI, 29, plank_infos[1].stack_id)),
        (ACTION_CONSUME, 1, (CONTAINER_UI, 30, plank_infos[2].stack_id)),
        (ACTION_CONSUME, 1, (CONTAINER_UI, 31, plank_infos[3].stack_id)),
        (ACTION_CREATE_OUTPUT, 0),
        (ACTION_TAKE, 1, (CONTAINER_UI, UI_CREATED_OUTPUT_SLOT, 0), (CONTAINER_INVENTORY, 0, 0)),
    ]
    touched = sess.inv_manager.apply_request(102, craft_table_req)
    assert sess.inventory[0] == (ID_CRAFTING_TABLE, 1, 0), f"Expected crafting table, got {sess.inventory[0]}"
    for i in range(4):
        assert craft2x2.items[i] == ITEM_AIR
    print("[3] Successfully crafted 4 Oak Planks -> 1 Crafting Table")

    # 4. Open Crafting Table window
    table_pos = (1, 64, 1)
    sess.open_crafting_table(table_pos)
    assert sess.open_window is True
    assert sess.open_window_type == WINDOW_WORKBENCH
    assert sess.open_window_pos == table_pos
    print("[4] Successfully opened 3x3 Workbench window")

    # Put stick and planks into 3x3 workbench grid to craft a sword
    craft3x3 = sess.containers.complex["crafting3x3"]
    # Sword: row 0 plank (slot 1), row 1 plank (slot 4), row 2 stick (slot 7)
    craft3x3.items[1] = (ID_PLANKS, 1, 0)
    craft3x3.items[4] = (ID_PLANKS, 1, 0)
    craft3x3.items[7] = (280, 1, 0)  # Stick
    s1 = sess.predictions.track_item_stack("ui:33", 1, craft3x3.items[1])
    s2 = sess.predictions.track_item_stack("ui:36", 4, craft3x3.items[4])
    s3 = sess.predictions.track_item_stack("ui:39", 7, craft3x3.items[7])

    craft_sword_req = [
        (ACTION_CONSUME, 1, (CONTAINER_UI, 33, s1.stack_id)),
        (ACTION_CONSUME, 1, (CONTAINER_UI, 36, s2.stack_id)),
        (ACTION_CONSUME, 1, (CONTAINER_UI, 39, s3.stack_id)),
        (ACTION_CREATE_OUTPUT, 0),
        (ACTION_TAKE, 1, (CONTAINER_UI, UI_CREATED_OUTPUT_SLOT, 0), (CONTAINER_INVENTORY, 1, 0)),
    ]
    touched = sess.inv_manager.apply_request(103, craft_sword_req)
    assert sess.inventory[1] == (268, 1, 0), f"Expected wooden sword (268), got {sess.inventory[1]}"
    print("[5] Successfully crafted Wooden Sword in 3x3 Workbench")

    sess.close_main_inventory(notify=False)
    assert sess.open_window is False

    # 5. Test Creative Mode Item Creation
    sess.gamemode_is_creative = lambda: True
    creative_req = [
        (ACTION_CREATIVE_CREATE, 340, 1),  # Diamond sword (id 340)
        (ACTION_TAKE, 1, (CONTAINER_UI, UI_CREATED_OUTPUT_SLOT, 0), (CONTAINER_INVENTORY, 2, 0)),
    ]
    sess.inv_manager.apply_request(104, creative_req)
    assert sess.inventory[2] == (340, 1, 0), f"Expected diamond sword, got {sess.inventory[2]}"
    print("[6] Successfully generated Diamond Sword via creative create action")

    # 6. Test Chest Storage & Drops
    chest_pos = (2, 64, 2)
    sess.open_chest(chest_pos)
    assert sess.open_window is True
    assert sess.open_window_type == WINDOW_CONTAINER
    assert chest_pos in srv.chests
    assert len(srv.chests[chest_pos]) == 27

    # Track diamond sword in hotbar slot 2
    sword_info = sess.predictions.track_item_stack(CONTAINER_INVENTORY, 2, sess.inventory[2])

    # Deposit diamond sword into chest slot 0
    chest_deposit_req = [
        (ACTION_TAKE, 1, (CONTAINER_INVENTORY, 2, sword_info.stack_id), (10, 0, 0)),
    ]
    sess.inv_manager.apply_request(105, chest_deposit_req)
    assert srv.chests[chest_pos][0] == (340, 1, 0), "Diamond sword should be stored in chest slot 0"
    assert sess.inventory[2] == ITEM_AIR, "Hotbar slot 2 should now be empty"
    print("[7] Successfully deposited Diamond Sword into Chest slot 0")

    # Place chest in world state and break it
    from pywer.world.state import EDITS
    EDITS.setdefault((2 >> 4, 2 >> 4), {})[(2 & 15, 64, 2 & 15)] = "chest"
    res = Server.break_block(srv, sess, 2, 64, 2)
    assert res is True, "break_block should return True for chest"
    assert chest_pos not in srv.chests, "Chest storage should be deleted when broken"
    srv.drop_item.assert_called()
    print("[8] Successfully verified Chest destruction drops stored items")

    print("=" * 60)
    print("ALL MILESTONE 2 SMOKE TESTS PASSED!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)

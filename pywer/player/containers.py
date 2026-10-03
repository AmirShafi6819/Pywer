# ---------------------------------------------------------------- player container registry
# PocketMine's InventoryManager tracks several containers per player. Two families exist:
#
#  * "simple" containers, addressed by their own network id
#      ContainerIds::INVENTORY = 0    36 slots (hotbar 0-8, main inventory 9-35)
#      ContainerIds::OFFHAND  = 119   1 slot
#      ContainerIds::ARMOR    = 120   4 slots (head, chest, legs, feet)
#
#  * "complex" containers, which all live in the single UI slot space
#      ContainerIds::UI = 124, with slots given by UIInventorySlotOffset
#
# The cursor and the player's 2x2 crafting grid are permanently complex (PocketMine
# registers them in InventoryManager::__construct), so the inventory screen always expects
# window 124 to exist.
CONTAINER_INVENTORY = 0
CONTAINER_OFFHAND = 119
CONTAINER_ARMOR = 120
CONTAINER_UI = 124

# Armor slot order used by Bedrock.
ARMOR_HEAD, ARMOR_CHEST, ARMOR_LEGS, ARMOR_FEET = 0, 1, 2, 3

# UIInventorySlotOffset (values extracted from PlayerUISlot in Bedrock)
UI_CURSOR = 0
UI_CRAFTING2X2 = {28: 0, 29: 1, 30: 2, 31: 3}

CONTAINER_SIZES = {
    CONTAINER_INVENTORY: 36,
    CONTAINER_OFFHAND: 1,
    CONTAINER_ARMOR: 4,
}

ITEM_AIR = (0, 0, 0)


class ComplexContainer:
    """An inventory addressed through the shared UI slot space (window 124)."""

    __slots__ = ("slot_map", "reverse_slot_map", "items")

    def __init__(self, slot_map, size):
        self.slot_map = dict(slot_map)          # net slot -> core slot
        self.reverse_slot_map = {v: k for k, v in self.slot_map.items()}
        self.items = [ITEM_AIR] * size

    def map_net_to_core(self, net_slot):
        return self.slot_map.get(net_slot)

    def map_core_to_net(self, core_slot):
        return self.reverse_slot_map.get(core_slot)


class ContainerRegistry:
    """Every synced container for one player, keyed by its Bedrock container id.

    The main inventory is read through the session rather than captured, so rebinding
    `session.inventory` (save loading, tests) can never leave the registry pointing at a
    stale list.
    """

    def __init__(self, session):
        self.session = session
        self.offhand = [ITEM_AIR]
        self.armor = [ITEM_AIR] * CONTAINER_SIZES[CONTAINER_ARMOR]
        # permanently-complex containers, exactly as PocketMine registers them
        self.complex = {
            "cursor": ComplexContainer({UI_CURSOR: 0}, 1),
            "crafting2x2": ComplexContainer(UI_CRAFTING2X2, 4),
        }
        self._by_net_slot = {}
        for entry in self.complex.values():
            for net, core in entry.slot_map.items():
                self._by_net_slot[net] = (entry, core)

    # -- simple containers -------------------------------------------------
    @property
    def items(self):
        return {
            CONTAINER_INVENTORY: self.session.inventory,
            CONTAINER_OFFHAND: self.offhand,
            CONTAINER_ARMOR: self.armor,
        }

    def ids(self):
        return list(self.items.keys())

    def get(self, container_id):
        return self.items.get(container_id)

    def size(self, container_id):
        cont = self.get(container_id)
        return len(cont) if cont is not None else 0

    def resolve(self, container_id, slot):
        cont = self.get(container_id)
        if cont is None or slot < 0 or slot >= len(cont):
            return None
        return cont

    # -- complex (UI) containers -------------------------------------------
    def complex_for_slot(self, net_slot):
        """(ComplexContainer, core slot) for a UI net slot, or None."""
        return self._by_net_slot.get(net_slot)

    def complex_entries(self):
        """[(name, ComplexContainer, core_slot)] for every mapped UI slot."""
        out = []
        for name, entry in self.complex.items():
            for core in range(len(entry.items)):
                out.append((name, entry, core))
        return out

    def complex_for_backing(self, lst_id):
        """(name, ComplexContainer) for a backing-list id, or None."""
        for name, entry in self.complex.items():
            if id(entry.items) == lst_id:
                return (name, entry)
        return None
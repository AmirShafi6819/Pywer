"""Block-related event classes."""

from typing import Any, Optional
from .base import Event, Cancellable


class BlockEvent(Event):
    """Base class for events concerning a world block."""

    def __init__(self, player: Any, x: int, y: int, z: int, block_key: str, **kwargs: Any) -> None:
        super().__init__()
        self.player = player
        self.x = int(x)
        self.y = int(y)
        self.z = int(z)
        self.block_key = block_key
        self.__dict__.update(kwargs)

    @property
    def pos(self):
        return (self.x, self.y, self.z)


class BlockBreakEvent(Cancellable, BlockEvent):
    """Fired before a block is broken. Cancelling keeps the block intact."""

    def __init__(
        self, player: Any, x: int, y: int, z: int, block_key: str, drops: Optional[list] = None
    ) -> None:
        super().__init__(player, x, y, z, block_key)
        self.drops = drops if drops is not None else []


class BlockPlaceEvent(Cancellable, BlockEvent):
    """Fired before a block is placed. Cancelling prevents the placement."""

    def __init__(
        self, player: Any, x: int, y: int, z: int, block_key: str, against_pos: Optional[tuple] = None
    ) -> None:
        super().__init__(player, x, y, z, block_key)
        self.against_pos = against_pos


class BlockInteractEvent(Cancellable, BlockEvent):
    """Fired when an interactive block (e.g. chest, crafting table) is clicked."""

    def __init__(self, player: Any, x: int, y: int, z: int, block_key: str) -> None:
        super().__init__(player, x, y, z, block_key)

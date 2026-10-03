"""Central CommandManager for registering, dispatching, and managing server commands."""

import math
from typing import Any, Dict, List, Optional, Set

from .base import Command
from .sender import CommandSender, ConsoleCommandSender, PlayerCommandSender


class CommandManager:
    """Manages command registration, alias mapping, permissions, and dispatching."""

    def __init__(self, server: Any = None) -> None:
        self.server = server
        self._commands: Dict[str, Command] = {}
        self._aliases: Dict[str, Command] = {}
        if server is not None:
            self._register_default_commands()

    def register_command(self, command: Command, plugin: Any = None) -> bool:
        """Registers a command and all its aliases."""
        name = command.name.lower()
        if not name:
            return False

        command.plugin = plugin
        self._commands[name] = command

        for alias in command.aliases:
            alias_lower = alias.lower()
            self._aliases[alias_lower] = command

        return True

    def unregister_command(self, name: str) -> bool:
        """Unregisters a command by name and cleans up aliases."""
        name_lower = name.lower()
        cmd = self._commands.pop(name_lower, None)
        if cmd is None:
            cmd = self._aliases.pop(name_lower, None)

        if cmd is not None:
            # Clean up all alias mappings pointing to this command
            aliases_to_remove = [
                a for a, c in self._aliases.items() if c is cmd or a == name_lower
            ]
            for a in aliases_to_remove:
                self._aliases.pop(a, None)
            return True

        return False

    def unregister_by_plugin(self, plugin: Any) -> int:
        """Unregisters all commands associated with a given plugin."""
        removed = 0
        cmds_to_remove = [
            cmd for cmd in self._commands.values() if cmd.plugin is plugin
        ]
        for cmd in cmds_to_remove:
            self.unregister_command(cmd.name)
            removed += 1
        return removed

    def get_command(self, name: str) -> Optional[Command]:
        """Resolves a command by its primary name or alias."""
        key = name.lower()
        return self._commands.get(key) or self._aliases.get(key)

    def get_all_commands(self) -> List[Command]:
        """Returns unique list of all registered commands."""
        seen: Set[Command] = set()
        result: List[Command] = []
        for cmd in list(self._commands.values()) + list(self._aliases.values()):
            if cmd not in seen:
                seen.add(cmd)
                result.append(cmd)
        return result

    def dispatch(self, sender: CommandSender, command_line: str) -> bool:
        """Parses, checks permissions, and dispatches a command line."""
        line = command_line.strip()
        if not line:
            return False

        if line.startswith(("/", "!")):
            line = line[1:].strip()

        if not line:
            return False

        parts = line.split()
        label = parts[0].lower()
        args = parts[1:]

        cmd = self.get_command(label)
        if cmd is None:
            sender.send_message(f"§cUnknown command '{label}'. Type /help for help.")
            return False

        if not sender.has_permission(cmd.permission):
            sender.send_message("§cYou do not have permission to use this command.")
            return False

        try:
            success = cmd.execute(sender, args)
            if not success:
                sender.send_message(f"§cUsage: {cmd.usage}")
                return False
            return True
        except Exception as e:
            print(f"[ERROR] [Command] Exception while executing '/{label}': {e!r}")
            sender.send_message("§cAn internal error occurred while executing this command.")
            return False

    def _register_default_commands(self) -> None:
        """Registers default built-in Pywer commands."""
        mgr = self

        class HelpCommand(Command):
            def __init__(self):
                super().__init__(
                    "help",
                    description="Shows help for available commands",
                    usage="/help [page]",
                    aliases=["?"],
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                cmds = sorted(mgr.get_all_commands(), key=lambda c: c.name)
                sender.send_message("§6=== Pywer Available Commands ===")
                for c in cmds:
                    sender.send_message(f"§e/{c.name}§7 - {c.description or 'No description'}")
                return True

        class PluginsCommand(Command):
            def __init__(self):
                super().__init__(
                    "plugins",
                    description="Lists loaded server plugins",
                    usage="/plugins",
                    aliases=["pl"],
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                if mgr.server and hasattr(mgr.server, "plugin_mgr"):
                    pl_list = mgr.server.plugin_mgr.plugins
                    names = [f"§a{p.name} v{p.version}§r" for p in pl_list.values()]
                    sender.send_message(f"Plugins ({len(pl_list)}): {', '.join(names) if names else 'None'}")
                else:
                    sender.send_message("Plugins (0): None")
                return True

        class VersionCommand(Command):
            def __init__(self):
                super().__init__(
                    "version",
                    description="Displays server version info",
                    usage="/version",
                    aliases=["ver", "about"],
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                sender.send_message("§aPywer Server v0.9.1 (Bedrock Protocol 766, v1.21.50)")
                return True

        class PosCommand(Command):
            def __init__(self):
                super().__init__(
                    "pos",
                    description="Shows current coordinates",
                    usage="/pos",
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                if not sender.is_player:
                    sender.send_message("Only players can check position.")
                    return True
                p = getattr(sender, "player", None)
                if p:
                    f = p.feet()
                    sender.send_message(
                        "pos %.2f %.2f %.2f yaw %.1f pitch %.1f ground=%s fall=%.1f"
                        % (f + (p.yaw, p.pitch, p.on_ground, p.fall_distance))
                    )
                return True

        class BlocksCommand(Command):
            def __init__(self):
                super().__init__(
                    "blocks",
                    description="Lists available blocks",
                    usage="/blocks",
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                try:
                    from ..world.palette import BLOCK_KEYS
                    sender.send_message("blocks: " + ", ".join(BLOCK_KEYS[1:]))
                except Exception as e:
                    sender.send_message(f"Error listing blocks: {e}")
                return True

        class ItemsCommand(Command):
            def __init__(self):
                super().__init__(
                    "items",
                    description="Lists available items",
                    usage="/items",
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                try:
                    from ..player.inventory import ITEM_RUNTIME
                    sender.send_message(
                        "items: "
                        + ", ".join(
                            sorted(
                                k
                                for k in ITEM_RUNTIME
                                if k not in ("air", "water", "bedrock")
                            )
                        )
                    )
                except Exception as e:
                    sender.send_message(f"Error listing items: {e}")
                return True

        class ToolsCommand(Command):
            def __init__(self):
                super().__init__(
                    "tools",
                    description="Gives starter tools",
                    usage="/tools",
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                if not sender.is_player or not mgr.server:
                    sender.send_message("Only players can use /tools.")
                    return True
                p = getattr(sender, "player", None)
                if p and hasattr(mgr.server, "give_tools"):
                    mgr.server.give_tools(p)
                return True

        class GiveCommand(Command):
            def __init__(self):
                super().__init__(
                    "give",
                    description="Gives item to player",
                    usage="/give <item> [amount] [slot]",
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                if not sender.is_player or not mgr.server:
                    sender.send_message("Only players can use /give.")
                    return True
                if not args:
                    return False
                p = getattr(sender, "player", None)
                if p and hasattr(mgr.server, "give"):
                    count = int(args[1]) if len(args) > 1 else 1
                    slot = int(args[2]) if len(args) > 2 else None
                    mgr.server.give(p, args[0], count, slot)
                return True

        class InvCommand(Command):
            def __init__(self):
                super().__init__(
                    "inv",
                    description="Shows current inventory",
                    usage="/inv",
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                if not sender.is_player:
                    sender.send_message("Only players can use /inv.")
                    return True
                p = getattr(sender, "player", None)
                if p:
                    from ..player.inventory import ITEM_NAME
                    sender.send_message(
                        "inv: "
                        + " ".join(
                            "%d:%s x%d" % (i, ITEM_NAME.get(s[0], s[0]), s[1])
                            for i, s in enumerate(p.inventory)
                            if s[1]
                        )
                    )
                return True

        class SetBlockCommand(Command):
            def __init__(self):
                super().__init__(
                    "setblock",
                    description="Sets block at coordinates",
                    usage="/setblock <x> <y> <z> <block>",
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                if len(args) < 4 or not mgr.server:
                    return False
                p = getattr(sender, "player", None)
                px = p.pos[0] if p else 0.0
                py = (p.pos[1] - 1.62) if p else 0.0
                pz = p.pos[2] if p else 0.0

                def co(v, cur):
                    return math.floor(cur) + int(v[1:] or 0) if v.startswith("~") else int(v)

                try:
                    x = co(args[0], px)
                    y = co(args[1], py)
                    z = co(args[2], pz)
                    ok = mgr.server.set_block(x, y, z, args[3])
                    sender.send_message(f"setblock {x} {y} {z} {args[3]} {'ok' if ok else 'out of range'}")
                except Exception as e:
                    sender.send_message(f"§cBad coordinates or block: {e}")
                return True

        class TeleportCommand(Command):
            def __init__(self):
                super().__init__(
                    "tp",
                    description="Teleports player to coordinates",
                    usage="/tp <x> <y> <z>",
                    aliases=["teleport"],
                )

            def execute(self, sender: CommandSender, args: List[str]) -> bool:
                if not sender.is_player:
                    sender.send_message("Only players can use /tp.")
                    return True
                if len(args) < 3:
                    return False
                p = getattr(sender, "player", None)
                if p:
                    f = p.feet()
                    t = [
                        (f[i] + float(v[1:] or 0)) if v.startswith("~") else float(v)
                        for i, v in enumerate(args[:3])
                    ]
                    p.teleport(*t)
                    sender.send_message("teleported to %.1f %.1f %.1f" % tuple(t))
                return True

        self.register_command(HelpCommand())
        self.register_command(PluginsCommand())
        self.register_command(VersionCommand())
        self.register_command(PosCommand())
        self.register_command(BlocksCommand())
        self.register_command(ItemsCommand())
        self.register_command(ToolsCommand())
        self.register_command(GiveCommand())
        self.register_command(InvCommand())
        self.register_command(SetBlockCommand())
        self.register_command(TeleportCommand())

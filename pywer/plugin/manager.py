"""PluginManager handles scanning, topological dependency loading, lifecycle, and auto-cleanup."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from ..event.server import PluginDisableEvent, PluginEnableEvent
from .base import PluginBase
from .compiler import PluginCompiler
from .loader import VirtualPluginLoader


class PluginManager:
    """Manages the full lifecycle of plugins, dependency resolution, and state isolation."""

    def __init__(
        self,
        server: Any,
        plugins_dir: Union[str, Path],
        data_dir: Union[str, Path],
    ) -> None:
        self.server = server
        self.plugins_dir = Path(plugins_dir).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.plugins: Dict[str, PluginBase] = {}
        self._plugin_paths: Dict[str, Path] = {}

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """Retrieves a loaded plugin instance by its registered name."""
        return self.plugins.get(name)

    def load_all_plugins(self) -> List[PluginBase]:
        """Discovers, topologically sorts, and virtually loads all .pywer packages."""
        if not self.plugins_dir.exists():
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            return []

        # 1. Discover all .pywer packages and inspect manifests
        discovered: Dict[str, Dict[str, Any]] = {}
        file_map: Dict[str, Path] = {}

        for pkg_file in self.plugins_dir.glob("*.pywer"):
            try:
                manifest_data = PluginCompiler.inspect(pkg_file)
                name = manifest_data["name"]
                discovered[name] = manifest_data
                file_map[name] = pkg_file
            except Exception as e:
                print(f"[ERROR] [Plugin] Failed to read package '{pkg_file.name}': {e}")

        # 2. Dependency resolution using Topological Sort (DFS)
        load_order: List[str] = []
        visited: Set[str] = set()
        visiting: Set[str] = set()

        def visit(p_name: str) -> None:
            if p_name in visiting:
                print(f"[WARN] [Plugin] Circular dependency detected involving '{p_name}'.")
                return
            if p_name not in visited:
                visiting.add(p_name)
                deps = discovered[p_name].get("dependencies", [])
                for dep in deps:
                    if dep in discovered:
                        visit(dep)
                    else:
                        print(
                            f"[WARN] [Plugin] Plugin '{p_name}' depends on '{dep}', but '{dep}' is missing!"
                        )
                visiting.remove(p_name)
                visited.add(p_name)
                load_order.append(p_name)

        for p_name in list(discovered.keys()):
            if p_name not in visited:
                visit(p_name)

        # 3. Virtual load each plugin in dependency order
        loaded: List[PluginBase] = []
        for p_name in load_order:
            pkg_path = file_map[p_name]
            try:
                plugin = VirtualPluginLoader.load_plugin(
                    pkg_path, self.server, self.data_dir
                )
                self.plugins[p_name] = plugin
                self._plugin_paths[p_name] = pkg_path
                loaded.append(plugin)
                print(f"[INFO] [Plugin] Loaded '{plugin.name}' v{plugin.version}.")
            except Exception as e:
                print(f"[ERROR] [Plugin] Failed to load plugin '{p_name}': {e}")

        return loaded

    def enable_plugin(self, plugin: PluginBase) -> bool:
        """Enables a loaded plugin and dispatches PluginEnableEvent."""
        if plugin.is_enabled:
            return True

        plugin._is_enabled = True

        try:
            plugin.on_enable()
        except Exception as e:
            plugin.logger.error(f"Exception during on_enable(): {e!r}")

        # Dispatch enable event
        if hasattr(self.server, "event_manager") and self.server.event_manager:
            self.server.event_manager.call(PluginEnableEvent(plugin))

        return True

    def disable_plugin(self, plugin: PluginBase) -> bool:
        """Disables a plugin, cleans up events, commands, and scheduler tasks."""
        if not plugin.is_enabled:
            return True

        # Dispatch disable event first
        if hasattr(self.server, "event_manager") and self.server.event_manager:
            self.server.event_manager.call(PluginDisableEvent(plugin))

        try:
            plugin.on_disable()
        except Exception as e:
            plugin.logger.error(f"Exception during on_disable(): {e!r}")

        # Comprehensive auto-cleanup:
        # 1. Unregister event listeners
        if hasattr(self.server, "event_manager") and self.server.event_manager:
            self.server.event_manager.unregister_by_plugin(plugin)

        # 2. Unregister commands
        if hasattr(self.server, "command_manager") and self.server.command_manager:
            self.server.command_manager.unregister_by_plugin(plugin)

        # 3. Cancel scheduled tasks
        if hasattr(self.server, "scheduler") and self.server.scheduler:
            self.server.scheduler.cancel_by_plugin(plugin)

        plugin._is_enabled = False
        return True

    def reload_plugin(self, name: str) -> Optional[PluginBase]:
        """Safely disables, reloads virtual modules from .pywer, and re-enables a plugin."""
        plugin = self.plugins.get(name)
        pkg_path = self._plugin_paths.get(name)
        if not plugin or not pkg_path:
            return None

        self.disable_plugin(plugin)

        try:
            new_plugin = VirtualPluginLoader.load_plugin(
                pkg_path, self.server, self.data_dir
            )
            self.plugins[name] = new_plugin
            self.enable_plugin(new_plugin)
            print(f"[INFO] [Plugin] Reloaded '{name}' v{new_plugin.version}.")
            return new_plugin
        except Exception as e:
            print(f"[ERROR] [Plugin] Failed to reload plugin '{name}': {e}")
            return None

    def enable_all(self) -> None:
        """Enables all loaded plugins in load order."""
        for plugin in list(self.plugins.values()):
            self.enable_plugin(plugin)

    def disable_all(self) -> None:
        """Disables all plugins in reverse dependency order."""
        for plugin in reversed(list(self.plugins.values())):
            self.disable_plugin(plugin)

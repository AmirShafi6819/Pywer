"""Base classes, interfaces, and configurations for Pywer plugins."""

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class PluginManifest:
    """Parsed metadata from a plugin's plugin.json manifest."""

    name: str
    version: str
    main: str
    api_version: str
    author: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    soft_dependencies: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        return cls(
            name=str(data["name"]),
            version=str(data.get("version", "1.0.0")),
            main=str(data["main"]),
            api_version=str(data.get("api_version", "1.0.0")),
            author=data.get("author"),
            description=data.get("description"),
            website=data.get("website"),
            dependencies=list(data.get("dependencies", [])),
            soft_dependencies=list(data.get("soft_dependencies", [])),
        )


class PluginLogger:
    """Logger scoped to a specific plugin instance."""

    def __init__(self, plugin_name: str) -> None:
        self.plugin_name = plugin_name

    def _format(self, level: str, msg: str) -> str:
        return f"[{level}] [{self.plugin_name}] {msg}"

    def info(self, msg: str) -> None:
        print(self._format("INFO", msg))

    def warning(self, msg: str) -> None:
        print(self._format("WARN", msg))

    def error(self, msg: str) -> None:
        print(self._format("ERROR", msg))

    def debug(self, msg: str) -> None:
        print(self._format("DEBUG", msg))


class PluginConfig:
    """Persistent JSON configuration wrapper for a plugin."""

    def __init__(
        self, config_file: Union[str, Path], defaults: Optional[Dict[str, Any]] = None
    ) -> None:
        self.config_path = Path(config_file).resolve()
        self._data: Dict[str, Any] = dict(defaults or {})
        if self.config_path.exists():
            self.reload()
        elif defaults:
            self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def as_dict(self) -> Dict[str, Any]:
        return dict(self._data)

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def reload(self) -> None:
        if self.config_path.is_file():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self._data.update(loaded)
            except Exception as e:
                print(f"[WARN] Failed to read config at {self.config_path}: {e}")


class PluginBase:
    """Abstract base class that all Pywer plugins must inherit from."""

    def __init__(self) -> None:
        self._manifest: Optional[PluginManifest] = None
        self._server: Any = None
        self._data_folder: Optional[Path] = None
        self._logger: Optional[PluginLogger] = None
        self._config: Optional[PluginConfig] = None
        self._package_path: Optional[Path] = None
        self._is_enabled: bool = False

    @property
    def manifest(self) -> PluginManifest:
        if self._manifest is None:
            raise RuntimeError("Plugin manifest has not been injected.")
        return self._manifest

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def server(self) -> Any:
        return self._server

    @property
    def data_folder(self) -> Path:
        if self._data_folder is None:
            raise RuntimeError("Plugin data_folder has not been configured.")
        return self._data_folder

    @property
    def logger(self) -> PluginLogger:
        if self._logger is None:
            self._logger = PluginLogger(self.name if self._manifest else "Plugin")
        return self._logger

    @property
    def config(self) -> PluginConfig:
        if self._config is None:
            cfg_file = self.data_folder / "config.json"
            self._config = PluginConfig(cfg_file)
        return self._config

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    def on_load(self) -> None:
        """Called immediately after plugin class instantiation."""
        pass

    def on_enable(self) -> None:
        """Called when server enables the plugin."""
        pass

    def on_disable(self) -> None:
        """Called when server disables the plugin or shuts down."""
        pass

    def get_resource(self, filename: str) -> Optional[bytes]:
        """Reads a bundled resource file directly from the .pywer package without disk extraction."""
        if not self._package_path or not self._package_path.is_file():
            return None
        norm_name = filename.replace("\\", "/").lstrip("/")
        try:
            with zipfile.ZipFile(self._package_path, "r") as zf:
                if norm_name in zf.namelist():
                    return zf.read(norm_name)
        except Exception:
            return None
        return None

    def register_listener(self, listener: Any) -> None:
        """Helper to register an event listener scoped to this plugin."""
        if self._server and hasattr(self._server, "event_manager") and self._server.event_manager:
            self._server.event_manager.register_listener(listener, plugin=self)

    def register_command(self, command: Any) -> None:
        """Helper to register a command scoped to this plugin."""
        if self._server and hasattr(self._server, "command_manager") and self._server.command_manager:
            self._server.command_manager.register_command(command, plugin=self)

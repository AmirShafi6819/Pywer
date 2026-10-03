"""Virtual in-memory plugin loader and module importer for .pywer zip packages."""

import importlib
import importlib.abc
import sys
import types
import zipfile
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Union

from .base import PluginBase, PluginConfig, PluginLogger, PluginManifest
from .compiler import PluginCompileError, PluginCompiler


class PywerZipLoader(importlib.abc.InspectLoader):
    """Loads Python code directly from an in-memory or archive .pywer package without extracting to disk."""

    def __init__(self, zip_path: Path, zip_subpath: str, is_pkg: bool) -> None:
        self.zip_path = Path(zip_path).resolve()
        self.zip_subpath = zip_subpath.replace("\\", "/")
        self.is_pkg = is_pkg

    def is_package(self, fullname: str) -> bool:
        return self.is_pkg

    def get_source(self, fullname: str) -> Optional[str]:
        if not self.zip_subpath:
            return ""
        try:
            with zipfile.ZipFile(self.zip_path, "r") as zf:
                if self.zip_subpath in zf.namelist():
                    return zf.read(self.zip_subpath).decode("utf-8")
        except Exception as e:
            raise ImportError(f"Failed to read source for '{fullname}' from zip: {e}") from e
        return None

    def get_code(self, fullname: str) -> Optional[types.CodeType]:
        source = self.get_source(fullname)
        if source is None:
            return None
        filename = (
            f"{self.zip_path}!/{self.zip_subpath}"
            if self.zip_subpath
            else f"{self.zip_path}!/"
        )
        return compile(source, filename, "exec")

    def exec_module(self, module: types.ModuleType) -> None:
        module.__file__ = (
            f"{self.zip_path}!/{self.zip_subpath}"
            if self.zip_subpath
            else f"{self.zip_path}!/"
        )
        if self.is_pkg:
            module.__path__ = [module.__file__]
        code = self.get_code(module.__name__)
        if code is not None:
            exec(code, module.__dict__)


class PywerZipFinder(importlib.abc.MetaPathFinder):
    """Meta-path finder that intercepts import requests for virtual plugin namespaces."""

    def __init__(self, prefix: str, zip_path: Path) -> None:
        self.prefix = prefix
        self.zip_path = Path(zip_path).resolve()
        try:
            with zipfile.ZipFile(self.zip_path, "r") as zf:
                self._namelist = set(zf.namelist())
        except Exception as e:
            self._namelist = set()

    def find_spec(
        self,
        fullname: str,
        path: Optional[Sequence[str]] = None,
        target: Optional[types.ModuleType] = None,
    ) -> Optional[ModuleSpec]:
        if fullname == "_pywer_plugins":
            loader = PywerZipLoader(self.zip_path, "", is_pkg=True)
            spec = ModuleSpec(fullname, loader, is_package=True)
            spec.submodule_search_locations = []
            return spec

        if fullname == self.prefix:
            has_init = "__init__.py" in self._namelist
            subpath = "__init__.py" if has_init else ""
            loader = PywerZipLoader(self.zip_path, subpath, is_pkg=True)
            spec = ModuleSpec(fullname, loader, is_package=True)
            spec.submodule_search_locations = [f"{self.zip_path}!/"]
            return spec

        if fullname.startswith(self.prefix + "."):
            rel_name = fullname[len(self.prefix) + 1 :]
            parts = rel_name.split(".")
            file_candidate = "/".join(parts) + ".py"
            pkg_candidate = "/".join(parts) + "/__init__.py"

            if pkg_candidate in self._namelist:
                loader = PywerZipLoader(self.zip_path, pkg_candidate, is_pkg=True)
                spec = ModuleSpec(fullname, loader, is_package=True)
                spec.submodule_search_locations = [
                    f"{self.zip_path}!/{'/'.join(parts)}"
                ]
                return spec
            elif file_candidate in self._namelist:
                loader = PywerZipLoader(self.zip_path, file_candidate, is_pkg=False)
                spec = ModuleSpec(fullname, loader, is_package=False)
                return spec

        return None


class VirtualPluginLoader:
    """Manages virtual in-memory loading and lifecycle initialization of .pywer packages."""

    _registered_finders: Dict[str, PywerZipFinder] = {}

    @classmethod
    def load_plugin(
        cls,
        pywer_path: Union[str, Path],
        server: Any,
        data_root: Union[str, Path],
    ) -> PluginBase:
        pkg_path = Path(pywer_path).resolve()
        if not pkg_path.is_file():
            raise PluginCompileError(f"Plugin package not found: {pkg_path}")

        manifest_data = PluginCompiler.inspect(pkg_path)
        manifest = PluginManifest.from_dict(manifest_data)

        # Isolated namespace prefix
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in manifest.name)
        prefix = f"_pywer_plugins.{safe_name}"

        # Clean up any existing finder/modules for reload safety
        if prefix in cls._registered_finders:
            old_finder = cls._registered_finders.pop(prefix)
            if old_finder in sys.meta_path:
                sys.meta_path.remove(old_finder)

        # Clean sys.modules under prefix
        to_del = [m for m in sys.modules if m == prefix or m.startswith(prefix + ".")]
        for m in to_del:
            sys.modules.pop(m, None)

        if "_pywer_plugins" not in sys.modules:
            root_pkg = types.ModuleType("_pywer_plugins")
            root_pkg.__path__ = []
            sys.modules["_pywer_plugins"] = root_pkg

        finder = PywerZipFinder(prefix, pkg_path)
        cls._registered_finders[prefix] = finder
        sys.meta_path.insert(0, finder)
        importlib.invalidate_caches()

        # Parse entry point
        if ":" not in manifest.main:
            raise PluginCompileError(
                f"Invalid manifest 'main' format '{manifest.main}', expected 'module:ClassName'."
            )
        mod_part, cls_part = manifest.main.split(":", 1)
        full_mod = f"{prefix}.{mod_part}"

        try:
            module = importlib.import_module(full_mod)
        except Exception as e:
            raise ImportError(
                f"Failed to virtually import plugin main module '{full_mod}': {e}"
            ) from e

        plugin_cls = getattr(module, cls_part, None)
        if plugin_cls is None:
            raise AttributeError(
                f"Plugin class '{cls_part}' not found in module '{full_mod}'."
            )
        if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, PluginBase)):
            raise TypeError(
                f"Plugin class '{cls_part}' must inherit from pywer.plugin.base.PluginBase."
            )

        # Instantiate and configure
        data_folder = Path(data_root) / manifest.name
        data_folder.mkdir(parents=True, exist_ok=True)

        plugin: PluginBase = plugin_cls()
        plugin._manifest = manifest
        plugin._server = server
        plugin._package_path = pkg_path
        plugin._data_folder = data_folder
        plugin._logger = PluginLogger(manifest.name)
        plugin._config = PluginConfig(data_folder / "config.json")

        plugin.on_load()
        return plugin

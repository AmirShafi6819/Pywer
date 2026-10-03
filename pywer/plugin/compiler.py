"""Pywer plugin compiler and packaging tooling.

Performs static AST validation and packages plugins into distributable .pywer zip archives.
"""

import ast
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional, Union


class PluginCompileError(Exception):
    """Raised when plugin packaging or AST verification encounters an error."""
    pass


class PluginCompiler:
    """Validates source directory and packages plugin into a .pywer archive."""

    REQUIRED_FIELDS = ("name", "version", "main", "api_version")
    IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".idea", ".vscode"}
    IGNORED_EXTS = {".pyc", ".pyo", ".pyd"}

    @classmethod
    def validate_source_dir(cls, source_dir: Union[str, Path]) -> Dict[str, Any]:
        """Performs static checks on the plugin manifest and all Python source files."""
        source_path = Path(source_dir).resolve()
        if not source_path.is_dir():
            raise PluginCompileError(f"Plugin source path is not a directory: {source_path}")

        manifest_file = source_path / "plugin.json"
        if not manifest_file.is_file():
            raise PluginCompileError(
                f"Missing required 'plugin.json' manifest in {source_path}"
            )

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            raise PluginCompileError(f"Failed to parse 'plugin.json': {e}") from e

        if not isinstance(manifest, dict):
            raise PluginCompileError("'plugin.json' must contain a JSON object.")

        for req in cls.REQUIRED_FIELDS:
            if req not in manifest or not manifest[req]:
                raise PluginCompileError(f"Missing required field '{req}' in 'plugin.json'.")

        # Validate main entrypoint format (module:Class)
        main_entry = manifest["main"]
        if not isinstance(main_entry, str) or ":" not in main_entry:
            raise PluginCompileError(
                f"Field 'main' must be in format 'module_name:ClassName', got '{main_entry}'."
            )

        # Static AST validation for all .py files
        for root, dirs, files in os.walk(source_path):
            dirs[:] = [d for d in dirs if d not in cls.IGNORED_DIRS]
            for file in files:
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(source_path).as_posix()
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        ast.parse(content, filename=rel_path)
                    except SyntaxError as se:
                        raise PluginCompileError(
                            f"Syntax error in '{rel_path}' at line {se.lineno}, col {se.offset}: {se.msg}"
                        ) from se
                    except Exception as e:
                        raise PluginCompileError(
                            f"Error reading/parsing '{rel_path}': {e}"
                        ) from e

        return manifest

    @classmethod
    def pack(
        cls,
        source_dir: Union[str, Path],
        output_file: Optional[Union[str, Path]] = None,
    ) -> Path:
        """Validates source and creates a .pywer package."""
        source_path = Path(source_dir).resolve()
        manifest = cls.validate_source_dir(source_path)

        if output_file is None:
            out_path = source_path.parent / f"{manifest['name']}.pywer"
        else:
            out_path = Path(output_file).resolve()
            if out_path.suffix != ".pywer":
                out_path = out_path.with_suffix(".pywer")

        out_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(source_path):
                dirs[:] = [d for d in dirs if d not in cls.IGNORED_DIRS]
                for file in files:
                    ext = Path(file).suffix.lower()
                    if ext in cls.IGNORED_EXTS:
                        continue
                    full_file = Path(root) / file
                    arcname = full_file.relative_to(source_path).as_posix()
                    zf.write(full_file, arcname=arcname)

        return out_path

    @classmethod
    def inspect(cls, package_path: Union[str, Path]) -> Dict[str, Any]:
        """Inspects and returns the manifest of a .pywer package without disk extraction."""
        pkg_path = Path(package_path).resolve()
        if not pkg_path.is_file():
            raise PluginCompileError(f"Package file not found: {pkg_path}")

        try:
            with zipfile.ZipFile(pkg_path, "r") as zf:
                if "plugin.json" not in zf.namelist():
                    raise PluginCompileError("Package does not contain 'plugin.json'")
                data = zf.read("plugin.json").decode("utf-8")
                manifest = json.loads(data)
                return manifest
        except Exception as e:
            raise PluginCompileError(f"Failed to inspect package '{pkg_path.name}': {e}") from e

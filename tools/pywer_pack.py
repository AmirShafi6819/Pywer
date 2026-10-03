#!/usr/bin/env python3
"""CLI utility to validate and package Pywer plugins into .pywer archives."""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path so it works directly from repo
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pywer.plugin.compiler import PluginCompileError, PluginCompiler


def main():
    parser = argparse.ArgumentParser(
        description="Compile and package a Pywer plugin source folder into a .pywer package."
    )
    parser.add_argument(
        "source",
        type=str,
        help="Path to plugin source directory containing plugin.json",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Target .pywer output filepath (default: <source_parent>/<PluginName>.pywer)",
    )

    args = parser.parse_args()
    source_dir = Path(args.source)

    try:
        print(f"[Pywer Pack] Validating source directory: {source_dir}")
        manifest = PluginCompiler.validate_source_dir(source_dir)
        print(
            f"[Pywer Pack] Manifest valid: {manifest.get('name')} v{manifest.get('version')}"
        )
        print(f"[Pywer Pack] Packaging into .pywer archive...")
        out_path = PluginCompiler.pack(source_dir, args.output)
        print(f"[Pywer Pack] Successfully built package: {out_path}")
    except PluginCompileError as e:
        print(f"[Pywer Pack] [ERROR] Compilation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[Pywer Pack] [FATAL] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

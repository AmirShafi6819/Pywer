#!/usr/bin/env python3
"""
Collect all Python files from a folder (recursively) into a single text file.

Output: pywer.txt
"""

from pathlib import Path


def collect_python_files(source_dir: str, output_file: str = "pywer.txt") -> None:
    """Recursively gather .py files and dump their contents into one file."""
    source = Path(source_dir)

    if not source.is_dir():
        raise NotADirectoryError(f"'{source_dir}' is not a valid directory.")

    py_files = sorted(source.rglob("*.py"))

    if not py_files:
        print(f"No Python files found in '{source_dir}'.")
        return

    with open(output_file, "w", encoding="utf-8") as out:
        for py_file in py_files:
            out.write(f"{'=' * 80}\n")
            out.write(f"# File: {py_file}\n")
            out.write(f"{'=' * 80}\n\n")

            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                content = f"# [Error reading file: {e}]\n"

            out.write(content)
            if not content.endswith("\n"):
                out.write("\n")
            out.write("\n\n")

    print(f"Done! {len(py_files)} Python file(s) written to '{output_file}'.")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    collect_python_files(str(repo_root / "pywer"), str(repo_root / "pywer.txt"))
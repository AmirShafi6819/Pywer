import importlib
import unittest
from pathlib import Path


class TestImports(unittest.TestCase):
    def test_all_modules_importable(self):
        pywer_dir = Path(__file__).resolve().parent.parent / "pywer"
        for py_path in pywer_dir.rglob("*.py"):
            rel = py_path.relative_to(pywer_dir.parent)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts.pop()
            else:
                parts[-1] = parts[-1][:-3]
            mod_name = ".".join(parts)
            try:
                mod = importlib.import_module(mod_name)
                self.assertIsNotNone(mod)
            except Exception as e:
                self.fail(f"Failed to import module {mod_name}: {e}")


if __name__ == "__main__":
    unittest.main()

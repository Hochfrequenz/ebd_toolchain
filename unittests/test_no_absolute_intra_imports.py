"""
Guard against absolute intra-package imports in ebd_toolchain.

The Dockerfile runs main.py directly via `python ebd_toolchain/main.py`, which means
ebd_toolchain's parent directory is NOT on sys.path. Absolute imports like
`from ebd_toolchain.ahb_pruefi import ...` fail with ModuleNotFoundError in Docker.
Relative imports (`from .ahb_pruefi import ...`) work in both contexts.
"""

import ast
from pathlib import Path

_PACKAGE_DIR = Path(__file__).parent.parent / "src" / "ebd_toolchain"


def test_no_absolute_intra_package_imports() -> None:
    """Ensure all intra-package imports use relative syntax."""
    violations: list[str] = []
    for py_file in _PACKAGE_DIR.glob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", None) or ""
                if module.startswith("ebd_toolchain.") or module == "ebd_toolchain":
                    violations.append(f"{py_file.name}:{node.lineno} — `{ast.dump(node)}` should use a relative import")

    assert not violations, (
        "Absolute intra-package imports break the Docker build "
        "(main.py is run directly, so ebd_toolchain's parent is not on sys.path).\n"
        "Use relative imports instead (e.g. `from .ahb_pruefi import ...`).\n\n" + "\n".join(violations)
    )

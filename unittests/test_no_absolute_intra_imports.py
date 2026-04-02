"""
Guard: the Dockerfile must set PYTHONPATH=/app.

The Dockerfile runs `python ebd_toolchain/main.py` directly, which adds
/app/ebd_toolchain/ to sys.path but NOT /app/. Without PYTHONPATH=/app,
absolute intra-package imports like `from ebd_toolchain.ahb_pruefi import ...`
fail with ModuleNotFoundError. Relative imports also fail because the script
runs as __main__ with no parent package context.
"""

from pathlib import Path


def test_dockerfile_has_pythonpath() -> None:
    """Ensure Dockerfile sets PYTHONPATH so intra-package imports work."""
    dockerfile = Path(__file__).parent.parent / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")
    assert "PYTHONPATH" in content, (
        "Dockerfile must set ENV PYTHONPATH=/app so that "
        "`from ebd_toolchain.ahb_pruefi import ...` works when main.py is run directly."
    )

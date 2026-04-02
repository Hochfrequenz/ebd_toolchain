"""
Guard: the Dockerfile must set PYTHONPATH=/app.

The Dockerfile runs `python ebd_toolchain/main.py` directly. Python adds the script's
directory (/app/ebd_toolchain/) to sys.path but NOT /app/. This means:
  - Absolute imports (`from ebd_toolchain.ahb_pruefi ...`) -> ModuleNotFoundError
  - Relative imports (`from .ahb_pruefi ...`) -> ImportError (no parent package)
Setting ENV PYTHONPATH=/app in the Dockerfile fixes the absolute import case.
"""

from pathlib import Path


def test_dockerfile_has_pythonpath() -> None:
    """Ensure Dockerfile sets PYTHONPATH so intra-package imports work."""
    dockerfile = Path(__file__).parent.parent / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")
    assert "ENV PYTHONPATH=/app" in content, (
        "Dockerfile must set ENV PYTHONPATH=/app so that "
        "`from ebd_toolchain.ahb_pruefi import ...` works when main.py is run as a script."
    )

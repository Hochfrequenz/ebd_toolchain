"""
tests the main script
"""

from pathlib import Path
from typing import Literal

import pytest
from _pytest.monkeypatch import MonkeyPatch

from ebd_toolchain.main import _main

repo_root = Path(__file__).parent.parent
recent_docx_file = (
    repo_root
    / "edi_energy_mirror"
    / "edi_energy_de"
    / "FV2504"
    / "Entscheidungsbaum-DiagrammeundCodelisten-informatorischeLesefassung4.0a_99991231_20250404.docx"
)
assert recent_docx_file.exists()


@pytest.mark.parametrize(
    "input_path, export_types", [pytest.param(recent_docx_file, ["puml", "dot", "json", "svg"], id="recent call")]
)
def test_main(
    input_path: Path,
    export_types: list[Literal["puml", "dot", "json", "svg"]],
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("KROKI_PORT", "8000")
    monkeypatch.setenv("KROKI_HOST", "localhost")
    # if you run into ConnectionErrors use
    # docker-compose up -d
    # in the repo root
    _main(input_path, tmp_path, export_types)
    # we don't assert on the results but instead just check that it doesn't crash

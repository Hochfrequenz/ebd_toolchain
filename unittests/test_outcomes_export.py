"""
tests the export of the outcomes (``<ebd_key>.outcomes.json`` and ``ebd_outcomes.schema.json``);
neither needs the edi_energy_mirror submodule nor a kroki instance
"""

import json
from pathlib import Path
from typing import Any, Literal

from pytest import CaptureFixture, MonkeyPatch
from rebdhuhn import EbdOutcomes
from rebdhuhn.graph_conversion import convert_table_to_graph

import ebd_toolchain.main
from ebd_toolchain.main import _dump_outcomes, _main, _outcomes_schema_text
from unittests.scraping_stubs import TWO_STEP_TABLE, WITH_TABLE, WITHOUT_TABLE


def test_dump_outcomes(tmp_path: Path) -> None:
    outcomes_path = tmp_path / "E_0003.outcomes.json"
    _dump_outcomes(outcomes_path, convert_table_to_graph(TWO_STEP_TABLE))
    text = outcomes_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    json.loads(text)  # must be valid json
    outcomes = EbdOutcomes.model_validate_json(text)
    result_codes = {outcome.result_code for outcome in outcomes.outcomes}
    assert {"A01", "A02"} <= result_codes


def test_outcomes_schema_text() -> None:
    schema = json.loads(_outcomes_schema_text())
    assert schema["title"] == "EbdOutcomes"


def test_main_writes_outcomes_only_for_ebds_with_table(patched_scraping: Path) -> None:
    export_types: list[Literal["puml", "dot", "json", "svg"]] = ["json", "dot"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    outcomes_files = sorted(path.name for path in patched_scraping.glob("*.outcomes.json"))
    assert outcomes_files == [f"{WITH_TABLE}.outcomes.json"]
    EbdOutcomes.model_validate_json((patched_scraping / f"{WITH_TABLE}.outcomes.json").read_text(encoding="utf-8"))
    assert (patched_scraping / f"{WITHOUT_TABLE}.json").exists()
    assert json.loads((patched_scraping / "ebd_outcomes.schema.json").read_text(encoding="utf-8"))["title"] == (
        "EbdOutcomes"
    )


def test_main_outcomes_failure_is_a_warning_only(
    patched_scraping: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise ValueError("boom")

    monkeypatch.setattr(ebd_toolchain.main, "_dump_outcomes", _fail)
    export_types: list[Literal["puml", "dot", "json", "svg"]] = ["json", "dot"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    assert (patched_scraping / f"{WITH_TABLE}.dot").exists()
    assert not list(patched_scraping.glob("*.outcomes.json"))
    stdout = capsys.readouterr().out
    summary = json.loads(stdout[stdout.rindex("{") : stdout.rindex("}") + 1])
    assert summary == {"[WARNING:outcomes_export] ValueError": [WITH_TABLE]}


def test_main_without_json_writes_no_outcomes(patched_scraping: Path) -> None:
    export_types: list[Literal["puml", "dot", "json", "svg"]] = ["dot"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    assert (patched_scraping / f"{WITH_TABLE}.dot").exists()
    assert not list(patched_scraping.glob("*.outcomes.json"))
    assert not (patched_scraping / "ebd_outcomes.schema.json").exists()

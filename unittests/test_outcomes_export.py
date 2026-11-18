"""
tests the export of the outcomes (``<ebd_key>.outcomes.json`` and ``ebd_outcomes.schema.json``);
neither needs the edi_energy_mirror submodule nor a kroki instance
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import pytest
from ebdamame import EbdNoTableSection
from pytest import CaptureFixture, MonkeyPatch
from rebdhuhn import EbdOutcomes
from rebdhuhn.graph_conversion import convert_table_to_graph
from rebdhuhn.models import EbdCheckResult, EbdTable, EbdTableMetaData, EbdTableRow, EbdTableSubRow

import ebd_toolchain.main
from ebd_toolchain.main import _dump_outcomes, _main, _outcomes_schema_text

_two_step_table = EbdTable(
    metadata=EbdTableMetaData(
        ebd_code="E_0003",
        chapter="7.39 AD: Bestellung der Aggregationsebene",
        section="7.39.1 E_0003_Bestellung der Aggregationsebene RZ prüfen",
        ebd_name="E_0003_Bestellung der Aggregationsebene RZ prüfen",
        role="ÜNB",
    ),
    rows=[
        EbdTableRow(
            step_number="1",
            description="Erfolgt der Eingang der Bestellung fristgerecht?",
            sub_rows=[
                EbdTableSubRow(
                    check_result=EbdCheckResult(result=False, subsequent_step_number=None),
                    result_code="A01",
                    note="Fristüberschreitung",
                ),
                EbdTableSubRow(
                    check_result=EbdCheckResult(result=True, subsequent_step_number="2"),
                    result_code=None,
                    note=None,
                ),
            ],
        ),
        EbdTableRow(
            step_number="2",
            description="Erfolgt die Bestellung zum Monatsersten 00:00 Uhr?",
            sub_rows=[
                EbdTableSubRow(
                    check_result=EbdCheckResult(result=False, subsequent_step_number=None),
                    result_code="A02",
                    note="Gewählter Zeitpunkt nicht zulässig",
                ),
                EbdTableSubRow(
                    check_result=EbdCheckResult(result=True, subsequent_step_number="Ende"),
                    result_code=None,
                    note=None,
                ),
            ],
        ),
    ],
)


def test_dump_outcomes(tmp_path: Path) -> None:
    outcomes_path = tmp_path / "E_0003.outcomes.json"
    _dump_outcomes(outcomes_path, convert_table_to_graph(_two_step_table))
    text = outcomes_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    json.loads(text)  # must be valid json
    outcomes = EbdOutcomes.model_validate_json(text)
    result_codes = {outcome.result_code for outcome in outcomes.outcomes}
    assert {"A01", "A02"} <= result_codes


def test_outcomes_schema_text() -> None:
    schema = json.loads(_outcomes_schema_text())
    assert schema["title"] == "EbdOutcomes"


_WITH_TABLE = "E_0003"
_WITHOUT_TABLE = "E_9999"


@pytest.fixture(name="patched_scraping")
def _patched_scraping(monkeypatch: MonkeyPatch, tmp_path: Path) -> Path:
    """lets _main process one EBD with a table and one without, without a docx file and without kroki"""
    kapitel = SimpleNamespace(
        subsection_title="sub", chapter_title="chapter", chapter=1, section=2, subsection=3, section_title="section"
    )
    monkeypatch.setenv("KROKI_HOST", "localhost")
    monkeypatch.setenv("KROKI_PORT", "8000")
    # an env variable overrides a token in a developer's .env; the empty string becomes None -> no AHB download
    monkeypatch.setenv("GITHUB_TOKEN", "")

    def _no_download(*_: Any, **__: Any) -> None:
        raise AssertionError("the AHB database must not be downloaded in these tests")

    monkeypatch.setattr(ebd_toolchain.main, "download_ahb_db", _no_download)
    monkeypatch.setattr(
        ebd_toolchain.main,
        "get_all_ebd_keys",
        lambda _: {_WITH_TABLE: ("title", kapitel), _WITHOUT_TABLE: ("title", kapitel)},
    )

    def _get_tables(docx_file_path: Path, ebd_key: str) -> Any:  # pylint:disable=unused-argument
        return EbdNoTableSection(ebd_key=ebd_key, remark="no table") if ebd_key == _WITHOUT_TABLE else "docx tables"

    class _FakeConverter:  # pylint:disable=too-few-public-methods
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def convert_docx_tables_to_ebd_table(self) -> EbdTable:
            return _two_step_table.model_copy(deep=True)

    monkeypatch.setattr(ebd_toolchain.main, "get_ebd_docx_tables", _get_tables)
    monkeypatch.setattr(ebd_toolchain.main, "DocxTableConverter", _FakeConverter)
    return tmp_path / "out"


def test_main_writes_outcomes_only_for_ebds_with_table(patched_scraping: Path) -> None:
    export_types: list[Literal["puml", "dot", "json", "svg"]] = ["json", "dot"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    outcomes_files = sorted(path.name for path in patched_scraping.glob("*.outcomes.json"))
    assert outcomes_files == [f"{_WITH_TABLE}.outcomes.json"]
    EbdOutcomes.model_validate_json((patched_scraping / f"{_WITH_TABLE}.outcomes.json").read_text(encoding="utf-8"))
    assert (patched_scraping / f"{_WITHOUT_TABLE}.json").exists()
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
    assert (patched_scraping / f"{_WITH_TABLE}.dot").exists()
    assert not list(patched_scraping.glob("*.outcomes.json"))
    stdout = capsys.readouterr().out
    summary = json.loads(stdout[stdout.rindex("{") : stdout.rindex("}") + 1])
    assert summary == {"[WARNING:outcomes_export] ValueError": [_WITH_TABLE]}


def test_main_without_json_writes_no_outcomes(patched_scraping: Path) -> None:
    export_types: list[Literal["puml", "dot", "json", "svg"]] = ["dot"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    assert (patched_scraping / f"{_WITH_TABLE}.dot").exists()
    assert not list(patched_scraping.glob("*.outcomes.json"))
    assert not (patched_scraping / "ebd_outcomes.schema.json").exists()

"""
tests ``export_report.json``: which EBDs/files are missing in the output directory and why;
runs ``_main`` without a docx file and without kroki
"""

import json
from pathlib import Path
from typing import Any, Literal

from pytest import MonkeyPatch
from rebdhuhn.graph_conversion import convert_table_to_graph
from rebdhuhn.models.errors import GraphConversionError

import ebd_toolchain.main
from ebd_toolchain.discovery import EbdExportIssue, EbdExportReport
from ebd_toolchain.main import _main
from unittests.scraping_stubs import SCRAPING_FAILS, WITH_TABLE, WITHOUT_TABLE

_ExportTypes = list[Literal["puml", "dot", "json", "svg"]]
_JSON_AND_DOT: _ExportTypes = ["json", "dot"]


def _read_report(out: Path) -> EbdExportReport:
    return EbdExportReport.model_validate_json((out / "export_report.json").read_text(encoding="utf-8"))


def _files(out: Path, ebd_code: str) -> list[str]:
    return sorted(path.name for path in out.glob(f"{ebd_code}.*"))


def test_report_for_fine_failing_and_table_less_ebd(failing_scraping: Path) -> None:
    _main(Path("unused.docx"), failing_scraping, _JSON_AND_DOT)
    report = _read_report(failing_scraping)
    assert report.ebd_codes_in_document == [WITH_TABLE, SCRAPING_FAILS, WITHOUT_TABLE]
    assert report.issues == [
        EbdExportIssue(
            ebd_code=SCRAPING_FAILS,
            ebd_name="failing title",
            stage="scraping",
            severity="error",
            error_type="EbdTableNotConvertibleError",
            message="EBD table 'E_0060' cannot be converted: uses -- instead of ja/nein",
            missing_files=[f"{SCRAPING_FAILS}.json", f"{SCRAPING_FAILS}.outcomes.json", f"{SCRAPING_FAILS}.dot"],
        )
    ]
    assert _files(failing_scraping, SCRAPING_FAILS) == []  # i.e. the missing files really are missing
    # the table-less EBD legitimately has no outcomes file and is not reported
    assert _files(failing_scraping, WITHOUT_TABLE) == [f"{WITHOUT_TABLE}.dot", f"{WITHOUT_TABLE}.json"]
    assert _files(failing_scraping, WITH_TABLE) == [
        f"{WITH_TABLE}.dot",
        f"{WITH_TABLE}.json",
        f"{WITH_TABLE}.outcomes.json",
    ]


def test_table_less_ebd_is_not_reported_as_missing_puml_or_outcomes(patched_scraping: Path) -> None:
    export_types: _ExportTypes = ["json", "dot", "puml"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    assert _read_report(patched_scraping).issues == []


def test_outcomes_warning(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise ValueError("boom\n  with   whitespace")

    monkeypatch.setattr(ebd_toolchain.main, "_dump_outcomes", _fail)
    _main(Path("unused.docx"), patched_scraping, _JSON_AND_DOT)
    report = _read_report(patched_scraping)
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert (issue.ebd_code, issue.stage, issue.severity, issue.error_type) == (
        WITH_TABLE,
        "outcomes_export",
        "warning",
        "ValueError",
    )
    assert issue.message == "boom with whitespace"
    assert issue.ebd_name == "sub"  # the title as it is known after scraping
    assert issue.missing_files == [f"{WITH_TABLE}.outcomes.json"]
    assert (patched_scraping / f"{WITH_TABLE}.dot").exists()


def test_message_is_truncated(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise ValueError("x" * 2000)

    monkeypatch.setattr(ebd_toolchain.main, "_dump_outcomes", _fail)
    _main(Path("unused.docx"), patched_scraping, _JSON_AND_DOT)
    assert len(_read_report(patched_scraping).issues[0].message) == 500


def test_graph_conversion_error(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _convert(table: Any) -> Any:
        if table.metadata.ebd_code == WITH_TABLE:
            raise GraphConversionError("cannot convert")
        return convert_table_to_graph(table)

    monkeypatch.setattr(ebd_toolchain.main, "convert_table_to_graph", _convert)
    export_types: _ExportTypes = ["json", "dot", "puml"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    report = _read_report(patched_scraping)
    assert [(i.ebd_code, i.stage, i.severity, i.error_type) for i in report.issues] == [
        (WITH_TABLE, "graph_conversion", "error", "GraphConversionError")
    ]
    assert report.issues[0].missing_files == [f"{WITH_TABLE}.outcomes.json", f"{WITH_TABLE}.dot", f"{WITH_TABLE}.puml"]
    assert _files(patched_scraping, WITH_TABLE) == [f"{WITH_TABLE}.json"]


def test_svg_error_only_misses_what_is_not_on_disk(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise RuntimeError("kroki is down")

    monkeypatch.setattr(ebd_toolchain.main, "_dump_svg", _fail)
    export_types: _ExportTypes = ["json", "dot", "svg"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    issues = _read_report(patched_scraping).issues
    assert [(i.ebd_code, i.stage, i.severity) for i in issues] == [
        (WITH_TABLE, "svg_export", "error"),
        (WITHOUT_TABLE, "svg_export", "error"),
    ]
    # the dot file is written before the svg is attempted
    assert [i.missing_files for i in issues] == [[f"{WITH_TABLE}.svg"], [f"{WITHOUT_TABLE}.svg"]]


def test_dot_error_misses_dot_and_svg(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise RuntimeError("no graphviz")

    monkeypatch.setattr(ebd_toolchain.main, "_dump_dot", _fail)
    export_types: _ExportTypes = ["json", "dot", "svg"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    issues = _read_report(patched_scraping).issues
    assert issues[0].missing_files == [f"{WITH_TABLE}.dot", f"{WITH_TABLE}.svg"]


def test_puml_warning(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise AssertionError("too complex")

    monkeypatch.setattr(ebd_toolchain.main, "_dump_puml", _fail)
    export_types: _ExportTypes = ["json", "dot", "puml"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    issues = _read_report(patched_scraping).issues
    assert [(i.stage, i.severity, i.missing_files) for i in issues] == [
        ("puml_export", "warning", [f"{WITH_TABLE}.puml"])
    ]


def test_no_issues_still_writes_the_report(patched_scraping: Path) -> None:
    _main(Path("unused.docx"), patched_scraping, _JSON_AND_DOT)
    text = (patched_scraping / "export_report.json").read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == {"ebd_codes_in_document": [WITH_TABLE, WITHOUT_TABLE], "issues": []}


def test_issues_are_sorted_by_code_then_stage(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise RuntimeError("fails")

    monkeypatch.setattr(ebd_toolchain.main, "_dump_puml", _fail)
    monkeypatch.setattr(ebd_toolchain.main, "_dump_outcomes", _fail)
    monkeypatch.setattr(ebd_toolchain.main, "_dump_svg", _fail)
    export_types: _ExportTypes = ["json", "dot", "svg", "puml"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    stages = [(i.ebd_code, i.stage) for i in _read_report(patched_scraping).issues]
    assert stages == [
        (WITH_TABLE, "outcomes_export"),
        (WITH_TABLE, "puml_export"),
        (WITH_TABLE, "svg_export"),
        (WITHOUT_TABLE, "svg_export"),
    ]


def test_report_round_trip_and_schema(patched_scraping: Path) -> None:
    _main(Path("unused.docx"), patched_scraping, _JSON_AND_DOT)
    report = _read_report(patched_scraping)
    assert EbdExportReport.model_validate_json(report.model_dump_json()) == report
    schema = json.loads((patched_scraping / "export_report.schema.json").read_text(encoding="utf-8"))
    assert schema["title"] == "EbdExportReport"
    assert schema == EbdExportReport.model_json_schema(mode="serialization")


def test_without_json_no_report(patched_scraping: Path) -> None:
    export_types: _ExportTypes = ["dot"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    assert not (patched_scraping / "export_report.json").exists()
    assert not (patched_scraping / "export_report.schema.json").exists()

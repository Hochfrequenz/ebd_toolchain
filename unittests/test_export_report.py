"""
tests ``export_report.json``: which EBDs/files are missing in the output directory and why;
runs ``_main`` without a docx file and without kroki
"""

import json
from pathlib import Path
from typing import Any, Literal

import pytest
from ebdamame import TableNotFoundError
from pytest import MonkeyPatch
from rebdhuhn.graph_conversion import convert_table_to_graph
from rebdhuhn.kroki import KrokiDotBadRequestError
from rebdhuhn.models.errors import GraphConversionError

import ebd_toolchain.main
from ebd_toolchain.discovery import EbdExportIssue, EbdExportReport
from ebd_toolchain.main import _ISSUE_CLASSIFICATION, ErrorCategory, _build_export_report, _issue_message, _main
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
    issues = _read_report(patched_scraping).issues
    assert [(i.ebd_code, i.stage) for i in issues] == [
        (WITH_TABLE, "outcomes_export"),
        (WITH_TABLE, "puml_export"),
        (WITH_TABLE, "svg_export"),
        (WITHOUT_TABLE, "svg_export"),
    ]
    # state based: every issue of an EBD lists everything that is absent, not only the file of its own stage
    all_missing = [f"{WITH_TABLE}.outcomes.json", f"{WITH_TABLE}.svg", f"{WITH_TABLE}.puml"]
    assert [i.missing_files for i in issues] == [all_missing, all_missing, all_missing, [f"{WITHOUT_TABLE}.svg"]]


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


def test_files_of_not_requested_export_types_are_never_listed(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _convert(table: Any) -> Any:
        raise GraphConversionError("cannot convert")

    monkeypatch.setattr(ebd_toolchain.main, "convert_table_to_graph", _convert)
    export_types: _ExportTypes = ["json"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    issues = _read_report(patched_scraping).issues
    assert [(i.ebd_code, i.missing_files) for i in issues] == [
        (WITH_TABLE, [f"{WITH_TABLE}.outcomes.json"]),
        (WITHOUT_TABLE, []),
    ]


def test_unexpected_scraping_error(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    class _BrokenConverter:  # pylint:disable=too-few-public-methods
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def convert_docx_tables_to_ebd_table(self) -> None:
            raise ValueError("kaputt")

    monkeypatch.setattr(ebd_toolchain.main, "DocxTableConverter", _BrokenConverter)
    _main(Path("unused.docx"), patched_scraping, _JSON_AND_DOT)
    issues = _read_report(patched_scraping).issues
    assert [(i.ebd_code, i.ebd_name, i.stage, i.severity, i.error_type, i.message) for i in issues] == [
        (WITH_TABLE, "sub", "scraping", "error", "ValueError", "kaputt")
    ]
    assert issues[0].missing_files == [f"{WITH_TABLE}.json", f"{WITH_TABLE}.outcomes.json", f"{WITH_TABLE}.dot"]


def test_empty_exception_text_falls_back_to_the_error_type(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise AssertionError  # a bare assert has no text

    monkeypatch.setattr(ebd_toolchain.main, "_dump_puml", _fail)
    export_types: _ExportTypes = ["json", "puml"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    assert [i.message for i in _read_report(patched_scraping).issues] == ["AssertionError"]


def test_table_not_found_error_has_an_empty_text_and_falls_back_to_the_type(
    patched_scraping: Path, monkeypatch: MonkeyPatch
) -> None:
    def _get_tables(docx_file_path: Path, ebd_key: str) -> Any:  # pylint:disable=unused-argument
        raise TableNotFoundError(ebd_key=ebd_key)  # the keyword form is how ebdamame raises it; its str is empty

    monkeypatch.setattr(ebd_toolchain.main, "get_ebd_docx_tables", _get_tables)
    _main(Path("unused.docx"), patched_scraping, _JSON_AND_DOT)
    issues = _read_report(patched_scraping).issues
    assert [(i.error_type, i.message) for i in issues] == [("TableNotFoundError", "TableNotFoundError")] * 2


def test_scraping_error_of_a_table_less_ebd_does_not_expect_outcomes_or_puml(
    patched_scraping: Path, monkeypatch: MonkeyPatch
) -> None:
    def _broken_metadata(**_: Any) -> None:
        raise ValueError("invalid metadata")

    monkeypatch.setattr(ebd_toolchain.main, "EbdTableMetaData", _broken_metadata)
    export_types: _ExportTypes = ["json", "dot", "puml"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    issues = _read_report(patched_scraping).issues
    assert [(i.ebd_code, i.stage) for i in issues] == [(WITHOUT_TABLE, "scraping")]
    assert issues[0].missing_files == [f"{WITHOUT_TABLE}.json", f"{WITHOUT_TABLE}.dot"]


def test_message_does_not_leak_environment_details(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise OSError(
            f"cannot write {patched_scraping.absolute()}/E_0003.svg; HTTPConnectionPool(host='localhost', port=8000): "
            "Max retries exceeded with url: / (Caused by <urllib3.connection.HTTPConnection object at 0x7f12ab>); "
            "http://localhost:8000/x and localhost:8000 and /home/someone/project/file.txt and unused.docx"
        )

    monkeypatch.setattr(ebd_toolchain.main, "_dump_svg", _fail)
    export_types: _ExportTypes = ["json", "svg"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    message = _read_report(patched_scraping).issues[0].message
    for leaked in (str(patched_scraping), "localhost", "8000", "0x7f12ab", "/home/someone", "unused.docx"):
        assert leaked not in message
    assert message.startswith("cannot write <output>/E_0003.svg; HTTPConnectionPool(<kroki>)")


def test_kroki_bad_request_keeps_only_the_part_before_the_diagram_source(
    patched_scraping: Path, monkeypatch: MonkeyPatch
) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise KrokiDotBadRequestError("digraph secret_dot_source {}", "Error 400: syntax error")

    monkeypatch.setattr(ebd_toolchain.main, "_dump_svg", _fail)
    export_types: _ExportTypes = ["json", "svg"]
    _main(Path("unused.docx"), patched_scraping, export_types)
    assert _read_report(patched_scraping).issues[0].message == "BadRequest while creating svg: Error 400: syntax error"


def test_long_message_is_cut_with_an_ellipsis(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise ValueError("x" * 2000)

    monkeypatch.setattr(ebd_toolchain.main, "_dump_outcomes", _fail)
    _main(Path("unused.docx"), patched_scraping, _JSON_AND_DOT)
    message = _read_report(patched_scraping).issues[0].message
    assert len(message) == 500
    assert message.endswith("x…")


def test_report_is_identical_across_output_directories(patched_scraping: Path, monkeypatch: MonkeyPatch) -> None:
    def _fail(path: Path, *_: Any, **__: Any) -> None:
        raise OSError(f"cannot write {path.absolute()} (object at 0x7f12ab34cd)")

    monkeypatch.setattr(ebd_toolchain.main, "_dump_svg", _fail)
    monkeypatch.setattr(ebd_toolchain.main, "_dump_outcomes", _fail)
    export_types: _ExportTypes = ["json", "svg"]
    other = patched_scraping.parent / "somewhere" / "else"
    _main(Path("unused.docx"), patched_scraping, export_types)
    _main(Path("unused.docx"), other, export_types)
    first = (patched_scraping / "export_report.json").read_bytes()
    assert first == (other / "export_report.json").read_bytes()
    assert b"cannot write <output>/E_0003.svg" in first


@pytest.mark.parametrize("category", list(ErrorCategory))
def test_every_error_category_yields_a_valid_issue(category: ErrorCategory, tmp_path: Path) -> None:
    assert category in _ISSUE_CLASSIFICATION
    report = _build_export_report(
        [WITH_TABLE],
        [(WITH_TABLE, None, category, ValueError("boom"))],
        tmp_path,
        ["json", "dot", "svg", "puml"],
        set(),
        input_path=Path("in.docx"),
        kroki_host="localhost",
        kroki_port=8000,
    )
    assert len(report.issues) == 1
    assert report.issues[0].severity == ("warning" if category.value.startswith("WARNING") else "error")
    assert category.value.endswith(report.issues[0].stage)


def _message(text: str, output: str = "/home/alice/work/out", input_doc: str = "/data/in/ebd.docx") -> str:
    return _issue_message(ValueError(text), Path(output), Path(input_doc), "localhost", 8000)


@pytest.mark.parametrize(
    "text, output, expected",
    [
        pytest.param("rel ../a ./b", ".", "rel ../a ./b", id="dot-only relative path is left alone"),
        pytest.param("rel ../a ./b", "..", "rel ../a ./b", id="dot-dot relative path is left alone"),
        pytest.param(
            "see out/x.svg and xout/y and a/out/z", "out", "see <output>/x.svg and xout/y and a/out/z", id="bare"
        ),
        pytest.param(
            "/home/alice/work/outer/x and /home/alice/work/out2/y",
            "/home/alice/work/out",
            "<path> and <path>",
            id="longer siblings are not cut in the middle",
        ),
        pytest.param(
            "wrote /home/alice/work/out/E.svg, then /home/alice/work/out.",
            "/home/alice/work/out",
            "wrote <output>/E.svg, then <output>.",
            id="exact path",
        ),
    ],
)
def test_output_path_replacement(text: str, output: str, expected: str) -> None:
    assert _message(text, output=output) == expected


def test_kroki_port_is_matched_completely() -> None:
    assert _message("localhost:80001 and localhost:8000") == "localhost:80001 and <kroki>"
    assert _message("http://localhost:80001/x") == "http://localhost:80001/x"


def test_bare_input_file_name_is_replaced() -> None:
    assert _message("cannot open ebd.docx (/data/in/ebd.docx) not myebd.docx.bak") == (
        "cannot open <input> (<input>) not myebd.docx.bak"
    )

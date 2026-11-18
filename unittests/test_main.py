"""
tests the main script
"""

import json
from pathlib import Path
from typing import Literal

import pytest
from _pytest.monkeypatch import MonkeyPatch
from rebdhuhn import EbdOutcomes

from ebd_toolchain.discovery import EbdExportReport
from ebd_toolchain.main import _main

repo_root = Path(__file__).parent.parent
recent_docx_file = (
    repo_root
    / "edi_energy_mirror"
    / "edi_energy_de"
    / "FV2504"
    / "Entscheidungsbaum-DiagrammeundCodelisten-informatorischeLesefassung4.0a_99991231_20250404.docx"
)
_mirror_root = repo_root / "edi_energy_mirror" / "edi_energy_de"

if _mirror_root.is_dir() and not recent_docx_file.exists():
    # The mirror is a scraper whose file names embed validity dates, so documents are
    # renamed and removed over time. If the submodule is checked out but this document
    # is gone, the pin is stale - that must fail loudly rather than silently skip, which
    # would disarm the only test that exercises _main.
    raise FileNotFoundError(
        f"edi_energy_mirror is checked out but {recent_docx_file.name} is missing - "
        "the submodule pin is stale or the document was renamed upstream."
    )

pytestmark = pytest.mark.skipif(
    not _mirror_root.is_dir(),
    reason="the private edi_energy_mirror submodule is not available",
)


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
    json_files = list(tmp_path.glob("*.json"))
    for json_file in json_files:
        assert json_file.exists()
        with open(json_file, encoding="utf-8") as f:
            _ = json.load(f)  # must be valid json
    # outcomes are tied to the json export
    outcomes_files = list(tmp_path.glob("*.outcomes.json"))
    assert len(outcomes_files) > 0
    assert (tmp_path / "ebd_outcomes.schema.json").exists()
    for outcomes_file in outcomes_files:
        _ = EbdOutcomes.model_validate_json(outcomes_file.read_text(encoding="utf-8"))
        assert (tmp_path / outcomes_file.name.removesuffix(".outcomes.json")).with_suffix(".json").exists()
    # the export report must tell the truth about what is (not) in the directory
    report = EbdExportReport.model_validate_json((tmp_path / "export_report.json").read_text(encoding="utf-8"))
    assert (tmp_path / "export_report.schema.json").exists()
    assert report.ebd_codes_in_document
    for issue in report.issues:
        assert issue.missing_files
        for missing_file in issue.missing_files:
            assert not (tmp_path / missing_file).exists()
    failed_scraping = {
        issue.ebd_code for issue in report.issues if issue.stage == "scraping" and issue.severity == "error"
    }
    for ebd_code in report.ebd_codes_in_document:
        assert (tmp_path / f"{ebd_code}.json").exists() or ebd_code in failed_scraping
    # the other direction: whatever is absent must be listed by the issues of that EBD
    listed: dict[str, set[str]] = {}
    for issue in report.issues:
        listed.setdefault(issue.ebd_code, set()).update(issue.missing_files)
    for ebd_code in report.ebd_codes_in_document:
        expected = [f"{ebd_code}.json", f"{ebd_code}.dot", f"{ebd_code}.svg"]
        json_path = tmp_path / f"{ebd_code}.json"
        if json_path.exists() and json.loads(json_path.read_text(encoding="utf-8"))["rows"]:
            expected.append(f"{ebd_code}.outcomes.json")
        for expected_file in expected:
            assert (tmp_path / expected_file).exists() or expected_file in listed.get(ebd_code, set()), expected_file

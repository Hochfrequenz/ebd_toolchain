"""
fixtures shared by the tests that run ``_main`` without a docx file and without kroki
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ebdamame import EbdNoTableSection, EbdTableNotConvertibleError
from pytest import MonkeyPatch
from rebdhuhn.models import EbdTable

import ebd_toolchain.main
from unittests.scraping_stubs import SCRAPING_FAILS, TWO_STEP_TABLE, WITH_TABLE, WITHOUT_TABLE

_KAPITEL = SimpleNamespace(
    subsection_title="sub", chapter_title="chapter", chapter=1, section=2, subsection=3, section_title="section"
)


@pytest.fixture(name="patched_scraping")
def _patched_scraping(monkeypatch: MonkeyPatch, tmp_path: Path) -> Path:
    """lets _main process one EBD with a table and one without, without a docx file and without kroki"""
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
        lambda _: {WITH_TABLE: ("title", _KAPITEL), WITHOUT_TABLE: ("title", _KAPITEL)},
    )

    def _get_tables(docx_file_path: Path, ebd_key: str) -> Any:  # pylint:disable=unused-argument
        return EbdNoTableSection(ebd_key=ebd_key, remark="no table") if ebd_key == WITHOUT_TABLE else "docx tables"

    class _FakeConverter:  # pylint:disable=too-few-public-methods
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def convert_docx_tables_to_ebd_table(self) -> EbdTable:
            return TWO_STEP_TABLE.model_copy(deep=True)

    monkeypatch.setattr(ebd_toolchain.main, "get_ebd_docx_tables", _get_tables)
    monkeypatch.setattr(ebd_toolchain.main, "DocxTableConverter", _FakeConverter)
    return tmp_path / "out"


@pytest.fixture(name="failing_scraping")
def _failing_scraping(patched_scraping: Path, monkeypatch: MonkeyPatch) -> Path:
    """like ``patched_scraping`` but the document contains a third EBD whose table cannot be converted"""
    main_module: Any = ebd_toolchain.main  # typed as Any because mypy --strict forbids re-exported names
    original_keys = main_module.get_all_ebd_keys  # the stub of patched_scraping
    original_get_tables = main_module.get_ebd_docx_tables

    def _get_all_ebd_keys(docx_path: Path) -> Any:
        return {**original_keys(docx_path), SCRAPING_FAILS: ("failing title", _KAPITEL)}

    def _get_tables(docx_file_path: Path, ebd_key: str) -> Any:
        if ebd_key == SCRAPING_FAILS:
            raise EbdTableNotConvertibleError(ebd_key, "uses -- instead of\nja/nein")
        return original_get_tables(docx_file_path=docx_file_path, ebd_key=ebd_key)

    monkeypatch.setattr(ebd_toolchain.main, "get_all_ebd_keys", _get_all_ebd_keys)
    monkeypatch.setattr(ebd_toolchain.main, "get_ebd_docx_tables", _get_tables)
    return patched_scraping

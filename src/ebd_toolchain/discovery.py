"""
Pydantic models for the discovery artifacts written alongside the EBD exports so that
AI/programmatic consumers can resolve a natural-language question or a Prüfidentifikator to an
``ebd_code`` (and thus to the ``<ebd_code>.json`` / ``.puml`` / ``.svg`` files) without crawling
the directory. See the ``machine-readable_…`` repo's ``llms.txt`` for the consumer-side contract.
"""

# pydantic RootModel wrappers legitimately have no public methods of their own
# pylint: disable=too-few-public-methods
from typing import Literal

from pydantic import BaseModel, Field, RootModel


class EbdIndexEntry(BaseModel):
    """one catalog entry per successfully-scraped EBD (a row of ``index.json``)"""

    ebd_code: str
    ebd_name: str
    chapter: str
    section: str
    role: str
    pruefidentifikatoren: list[str] = Field(default_factory=list)


class EbdIndex(RootModel[list[EbdIndexEntry]]):
    """``index.json``: the catalog of all EBDs in a format version"""


class PruefiToKey(RootModel[dict[str, str]]):
    """``pruefi_to_key.json``: Prüfidentifikator -> ``ebd_code`` (the primary lookup)"""


class EbdExportIssue(BaseModel):
    """one thing that went wrong for one EBD, and which of its files are consequently missing"""

    ebd_code: str = Field(description="the EBD code, e.g. E_0060")
    ebd_name: str | None = Field(description="the title from the document if it was known at that point, else null")
    stage: Literal["scraping", "graph_conversion", "svg_export", "puml_export", "outcomes_export"] = Field(
        description="the pipeline stage that failed"
    )
    severity: Literal["error", "warning"] = Field(
        description="errors affect the primary outputs, warnings only secondary outputs (.puml, .outcomes.json)"
    )
    error_type: str = Field(description="class name of the exception, e.g. EbdTableNotConvertibleError")
    message: str = Field(description="the exception message in a single line, at most 500 characters")
    missing_files: list[str] = Field(
        description="files of this EBD that were requested by the export types but are not in the directory"
    )


class EbdExportReport(BaseModel):
    """``export_report.json``: which EBDs/files of the document are missing in the directory and why"""

    ebd_codes_in_document: list[str] = Field(description="all EBD codes found in the document, sorted")
    issues: list[EbdExportIssue] = Field(description="sorted by ebd_code, then by pipeline stage")

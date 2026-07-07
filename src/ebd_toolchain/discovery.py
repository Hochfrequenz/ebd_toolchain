"""
Pydantic models for the discovery artifacts written alongside the EBD exports so that
AI/programmatic consumers can resolve a natural-language question or a Prüfidentifikator to an
``ebd_code`` (and thus to the ``<ebd_code>.json`` / ``.puml`` / ``.svg`` files) without crawling
the directory. See the ``machine-readable_…`` repo's ``llms.txt`` for the consumer-side contract.
"""

# pydantic RootModel wrappers legitimately have no public methods of their own
# pylint: disable=too-few-public-methods
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

"""
A small click-based script to extract all EBDs from a given .docx file (available at edi-energy.de).
For each EBD it writes (depending on the chosen export types) ``<EBD>.json``, ``.dot``, ``.svg`` and ``.puml``.
With ``json`` it additionally writes ``<EBD>.outcomes.json`` (only for EBDs with a table) and the discovery files
``index.json``, ``pruefi_to_key.json``, ``ebd.schema.json``, ``ebd_outcomes.schema.json`` and
``export_report.json`` (+ ``export_report.schema.json``), which lists the EBDs/files that are missing and why.
"""

# invoke like this:
# main.py -i unittests/test_data/ebd20230619_v33.docx
#  -o ../machine-readable_entscheidungsbaumdiagramme/FV2304
#  -t json -t dot -t svg -t puml
#
# or
#
# main.py -i unittests/test_data/ebd20230629_v34.docx
#  -o ../machine-readable_entscheidungsbaumdiagramme/FV2310
#  -t json -t dot -t svg -t puml
#
# or
# install this package using `pip install .`
# or `git+https://$github_username:$gh_personal_token@github.com/Hochfrequenz/ebd_toolchain.git@$v1.2.3`
#
# and then call
# scrape_and_graph -i unittests/test_data/ebd20230629_v34.docx
#  -o ../machine-readable_entscheidungsbaumdiagramme/FV2310
#  -t json -t dot -t svg -t puml
# where scrape_and_graph is just a placeholder/link to the main.py file as defined in the pyproject.toml scripts section

import json
import logging
from collections.abc import Iterable, Sequence
from collections.abc import Set as AbstractSet
from enum import Enum
from pathlib import Path
from typing import Literal

import click
from ebdamame import (
    EbdNoTableSection,
    EbdTableNotConvertibleError,
    TableNotFoundError,
    get_all_ebd_keys,
    get_ebd_docx_tables,
)
from ebdamame.docxtableconverter import DocxTableConverter
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rebdhuhn import EbdOutcomes, explain_outcomes
from rebdhuhn.graph_conversion import convert_table_to_graph
from rebdhuhn.graphviz import convert_dot_to_svg_kroki, convert_graph_to_dot
from rebdhuhn.kroki import DotToSvgConverter, Kroki
from rebdhuhn.models.ebd_graph import EbdGraph
from rebdhuhn.models.ebd_table import EbdPruefidentifikator, EbdTable, EbdTableMetaData
from rebdhuhn.models.errors import GraphConversionError, PlantumlConversionError, SvgConversionError
from rebdhuhn.plantuml import convert_graph_to_plantuml

from ebd_toolchain.ahb_pruefi import download_ahb_db, get_ebd_to_pruefis_mapping
from ebd_toolchain.discovery import EbdExportIssue, EbdExportReport, EbdIndex, EbdIndexEntry, PruefiToKey

_logger = logging.getLogger(__name__)

_MAX_ISSUE_MESSAGE_LENGTH = 500
_ISSUE_STAGES_IN_PIPELINE_ORDER = ["scraping", "graph_conversion", "outcomes_export", "puml_export", "svg_export"]


class ErrorCategory(Enum):
    """Categories for classifying errors by pipeline stage and severity."""

    # Errors (critical - affect primary outputs)
    SCRAPING = "ERROR:scraping"
    GRAPH_CONVERSION = "ERROR:graph_conversion"
    SVG_EXPORT = "ERROR:svg_export"
    # Warnings (non-critical - only affect secondary outputs)
    PUML_EXPORT = "WARNING:puml_export"
    OUTCOMES_EXPORT = "WARNING:outcomes_export"


# pylint:disable=too-few-public-methods
class Settings(BaseSettings):
    """settings loaded from environment variable/.env file"""

    kroki_port: int = Field(alias="KROKI_PORT")
    kroki_host: str = Field(alias="KROKI_HOST")
    github_token: str | None = Field(
        default=None,
        alias="GITHUB_TOKEN",
        description="GitHub token to download AHB DB from Hochfrequenz/xml-migs-and-ahbs releases",
    )
    format_version: str | None = Field(default=None, alias="FORMAT_VERSION")
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("github_token", "format_version", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: object) -> object:
        """Treat empty strings from .env files as None."""
        if v == "":
            return None
        return v


def _dump_puml(puml_path: Path, ebd_graph: EbdGraph) -> None:
    plantuml_code = convert_graph_to_plantuml(ebd_graph)
    with open(puml_path, "w+", encoding="utf-8") as uml_file:
        uml_file.write(plantuml_code)


def _dump_outcomes(outcomes_path: Path, ebd_graph: EbdGraph) -> None:
    """write which steps a result code implies (see rebdhuhn's ``explain_outcomes``) as JSON"""
    _write_json_text(outcomes_path, explain_outcomes(ebd_graph).model_dump_json(indent=2))


def _outcomes_schema_text() -> str:
    """the JSON Schema of the ``<ebd_code>.outcomes.json`` files (content of ``ebd_outcomes.schema.json``)"""
    return json.dumps(EbdOutcomes.model_json_schema(mode="serialization"), indent=2, sort_keys=True)


def _export_report_schema_text() -> str:
    """the JSON Schema of ``export_report.json`` (content of ``export_report.schema.json``)"""
    return json.dumps(EbdExportReport.model_json_schema(mode="serialization"), indent=2, sort_keys=True)


def _expected_files(ebd_code: str, export_types: Sequence[str], has_table: bool) -> list[str]:
    """
    The files that the requested export types should yield for an EBD (in a fixed order).
    EBDs without a table legitimately have neither an outcomes nor a puml file.
    """
    expected: list[str] = []
    if "json" in export_types:
        expected.append(f"{ebd_code}.json")
        if has_table:
            expected.append(f"{ebd_code}.outcomes.json")
    if "dot" in export_types:
        expected.append(f"{ebd_code}.dot")
    if "svg" in export_types:
        expected.append(f"{ebd_code}.svg")
    if "puml" in export_types and has_table:
        expected.append(f"{ebd_code}.puml")
    return expected


def _build_export_report(
    ebd_codes_in_document: Iterable[str],
    raw_issues: Iterable[tuple[str, str | None, ErrorCategory, Exception]],
    output_path: Path,
    export_types: Sequence[str],
    ebds_without_table: AbstractSet[str],
) -> EbdExportReport:
    """
    Turns the errors collected during the run into the report.
    ``missing_files`` is what is really absent in the output directory (of the files the export types ask for),
    not a guess based on the stage; so the claim holds even if e.g. only the dot but not the svg got written.
    """
    issues: list[EbdExportIssue] = []
    for ebd_code, ebd_name, category, error in raw_issues:
        severity, stage = category.value.lower().split(":")
        expected = _expected_files(ebd_code, export_types, ebd_code not in ebds_without_table)
        message = " ".join(str(error).split())
        issues.append(
            EbdExportIssue(
                ebd_code=ebd_code,
                ebd_name=ebd_name,
                stage=stage,  # type:ignore[arg-type] # validated by pydantic; the values are those of ErrorCategory
                severity=severity,  # type:ignore[arg-type]
                error_type=type(error).__name__,
                message=message[:_MAX_ISSUE_MESSAGE_LENGTH],
                missing_files=[name for name in expected if not (output_path / name).exists()],
            )
        )
    issues.sort(key=lambda issue: (issue.ebd_code, _ISSUE_STAGES_IN_PIPELINE_ORDER.index(issue.stage)))
    return EbdExportReport(ebd_codes_in_document=sorted(ebd_codes_in_document), issues=issues)


def _dump_dot(dot_path: Path, ebd_graph: EbdGraph) -> None:
    dot_code = convert_graph_to_dot(ebd_graph, ebd_link_template="?ebd={ebd_code}")
    # the ?ebd=... relative link should work on ebd.hochfrequenz.de... hopefully
    # my expectation is, that this link target simply replaces the set query parameter
    with open(dot_path, "w+", encoding="utf-8") as uml_file:
        uml_file.write(dot_code)


def _dump_svg(svg_path: Path, ebd_graph: EbdGraph, converter: DotToSvgConverter) -> None:
    dot_code = convert_graph_to_dot(ebd_graph, ebd_link_template="?ebd={ebd_code}")
    svg_code = convert_dot_to_svg_kroki(
        dot_code,
        converter,
        release_info=ebd_graph.metadata.release_information,
        pruefidentifikatoren=ebd_graph.metadata.pruefidentifikatoren,
    )
    with open(svg_path, "w+", encoding="utf-8") as svg_file:
        svg_file.write(svg_code)


def _dump_json(json_path: Path, ebd_table: EbdTable | EbdTableMetaData) -> None:
    with open(json_path, "w+", encoding="utf-8") as json_file:
        json.dump(ebd_table.model_dump(mode="json"), json_file, ensure_ascii=False, indent=2, sort_keys=True)


def _write_json_text(json_path: Path, json_text: str) -> None:
    """write a pre-serialised JSON string (e.g. from a pydantic ``model_dump_json``) plus a newline"""
    with open(json_path, "w+", encoding="utf-8") as json_file:
        json_file.write(json_text)
        json_file.write("\n")


@click.command()
@click.option(
    "-i",
    "--input_path",
    type=click.Path(exists=True, dir_okay=False, file_okay=True, path_type=Path),
    prompt="Input DOCX File",
    help="Path of a .docx file from which the EBDs shall be extracted",
)
@click.option(
    "-o",
    "--output_path",
    type=click.Path(exists=False, dir_okay=True, file_okay=False, path_type=Path),
    default="output",
    prompt="Output directory",
    help="Define the path where you want to save the generated files",
)
@click.option(
    "-t",
    "--export_types",
    type=click.Choice(["puml", "dot", "json", "svg"], case_sensitive=False),
    multiple=True,
    help="Choose which file you'd like to create. 'json' also writes the outcomes and discovery files.",
)
def main(input_path: Path, output_path: Path, export_types: list[Literal["puml", "dot", "json", "svg"]]) -> None:
    """
    A program to get a machine-readable version of the AHBs docx files published by edi@energy.
    """
    _main(input_path, output_path, export_types)


# pylint:disable=too-many-locals, too-many-branches, too-many-statements,
def _main(input_path: Path, output_path: Path, export_types: list[Literal["puml", "dot", "json", "svg"]]) -> None:
    """same as main but without the click decorators"""
    settings = Settings()  # type: ignore[call-arg]
    # read settings from environment variable/.env file
    kroki_client = Kroki(kroki_host=f"http://{settings.kroki_host}:{settings.kroki_port}")

    # Load EBD-to-Pruefidentifikator mapping from AHB database (if available)
    ebd_to_pruefis: dict[str, list[EbdPruefidentifikator]] = {}
    if settings.github_token:
        click.secho("Downloading AHB database from xml-migs-and-ahbs...", fg="cyan")
        db_path = download_ahb_db(settings.github_token)
        click.secho(f"Loading EBD-to-Prüfi mapping from {db_path} (format_version={settings.format_version})")
        ebd_to_pruefis = get_ebd_to_pruefis_mapping(db_path, format_version=settings.format_version)
        click.secho(f"Loaded Prüfi mapping for {len(ebd_to_pruefis)} EBDs", fg="green")
    if output_path.exists() and output_path.is_dir():
        click.secho(f"The output directory '{output_path}' exists already. Will remove its content.", fg="yellow")
        for item in output_path.iterdir():
            if item.is_file():
                item.unlink()
    output_path.mkdir(parents=True, exist_ok=True)
    click.secho(f"Created a new directory at {output_path}", fg="green")
    all_ebd_keys = get_all_ebd_keys(input_path)
    error_sources: dict[str, list[str]] = {}
    # one discovery entry per successfully-scraped EBD; written out (as index.json / pruefi_to_key.json)
    # after the loop, but only when JSON export is requested -- these artifacts describe/point to the
    # <ebd_code>.json files, so they are meaningless without them. Lets AI/programmatic consumers map a
    # natural-language question or Prüfidentifikator -> ebd_code -> file without crawling the directory.
    index_entries: list[EbdIndexEntry] = []

    # every handled error, in the order of occurrence; becomes export_report.json once the files on disk are known
    raw_issues: list[tuple[str, str | None, ErrorCategory, Exception]] = []
    # EBDs without a table legitimately have neither .outcomes.json nor .puml
    ebds_without_table: set[str] = set()

    def handle_known_error(error: Exception, ebd_key: str, category: ErrorCategory, ebd_name: str | None) -> None:
        raw_issues.append((ebd_key, ebd_name, category, error))
        color = "yellow" if category.value.startswith("WARNING") else "red"
        click.secho(f"{category.value}: {ebd_key}: {error}", fg=color)
        error_type_name = type(error).__name__
        key = f"[{category.value}] {error_type_name}"
        if key not in error_sources:
            error_sources[key] = []
        error_sources[key].append(ebd_key)

    for ebd_key, (ebd_title, ebd_kapitel) in all_ebd_keys.items():
        # for ebd_key, (ebd_title, ebd_kapitel) in {"E_0267": all_ebd_keys["E_0267"]}.items():
        click.secho(f"Processing EBD {ebd_kapitel} '{ebd_key}' ({ebd_title})")
        try:
            docx_tables = get_ebd_docx_tables(docx_file_path=input_path, ebd_key=ebd_key)
        except TableNotFoundError as table_not_found_error:
            handle_known_error(table_not_found_error, ebd_key, ErrorCategory.SCRAPING, ebd_title)
            continue
        except EbdTableNotConvertibleError as not_convertible_error:
            handle_known_error(not_convertible_error, ebd_key, ErrorCategory.SCRAPING, ebd_title)
            continue
        assert ebd_kapitel is not None
        ebd_name = ebd_kapitel.subsection_title or ebd_title
        try:
            if isinstance(docx_tables, EbdNoTableSection):
                ebd_meta_data = EbdTableMetaData(
                    ebd_code=ebd_key,
                    ebd_name=ebd_name,
                    chapter=ebd_kapitel.chapter_title,  # type: ignore[arg-type]
                    section=f"{ebd_kapitel.chapter}.{ebd_kapitel.section}.{ebd_kapitel.subsection}: {ebd_kapitel.section_title}",  # noqa: E501
                    role="N/A",
                    remark=docx_tables.remark,  # pylint:disable=no-member
                )
                ebd_table = EbdTable(metadata=ebd_meta_data, rows=[])
                ebds_without_table.add(ebd_key)

            else:
                converter = DocxTableConverter(
                    docx_tables,
                    ebd_key=ebd_key,
                    ebd_name=ebd_name,
                    chapter=ebd_kapitel.chapter_title,  # type: ignore[arg-type]
                    section=f"{ebd_kapitel.chapter}.{ebd_kapitel.section}.{ebd_kapitel.subsection}: {ebd_kapitel.section_title}",  # noqa: E501
                )
                ebd_table = converter.convert_docx_tables_to_ebd_table()
            ebd_table.metadata.pruefidentifikatoren = ebd_to_pruefis.get(ebd_key)
        except Exception as scraping_error:  # pylint:disable=broad-except
            handle_known_error(scraping_error, ebd_key, ErrorCategory.SCRAPING, ebd_name)
            continue
        _md = ebd_table.metadata
        index_entries.append(
            EbdIndexEntry(
                ebd_code=_md.ebd_code,
                ebd_name=_md.ebd_name,
                chapter=_md.chapter,
                section=_md.section,
                role=_md.role,
                pruefidentifikatoren=[p.pruefidentifikator for p in (_md.pruefidentifikatoren or [])],
            )
        )
        if "json" in export_types:
            json_path = output_path / Path(f"{ebd_key}.json")
            _dump_json(json_path, ebd_table)
            click.secho(f"💾 Successfully exported '{ebd_key}.json' to {json_path.absolute()}")
        try:
            ebd_graph = convert_table_to_graph(ebd_table)
        except GraphConversionError as graph_error:
            handle_known_error(graph_error, ebd_key, ErrorCategory.GRAPH_CONVERSION, ebd_name)
            continue
        except Exception as unknown_error:  # pylint:disable=broad-except
            handle_known_error(unknown_error, ebd_key, ErrorCategory.GRAPH_CONVERSION, ebd_name)
            continue
        if "json" in export_types and any(ebd_table.rows):
            # EBDs without a table have nothing to explain, hence no outcomes file for them
            try:
                outcomes_path = output_path / Path(f"{ebd_key}.outcomes.json")
                _dump_outcomes(outcomes_path, ebd_graph)
                click.secho(f"💾 Successfully exported '{ebd_key}.outcomes.json' to {outcomes_path.absolute()}")
            except Exception as outcomes_error:  # pylint:disable=broad-exception-caught
                handle_known_error(outcomes_error, ebd_key, ErrorCategory.OUTCOMES_EXPORT, ebd_name)
        if "puml" in export_types:
            if not any(ebd_table.rows):
                click.secho(f"EBD {ebd_key} has no ebd table; Skip puml creation!", fg="yellow")
            else:
                try:
                    puml_path = output_path / Path(f"{ebd_key}.puml")
                    _dump_puml(puml_path, ebd_graph)
                    click.secho(f"💾 Successfully exported '{ebd_key}.puml' to {puml_path.absolute()}")
                except PlantumlConversionError as puml_error:
                    handle_known_error(puml_error, ebd_key, ErrorCategory.PUML_EXPORT, ebd_name)
                except (AssertionError, Exception) as general_error:  # pylint:disable=broad-exception-caught
                    handle_known_error(general_error, ebd_key, ErrorCategory.PUML_EXPORT, ebd_name)

        try:
            if "dot" in export_types:
                dot_path = output_path / Path(f"{ebd_key}.dot")
                _dump_dot(dot_path, ebd_graph)
                click.secho(f"💾 Successfully exported '{ebd_key}.dot' to {dot_path.absolute()}")
            if "svg" in export_types:
                svg_path = output_path / Path(f"{ebd_key}.svg")
                _dump_svg(svg_path, ebd_graph, kroki_client)
                click.secho(f"💾 Successfully exported '{ebd_key}.svg' to {svg_path.absolute()}")
        except SvgConversionError as svg_error:
            handle_known_error(svg_error, ebd_key, ErrorCategory.SVG_EXPORT, ebd_name)
        except (AssertionError, Exception) as general_error:  # pylint:disable=broad-exception-caught
            # both the SVG and dot path require graphviz to work, hence the common error handling block
            handle_known_error(general_error, ebd_key, ErrorCategory.SVG_EXPORT, ebd_name)
    # --- discovery artifacts for AI/programmatic consumers (see machine-readable_… repo llms.txt) ---
    # Only emitted alongside JSON export: they describe/point to the <ebd_code>.json files.
    if "json" in export_types:
        # index.json: a JSON array of entries {ebd_code, ebd_name, chapter, section, role, pruefis},
        # sorted by ebd_code, for natural-language -> key resolution.
        index = EbdIndex(sorted(index_entries, key=lambda entry: entry.ebd_code))
        _write_json_text(output_path / "index.json", index.model_dump_json(indent=2))
        # pruefi_to_key.json: the primary lookup, since users quote Prüfidentifikatoren from AHBs/EDIFACT.
        # A Prüfidentifikator should map to exactly one EBD; if the AHB data ever links one to several,
        # keep the first (lowest ebd_code, since sorted) and warn instead of silently overwriting.
        pruefi_to_key: dict[str, str] = {}
        collisions: dict[str, list[str]] = {}
        for entry in index.root:
            for pruefi in entry.pruefidentifikatoren:
                if pruefi in pruefi_to_key and pruefi_to_key[pruefi] != entry.ebd_code:
                    collisions.setdefault(pruefi, [pruefi_to_key[pruefi]]).append(entry.ebd_code)
                    continue
                pruefi_to_key[pruefi] = entry.ebd_code
        if collisions:
            click.secho(f"⚠️ Prüfidentifikator(en) mapped to multiple EBDs (kept first): {collisions}", fg="yellow")
        _write_json_text(
            output_path / "pruefi_to_key.json",
            PruefiToKey(dict(sorted(pruefi_to_key.items()))).model_dump_json(indent=2),
        )
        # ebd.schema.json: the JSON Schema of the <ebd_code>.json files, so consumers can reason over them.
        schema_text = json.dumps(EbdTable.model_json_schema(), indent=2, sort_keys=True)
        _write_json_text(output_path / "ebd.schema.json", schema_text)
        # ebd_outcomes.schema.json: the JSON Schema of the <ebd_code>.outcomes.json files.
        _write_json_text(output_path / "ebd_outcomes.schema.json", _outcomes_schema_text())
        # export_report.json: what is missing in this directory (compared to the document) and why.
        # Built last, because it checks which of the expected files actually exist.
        export_report = _build_export_report(
            all_ebd_keys.keys(), raw_issues, output_path, export_types, ebds_without_table
        )
        _write_json_text(output_path / "export_report.json", export_report.model_dump_json(indent=2))
        _write_json_text(output_path / "export_report.schema.json", _export_report_schema_text())
        click.secho(
            f"💾 Wrote index.json ({len(index.root)} EBDs), "
            f"pruefi_to_key.json ({len(pruefi_to_key)} Prüfis), ebd.schema.json, ebd_outcomes.schema.json, "
            f"export_report.json ({len(export_report.issues)} issues) and export_report.schema.json",
            fg="green",
        )

    # Sort: ERRORs first, then WARNINGs
    sorted_errors = dict(sorted(error_sources.items(), key=lambda x: (x[0].startswith("[WARNING"), x[0])))
    click.secho(json.dumps(sorted_errors, indent=4))
    click.secho("🏁Finished")


if __name__ == "__main__":
    # the parameter arguments gets provided over the CLI
    main()  # pylint:disable=no-value-for-parameter
    # ⚠️ If you rename main(), you also need to refer to the new function in the pyproject.toml project.scripts section

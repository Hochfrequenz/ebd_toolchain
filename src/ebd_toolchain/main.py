"""
A small click-based script to extract all EBDs from a given .docx file (available at edi-energy.de).
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
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from rebdhuhn.graph_conversion import convert_table_to_graph
from rebdhuhn.graphviz import convert_dot_to_svg_kroki, convert_graph_to_dot
from rebdhuhn.kroki import DotToSvgConverter, Kroki
from rebdhuhn.models.ebd_graph import EbdGraph
from rebdhuhn.models.ebd_table import EbdTable, EbdTableMetaData
from rebdhuhn.models.errors import GraphConversionError, PlantumlConversionError, SvgConversionError
from rebdhuhn.plantuml import convert_graph_to_plantuml

_logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories for classifying errors by pipeline stage and severity."""

    # Errors (critical - affect primary outputs)
    SCRAPING = "ERROR:scraping"
    GRAPH_CONVERSION = "ERROR:graph_conversion"
    SVG_EXPORT = "ERROR:svg_export"
    # Warnings (non-critical - only affect secondary outputs)
    PUML_EXPORT = "WARNING:puml_export"


# pylint:disable=too-few-public-methods
class Settings(BaseSettings):
    """settings loaded from environment variable/.env file"""

    kroki_port: int = Field(alias="KROKI_PORT")
    kroki_host: str = Field(alias="KROKI_HOST")
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def _dump_puml(puml_path: Path, ebd_graph: EbdGraph) -> None:
    plantuml_code = convert_graph_to_plantuml(ebd_graph)
    with open(puml_path, "w+", encoding="utf-8") as uml_file:
        uml_file.write(plantuml_code)


def _dump_dot(dot_path: Path, ebd_graph: EbdGraph) -> None:
    dot_code = convert_graph_to_dot(ebd_graph, ebd_link_template="?ebd={ebd_code}")
    # the ?ebd=... relative link should work on ebd.hochfrequenz.de... hopefully
    with open(dot_path, "w+", encoding="utf-8") as uml_file:
        uml_file.write(dot_code)


def _dump_svg(svg_path: Path, ebd_graph: EbdGraph, converter: DotToSvgConverter) -> None:
    dot_code = convert_graph_to_dot(ebd_graph, ebd_link_template="?ebd={ebd_code}")
    svg_code = convert_dot_to_svg_kroki(dot_code, converter)
    with open(svg_path, "w+", encoding="utf-8") as svg_file:
        svg_file.write(svg_code)


def _dump_json(json_path: Path, ebd_table: EbdTable | EbdTableMetaData) -> None:
    with open(json_path, "w+", encoding="utf-8") as json_file:
        json.dump(ebd_table.model_dump(mode="json"), json_file, ensure_ascii=False, indent=2, sort_keys=True)


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
    help="Choose which file you'd like to create",
)
def main(input_path: Path, output_path: Path, export_types: list[Literal["puml", "dot", "json", "svg"]]) -> None:
    """
    A program to get a machine-readable version of the AHBs docx files published by edi@energy.
    """
    _main(input_path, output_path, export_types)


# pylint:disable=too-many-locals, too-many-branches, too-many-statements,
def _main(input_path: Path, output_path: Path, export_types: list[Literal["puml", "dot", "json", "svg"]]) -> None:
    """same as main but without the click decorators"""
    settings = Settings()  # type:ignore[call-arg]
    # read settings from environment variable/.env file
    kroki_client = Kroki(kroki_host=f"http://{settings.kroki_host}:{settings.kroki_port}")
    if output_path.exists() and output_path.is_dir():
        click.secho(f"The output directory '{output_path}' exists already. Will remove its content.", fg="yellow")
        for item in output_path.iterdir():
            if item.is_file():
                item.unlink()
    output_path.mkdir(parents=True, exist_ok=True)
    click.secho(f"Created a new directory at {output_path}", fg="green")
    all_ebd_keys = get_all_ebd_keys(input_path)
    error_sources: dict[str, list[str]] = {}

    def handle_known_error(error: Exception, ebd_key: str, category: ErrorCategory) -> None:
        color = "yellow" if category == ErrorCategory.PUML_EXPORT else "red"
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
            handle_known_error(table_not_found_error, ebd_key, ErrorCategory.SCRAPING)
            continue
        except EbdTableNotConvertibleError as not_convertible_error:
            handle_known_error(not_convertible_error, ebd_key, ErrorCategory.SCRAPING)
            continue
        assert ebd_kapitel is not None
        assert ebd_kapitel.subsection_title is not None
        try:
            if isinstance(docx_tables, EbdNoTableSection):
                ebd_meta_data = EbdTableMetaData(
                    ebd_code=ebd_key,
                    ebd_name=ebd_kapitel.subsection_title,
                    chapter=ebd_kapitel.chapter_title,  # type:ignore[arg-type]
                    # pylint:disable=line-too-long
                    section=f"{ebd_kapitel.chapter}.{ebd_kapitel.section}.{ebd_kapitel.subsection}: {ebd_kapitel.section_title}",
                    role="N/A",
                    remark=docx_tables.remark,  # pylint:disable=no-member
                )
                ebd_table = EbdTable(metadata=ebd_meta_data, rows=[])

            else:
                converter = DocxTableConverter(
                    docx_tables,
                    ebd_key=ebd_key,
                    ebd_name=ebd_kapitel.subsection_title,
                    chapter=ebd_kapitel.chapter_title,  # type:ignore[arg-type]
                    # pylint:disable=line-too-long
                    section=f"{ebd_kapitel.chapter}.{ebd_kapitel.section}.{ebd_kapitel.subsection}: {ebd_kapitel.section_title}",
                )
                ebd_table = converter.convert_docx_tables_to_ebd_table()
        except Exception as scraping_error:  # pylint:disable=broad-except
            handle_known_error(scraping_error, ebd_key, ErrorCategory.SCRAPING)
            continue
        if "json" in export_types:
            json_path = output_path / Path(f"{ebd_key}.json")
            _dump_json(json_path, ebd_table)
            click.secho(f"💾 Successfully exported '{ebd_key}.json' to {json_path.absolute()}")
        try:
            ebd_graph = convert_table_to_graph(ebd_table)
        except GraphConversionError as graph_error:
            handle_known_error(graph_error, ebd_key, ErrorCategory.GRAPH_CONVERSION)
            continue
        except Exception as unknown_error:  # pylint:disable=broad-except
            handle_known_error(unknown_error, ebd_key, ErrorCategory.GRAPH_CONVERSION)
            continue
        if "puml" in export_types:
            if not any(ebd_table.rows):
                click.secho(f"EBD {ebd_key} has no ebd table; Skip puml creation!", fg="yellow")
            else:
                try:
                    puml_path = output_path / Path(f"{ebd_key}.puml")
                    _dump_puml(puml_path, ebd_graph)
                    click.secho(f"💾 Successfully exported '{ebd_key}.puml' to {puml_path.absolute()}")
                except PlantumlConversionError as puml_error:
                    handle_known_error(puml_error, ebd_key, ErrorCategory.PUML_EXPORT)
                except (AssertionError, Exception) as general_error:  # pylint:disable=broad-exception-caught
                    handle_known_error(general_error, ebd_key, ErrorCategory.PUML_EXPORT)

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
            handle_known_error(svg_error, ebd_key, ErrorCategory.SVG_EXPORT)
        except (AssertionError, Exception) as general_error:  # pylint:disable=broad-exception-caught
            # both the SVG and dot path require graphviz to work, hence the common error handling block
            handle_known_error(general_error, ebd_key, ErrorCategory.SVG_EXPORT)
    # Sort: ERRORs first, then WARNINGs
    sorted_errors = dict(sorted(error_sources.items(), key=lambda x: (x[0].startswith("[WARNING"), x[0])))
    click.secho(json.dumps(sorted_errors, indent=4))
    click.secho("🏁Finished")


if __name__ == "__main__":
    # the parameter arguments gets provided over the CLI
    main()  # pylint:disable=no-value-for-parameter
    # ⚠️ If you rename main(), you also need to refer to the new function in the pyproject.toml project.scripts section

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
from pathlib import Path
from typing import Literal

import cattrs
import click
from ebdamame import EbdNoTableSection, TableNotFoundError, get_all_ebd_keys, get_ebd_docx_tables
from ebdamame.docxtableconverter import DocxTableConverter
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from rebdhuhn.graph_conversion import convert_table_to_graph
from rebdhuhn.graphviz import convert_dot_to_svg_kroki, convert_graph_to_dot
from rebdhuhn.kroki import DotToSvgConverter, Kroki, KrokiDotBadRequestError, KrokiPlantUmlBadRequestError
from rebdhuhn.models.ebd_graph import EbdGraph
from rebdhuhn.models.ebd_table import EbdTable, EbdTableMetaData
from rebdhuhn.models.errors import (
    EbdCrossReferenceNotSupportedError,
    EndeInWrongColumnError,
    GraphTooComplexForPlantumlError,
    NotExactlyTwoOutgoingEdgesError,
    OutcomeCodeAmbiguousError,
    PathsNotGreaterThanOneError,
)
from rebdhuhn.plantuml import convert_graph_to_plantuml

_logger = logging.getLogger(__name__)


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
    dot_code = convert_graph_to_dot(ebd_graph)
    with open(dot_path, "w+", encoding="utf-8") as uml_file:
        uml_file.write(dot_code)


def _dump_svg(svg_path: Path, ebd_graph: EbdGraph, converter: DotToSvgConverter) -> None:
    dot_code = convert_graph_to_dot(ebd_graph)
    svg_code = convert_dot_to_svg_kroki(dot_code, converter)
    with open(svg_path, "w+", encoding="utf-8") as svg_file:
        svg_file.write(svg_code)


def _dump_json(json_path: Path, ebd_table: EbdTable | EbdNoTableSection | EbdTableMetaData) -> None:
    with open(json_path, "w+", encoding="utf-8") as json_file:
        json.dump(cattrs.unstructure(ebd_table), json_file, ensure_ascii=False, indent=2, sort_keys=True)
        if isinstance(ebd_table, EbdTableMetaData):
            json.dump(
                cattrs.unstructure(EbdTable(metadata=ebd_table, rows=[])),
                json_file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        else:
            json.dump(cattrs.unstructure(ebd_table), json_file, ensure_ascii=False, indent=2, sort_keys=True)


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
    if output_path.exists():
        click.secho(f"The output directory '{output_path}' exists already.", fg="yellow")
    else:
        output_path.mkdir(parents=True)
        click.secho(f"Created a new directory at {output_path}", fg="green")
    all_ebd_keys = get_all_ebd_keys(input_path)
    error_sources: dict[type, list[str]] = {}

    def handle_known_error(error: Exception, ebd_key: str) -> None:
        click.secho(f"Error while processing EBD {ebd_key}: {error}", fg="yellow")
        if type(error) not in error_sources:
            error_sources[type(error)] = []
        error_sources[type(error)].append(ebd_key)

    for ebd_key, (ebd_title, ebd_kapitel) in all_ebd_keys.items():
        click.secho(f"Processing EBD {ebd_kapitel} '{ebd_key}' ({ebd_title})")
        try:
            docx_tables = get_ebd_docx_tables(docx_file_path=input_path, ebd_key=ebd_key)
        except TableNotFoundError as table_not_found_error:
            click.secho(f"Table not found: {ebd_key}: {str(table_not_found_error)}; Skip!", fg="yellow")
            continue
        assert ebd_kapitel is not None
        if isinstance(docx_tables, EbdNoTableSection):
            if "json" in export_types:
                ebd_meta_data = EbdTableMetaData(
                    ebd_code=ebd_key,
                    ebd_name=ebd_kapitel.section_title,
                    chapter=ebd_kapitel.chapter_title,  # type:ignore[arg-type]
                    # pylint:disable=line-too-long
                    section=f"{ebd_kapitel.chapter}.{ebd_kapitel.section}.{ebd_kapitel.subsection}: {ebd_kapitel.section_title}",
                    role="N/A",
                    remark=docx_tables.remark,
                )
                json_path = output_path / Path(f"{ebd_key}.json")
                _dump_json(json_path, ebd_meta_data)
                click.secho(f"💾 Successfully exported '{ebd_key}.json' to {json_path.absolute()}")
        try:
            converter = DocxTableConverter(
                docx_tables,
                ebd_key=ebd_key,
                # pylint: disable=fixme
                ebd_name=ebd_key,  # todo: use real ebd_name, this is just a placeholder for now
                chapter=ebd_kapitel.chapter_title,  # type:ignore[arg-type]
                # pylint:disable=line-too-long
                section=f"{ebd_kapitel.chapter}.{ebd_kapitel.section}.{ebd_kapitel.subsection}: {ebd_kapitel.section_title}",
            )
            ebd_table = converter.convert_docx_tables_to_ebd_table()
        except Exception as scraping_error:  # pylint:disable=broad-except
            click.secho(f"Error while scraping {ebd_key}: {str(scraping_error)}; Skip!", fg="red")
            continue
        if "json" in export_types:
            json_path = output_path / Path(f"{ebd_key}.json")
            _dump_json(json_path, ebd_table)
            click.secho(f"💾 Successfully exported '{ebd_key}.json' to {json_path.absolute()}")
        try:
            ebd_graph = convert_table_to_graph(ebd_table)
        except (EbdCrossReferenceNotSupportedError, EndeInWrongColumnError, OutcomeCodeAmbiguousError) as known_issue:
            handle_known_error(known_issue, ebd_key)
            continue
        except Exception as unknown_error:  # pylint:disable=broad-except
            click.secho(f"Error while graphing {ebd_key}: {str(unknown_error)}; Skip!", fg="red")
            continue
        if "puml" in export_types:
            try:
                puml_path = output_path / Path(f"{ebd_key}.puml")
                _dump_puml(puml_path, ebd_graph)
                click.secho(f"💾 Successfully exported '{ebd_key}.puml' to {puml_path.absolute()}")
            except AssertionError as assertion_error:
                # https://github.com/Hochfrequenz/rebdhuhn/issues/35
                click.secho(str(assertion_error), fg="red")
            except (
                NotExactlyTwoOutgoingEdgesError,
                GraphTooComplexForPlantumlError,
                KrokiPlantUmlBadRequestError,
            ) as known_issue:
                handle_known_error(known_issue, ebd_key)
            except Exception as general_error:  # pylint:disable=broad-exception-caught
                click.secho(f"Error while exporting {ebd_key} as UML: {str(general_error)}; Skip!", fg="yellow")

        try:
            if "dot" in export_types:
                dot_path = output_path / Path(f"{ebd_key}.dot")
                _dump_dot(dot_path, ebd_graph)
                click.secho(f"💾 Successfully exported '{ebd_key}.dot' to {dot_path.absolute()}")
            if "svg" in export_types:
                svg_path = output_path / Path(f"{ebd_key}.svg")
                _dump_svg(svg_path, ebd_graph, kroki_client)
                click.secho(f"💾 Successfully exported '{ebd_key}.svg' to {svg_path.absolute()}")
        except (PathsNotGreaterThanOneError, KrokiDotBadRequestError) as known_issue:
            handle_known_error(known_issue, ebd_key)
        except AssertionError as assertion_error:
            # e.g. AssertionError: If indegree > 1, the number of paths should always be greater than 1 too.
            click.secho(str(assertion_error), fg="red")
            # both the SVG and dot path require graphviz to work, hence the common error handling block
    click.secho(json.dumps({str(k): v for k, v in error_sources.items()}, indent=4))
    click.secho("🏁Finished")


if __name__ == "__main__":
    # the parameter arguments gets provided over the CLI
    main()  # pylint:disable=no-value-for-parameter
    # ⚠️ If you rename main(), you also need to refer to the new function in the pyproject.toml project.scripts section

"""
This module downloads the AHB SQLite database from the xml-migs-and-ahbs GitHub release
and queries the EBD-to-Pruefidentifikator mapping from the v_ahbtabellen view.
"""

import json
import logging
import tempfile
from pathlib import Path

import py7zr
import requests
from efoli import EdifactFormatVersion
from rebdhuhn.models.ebd_table import EbdPruefidentifikator
from sqlmodel import Session, create_engine, text

_logger = logging.getLogger(__name__)


def download_ahb_db(github_token: str, target_dir: Path | None = None) -> Path:
    """
    Downloads the unencrypted AHB SQLite database from the latest xml-migs-and-ahbs release.
    Returns the path to the extracted .db file.
    """
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }
    # Get the latest release
    release_url = "https://api.github.com/repos/Hochfrequenz/xml-migs-and-ahbs/releases/latest"
    response = requests.get(release_url, headers=headers, timeout=30)
    response.raise_for_status()
    release_data = response.json()

    # Find the unencrypted .db.7z asset (not .encrypted.7z)
    db_asset = None
    for asset in release_data["assets"]:
        if asset["name"].endswith(".db.7z") and ".encrypted." not in asset["name"]:
            db_asset = asset
            break

    if db_asset is None:
        raise FileNotFoundError("No unencrypted .db.7z asset found in the latest release")

    _logger.info("Downloading AHB database: %s", db_asset["name"])

    # Download the asset
    download_url = db_asset["url"]
    download_response = requests.get(
        download_url,
        headers={**headers, "Accept": "application/octet-stream"},
        timeout=300,
    )
    download_response.raise_for_status()

    if target_dir is None:
        target_dir = Path(tempfile.mkdtemp(prefix="ahb_db_"))
    target_dir.mkdir(parents=True, exist_ok=True)

    archive_path = target_dir / db_asset["name"]
    archive_path.write_bytes(download_response.content)

    # Extract the .7z archive
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        archive.extractall(path=target_dir)
    archive_path.unlink()

    # Find the extracted .db file
    db_files = list(target_dir.glob("*.db"))
    if not db_files:
        raise FileNotFoundError(f"No .db file found after extracting {archive_path}")

    _logger.info("AHB database extracted to: %s", db_files[0])
    return db_files[0]


def get_ebd_to_pruefis_mapping(
    db_path: Path, format_version: str | None = None
) -> dict[str, list[EbdPruefidentifikator]]:
    """
    Queries the v_ahbtabellen view for EBD qualifiers and returns a mapping
    from EBD code (e.g. 'E_0003') to a list of EbdPruefidentifikator objects.

    Uses REGEXP and GROUP BY in SQLite to do all filtering and aggregation in the database.

    Args:
        db_path: Path to the AHB SQLite database file.
        format_version: Optional format version filter (e.g. 'FV2610').
            If None, returns mappings across all format versions.
    """
    engine = create_engine(f"sqlite:///{db_path}")

    sql = """
        SELECT v_ahbtabellen.format_version,
               qualifier AS ebd_key,
               JSON_GROUP_ARRAY(DISTINCT pruefidentifikator) AS pruefidentifikatoren
        FROM v_ahbtabellen
        WHERE qualifier REGEXP 'E_[0-9]+'
    """
    params: dict[str, str] = {}
    if format_version is not None:
        sql += " AND format_version = :fv"
        params["fv"] = format_version
    sql += " GROUP BY v_ahbtabellen.format_version, qualifier ORDER BY v_ahbtabellen.format_version DESC, ebd_key"

    with Session(bind=engine) as session:
        results = session.exec(text(sql), params=params).all()  # type: ignore[call-overload]

    mapping: dict[str, list[EbdPruefidentifikator]] = {}
    for fv, ebd_key, pruefis_json in results:
        pruefis: list[str] = json.loads(pruefis_json)
        mapping[ebd_key] = sorted(
            [EbdPruefidentifikator(format_version=EdifactFormatVersion(fv), pruefidentifikator=pi) for pi in pruefis],
            key=lambda p: p.pruefidentifikator,
        )

    return mapping

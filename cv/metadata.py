"""
Dates d'une candidature (cv/applications/<cv_id>/metadata.json), en UTC :

    {"schema_version": 1, "created_at": "2026-10-22T10:15:03.123456Z", "updated_at": "..."}

created_at est écrit une seule fois, à la création du dossier (write_cv), et n'est jamais modifié ;
updated_at change à chaque modification enregistrée du CV (PUT /api/cvs/{cv_id}).

Les dates du système de fichiers ne suffisent pas : le dossier est copié depuis cv/template et
shutil.copytree lui donne la date du template. Pour les CV créés avant ce fichier, seule une date
fiable est reprise (création de offer.json, écrit une seule fois par write_cv) ; sinon la date
reste inconnue (None). Les dossiers existants ne sont jamais modifiés automatiquement.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

METADATA_FILE = "metadata.json"
SCHEMA_VERSION = 1


def now_utc() -> str:
    """Horodatage ISO 8601 en UTC, ex. « 2026-10-22T10:15:03.123456Z »."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def to_timestamp(value) -> float | None:
    """« 2026-10-22T10:15:03.123456Z » -> secondes Unix (UTC) ; None si la valeur n'est pas une date valide."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:                       # sans fuseau : non fiable, on ne devine pas
        return None
    return moment.timestamp()


def _write(folder: Path, data: dict) -> None:
    path = Path(folder) / METADATA_FILE
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as temporary:
        temporary.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary.name, path)


def read_metadata(folder: Path) -> dict | None:
    """Le contenu de metadata.json, ou None s'il est absent ou illisible."""
    try:
        data = json.loads((Path(folder) / METADATA_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def create_metadata(folder: Path, created_at: str | None = None) -> dict:
    """Écrit metadata.json à la création de la candidature (created_at = updated_at = maintenant)."""
    stamp = created_at or now_utc()
    data = {"schema_version": SCHEMA_VERSION, "created_at": stamp, "updated_at": stamp}
    _write(folder, data)
    return data


def mark_updated(folder: Path) -> None:
    """
    Met à jour updated_at après une modification enregistrée. created_at est conservé tel quel ;
    un CV sans metadata.json (créé avant) n'en reçoit pas : sa date de création reste celle qu'on sait retrouver.
    """
    data = read_metadata(folder)
    if data is None:
        return
    _write(folder, {**data, "updated_at": now_utc()})


def _legacy_created_at(folder: Path) -> float | None:
    """
    Date de création d'un CV sans metadata.json : la création de offer.json, que write_cv écrit
    une seule fois (jamais copié depuis le template ni réécrit ensuite). Seulement si le système
    fournit une vraie date de création (st_birthtime, macOS) ; st_ctime n'en est pas une.
    """
    try:
        stat = (Path(folder) / "offer.json").stat()
    except OSError:
        return None
    return getattr(stat, "st_birthtime", None)


def cv_dates(folder: Path, fallback_updated_at: float) -> tuple[float | None, float]:
    """
    (created_at, updated_at) en secondes Unix UTC pour l'API. created_at vaut None quand aucune date
    fiable n'existe. updated_at : metadata.json, sinon `fallback_updated_at` (dernière écriture du CV ou du PDF).
    """
    data = read_metadata(folder)
    if data is not None and to_timestamp(data.get("created_at")) is not None:
        created = to_timestamp(data["created_at"])
        updated = to_timestamp(data.get("updated_at"))
        return created, max(updated, created) if updated is not None else max(fallback_updated_at, created)
    return _legacy_created_at(folder), fallback_updated_at

"""Lecture et écriture des fichiers JSON de la préparation (dans le dossier de la candidature)."""

import json
import os
import tempfile
from pathlib import Path


def write_json(path: Path, data: dict) -> Path:
    """Fichier temporaire puis remplacement : jamais de fichier à moitié écrit."""
    path = Path(path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as temporary:
        temporary.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary.name, path)
    return path


def read_json(path: Path) -> dict | None:
    """Le contenu du fichier s'il existe et est un objet JSON, sinon None."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None

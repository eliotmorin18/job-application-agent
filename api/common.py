"""Éléments partagés par les routes de l'API (api/main.py, api/cvs.py)."""

from pathlib import Path

from candidate import profile as profile_module


def profile_path() -> Path:
    """Profil candidat utilisé par l'API (remplacé par un profil temporaire dans les tests)."""
    return profile_module.CANDIDATE_PATH


class ApiError(Exception):
    """Erreur renvoyée au frontend : {"detail": {"message": ..., "problems": [...]}}."""

    def __init__(self, status: int, message: str, problems: list[str] | None = None):
        self.status, self.message, self.problems = status, message, problems or [message]

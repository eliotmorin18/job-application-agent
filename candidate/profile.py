"""
Lecture et validation du profil candidat (profile/private/candidate.yaml).

Le profil peut être construit petit à petit : seuls le prénom et le nom sont
obligatoires. Les sections absentes ou laissées vides (`null` en YAML) sont
remplacées par une valeur vide. Les erreurs sont toutes signalées d'un coup,
avec un message lisible, avant tout appel à Claude.

Réutilisable par la future gestion du profil et par l'import de CV.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "profile" / "private" / "candidate.yaml"
EXAMPLE_PATH = ROOT / "profile" / "candidate.example.yaml"

# Sections facultatives et leur valeur quand elles sont absentes ou vides
OPTIONAL_LISTS = ["education", "experiences", "projects", "languages", "interests", "awards"]
OPTIONAL_DICTS = ["career", "skills", "preferences", "form_answers", "application_rules"]

LIMITS = ["max_cv_experiences", "max_cv_projects"]


@dataclass(frozen=True)
class CandidateProfile:
    """
    Profil candidat lu une seule fois et partagé par tout le pipeline.
    - data : version validée (sections absentes ou null remplacées par du vide),
      utilisée par Python pour ses contrôles (ids, limites, prénom et nom)
    - text : le fichier tel qu'il est écrit, envoyé à Claude pour rédiger et vérifier le CV
    """

    data: dict
    text: str
    path: Path


class ProfileError(Exception):
    """Le profil ne permet pas de générer un CV. `problems` liste les raisons."""

    def __init__(self, problems: list[str], path: Path | None = None):
        self.problems = problems
        where = f" ({path})" if path else ""
        lines = [f"Profil candidat invalide{where} :"] + [f"  - {problem}" for problem in problems]
        super().__init__("\n".join(lines))


def _is_text(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def validate_profile(data) -> dict:
    """
    Vérifie un profil déjà chargé (dict issu du YAML) et renvoie une copie normalisée :
    sections facultatives absentes ou `null` remplacées par [] ou {}.
    Lève ProfileError avec la liste de tous les problèmes trouvés.
    """

    if data is None:
        raise ProfileError(["le profil est vide : renseigne au moins personal.first_name et personal.last_name."])
    if not isinstance(data, dict):
        raise ProfileError(["le profil doit être une suite de sections (personal:, experiences:...), pas une liste ou un texte."])

    problems = []
    profile = dict(data)

    # Identité : seul élément indispensable (prénom et nom servent au CV et au nom du PDF)
    personal = profile.get("personal")
    if personal is None:
        problems.append("la section « personal » est manquante : ajoute personal.first_name et personal.last_name.")
        personal = {}
    elif not isinstance(personal, dict):
        problems.append("la section « personal » doit contenir des champs (first_name:, last_name:...).")
        personal = {}
    else:
        for field in ("first_name", "last_name"):
            if not _is_text(personal.get(field)):
                problems.append(f"personal.{field} est obligatoire et doit être un texte non vide.")
    profile["personal"] = personal

    # Sections facultatives : absentes ou null -> vides
    for key in OPTIONAL_LISTS:
        value = profile.get(key)
        if value is None:
            profile[key] = []
        elif not isinstance(value, list):
            problems.append(f"« {key} » doit être une liste (chaque élément commence par « - »).")
            profile[key] = []

    for key in OPTIONAL_DICTS:
        value = profile.get(key)
        if value is None:
            profile[key] = {}
        elif not isinstance(value, dict):
            problems.append(f"« {key} » doit contenir des champs (nom: valeur), pas une liste ou un texte.")
            profile[key] = {}

    # Expériences et projets : chaque élément a un id unique (dans tout le profil)
    seen: dict[str, str] = {}
    for key, label in (("experiences", "expérience"), ("projects", "projet")):
        for number, item in enumerate(profile[key], start=1):
            where = f"{label} n°{number}"
            if not isinstance(item, dict):
                problems.append(f"{where} : doit contenir des champs (id:, ...), pas un simple texte.")
                continue

            name = item.get("company") or item.get("name") or item.get("title")
            if _is_text(name):
                where += f" (« {name} »)"

            item_id = item.get("id")
            if not _is_text(item_id):
                problems.append(f"{where} : il manque un « id » (un identifiant court et unique, par ex. « mon-stage-2025 »).")
            elif item_id in seen:
                problems.append(f"{where} : l'id « {item_id} » est déjà utilisé par {seen[item_id]}.")
            else:
                seen[item_id] = where

    # Limites du nombre d'éléments sur le CV : facultatives, mais des entiers si présentes
    rules = profile["application_rules"]
    for limit in LIMITS:
        value = rules.get(limit)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            problems.append(f"application_rules.{limit} doit être un nombre entier positif (ou être retiré).")

    if problems:
        raise ProfileError(problems)

    return profile


def load_profile(path: Path | None = None) -> CandidateProfile:
    """Lit et valide le profil. Lève ProfileError avec un message lisible si besoin."""

    path = Path(path) if path else CANDIDATE_PATH

    if not path.exists():
        raise ProfileError(
            [f"le fichier n'existe pas. Crée-le à partir de l'exemple : cp {EXAMPLE_PATH.relative_to(ROOT)} {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"],
            path,
        )

    text = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        line = f" (ligne {mark.line + 1})" if mark else ""
        raise ProfileError([f"le fichier n'est pas un YAML valide{line} : vérifie l'indentation et les « : »."], path)

    try:
        return CandidateProfile(data=validate_profile(data), text=text, path=path)
    except ProfileError as error:
        raise ProfileError(error.problems, path)

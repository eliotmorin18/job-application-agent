"""
Modification du profil candidat (profile/private/candidate.yaml).

L'écriture utilise ruamel.yaml, qui conserve les commentaires, l'ordre des champs
et la mise en forme du fichier (PyYAML les effacerait). La lecture et la
validation restent celles de candidate/profile.py.

Réutilisable par le futur frontend : chaque fonction reçoit des données simples
(dict, listes, textes) et renvoie un résultat simple.
"""

import io
import os
import re
import tempfile
import unicodedata
from pathlib import Path

import yaml as pyyaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from candidate import profile as profile_module
from candidate.profile import ProfileError, load_profile, validate_profile


# Champs d'une expérience, dans l'ordre où ils sont écrits dans le fichier
EXPERIENCE_TEXT_FIELDS = ["company", "title", "start_date", "end_date", "location", "priority", "context", "description"]
EXPERIENCE_LIST_FIELDS = ["tags", "responsibilities", "achievements", "skills"]
EXPERIENCE_REQUIRED = ["company", "title"]

PRIORITIES = ["high", "medium", "low"]
DATE_PATTERN = re.compile(r"^\d{4}(-\d{2})?$")  # "2025" ou "2025-09"


class ExperienceError(ValueError):
    """Les informations de la nouvelle expérience sont incomplètes ou incorrectes."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Expérience invalide :\n" + "\n".join(f"  - {problem}" for problem in problems))


def _yaml() -> YAML:
    """Même mise en forme que le profil : 2 espaces, listes « - » décalées de 2."""
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096  # ne pas recouper les longues lignes
    return yaml


def _scalar(value: str, quote: bool = False):
    """
    Texte à écrire dans le YAML. Entre guillemets si demandé (dates, comme dans le profil)
    ou si le lecteur du profil (PyYAML) le relirait autrement : « 2025 » (nombre),
    « yes » / « no » / « on » (vrai ou faux), « null »...
    """
    if quote or pyyaml.safe_load(value) != value:
        return DoubleQuotedScalarString(value)
    return value


def _slug(text: str) -> str:
    """« CNRS Foundation - via Aubay » -> « cnrs-foundation-via-aubay »"""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "-".join(re.findall(r"[a-z0-9]+", ascii_text.lower()))


def _unique_id(base: str, existing: set[str]) -> str:
    candidate_id = base or "experience"
    number = 2
    while candidate_id in existing:
        candidate_id = f"{base or 'experience'}-{number}"
        number += 1
    return candidate_id


def _clean_experience(fields: dict) -> CommentedMap:
    """
    Vérifie et nettoie les informations reçues. Les champs facultatifs vides
    (None, "", [], espaces) sont simplement omis.
    """

    problems = []
    known = set(EXPERIENCE_TEXT_FIELDS) | set(EXPERIENCE_LIST_FIELDS)

    unknown = sorted(set(fields) - known - {"id"})
    if unknown:
        problems.append(f"champ(s) inconnu(s) : {', '.join(unknown)}. Champs possibles : {', '.join(EXPERIENCE_TEXT_FIELDS + EXPERIENCE_LIST_FIELDS)}.")
    if "id" in fields:
        problems.append("l'id est généré automatiquement : ne le fournis pas.")

    experience = CommentedMap()

    for field in EXPERIENCE_TEXT_FIELDS:
        value = fields.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            if field in EXPERIENCE_REQUIRED:
                problems.append(f"« {field} » est obligatoire.")
            continue
        if not isinstance(value, str):
            problems.append(f"« {field} » doit être un texte.")
            continue
        value = value.strip()
        if field in ("start_date", "end_date") and not DATE_PATTERN.match(value):
            problems.append(f"« {field} » doit avoir la forme « AAAA » ou « AAAA-MM » (reçu : « {value} »).")
            continue
        if field == "priority" and value not in PRIORITIES:
            problems.append(f"« priority » doit valoir {', '.join(PRIORITIES)} (reçu : « {value} »).")
            continue
        experience[field] = _scalar(value, quote=field in ("start_date", "end_date"))

    for field in EXPERIENCE_LIST_FIELDS:
        value = fields.get(field)
        if value is None:
            continue
        if isinstance(value, str) or not all(isinstance(item, str) for item in value):
            problems.append(f"« {field} » doit être une liste de textes.")
            continue
        items = [_scalar(item.strip()) for item in value if item.strip()]
        if items:
            experience[field] = CommentedSeq(items)

    if "start_date" in experience and "end_date" in experience and experience["end_date"] < experience["start_date"]:
        problems.append("« end_date » est avant « start_date ».")

    if problems:
        raise ExperienceError(problems)

    return experience


def _to_text(data) -> str:
    buffer = io.StringIO()
    _yaml().dump(data, buffer)
    return buffer.getvalue()


def _write_atomically(path: Path, text: str) -> None:
    """Écrit dans un fichier temporaire puis le met à la place : jamais de fichier à moitié écrit."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as temporary:
        temporary.write(text)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, path)


def add_experience(fields: dict, path: Path | None = None) -> str:
    """
    Ajoute une expérience professionnelle au profil et renvoie son id (généré à
    partir de l'entreprise, rendu unique dans tout le profil).

    `fields` : company et title obligatoires ; start_date, end_date, location,
    priority, context, description (textes) et tags, responsibilities,
    achievements, skills (listes de textes) facultatifs.

    Le profil doit être valide avant la modification et l'est encore après ;
    sinon rien n'est écrit. Lève ProfileError ou ExperienceError.
    """

    path = Path(path) if path else profile_module.CANDIDATE_PATH

    # 1. Le profil actuel doit être lisible et valide (sinon on ne l'aggrave pas)
    current = load_profile(path)

    # 2. La nouvelle expérience, nettoyée, avec un id unique
    experience = _clean_experience(fields)
    existing_ids = {item["id"] for item in current.data["experiences"] + current.data["projects"]}
    new_id = _unique_id(_slug(experience["company"]), existing_ids)

    entry = CommentedMap()
    entry["id"] = _scalar(new_id)
    entry.update(experience)

    # 3. Ajout dans le fichier, en conservant commentaires et mise en forme
    data = _yaml().load(path.read_text(encoding="utf-8"))
    # Absente, « experiences: » sans valeur, ou « experiences: [] » écrit sur une ligne :
    # on part d'une liste vide classique (une « - » par élément)
    if not data.get("experiences"):
        data["experiences"] = CommentedSeq()
    data["experiences"].append(entry)

    # 4. Le texte exact qui va être écrit est relu comme le fera le pipeline (PyYAML) :
    #    il doit être valide et contenir la nouvelle expérience, sinon le fichier n'est pas touché
    text = _to_text(data)
    try:
        written = validate_profile(pyyaml.safe_load(text))
    except ProfileError as error:
        raise ProfileError(error.problems, path)
    if new_id not in {item["id"] for item in written["experiences"]}:
        raise ProfileError([f"l'expérience « {new_id} » ne serait pas relue correctement : rien n'a été enregistré."], path)

    _write_atomically(path, text)
    return new_id

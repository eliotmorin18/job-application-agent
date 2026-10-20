"""
Modification du profil candidat (profile/private/candidate.yaml).

L'écriture utilise ruamel.yaml, qui conserve les commentaires, l'ordre des champs
et la mise en forme du fichier (PyYAML les effacerait). La lecture et la
validation restent celles de candidate/profile.py.

Chaque type d'élément (expérience, projet, formation) est décrit une seule fois
dans ITEM_KINDS ; l'ajout est le même pour tous.

Réutilisable par le futur frontend : chaque fonction reçoit des données simples
(dict, listes, textes) et renvoie un résultat simple.
"""

import io
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml as pyyaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from candidate import profile as profile_module
from candidate.profile import ProfileError, load_profile, validate_profile


PRIORITIES = ["high", "medium", "low"]
DATE_PATTERN = re.compile(r"^\d{4}(-\d{2})?$")  # "2025" ou "2025-09"
DATE_FIELDS = ("start_date", "end_date")


@dataclass(frozen=True)
class ItemKind:
    """Un type d'élément du profil et ses champs."""

    section: str             # liste du YAML où l'élément est ajouté
    label: str               # nom affiché dans les messages
    fields: tuple[str, ...]  # champs possibles, dans l'ordre où ils sont écrits
    list_fields: frozenset   # parmi eux, ceux qui sont des listes de textes
    required: tuple[str, ...]
    id_from: str             # champ qui sert à créer l'id


ITEM_KINDS = {
    "experience": ItemKind(
        section="experiences",
        label="expérience",
        fields=("company", "title", "start_date", "end_date", "location", "priority", "tags",
                "context", "description", "responsibilities", "achievements", "skills"),
        list_fields=frozenset({"tags", "responsibilities", "achievements", "skills"}),
        required=("company", "title"),
        id_from="company",
    ),
    "project": ItemKind(
        section="projects",
        label="projet",
        fields=("name", "start_date", "end_date", "priority", "tags", "context", "description",
                "responsibilities", "achievements", "skills", "github_url"),
        list_fields=frozenset({"tags", "responsibilities", "achievements", "skills"}),
        required=("name",),
        id_from="name",
    ),
    "education": ItemKind(
        section="education",
        label="formation",
        fields=("school", "degree", "specialization", "start_date", "end_date", "location", "details"),
        list_fields=frozenset({"details"}),
        required=("school",),
        id_from="school",
    ),
}


class ItemError(ValueError):
    """Les informations du nouvel élément sont incomplètes ou incorrectes."""

    def __init__(self, label: str, problems: list[str]):
        self.problems = problems
        super().__init__(f"{label.capitalize()} invalide :\n" + "\n".join(f"  - {problem}" for problem in problems))


# Ancien nom, gardé pour ne rien casser
ExperienceError = ItemError


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


def _unique_id(base: str, existing: set[str], fallback: str) -> str:
    base = base or fallback
    candidate_id = base
    number = 2
    while candidate_id in existing:
        candidate_id = f"{base}-{number}"
        number += 1
    return candidate_id


def _clean_item(kind: ItemKind, fields: dict) -> CommentedMap:
    """
    Vérifie et nettoie les informations reçues. Les champs facultatifs vides
    (None, "", [], espaces) sont simplement omis.
    """

    problems = []

    unknown = sorted(set(fields) - set(kind.fields) - {"id"})
    if unknown:
        problems.append(f"champ(s) inconnu(s) : {', '.join(unknown)}. Champs possibles : {', '.join(kind.fields)}.")
    if "id" in fields:
        problems.append("l'id est généré automatiquement : ne le fournis pas.")

    item = CommentedMap()

    for field in kind.fields:
        value = fields.get(field)

        if field in kind.list_fields:
            if value is None:
                continue
            if isinstance(value, str) or not all(isinstance(entry, str) for entry in value):
                problems.append(f"« {field} » doit être une liste de textes.")
                continue
            entries = [_scalar(entry.strip()) for entry in value if entry.strip()]
            if entries:
                item[field] = CommentedSeq(entries)
            continue

        if value is None or (isinstance(value, str) and not value.strip()):
            if field in kind.required:
                problems.append(f"« {field} » est obligatoire.")
            continue
        if not isinstance(value, str):
            problems.append(f"« {field} » doit être un texte.")
            continue

        value = value.strip()
        if field in DATE_FIELDS and not DATE_PATTERN.match(value):
            problems.append(f"« {field} » doit avoir la forme « AAAA » ou « AAAA-MM » (reçu : « {value} »).")
            continue
        if field == "priority" and value not in PRIORITIES:
            problems.append(f"« priority » doit valoir {', '.join(PRIORITIES)} (reçu : « {value} »).")
            continue
        if field == "github_url" and not value.startswith(("http://", "https://")):
            problems.append(f"« github_url » doit commencer par http:// ou https:// (reçu : « {value} »).")
            continue

        item[field] = _scalar(value, quote=field in DATE_FIELDS)

    if "start_date" in item and "end_date" in item and item["end_date"] < item["start_date"]:
        problems.append("« end_date » est avant « start_date ».")

    if problems:
        raise ItemError(kind.label, problems)

    return item


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


def _existing_ids(profile_data: dict) -> set[str]:
    """Tous les id déjà utilisés dans le profil (expériences, projets, formations)."""
    return {
        item["id"]
        for kind in ITEM_KINDS.values()
        for item in profile_data[kind.section]
        if isinstance(item, dict) and item.get("id")
    }


def _add_item(kind: ItemKind, fields: dict, path: Path | None) -> str:
    """
    Ajoute un élément à la liste `kind.section` du profil et renvoie son id (créé à
    partir du champ `kind.id_from`, rendu unique dans tout le profil).

    Le profil doit être valide avant la modification et l'est encore après ;
    sinon rien n'est écrit. Lève ProfileError ou ItemError.
    """

    path = Path(path) if path else profile_module.CANDIDATE_PATH

    # 1. Le profil actuel doit être lisible et valide (sinon on ne l'aggrave pas)
    current = load_profile(path)

    # 2. Le nouvel élément, nettoyé, avec un id unique
    item = _clean_item(kind, fields)
    new_id = _unique_id(_slug(item[kind.id_from]), _existing_ids(current.data), fallback=_slug(kind.label))

    entry = CommentedMap()
    entry["id"] = _scalar(new_id)
    entry.update(item)

    # 3. Ajout dans le fichier, en conservant commentaires et mise en forme.
    #    Section absente, sans valeur ou « [] » écrit sur une ligne : on part d'une liste
    #    vide classique (une « - » par élément)
    data = _yaml().load(path.read_text(encoding="utf-8"))
    if not data.get(kind.section):
        data[kind.section] = CommentedSeq()
    data[kind.section].append(entry)

    # 4. Le texte exact qui va être écrit est relu comme le fera le pipeline (PyYAML) :
    #    il doit être valide et contenir le nouvel élément, sinon le fichier n'est pas touché
    text = _to_text(data)
    try:
        written = validate_profile(pyyaml.safe_load(text))
    except ProfileError as error:
        raise ProfileError(error.problems, path)
    if new_id not in {element.get("id") for element in written[kind.section] if isinstance(element, dict)}:
        raise ProfileError([f"{kind.label} « {new_id} » ne serait pas relu(e) correctement : rien n'a été enregistré."], path)

    _write_atomically(path, text)
    return new_id


def add_experience(fields: dict, path: Path | None = None) -> str:
    """
    Ajoute une expérience professionnelle et renvoie son id (créé à partir de l'entreprise).
    Obligatoires : company, title. Facultatifs : start_date, end_date, location, priority,
    context, description (textes) ; tags, responsibilities, achievements, skills (listes).
    """
    return _add_item(ITEM_KINDS["experience"], fields, path)


def add_project(fields: dict, path: Path | None = None) -> str:
    """
    Ajoute un projet et renvoie son id (créé à partir du nom).
    Obligatoire : name. Facultatifs : start_date, end_date, priority, context, description,
    github_url (textes) ; tags, responsibilities, achievements, skills (listes).
    """
    return _add_item(ITEM_KINDS["project"], fields, path)


def add_education(fields: dict, path: Path | None = None) -> str:
    """
    Ajoute une formation et renvoie son id (créé à partir de l'école).
    Obligatoire : school. Facultatifs : degree, specialization, start_date, end_date,
    location (textes) ; details (liste).
    """
    return _add_item(ITEM_KINDS["education"], fields, path)

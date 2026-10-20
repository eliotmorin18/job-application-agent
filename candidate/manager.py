"""
Modification du profil candidat (profile/private/candidate.yaml).

L'écriture utilise ruamel.yaml, qui conserve les commentaires, l'ordre des champs
et la mise en forme du fichier (PyYAML les effacerait). La lecture et la
validation restent celles de candidate/profile.py.

Chaque type d'élément (expérience, projet, formation) est décrit une seule fois
dans ITEM_KINDS ; l'ajout est le même pour tous. Les compétences, langues et
centres d'intérêt ont leur propre fonction d'ajout. Les sections uniques
(personal, career, preferences) sont décrites dans SECTION_SPECS et mises à jour
champ par champ. Toutes partagent la même lecture (_load_for_edit) et le même
enregistrement sûr (_save).

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


def _check_item_fields(kind: ItemKind, fields: dict, partial: bool) -> tuple[dict, list[str]]:
    """
    Vérifie les champs fournis pour un élément (expérience, projet, formation).
    Renvoie ({champ: valeur à écrire}, [champs vidés]).
    - partial=False (ajout) : les champs obligatoires doivent être fournis.
    - partial=True (modification) : seuls les champs fournis sont vérifiés ; un champ fourni
      vide (None, "", [], espaces) est à vider, sauf s'il est obligatoire.
    """

    problems = []

    unknown = sorted(set(fields) - set(kind.fields) - {"id"})
    if unknown:
        problems.append(f"champ(s) inconnu(s) : {', '.join(unknown)}. Champs possibles : {', '.join(kind.fields)}.")
    if "id" in fields:
        problems.append("l'id est géré automatiquement : il ne peut être ni fourni ni modifié.")

    values, cleared = {}, []

    for field in kind.fields:
        if partial and field not in fields:
            continue
        value = fields.get(field)

        if field in kind.list_fields:
            if value is not None and (isinstance(value, str) or not all(isinstance(entry, str) for entry in value)):
                problems.append(f"« {field} » doit être une liste de textes.")
                continue
            entries = [_scalar(entry.strip()) for entry in value or [] if entry.strip()]
            if entries:
                values[field] = CommentedSeq(entries)
            else:
                cleared.append(field)
            continue

        if value is None or (isinstance(value, str) and not value.strip()):
            if field in kind.required:
                problems.append(f"« {field} » est obligatoire" + (" et ne peut pas être vidé." if partial else "."))
            else:
                cleared.append(field)
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

        values[field] = _scalar(value, quote=field in DATE_FIELDS)

    if problems:
        raise ItemError(kind.label, problems)

    return values, cleared


def _check_dates(kind: ItemKind, item) -> None:
    """La fin ne peut pas être avant le début (y compris avec les dates déjà présentes)."""
    start, end = item.get("start_date"), item.get("end_date")
    if start and end and str(end) < str(start):
        raise ItemError(kind.label, ["« end_date » est avant « start_date »."])


def _clean_item(kind: ItemKind, fields: dict) -> CommentedMap:
    """Nouvel élément : champs vérifiés, champs facultatifs vides simplement omis."""
    values, _ = _check_item_fields(kind, fields, partial=False)
    item = CommentedMap((field, values[field]) for field in kind.fields if field in values)
    _check_dates(kind, item)
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


def _load_for_edit(path: Path | None):
    """
    Le profil actuel, qui doit être lisible et valide (sinon on ne l'aggrave pas), et sa
    version modifiable (ruamel.yaml, qui garde commentaires et mise en forme).
    """
    path = Path(path) if path else profile_module.CANDIDATE_PATH
    current = load_profile(path)
    data = _yaml().load(path.read_text(encoding="utf-8"))
    return path, current, data


def _save(path: Path, data, is_saved, what: str) -> None:
    """
    Enregistre `data`. Le texte exact qui va être écrit est relu comme le fera le pipeline
    (PyYAML) : il doit être valide et `is_saved(profil relu)` doit être vrai, sinon le
    fichier n'est pas touché.
    """
    text = _to_text(data)
    try:
        written = validate_profile(pyyaml.safe_load(text))
    except ProfileError as error:
        raise ProfileError(error.problems, path)
    if not is_saved(written):
        raise ProfileError([f"{what} ne serait pas relu(e) correctement : rien n'a été enregistré."], path)
    _write_atomically(path, text)


def _list_section(data, section: str) -> CommentedSeq:
    """
    La liste `section` du YAML modifiable. Absente, sans valeur ou « [] » écrit sur une
    ligne : on part d'une liste vide classique (une « - » par élément).
    """
    if not data.get(section):
        data[section] = CommentedSeq()
    return data[section]


def _clean_text(value, label: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ItemError(label, [f"« {field} » est obligatoire et doit être un texte non vide."])
    return value.strip()


def _same(a, b) -> bool:
    """Comparaison qui ignore majuscules et espaces : « python » = « Python »."""
    return isinstance(a, str) and isinstance(b, str) and a.strip().casefold() == b.strip().casefold()


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

    path, current, data = _load_for_edit(path)

    # Le nouvel élément, nettoyé, avec un id unique
    item = _clean_item(kind, fields)
    new_id = _unique_id(_slug(item[kind.id_from]), _existing_ids(current.data), fallback=_slug(kind.label))

    entry = CommentedMap()
    entry["id"] = _scalar(new_id)
    entry.update(item)

    _list_section(data, kind.section).append(entry)

    _save(
        path, data,
        lambda written: new_id in {element.get("id") for element in written[kind.section] if isinstance(element, dict)},
        f"{kind.label} « {new_id} »",
    )
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


def _category_key(text: str) -> str:
    """Nom de catégorie au format du profil : « Machine Learning » -> « machine_learning »."""
    return _slug(text).replace("-", "_")


def add_skill(skill: str, category: str, path: Path | None = None, create_category: bool = False) -> str:
    """
    Ajoute une compétence dans une catégorie de `skills` (ex. « Python » dans
    « programming ») et renvoie le nom de la catégorie utilisée.

    La catégorie est retrouvée sans tenir compte des majuscules ni des espaces
    (« Machine Learning » = « machine_learning »). Si elle n'existe pas, elle n'est créée
    que si `create_category=True` (pour éviter qu'une faute de frappe crée une catégorie).
    Refuse une compétence déjà présente dans la catégorie.
    """

    skill = _clean_text(skill, "compétence", "skill")
    category = _clean_text(category, "compétence", "category")
    key = _category_key(category)
    if not key:
        raise ItemError("compétence", [f"le nom de catégorie « {category} » doit contenir des lettres ou des chiffres."])

    path, current, data = _load_for_edit(path)

    if not isinstance(data.get("skills"), dict) or not data.get("skills"):
        data["skills"] = CommentedMap()
    skills = data["skills"]

    existing = next((name for name in skills if _category_key(str(name)) == key), None)
    if existing is None:
        if not create_category:
            known = ", ".join(str(name) for name in skills) or "aucune"
            raise ItemError("compétence", [
                f"la catégorie « {category} » n'existe pas (catégories : {known}). "
                "Utilise create_category=True pour la créer."
            ])
        existing = key
        skills[existing] = CommentedSeq()
    elif not isinstance(skills[existing], list) or not skills[existing]:
        skills[existing] = CommentedSeq()

    if any(_same(item, skill) for item in skills[existing]):
        raise ItemError("compétence", [f"« {skill} » est déjà dans la catégorie « {existing} »."])
    skills[existing].append(_scalar(skill))

    _save(
        path, data,
        lambda written: any(_same(item, skill) for item in written["skills"].get(existing) or []),
        f"la compétence « {skill} »",
    )
    return existing


def add_language(language: str, level: str, path: Path | None = None) -> str:
    """
    Ajoute une langue avec son niveau (ex. « Spanish », « Intermediate » ou « B2 ») et
    renvoie le nom de la langue. Refuse une langue déjà présente.
    """

    language = _clean_text(language, "langue", "language")
    level = _clean_text(level, "langue", "level")

    path, current, data = _load_for_edit(path)

    for entry in current.data["languages"]:
        if isinstance(entry, dict) and _same(entry.get("language"), language):
            raise ItemError("langue", [f"« {language} » est déjà dans le profil (niveau : {entry.get('level')})."])

    entry = CommentedMap()
    entry["language"] = _scalar(language)
    entry["level"] = _scalar(level)
    _list_section(data, "languages").append(entry)

    _save(
        path, data,
        lambda written: any(isinstance(e, dict) and _same(e.get("language"), language) for e in written["languages"]),
        f"la langue « {language} »",
    )
    return language


def add_interest(interest: str, path: Path | None = None) -> str:
    """
    Ajoute un centre d'intérêt à la fin de la liste (l'ordre est la priorité : les
    premiers sont utilisés en premier dans le CV) et le renvoie. Refuse un doublon.
    """

    interest = _clean_text(interest, "centre d'intérêt", "interest")

    path, current, data = _load_for_edit(path)

    if any(_same(item, interest) for item in current.data["interests"]):
        raise ItemError("centre d'intérêt", [f"« {interest} » est déjà dans les centres d'intérêt."])
    _list_section(data, "interests").append(_scalar(interest))

    _save(
        path, data,
        lambda written: any(_same(item, interest) for item in written["interests"]),
        f"le centre d'intérêt « {interest} »",
    )
    return interest


# ---------- Sections uniques : informations personnelles, statut, préférences ----------

BIRTH_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # "2001-06-18"

# Ordre des sections dans le profil : une section créée est placée au bon endroit
SECTION_ORDER = ["personal", "career", "education", "experiences", "projects", "awards", "skills",
                 "languages", "interests", "preferences", "form_answers", "application_rules"]


@dataclass(frozen=True)
class SectionSpec:
    """Une section unique du profil (sans id) et le type de chacun de ses champs."""

    section: str
    label: str
    fields: dict             # champ -> type : "text", "email", "url", "birth_date", "month", "list" ou tuple de choix
    required: tuple[str, ...] = ()


SECTION_SPECS = {
    "personal": SectionSpec(
        section="personal",
        label="informations personnelles",
        fields={
            "first_name": "text", "last_name": "text", "email": "email", "phone": "text",
            "birth_date": "birth_date", "gender": "text", "nationality": "text", "address": "text",
            "postal_code": "text", "city": "text", "country": "text", "linkedin": "url", "github": "url",
        },
        required=("first_name", "last_name"),
    ),
    "career": SectionSpec(
        section="career",
        label="statut",
        fields={
            "academic_status": ("student", "graduated"),
            "employment_status": ("employed", "job_seeking", "internship", "freelance", "other"),
            "graduation_date": "month",
        },
    ),
    "preferences": SectionSpec(
        section="preferences",
        label="préférences",
        fields={"target_roles": "list", "preferred_locations": "list", "employment_types": "list"},
    ),
}


def _clean_section_fields(spec: SectionSpec, fields: dict) -> dict:
    """
    Vérifie les champs fournis. Un champ fourni vide ("", None, []) est enregistré vide,
    sauf les champs obligatoires. Renvoie {champ: valeur à écrire}.
    """

    problems = []

    if not isinstance(fields, dict) or not fields:
        raise ItemError(spec.label, ["aucun champ à mettre à jour."])

    unknown = sorted(set(fields) - set(spec.fields))
    if unknown:
        problems.append(f"champ(s) inconnu(s) : {', '.join(unknown)}. Champs possibles : {', '.join(spec.fields)}.")

    cleaned = {}
    for field, kind in spec.fields.items():
        if field not in fields:
            continue
        value = fields[field]

        if kind == "list":
            if value is None:
                value = []
            if isinstance(value, str) or not all(isinstance(entry, str) for entry in value):
                problems.append(f"« {field} » doit être une liste de textes.")
                continue
            entries = []
            for entry in (entry.strip() for entry in value):
                if entry and not any(_same(entry, kept) for kept in entries):
                    entries.append(entry)
            cleaned[field] = CommentedSeq(_scalar(entry) for entry in entries)
            continue

        if value is None:
            value = ""
        if not isinstance(value, str):
            problems.append(f"« {field} » doit être un texte.")
            continue
        value = value.strip()

        if not value:
            if field in spec.required:
                problems.append(f"« {field} » est obligatoire et ne peut pas être vidé.")
            else:
                cleaned[field] = DoubleQuotedScalarString("")
            continue

        if isinstance(kind, tuple) and value not in kind:
            problems.append(f"« {field} » doit valoir {', '.join(kind)} (reçu : « {value} »).")
        elif kind == "email" and ("@" not in value or " " in value):
            problems.append(f"« {field} » n'est pas une adresse e-mail valide (reçu : « {value} »).")
        elif kind == "url" and not value.startswith(("http://", "https://")):
            problems.append(f"« {field} » doit commencer par http:// ou https:// (reçu : « {value} »).")
        elif kind == "birth_date" and not BIRTH_DATE_PATTERN.match(value):
            problems.append(f"« {field} » doit avoir la forme « AAAA-MM-JJ » (reçu : « {value} »).")
        elif kind == "month" and not DATE_PATTERN.match(value):
            problems.append(f"« {field} » doit avoir la forme « AAAA » ou « AAAA-MM » (reçu : « {value} »).")
        else:
            cleaned[field] = _scalar(value, quote=kind in ("birth_date", "month"))

    if problems:
        raise ItemError(spec.label, problems)

    return cleaned


def _section_map(data, section: str) -> CommentedMap:
    """
    La section `section` du YAML modifiable. Sans valeur ou « {} » : remplacée sur place.
    Absente : créée à sa place habituelle dans le profil (ex. career juste après personal).
    """
    value = data.get(section)
    if isinstance(value, dict) and value:
        return value

    new_section = CommentedMap()
    if section in data:
        data[section] = new_section
        return new_section

    previous = SECTION_ORDER[:SECTION_ORDER.index(section)]
    keys = list(data)
    position = max((keys.index(key) + 1 for key in previous if key in data), default=len(keys))
    data.insert(position, section, new_section)
    return new_section


def _update_section(spec: SectionSpec, fields: dict, path: Path | None) -> dict:
    """
    Met à jour seulement les champs fournis de la section et renvoie la section enregistrée.
    Les autres champs, sections et commentaires sont conservés. Lève ProfileError ou ItemError.
    """

    cleaned = _clean_section_fields(spec, fields)
    path, current, data = _load_for_edit(path)

    section = _section_map(data, spec.section)
    for field, value in cleaned.items():
        section[field] = value

    expected = {field: (list(value) if isinstance(value, list) else str(value)) for field, value in cleaned.items()}
    _save(
        path, data,
        lambda written: all(written[spec.section].get(field) == value for field, value in expected.items()),
        f"la mise à jour de « {spec.section} »",
    )
    return dict(load_profile(path).data[spec.section])


def update_personal(fields: dict, path: Path | None = None) -> dict:
    """
    Met à jour les informations personnelles fournies (ex. {"phone": "+33 6 ...", "city": "Lyon"})
    et renvoie la section. first_name et last_name ne peuvent pas être vidés.
    Champs : first_name, last_name, email, phone, birth_date (AAAA-MM-JJ), gender, nationality,
    address, postal_code, city, country, linkedin, github (URL).
    """
    return _update_section(SECTION_SPECS["personal"], fields, path)


def update_career(fields: dict, path: Path | None = None) -> dict:
    """
    Met à jour le statut du candidat et renvoie la section (créée si elle n'existe pas).
    Champs : academic_status (student | graduated), employment_status (employed | job_seeking |
    internship | freelance | other), graduation_date (AAAA ou AAAA-MM).
    """
    return _update_section(SECTION_SPECS["career"], fields, path)


def update_preferences(fields: dict, path: Path | None = None) -> dict:
    """
    REMPLACE des listes de préférences et renvoie la section : chaque liste fournie remplace
    entièrement l'ancienne (doublons retirés) ; les listes non fournies sont inchangées.
    Pour ajouter une seule valeur sans toucher aux autres : add_preference().
    Champs : target_roles, preferred_locations, employment_types.
    """
    return _update_section(SECTION_SPECS["preferences"], fields, path)


def add_preference(category: str, value: str, path: Path | None = None) -> list:
    """
    AJOUTE une valeur à la fin d'une liste de préférences, en conservant les valeurs
    existantes, et renvoie la liste enregistrée. Refuse un doublon (« paris » = « Paris »).
    Pour remplacer toute une liste : update_preferences().
    Catégories : target_roles, preferred_locations, employment_types.
    """

    spec = SECTION_SPECS["preferences"]
    if category not in spec.fields:
        raise ItemError(spec.label, [f"catégorie inconnue : « {category} ». Catégories possibles : {', '.join(spec.fields)}."])
    value = _clean_text(value, spec.label, "value")

    path, current, data = _load_for_edit(path)

    existing = current.data["preferences"].get(category) or []
    if any(_same(item, value) for item in existing):
        raise ItemError(spec.label, [f"« {value} » est déjà dans « {category} »."])

    section = _section_map(data, "preferences")
    if not isinstance(section.get(category), list) or not section.get(category):
        section[category] = CommentedSeq()
    section[category].append(_scalar(value))

    _save(
        path, data,
        lambda written: any(_same(item, value) for item in written["preferences"].get(category) or []),
        f"la préférence « {value} »",
    )
    return list(load_profile(path).data["preferences"][category])


# ---------- Modification d'un élément existant ----------

def _kind_for_section(section: str) -> ItemKind:
    for kind in ITEM_KINDS.values():
        if kind.section == section:
            return kind
    sections = ", ".join(kind.section for kind in ITEM_KINDS.values())
    raise ItemError("élément", [f"section inconnue : « {section} ». Sections possibles : {sections}."])


def _plain(item) -> dict:
    """L'élément tel que le relira le pipeline (textes et listes simples)."""
    return {str(key): (list(value) if isinstance(value, list) else str(value)) for key, value in item.items()}


def update_item(section: str, item_id: str, changes: dict, path: Path | None = None) -> dict:
    """
    Modifie seulement les champs fournis d'une expérience, d'un projet ou d'une formation,
    retrouvé(e) par son id, et renvoie l'élément enregistré.

    - section : "experiences", "projects" ou "education".
    - changes : {champ: nouvelle valeur}. Une valeur vide (None, "", []) retire un champ
      facultatif ; un champ obligatoire ne peut pas être vidé.
    - L'id ne peut pas être modifié (il reste le même si l'entreprise ou le nom change).
    Les mêmes règles qu'à l'ajout s'appliquent. Lève ProfileError ou ItemError.
    """

    kind = _kind_for_section(section)
    if not isinstance(changes, dict) or not changes:
        raise ItemError(kind.label, ["aucun champ à modifier."])
    values, cleared = _check_item_fields(kind, changes, partial=True)

    path, current, data = _load_for_edit(path)

    item = next((element for element in data.get(section) or [] if isinstance(element, dict) and element.get("id") == item_id), None)
    if item is None:
        known = [element["id"] for element in current.data[section] if isinstance(element, dict) and element.get("id")]
        message = f"aucun(e) {kind.label} avec l'id « {item_id} ». Ids existants : {', '.join(known) or 'aucun'}."
        if any(isinstance(element, dict) and not element.get("id") for element in current.data[section]):
            message += " Certain(e)s n'ont pas d'id : utilise assign_missing_ids() pour leur en donner un."
        raise ItemError(kind.label, [message])

    for field, value in values.items():
        item[field] = value          # champ existant : modifié sur place ; nouveau : ajouté à la fin
    for field in cleared:
        item.pop(field, None)
    _check_dates(kind, item)

    expected = _plain(item)
    _save(
        path, data,
        lambda written: any(isinstance(e, dict) and e.get("id") == item_id and e == expected for e in written[section]),
        f"{kind.label} « {item_id} »",
    )
    return expected


def assign_missing_ids(path: Path | None = None) -> dict:
    """
    Donne un id aux formations qui n'en ont pas encore (les profils créés avant les id de
    formation), à partir du nom de l'école, pour pouvoir ensuite les modifier par id.
    Ne change rien d'autre. Renvoie {position (1, 2...) : id attribué} ({} si rien à faire).
    """

    kind = ITEM_KINDS["education"]
    path, current, data = _load_for_edit(path)

    existing = _existing_ids(current.data)
    assigned = {}
    for number, element in enumerate(data.get(kind.section) or [], start=1):
        if not isinstance(element, dict) or element.get("id"):
            continue
        new_id = _unique_id(_slug(str(element.get(kind.id_from) or "")), existing, fallback=_slug(kind.label))
        existing.add(new_id)
        element.insert(0, "id", _scalar(new_id))   # en premier, comme pour les éléments ajoutés
        assigned[number] = new_id

    if assigned:
        _save(
            path, data,
            lambda written: all(written[kind.section][number - 1].get("id") == new_id for number, new_id in assigned.items()),
            "les id de formation",
        )
    return assigned

"""
Extraction d'un profil candidat à partir du texte d'un CV, par Claude.

Prompt, schéma JSON imposé à Claude, appel (llm/claude_cli.py) et nettoyage de sa
réponse. La structure reprend les champs du profil (ceux de candidate/manager.py, qui
décrivent candidate.example.yaml). Les informations déduites ou ambiguës sont signalées
dans `uncertain_fields` et `warnings`.

La lecture du PDF et l'enregistrement du résultat sont dans candidate/import_cv.py.
"""

import re
import unicodedata

from candidate.manager import DATE_PATTERN, ITEM_KINDS, SECTION_SPECS
from llm.claude_cli import run_claude


# Champs d'organisation du profil, qui ne figurent pas sur un CV
NOT_IN_A_CV = {"priority", "tags"}

# Champs extraits pour chaque liste d'éléments, dans l'ordre du profil
ITEM_FIELDS = {
    kind.section: [field for field in kind.fields if field not in NOT_IN_A_CV]
    for kind in ITEM_KINDS.values()
}
PERSONAL_FIELDS = list(SECTION_SPECS["personal"].fields)


def _nullable_text() -> dict:
    return {"type": ["string", "null"]}


def _text_list() -> dict:
    return {"type": "array", "items": {"type": "string"}}


def _item_schema(fields: list[str], list_fields: frozenset) -> dict:
    properties = {field: (_text_list() if field in list_fields else _nullable_text()) for field in fields}
    properties["uncertain_fields"] = _text_list()
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


PERSONAL_SCHEMA = {
    "type": "object",
    "properties": {**{field: _nullable_text() for field in PERSONAL_FIELDS}, "uncertain_fields": _text_list()},
    "required": PERSONAL_FIELDS + ["uncertain_fields"],
    "additionalProperties": False,
}

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "personal": PERSONAL_SCHEMA,
        **{
            kind.section: {"type": "array", "items": _item_schema(ITEM_FIELDS[kind.section], kind.list_fields)}
            for kind in ITEM_KINDS.values()
        },
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"category": {"type": "string"}, "skills": _text_list()},
                "required": ["category", "skills"],
                "additionalProperties": False,
            },
        },
        "languages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"language": {"type": "string"}, "level": _nullable_text()},
                "required": ["language", "level"],
                "additionalProperties": False,
            },
        },
        "interests": _text_list(),
        "warnings": _text_list(),
    },
    "required": ["personal", "education", "experiences", "projects", "skills", "languages", "interests", "warnings"],
    "additionalProperties": False,
}


EXTRACTION_PROMPT = """
You read the text of a candidate's CV (extracted from a PDF, provided on stdin) and extract
the candidate's information into the requested JSON structure.

FAITHFULNESS — the most important rule:
- Extract ONLY what the CV states. Never invent, complete or improve anything: no skill,
  tool, task, result, number, date, place, degree or contact detail that is not in the text.
- A field the CV does not give: null (text) or [] (list).
- Keep the CV's own words. Do not translate. Do not merge two experiences into one.
- PDF extraction can split words or glue them ("F ondation", "CNRS(Aubay)Paris"): restore
  the obvious word, but do not change its meaning.

UNCERTAINTY:
- For each experience, project, education entry and for personal, list in uncertain_fields
  the fields you had to deduce or that are ambiguous (e.g. a date only given as a year range,
  a location you inferred, a title split across lines).
- Put in warnings, in French, anything the candidate should check (unreadable parts,
  information that could belong to two entries, missing dates...).

FORMATS:
- Dates: "YYYY" or "YYYY-MM" only (e.g. "2024", "2025-09"). An ongoing position ("present",
  "aujourd'hui"): end_date null, and say it in warnings. birth_date: "YYYY-MM-DD" or null.
- responsibilities: what the candidate did (one task per item). achievements: measurable
  results or outcomes stated in the CV (one per item). Do not duplicate a line in both.
- description / context: a short sentence from the CV if there is one, otherwise null.
- linkedin / github / github_url: full URL as written (add "https://" if it is missing).
- skills: group them by the CV's own categories; use short lowercase snake_case category
  names (e.g. "programming", "machine_learning", "tools"). Without categories: "other".
- languages: the level exactly as written (e.g. "C1", "Native", "Courant"), null if absent.
- Awards, certifications, volunteering: if attached to an experience or project, keep them
  there; otherwise mention them in warnings.
""".strip()


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9@.+]+", " ", text.lower()).strip()


def _in_text(value: str, text: str) -> bool:
    """La valeur figure-t-elle dans le texte du CV (sans tenir compte des accents ni de la casse) ?"""
    wanted = _normalize(value)
    return bool(wanted) and (wanted in text or wanted.replace(" ", "") in text.replace(" ", ""))


def _is_empty(value) -> bool:
    return value is None or value == [] or (isinstance(value, str) and not value.strip())


def _clean_extraction(raw: dict, cv_text: str) -> dict:
    """
    Remet le résultat de Claude au format du profil (skills en dictionnaire), retire les
    champs vides, vérifie les dates et marque comme incertain ce qui n'est pas dans le CV.
    """

    text = _normalize(cv_text)
    warnings = [warning for warning in raw.get("warnings", []) if warning.strip()]

    def clean_entry(entry: dict, label: str, checked: tuple) -> dict:
        uncertain = set(entry.get("uncertain_fields") or [])
        result = {}
        for field, value in entry.items():
            if field == "uncertain_fields" or _is_empty(value):
                continue
            if isinstance(value, list):
                value = [item.strip() for item in value if item.strip()]
            else:
                value = value.strip()
            if field in ("start_date", "end_date", "graduation_date") and not DATE_PATTERN.match(value):
                warnings.append(f"{label} : la date « {value} » ({field}) n'a pas le format AAAA ou AAAA-MM, elle a été retirée.")
                continue
            if field == "birth_date" and not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                warnings.append(f"{label} : la date de naissance « {value} » n'a pas le format AAAA-MM-JJ, elle a été retirée.")
                continue
            if field in checked and not _in_text(value, text):
                uncertain.add(field)
                warnings.append(f"{label} : « {value} » ({field}) ne figure pas tel quel dans le CV, à vérifier.")
            result[field] = value
        uncertain &= set(result)
        if uncertain:
            result["uncertain_fields"] = sorted(uncertain)
        return result

    personal = clean_entry(raw.get("personal") or {}, "coordonnées",
                           ("first_name", "last_name", "email", "phone"))

    sections = {}
    for kind in ITEM_KINDS.values():
        checked = {"experiences": ("company",), "projects": ("name",), "education": ("school",)}[kind.section]
        entries = []
        for number, entry in enumerate(raw.get(kind.section) or [], start=1):
            name = entry.get(kind.id_from) or f"n°{number}"
            cleaned = clean_entry(entry, f"{kind.label} « {name} »", checked)
            if cleaned:
                entries.append(cleaned)
        sections[kind.section] = entries

    skills: dict[str, list[str]] = {}
    for group in raw.get("skills") or []:
        category = re.sub(r"[^a-z0-9]+", "_", _normalize(group.get("category") or "other")).strip("_") or "other"
        for skill in group.get("skills") or []:
            skill = skill.strip()
            if skill and skill.lower() not in (known.lower() for known in skills.setdefault(category, [])):
                skills[category].append(skill)
                if not _in_text(skill, text):
                    warnings.append(f"compétence « {skill} » : ne figure pas telle quelle dans le CV, à vérifier.")
    skills = {category: values for category, values in skills.items() if values}

    languages = []
    for entry in raw.get("languages") or []:
        language = (entry.get("language") or "").strip()
        if not language:
            continue
        cleaned = {"language": language}
        if not _is_empty(entry.get("level")):
            cleaned["level"] = entry["level"].strip()
        if not _in_text(language, text):
            warnings.append(f"langue « {language} » : ne figure pas telle quelle dans le CV, à vérifier.")
        languages.append(cleaned)

    interests = [interest.strip() for interest in raw.get("interests") or [] if interest.strip()]

    return {
        "personal": personal,
        **sections,
        "skills": skills,
        "languages": languages,
        "interests": interests,
        "warnings": warnings,
    }


def extract_profile(cv_text: str, timeout: int = 300) -> dict:
    """Envoie le texte du CV à Claude et renvoie la proposition de profil nettoyée."""
    raw = run_claude(EXTRACTION_PROMPT, "=== CV TEXT ===\n" + cv_text, EXTRACTION_SCHEMA, timeout)
    return _clean_extraction(raw, cv_text)

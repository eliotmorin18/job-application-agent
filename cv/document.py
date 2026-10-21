"""
CV structuré (cv.json) : schéma, construction, validation, sauvegarde et relecture.

Claude rédige les textes (CLAUDE_SCHEMA) ; build_document() y ajoute ce qui vient du profil
(nom, contacts, dates, lieux, liens), enregistré comme instantané : un CV déjà créé ne
change pas si le profil change ensuite. Python le convertit ensuite en LaTeX (cv/render.py).

L'ordre des listes est l'ordre d'affichage : ajouter, retirer ou réordonner un élément ou une
puce revient à modifier la liste. Une liste vide masque la section dans le PDF.
Modifier un CV ne modifie jamais candidate.yaml.

    {
      "schema_version": 1, "language": "fr", "company": "...", "role": "...",
      "header": {"name": "...", "contacts": [{"type": "email", "value": "..."}], "summary": "..."},
      "experiences": [{"source_id", "title", "organization", "context", "location", "dates", "bullets"}],
      "education":   [{"source_id", "institution", "location", "dates", "bullets"}],
      "projects":    [{"source_id", "name", "link": {"url", "label"} | null, "bullets"}],
      "skills":      [{"label", "items"}],
      "languages":   [{"name", "level"}],
      "interests":   ["..."],
      "gaps":        ["..."]
    }
"""

import json
from pathlib import Path

from candidate.manager import _existing_ids, _slug, _unique_id
from candidate.profile import CandidateProfile
from cv.render import LABELS, format_dates, short_location


SCHEMA_VERSION = 1
DOCUMENT_FILE = "cv.json"
CONTACT_TYPES = ["email", "phone", "linkedin", "github"]   # ordre d'affichage dans l'en-tête


class CVDocumentError(ValueError):
    """Le CV structuré est invalide. `problems` liste toutes les raisons."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("CV invalide :\n" + "\n".join(f"  - {problem}" for problem in problems))


# ---------- Ce que Claude renvoie ----------

def _text() -> dict:
    return {"type": "string"}


def _texts() -> dict:
    return {"type": "array", "items": {"type": "string"}}


def _object(**properties) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


# Pas de dates, lieux, contacts ni liens : ils viennent du profil. Pas de LaTeX.
CLAUDE_SCHEMA = _object(
    company=_text(),
    role=_text(),
    language={"type": "string", "enum": list(LABELS)},
    summary=_text(),
    experiences={"type": "array", "items": _object(
        source_id=_text(), title=_text(), organization=_text(),
        context={"type": ["string", "null"]}, bullets=_texts())},
    education={"type": "array", "items": _object(source_id=_text(), institution=_text(), bullets=_texts())},
    projects={"type": "array", "items": _object(source_id=_text(), name=_text(), bullets=_texts())},
    skills={"type": "array", "items": _object(label=_text(), items=_texts())},
    languages={"type": "array", "items": _object(name=_text(), level=_text())},
    interests=_texts(),
    gaps=_texts(),
)


# ---------- Identifiants des éléments du profil ----------

def education_keys(profile_data: dict) -> list[tuple[str, dict]]:
    """
    (identifiant, formation) dans l'ordre du profil. L'id de la formation s'il existe ; sinon un
    identifiant calculé à partir de l'école, exactement comme le ferait manager.assign_missing_ids()
    (le profil n'est pas modifié, et les deux restent cohérents si des id sont ajoutés plus tard).
    """
    existing = _existing_ids(profile_data)
    keys = []
    for item in profile_data["education"]:
        if not isinstance(item, dict):
            continue
        key = item.get("id")
        if not key:
            key = _unique_id(_slug(str(item.get("school") or "")), existing, fallback="formation")
            existing.add(key)
        keys.append((key, item))
    return keys


def _profile_items(profile_data: dict) -> dict[str, dict[str, dict]]:
    """{section du CV: {source_id: élément du profil}}"""
    return {
        "experiences": {item["id"]: item for item in profile_data["experiences"] if isinstance(item, dict) and item.get("id")},
        "projects": {item["id"]: item for item in profile_data["projects"] if isinstance(item, dict) and item.get("id")},
        "education": dict(education_keys(profile_data)),
    }


def _contacts(personal: dict) -> list[dict]:
    return [{"type": kind, "value": str(personal[kind]).strip()}
            for kind in CONTACT_TYPES if str(personal.get(kind) or "").strip()]


def _facts(section: str, item: dict) -> dict:
    """Ce qui est repris tel quel du profil (instantané) : dates, lieu, lien."""
    if section == "projects":
        url = str(item.get("github_url") or "").strip()
        return {"link": {"url": url, "label": "GitHub"} if url else None}
    return {"location": short_location(item.get("location")), "dates": format_dates(item.get("start_date"), item.get("end_date"))}


def _clean(values) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def entry_from_profile(section: str, source_id: str, profile_data: dict) -> dict:
    """
    Un élément du profil prêt à être ajouté au CV (textes du profil, non retravaillés).
    Sert à ajouter une expérience, une formation ou un projet sans passer par Claude.
    """
    item = _profile_items(profile_data)[section].get(source_id)
    if item is None:
        raise CVDocumentError([f"{section} : aucun élément « {source_id} » dans le profil."])
    if section == "experiences":
        texts = {"title": str(item.get("title") or ""), "organization": str(item.get("company") or ""),
                 "context": None, "bullets": _clean(item.get("responsibilities"))}
    elif section == "education":
        texts = {"institution": str(item.get("school") or ""), "bullets": _clean(item.get("details"))}
    else:
        texts = {"name": str(item.get("name") or ""), "bullets": _clean(item.get("responsibilities"))}
    bullets = texts.pop("bullets")
    return {"source_id": source_id, **texts, **_facts(section, item), "bullets": bullets}


# ---------- Construction (après Claude) ----------

def build_document(draft: dict, profile: CandidateProfile) -> dict:
    """
    CV complet à partir de la réponse de Claude : sélection vérifiée (éléments du profil, pas de
    doublon, limites max_cv_*), puis dates, lieux, contacts et liens repris du profil.
    Lève CVDocumentError si la sélection est impossible.
    """
    data = profile.data
    items = _profile_items(data)
    rules = data.get("application_rules", {})
    problems = []

    for section, label, limit in (("experiences", "expérience", rules.get("max_cv_experiences")),
                                  ("projects", "projet", rules.get("max_cv_projects")),
                                  ("education", "formation", None)):
        selected = [entry["source_id"] for entry in draft[section]]
        unknown = [source_id for source_id in selected if source_id not in items[section]]
        if unknown:
            problems.append(f"Claude a choisi des {label}s qui n'existent pas dans le profil : {unknown}")
        if len(set(selected)) != len(selected):
            problems.append(f"Claude a choisi plusieurs fois la même {label} : {selected}")
        if limit is not None and len(selected) > limit:
            problems.append(f"Claude a choisi {len(selected)} {label}s, le maximum est {limit}.")
    if problems:
        raise CVDocumentError(problems)

    def entries(section: str, fields: tuple) -> list[dict]:
        built = []
        for entry in draft[section]:
            texts = {field: str(entry.get(field) or "").strip() for field in fields}
            if "context" in texts:
                texts["context"] = texts["context"] or None
            built.append({"source_id": entry["source_id"], **texts,
                          **_facts(section, items[section][entry["source_id"]]),
                          "bullets": _clean(entry.get("bullets"))})
        return built

    personal = data["personal"]
    doc = {
        "schema_version": SCHEMA_VERSION,
        "language": draft["language"],
        "company": draft["company"].strip(),
        "role": draft["role"].strip(),
        "header": {
            "name": f"{personal['first_name'].strip()} {personal['last_name'].strip()}",
            "contacts": _contacts(personal),
            "summary": draft["summary"].strip(),
        },
        "experiences": entries("experiences", ("title", "organization", "context")),
        "education": entries("education", ("institution",)),
        "projects": entries("projects", ("name",)),
        "skills": [{"label": group["label"].strip(), "items": _clean(group["items"])}
                   for group in draft["skills"] if group["label"].strip() and _clean(group["items"])],
        "languages": [{"name": lang["name"].strip(), "level": lang["level"].strip()}
                      for lang in draft["languages"] if lang["name"].strip()],
        "interests": _clean(draft["interests"]),
        "gaps": _clean(draft["gaps"]),
    }
    validate_document(doc, data)
    return doc


def selected_ids(doc: dict) -> tuple[list[str], list[str]]:
    """Ids des expériences et projets du CV, dans l'ordre (pour selection.json et l'affichage)."""
    return [entry["source_id"] for entry in doc["experiences"]], [entry["source_id"] for entry in doc["projects"]]


# ---------- Validation ----------

TEXT, OPTIONAL_TEXT, TEXTS = "text", "optional text", "texts"

ENTRY_FIELDS = {
    "experiences": {"source_id": TEXT, "title": TEXT, "organization": str, "context": OPTIONAL_TEXT,
                    "location": str, "dates": str, "bullets": TEXTS},
    "education": {"source_id": TEXT, "institution": TEXT, "location": str, "dates": str, "bullets": TEXTS},
    "projects": {"source_id": TEXT, "name": TEXT, "link": "link", "bullets": TEXTS},
}


def _check_value(where: str, value, kind, problems: list) -> None:
    if kind is str:
        if not isinstance(value, str):
            problems.append(f"{where} doit être un texte.")
    elif kind == TEXT:
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{where} doit être un texte non vide.")
    elif kind == OPTIONAL_TEXT:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            problems.append(f"{where} doit être un texte non vide ou null.")
    elif kind == TEXTS:
        if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
            problems.append(f"{where} doit être une liste de textes non vides.")
    elif kind == "link":
        if value is not None and not (isinstance(value, dict) and set(value) == {"url", "label"}
                                      and str(value["url"]).startswith(("http://", "https://"))
                                      and isinstance(value["label"], str) and value["label"].strip()):
            problems.append(f"{where} doit être null ou {{\"url\": \"https://...\", \"label\": \"...\"}}.")


def _check_object(where: str, value, fields: dict, problems: list) -> bool:
    if not isinstance(value, dict):
        problems.append(f"{where} doit être un objet.")
        return False
    missing, unknown = sorted(set(fields) - set(value)), sorted(set(value) - set(fields))
    if missing:
        problems.append(f"{where} : champ(s) manquant(s) : {', '.join(missing)}.")
    if unknown:
        problems.append(f"{where} : champ(s) inconnu(s) : {', '.join(unknown)}.")
    for field, kind in fields.items():
        if field in value:
            _check_value(f"{where}.{field}", value[field], kind, problems)
    return not missing


def validate_document(doc, profile_data: dict | None = None) -> None:
    """
    Vérifie la structure du CV et, si le profil est donné, que chaque source_id existe dans le
    profil. Pas de limite de nombre ici (max_cv_* ne s'impose qu'au choix fait par Claude).
    Lève CVDocumentError avec tous les problèmes.
    """
    problems = []
    top = {"schema_version": int, "language": str, "company": str, "role": str, "header": dict,
           "experiences": list, "education": list, "projects": list, "skills": list, "languages": list,
           "interests": TEXTS, "gaps": list}
    if not isinstance(doc, dict):
        raise CVDocumentError(["le CV doit être un objet JSON."])
    missing, unknown = sorted(set(top) - set(doc)), sorted(set(doc) - set(top))
    if missing:
        problems.append(f"champ(s) manquant(s) : {', '.join(missing)}.")
    if unknown:
        problems.append(f"champ(s) inconnu(s) : {', '.join(unknown)}.")
    for field, kind in top.items():
        if field in doc and kind in (int, dict, list) and not isinstance(doc[field], kind):
            problems.append(f"« {field} » doit être {'un nombre' if kind is int else 'un objet' if kind is dict else 'une liste'}.")
    if problems:
        raise CVDocumentError(problems)

    if doc["schema_version"] != SCHEMA_VERSION:
        problems.append(f"schema_version {doc['schema_version']} non pris en charge (attendu : {SCHEMA_VERSION}).")
    if doc["language"] not in LABELS:
        problems.append(f"« language » doit valoir {', '.join(LABELS)}.")
    _check_value("interests", doc["interests"], TEXTS, problems)
    _check_value("gaps", doc["gaps"], TEXTS, problems)

    header = doc["header"]
    if _check_object("header", header, {"name": TEXT, "contacts": list, "summary": str}, problems):
        if isinstance(header["contacts"], list):
            for n, contact in enumerate(header["contacts"]):
                where = f"header.contacts[{n}]"
                if _check_object(where, contact, {"type": TEXT, "value": TEXT}, problems):
                    if contact["type"] not in CONTACT_TYPES:
                        problems.append(f"{where}.type doit valoir {', '.join(CONTACT_TYPES)}.")
                    elif contact["type"] in ("linkedin", "github") and not str(contact["value"]).startswith(("http://", "https://")):
                        problems.append(f"{where}.value doit commencer par http:// ou https://.")
        else:
            problems.append("header.contacts doit être une liste.")

    known = _profile_items(profile_data) if profile_data is not None else None
    for section, fields in ENTRY_FIELDS.items():
        seen = set()
        for n, entry in enumerate(doc[section]):
            where = f"{section}[{n}]"
            if not _check_object(where, entry, fields, problems) or not isinstance(entry.get("source_id"), str):
                continue
            source_id = entry["source_id"]
            if source_id in seen:
                problems.append(f"{where} : « {source_id} » est déjà dans le CV.")
            seen.add(source_id)
            if known is not None and source_id not in known[section]:
                problems.append(f"{where} : « {source_id} » n'existe pas dans le profil.")

    for n, group in enumerate(doc["skills"]):
        if _check_object(f"skills[{n}]", group, {"label": TEXT, "items": TEXTS}, problems) and not group["items"]:
            problems.append(f"skills[{n}] : un groupe de compétences ne peut pas être vide (retire-le).")
    for n, lang in enumerate(doc["languages"]):
        _check_object(f"languages[{n}]", lang, {"name": TEXT, "level": str}, problems)

    if problems:
        raise CVDocumentError(problems)


# ---------- Sauvegarde et relecture ----------

def save_document(folder: Path, doc: dict, profile_data: dict | None = None) -> Path:
    """Valide puis écrit <folder>/cv.json (UTF-8, lisible). Renvoie le chemin."""
    validate_document(doc, profile_data)
    path = Path(folder) / DOCUMENT_FILE
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_document(folder: Path, profile_data: dict | None = None) -> dict:
    """Relit <folder>/cv.json et le valide. Lève CVDocumentError si absent ou invalide."""
    path = Path(folder) / DOCUMENT_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CVDocumentError([f"« {path} » n'existe pas (CV créé avant cv.json ?)."])
    except json.JSONDecodeError as error:
        raise CVDocumentError([f"« {path} » n'est pas un JSON valide ({error})."])
    validate_document(doc, profile_data)
    return doc


# ---------- Texte lisible (vérification par Claude) ----------

def document_text(doc: dict) -> dict[str, str]:
    """Le contenu du CV en texte simple, section par section (noms des fichiers de section)."""

    def entry_line(head: str, place: list) -> str:
        details = ", ".join(part for part in place if part)
        return head + (f" | {details}" if details else "")

    def bullets(entry: dict) -> list[str]:
        return [f"- {bullet}" for bullet in entry["bullets"]]

    header = doc["header"]
    heading = [f"Name: {header['name']}"]
    heading += [f"{contact['type']}: {contact['value']}" for contact in header["contacts"]]
    if header["summary"]:
        heading.append(f"Summary: {header['summary']}")

    experience = []
    for entry in doc["experiences"]:
        head = " — ".join(part for part in (entry["title"], entry["organization"]) if part)
        head += f" ({entry['context']})" if entry["context"] else ""
        experience += [entry_line(head, [entry["location"], entry["dates"]])] + bullets(entry)

    education = []
    for entry in doc["education"]:
        education += [entry_line(entry["institution"], [entry["location"], entry["dates"]])] + bullets(entry)

    projects = []
    for entry in doc["projects"]:
        projects += [entry_line(entry["name"], [entry["link"]["url"]] if entry["link"] else [])] + bullets(entry)

    skills = [f"{group['label']}: {', '.join(group['items'])}" for group in doc["skills"]]
    if doc["languages"]:
        skills.append("Languages: " + ", ".join(
            lang["name"] + (f" ({lang['level']})" if lang["level"] else "") for lang in doc["languages"]))

    return {
        "heading": "\n".join(heading),
        "experience": "\n".join(experience),
        "education": "\n".join(education),
        "projects": "\n".join(projects),
        "technical-skills": "\n".join(skills),
        "interests": ", ".join(doc["interests"]),
    }

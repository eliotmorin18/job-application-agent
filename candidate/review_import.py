"""
Comparaison d'une proposition d'import (JSON produit par candidate/import_cv.py) avec le
profil candidat existant, pour préparer sa validation.

Rien n'est enregistré : la fonction renvoie, pour chaque information extraite, son statut
(nouvelle, doublon, doublon probable ou possible), les correspondances trouvées dans le
profil (avec leurs id) et les avertissements de l'extraction. Le futur frontend s'en sert
pour proposer d'ajouter, corriger, ignorer ou mettre à jour. Pas d'appel à Claude.

Statuts :
- new                 : aucune correspondance dans le profil
- duplicate           : même texte (sans casse ni accents) ou équivalence évidente (Français = French)
- probable_duplicate  : élément avec le même nom et une date ou un intitulé qui concorde
- possible_duplicate  : nom proche seulement (incertain)
Aucun statut n'entraîne d'action automatique.
"""

import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

from candidate.manager import ITEM_KINDS, SECTION_SPECS, _category_key, _slug
from candidate.profile import load_profile


class ReviewError(Exception):
    """Le fichier d'import ne peut pas être relu."""


# Mots trop courants pour comparer des noms d'entreprises, d'écoles ou de projets
STOPWORDS = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "en", "a", "au", "of", "the", "and", "for", "in", "at", "via"}

# Équivalences simples entre langues (français / anglais / langue d'origine)
LANGUAGE_NAMES = [
    {"francais", "french", "francaise"},
    {"anglais", "english", "anglaise"},
    {"espagnol", "spanish", "espanol", "castillan"},
    {"allemand", "german", "deutsch"},
    {"italien", "italian", "italiano"},
    {"portugais", "portuguese", "portugues"},
    {"neerlandais", "dutch", "nederlands"},
    {"chinois", "chinese", "mandarin"},
    {"japonais", "japanese"},
    {"arabe", "arabic"},
    {"russe", "russian"},
    {"coreen", "korean"},
]

# Niveaux équivalents (le reste est comparé tel quel : « C1 » = « C1 / Fluent »)
LEVEL_NAMES = [
    {"native", "natif", "native speaker", "langue maternelle", "maternelle", "mother tongue"},
    {"fluent", "courant", "bilingue", "bilingual"},
    {"basic", "notions", "debutant", "beginner", "elementary", "elementaire"},
    {"intermediate", "intermediaire"},
]

# Quelques centres d'intérêt évidents en français et en anglais
INTEREST_NAMES = [
    {"echecs", "chess"}, {"musique", "music"}, {"lecture", "reading"}, {"voyages", "voyage", "travel", "travelling"},
    {"course a pied", "running"}, {"natation", "swimming"}, {"escalade", "climbing"}, {"cuisine", "cooking"},
    {"randonnee", "hiking"}, {"photographie", "photography"}, {"ski", "skiing"}, {"velo", "cyclisme", "cycling"},
]


# ---------- Normalisation et comparaison ----------

def _norm(text) -> str:
    """« Télécom SudParis » -> « telecom sudparis » (sans accents, casse ni ponctuation)."""
    return _slug(str(text or "")).replace("-", " ")


def _same_meaning(a, b, groups: list[set]) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a) and (a == b or any(a in group and b in group for group in groups))


def _tokens(text) -> list[str]:
    return [token for token in _norm(text).split() if token not in STOPWORDS]


def _name_score(a, b) -> float:
    """
    Proximité de deux noms, de 0 à 1 : part des mots du nom le plus court retrouvés dans
    l'autre (mots proches acceptés : « fondation » ~ « foundation »).
    """
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    short, long_ = (left, right) if len(left) <= len(right) else (right, left)
    found = sum(any(word == other or SequenceMatcher(None, word, other).ratio() >= 0.85 for other in long_)
                for word in short)
    return round(found / len(short), 2)


def _year(date) -> str:
    return str(date or "")[:4]


# ---------- Expériences, projets, formations ----------

# Champ du nom et champ secondaire servant à confirmer une correspondance
MATCH_FIELDS = {"experiences": ("company", "title"), "projects": ("name", None), "education": ("school", "degree")}


def _differences(extracted: dict, existing: dict) -> dict:
    """Champs à proposer en correction ou mise à jour : différents, ou absents du profil."""
    differences = {}
    for field, value in extracted.items():
        if field == "uncertain_fields":
            continue
        current = existing.get(field)
        if current in (None, "", []):
            differences[field] = {"extracted": value, "current": None, "change": "missing_in_profile"}
        elif isinstance(value, list) and isinstance(current, list):
            added = [item for item in value if not any(_norm(item) == _norm(known) for known in current)]
            if added:
                differences[field] = {"extracted": value, "current": current, "change": "new_values", "new_values": added}
        elif _norm(value) != _norm(current):
            differences[field] = {"extracted": value, "current": current, "change": "different"}
    return differences


def _match_item(section: str, extracted: dict, existing: list[dict]) -> tuple[str, list[dict]]:
    """Statut d'un élément extrait et ses correspondances possibles dans le profil, de la plus proche à la moins proche."""
    name_field, second_field = MATCH_FIELDS[section]
    matches = []

    for item in existing:
        if not isinstance(item, dict):
            continue
        name, other = extracted.get(name_field), item.get(name_field)
        score = _name_score(name, other)
        same_name = bool(_tokens(name)) and set(_tokens(name)) == set(_tokens(other))   # mêmes mots, ordre libre
        reasons = []
        if same_name:
            reasons.append("même nom")
        elif score == 1.0:
            reasons.append("nom très proche (tous les mots de l'un sont dans l'autre)")
        elif score >= 0.5:
            reasons.append(f"nom proche ({int(score * 100)} %)")

        same_second = bool(second_field) and _name_score(extracted.get(second_field), item.get(second_field)) >= 0.6
        if same_second:
            reasons.append("intitulé proche" if section == "experiences" else "diplôme proche")
        same_start = bool(extracted.get("start_date")) and _year(extracted.get("start_date")) == _year(item.get("start_date"))
        if same_start:
            reasons.append("même année de début")
        confirmed = same_second or same_start
        nothing_to_confirm = not extracted.get("start_date") and not (second_field and extracted.get(second_field))

        # « Probable » : même nom (confirmé si possible), ou nom très proche ET confirmé par une date
        # ou un intitulé. Tout le reste reste « possible » : jamais considéré comme un doublon certain.
        if (same_name and (confirmed or nothing_to_confirm)) or (score == 1.0 and confirmed):
            level = "probable_duplicate"
        elif score >= 0.5 or (same_second and same_start):   # nom proche, ou même poste la même année
            level = "possible_duplicate"
        else:
            continue

        matches.append({
            "id": item.get("id"),                 # id existant, conservé tel quel (peut manquer : anciennes formations)
            "level": level,
            "score": score,
            "reasons": reasons,
            "existing": item,
            "differences": _differences(extracted, item),
        })

    order = {"probable_duplicate": 0, "possible_duplicate": 1}
    matches.sort(key=lambda match: (order[match["level"]], -match["score"]))
    return (matches[0]["level"] if matches else "new"), matches


# ---------- Compétences, langues, centres d'intérêt ----------

def _review_skills(extracted: dict, existing: dict) -> list[dict]:
    reviews = []
    existing_keys = {_category_key(str(name)): name for name in existing}
    for category, skills in extracted.items():
        target = existing_keys.get(_category_key(category))
        for skill in skills:
            found = [(name, value) for name, values in existing.items() for value in values or [] if _norm(value) == _norm(skill)]
            same_category = [match for match in found if match[0] == target]
            review = {
                "category": category,
                "skill": skill,
                "category_in_profile": target,      # None : la catégorie n'existe pas encore dans le profil
                "status": "duplicate" if found else "new",
                "matches": [{"category": name, "skill": value} for name, value in found],
            }
            if found and not same_category:
                review["note"] = "déjà présente dans une autre catégorie"
            reviews.append(review)
    return reviews


def _same_level(a, b) -> bool:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return a == b
    return a == b or set(a.split()) <= set(b.split()) or set(b.split()) <= set(a.split()) or _same_meaning(a, b, LEVEL_NAMES)


def _review_languages(extracted: list[dict], existing: list[dict]) -> list[dict]:
    reviews = []
    for entry in extracted:
        match = next((known for known in existing if isinstance(known, dict)
                      and _same_meaning(entry.get("language"), known.get("language"), LANGUAGE_NAMES)), None)
        review = {"language": entry.get("language"), "level": entry.get("level"), "status": "new", "matches": []}
        if match:
            review["status"] = "duplicate"
            review["matches"] = [match]
            if _norm(entry.get("language")) != _norm(match.get("language")):
                review["note"] = f"équivalent de « {match.get('language')} »"
            if entry.get("level") and not _same_level(entry.get("level"), match.get("level")):
                review["level_differs"] = True       # le frontend peut proposer de mettre à jour le niveau
        reviews.append(review)
    return reviews


def _review_interests(extracted: list[str], existing: list[str]) -> list[dict]:
    reviews = []
    for interest in extracted:
        same = [known for known in existing if _same_meaning(interest, known, INTEREST_NAMES)]
        close = [known for known in existing if known not in same and _name_score(interest, known) >= 0.8]
        status = "duplicate" if same else ("possible_duplicate" if close else "new")
        reviews.append({"interest": interest, "status": status, "matches": same or close})
    return reviews


# ---------- Coordonnées ----------

def _review_personal(extracted: dict, existing: dict) -> list[dict]:
    reviews = []
    for field in SECTION_SPECS["personal"].fields:
        if field not in extracted:
            continue
        current = existing.get(field)
        if current in (None, ""):
            status = "missing_in_profile"
        elif _norm(current) == _norm(extracted[field]):
            status = "same"
        else:
            status = "different"
        reviews.append({
            "field": field, "extracted": extracted[field], "current": current or None, "status": status,
            "uncertain": field in extracted.get("uncertain_fields", []),
        })
    return reviews


# ---------- Point d'entrée ----------

def review_import(json_path, profile_path: Path | None = None) -> dict:
    """
    Compare une proposition d'import (JSON de candidate/import_cv.py) au profil candidat
    et renvoie ce qu'il faut afficher pour la valider. Ne modifie rien.
    """

    json_path = Path(json_path)
    try:
        imported = json.loads(json_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReviewError(f"le fichier « {json_path} » n'existe pas.")
    except json.JSONDecodeError as error:
        raise ReviewError(f"« {json_path.name} » n'est pas un JSON valide ({error}).")
    if not isinstance(imported, dict) or not isinstance(imported.get("profile"), dict):
        raise ReviewError(f"« {json_path.name} » n'est pas un import de CV (section « profile » manquante).")

    extracted = imported["profile"]
    profile = load_profile(profile_path).data

    review = {
        "source": {
            "json": str(json_path),
            "source_pdf": imported.get("source_pdf"),
            "extracted_at": imported.get("extracted_at"),
        },
        "warnings": list(imported.get("warnings") or []),
        "personal": _review_personal(extracted.get("personal") or {}, profile["personal"]),
    }

    for kind in ITEM_KINDS.values():
        proposals = []
        for number, item in enumerate(extracted.get(kind.section) or [], start=1):
            status, matches = _match_item(kind.section, item, profile[kind.section])
            proposals.append({
                "proposal_id": f"{kind.section}-{number}",
                "status": status,
                "data": {field: value for field, value in item.items() if field != "uncertain_fields"},
                "uncertain_fields": list(item.get("uncertain_fields") or []),
                "matches": matches,
            })
        review[kind.section] = proposals

    review["skills"] = _review_skills(extracted.get("skills") or {}, profile["skills"])
    review["languages"] = _review_languages(extracted.get("languages") or [], profile["languages"])
    review["interests"] = _review_interests(extracted.get("interests") or [], profile["interests"])

    counts: dict[str, int] = {}
    for section in ("experiences", "projects", "education", "skills", "languages", "interests"):
        for entry in review[section]:
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    review["summary"] = counts

    return review


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print('Usage: python -m candidate.review_import "<chemin du JSON extrait>"')
        sys.exit(1)

    try:
        result = review_import(sys.argv[1])
    except ReviewError as error:
        print(f"Comparaison impossible : {error}")
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))

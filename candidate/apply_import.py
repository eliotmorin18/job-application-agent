"""
Application des choix de l'utilisateur après l'import d'un CV.

`review_import()` (candidate/review_import.py) liste les propositions, chacune avec un
`proposal_id`. L'utilisateur décide, proposition par proposition ; `apply_import()`
applique UNIQUEMENT ces décisions explicites, avec les fonctions de candidate/manager.py.

Tout ou rien : les décisions sont d'abord toutes vérifiées, puis appliquées sur une copie
temporaire du profil, validée, qui remplace le profil d'un seul coup. Au moindre problème,
rien n'est enregistré.

Structure des décisions (dict, clé = proposal_id de review_import) :

    {
      # Expériences, projets, formations ("experiences-1", "projects-2", "education-1"...)
      "experiences-1": {"action": "skip"},
      "experiences-2": {"action": "add"},                       # tous les champs extraits
      "projects-1":    {"action": "add", "fields": ["name", "description"],   # une partie seulement
                        "allow_duplicate": True},               # obligatoire si la revue a vu un doublon
      "experiences-3": {"action": "update", "target_id": "cnrs-aubay",
                        "fields": ["responsibilities", "end_date"],          # champs repris de l'extraction
                        "clear": ["context"],                   # facultatif : champs à vider
                        "allow_less_precise": False},           # « 2026 » ne remplace pas « 2026-02 »
      "education-2":   {"action": "update", "target_position": 1, "fields": ["details"]},  # formation sans id

      # Compétences, langues, centres d'intérêt ("skills-3", "languages-1", "interests-2"...)
      "skills-3":     {"action": "add", "category": "programming",          # facultatif
                       "create_category": False},               # True pour créer une nouvelle catégorie
      "languages-1":  {"action": "update"},                     # niveau extrait -> langue correspondante
      "languages-4":  {"action": "add", "level": "B2"},         # niveau obligatoire s'il n'a pas été extrait
      "interests-2":  {"action": "add", "allow_duplicate": True},
      "interests-5":  {"action": "update", "target": "Skiing"}, # renomme « Skiing » avec le texte extrait

      # Coordonnées : seulement les champs cités
      "personal":     {"action": "update", "fields": ["phone", "linkedin"]},
    }

Règles :
- Une proposition sans décision est ignorée (jamais d'ajout ou de remplacement automatique).
- update d'une liste (responsibilities, skills, details...) : les nouvelles valeurs sont
  AJOUTÉES aux existantes, rien n'est retiré.
- update d'un texte : remplacé, sauf si la nouvelle valeur est moins précise (« 2026 » au
  lieu de « 2026-02 », « Paris » au lieu de « Paris, France ») sans allow_less_precise.
- Les id existants sont conservés. Une ancienne formation sans id reçoit un id, et elle seule.
"""

import os
import shutil
import sys
import json
from pathlib import Path

from candidate import manager
from candidate import profile as profile_module
from candidate.manager import ITEM_KINDS, DATE_PATTERN, ItemError, _category_key, _slug
from candidate.profile import ProfileError, load_profile
from candidate.review_import import review_import


ACTIONS = ("skip", "add", "update")
ITEM_SECTIONS = {kind.section: kind for kind in ITEM_KINDS.values()}
ADD_FUNCTIONS = {"experiences": manager.add_experience, "projects": manager.add_project, "education": manager.add_education}


class DecisionError(Exception):
    """Une ou plusieurs décisions sont invalides : rien n'a été enregistré."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Décisions refusées, rien n'a été enregistré :\n" + "\n".join(f"  - {problem}" for problem in problems))


# ---------- Comparaisons ----------

def _norm(value) -> str:
    return _slug(str(value or "")).replace("-", " ")


def _less_precise(new, current) -> bool:
    """« 2026 » face à « 2026-02 », « Paris » face à « Paris, France » : la nouvelle valeur en dit moins."""
    if current in (None, "", []) or new in (None, "", []):
        return False
    new, current = str(new), str(current)
    if DATE_PATTERN.match(new) and DATE_PATTERN.match(current):
        return len(new) < len(current) and current.startswith(new[:4])
    new_words, current_words = set(_norm(new).split()), set(_norm(current).split())
    return bool(new_words) and new_words < current_words


def _merge_list(current, extracted) -> list:
    """Valeurs existantes conservées, nouvelles valeurs ajoutées à la suite (sans doublon)."""
    merged = list(current or [])
    for value in extracted:
        if not any(_norm(value) == _norm(known) for known in merged):
            merged.append(value)
    return merged


# ---------- Forme des décisions ----------

# Options permises, selon le type de proposition et l'action
OPTIONS = {
    ("item", "add"): {"fields", "allow_duplicate"},
    ("item", "update"): {"target_id", "target_position", "fields", "clear", "allow_less_precise"},
    ("skills", "add"): {"category", "create_category", "allow_duplicate"},
    ("languages", "add"): {"level", "allow_duplicate"},
    ("languages", "update"): {"level"},
    ("interests", "add"): {"allow_duplicate"},
    ("interests", "update"): {"target"},
    ("personal", "update"): {"fields", "allow_less_precise"},
}
BOOLEAN_OPTIONS = {"allow_duplicate", "allow_less_precise", "create_category"}
TEXT_OPTIONS = {"target_id", "category", "level", "target"}
LIST_OPTIONS = {"fields", "clear"}


def _check_shape(where: str, group: str, decision: dict, problems: list) -> bool:
    """Options connues et du bon type, avant toute autre vérification."""
    action = decision["action"]
    allowed = OPTIONS.get((group, action), set())
    if (group, action) not in OPTIONS and action != "skip":
        problems.append(f"{where} : l'action « {action} » n'est pas possible ici.")
        return False

    errors = []
    unknown = sorted(set(decision) - allowed - {"action"})
    if unknown:
        errors.append(f"option(s) inconnue(s) : {', '.join(unknown)}"
                      + (f" (possibles : {', '.join(sorted(allowed))})" if allowed else ""))
    for key, value in decision.items():
        if key in BOOLEAN_OPTIONS and not isinstance(value, bool):
            errors.append(f"« {key} » doit valoir true ou false")
        elif key in TEXT_OPTIONS and (not isinstance(value, str) or not value.strip()):
            errors.append(f"« {key} » doit être un texte non vide")
        elif key in LIST_OPTIONS and (not isinstance(value, list) or not all(isinstance(v, str) for v in value)):
            errors.append(f"« {key} » doit être une liste de noms de champs, par ex. [\"context\"]")
        elif key == "target_position" and (isinstance(value, bool) or not isinstance(value, int)):
            errors.append("« target_position » doit être un numéro (1, 2...)")

    for error in errors:
        problems.append(f"{where} : {error}.")
    return not errors


# ---------- Préparation : tout est vérifié avant de modifier quoi que ce soit ----------

def _plan(review: dict, decisions: dict, profile: dict):
    """
    Transforme les décisions en opérations à appliquer, sans rien modifier.
    Renvoie (opérations, problèmes, compte rendu).
    """

    problems, operations = [], []
    report = {"added": [], "updated": [], "skipped": []}

    proposals = {}
    for section in ("experiences", "projects", "education", "skills", "languages", "interests"):
        for entry in review[section]:
            proposals[entry["proposal_id"]] = (section, entry)

    if not isinstance(decisions, dict):
        raise DecisionError(["les décisions doivent être un dictionnaire {proposal_id: décision}."])

    unknown = sorted(set(decisions) - set(proposals) - {"personal"})
    if unknown:
        problems.append(f"proposition(s) inconnue(s) : {', '.join(unknown)}.")

    batch: set = set()   # valeurs ajoutées par ce lot de décisions (deux fois la même : refusé)

    for proposal_id, (section, entry) in proposals.items():
        decision = decisions.get(proposal_id)
        if decision is None:
            report["skipped"].append({"proposal_id": proposal_id, "section": section, "reason": "aucune décision"})
            continue
        if not isinstance(decision, dict) or decision.get("action") not in ACTIONS:
            problems.append(f"{proposal_id} : « action » doit valoir {', '.join(ACTIONS)}.")
            continue
        group = "item" if section in ITEM_SECTIONS else section
        if not _check_shape(proposal_id, group, decision, problems):
            continue
        if decision["action"] == "skip":
            report["skipped"].append({"proposal_id": proposal_id, "section": section, "reason": "ignorée"})
            continue

        where = f"{proposal_id}"
        if section in ITEM_SECTIONS:
            _plan_item(where, ITEM_SECTIONS[section], entry, decision, profile, problems, operations, report)
        elif section == "skills":
            _plan_skill(where, entry, decision, profile, problems, operations, report, batch)
        elif section == "languages":
            _plan_language(where, entry, decision, profile, problems, operations, report, batch)
        else:
            _plan_interest(where, entry, decision, profile, problems, operations, report, batch)

    if "personal" in decisions:
        _plan_personal(review, decisions["personal"], problems, operations, report)

    return operations, problems, report


def _check_duplicate(where: str, entry: dict, decision: dict, problems: list) -> bool:
    if entry["status"] != "new" and not decision.get("allow_duplicate"):
        problems.append(f"{where} : la revue a signalé un doublon ({entry['status']}). "
                        "Pour l'ajouter quand même, ajoute \"allow_duplicate\": true.")
        return False
    return True


def _plan_item(where, kind, entry, decision, profile, problems, operations, report):
    data = entry["data"]
    action = decision["action"]

    fields = decision.get("fields")
    unknown = sorted(set(fields or []) - set(data))
    if unknown:
        problems.append(f"{where} : champ(s) absent(s) de l'extraction : {', '.join(unknown)}. "
                        f"Champs extraits : {', '.join(data)}.")
        return

    if action == "add":
        if not _check_duplicate(where, entry, decision, problems):
            return
        chosen = {field: data[field] for field in (fields or data)}
        record = {"proposal_id": where, "section": kind.section, "id": None}

        def add(path, chosen=chosen, record=record):
            record["id"] = ADD_FUNCTIONS[kind.section](chosen, path)

        operations.append(add)
        report["added"].append(record)
        return

    # update : cible explicite et champs choisis
    if not fields:
        problems.append(f"{where} : « fields » est obligatoire pour une mise à jour (les champs à reprendre).")
        return
    existing = profile[kind.section]
    target_id, target_position = decision.get("target_id"), decision.get("target_position")
    if target_id is not None:
        target = next((item for item in existing if isinstance(item, dict) and item.get("id") == target_id), None)
        if target is None:
            known = ", ".join(item["id"] for item in existing if isinstance(item, dict) and item.get("id")) or "aucun"
            problems.append(f"{where} : aucun(e) {kind.label} avec l'id « {target_id} » (ids : {known}).")
            return
        position = None
    elif target_position is not None:
        if not 1 <= target_position <= len(existing) or not isinstance(existing[target_position - 1], dict):
            problems.append(f"{where} : « target_position » doit être un numéro de {kind.label} entre 1 et {len(existing)}.")
            return
        target = existing[target_position - 1]
        target_id, position = target.get("id"), (None if target.get("id") else target_position)
    else:
        problems.append(f"{where} : indique la cible avec « target_id » (ou « target_position » pour une formation sans id).")
        return

    clear = decision.get("clear") or []
    bad_clear = sorted((set(clear) - set(kind.fields)) | (set(clear) & set(kind.required)) | (set(clear) & set(fields)))
    if bad_clear:
        problems.append(f"{where} : champ(s) impossible(s) à vider : {', '.join(bad_clear)} "
                        "(inconnu, obligatoire ou déjà mis à jour).")
        return

    changes = {}
    for field in fields:
        if field in kind.list_fields:
            changes[field] = _merge_list(target.get(field), data[field])
        else:
            if _less_precise(data[field], target.get(field)) and not decision.get("allow_less_precise"):
                problems.append(f"{where} : « {data[field]} » est moins précis que « {target.get(field)} » ({field}). "
                                "Retire ce champ ou ajoute \"allow_less_precise\": true.")
                return
            changes[field] = data[field]
    changes.update({field: None for field in clear})

    record = {"proposal_id": where, "section": kind.section, "id": target_id,
              "fields": list(fields), "cleared": list(clear)}

    def update(path, changes=changes, record=record, position=position):
        if position is not None:          # ancienne formation sans id : elle seule reçoit un id
            record["id"] = manager.assign_missing_ids(path, positions=[position])[position]
            record["id_assigned"] = True
        manager.update_item(kind.section, record["id"], changes, path)

    operations.append(update)
    report["updated"].append(record)


def _plan_skill(where, entry, decision, profile, problems, operations, report, batch):
    category = decision.get("category") or entry["category_in_profile"] or entry["category"]
    target = next((name for name in profile["skills"] if _category_key(str(name)) == _category_key(category)), None)
    if target is None and not decision.get("create_category"):
        problems.append(f"{where} : la catégorie « {category} » n'existe pas dans le profil. "
                        "Choisis une catégorie existante (« category ») ou ajoute \"create_category\": true.")
        return

    skill = entry["skill"]
    # Comme manager.add_skill : jamais deux fois la même compétence dans une catégorie (allow_duplicate n'y change rien)
    if target is not None and any(_norm(skill) == _norm(known) for known in profile["skills"][target] or []):
        problems.append(f"{where} : « {skill} » est déjà dans la catégorie « {target} » ; "
                        "une compétence ne peut pas y figurer deux fois.")
        return
    # Ailleurs dans le profil : permis par manager, mais seulement si l'utilisateur le confirme
    elsewhere = [name for name, values in profile["skills"].items() if any(_norm(skill) == _norm(v) for v in values or [])]
    if elsewhere and not decision.get("allow_duplicate"):
        problems.append(f"{where} : « {skill} » est déjà dans la catégorie « {elsewhere[0]} ». "
                        "Pour l'ajouter aussi dans « " + category + " », ajoute \"allow_duplicate\": true.")
        return
    key = ("skills", _category_key(category), _norm(skill))
    if key in batch:
        problems.append(f"{where} : « {skill} » est déjà ajoutée dans « {category} » par une autre décision.")
        return
    batch.add(key)

    record = {"proposal_id": where, "section": "skills", "value": skill, "category": target or category}

    def add(path, skill=skill, category=target or category, create=target is None, record=record):
        record["category"] = manager.add_skill(skill, category, path, create_category=create)

    operations.append(add)
    report["added"].append(record)


def _plan_language(where, entry, decision, profile, problems, operations, report, batch):
    level = decision.get("level") or entry.get("level")
    language = entry["language"]

    if decision["action"] == "add":
        # Comme manager.add_language : jamais deux fois le même nom (allow_duplicate n'y change rien)
        if any(isinstance(known, dict) and _norm(known.get("language")) == _norm(language) for known in profile["languages"]):
            problems.append(f"{where} : « {language} » est déjà dans le profil. Utilise plutôt « update » pour changer son niveau.")
            return
        # Langue équivalente sous un autre nom (Français / French) : seulement si l'utilisateur le confirme
        if entry["status"] == "duplicate" and not decision.get("allow_duplicate"):
            problems.append(f"{where} : « {language} » correspond à « {entry['matches'][0]['language']} » déjà dans le profil. "
                            "Utilise plutôt « update », ou ajoute \"allow_duplicate\": true pour l'ajouter quand même.")
            return
        if not level:
            problems.append(f"{where} : le niveau de « {language} » n'a pas été extrait : indique-le avec « level ».")
            return
        key = ("languages", _norm(language))
        if key in batch:
            problems.append(f"{where} : « {language} » est déjà ajoutée par une autre décision.")
            return
        batch.add(key)
        operations.append(lambda path, language=language, level=level: manager.add_language(language, level, path))
        report["added"].append({"proposal_id": where, "section": "languages", "value": language, "level": level})
        return

    if not entry["matches"]:
        problems.append(f"{where} : « {language} » n'est pas dans le profil : utilise « add ».")
        return
    if not level:
        problems.append(f"{where} : aucun niveau à reprendre pour « {language} » : indique-le avec « level ».")
        return
    existing = entry["matches"][0]["language"]
    operations.append(lambda path, existing=existing, level=level: manager.update_language(existing, level, path))
    report["updated"].append({"proposal_id": where, "section": "languages", "value": existing, "fields": ["level"], "level": level})


def _plan_interest(where, entry, decision, profile, problems, operations, report, batch):
    if decision["action"] == "add":
        # Comme manager.add_interest : jamais deux fois le même texte (allow_duplicate n'y change rien)
        if any(_norm(entry["interest"]) == _norm(known) for known in profile["interests"]):
            problems.append(f"{where} : « {entry['interest']} » est déjà dans les centres d'intérêt.")
            return
        if not _check_duplicate(where, entry, decision, problems):
            return
        key = ("interests", _norm(entry["interest"]))
        if key in batch:
            problems.append(f"{where} : « {entry['interest']} » est déjà ajouté par une autre décision.")
            return
        batch.add(key)
        operations.append(lambda path, interest=entry["interest"]: manager.add_interest(interest, path))
        report["added"].append({"proposal_id": where, "section": "interests", "value": entry["interest"]})
        return

    target = decision.get("target")
    if not target or not any(_norm(target) == _norm(known) for known in profile["interests"]):
        problems.append(f"{where} : indique avec « target » le centre d'intérêt existant à renommer "
                        f"(existants : {', '.join(profile['interests']) or 'aucun'}).")
        return
    operations.append(lambda path, target=target, new=entry["interest"]: manager.rename_interest(target, new, path))
    report["updated"].append({"proposal_id": where, "section": "interests", "value": target, "new_value": entry["interest"]})


def _plan_personal(review, decision, problems, operations, report):
    if not isinstance(decision, dict) or decision.get("action") not in ACTIONS:
        problems.append(f"personal : « action » doit valoir {', '.join(ACTIONS)}.")
        return
    if decision["action"] == "add":
        decision = {**decision, "action": "update"}      # pour les coordonnées, ajouter et mettre à jour reviennent au même
    if not _check_shape("personal", "personal", decision, problems):
        return
    if decision["action"] == "skip":
        report["skipped"].append({"proposal_id": "personal", "section": "personal", "reason": "ignorée"})
        return
    extracted = {entry["field"]: entry for entry in review["personal"]}
    fields = decision.get("fields")
    if not fields:
        problems.append("personal : « fields » est obligatoire (les coordonnées à reprendre).")
        return
    unknown = sorted(set(fields) - set(extracted))
    if unknown:
        problems.append(f"personal : champ(s) absent(s) de l'extraction : {', '.join(unknown)}.")
        return
    for field in fields:
        entry = extracted[field]
        if _less_precise(entry["extracted"], entry["current"]) and not decision.get("allow_less_precise"):
            problems.append(f"personal : « {entry['extracted']} » est moins précis que « {entry['current']} » ({field}).")
            return
    changes = {field: extracted[field]["extracted"] for field in fields}
    operations.append(lambda path, changes=changes: manager.update_personal(changes, path))
    report["updated"].append({"proposal_id": "personal", "section": "personal", "fields": list(fields)})


# ---------- Application : tout ou rien ----------

def _execute(path: Path, operations: list) -> None:
    """Applique les opérations sur une copie du profil ; la copie remplace le profil seulement si tout réussit."""
    working = path.with_name(f".{path.name}.import-tmp")
    shutil.copy2(path, working)
    try:
        for operation in operations:
            operation(working)
        load_profile(working)                     # le profil final doit être valide
        os.replace(working, path)
    except (ItemError, ProfileError, KeyError, ValueError) as error:
        raise DecisionError([f"l'application a échoué ({error}) ; le profil n'a pas été modifié."])
    finally:
        if working.exists():
            working.unlink()


def apply_import(json_path, decisions: dict, profile_path: Path | None = None) -> dict:
    """
    Applique les décisions de l'utilisateur sur une proposition d'import (JSON de
    candidate/import_cv.py) et renvoie le compte rendu :
        {"added": [...], "updated": [...], "skipped": [...], "profile": chemin}
    Tout ou rien : lève DecisionError (et n'enregistre rien) si une décision est invalide.
    """

    path = Path(profile_path) if profile_path else profile_module.CANDIDATE_PATH
    review = review_import(json_path, path)
    operations, problems, report = _plan(review, decisions, load_profile(path).data)

    if problems:
        raise DecisionError(problems)
    if operations:
        _execute(path, operations)

    report["profile"] = str(path)
    return report


if __name__ == "__main__":

    if len(sys.argv) != 3:
        print('Usage: python -m candidate.apply_import "<JSON extrait>" "<JSON des décisions>"')
        sys.exit(1)

    try:
        result = apply_import(sys.argv[1], json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    except DecisionError as error:
        print(error)
        sys.exit(1)

    print(json.dumps(result, indent=2, ensure_ascii=False))

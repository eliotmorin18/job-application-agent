"""
API locale du profil candidat, pour le frontend (frontend/).

Lancement (depuis la racine du projet) :  uvicorn api.main:app --reload

Les routes ne font qu'appeler candidate/manager.py (profil), candidate/import_cv.py,
candidate/review_import.py et candidate/apply_import.py (import d'un CV) : toute la
validation et l'écriture du YAML restent dans ces modules.

Les routes des CV (génération, liste, lecture, modification) sont dans api/cvs.py.

Les erreurs sont renvoyées au format :
    {"detail": {"message": "...", "problems": ["...", "..."]}}
"""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi import Body, Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse

from candidate import import_cv as import_module
from candidate import manager
from candidate.apply_import import DecisionError, apply_import
from candidate.import_cv import CVImportError, import_cv
from candidate.manager import ITEM_KINDS, ItemError
from candidate.profile import ProfileError, load_profile
from candidate.review_import import ReviewError, review_import
from api import cvs
from api.common import ApiError, profile_path
from cv.document import CVDocumentError


app = FastAPI(title="Job Application Agent")
app.include_router(cvs.router)

ITEM_SECTIONS = {kind.section: kind for kind in ITEM_KINDS.values()}
ADD_FUNCTIONS = {"experiences": manager.add_experience, "projects": manager.add_project, "education": manager.add_education}
MAX_PDF_BYTES = 10 * 1024 * 1024
IMPORT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


# ---------- Où sont les fichiers (remplacés par des dossiers temporaires dans les tests) ----------

def import_dirs() -> tuple[Path, Path]:
    """(dossier des PDF importés, dossier des propositions extraites)"""
    return import_module.IMPORTS_DIR, import_module.EXTRACTED_DIR


# ---------- Erreurs ----------

def _error(status: int, message: str, problems: list[str]) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": {"message": message, "problems": problems}})


@app.exception_handler(ApiError)
def _api_error(request: Request, error: ApiError):
    return _error(error.status, error.message, error.problems)


@app.exception_handler(ItemError)
def _item_error(request: Request, error: ItemError):
    return _error(422, str(error).split("\n")[0].rstrip(" :"), error.problems)


@app.exception_handler(ProfileError)
def _profile_error(request: Request, error: ProfileError):
    return _error(422, "Profil candidat invalide", error.problems)


@app.exception_handler(DecisionError)
def _decision_error(request: Request, error: DecisionError):
    return _error(422, "Décisions refusées, rien n'a été enregistré", error.problems)


@app.exception_handler(CVImportError)
def _import_error(request: Request, error: CVImportError):
    return _error(422, "Import impossible", [str(error)])


@app.exception_handler(CVDocumentError)
def _cv_document_error(request: Request, error: CVDocumentError):
    return _error(422, "CV invalide : rien n'a été enregistré", error.problems)


# ---------- Outils ----------

def _empty(value) -> bool:
    return value is None or value == "" or value == []


def _same(a, b) -> bool:
    if _empty(a) and _empty(b):
        return True
    if isinstance(a, list) and isinstance(b, list):
        return [str(x).strip() for x in a] == [str(x).strip() for x in b]
    if isinstance(a, list) or isinstance(b, list):
        return False
    return str(a).strip() == str(b).strip()


def _only_changes(current: dict, changes: dict) -> dict:
    """
    Le frontend renvoie tout le formulaire : on ne transmet à manager que les champs
    réellement modifiés (les autres gardent leur mise en forme dans le YAML).
    """
    if not isinstance(changes, dict):
        raise ApiError(422, "Requête invalide", ["le corps de la requête doit être un objet JSON {champ: valeur}."])
    return {field: value for field, value in changes.items() if not _same(value, current.get(field))}


def _section(section: str):
    kind = ITEM_SECTIONS.get(section)
    if kind is None:
        raise ApiError(404, "Section inconnue", [f"section inconnue : « {section} » (possibles : {', '.join(ITEM_SECTIONS)})."])
    return kind


def _locate(section: str, key: str, path: Path) -> tuple[dict, str | None, int | None]:
    """
    L'élément visé par `key` : son id, ou « index-N » (position N à partir de 0) pour une
    ancienne formation sans id. Renvoie (élément, id ou None, position 1, 2... si sans id).
    """
    items = load_profile(path).data[section]
    for item in items:
        if isinstance(item, dict) and item.get("id") == key:
            return item, key, None

    match = re.fullmatch(r"index-(\d+)", key)
    if match and int(match[1]) < len(items) and isinstance(items[int(match[1])], dict):
        item = items[int(match[1])]
        return item, item.get("id"), (None if item.get("id") else int(match[1]) + 1)

    known = ", ".join(item["id"] for item in items if isinstance(item, dict) and item.get("id")) or "aucun"
    raise ApiError(404, "Élément introuvable", [f"aucun(e) {_section(section).label} « {key} » (ids : {known})."])


def _atomically(path: Path, operation):
    """
    Plusieurs écritures (attribuer un id, puis modifier ou supprimer) appliquées sur une
    copie du profil, qui ne remplace le profil que si tout a réussi : jamais d'état partiel.
    """
    working = path.with_name(f".{path.name}.api-tmp")
    shutil.copy2(path, working)
    try:
        result = operation(working)
        load_profile(working)
        os.replace(working, path)
        return result
    finally:
        if working.exists():
            working.unlink()


def _item(section: str, item_id: str, path: Path) -> dict:
    return next(item for item in load_profile(path).data[section] if isinstance(item, dict) and item.get("id") == item_id)


def _text(payload: dict, field: str):
    return payload.get(field) if isinstance(payload, dict) else None


# ---------- Profil ----------

@app.get("/api/profile")
def get_profile(path: Path = Depends(profile_path)):
    return load_profile(path).data


@app.post("/api/profile/{section}", status_code=201)
def add_item(section: str, fields: dict = Body(...), path: Path = Depends(profile_path)):
    _section(section)
    new_id = ADD_FUNCTIONS[section](fields, path)
    return _item(section, new_id, path)


@app.patch("/api/profile/{section}/{key}")
def update_item(section: str, key: str, changes: dict = Body(...), path: Path = Depends(profile_path)):
    _section(section)
    current, item_id, position = _locate(section, key, path)
    changes = _only_changes(current, changes)

    if position is None:
        if changes:
            manager.update_item(section, item_id, changes, path)
        return _item(section, item_id, path)

    # Ancienne formation sans id : id attribué ET modification, en une seule fois
    def assign_and_update(working: Path) -> str:
        new_id = manager.assign_missing_ids(working, positions=[position])[position]
        if changes:
            manager.update_item(section, new_id, changes, working)
        return new_id

    return _item(section, _atomically(path, assign_and_update), path)


@app.delete("/api/profile/{section}/{key}")
def delete_item(section: str, key: str, path: Path = Depends(profile_path)):
    _section(section)
    _, item_id, position = _locate(section, key, path)

    if position is None:
        return {"deleted": manager.delete_item(section, item_id, path)}

    def assign_and_delete(working: Path) -> dict:
        new_id = manager.assign_missing_ids(working, positions=[position])[position]
        removed = manager.delete_item(section, new_id, working)
        removed.pop("id", None)          # id attribué seulement pour pouvoir supprimer
        return removed

    return {"deleted": _atomically(path, assign_and_delete)}


@app.patch("/api/personal")
def update_personal(changes: dict = Body(...), path: Path = Depends(profile_path)):
    changes = _only_changes(load_profile(path).data["personal"], changes)
    return manager.update_personal(changes, path) if changes else load_profile(path).data["personal"]


@app.patch("/api/career")
def update_career(changes: dict = Body(...), path: Path = Depends(profile_path)):
    changes = _only_changes(load_profile(path).data["career"], changes)
    return manager.update_career(changes, path) if changes else load_profile(path).data["career"]


@app.patch("/api/preferences")
def update_preferences(changes: dict = Body(...), path: Path = Depends(profile_path)):
    changes = _only_changes(load_profile(path).data["preferences"], changes)
    return manager.update_preferences(changes, path) if changes else load_profile(path).data["preferences"]


@app.post("/api/preferences/{category}")
def add_preference(category: str, payload: dict = Body(...), path: Path = Depends(profile_path)):
    manager.add_preference(category, _text(payload, "value"), path)
    return load_profile(path).data["preferences"]


# ---------- Compétences, langues, centres d'intérêt ----------

@app.post("/api/skills", status_code=201)
def add_skill(payload: dict = Body(...), path: Path = Depends(profile_path)):
    category = manager.add_skill(_text(payload, "skill"), _text(payload, "category"), path,
                                 create_category=payload.get("create_category") is True)
    return {"category": category, "skills": load_profile(path).data["skills"]}


@app.patch("/api/skills/{category}/{skill:path}")
def rename_skill(category: str, skill: str, payload: dict = Body(...), path: Path = Depends(profile_path)):
    manager.rename_skill(category, skill, _text(payload, "new_name"), path)
    return load_profile(path).data["skills"]


@app.delete("/api/skills/{category}/{skill:path}")
def delete_skill(category: str, skill: str, path: Path = Depends(profile_path)):
    manager.delete_skill(category, skill, path)
    return load_profile(path).data["skills"]


@app.post("/api/languages", status_code=201)
def add_language(payload: dict = Body(...), path: Path = Depends(profile_path)):
    manager.add_language(_text(payload, "language"), _text(payload, "level"), path)
    return load_profile(path).data["languages"]


@app.patch("/api/languages/{language:path}")
def update_language(language: str, payload: dict = Body(...), path: Path = Depends(profile_path)):
    return manager.update_language(language, _text(payload, "level"), path)


@app.delete("/api/languages/{language:path}")
def delete_language(language: str, path: Path = Depends(profile_path)):
    return {"deleted": manager.delete_language(language, path)}


@app.post("/api/interests", status_code=201)
def add_interest(payload: dict = Body(...), path: Path = Depends(profile_path)):
    manager.add_interest(_text(payload, "interest"), path)
    return load_profile(path).data["interests"]


@app.patch("/api/interests/{interest:path}")
def rename_interest(interest: str, payload: dict = Body(...), path: Path = Depends(profile_path)):
    return manager.rename_interest(interest, _text(payload, "new_name"), path)


@app.delete("/api/interests/{interest:path}")
def delete_interest(interest: str, path: Path = Depends(profile_path)):
    return manager.delete_interest(interest, path)


# ---------- Import d'un CV ----------

def _import_json(import_id: str, extracted_dir: Path) -> Path:
    json_path = extracted_dir / f"{import_id}.json"
    if not IMPORT_ID_PATTERN.match(import_id) or not json_path.is_file():
        raise ApiError(404, "Import introuvable", [f"aucun import « {import_id} »."])
    return json_path


def _review(json_path: Path, path: Path) -> dict:
    try:
        review = review_import(json_path, path)
    except ReviewError as error:
        raise ApiError(422, "Import illisible", [str(error)])
    review["source"].pop("json", None)        # chemin local : inutile au frontend
    review["import_id"] = json_path.stem
    return review


@app.get("/api/imports")
def list_imports(dirs: tuple[Path, Path] = Depends(import_dirs)):
    """Propositions déjà extraites (pour en reprendre une sans relancer l'extraction)."""
    imports = []
    for json_path in sorted(dirs[1].glob("*.json"), reverse=True) if dirs[1].is_dir() else []:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("profile"), dict):
            imports.append({"import_id": json_path.stem, "source_pdf": data.get("source_pdf"),
                            "extracted_at": data.get("extracted_at")})
    return imports


@app.post("/api/imports", status_code=201)
def create_import(file: UploadFile = File(...), path: Path = Depends(profile_path),
                  dirs: tuple[Path, Path] = Depends(import_dirs)):
    """Envoie le PDF à candidate/import_cv.py (qui appelle Claude), puis renvoie la comparaison."""
    content = file.file.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise ApiError(422, "Import impossible", ["le fichier dépasse 10 Mo."])

    name = Path(file.filename or "cv.pdf").name
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    folder = Path(tempfile.mkdtemp(prefix="cv-upload-"))
    try:
        pdf = folder / name
        pdf.write_bytes(content)
        try:
            json_path = import_cv(pdf, imports_dir=dirs[0], extracted_dir=dirs[1])
        except RuntimeError as error:          # Claude indisponible, délai dépassé...
            raise ApiError(502, "L'extraction a échoué", [str(error)])
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    return _review(json_path, path)


@app.get("/api/imports/{import_id}/review")
def get_review(import_id: str, path: Path = Depends(profile_path), dirs: tuple[Path, Path] = Depends(import_dirs)):
    return _review(_import_json(import_id, dirs[1]), path)


@app.post("/api/imports/{import_id}/apply")
def apply_decisions(import_id: str, payload: dict = Body(...), path: Path = Depends(profile_path),
                    dirs: tuple[Path, Path] = Depends(import_dirs)):
    try:
        report = apply_import(_import_json(import_id, dirs[1]), _text(payload, "decisions"), path)
    except ReviewError as error:
        raise ApiError(422, "Import illisible", [str(error)])
    report.pop("profile", None)               # chemin local
    return report

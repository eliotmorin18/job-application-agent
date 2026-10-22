"""
Routes « Mes CV » : génération à partir de l'URL d'une offre (tâche en arrière-plan),
liste, lecture, PDF, zones cliquables, modification d'un CV et analyse de correspondance
offre / profil (analysis.json : lue telle quelle, relancée seulement sur demande).

Un CV est désigné par le nom de son dossier dans cv/applications/ (ex. « acme-stage-ia »),
vérifié strictement : aucun chemin fourni par le frontend n'est utilisé tel quel.

Les générations tournent une par une dans un fil d'exécution (navigateur et Claude en local) ;
leur statut est gardé en mémoire : il est perdu si le serveur redémarre, pas les CV.
"""

import json
import re
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Body, Depends
from fastapi.responses import FileResponse

from api.common import ApiError, profile_path
from candidate.profile import ProfileError, load_profile
from cv import build_cv
from cv.analysis import analyze_folder, load_analysis
from cv.build_cv import ROOT, _count_pages, rebuild_cv
from cv.document import DOCUMENT_FILE, CVDocumentError, load_document, save_document, validate_document
from cv.layout import LAYOUT_FILE
from cv.pipeline import STEPS, generate_from_url
from jobs.url_check import UnsafeUrlError, check_public_url


router = APIRouter(prefix="/api/cvs")

CV_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,150}$")
TASK_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_TASKS = 50


# ---------- Ce qui est remplacé dans les tests ----------

def applications_dir() -> Path:
    return build_cv.APPLICATIONS_DIR


def cv_generator():
    """Le pipeline complet (cv/pipeline.py) ; remplacé par un faux dans les tests (pas de Claude)."""
    return generate_from_url


def cv_rebuilder():
    """Réécrit les sections depuis cv.json et recompile ; remplacé par un faux dans certains tests."""
    return rebuild_cv


def url_checker():
    return check_public_url


def cv_analyzer():
    """L'analyse de correspondance (cv/analysis.py) ; remplacée par un faux dans les tests (pas de Claude)."""
    return analyze_folder


# ---------- Messages d'erreur lisibles et sans chemin du serveur ----------

# Chemin absolu (pas « ./sections/x.tex », utile dans les erreurs LaTeX) : réduit à son dernier élément
_ABSOLUTE_PATH = re.compile(r"(?<![\w.~])/(?:[^\s/()'\"«»]+/)+([^\s/()'\"«»]+)")


def _clean(text) -> str:
    """Message sans chemin du serveur : chemins du projet relatifs, autres chemins absolus réduits à leur nom."""
    text = str(text).replace(str(ROOT) + "/", "").replace(str(ROOT), ".")
    text = _ABSOLUTE_PATH.sub(r"\1", text)
    return text if len(text) <= 1500 else text[:1500] + "…"


def _error_detail(error: Exception) -> dict:
    if isinstance(error, ProfileError):
        return {"message": "Profil candidat invalide", "problems": [_clean(p) for p in error.problems]}
    if isinstance(error, CVDocumentError):
        return {"message": "La réponse de Claude n'a pas pu être utilisée", "problems": [_clean(p) for p in error.problems]}
    if isinstance(error, RuntimeError):
        return {"message": "La génération a échoué", "problems": [_clean(error)]}
    if type(error).__module__.startswith("playwright"):
        first_line = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
        return {"message": "Impossible de lire la page de l'offre", "problems": [_clean(first_line)]}
    return {"message": "Erreur inattendue pendant la génération", "problems": [f"{type(error).__name__}"]}


# ---------- Tâches de génération (en mémoire) ----------

class TaskStore:
    """Statut des générations. Une seule génération à la fois ; les suivantes attendent (pending)."""

    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cv-generation")

    def create(self, url: str | None, kind: str = "generation", cv_id: str | None = None) -> dict:
        now = time.time()
        task = {"task_id": uuid.uuid4().hex, "kind": kind, "status": "pending", "step": "pending",
                "step_label": "En attente", "url": url, "cv_id": cv_id, "error": None, "result": None,
                "created_at": now, "updated_at": now}
        with self._lock:
            self._tasks[task["task_id"]] = task
            for old in sorted(self._tasks.values(), key=lambda t: t["created_at"])[:-MAX_TASKS]:
                if old["status"] in ("completed", "failed"):
                    del self._tasks[old["task_id"]]
        return dict(task)

    def update(self, task_id: str, **fields) -> None:
        with self._lock:
            self._tasks[task_id].update(fields, updated_at=time.time())

    def analysis_in_progress(self, cv_id: str) -> bool:
        with self._lock:
            return any(t["kind"] == "analysis" and t["cv_id"] == cv_id and t["status"] in ("pending", "running")
                       for t in self._tasks.values())

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return json.loads(json.dumps(task)) if task else None

    def submit(self, function, *args) -> None:
        self._executor.submit(function, *args)


class CvLocks:
    """Un seul enregistrement (ou une seule compilation) à la fois par CV."""

    def __init__(self):
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _lock(self, cv_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(cv_id, threading.Lock())

    def try_acquire(self, cv_id: str) -> bool:
        return self._lock(cv_id).acquire(blocking=False)

    def acquire(self, cv_id: str) -> None:
        self._lock(cv_id).acquire()

    def release(self, cv_id: str) -> None:
        self._lock(cv_id).release()


TASKS = TaskStore()
LOCKS = CvLocks()


def _run_generation(task_id: str, url: str, profile, generator, folder: Path) -> None:
    held = []

    def on_step(step: str, **details) -> None:
        TASKS.update(task_id, step=step, step_label=STEPS.get(step, step))
        if step == "compile":                       # le dossier existe : personne ne le modifie pendant la compilation
            cv_id = details["folder"].name
            LOCKS.acquire(cv_id)
            held.append(cv_id)
            TASKS.update(task_id, cv_id=cv_id)

    TASKS.update(task_id, status="running")
    try:
        result = generator(url, profile, on_step=on_step, applications_dir=folder)
    except Exception as error:                      # l'erreur est rendue lisible, jamais affichée telle quelle
        TASKS.update(task_id, status="failed", error=_error_detail(error))
    else:
        analysis = result.analysis or {}
        TASKS.update(task_id, status="completed", step="done", step_label="Terminé", cv_id=result.folder.name,
                     result={"pages": result.pages, "fits_one_page": result.pages == 1,
                             "verification_issues": len(result.issues), "gaps": len(result.document["gaps"]),
                             "analysis_status": analysis.get("status", "missing"),
                             "fit_score": (analysis.get("score") or {}).get("value")})
    finally:
        for cv_id in held:
            LOCKS.release(cv_id)


# ---------- Dossiers des CV ----------

def _cv_folder(cv_id: str, base: Path) -> Path:
    """Le dossier du CV `cv_id`, uniquement s'il est directement dans cv/applications/. Sinon 404."""
    if not isinstance(cv_id, str) or not CV_ID_PATTERN.match(cv_id):
        raise ApiError(404, "CV introuvable", [f"aucun CV « {cv_id[:80]} »."])
    base = Path(base).resolve()
    folder = (base / cv_id).resolve()
    if folder.parent != base or not folder.is_dir() or folder.is_symlink():
        raise ApiError(404, "CV introuvable", [f"aucun CV « {cv_id} »."])
    return folder


def _main_tex(folder: Path) -> Path | None:
    return next(iter(sorted(folder.glob("*.tex"))), None)


def _pdf(folder: Path) -> Path | None:
    main_tex = _main_tex(folder)
    pdf = folder / "build" / f"{main_tex.stem}.pdf" if main_tex else None
    return pdf if pdf and pdf.is_file() else None


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pages(folder: Path) -> int | None:
    layout = _read_json(folder / "build" / LAYOUT_FILE)
    if isinstance(layout, dict) and isinstance(layout.get("pages"), int):
        return layout["pages"]
    main_tex = _main_tex(folder)
    log = folder / "build" / f"{main_tex.stem}.log" if main_tex else None
    if log and log.is_file() and _pdf(folder):
        return _count_pages(log.read_text(errors="ignore")) or None
    return None


def _analysis_summary(folder: Path) -> dict:
    """Statut de l'analyse (completed, failed, missing, running) et score, sans jamais la lancer."""
    analysis = load_analysis(folder)
    status = "running" if TASKS.analysis_in_progress(folder.name) else (analysis or {}).get("status", "missing")
    score = (analysis or {}).get("score") or {}
    return {"analysis_status": status, "fit_score": score.get("value"), "fit_level": score.get("level")}


def _summary(folder: Path) -> dict:
    """Métadonnées d'un CV, pour la liste et l'en-tête de l'éditeur."""
    doc = _read_json(folder / DOCUMENT_FILE)
    offer = _read_json(folder / "offer.json") or {}
    selection = _read_json(folder / "selection.json") or {}
    doc = doc if isinstance(doc, dict) else None
    pdf = _pdf(folder)
    pages = _pages(folder)
    stamps = [p.stat().st_mtime for p in (folder / DOCUMENT_FILE, pdf) if p and p.exists()]
    stat = folder.stat()
    return {
        "id": folder.name,
        "company": (doc or {}).get("company") or offer.get("company"),
        "role": (doc or {}).get("role") or offer.get("job_title"),
        "job_title": offer.get("job_title"),
        "language": (doc or {}).get("language") or selection.get("language"),
        "source_url": offer.get("source_url"),
        "editable": doc is not None,               # les CV créés avant cv.json se consultent seulement
        "has_pdf": pdf is not None,
        "has_layout": (folder / "build" / LAYOUT_FILE).is_file(),
        "pages": pages,
        "fits_one_page": pages == 1 if pages else None,
        "verification_issues": len(selection.get("verification_issues") or []),
        **_analysis_summary(folder),
        "created_at": getattr(stat, "st_birthtime", stat.st_ctime),
        "updated_at": max(stamps) if stamps else stat.st_mtime,
    }


# ---------- Routes ----------

@router.post("/generate", status_code=202)
def generate(payload: dict = Body(...), path: Path = Depends(profile_path), base: Path = Depends(applications_dir),
             generator=Depends(cv_generator), check_url=Depends(url_checker)):
    """{"url": "..."} -> {"task_id", "status"} ; la génération continue en arrière-plan."""
    url = payload.get("url") if isinstance(payload, dict) else None
    try:
        url = check_url(url)
    except UnsafeUrlError as error:
        raise ApiError(422, "URL refusée", [str(error)])
    profile = load_profile(path)                   # profil invalide : erreur immédiate, avant le navigateur
    task = TASKS.create(url)
    TASKS.submit(_run_generation, task["task_id"], url, profile, generator, Path(base))
    return {"task_id": task["task_id"], "status": task["status"]}


@router.get("/tasks/{task_id}")
def task_status(task_id: str):
    task = TASKS.get(task_id) if TASK_ID_PATTERN.match(task_id) else None
    if task is None:
        raise ApiError(404, "Tâche introuvable", [f"aucune tâche « {task_id[:40]} » (le serveur a peut-être redémarré)."])
    return task


@router.get("")
def list_cvs(base: Path = Depends(applications_dir)):
    base = Path(base)
    folders = [f for f in base.iterdir() if f.is_dir() and not f.is_symlink() and CV_ID_PATTERN.match(f.name)] \
        if base.is_dir() else []
    return sorted((_summary(f) for f in folders), key=lambda cv: cv["updated_at"], reverse=True)


@router.get("/{cv_id}")
def read_cv(cv_id: str, base: Path = Depends(applications_dir)):
    folder = _cv_folder(cv_id, base)
    if not (folder / DOCUMENT_FILE).is_file():
        raise ApiError(409, "CV non modifiable", ["ce CV a été créé avant cv.json : seul son PDF est consultable."])
    selection = _read_json(folder / "selection.json") or {}
    return {"cv": _summary(folder), "document": load_document(folder),
            "verification_issues": selection.get("verification_issues") or []}


@router.get("/{cv_id}/pdf")
def read_pdf(cv_id: str, base: Path = Depends(applications_dir)):
    pdf = _pdf(_cv_folder(cv_id, base))
    if pdf is None:
        raise ApiError(404, "PDF introuvable", ["ce CV n'a pas encore de PDF compilé."])
    return FileResponse(pdf, media_type="application/pdf", filename=pdf.name, content_disposition_type="inline",
                        headers={"Cache-Control": "no-store"})


@router.get("/{cv_id}/layout")
def read_layout(cv_id: str, base: Path = Depends(applications_dir)):
    layout = _read_json(_cv_folder(cv_id, base) / "build" / LAYOUT_FILE)
    if not isinstance(layout, dict):
        raise ApiError(404, "Zones introuvables", ["ce CV n'a pas de zones cliquables (CV créé avant les marqueurs ?)."])
    return layout


def _check_new_items(doc: dict, current: dict, path: Path) -> None:
    """Un élément ajouté (source_id absent du CV enregistré) doit exister dans le profil."""
    added = {section: {e.get("source_id") for e in doc[section]} - {e["source_id"] for e in current[section]}
             for section in ("experiences", "education", "projects")}
    if any(added.values()):
        validate_document({**doc, **{s: [e for e in doc[s] if e.get("source_id") in ids] for s, ids in added.items()}},
                          load_profile(path).data)


@router.put("/{cv_id}")
def update_cv(cv_id: str, doc: dict = Body(...), path: Path = Depends(profile_path),
              base: Path = Depends(applications_dir), rebuilder=Depends(cv_rebuilder)):
    """
    Enregistre le CV modifié et recompile le PDF. Le document est validé avant toute écriture ;
    si la compilation échoue, cv.json, les sections, le PDF et layout.json précédents sont restaurés.
    """
    folder = _cv_folder(cv_id, base)
    if not (folder / DOCUMENT_FILE).is_file():
        raise ApiError(409, "CV non modifiable", ["ce CV a été créé avant cv.json : il ne peut pas être modifié."])
    if not LOCKS.try_acquire(cv_id):
        raise ApiError(409, "CV en cours de modification", ["une autre modification de ce CV est en cours : réessaie dans un instant."])
    backup = Path(tempfile.mkdtemp(prefix="cv-backup-"))
    try:
        current = load_document(folder)
        validate_document(doc)
        _check_new_items(doc, current, path)

        kept = [folder / DOCUMENT_FILE, folder / "sections", folder / "build" / LAYOUT_FILE]
        if _pdf(folder):
            kept.append(_pdf(folder))
        for item in kept:
            if item.exists():
                target = backup / item.relative_to(folder)
                target.parent.mkdir(parents=True, exist_ok=True)
                (shutil.copytree if item.is_dir() else shutil.copy2)(item, target)

        save_document(folder, doc)
        try:
            pdf, pages = rebuilder(folder)
        except Exception as error:
            for item in kept:                       # retour à la dernière version valide
                saved = backup / item.relative_to(folder)
                if item.is_dir():
                    shutil.rmtree(item)
                elif item.exists():
                    item.unlink()
                if saved.exists():
                    (shutil.copytree if saved.is_dir() else shutil.copy2)(saved, item)
            problems = [_clean(error)] if isinstance(error, RuntimeError) else [type(error).__name__]
            raise ApiError(422, "La compilation a échoué : la version précédente du CV a été conservée.", problems)
        return {"cv": _summary(folder), "document": load_document(folder), "pages": pages, "fits_one_page": pages == 1,
                "has_layout": (folder / "build" / LAYOUT_FILE).is_file()}
    finally:
        LOCKS.release(cv_id)
        shutil.rmtree(backup, ignore_errors=True)


# ---------- Analyse de correspondance offre / profil ----------

def _run_analysis(task_id: str, folder: Path, profile, analyzer) -> None:
    TASKS.update(task_id, status="running", step="analyze_fit", step_label=STEPS["analyze_fit"])
    try:
        analysis = analyzer(folder, profile)
    except Exception as error:                      # analyse non enregistrée : l'ancienne reste en place
        TASKS.update(task_id, status="failed", error=_error_detail(error))
    else:
        score = analysis.get("score") or {}
        TASKS.update(task_id, status="completed", step="done", step_label="Terminé",
                     result={"analysis_status": analysis.get("status"), "fit_score": score.get("value"),
                             "fit_level": score.get("level")})


@router.get("/{cv_id}/analysis")
def read_analysis(cv_id: str, base: Path = Depends(applications_dir)):
    """L'analyse enregistrée (completed ou failed). Ne lance jamais Claude : voir POST pour la générer."""
    folder = _cv_folder(cv_id, base)
    analysis = load_analysis(folder)
    if analysis is None:
        raise ApiError(404, "Analyse non disponible",
                       ["aucune analyse pour ce CV : demande-la avec POST /api/cvs/{cv_id}/analysis."])
    if analysis.get("status") == "failed":
        error = analysis.get("error") or {}
        analysis = {**analysis, "error": {"message": error.get("message", "L'analyse a échoué"),
                                          "problems": [_clean(p) for p in error.get("problems") or []]}}
    return {**analysis, "running": TASKS.analysis_in_progress(folder.name)}


@router.post("/{cv_id}/analysis", status_code=202)
def request_analysis(cv_id: str, path: Path = Depends(profile_path), base: Path = Depends(applications_dir),
                     analyzer=Depends(cv_analyzer)):
    """
    Lance (ou relance) l'analyse de correspondance en arrière-plan, sans régénérer le CV ;
    fonctionne aussi pour les CV créés avant cette fonctionnalité. -> {"task_id", "status"}
    """
    folder = _cv_folder(cv_id, base)
    if not (folder / "offer.json").is_file():
        raise ApiError(409, "Analyse impossible", ["l'offre de cette candidature (offer.json) n'est pas connue."])
    if TASKS.analysis_in_progress(cv_id):
        raise ApiError(409, "Analyse déjà en cours", ["une analyse de ce CV est déjà en cours ou en attente."])
    profile = load_profile(path)
    task = TASKS.create(None, kind="analysis", cv_id=cv_id)
    TASKS.submit(_run_analysis, task["task_id"], folder, profile, analyzer)
    return {"task_id": task["task_id"], "status": task["status"]}


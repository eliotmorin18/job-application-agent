import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from cv.document import load_document, save_document, selected_ids, validate_document
from cv.layout import LAYOUT_FILE, write_layout
from cv.render import render_sections


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "cv" / "template"
TEMPLATE_MAIN = "main.tex"
APPLICATIONS_DIR = ROOT / "cv" / "applications"


def _ascii_words(text: str) -> list[str]:
    """'Stage IA Optimisation (F/H)' -> ['Stage', 'IA', 'Optimisation', 'F', 'H']"""

    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()

    return re.findall(r"[A-Za-z0-9]+", ascii_text)


def _new_application_dir(company: str, role: str, applications_dir: Path | None = None) -> Path:
    """cv/applications/<company>-<role>/, avec -2, -3... si le dossier existe déjà."""

    applications_dir = Path(applications_dir) if applications_dir else APPLICATIONS_DIR
    base = "-".join(_ascii_words(company) + _ascii_words(role)).lower() or "cv"
    folder = applications_dir / base
    number = 2

    while folder.exists():
        folder = applications_dir / f"{base}-{number}"
        number += 1

    return folder


def write_sections(folder: Path, doc: dict) -> None:
    """Écrit les six fichiers sections/*.tex du CV à partir de son contenu structuré (cv.json)."""

    for name, content in render_sections(doc).items():
        (Path(folder) / "sections" / f"{name}.tex").write_text(content.strip() + "\n", encoding="utf-8")


def write_cv(doc: dict, offer: dict, verification_issues: list | None = None,
             applications_dir: Path | None = None) -> Path:
    """
    Crée cv/applications/<company>-<role>/ depuis le template, y écrit le CV structuré
    (cv.json), les sections LaTeX calculées à partir de lui, l'offre et la sélection,
    puis renvoie le chemin du .tex principal.
    """

    validate_document(doc)
    folder = _new_application_dir(doc["company"], doc["role"], applications_dir)

    shutil.copytree(TEMPLATE_DIR, folder)

    name_parts = _ascii_words(doc["header"]["name"]) + ["Candidature"]
    name_parts += _ascii_words(doc["company"]) + _ascii_words(doc["role"])
    main_tex = folder / ("_".join(name_parts) + ".tex")

    (folder / TEMPLATE_MAIN).rename(main_tex)

    write_sections(folder, doc)
    save_document(folder, doc)

    # Garder une trace de l'offre et des choix de Claude à côté du CV
    (folder / "offer.json").write_text(json.dumps(offer, indent=2, ensure_ascii=False), encoding="utf-8")

    experience_ids, project_ids = selected_ids(doc)
    selection = {
        "language": doc["language"],
        "selected_experience_ids": experience_ids,
        "selected_project_ids": project_ids,
        "gaps": doc["gaps"],
        "verification_issues": verification_issues or [],
    }
    (folder / "selection.json").write_text(json.dumps(selection, indent=2, ensure_ascii=False), encoding="utf-8")

    return main_tex


def rebuild_cv(folder: Path, timeout: int = 180) -> tuple[Path, int]:
    """
    Relit cv.json, réécrit les sections LaTeX et recompile le PDF (après une modification du CV).
    Renvoie (chemin du PDF, nombre de pages). Les CV créés avant cv.json ne sont pas concernés.
    """

    folder = Path(folder)
    doc = load_document(folder)
    main_tex = next(path for path in sorted(folder.glob("*.tex")))
    write_sections(folder, doc)
    return compile_cv(main_tex, timeout)


def compile_cv(main_tex: Path, timeout: int = 180) -> tuple[Path, int]:
    """
    Compile le CV avec latexmk dans build/ et renvoie (chemin du PDF, nombre de pages).
    Écrit aussi build/layout.json (zones cliquables, cv/layout.py) à partir de la même
    compilation ; l'ancien est supprimé avant, pour qu'un échec n'en laisse jamais d'obsolète.
    """

    if shutil.which("latexmk") is None:
        raise RuntimeError("La commande 'latexmk' est introuvable. LaTeX (MacTeX) est-il installé ?")

    layout = main_tex.parent / "build" / LAYOUT_FILE
    if layout.exists():
        layout.unlink()

    result = subprocess.run(
        [
            "latexmk",
            "-pdf",
            "-interaction=nonstopmode",
            "-file-line-error",
            "-outdir=build",
            main_tex.name,
        ],
        cwd=main_tex.parent,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    pdf = main_tex.parent / "build" / main_tex.with_suffix(".pdf").name

    if result.returncode != 0 or not pdf.exists():
        errors = [line for line in result.stdout.splitlines() if ".tex:" in line]
        details = "\n".join(errors[:10]) or result.stdout[-2000:]
        raise RuntimeError(f"La compilation LaTeX a échoué ({main_tex}) :\n{details}")

    log = (main_tex.parent / "build" / main_tex.with_suffix(".log").name).read_text(errors="ignore")
    pages = _count_pages(log)

    write_layout(main_tex.parent / "build", pdf, pages)

    return pdf, pages


def _count_pages(log: str) -> int:
    """
    Nombre de pages lu dans le journal LaTeX ("Output written on X.pdf (1 page, ...)").
    LaTeX coupe ses lignes à 79 caractères : selon la longueur du nom du PDF, un retour
    à la ligne peut tomber entre le chiffre et « page ». Renvoie 0 si rien n'est trouvé.
    """

    match = re.search(r"Output written on .*?\(\s*(\d+)\s+pages?", log, re.DOTALL)
    return int(match.group(1)) if match else 0

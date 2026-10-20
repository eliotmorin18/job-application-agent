import json
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "cv" / "template"
TEMPLATE_MAIN = "main.tex"
APPLICATIONS_DIR = ROOT / "cv" / "applications"


def _ascii_words(text: str) -> list[str]:
    """'Stage IA Optimisation (F/H)' -> ['Stage', 'IA', 'Optimisation', 'F', 'H']"""

    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()

    return re.findall(r"[A-Za-z0-9]+", ascii_text)


def _new_application_dir(company: str, role: str) -> Path:
    """cv/applications/<company>-<role>/, avec -2, -3... si le dossier existe déjà."""

    base = "-".join(_ascii_words(company) + _ascii_words(role)).lower()
    folder = APPLICATIONS_DIR / base
    number = 2

    while folder.exists():
        folder = APPLICATIONS_DIR / f"{base}-{number}"
        number += 1

    return folder


def write_cv(cv: dict, offer: dict) -> Path:
    """
    Crée cv/applications/<company>-<role>/ depuis le template, y écrit les sections
    générées et renvoie le chemin du .tex principal.
    """

    folder = _new_application_dir(cv["company"], cv["role"])

    shutil.copytree(TEMPLATE_DIR, folder)

    first_name, last_name = cv["candidate_name"]
    name_parts = _ascii_words(first_name) + _ascii_words(last_name) + ["Candidature"]
    name_parts += _ascii_words(cv["company"]) + _ascii_words(cv["role"])
    main_tex = folder / ("_".join(name_parts) + ".tex")

    (folder / TEMPLATE_MAIN).rename(main_tex)

    for name, content in cv["sections"].items():
        (folder / "sections" / f"{name}.tex").write_text(content.strip() + "\n", encoding="utf-8")

    # Garder une trace de l'offre et des choix de Claude à côté du CV
    (folder / "offer.json").write_text(json.dumps(offer, indent=2, ensure_ascii=False), encoding="utf-8")

    keys = ["language", "selected_experience_ids", "selected_project_ids", "gaps", "verification_issues"]
    selection = {key: cv.get(key) for key in keys}
    (folder / "selection.json").write_text(json.dumps(selection, indent=2, ensure_ascii=False), encoding="utf-8")

    return main_tex


def compile_cv(main_tex: Path, timeout: int = 180) -> tuple[Path, int]:
    """Compile le CV avec latexmk dans build/ et renvoie (chemin du PDF, nombre de pages)."""

    if shutil.which("latexmk") is None:
        raise RuntimeError("La commande 'latexmk' est introuvable. LaTeX (MacTeX) est-il installé ?")

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

    return pdf, _count_pages(log)


def _count_pages(log: str) -> int:
    """
    Nombre de pages lu dans le journal LaTeX ("Output written on X.pdf (1 page, ...)").
    LaTeX coupe ses lignes à 79 caractères : selon la longueur du nom du PDF, un retour
    à la ligne peut tomber entre le chiffre et « page ». Renvoie 0 si rien n'est trouvé.
    """

    match = re.search(r"Output written on .*?\(\s*(\d+)\s+pages?", log, re.DOTALL)
    return int(match.group(1)) if match else 0

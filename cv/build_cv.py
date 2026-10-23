import copy
import json
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from cv.document import load_document, save_document, selected_ids, validate_document
from cv.layout import LAYOUT_FILE, write_layout
from cv.metadata import create_metadata
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
    (cv.json), les sections LaTeX calculées à partir de lui, l'offre, la sélection et les
    dates de la candidature (metadata.json), puis renvoie le chemin du .tex principal.
    """

    validate_document(doc)
    folder = _new_application_dir(doc["company"], doc["role"], applications_dir)

    shutil.copytree(TEMPLATE_DIR, folder)
    # Date de création explicite : celle du dossier est celle du template (copytree copie ses dates)
    create_metadata(folder)

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
    pages = pdf_pages(pdf) or _count_pages(log)

    write_layout(main_tex.parent / "build", pdf, pages)

    return pdf, pages


def pdf_pages(pdf: Path) -> int:
    """Nombre réel de pages du PDF (0 s'il ne peut pas être lu)."""
    try:
        return len(PdfReader(str(pdf)).pages)
    except Exception:                               # PDF illisible : le nombre reste inconnu
        return 0


# ---------- Une page au maximum ----------

# Compilations supplémentaires au plus pour ramener un CV trop long à une page (aucun appel à Claude)
MAX_FIT_COMPILES = 6


class CvTooLongError(RuntimeError):
    """Le CV dépasse une page malgré les ajustements : il est enregistré tel que rédigé, à raccourcir."""

    def __init__(self, folder: Path, pages: int, adjustments: list[str]):
        self.folder, self.pages, self.adjustments = Path(folder), pages, adjustments
        count = f"{pages} pages" if pages else "un nombre de pages inconnu"
        super().__init__(f"Le CV ne tient pas sur une page, même après les ajustements automatiques (le PDF fait "
                         f"{count}). Il a été enregistré tel que rédigé : raccourcis-le dans l'éditeur (onglet « CV »).")


@dataclass
class FitResult:
    pdf: Path
    pages: int
    document: dict
    adjustments: list[str] = field(default_factory=list)


def _trim(entries: list, first: int, others: int) -> bool:
    """Garde au plus `first` puces pour la première entrée, `others` pour les suivantes. True si modifié."""
    changed = False
    for n, entry in enumerate(entries):
        keep = first if n == 0 else others
        if len(entry["bullets"]) > keep:
            entry["bullets"] = entry["bullets"][:keep]
            changed = True
    return changed


def _secondary_bullets(doc: dict) -> str | None:
    projects = _trim(doc["projects"], 2, 1)
    education = _trim(doc["education"], 1, 1)
    return "Détails secondaires des projets et des formations retirés." if projects or education else None


def _last_project(doc: dict) -> str | None:
    if len(doc["projects"]) > 1:
        return f"Projet « {doc['projects'].pop()['name']} » retiré (le moins pertinent pour l'offre)."
    return None


def _last_education(doc: dict) -> str | None:
    if len(doc["education"]) > 2:
        return f"Formation « {doc['education'].pop()['institution']} » retirée (la moins utile pour l'offre)."
    return None


def _experience_bullets(doc: dict) -> str | None:
    return "Puces secondaires des expériences retirées." if _trim(doc["experiences"], 3, 2) else None


def _interests(doc: dict) -> str | None:
    if len(doc["interests"]) > 3:
        doc["interests"] = doc["interests"][:3]
        return "Centres d'intérêt limités à trois."
    return None


def _last_experience(doc: dict) -> str | None:
    if len(doc["experiences"]) > 2:
        experience = doc["experiences"].pop()
        name = " — ".join(part for part in (experience["title"], experience["organization"]) if part)
        return f"Expérience « {name} » retirée (la moins pertinente pour l'offre)."
    return None


# Du moins important au plus important. Claude ordonne chaque liste par pertinence (cv/generate.py) :
# on retire toujours en fin de liste. Rien n'est réécrit : aucune information ne peut être ajoutée.
REDUCTIONS = (_secondary_bullets, _last_project, _last_education, _last_education, _experience_bullets,
              _interests, _last_experience)


def _apply(folder: Path, doc: dict, main_tex: Path, compile_pdf) -> tuple[Path, int]:
    write_sections(folder, doc)
    save_document(folder, doc)
    return compile_pdf(main_tex)


def fit_one_page(main_tex: Path, doc: dict, compile_pdf=None) -> FitResult:
    """
    Compile le CV et le ramène à une page si besoin, en retirant le contenu secondaire (une
    réduction à la fois, au plus MAX_FIT_COMPILES compilations de plus, sans appel à Claude).
    cv.json et selection.json décrivent toujours le PDF obtenu. Si une page ne peut pas être
    atteinte, le CV d'origine est remis (contenu complet, à raccourcir à la main) et
    CvTooLongError est levée : jamais de succès avec plus d'une page.
    """
    compile_pdf = compile_pdf or compile_cv
    folder = main_tex.parent
    pdf, pages = compile_pdf(main_tex)
    if pages == 1:
        return FitResult(pdf, pages, doc)

    current, adjustments, compiles = copy.deepcopy(doc), [], 0
    for reduce in REDUCTIONS:
        if compiles >= MAX_FIT_COMPILES:
            break
        note = reduce(current)
        if note is None:
            continue
        adjustments.append(note)
        compiles += 1
        pdf, pages = _apply(folder, current, main_tex, compile_pdf)
        if pages == 1:
            _record_adjustments(folder, current, adjustments)
            return FitResult(pdf, pages, current, adjustments)

    _, pages = _apply(folder, doc, main_tex, compile_pdf)  # contenu complet : l'utilisateur choisit quoi retirer
    raise CvTooLongError(folder, pages, adjustments)


def _record_adjustments(folder: Path, doc: dict, adjustments: list[str]) -> None:
    """selection.json garde les éléments réellement dans le CV et la liste des ajustements faits."""
    path = folder / "selection.json"
    try:
        selection = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        selection = {}
    experience_ids, project_ids = selected_ids(doc)
    selection.update(selected_experience_ids=experience_ids, selected_project_ids=project_ids,
                     page_adjustments=adjustments)
    path.write_text(json.dumps(selection, indent=2, ensure_ascii=False), encoding="utf-8")


def _count_pages(log: str) -> int:
    """
    Nombre de pages lu dans le journal LaTeX ("Output written on X.pdf (1 page, ...)").
    LaTeX coupe ses lignes à 79 caractères : selon la longueur du nom du PDF, un retour
    à la ligne peut tomber entre le chiffre et « page ». Renvoie 0 si rien n'est trouvé.
    """

    match = re.search(r"Output written on .*?\(\s*(\d+)\s+pages?", log, re.DOTALL)
    return int(match.group(1)) if match else 0

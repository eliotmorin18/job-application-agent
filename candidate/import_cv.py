"""
Import d'un CV PDF : extraction du texte, puis Claude propose un profil structuré (JSON).

Ce module lit le PDF (pypdf), corrige le texte et gère les fichiers. L'extraction des
informations par Claude est dans candidate/extract_profile.py.

Le résultat est une PROPOSITION à valider, enregistrée dans profile/private/extracted/ :
rien n'est écrit dans candidate.yaml. Le PDF fourni est copié dans profile/private/imports/
pour garder une trace de la source.

Réutilisable par la future API : import_cv(chemin du PDF) -> chemin du JSON.
"""

import json
import logging
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from candidate.extract_profile import extract_profile


# pypdf écrit ses propres avertissements techniques sur les PDF abîmés : on affiche les nôtres
logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
IMPORTS_DIR = ROOT / "profile" / "private" / "imports"
EXTRACTED_DIR = ROOT / "profile" / "private" / "extracted"

# En dessous, le PDF ne contient pas de texte exploitable (souvent un CV scanné : pas d'OCR)
MIN_TEXT_CHARACTERS = 200

class CVImportError(Exception):
    """Le CV ne peut pas être importé (fichier absent, PDF illisible, pas de texte...)."""


# ---------- 1. Texte du PDF ----------

# Accents séparés de leur lettre dans les PDF produits par LaTeX : « d´ eveloppement »
_COMBINING = {"´": "́", "`": "̀", "ˆ": "̂", "¨": "̈", "˜": "̃"}


def _fix_accents(text: str) -> str:
    """« d´ eveloppement » -> « développement », « fran¸ cais » -> « français »."""
    text = re.sub(r"([´`ˆ¨˜])\s?([A-Za-zı])", lambda m: ("i" if m[2] == "ı" else m[2]) + _COMBINING[m[1]], text)
    text = re.sub(r"¸\s?([cC])", lambda m: m[1] + "̧", text)
    text = re.sub(r"([cC])\s?¸", lambda m: m[1] + "̧", text)
    return unicodedata.normalize("NFC", text)


def extract_pdf_text(pdf_path: Path) -> str:
    """Texte d'un PDF. Erreur claire si le fichier est absent, illisible ou sans texte."""

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise CVImportError(f"le fichier « {pdf_path} » n'existe pas.")

    try:
        reader = PdfReader(pdf_path)
        if reader.is_encrypted:
            raise CVImportError("le PDF est protégé par un mot de passe : enregistre une copie sans protection.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except CVImportError:
        raise
    except (PdfReadError, OSError, ValueError) as error:
        raise CVImportError(f"le fichier « {pdf_path.name} » n'est pas un PDF lisible ({error}).")

    text = _fix_accents(text).strip()
    if len(re.sub(r"\s", "", text)) < MIN_TEXT_CHARACTERS:
        raise CVImportError(
            f"« {pdf_path.name} » ne contient pas de texte exploitable. C'est souvent un CV scanné "
            "ou enregistré en image : la reconnaissance de texte (OCR) n'est pas prise en charge. "
            "Exporte ton CV en PDF depuis Word, Google Docs ou LaTeX."
        )
    return text


# ---------- 2. Import complet ----------

def import_cv(pdf_path, imports_dir: Path | None = None, extracted_dir: Path | None = None) -> Path:
    """
    Importe un CV PDF : copie le PDF dans imports/, extrait son texte, demande à Claude une
    proposition de profil et l'enregistre en JSON dans extracted/. Renvoie le chemin du JSON.
    Ne modifie pas candidate.yaml. Lève CVImportError si le PDF ne peut pas être lu.
    """

    pdf_path = Path(pdf_path).expanduser().resolve()
    imports_dir = Path(imports_dir) if imports_dir else IMPORTS_DIR
    extracted_dir = Path(extracted_dir) if extracted_dir else EXTRACTED_DIR

    cv_text = extract_pdf_text(pdf_path)          # erreur claire avant tout appel à Claude
    proposal = extract_profile(cv_text)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", pdf_path.stem).strip("-") or "cv"

    imports_dir.mkdir(parents=True, exist_ok=True)
    imported = pdf_path if pdf_path.parent == imports_dir.resolve() else imports_dir / f"{name}-{stamp}.pdf"
    if imported != pdf_path:
        shutil.copy2(pdf_path, imported)

    extracted_dir.mkdir(parents=True, exist_ok=True)
    output = extracted_dir / f"{name}-{stamp}.json"
    output.write_text(json.dumps({
        "status": "proposal",   # à valider : pas encore dans le profil
        "source_pdf": pdf_path.name,
        "imported_pdf": str(imported),
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
        "text_characters": len(cv_text),
        "profile": {key: value for key, value in proposal.items() if key != "warnings"},
        "warnings": proposal["warnings"],
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return output


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print('Usage: python -m candidate.import_cv "<chemin du CV.pdf>"')
        sys.exit(1)

    try:
        path = import_cv(sys.argv[1])
    except CVImportError as error:
        print(f"Import impossible : {error}")
        sys.exit(1)

    print(f"Proposition de profil enregistrée : {path}")
    print("Elle n'est pas encore dans ton profil : relis-la avant de l'utiliser.")

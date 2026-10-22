"""
Génération complète d'un CV à partir de l'URL d'une offre : lecture, analyse, rédaction,
vérification (avec corrections), écriture du dossier, compilation du PDF, puis analyse de
correspondance entre l'offre et le profil (analysis.json). Un échec de cette dernière analyse
n'annule jamais le CV : il est enregistré comme une analyse en échec.

Une seule implémentation, utilisée par la ligne de commande (cv/cli.py) et par l'API
(api/cvs.py). Chaque étape est signalée par on_step(étape, **détails) : la CLI l'affiche,
l'API l'enregistre dans le statut de la tâche.
"""

from dataclasses import dataclass
from pathlib import Path

from candidate.profile import CandidateProfile
from cv.analysis import analyze_folder, error_analysis, save_analysis
from cv.build_cv import compile_cv, write_cv
from cv.generate import generate_cv
from cv.verify import verify_cv
from jobs.analyze_job import analyze_job
from jobs.read_job import normalize_job_url, read_job


# Nombre de fois où Claude peut réécrire le CV si la vérification trouve des choses inventées
MAX_CORRECTIONS = 2

# Étapes signalées à on_step, dans l'ordre, avec leur libellé pour l'interface
STEPS = {
    "read_offer": "Lecture de l'offre",
    "analyze_offer": "Analyse de l'offre",
    "offer_analyzed": "Analyse de l'offre",
    "write_cv": "Rédaction du CV",
    "verify_cv": "Vérification du CV",
    "correct_cv": "Correction du CV",
    "verified": "Vérification du CV",
    "compile": "Compilation du PDF",
    "analyze_fit": "Analyse de correspondance",
}


@dataclass
class GenerationResult:
    folder: Path          # cv/applications/<entreprise>-<poste>/
    main_tex: Path
    pdf: Path
    pages: int
    document: dict        # contenu de cv.json
    issues: list          # affirmations encore absentes du profil après les corrections
    offer: dict
    analysis: dict | None = None   # contenu d'analysis.json (status completed ou failed)


def _ignore(step: str, **details) -> None:
    pass


def generate_from_url(
    url: str,
    profile: CandidateProfile,
    on_step=None,
    applications_dir: Path | None = None,
) -> GenerationResult:
    """
    Génère, vérifie, enregistre et compile un CV pour l'offre à cette URL, avec le profil
    déjà chargé (le même pour la rédaction et la vérification). Lève les erreurs des étapes
    (RuntimeError de Claude ou de LaTeX, erreurs du navigateur...).
    """

    notify = on_step or _ignore
    url = normalize_job_url(url)

    notify("read_offer")
    job = read_job(url)

    notify("analyze_offer")
    offer = analyze_job(job)
    notify("offer_analyzed", offer=offer)

    notify("write_cv")
    cv = generate_cv(offer, profile)

    notify("verify_cv")
    issues = verify_cv(cv, profile)

    for attempt in range(1, MAX_CORRECTIONS + 1):
        if not issues:
            break

        notify("correct_cv", attempt=attempt, issues=issues)
        cv = generate_cv(offer, profile, previous_cv=cv, issues=issues)
        issues = verify_cv(cv, profile)

    notify("verified", issues=issues)

    # L'URL est gardée avec l'offre (offer.json) pour retrouver l'origine du CV ; Claude ne la reçoit pas
    main_tex = write_cv(cv, {**offer, "source_url": url}, verification_issues=issues,
                        applications_dir=applications_dir)

    notify("compile", folder=main_tex.parent)
    pdf, pages = compile_cv(main_tex)

    # Le CV et son PDF sont enregistrés : une erreur d'analyse ne doit pas les faire perdre
    notify("analyze_fit", folder=main_tex.parent)
    try:
        analysis = analyze_folder(main_tex.parent, profile)
    except Exception as error:
        analysis = error_analysis(error)
        try:
            save_analysis(main_tex.parent, analysis)
        except OSError:
            pass

    return GenerationResult(folder=main_tex.parent, main_tex=main_tex, pdf=pdf, pages=pages,
                            document=cv, issues=issues, offer=offer, analysis=analysis)

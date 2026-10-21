import sys

from candidate.profile import ProfileError, load_profile
from cv.document import selected_ids
from cv.pipeline import MAX_CORRECTIONS, generate_from_url


def _print_issues(issues: list[dict]) -> None:
    for issue in issues:
        print(f"  - [{issue['section']}] « {issue['cv_text']} » : {issue['problem']}")


def _print_step(step: str, **details) -> None:
    """Affichage de chaque étape du pipeline (cv/pipeline.py), comme avant."""

    if step == "read_offer":
        print("1/5 Lecture de l'offre...")
    elif step == "analyze_offer":
        print("2/5 Analyse de l'offre par Claude...")
    elif step == "offer_analyzed":
        print(f"    {details['offer']['job_title']} — {details['offer']['company']}")
    elif step == "write_cv":
        print("3/5 Rédaction du CV par Claude...")
    elif step == "verify_cv":
        print("4/5 Vérification du CV contre candidate.yaml...")
    elif step == "correct_cv":
        issues = details["issues"]
        print(f"    {len(issues)} affirmation(s) absente(s) de ton profil, correction {details['attempt']}/{MAX_CORRECTIONS} :")
        _print_issues(issues)
    elif step == "verified" and not details["issues"]:
        print("    OK : tout ce qui est dans le CV vient de ton profil.")
    elif step == "compile":
        print("5/5 Compilation LaTeX...")


def main(url: str) -> None:

    # Charger et vérifier le profil une seule fois, avant le navigateur et Claude :
    # le même profil sert ensuite à rédiger et à vérifier le CV
    try:
        profile = load_profile()
    except ProfileError as error:
        print(error)
        sys.exit(1)

    result = generate_from_url(url, profile, on_step=_print_step)
    cv, issues, pages = result.document, result.issues, result.pages

    print()
    experience_ids, project_ids = selected_ids(cv)
    print(f"Expériences choisies : {', '.join(experience_ids)}")
    print(f"Projets choisis      : {', '.join(project_ids)}")

    if cv["gaps"]:
        print("Points de l'offre non couverts par ton profil :")
        for gap in cv["gaps"]:
            print(f"  - {gap}")

    if issues:
        print()
        print("!" * 70)
        print("ATTENTION : le CV contient encore des choses qui ne sont PAS dans ton profil.")
        print("Corrige-les à la main avant d'envoyer le CV :")
        _print_issues(issues)
        print("!" * 70)

    if pages > 1:
        print(f"\nAttention : le CV fait {pages} pages au lieu d'une.")

    print(f"\nCV généré : {result.pdf}")


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print('Usage: python -m cv.cli "<URL>"')
        sys.exit(1)

    main(sys.argv[1])

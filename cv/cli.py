import sys

from candidate.profile import ProfileError, load_profile
from cv.build_cv import compile_cv, write_cv
from cv.generate import generate_cv
from cv.verify import verify_cv
from jobs.analyze_job import analyze_job
from jobs.read_job import normalize_job_url, read_job


# Nombre de fois où Claude peut réécrire le CV si la vérification trouve des choses inventées
MAX_CORRECTIONS = 2


def _print_issues(issues: list[dict]) -> None:
    for issue in issues:
        print(f"  - [{issue['section']}] « {issue['cv_text']} » : {issue['problem']}")


def main(url: str) -> None:

    # Charger et vérifier le profil une seule fois, avant le navigateur et Claude :
    # le même profil sert ensuite à rédiger et à vérifier le CV
    try:
        profile = load_profile()
    except ProfileError as error:
        print(error)
        sys.exit(1)

    url = normalize_job_url(url)

    print("1/5 Lecture de l'offre...")
    job = read_job(url)

    print("2/5 Analyse de l'offre par Claude...")
    offer = analyze_job(job)
    print(f"    {offer['job_title']} — {offer['company']}")

    print("3/5 Rédaction du CV par Claude...")
    cv = generate_cv(offer, profile)

    print("4/5 Vérification du CV contre candidate.yaml...")
    issues = verify_cv(cv, profile)

    for attempt in range(1, MAX_CORRECTIONS + 1):
        if not issues:
            break

        print(f"    {len(issues)} affirmation(s) absente(s) de ton profil, correction {attempt}/{MAX_CORRECTIONS} :")
        _print_issues(issues)

        cv = generate_cv(offer, profile, previous_cv=cv, issues=issues)
        issues = verify_cv(cv, profile)

    cv["verification_issues"] = issues

    if not issues:
        print("    OK : tout ce qui est dans le CV vient de ton profil.")

    main_tex = write_cv(cv, offer)

    print("5/5 Compilation LaTeX...")
    pdf, pages = compile_cv(main_tex)

    print()
    print(f"Expériences choisies : {', '.join(cv['selected_experience_ids'])}")
    print(f"Projets choisis      : {', '.join(cv['selected_project_ids'])}")

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

    print(f"\nCV généré : {pdf}")


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print('Usage: python -m cv.cli "<URL>"')
        sys.exit(1)

    main(sys.argv[1])

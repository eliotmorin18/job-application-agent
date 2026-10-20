import sys

from browser.apply_agent import apply_in_terminal
from browser.read_job import normalize_job_url, read_job
from cv.build_cv import compile_cv, write_cv
from llm.analyze_job import analyze_job
from llm.generate_cv import generate_cv
from llm.verify_cv import verify_cv


# Nombre de fois où Claude peut réécrire le CV si la vérification trouve des choses inventées
MAX_CORRECTIONS = 2


def _print_issues(issues: list[dict]) -> None:
    for issue in issues:
        print(f"  - [{issue['section']}] « {issue['cv_text']} » : {issue['problem']}")


def main(url: str) -> None:

    url = normalize_job_url(url)

    print("1/6 Lecture de l'offre...")
    job = read_job(url)

    print("2/6 Analyse de l'offre par Claude...")
    offer = analyze_job(job)
    print(f"    {offer['job_title']} — {offer['company']}")

    print("3/6 Rédaction du CV par Claude...")
    cv = generate_cv(offer)

    print("4/6 Vérification du CV contre candidate.yaml...")
    issues = verify_cv(cv)

    for attempt in range(1, MAX_CORRECTIONS + 1):
        if not issues:
            break

        print(f"    {len(issues)} affirmation(s) absente(s) de ton profil, correction {attempt}/{MAX_CORRECTIONS} :")
        _print_issues(issues)

        cv = generate_cv(offer, previous_cv=cv, issues=issues)
        issues = verify_cv(cv)

    cv["verification_issues"] = issues

    if not issues:
        print("    OK : tout ce qui est dans le CV vient de ton profil.")

    main_tex = write_cv(cv, offer)

    print("5/6 Compilation LaTeX...")
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

    print(f"\nCV : {pdf.relative_to(main_tex.parents[3])}")

    print("\n6/6 Candidature dans Chrome...")
    apply_in_terminal(url, pdf, offer, report_path=main_tex.parent / "a_faire.txt")


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print('Usage: python main.py "<URL>"')
        sys.exit(1)

    main(sys.argv[1])

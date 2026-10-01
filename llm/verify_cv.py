from typing import Any

from llm.claude_cli import run_claude
from llm.generate_cv import CANDIDATE_PATH


VERIFY_PROMPT = """
You are a strict fact-checker for a CV. Provided on stdin:
- CANDIDATE PROFILE: candidate.yaml, the ONLY source of truth about the candidate
- CV: the LaTeX source of each section of a CV written for this candidate

Check EVERY statement of the CV (each bullet, the profile summary, titles, dates, places,
degrees, skills, languages, interests, links) against CANDIDATE PROFILE.

A statement is SUPPORTED if the profile says the same thing, even translated
(e.g. French CV, English profile), shortened, merged or reworded.

A statement is UNSUPPORTED if it adds anything the profile does not say, for example:
- a task, tool, library, method, metric, number, result or domain not in the profile
- a qualifier that strengthens a fact ("object-oriented", "in production", "led", "expert"...)
- a soft skill or personality trait ("rigorous", "autonomous"...) not in the profile
- a date, place, title, degree detail or award that differs from the profile
- a purpose or outcome not in the profile ("to meet a business need", "improving efficiency"...)

Ignore LaTeX commands, formatting and section titles. Do not report style problems.
Be strict: when in doubt, report it.

For each unsupported statement return:
- section: the section file name (heading, experience, education, projects, technical-skills, interests)
- cv_text: the exact unsupported words in the CV
- problem: in French, a short explanation of what is not in the profile
Return an empty list if everything is supported.
""".strip()


VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "cv_text": {"type": "string"},
                    "problem": {"type": "string"},
                },
                "required": ["section", "cv_text", "problem"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["issues"],
    "additionalProperties": False,
}


def verify_cv(cv: dict, timeout: int = 300) -> list[dict[str, Any]]:
    """
    Fait relire le CV par Claude, sans l'offre, uniquement contre candidate.yaml.
    Renvoie la liste des affirmations du CV qui ne sont pas dans le profil.
    """

    candidate_text = CANDIDATE_PATH.read_text(encoding="utf-8")

    sections = "\n\n".join(
        f"--- SECTION: {name} ---\n{content}" for name, content in cv["sections"].items()
    )

    stdin_text = "=== CANDIDATE PROFILE ===\n" + candidate_text + "\n\n=== CV ===\n" + sections

    return run_claude(VERIFY_PROMPT, stdin_text, VERIFY_SCHEMA, timeout)["issues"]

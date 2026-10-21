import json
from pathlib import Path
from typing import Any

from candidate.profile import CandidateProfile
from cv.document import CLAUDE_SCHEMA, build_document, education_keys
from llm.claude_cli import run_claude


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = ROOT / "cv" / "reference"


CV_PROMPT = """
You are a CV-writing system. Everything you need is provided on stdin:
- JOB OFFER: the structured job offer (JSON)
- CANDIDATE PROFILE: candidate.yaml, the ONLY source of truth about the candidate
- EDUCATION KEYS: the identifier to use for each education entry of the profile
- STYLE REFERENCES: previous CVs of the candidate, to copy their style, tone and layout

Your task: write the content of a one-page CV tailored to this job offer, as structured data.
The CV layout (LaTeX) is produced from your answer by the application.

Facts — THE MOST IMPORTANT RULE. This CV is sent in the candidate's name to a real employer:
any claim that is not in the profile is a lie the candidate will have to defend in an interview.
- Every statement in the CV must be traceable to CANDIDATE PROFILE. If you cannot point to
  where the profile says it, do not write it.
- Never add a VERIFIABLE fact that is not in the profile: a task, tool, library, method,
  metric, number, result, date, title, degree detail, award or domain experience.
- Never add a COMMITMENT that is not in the profile (availability, mobility, working hours,
  travel, start date, salary...).
- Exception — motivation and personality: in the "Profile" summary only, you may add a few
  (up to 3) short statements of interest, motivation or general quality that fit the offer
  (e.g. "intéressé par la planification de production", "curieux et rigoureux").
  Each must be plausible given the profile, unverifiable, easy to defend in an interview,
  and must not imply a skill or experience the profile does not have
  ("passionné de MILP" or "expert en planification" are NOT allowed).
- Never add a qualifier that strengthens a fact (e.g. "object-oriented Python", "in production",
  "at scale", "led", "expert") unless the profile says so.
- STYLE REFERENCES may contain facts that are not in the profile: never copy facts from them,
  only their style and layout.
- You may translate, shorten, merge and reorder the profile's content, and use the offer's
  vocabulary for something the profile really says (e.g. "constrained optimization" ->
  "optimisation sous contraintes"). You may not change what was actually done.
- If the offer asks for something the profile does not have, it goes in gaps, never in the CV.
- When in doubt, leave it out.

Using the offer:
- key_points and must_have are what the recruiter cares about most: select and order the
  content so that what the profile really has for them comes first. nice_to_have comes next.
- keywords: when the profile really supports a keyword, use the offer's exact word for it
  (it helps ATS screening). Never use a keyword the profile does not support.
- Required items of must_have that the profile does not cover go in gaps.

Selection:
- Select at most application_rules.max_cv_experiences experiences and
  application_rules.max_cv_projects projects, the most relevant to the offer.
- Prefer priority: high, recent items, and items whose tags/skills match the offer.
- Return the ids of the selected items exactly as written in the profile (source_id).
- For education, use as source_id the key given in EDUCATION KEYS.

Writing:
- Write the CV in the language of the job offer (French offer -> French CV, otherwise English),
  and set language accordingly. Section titles are added by the application.
- The "Profile" summary must be written specifically for this offer (2-3 sentences).
- Technical skills: put first what matches the offer; the spoken languages go in languages.
- Interests: 3 to 5 items from the profile, taken in the order of the profile list
  (the first ones are the candidate's priority).
- The whole CV must fit on ONE page: keep bullets short (1-2 lines), 1 to 3 bullets per item.

Format:
- Plain text only: no LaTeX, no HTML, no Markdown, except **bold** around a few words.
- Do not write the name, contact details, dates, locations or links: the application adds them
  from the profile for the selected items.
- Each bullet is one item of its list; the order of the lists is the order in the CV.

Also return:
- company and role: short names for the file name (e.g. "Airbus", "Stage IA Optimisation").
- gaps: in French, the important requirements of the offer that the profile does NOT cover
  (so the candidate knows what is missing). Empty list if none.
""".strip()


CORRECTION_PROMPT = """

=== CORRECTION ===
A previous version of this CV was checked against the profile and contained statements
that are NOT supported by CANDIDATE PROFILE. They are listed on stdin under PREVIOUS ATTEMPT.
Rewrite the CV: remove or correct each of these statements so that everything is supported
by the profile. Do not introduce any new unsupported statement.
"""


def _read_tex_files(folder: Path) -> str:
    """Concatène tous les .tex d'un dossier, chacun précédé de son chemin."""

    parts = []

    for path in sorted(folder.rglob("*.tex")):
        relative = path.relative_to(ROOT)
        parts.append(f"--- FILE: {relative} ---\n{path.read_text(encoding='utf-8')}")

    return "\n\n".join(parts)


def _education_keys_text(candidate: dict) -> str:
    """« key: école — diplôme », une formation par ligne, dans l'ordre du profil."""

    lines = [
        f"{key}: {item.get('school') or ''}" + (f" — {item['degree']}" if item.get("degree") else "")
        for key, item in education_keys(candidate)
    ]
    return "\n".join(lines) or "(no education in the profile)"


def generate_cv(
    offer: dict,
    profile: CandidateProfile,
    previous_cv: dict | None = None,
    issues: list[dict] | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """
    Envoie l'offre structurée + le profil candidat (déjà chargé et validé par
    candidate.profile.load_profile) + références à Claude Code et renvoie le CV
    structuré (voir cv/document.py), complété avec les dates, lieux, contacts et
    liens du profil. Le LaTeX est produit ensuite par cv/render.py.

    Si previous_cv et issues sont donnés (sortie de verify_cv), Claude réécrit
    le CV en corrigeant les affirmations non justifiées par le profil.
    """

    candidate_text = profile.text
    candidate = profile.data

    parts = [
        "=== JOB OFFER ===\n" + json.dumps(
            {key: value for key, value in offer.items() if key != "removed_by_check"},
            indent=2,
            ensure_ascii=False,
        ),
        "=== CANDIDATE PROFILE ===\n" + candidate_text,
        "=== EDUCATION KEYS ===\n" + _education_keys_text(candidate),
        "=== STYLE REFERENCES ===\n" + _read_tex_files(REFERENCE_DIR),
    ]
    prompt = CV_PROMPT

    if previous_cv and issues:
        previous = {"cv": previous_cv, "unsupported_statements": issues}
        parts.append("=== PREVIOUS ATTEMPT ===\n" + json.dumps(previous, indent=2, ensure_ascii=False))
        prompt += CORRECTION_PROMPT

    draft = run_claude(prompt, "\n\n".join(parts), CLAUDE_SCHEMA, timeout)

    return build_document(draft, profile)

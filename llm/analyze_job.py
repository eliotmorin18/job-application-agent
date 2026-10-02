import json
import re
import sys
import unicodedata
from typing import Any

from llm.claude_cli import run_claude


EXTRACTION_PROMPT = """
You extract a job offer from a web page, to prepare a CV tailored to it.
Your output is the ONLY thing the CV writer will see of the offer: it must contain
everything that matters for the CV, nothing that does not, and nothing that is not in the offer.

The page text is provided on stdin. Besides the job offer, it usually contains noise:
cookie banners, navigation menus, footers, sharing buttons, "similar jobs" / recommended
offers, company marketing, legal notices, login prompts. A search page may list several
offers: extract only the one that is displayed in detail (the selected one).
Ignore all the noise.

FAITHFULNESS — the most important rule:
- Every value must come from the offer itself. Never add a skill, tool, requirement,
  mission, location or condition that the offer does not state, even if it is "usual"
  for this kind of job.
- Do not upgrade or downgrade a requirement: "a plus" stays nice_to_have, "required" stays must_have.
- You may shorten and merge sentences, but keep the offer's own words for technical terms.
- Write values in the language of the offer.
- If something is not stated, use null or an empty list. When in doubt, leave it out.
- If the page contains no job offer (error page, expired offer, login wall), return null
  for job_title and empty lists everywhere.

What to extract:
- company, job_title, location, contract_type: as stated (null if absent).
- job_level: the level the offer targets, as stated or obvious from the title
  (e.g. "Stage", "Internship", "Alternance", "Junior", "Senior", "8+ years"). null if unclear.
- offer_language: the language the offer is written in ("fr", "en", ...).
- summary: 1-2 sentences describing the role and the team/context, from the offer.
- missions: the main tasks of the job, at most 8, most important first. One task per item.
  Do not include section headings ("Activités", "Your missions") as tasks.
- must_have: the requirements the offer presents as required (skills, tools, experience,
  education, languages, certifications). A requirement not explicitly marked as optional
  is a must_have. One requirement per item.
- nice_to_have: what the offer explicitly presents as a plus / preferred / appreciated /
  "idéalement" / "serait un plus". One per item.
- education: the required degree / field, as one short text (null if absent).
- experience: the required experience (years, domain), as one short text (null if absent).
- languages: the spoken languages required, with level if stated.
- soft_skills: the personal qualities the offer explicitly asks for.
- keywords: technical terms, tools, methods and domain words that appear LITERALLY in the
  offer and that a recruiter or an ATS would look for in the CV (e.g. "Python", "MLOps",
  "computer vision", "optimisation combinatoire"). Copy them exactly as written. At most 20.
- key_points: the 3 to 5 things that matter most to the recruiter for this job, each with
  "point" (short, in your words) and "quote" (an exact excerpt of the offer, copied
  character for character, that supports it).
- practical_info: practical conditions stated in the offer (duration, start date, remote /
  on-site days, salary, travel, required availability...). One per item.
""".strip()


def _text_or_null() -> dict:
    return {"type": ["string", "null"]}


def _list_of_text() -> dict:
    return {"type": "array", "items": {"type": "string"}}


# Format imposé à Claude via --json-schema : il ne peut pas renvoyer autre chose.
JOB_SCHEMA = {
    "type": "object",
    "properties": {
        "company": _text_or_null(),
        "job_title": _text_or_null(),
        "location": _text_or_null(),
        "contract_type": _text_or_null(),
        "job_level": _text_or_null(),
        "offer_language": _text_or_null(),
        "summary": _text_or_null(),
        "missions": _list_of_text(),
        "must_have": _list_of_text(),
        "nice_to_have": _list_of_text(),
        "education": _text_or_null(),
        "experience": _text_or_null(),
        "languages": _list_of_text(),
        "soft_skills": _list_of_text(),
        "keywords": _list_of_text(),
        "key_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["point", "quote"],
                "additionalProperties": False,
            },
        },
        "practical_info": _list_of_text(),
    },
    "required": [
        "company",
        "job_title",
        "location",
        "contract_type",
        "job_level",
        "offer_language",
        "summary",
        "missions",
        "must_have",
        "nice_to_have",
        "education",
        "experience",
        "languages",
        "soft_skills",
        "keywords",
        "key_points",
        "practical_info",
    ],
    "additionalProperties": False,
}


def _normalize(text: str) -> str:
    """Minuscules, sans accents ni apostrophes typographiques, espaces simplifiés."""

    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def _keep_only_what_is_in_page(offer: dict, page_text: str) -> dict:
    """
    Garde-fou contre les inventions : les mots-clés et les citations des points clés
    doivent figurer réellement dans la page. Ce qui n'y est pas est retiré.
    """

    page = _normalize(page_text)

    removed_keywords = [k for k in offer["keywords"] if _normalize(k) not in page]
    offer["keywords"] = [k for k in offer["keywords"] if _normalize(k) in page]

    removed_points = [p for p in offer["key_points"] if _normalize(p["quote"]) not in page]
    offer["key_points"] = [p for p in offer["key_points"] if _normalize(p["quote"]) in page]

    offer["removed_by_check"] = {
        "keywords": removed_keywords,
        "key_points": removed_points,
    }

    return offer


def analyze_job(job: dict, timeout: int = 180) -> dict[str, Any]:
    """
    Envoie le texte d'une offre (sortie de read_job) à Claude Code
    et renvoie l'offre structurée, vérifiée contre le texte de la page.
    """

    page_content = f"URL: {job.get('url', '')}\nTITLE: {job.get('title', '')}\n\n{job['text']}"

    offer = run_claude(EXTRACTION_PROMPT, page_content, JOB_SCHEMA, timeout)

    # Page vide, offre retirée, erreur du site... : inutile de faire un CV pour rien
    if not offer["job_title"] or not (offer["missions"] or offer["must_have"]):
        start = job["text"][:200].replace("\n", " ")
        raise RuntimeError(f"Aucune offre d'emploi trouvée sur la page {job.get('url', '')}\nDébut de la page : {start!r}")

    return _keep_only_what_is_in_page(offer, page_content)


if __name__ == "__main__":

    # Test rapide : le texte de l'offre est lu sur l'entrée standard.
    # Exemple : python -m llm.analyze_job < offre.txt
    text = sys.stdin.read()

    if not text.strip():
        print("Usage: python -m llm.analyze_job < offre.txt")
        sys.exit(1)

    offer = analyze_job({"url": "", "title": "", "text": text})

    print(json.dumps(offer, indent=2, ensure_ascii=False))

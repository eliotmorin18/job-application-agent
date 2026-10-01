import json
import sys
from typing import Any

from llm.claude_cli import run_claude


EXTRACTION_PROMPT = """
You are a job-offer extraction system.

The job page content is provided on stdin. It may contain irrelevant content such as:
- cookie banners
- navigation menus
- footers
- sharing buttons
- recommended jobs
- unrelated website content

Ignore irrelevant content and extract only information that belongs to the target job offer.

Rules:
- Do not invent information.
- If a value is missing, use null or an empty list.
- Keep the wording faithful to the offer.
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
        "job_description": _text_or_null(),
        "missions": _list_of_text(),
        "requirements": _list_of_text(),
        "preferred_qualifications": _list_of_text(),
        "skills": _list_of_text(),
        "education_requirements": _list_of_text(),
        "experience_requirements": _list_of_text(),
        "languages": _list_of_text(),
    },
    "required": [
        "company",
        "job_title",
        "location",
        "contract_type",
        "job_description",
        "missions",
        "requirements",
        "preferred_qualifications",
        "skills",
        "education_requirements",
        "experience_requirements",
        "languages",
    ],
    "additionalProperties": False,
}


def analyze_job(job: dict, timeout: int = 180) -> dict[str, Any]:
    """
    Envoie le texte d'une offre (sortie de read_job) à Claude Code
    et renvoie l'offre structurée.
    """

    page_content = f"URL: {job.get('url', '')}\nTITLE: {job.get('title', '')}\n\n{job['text']}"

    return run_claude(EXTRACTION_PROMPT, page_content, JOB_SCHEMA, timeout)


if __name__ == "__main__":

    # Test rapide : le texte de l'offre est lu sur l'entrée standard.
    # Exemple : python -m llm.analyze_job < offre.txt
    text = sys.stdin.read()

    if not text.strip():
        print("Usage: python -m llm.analyze_job < offre.txt")
        sys.exit(1)

    offer = analyze_job({"url": "", "title": "", "text": text})

    print(json.dumps(offer, indent=2, ensure_ascii=False))

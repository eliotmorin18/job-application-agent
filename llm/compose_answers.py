import json
from typing import Any

from llm.claude_cli import run_claude


COMPOSE_PROMPT = """
You turn a candidate's rough notes into the final answers of a job application form.
Provided on stdin:
- CANDIDATE PROFILE: candidate.yaml (the candidate's real background)
- JOB: the structured job offer
- QUESTIONS: the form questions the candidate had to answer. Each has a number, the field
  label, a kind (text, choice, checkbox, other) and, for choice, the exact list of options.
- NOTES: what the candidate wrote, by question number (rough, in any language). Key "0" is a
  free text where the candidate answered several questions at once: find in it the answer
  to each question (if a question is not addressed in it, treat it as empty notes).

For each question, return one answer with its number and a status:
- "ready": you can produce the final value.
  - choice: value must be EXACTLY one of the options, character for character: the option
    that matches what the candidate meant (e.g. notes "un ami m'en a parlé" -> option
    "Referral / Connaissance"). For a multi-select question, separate several options with " | ".
  - checkbox: if the question has options (a group of boxes), same as choice (exact label(s)
    of the box(es) to check, separated by " | "); otherwise value "check" or "uncheck".
  - text: write the final text from the notes, in the language of the question, with the
    length the question calls for (a few sentences for a motivation question). Keep the
    candidate's ideas; do not add ideas he did not give.
- "follow_up": the notes are ambiguous (several options could match), contradictory, or miss
  an information you need. Put ONE precise question in French in follow_up, mentioning the
  possible options if it is a choice. value "".
- "manual": the notes are empty or say the candidate will do it himself ("moi", "je le fais").
  value "".

Honesty rules for text answers (the text is sent in the candidate's name):
- Facts (skills, tools, experiences, results, numbers, dates, degrees) must come from the
  notes or the CANDIDATE PROFILE. Never invent one.
- Motivation, interest and general qualities are allowed if they follow the notes and are
  plausible given the profile.
- Never add a commitment (availability, salary, mobility...) the notes or profile do not state.
""".strip()


COMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "status": {"type": "string", "enum": ["ready", "follow_up", "manual"]},
                    "value": {"type": "string"},
                    "follow_up": {"type": "string"},
                },
                "required": ["number", "status", "value", "follow_up"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answers"],
    "additionalProperties": False,
}


def compose_answers(
    questions: list[dict],
    notes: dict[int, str],
    candidate_text: str,
    offer: dict | None,
    timeout: int = 300,
) -> list[dict[str, Any]]:
    """Transforme les notes du candidat en réponses finales (ou questions complémentaires)."""

    stdin_text = "\n\n".join([
        "=== CANDIDATE PROFILE ===\n" + candidate_text,
        "=== JOB ===\n" + json.dumps(offer or {}, indent=2, ensure_ascii=False),
        "=== QUESTIONS ===\n" + json.dumps(questions, indent=2, ensure_ascii=False),
        "=== NOTES ===\n" + json.dumps({str(k): v for k, v in notes.items()}, indent=2, ensure_ascii=False),
    ])

    answers = run_claude(COMPOSE_PROMPT, stdin_text, COMPOSE_SCHEMA, timeout)["answers"]

    # Garde-fou : une option de liste doit exister telle quelle, sinon on redemande
    options_by_number = {q["number"]: q.get("options") or [] for q in questions}

    for answer in answers:
        options = options_by_number.get(answer["number"])
        if answer["status"] == "ready" and options:
            chosen = [part.strip() for part in answer["value"].split("|")]
            unknown = [part for part in chosen if part not in options]
            if unknown:
                answer["status"] = "follow_up"
                answer["follow_up"] = (
                    f"Je n'ai pas trouvé d'option correspondant à « {answer['value']} ». "
                    f"Laquelle choisir : {' · '.join(options)} ?"
                )
                answer["value"] = ""

    return answers

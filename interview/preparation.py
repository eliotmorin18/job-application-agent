"""
Préparation approfondie à l'entretien d'une candidature, enregistrée dans
cv/applications/<cv_id>/preparation.json. Facultative : générée uniquement à la demande, jamais
pendant la création d'une candidature, et jamais régénérée automatiquement.

Deux appels au modèle au plus (via llm/structured.py) :
1. recherche sur l'entreprise (interview/research.py), sautée si company_research.json existe ;
2. rédaction de la préparation, sans outil, à partir d'une entrée compacte : offre, exigences et
   statuts de analysis.json, points forts, recommandations et questions des anciennes analyses
   (réutilisées telles quelles ; les nouvelles analyses n'en ont plus : ces blocs ne sont pas
   envoyés et le modèle écrit toutes les questions), faits sur l'entreprise, profil filtré
   (sans coordonnées) et résumé du CV.

Python vérifie tout ce qui peut l'être : identifiants d'exigences, de faits et de questions,
preuves présentes dans le profil, type des points de vigilance calculé à partir des statuts de
l'analyse (« non remplie » et « non documentée » restent distincts), plafonds et longueurs.

    {"schema_version": 1, "status": "completed", "generated_at", "profile_fingerprint", "analysis_generated_at",
     "company": {"name", "research_status", "official_website", "note",
                 "facts": [{"id", "topic", "origin": "offer" | "web", "text", "interview_use", "source_ids"}],
                 "sources": [{"id", "url", "title", "official", "published_at", "accessed_at", "access"}],
                 "warnings"},
     "priorities": [{"title", "why", "actions", "requirement_ids", "fact_ids"}],
     "questions": [{"id", "origin": "analysis" | "preparation", "kind", "question", "purpose", "answer_guidance",
                    "evidence", "topics_to_review", "requirement_ids", "fact_ids"}],
     "knowledge": [{"topic", "why", "explanation", "check_points", "requirement_ids"}],
     "experiences": [{"evidence": {"type", "id", "label"}, "angle", "key_points", "question_ids", "requirement_ids"}],
     "vigilance": [{"kind": "missing" | "not_documented" | "partial" | "other", "requirement_ids", "concern",
                    "how_to_address"}],
     "warnings": ["..."]}

En cas d'échec, rien n'est écrit (aucun fichier « failed ») : l'état précédent reste en place.
"""

import json
from datetime import date, datetime
from pathlib import Path

from candidate.profile import CandidateProfile
from candidate.review_import import _norm
from cv.analysis import (EVIDENCE_TYPES, STATUSES, _valid_evidence, load_analysis, profile_fingerprint,
                         profile_references)
from cv.document import DOCUMENT_FILE, CVDocumentError, education_keys, load_document
from interview.files import read_json, write_json
from interview.research import _clip, load_research, research_company, save_research
from llm.structured import StructuredRequest, generate_structured


SCHEMA_VERSION = 1
PREPARATION_FILE = "preparation.json"
PREPARATION_TIMEOUT = 300
PREPARATION_BUDGET_USD = 1.50
MIN_QUESTIONS, MAX_QUESTIONS, MAX_NEW_WHEN_ENOUGH = 5, 8, 3
QUESTION_KINDS = ["technical", "experience", "gap", "motivation"]
MAX_TOPICS = 6
MAX_PRIORITIES, MAX_KNOWLEDGE, MAX_EXPERIENCES, MAX_VIGILANCE = 5, 6, 5, 5
STORY_TYPES = ["experience", "project", "education"]
VIGILANCE_ORDER = {"missing": 0, "not_documented": 1, "partial": 2, "other": 3}
# Disponibilités utiles aux points de vigilance (jamais salaire, santé, date de naissance...)
AVAILABILITY_KEYS = ("available_start_date", "internship_duration", "notice_period", "willing_to_relocate",
                     "willing_to_work_on_site", "work_authorization_france", "studies_completed", "graduation_date")
# Champs du profil inutiles au modèle (gain de place), jamais les faits eux-mêmes
DROPPED_KEYS = {"priority", "tags", "github_url", "url", "link", "links"}


class PreparationError(RuntimeError):
    """La préparation ne peut pas être faite (offre ou analyse absente...)."""


# ---------- Ce que le modèle renvoie ----------

def _object(**properties) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _text(max_length: int) -> dict:
    return {"type": "string", "maxLength": max_length}


def _texts(max_length: int, max_items: int | None = None) -> dict:
    schema = {"type": "array", "items": _text(max_length)}
    return {**schema, "maxItems": max_items} if max_items else schema


_IDS = {"type": "array", "items": {"type": "string"}}

PREPARATION_SCHEMA = _object(
    priorities={"type": "array", "maxItems": MAX_PRIORITIES, "items": _object(
        title=_text(80), why=_text(300), actions=_texts(200, 3), requirement_ids=_IDS, fact_ids=_IDS)},
    questions=_object(
        keep=_IDS,
        new={"type": "array", "maxItems": MAX_QUESTIONS, "items": _object(
            kind={"type": "string", "enum": QUESTION_KINDS}, question=_text(250), purpose=_text(250),
            answer_guidance=_texts(250, 4),
            evidence={"type": "array", "items": _object(type={"type": "string", "enum": EVIDENCE_TYPES}, id=_text(120),
                                                        justification=_text(200))},
            topics_to_review=_texts(60, 6), requirement_ids=_IDS, fact_ids=_IDS)}),
    knowledge={"type": "array", "maxItems": MAX_KNOWLEDGE, "items": _object(
        topic=_text(80), why=_text(250), explanation=_text(700), check_points=_texts(160, 3), requirement_ids=_IDS)},
    experiences={"type": "array", "maxItems": MAX_EXPERIENCES, "items": _object(
        evidence=_object(type={"type": "string", "enum": STORY_TYPES}, id=_text(120)), angle=_text(250),
        key_points=_texts(250, 4), question_refs=_IDS, requirement_ids=_IDS)},
    vigilance={"type": "array", "maxItems": MAX_VIGILANCE, "items": _object(
        requirement_ids=_IDS, concern=_text(250), how_to_address=_texts(300, 3))},
)

PREPARATION_PROMPT = """
You prepare a candidate for a job interview for ONE specific offer. The fit analysis is already
done: build on it, do not redo it. Write in French, for the candidate ("tu"), concretely and
precisely. Every item must be specific to THIS offer, THIS company and THIS candidate: if an item
would be equally true for any job or any candidate, remove it. Fewer, better items are preferred
to filled sections; an empty list is acceptable. The numbers of items below are maximums, never
targets.

Provided on stdin:
- TODAY
- OFFER: the structured offer (missions, key points with exact quotes, keywords...)
- REQUIREMENTS: each requirement with its id, category, importance and status from the analysis
  (met, partial, not_documented, missing), its explanation and its evidence ids
- STRENGTHS: from the analysis
- RECOMMENDATIONS (ids r1...): from the analysis, only for some applications (often absent)
- EXISTING QUESTIONS (ids q1...): interview questions already prepared, with their purpose (often
  absent: then write all the questions yourself, within QUESTION TARGET)
- COMPANY FACTS (ids o1... from the offer, w1... from sourced research): facts about the company
- CANDIDATE: the candidate's profile, the ONLY source of truth about the candidate, with the ids
  to cite; elements listed on one line are known by their id and title only
- CV: what the recruiter will have in hand (summary and included elements)
- QUESTION TARGET: how many new questions to write (min, max)

Absolute rules:
- Never invent or embellish an experience, a skill, a result, a figure, a tool or a
  responsibility. Use only what CANDIDATE states; cite elements by their ids exactly as given.
- Keep the distinction: not_documented = the profile is silent (the candidate may have it: advise
  mentioning it only if they really have it); missing = the profile shows the requirement is not
  met (acknowledge it honestly and show how to address it).
- Knowledge about the company comes ONLY from COMPANY FACTS (cite their ids). Never add facts
  about the company from your own knowledge.
- Each piece of advice appears once, in the section where it is most useful; other items refer to
  it by id instead of repeating it.
- Do not paraphrase RECOMMENDATIONS or EXISTING QUESTIONS: go further (more precise, more
  actionable) or leave them out.

priorities (3 to 5): the topics that will weigh most in THIS interview, most important first,
derived from high-importance requirements, the offer's key points, the main strengths to show and
the most delicate gaps. Each: title (short); why (one or two sentences grounded in the offer or the
analysis); actions (1 to 3 concrete things to do before the interview, e.g. "Prépare un récit de
2 minutes sur … en insistant sur …"); requirement_ids; fact_ids.

questions:
- keep: the ids of the EXISTING QUESTIONS to keep (normally all of them; drop one only if it is
  redundant with another or not anchored in the offer); empty if EXISTING QUESTIONS is absent.
- new: new questions within QUESTION TARGET, covering what the kept questions do not cover yet:
  priorities without a question, the company and the motivation (using COMPANY FACTS), important
  requirements or gaps not yet addressed. Never a reworded existing question. Fields: kind
  (technical, experience, gap, motivation); question (as a recruiter would say it); purpose (what
  the recruiter wants to assess, one sentence); answer_guidance (2 to 4 tips grounded in the
  profile, with its ids, or on how to structure the answer); evidence (profile ids, REQUIRED for
  kind experience); topics_to_review (short items, possibly empty); requirement_ids; fact_ids.

knowledge (0 to 6): notions, technologies or methods to revise because the offer names them AND
the interview is likely to test them, prioritising partial, not_documented or missing
requirements and the technologies of the missions. Skip a notion the profile shows the candidate
already masters, unless the offer requires a deeper level. Each: topic; why (the link with the
offer, quoting its words); explanation (2 to 4 sentences on what the candidate must concretely
know: key concepts, typical use in this job, classic pitfalls; correct and specific, not a
textbook definition); check_points (1 to 3 items phrased "Savoir expliquer…", "Savoir
comparer…"); requirement_ids.

experiences (2 to 5): real elements of the profile (experience, project or education) the
candidate should be ready to tell, most useful first. Each: evidence (type and id from CANDIDATE);
angle (why this element matters for this job, one sentence); key_points (2 to 4 precise points
from the profile to put forward: context, what the candidate did, tools, outcome AS STATED in the
profile, nothing added); question_refs (ids of the questions it helps answer: q... for kept
questions, n1, n2... for the new ones in order); requirement_ids.

vigilance (0 to 5): what a recruiter could raise against the application: partial,
not_documented or missing requirements (high importance first) and other concrete objections
visible in the offer and the profile (availability, location, level, duration), never
speculative. Each: requirement_ids (empty only for an objection not tied to a requirement);
concern (the objection as a recruiter could see it, one sentence); how_to_address (1 to 3 honest,
constructive lines: real transferable experience with its ids, learning already started only if
the profile says so, or how to acknowledge the gap). Never advise hiding or minimising a gap.
""".strip()


# ---------- Entrée compacte ----------

def question_target(existing: int) -> dict:
    """Nombre de nouvelles questions : compléter jusqu'à 5 à 8 au total, au plus 3 si 5 existent déjà."""
    if existing >= MIN_QUESTIONS:
        return {"min": 0, "max": max(0, min(MAX_NEW_WHEN_ENOUGH, MAX_QUESTIONS - existing))}
    return {"min": MIN_QUESTIONS - existing, "max": MAX_QUESTIONS - existing}


def _ids(evidence) -> list[str]:
    return [f"{e['type']}:{e['id']}" for e in evidence or [] if isinstance(e, dict) and e.get("type") and e.get("id")]


def _cited(analysis: dict, document: dict | None) -> set[tuple[str, str]]:
    """Éléments du profil cités par l'analyse ou présents dans le CV : transmis en détail."""
    cited = set()
    for group in (analysis.get("requirements") or [], analysis.get("strengths") or [],
                  analysis.get("interview_questions") or []):
        for item in group:
            cited |= {(e["type"], e["id"]) for e in item.get("evidence") or [] if e.get("type") in STORY_TYPES}
    if document:
        for section, kind in (("experiences", "experience"), ("projects", "project"), ("education", "education")):
            cited |= {(kind, entry.get("source_id")) for entry in document.get(section) or []}
    return cited


def _compact(item: dict) -> dict:
    return {key: value for key, value in item.items() if key not in DROPPED_KEYS and value not in (None, "", [], {})}


def compact_profile(profile_data: dict, detailed: set[tuple[str, str]]) -> dict:
    """
    Le profil utile à la préparation : en détail les éléments cités, sur une ligne les autres,
    compétences, langues, situation et disponibilités. Jamais les coordonnées ni les données personnelles.
    """
    def entries(section: str, kind: str, short_keys: tuple) -> list[dict]:
        result = []
        for item in profile_data.get(section) or []:
            if isinstance(item, dict) and item.get("id"):
                if (kind, item["id"]) in detailed:
                    result.append(_compact(item))
                else:
                    result.append({key: item[key] for key in ("id", *short_keys) if item.get(key)})
        return result

    education = []
    for key, item in education_keys(profile_data):
        if ("education", key) in detailed:
            education.append({**_compact(item), "id": key})
        else:
            education.append({"id": key, **{k: item[k] for k in ("school", "degree", "end_date") if item.get(k)}})
    form_answers = profile_data.get("form_answers") or {}
    return {
        "career": profile_data.get("career") or {},
        "availability": {key: form_answers[key] for key in AVAILABILITY_KEYS if form_answers.get(key) not in (None, "")},
        "experiences": entries("experiences", "experience", ("title", "company", "start_date", "end_date")),
        "projects": entries("projects", "project", ("name", "start_date", "end_date")),
        "education": education,
        "skills": profile_data.get("skills") or {},
        "languages": profile_data.get("languages") or [],
    }


def company_section(offer: dict, research: dict) -> dict:
    """Section « Comprendre l'entreprise » : faits de l'offre puis faits sourcés de la recherche (sans IA)."""
    facts = []
    if str(offer.get("summary") or "").strip():
        facts.append({"id": "o1", "topic": "activity", "origin": "offer", "text": _clip(offer["summary"], 600),
                      "interview_use": "", "source_ids": []})
    facts += [{**fact, "origin": "web"} for fact in research.get("facts") or []]
    return {"name": offer.get("company"), "research_status": research.get("status"),
            "official_website": research.get("official_website"), "note": research.get("note") or "",
            "facts": facts, "sources": research.get("sources") or [], "warnings": research.get("warnings") or []}


def preparation_input(offer: dict, analysis: dict, profile_data: dict, document: dict | None, company: dict,
                      today: date) -> str:
    questions = analysis.get("interview_questions") or []
    recommendations = [r for r in analysis.get("recommendations") or [] if r.get("category") != "cv"]
    blocks = {
        "TODAY": today.isoformat(),
        "OFFER": {key: offer.get(key) for key in ("job_title", "company", "job_level", "contract_type", "summary",
                                                  "missions", "key_points", "keywords", "soft_skills", "practical_info")
                  if offer.get(key)},
        "REQUIREMENTS": [{"id": r["id"], "text": r["text"], "category": r["category"], "importance": r["importance"],
                          "status": r["status"], "explanation": r.get("explanation") or "", "evidence": _ids(r.get("evidence"))}
                         for r in analysis.get("requirements") or [] if not r.get("duplicate_of")],
        "STRENGTHS": [{"title": s["title"], "evidence": _ids(s.get("evidence"))} for s in analysis.get("strengths") or []],
        # Anciennes analyses seulement : blocs omis quand ils sont vides (cas des nouvelles analyses)
        "RECOMMENDATIONS": [{"id": f"r{n}", "category": r["category"], "text": r["text"]}
                            for n, r in enumerate(recommendations, start=1)] or None,
        "EXISTING QUESTIONS": [{"id": f"q{n}", "kind": q.get("kind"), "question": q.get("question"),
                                "purpose": q.get("purpose"), "evidence": _ids(q.get("evidence")),
                                "requirement_ids": q.get("requirement_ids") or []}
                               for n, q in enumerate(questions, start=1)] or None,
        "COMPANY FACTS": [{"id": f["id"], "topic": f["topic"], "origin": f["origin"], "text": f["text"]}
                          for f in company["facts"]],
        "CANDIDATE": compact_profile(profile_data, _cited(analysis, document)),
        "CV": ({"summary": (document.get("header") or {}).get("summary") or "",
                "included": [f"{kind}:{entry.get('source_id')}"
                             for section, kind in (("experiences", "experience"), ("projects", "project"),
                                                   ("education", "education"))
                             for entry in document.get(section) or []]} if document else "(absent)"),
        "QUESTION TARGET": question_target(len(questions)),
    }
    return "\n\n".join(f"=== {name} ===\n" + (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
                       for name, value in blocks.items() if value is not None)


# ---------- Vérification ----------

def _list(values, limit: int, max_items: int) -> list[str]:
    result = []
    for value in values or []:
        text = _clip(value, limit)
        if text and _norm(text) not in {_norm(r) for r in result}:
            result.append(text)
    return result[:max_items]


class _Context:
    """Ce que les réponses du modèle peuvent citer : exigences (avec statut et importance), faits, profil."""

    def __init__(self, analysis: dict, references: dict, company: dict, warnings: list):
        self.items = analysis.get("requirements") or []
        self.statuses = {item["id"]: item["status"] for item in self.items}
        self.high = {item["id"] for item in self.items if item.get("importance") == "high"}
        for item in self.items:                     # exigence séparée : statut le moins favorable de ses parties
            if item.get("parent_id"):
                parent = item["parent_id"]
                self.statuses[parent] = max(self.statuses.get(parent, "met"), item["status"], key=STATUSES.index)
                if item.get("importance") == "high":
                    self.high.add(parent)
        self.facts = {fact["id"] for fact in company["facts"]}
        self.references = references
        self.warnings = warnings

    def requirement_ids(self, ids) -> list[str]:
        return list(dict.fromkeys(i for i in ids or [] if i in self.statuses))

    def fact_ids(self, ids) -> list[str]:
        return list(dict.fromkeys(i for i in ids or [] if i in self.facts))


def _interview_questions(answers: list, references: dict, items: list[dict], warnings: list) -> list[dict]:
    """
    Questions d'entretien vérifiées : preuves limitées aux éléments du profil, exigences connues,
    doublons et questions vides retirés, au plus MAX_QUESTIONS. Une question sur une expérience sans
    preuve valide est retirée (elle porterait sur une expérience inexistante).
    """
    statuses = {item["id"]: item["status"] for item in items}
    for item in items:                              # exigence séparée : le statut le moins favorable de ses parties
        if item["parent_id"]:
            current = statuses.get(item["parent_id"], "met")
            statuses[item["parent_id"]] = max(current, item["status"], key=STATUSES.index)
    questions, seen = [], set()
    for answer in answers or []:
        text = str(answer.get("question") or "").strip()
        if not text or _norm(text) in seen:
            continue
        guidance = [str(tip).strip() for tip in answer.get("answer_guidance") or [] if str(tip).strip()]
        if not guidance:
            warnings.append(f"Question d'entretien ignorée (sans piste de réponse) : « {text} ».")
            continue
        evidence = _valid_evidence(answer.get("evidence"), references, warnings)
        if answer.get("kind") == "experience" and not evidence:
            warnings.append(f"Question d'entretien ignorée (expérience absente du profil) : « {text} ».")
            continue
        requirement_ids = [i for i in answer.get("requirement_ids") or [] if i in statuses]
        if answer.get("kind") == "gap" and requirement_ids and all(statuses[i] == "met" for i in requirement_ids):
            warnings.append(f"Question « {text} » : l'exigence liée est remplie, ce n'est pas une lacune.")
        topics = []
        for topic in answer.get("topics_to_review") or []:
            topic = str(topic).strip()
            if topic and _norm(topic) not in {_norm(t) for t in topics}:
                topics.append(topic)
        seen.add(_norm(text))
        questions.append({
            "kind": answer.get("kind") if answer.get("kind") in QUESTION_KINDS else "technical",
            "question": text,
            "purpose": str(answer.get("purpose") or "").strip(),
            "answer_guidance": guidance,
            "evidence": evidence,
            "topics_to_review": topics[:MAX_TOPICS],
            "requirement_ids": requirement_ids,
        })
    if len(questions) > MAX_QUESTIONS:
        warnings.append(f"{len(questions) - MAX_QUESTIONS} question(s) d'entretien en trop ignorée(s).")
    return questions[:MAX_QUESTIONS]


def _questions(answer: dict, analysis: dict, context: _Context) -> tuple[list[dict], dict]:
    """Questions gardées (recopiées de l'analyse) puis nouvelles (vérifiées), renumérotées q1… ; table des renvois."""
    existing = analysis.get("interview_questions") or []
    questions, refs, seen = [], {}, set()

    def add(question: dict, ref: str) -> None:
        if len(questions) >= MAX_QUESTIONS or _norm(question["question"]) in seen:
            return
        seen.add(_norm(question["question"]))
        refs[ref] = f"q{len(questions) + 1}"
        questions.append({"id": refs[ref], **question})

    for ref in dict.fromkeys(answer.get("keep") or []):
        index = int(ref[1:]) - 1 if isinstance(ref, str) and ref[:1] == "q" and ref[1:].isdigit() else -1
        if 0 <= index < len(existing):
            add({**existing[index], "origin": "analysis", "fact_ids": []}, ref)
    for n, new in enumerate(answer.get("new") or [], start=1):
        checked = _interview_questions([new], context.references, context.items, context.warnings)
        if checked:
            add({**checked[0], "origin": "preparation", "fact_ids": context.fact_ids(new.get("fact_ids"))}, f"n{n}")
    if len(questions) < MIN_QUESTIONS:
        context.warnings.append(f"Seulement {len(questions)} question(s) d'entretien retenue(s).")
    return questions, refs


def _priorities(answer: dict, context: _Context) -> list[dict]:
    priorities = []
    for item in answer.get("priorities") or []:
        title, why = _clip(item.get("title"), 80), _clip(item.get("why"), 300)
        if title and why and _norm(title) not in {_norm(p["title"]) for p in priorities}:
            priorities.append({"title": title, "why": why, "actions": _list(item.get("actions"), 200, 3),
                               "requirement_ids": context.requirement_ids(item.get("requirement_ids")),
                               "fact_ids": context.fact_ids(item.get("fact_ids"))})
    return priorities[:MAX_PRIORITIES]


def _knowledge(answer: dict, context: _Context) -> list[dict]:
    knowledge = []
    for item in answer.get("knowledge") or []:
        topic, explanation = _clip(item.get("topic"), 80), _clip(item.get("explanation"), 700)
        if topic and explanation and _norm(topic) not in {_norm(k["topic"]) for k in knowledge}:
            knowledge.append({"topic": topic, "why": _clip(item.get("why"), 250), "explanation": explanation,
                              "check_points": _list(item.get("check_points"), 160, 3),
                              "requirement_ids": context.requirement_ids(item.get("requirement_ids"))})
    return knowledge[:MAX_KNOWLEDGE]


def _experiences(answer: dict, refs: dict, context: _Context) -> list[dict]:
    experiences = []
    for item in answer.get("experiences") or []:
        evidence = item.get("evidence") or {}
        if evidence.get("type") not in STORY_TYPES:
            continue
        found = _valid_evidence([{**evidence, "justification": ""}], context.references, context.warnings)
        key_points = _list(item.get("key_points"), 250, 4)
        if not found or not key_points:
            if found:
                context.warnings.append(f"Expérience ignorée (sans point à souligner) : « {found[0]['label']} ».")
            continue
        found = {k: found[0][k] for k in ("type", "id", "label")}
        if any(e["evidence"]["type"] == found["type"] and e["evidence"]["id"] == found["id"] for e in experiences):
            continue
        experiences.append({"evidence": found, "angle": _clip(item.get("angle"), 250), "key_points": key_points,
                            "question_ids": list(dict.fromkeys(refs[r] for r in item.get("question_refs") or [] if r in refs)),
                            "requirement_ids": context.requirement_ids(item.get("requirement_ids"))})
    return experiences[:MAX_EXPERIENCES]


def _vigilance(answer: dict, context: _Context) -> list[dict]:
    """Le type vient des statuts de l'analyse (jamais du modèle) ; une exigence remplie n'est pas un point de vigilance."""
    vigilance = []
    for item in answer.get("vigilance") or []:
        concern = _clip(item.get("concern"), 250)
        asked = context.requirement_ids(item.get("requirement_ids"))
        ids = [i for i in asked if context.statuses[i] != "met"]
        if len(ids) < len(asked):
            context.warnings.append(f"Point de vigilance : exigence remplie retirée (« {_clip(concern, 60)} »).")
        if not concern or (item.get("requirement_ids") and not ids):
            continue
        kind = max((context.statuses[i] for i in ids), key=STATUSES.index) if ids else "other"
        vigilance.append({"kind": kind, "requirement_ids": ids, "concern": concern,
                          "how_to_address": _list(item.get("how_to_address"), 300, 3)})
    vigilance.sort(key=lambda v: (not any(i in context.high for i in v["requirement_ids"]), VIGILANCE_ORDER[v["kind"]]))
    return vigilance[:MAX_VIGILANCE]


def assemble_preparation(answer: dict, analysis: dict, profile: CandidateProfile, company: dict) -> dict:
    warnings = []
    context = _Context(analysis, profile_references(profile.data), company, warnings)
    questions, refs = _questions(answer.get("questions") or {}, analysis, context)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile_fingerprint": profile_fingerprint(profile),
        "analysis_generated_at": analysis.get("generated_at"),
        "company": company,
        "priorities": _priorities(answer, context),
        "questions": questions,
        "knowledge": _knowledge(answer, context),
        "experiences": _experiences(answer, refs, context),
        "vigilance": _vigilance(answer, context),
        "warnings": warnings,
    }


# ---------- Dossier d'une candidature ----------

def load_preparation(folder: Path) -> dict | None:
    """La préparation enregistrée, None si elle n'existe pas (ou est illisible : elle peut alors être refaite)."""
    preparation = read_json(Path(folder) / PREPARATION_FILE)
    return preparation if preparation and preparation.get("status") == "completed" else None


def check_preparable(folder: Path) -> tuple[dict, dict]:
    """(offre, analyse) d'une candidature prête à être préparée ; sinon PreparationError (rien n'est lancé)."""
    offer = read_json(Path(folder) / "offer.json")
    if offer is None:
        raise PreparationError("l'offre de cette candidature (offer.json) n'est pas connue.")
    analysis = load_analysis(folder)
    if not analysis or analysis.get("status") != "completed":
        raise PreparationError("l'analyse d'adéquation de cette candidature n'est pas disponible : lance-la d'abord.")
    return offer, analysis


def prepare_folder(folder: Path, profile: CandidateProfile, on_step=None, generate=generate_structured,
                   today: date | None = None) -> dict:
    """
    Prépare l'entretien d'une candidature et enregistre preparation.json (deux appels au plus,
    un seul si la recherche est déjà enregistrée). Ne modifie ni le CV, ni l'analyse, ni le profil.
    Lève PreparationError ou l'erreur du modèle ; dans ce cas rien n'est écrit, sauf la recherche réussie.
    """
    folder = Path(folder)
    today = today or date.today()
    step = on_step or (lambda name: None)
    offer, analysis = check_preparable(folder)
    document = None
    if (folder / DOCUMENT_FILE).is_file():
        try:
            document = load_document(folder)
        except CVDocumentError:
            document = None

    research = load_research(folder)
    if research is None:
        step("research_company")
        research = research_company(offer, today, generate)
        save_research(folder, research)
    company = company_section(offer, research)

    step("write_preparation")
    result = generate(StructuredRequest(PREPARATION_PROMPT,
                                        preparation_input(offer, analysis, profile.data, document, company, today),
                                        PREPARATION_SCHEMA, PREPARATION_TIMEOUT, max_budget_usd=PREPARATION_BUDGET_USD))
    preparation = assemble_preparation(result.data, analysis, profile, company)
    write_json(folder / PREPARATION_FILE, preparation)
    return preparation

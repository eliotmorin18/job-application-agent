"""
Analyse de correspondance entre une offre et le profil candidat, enregistrée dans
cv/applications/<cv_id>/analysis.json à côté du CV.

Un appel à Claude (séparé de la génération du CV) explique l'offre et évalue chaque exigence ;
Python fixe la liste des exigences (offer.json), vérifie chaque preuve contre le profil,
calcule le score (cv/fit_score.py) et assemble le résultat. Rédigé en français.

    {
      "schema_version": 1, "status": "completed", "generated_at": "...", "profile_fingerprint": "...",
      "offer": {"company", "job_title", "location", "contract_type", "source_url", "company_activity"},
      "overview": {"summary", "missions", "technologies", "skills_sought", "plain_explanation",
                   "possible_tasks", "glossary": [{"term", "explanation"}]},
      "requirements": [{"id", "text", "category", "source", "parent_id", "parent_text", "duplicate_of",
                        "importance", "weight", "status", "explanation", "evidence": [...]}],
      "strengths": [{"title", "explanation", "evidence", "requirement_ids"}],
      "weaknesses": [{"requirement_id", "text", "category", "kind", "explanation"}],
      "score": {"value", "level", "breakdown", "status_counts", "warnings", "explanation"},
      "recommendations": [],
      "warnings": ["..."]
    }

L'analyse ne prépare pas l'entretien : questions, conseils et recherche sur l'entreprise viennent
de la préparation approfondie, à la demande (interview/preparation.py). Les analyses enregistrées
avant cette séparation peuvent contenir "recommendations" (catégories cv, interview, learning,
obstacle) et "interview_questions" : elles sont lues telles quelles (avec .get()), jamais réécrites,
et la préparation réutilise leurs questions. Les nouvelles analyses gardent "recommendations": []
pour que le format reste le même.

En cas d'échec : {"schema_version": 1, "status": "failed", "generated_at", "error": {"message", "problems"}}.
Une preuve est {"type": experience|project|education|skill|language|interest, "id", "label", "justification"} :
son identifiant doit exister dans le profil (la correspondance peut être sémantique, justifiée
par Claude), mais une preuve valide ne suffit pas à rendre une exigence « couverte ».
"offer.company_activity" (activité de l'entreprise d'après l'offre) et le type de preuve "interest" sont
absents des analyses plus anciennes ; une exigence (ou partie) dont les mots sont ceux d'une exigence
précédente y est marquée comme doublon ("duplicate_of", poids 0).
"""

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from candidate.profile import CandidateProfile
from candidate.review_import import STOPWORDS, _norm, _skill_norm
from cv.document import DOCUMENT_FILE, document_text, education_keys, load_document, CVDocumentError
from cv.fit_score import IMPORTANCE_WEIGHTS, compute_score
from llm.claude_cli import run_claude


SCHEMA_VERSION = 1
ANALYSIS_FILE = "analysis.json"
STATUSES = ["met", "partial", "not_documented", "missing"]
EVIDENCE_TYPES = ["experience", "project", "education", "skill", "language", "interest"]
MAX_PARTS = 6


class AnalysisError(RuntimeError):
    """L'analyse ne peut pas être faite (offre absente, réponse inutilisable...)."""


# ---------- Exigences de l'offre (fixées par Python, jamais par Claude) ----------

def requirements_from_offer(offer: dict) -> list[dict]:
    """
    Exigences à évaluer, dans l'ordre : indispensables (must_have, formation, expérience, langues),
    puis appréciées (nice_to_have). Doublons exacts retirés. Les qualités personnelles (soft_skills)
    ne sont pas évaluées : le profil ne peut pas les prouver.
    """
    requirements = []

    def add(text, category: str, source: str) -> None:
        text = str(text or "").strip()
        if text and not any(_norm(r["text"]) == _norm(text) for r in requirements):
            requirements.append({"id": f"req-{len(requirements) + 1}", "text": text, "category": category, "source": source})

    for text in offer.get("must_have") or []:
        add(text, "required", "must_have")
    add(offer.get("education"), "required", "education")
    add(offer.get("experience"), "required", "experience")
    for text in offer.get("languages") or []:
        add(text, "required", "languages")
    for text in offer.get("nice_to_have") or []:
        add(text, "preferred", "nice_to_have")
    return requirements


# ---------- Ce que Claude renvoie ----------

def _object(**properties) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


_TEXT = {"type": "string"}
_TEXTS = {"type": "array", "items": _TEXT}
_EVIDENCE = {"type": "array", "items": _object(type={"type": "string", "enum": EVIDENCE_TYPES}, id=_TEXT, justification=_TEXT)}

ANALYSIS_SCHEMA = _object(
    overview=_object(summary=_TEXT, plain_explanation=_TEXT, technologies=_TEXTS, skills_sought=_TEXTS,
                     possible_tasks=_TEXTS, glossary={"type": "array", "items": _object(term=_TEXT, explanation=_TEXT)}),
    requirements={"type": "array", "items": _object(
        id=_TEXT, duplicate_of={"type": ["string", "null"]},
        parts={"type": "array", "items": _object(
            text=_TEXT, status={"type": "string", "enum": STATUSES},
            importance={"type": "string", "enum": list(IMPORTANCE_WEIGHTS)}, explanation=_TEXT, evidence=_EVIDENCE)})},
    strengths={"type": "array", "items": _object(title=_TEXT, explanation=_TEXT, evidence=_EVIDENCE, requirement_ids=_TEXTS)},
)

ANALYSIS_PROMPT = """
You analyse how well a candidate's profile matches a job offer, for the candidate.
Provided on stdin:
- JOB OFFER: the structured job offer (JSON)
- REQUIREMENTS: the requirements of the offer to assess, each with an id (fixed list)
- CANDIDATE PROFILE: candidate.yaml, the ONLY source of truth about the candidate
- PROFILE REFERENCES: the ids to cite as evidence (experiences, projects, education, skills, languages,
  interests)
- CV: the content of the CV generated for this offer (may be absent)
- KNOWN GAPS: requirements already identified as not covered when the CV was written (may be empty)

Write everything in French, clearly and concisely, for the candidate ("tu").

Overview (the candidate must understand the job in 30 seconds):
- summary: 1-2 sentences on the role and its goal, faithful to the offer. Do not describe what the
  company does (the offer's company_activity is shown separately).
- plain_explanation: in plain language, what the candidate would concretely do, what it is for,
  and the kind of daily tasks. Only what the offer says.
- possible_tasks: 2-4 illustrative daily tasks, each clearly worded as a possibility
  ("par exemple, tu pourrais…"), consistent with the missions. Never present them as certain.
- technologies and skills_sought: copied from the offer (its own words), no addition.
- glossary: technical terms or jargon THAT APPEAR IN THE OFFER and that help understanding, each
  explained in one short sentence. Empty list if none is useful.
- Never invent missions, responsibilities, projects, teams or tools.

Requirements: assess EVERY requirement of REQUIREMENTS, by its id. Do not add or remove any.
- parts: one part with the same text, unless the requirement clearly lists several distinct
  criteria ("Python et SQL" -> "Python", "SQL"); split only when unambiguous, using the offer's
  own words for each part. Never invent a criterion.
- duplicate_of: the id of another requirement that says exactly the same thing (e.g. the education
  field repeating a must-have), otherwise null.
- status of each part:
  - met: the profile clearly shows it, at the required level.
  - partial: the profile shows something related but weaker, narrower or at a lower level.
  - not_documented: the profile says nothing about it. This does NOT mean the candidate lacks it.
  - missing: the profile shows the requirement is NOT fulfilled (lower degree or level, fewer years
    of experience, a required language level below the requirement...). Explain the contradiction.
  A close or similar skill is NOT the required skill: never assume mastery from proximity.
  When a requirement lists several criteria and the profile shows some of them but says nothing about
  the others, split it into parts so that each keeps its own status (e.g. met + not_documented)
  instead of marking the whole requirement partial. In explanations, say that something "n'est pas
  mentionné dans ton profil", never that the candidate lacks it, unless the profile contradicts it.
  A valid piece of evidence does not make a requirement "met" by itself: judge the level and scope.
- importance: high if the requirement corresponds to one of the offer's key_points or is explicitly
  stressed by the offer, otherwise normal.
- explanation: one or two sentences explaining the status, citing the profile.
- evidence: the elements of the profile supporting the assessment, using ONLY the ids listed in
  PROFILE REFERENCES (type + id exactly as listed). A semantic match is allowed (e.g. the offer says
  "Computer Vision", the profile says "Vision par ordinateur"), explained in justification.
  No evidence for not_documented.

Strengths: 3 to 5 strengths of the profile for this offer, each explaining why it matters for the
job, with its evidence (ids from PROFILE REFERENCES) and the related requirement ids.

Never invent or exaggerate the candidate's skills.
""".strip()


# ---------- Références du profil (les seules preuves acceptées) ----------

def profile_references(profile_data: dict) -> dict[str, dict[str, str]]:
    """{type: {clé normalisée: (id, libellé)}} — ce qui peut être cité comme preuve."""
    def items(section: str, label) -> dict:
        return {item["id"]: (item["id"], label(item)) for item in profile_data[section]
                if isinstance(item, dict) and item.get("id")}

    skills = {}
    for values in list((profile_data.get("skills") or {}).values()) + [
            item.get("skills") or [] for section in ("experiences", "projects") for item in profile_data[section]
            if isinstance(item, dict)]:
        for value in values or []:
            skills.setdefault(_skill_norm(value), (str(value), str(value)))
    languages = {_norm(entry.get("language")): (str(entry.get("language")), str(entry.get("language")))
                 for entry in profile_data.get("languages") or [] if isinstance(entry, dict) and entry.get("language")}
    interests = {_norm(value): (str(value).strip(), str(value).strip())
                 for value in profile_data.get("interests") or [] if isinstance(value, str) and value.strip()}
    return {
        "experience": items("experiences", lambda i: " — ".join(p for p in (i.get("title"), i.get("company")) if p)),
        "project": items("projects", lambda i: str(i.get("name") or i["id"])),
        "education": {key: (key, " — ".join(p for p in (item.get("school"), item.get("degree")) if p))
                      for key, item in education_keys(profile_data)},
        "skill": skills,
        "language": languages,
        "interest": interests,
    }


def _references_text(references: dict) -> str:
    lines = []
    for kind, entries in references.items():
        lines.append(f"{kind}:")
        lines += [f"  - {ref_id}" + (f" ({label})" if label != ref_id else "") for ref_id, label in entries.values()]
    return "\n".join(lines)


def _lookup(references: dict, kind: str, ref_id: str):
    entries = references.get(kind, {})
    key = _skill_norm(ref_id) if kind == "skill" else _norm(ref_id) if kind in ("language", "interest") \
        else str(ref_id).strip()
    return entries.get(key)


def _valid_evidence(evidence: list, references: dict, warnings: list) -> list[dict]:
    valid = []
    for item in evidence or []:
        found = _lookup(references, item.get("type"), item.get("id"))
        if found is None:
            warnings.append(f"Preuve ignorée : {item.get('type')} « {item.get('id')} » n'existe pas dans le profil.")
            continue
        ref_id, label = found
        if not any(v["type"] == item["type"] and v["id"] == ref_id for v in valid):
            valid.append({"type": item["type"], "id": ref_id, "label": label,
                          "justification": str(item.get("justification") or "").strip()})
    return valid


# ---------- Assemblage ----------

def _words(text: str) -> set:
    return {word for word in _norm(text).split() if word not in STOPWORDS}


def _in_offer(text: str, offer_text: str) -> bool:
    return bool(_norm(text)) and _norm(text) in offer_text


def _assess(requirements: list[dict], answers: list, references: dict, warnings: list) -> list[dict]:
    """Une ligne par exigence (ou par partie d'une exigence séparée), avec son poids et ses preuves vérifiées."""
    by_id = {}
    for answer in answers:
        if answer.get("id") in {r["id"] for r in requirements} and answer["id"] not in by_id:
            by_id[answer["id"]] = answer
        elif answer.get("id") not in {r["id"] for r in requirements}:
            warnings.append(f"Évaluation ignorée : exigence « {answer.get('id')} » inconnue.")

    items = []
    duplicates = {}
    for requirement in requirements:
        answer = by_id.get(requirement["id"])
        if answer is None:
            warnings.append(f"Exigence « {requirement['text']} » non évaluée : comptée comme non documentée.")
            answer = {"duplicate_of": None, "parts": []}

        target = answer.get("duplicate_of")
        target_requirement = next((r for r in requirements if r["id"] == target), None)
        if target and (target_requirement is None or target == requirement["id"] or target in duplicates
                       or (requirement["category"] == "required" and target_requirement["category"] == "preferred")):
            warnings.append(f"Doublon ignoré pour « {requirement['text']} » ({target}).")
            target = None
        if target:
            duplicates[requirement["id"]] = target

        parts = answer.get("parts") or []
        if len(parts) > 1 and (len(parts) > MAX_PARTS or not all(
                _words(part["text"]) and _words(part["text"]) <= _words(requirement["text"]) for part in parts)):
            warnings.append(f"Découpage ignoré pour « {requirement['text']} » : parties absentes du texte de l'offre.")
            worst = max(parts, key=lambda part: STATUSES.index(part["status"]))      # le statut le moins favorable
            parts = [{**worst, "text": requirement["text"],
                      "importance": "high" if any(p["importance"] == "high" for p in parts) else "normal",
                      "evidence": [e for p in parts for e in p.get("evidence") or []],
                      "explanation": " ".join(p["explanation"] for p in parts)}]
        if not parts:
            parts = [{"text": requirement["text"], "status": "not_documented", "importance": "normal",
                      "explanation": "Exigence non évaluée.", "evidence": []}]

        split = len(parts) > 1
        for n, part in enumerate(parts):
            evidence = _valid_evidence(part.get("evidence"), references, warnings)
            status, explanation = part["status"], str(part.get("explanation") or "").strip()
            if status in ("met", "partial") and not evidence:
                warnings.append(f"« {part['text']} » : aucune preuve valide dans le profil, comptée comme non documentée.")
                status = "not_documented"
                explanation = (explanation + " " if explanation else "") + "(Aucune preuve vérifiable dans le profil.)"
            items.append({
                "id": f"{requirement['id']}{chr(97 + n)}" if split else requirement["id"],
                "text": part["text"].strip() if split else requirement["text"],
                "category": requirement["category"],
                "source": requirement["source"],
                "parent_id": requirement["id"] if split else None,
                "parent_text": requirement["text"] if split else None,
                "duplicate_of": target,
                "importance": part["importance"],
                "weight": 0 if target else round(IMPORTANCE_WEIGHTS[part["importance"]] / len(parts), 3),
                "status": status,
                "explanation": explanation,
                "evidence": evidence,
            })
    _mark_repeated(items)
    return items


LINK_WORDS = {"avec", "with", "un", "une", "aux"}      # « avec PyTorch » = « (PyTorch) »


def _mark_repeated(items: list[dict]) -> None:
    """
    Une exigence ou une partie dont les mots (dans le même ordre) sont exactement ceux d'une exigence précédente (souvent une
    partie de « experience » qui reprend un « must_have ») devient son doublon : affichée une fois, poids 0.
    Comme pour duplicate_of, une exigence indispensable n'est jamais le doublon d'une exigence appréciée.
    """
    def words(text: str) -> list:                     # dans l'ordre : mêmes mots autrement rangés = autre critère
        return [word for word in _norm(text).split() if word not in STOPWORDS and word not in LINK_WORDS]

    for n, item in enumerate(items):
        if item["duplicate_of"] or not words(item["text"]):
            continue
        earlier = next((other for other in items[:n] if not other["duplicate_of"]
                        and words(other["text"]) == words(item["text"])
                        and not (item["category"] == "required" and other["category"] == "preferred")), None)
        if earlier:
            item["duplicate_of"], item["weight"] = earlier["id"], 0


WEAKNESS_ORDER = {"missing": 0, "not_documented": 1, "partial": 2}


def _weaknesses(items: list[dict]) -> list[dict]:
    weak = [item for item in items if item["status"] in WEAKNESS_ORDER and not item["duplicate_of"]]
    weak.sort(key=lambda item: (item["category"] != "required", WEAKNESS_ORDER[item["status"]]))
    return [{"requirement_id": item["id"], "text": item["text"], "category": item["category"],
             "kind": item["status"], "explanation": item["explanation"]} for item in weak]


def profile_fingerprint(profile: CandidateProfile) -> str:
    """Empreinte du profil (sans son contenu) : permet de savoir si le profil a changé depuis l'analyse."""
    return hashlib.sha256(profile.text.encode("utf-8")).hexdigest()[:16]


def analyze_fit(offer: dict, profile: CandidateProfile, document: dict | None = None, gaps: list | None = None,
                timeout: int = 300) -> dict:
    """Analyse complète (un appel à Claude). Lève AnalysisError ou les erreurs de Claude."""

    requirements = requirements_from_offer(offer)
    references = profile_references(profile.data)
    offer_for_claude = {key: value for key, value in offer.items() if key not in ("removed_by_check", "source_url")}

    parts = [
        "=== JOB OFFER ===\n" + json.dumps(offer_for_claude, indent=2, ensure_ascii=False),
        "=== REQUIREMENTS ===\n" + json.dumps(
            [{k: r[k] for k in ("id", "text", "category")} for r in requirements], indent=2, ensure_ascii=False),
        "=== CANDIDATE PROFILE ===\n" + profile.text,
        "=== PROFILE REFERENCES ===\n" + _references_text(references),
        "=== CV ===\n" + ("\n\n".join(f"--- {name} ---\n{text}" for name, text in document_text(document).items())
                          if document else "(absent)"),
        "=== KNOWN GAPS ===\n" + ("\n".join(f"- {gap}" for gap in gaps) if gaps else "(none)"),
    ]
    answer = run_claude(ANALYSIS_PROMPT, "\n\n".join(parts), ANALYSIS_SCHEMA, timeout)

    warnings = []
    items = _assess(requirements, answer["requirements"], references, warnings)
    known_ids = {item["id"] for item in items} | {item["parent_id"] for item in items if item["parent_id"]}
    offer_text = _norm(json.dumps(offer_for_claude, ensure_ascii=False))

    overview = answer["overview"]
    glossary = [{"term": g["term"].strip(), "explanation": g["explanation"].strip()}
                for g in overview["glossary"] if _in_offer(g["term"], offer_text)]
    if len(glossary) < len(overview["glossary"]):
        warnings.append("Termes du glossaire absents de l'offre ignorés.")

    strengths = []
    for strength in answer["strengths"]:
        evidence = _valid_evidence(strength["evidence"], references, warnings)
        if not evidence:
            warnings.append(f"Point fort ignoré (sans preuve dans le profil) : « {strength['title']} ».")
            continue
        strengths.append({"title": strength["title"].strip(), "explanation": strength["explanation"].strip(),
                          "evidence": evidence, "requirement_ids": [i for i in strength["requirement_ids"] if i in known_ids]})

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "completed",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile_fingerprint": profile_fingerprint(profile),
        "offer": {key: offer.get(key) for key in ("company", "job_title", "location", "contract_type", "source_url",
                                                  "company_activity")},
        "overview": {
            "summary": overview["summary"].strip(),
            "missions": [str(m) for m in offer.get("missions") or []],
            "technologies": [t.strip() for t in overview["technologies"] if _in_offer(t, offer_text)],
            "skills_sought": [s.strip() for s in overview["skills_sought"] if _in_offer(s, offer_text)],
            "plain_explanation": overview["plain_explanation"].strip(),
            "possible_tasks": [t.strip() for t in overview["possible_tasks"] if t.strip()],
            "glossary": glossary,
        },
        "requirements": items,
        "strengths": strengths,
        "weaknesses": _weaknesses(items),
        "score": compute_score(items),
        "recommendations": [],                    # format inchangé ; la préparation est faite à part
        "warnings": warnings,
    }


# ---------- Dossier d'une candidature ----------

def failed_analysis(message: str, problems: list[str]) -> dict:
    return {"schema_version": SCHEMA_VERSION, "status": "failed",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "error": {"message": message, "problems": problems}}


def error_analysis(error: Exception) -> dict:
    """Analyse en échec, avec un message lisible (le détail technique n'est gardé que s'il est explicite)."""
    if isinstance(error, (AnalysisError, RuntimeError)):
        return failed_analysis("L'analyse de correspondance a échoué", [str(error)[:1000]])
    return failed_analysis("L'analyse de correspondance a échoué", [type(error).__name__])


def save_analysis(folder: Path, analysis: dict) -> Path:
    """Écrit analysis.json (fichier temporaire puis remplacement : jamais de fichier à moitié écrit)."""
    path = Path(folder) / ANALYSIS_FILE
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as temporary:
        temporary.write(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary.name, path)
    return path


def load_analysis(folder: Path) -> dict | None:
    """L'analyse enregistrée, None si elle n'existe pas. Un fichier illisible est signalé comme un échec."""
    path = Path(folder) / ANALYSIS_FILE
    if not path.is_file():
        return None
    try:
        analysis = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return failed_analysis("Analyse illisible", ["le fichier analysis.json est illisible : relance l'analyse."])
    return analysis if isinstance(analysis, dict) and analysis.get("status") in ("completed", "failed") else \
        failed_analysis("Analyse illisible", ["le fichier analysis.json est invalide : relance l'analyse."])


def analyze_folder(folder: Path, profile: CandidateProfile, timeout: int = 300) -> dict:
    """
    Analyse la candidature d'un dossier (offer.json obligatoire ; cv.json et ses gaps s'ils existent)
    et enregistre analysis.json. Ne modifie ni le CV ni le profil. Lève AnalysisError sans offer.json.
    """
    folder = Path(folder)
    try:
        offer = json.loads((folder / "offer.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise AnalysisError("offer.json est absent ou illisible : l'offre de cette candidature n'est pas connue.")
    if not isinstance(offer, dict):
        raise AnalysisError("offer.json est invalide.")

    document = None
    if (folder / DOCUMENT_FILE).is_file():
        try:
            document = load_document(folder)
        except CVDocumentError:
            document = None
    if document:
        gaps = document["gaps"]
    else:
        try:
            gaps = json.loads((folder / "selection.json").read_text(encoding="utf-8")).get("gaps") or []
        except (OSError, ValueError, AttributeError):
            gaps = []

    analysis = analyze_fit(offer, profile, document, gaps, timeout)
    save_analysis(folder, analysis)
    return analysis

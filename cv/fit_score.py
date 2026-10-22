"""
Score d'adéquation entre une offre et le profil candidat, calculé de façon déterministe.

Claude évalue chaque exigence de l'offre (statut, importance, preuves) ; ce module seul en
déduit le score, avec des règles fixes et lisibles :

- crédit d'une exigence selon son statut : met = 1, partial = 0,5, not_documented = 0, missing = 0
- poids d'une exigence : 2 si importante (liée à un point clé de l'offre), 1 sinon ; une exigence
  séparée en plusieurs parties partage son poids entre elles (la séparer ne change pas son poids) ;
  un doublon d'une autre exigence ne compte pas
- score = 100 × (0,80 × indispensables + 0,20 × appréciées), chaque groupe valant
  Σ(crédit × poids) / Σ(poids) ; 100 × indispensables si l'offre n'a pas d'exigence appréciée
- pas de plafond : une exigence indispensable non remplie (missing) donne un avertissement explicite
- score indisponible (None) si l'offre ne donne pas assez d'exigences exploitables

Le score estime l'adéquation aux critères de l'annonce, pas une probabilité d'être recruté.
"""

CREDITS = {"met": 1.0, "partial": 0.5, "not_documented": 0.0, "missing": 0.0}
IMPORTANCE_WEIGHTS = {"high": 2, "normal": 1}
GROUP_WEIGHTS = {"required": 80, "preferred": 20}
MIN_REQUIREMENTS = 3          # en dessous (ou sans exigence indispensable) : score non calculé

STATUS_LABELS = {
    "met": "couverte",
    "partial": "partiellement couverte",
    "not_documented": "non documentée dans le profil",
    "missing": "non remplie",
}
LEVELS = [(80, "Forte adéquation"), (60, "Bonne adéquation"), (40, "Adéquation partielle"), (0, "Adéquation faible")]
DISCLAIMER = "Estimation de l'adéquation aux critères de l'annonce, pas une probabilité d'être recruté."


def _number(value: float) -> str:
    """1.5 -> « 1,5 », 2.0 -> « 2 » (affichage français)."""
    return f"{value:g}".replace(".", ",")


def _group(items: list[dict]) -> dict:
    earned = sum(CREDITS[item["status"]] * item["weight"] for item in items)
    maximum = sum(item["weight"] for item in items)
    return {"earned": round(earned, 2), "max": round(maximum, 2), "ratio": earned / maximum if maximum else None,
            "count": len(items)}


def level_for(value: int | None) -> str | None:
    if value is None:
        return None
    return next(label for threshold, label in LEVELS if value >= threshold)


def compute_score(items: list[dict]) -> dict:
    """
    items : exigences évaluées, chacune {"text", "category": required|preferred, "status", "weight"}
    (weight déjà calculé ; 0 pour un doublon). Renvoie {"value", "level", "breakdown", "explanation",
    "warnings", "status_counts"} — value et level valent None si le score n'est pas calculable.
    """
    scored = [item for item in items if item["weight"] > 0]
    required = [item for item in scored if item["category"] == "required"]
    preferred = [item for item in scored if item["category"] == "preferred"]

    counts = {status: sum(1 for item in scored if item["status"] == status) for status in CREDITS}
    missing = [item for item in required if item["status"] == "missing"]
    undocumented = [item for item in required if item["status"] == "not_documented"]
    warnings = [f"Exigence indispensable non remplie : « {item['text']} »." for item in missing]
    if undocumented:
        warnings.append(f"{len(undocumented)} exigence(s) indispensable(s) non documentée(s) dans ton profil : "
                        "à vérifier, elles ne sont pas forcément absentes.")

    if not required or len(scored) < MIN_REQUIREMENTS:
        reason = ("l'offre ne liste aucune exigence indispensable exploitable" if not required
                  else f"l'offre ne donne que {len(scored)} exigence(s) exploitable(s) (minimum {MIN_REQUIREMENTS})")
        return {"value": None, "level": None, "breakdown": None, "status_counts": counts, "warnings": warnings,
                "explanation": [f"Score non calculé : {reason}. Un pourcentage serait trompeur ; "
                                "l'évaluation de chaque exigence reste disponible.", DISCLAIMER]}

    groups = {"required": _group(required), "preferred": _group(preferred)}
    weights = dict(GROUP_WEIGHTS) if preferred else {"required": 100, "preferred": 0}
    breakdown = {}
    for name, group in groups.items():
        points = (group["ratio"] or 0) * weights[name]
        breakdown[name] = {"earned": group["earned"], "max": group["max"], "count": group["count"],
                           "weight": weights[name], "points": round(points, 1)}
    value = int(sum(part["points"] for part in breakdown.values()) + 0.5)

    explanation = []
    for name, label in (("required", "Exigences indispensables"), ("preferred", "Exigences appréciées")):
        part = breakdown[name]
        if part["count"]:
            explanation.append(f"{label} : {_number(part['earned'])} / {_number(part['max'])} "
                               f"({int(100 * part['earned'] / part['max'] + 0.5)} %) → {_number(part['points'])} / {part['weight']} points")
    if not preferred:
        explanation.append("Aucune exigence appréciée dans l'offre : le score repose sur les exigences indispensables.")
    explanation.append(
        f"Exigences : {counts['met']} couverte(s), {counts['partial']} partiellement, "
        f"{counts['not_documented']} non documentée(s) dans le profil, {counts['missing']} non remplie(s).")
    explanation.append("Crédits : couverte = 1, partielle = 0,5, non documentée ou non remplie = 0 ; "
                       "exigence importante = poids 2, sinon 1.")
    explanation.append(DISCLAIMER)

    return {"value": value, "level": level_for(value), "breakdown": breakdown, "status_counts": counts,
            "warnings": warnings, "explanation": explanation}

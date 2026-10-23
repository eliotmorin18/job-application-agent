"""
Façade minimale entre les modules métier et l'exécution du modèle : les modules décrivent ce dont
ils ont besoin (instructions, entrée, schéma JSON, recherche web ou non, niveau de modèle) et
reçoivent des données structurées, sans savoir quel fournisseur répond.

Seul fournisseur aujourd'hui : Claude Code CLI avec l'abonnement connecté (llm/claude_cli.py).
Un autre fournisseur (API Anthropic, OpenAI, Gemini, modèle local...) s'ajouterait ici ; s'il ne
sait pas faire de recherche web, il lève CapabilityUnavailable et l'appelant s'en passe.
"""

from dataclasses import dataclass, field

from llm.claude_cli import WEB_TOOLS, WebPage, run_claude_task


# Niveaux de modèle : le métier choisit un niveau, le fournisseur choisit le modèle
TIERS = {"default": None, "light": "sonnet"}


class CapabilityUnavailable(RuntimeError):
    """Le fournisseur ne sait pas faire ce qui est demandé (ex. recherche web)."""


@dataclass
class StructuredRequest:
    instructions: str
    input_text: str
    schema: dict
    timeout: int
    web_research: bool = False
    tier: str = "default"
    max_budget_usd: float | None = None     # plafond de consommation estimée de l'appel


@dataclass
class StructuredResult:
    data: dict
    pages: list[WebPage] = field(default_factory=list)     # pages renvoyées par les outils web


def generate_structured(request: StructuredRequest) -> StructuredResult:
    """Un appel au modèle, une seule tentative. Lève RuntimeError (ou CapabilityUnavailable) en cas d'échec."""
    if request.tier not in TIERS:
        raise ValueError(f"niveau de modèle inconnu : {request.tier}")
    result = run_claude_task(request.instructions, request.input_text, request.schema, request.timeout,
                             model=TIERS[request.tier], tools=WEB_TOOLS if request.web_research else (),
                             max_budget_usd=request.max_budget_usd)
    return StructuredResult(result.output, result.pages)

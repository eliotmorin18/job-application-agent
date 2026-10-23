"""
Seul point d'appel à Claude : la commande `claude -p` de Claude Code, avec l'abonnement claude.ai
connecté. Aucune clé API : les variables qui feraient basculer vers une facturation API sont
retirées de l'environnement, et l'authentification est vérifiée AVANT chaque appel
(`claude auth status`, local, ne consomme rien). Ne jamais utiliser `--bare` : ce mode ne lit pas
le trousseau macOS (donc pas la connexion claude.ai) et exige une clé API.

- run_claude : appels existants (CV, analyse, import...), comportement inchangé.
- run_claude_task : appels « légers » (préparation à l'entretien) : une seule tentative, contexte
  réduit, outils web facultatifs, plafond de budget, pages réellement consultées renvoyées.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any


# Si Claude n'arrive pas à respecter le format imposé, on relance l'appel (ça arrive de temps en temps)
ATTEMPTS = 2

# Variables qui feraient utiliser une clé API (facturée) ou un autre fournisseur au lieu de l'abonnement
BILLING_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
               "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")
AUTH_CACHE_SECONDS = 300
AUTH_TIMEOUT = 30

_auth_lock = threading.Lock()
_auth_checked_at: float | None = None


def subscription_env() -> dict[str, str]:
    """L'environnement du processus, sans les variables d'authentification par clé API."""
    return {key: value for key, value in os.environ.items() if key not in BILLING_ENV}


def check_subscription(env: dict[str, str]) -> None:
    """
    Vérifie, avant tout appel, que Claude Code utilise l'abonnement claude.ai connecté
    (loggedIn, authMethod « claude.ai », apiProvider « firstParty »). Résultat gardé quelques minutes.
    """
    global _auth_checked_at
    with _auth_lock:
        if _auth_checked_at is not None and time.monotonic() - _auth_checked_at < AUTH_CACHE_SECONDS:
            return
        refused = "Claude Code n'est pas connecté avec un abonnement claude.ai : aucun appel lancé."
        try:
            result = subprocess.run(["claude", "auth", "status", "--json"], capture_output=True, text=True,
                                    timeout=AUTH_TIMEOUT, env=env)
            status = json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Impossible de vérifier la connexion de Claude Code (délai dépassé) : aucun appel lancé.")
        except (ValueError, OSError):
            raise RuntimeError(f"{refused} Lance « claude » puis connecte-toi avec ton compte.")
        if not isinstance(status, dict) or status.get("loggedIn") is not True:
            raise RuntimeError(f"{refused} Lance « claude » puis connecte-toi avec ton compte.")
        if status.get("authMethod") != "claude.ai" or status.get("apiProvider") != "firstParty":
            raise RuntimeError(f"{refused} Mode détecté : {status.get('authMethod')} / {status.get('apiProvider')}.")
        _auth_checked_at = time.monotonic()


def _require_claude() -> dict[str, str]:
    if shutil.which("claude") is None:
        raise RuntimeError("La commande 'claude' est introuvable. Claude Code est-il installé ?")
    env = subscription_env()
    check_subscription(env)
    return env


def _call(prompt: str, stdin_text: str, schema: dict, timeout: int, env: dict[str, str]) -> dict[str, Any]:
    """Un appel à `claude -p`. Renvoie la réponse JSON complète de Claude Code."""

    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(schema),
                # Claude n'a besoin d'aucun outil (fichiers, web...) : tout est dans stdin
                "--tools",
                "",
            ],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude n'a pas répondu en moins de {timeout} secondes.")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        details = (result.stderr or result.stdout).strip()[:500]
        raise RuntimeError(f"Claude a échoué (code {result.returncode}) : {details}")


def _structured_output(response: dict) -> dict[str, Any] | None:
    """La réponse au format imposé, None si Claude n'a pas respecté le format. Lève les autres échecs."""
    if not response.get("is_error") and "structured_output" in response:
        return response["structured_output"]
    if response.get("subtype") == "error_max_structured_output_retries":
        return None
    if response.get("subtype") == "error_max_budget_usd":
        raise RuntimeError("Claude a atteint la limite de consommation prévue pour cette étape.")
    errors = response.get("errors") or [response.get("result") or response.get("subtype") or "erreur inconnue"]
    raise RuntimeError(f"Claude a échoué : {'; '.join(str(error) for error in errors)[:300]}")


def run_claude(prompt: str, stdin_text: str, schema: dict, timeout: int) -> dict[str, Any]:
    """
    Lance `claude -p` localement, envoie stdin_text sur l'entrée standard
    et renvoie la réponse, forcée au format `schema` via --json-schema.
    """

    env = _require_claude()

    for attempt in range(1, ATTEMPTS + 1):
        output = _structured_output(_call(prompt, stdin_text, schema, timeout, env))
        if output is not None:
            return output
        if attempt < ATTEMPTS:
            print("Claude n'a pas respecté le format attendu, nouvel essai...")
            continue
        raise RuntimeError("Claude n'a pas réussi à répondre au format attendu, même après plusieurs essais. Réessaie.")

    raise RuntimeError("Claude n'a pas répondu.")


# ---------- Appels légers (une tentative, contexte réduit, outils web facultatifs) ----------

TASK_SYSTEM_PROMPT = ("You are a careful assistant. Follow the user's instructions exactly and return only the "
                      "requested structured data. Never invent facts.")
WEB_TOOLS = ("WebSearch", "WebFetch")
_URL = re.compile(r"https?://[^\s\"'<>()\[\]{}\\]+")


@dataclass
class WebPage:
    """Une page renvoyée par les outils web pendant l'appel : lue (WebFetch) ou résultat de recherche."""
    url: str
    access: str                     # "fetched" | "search"
    text: str = ""                  # ce que l'outil a renvoyé pour cette page (sert à vérifier les faits)


@dataclass
class TaskResult:
    output: dict[str, Any]
    pages: list[WebPage] = field(default_factory=list)


def _block_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_block_text(item.get("text") if isinstance(item, dict) else item) for item in content)
    return ""


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:!?")


def parse_stream(stdout: str) -> tuple[dict | None, dict | None, list[WebPage]]:
    """
    Lit la sortie `--output-format stream-json` : message d'initialisation, résultat final et pages
    consultées. Une URL n'est retenue que si un outil l'a réellement renvoyée : adresse lue par
    WebFetch sans erreur, ou lien d'un résultat WebSearch (jamais une URL citée dans une page lue).
    """
    init, result, tool_uses, pages = None, None, {}, {}
    for line in stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        kind = message.get("type")
        if kind == "system" and message.get("subtype") == "init":
            init = message
        elif kind == "result":
            result = message
        elif kind == "assistant":
            for block in (message.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_uses[block.get("id")] = (block.get("name"), block.get("input") or {})
        elif kind == "user":
            for block in (message.get("message") or {}).get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_result" or block.get("is_error"):
                    continue
                name, tool_input = tool_uses.get(block.get("tool_use_id"), (None, {}))
                text = _block_text(block.get("content"))
                if name == "WebFetch" and isinstance(tool_input.get("url"), str):
                    url = _clean_url(tool_input["url"])
                    page = pages.setdefault(url, WebPage(url, "fetched"))
                    page.access, page.text = "fetched", (page.text + "\n" + text).strip()
                elif name == "WebSearch":
                    found = text + "\n" + json.dumps(message.get("tool_use_result") or {}, ensure_ascii=False)
                    for url in dict.fromkeys(_clean_url(u) for u in _URL.findall(found)):
                        page = pages.setdefault(url, WebPage(url, "search"))
                        page.text = (page.text + "\n" + text).strip()
    return init, result, list(pages.values())


def run_claude_task(prompt: str, stdin_text: str, schema: dict, timeout: int, *, model: str | None = None,
                    tools: tuple[str, ...] = (), max_budget_usd: float | None = None) -> TaskResult:
    """
    Un seul appel (pas de nouvel essai), dans un dossier temporaire (pas de CLAUDE.md du projet),
    avec un prompt système court, sans MCP, sans skills, sans session enregistrée. `tools` : outils
    autorisés (uniquement WEB_TOOLS). Lève RuntimeError en cas d'échec.
    """
    if any(tool not in WEB_TOOLS for tool in tools):
        raise ValueError(f"outils non autorisés : {tools}")
    env = _require_claude()

    command = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
               "--json-schema", json.dumps(schema), "--tools", ",".join(tools),
               "--system-prompt", TASK_SYSTEM_PROMPT, "--strict-mcp-config", "--disable-slash-commands",
               "--no-session-persistence"]
    if tools:
        command += ["--allowedTools", ",".join(tools)]
    if model:
        command += ["--model", model]
    if max_budget_usd is not None:
        command += ["--max-budget-usd", f"{max_budget_usd:.2f}"]

    with tempfile.TemporaryDirectory(prefix="claude-task-") as workdir:
        try:
            completed = subprocess.run(command, input=stdin_text, capture_output=True, text=True, timeout=timeout,
                                       env=env, cwd=workdir)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude n'a pas répondu en moins de {timeout} secondes.")

    init, result, pages = parse_stream(completed.stdout)
    if init is not None and init.get("apiKeySource") not in (None, "none"):
        raise RuntimeError("Claude Code a utilisé une clé API au lieu de l'abonnement claude.ai : résultat ignoré.")
    if result is None:
        details = (completed.stderr or completed.stdout).strip()[-500:]
        raise RuntimeError(f"Claude a échoué (code {completed.returncode}) : {details}")
    output = _structured_output(result)
    if output is None:
        raise RuntimeError("Claude n'a pas réussi à répondre au format attendu. Réessaie.")
    return TaskResult(output, pages)

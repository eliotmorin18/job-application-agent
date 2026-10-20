import json
import shutil
import subprocess
from typing import Any


# Si Claude n'arrive pas à respecter le format imposé, on relance l'appel (ça arrive de temps en temps)
ATTEMPTS = 2


def _call(prompt: str, stdin_text: str, schema: dict, timeout: int) -> dict[str, Any]:
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
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Claude n'a pas répondu en moins de {timeout} secondes.")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        details = (result.stderr or result.stdout).strip()[:500]
        raise RuntimeError(f"Claude a échoué (code {result.returncode}) : {details}")


def run_claude(prompt: str, stdin_text: str, schema: dict, timeout: int) -> dict[str, Any]:
    """
    Lance `claude -p` localement, envoie stdin_text sur l'entrée standard
    et renvoie la réponse, forcée au format `schema` via --json-schema.
    """

    if shutil.which("claude") is None:
        raise RuntimeError("La commande 'claude' est introuvable. Claude Code est-il installé ?")

    for attempt in range(1, ATTEMPTS + 1):
        response = _call(prompt, stdin_text, schema, timeout)

        if not response.get("is_error") and "structured_output" in response:
            return response["structured_output"]

        format_failure = response.get("subtype") == "error_max_structured_output_retries"
        if format_failure and attempt < ATTEMPTS:
            print("Claude n'a pas respecté le format attendu, nouvel essai...")
            continue

        if format_failure:
            raise RuntimeError("Claude n'a pas réussi à répondre au format attendu, même après plusieurs essais. Réessaie.")

        errors = response.get("errors") or [response.get("result") or response.get("subtype") or "erreur inconnue"]
        raise RuntimeError(f"Claude a échoué : {'; '.join(str(error) for error in errors)[:300]}")

    raise RuntimeError("Claude n'a pas répondu.")

import json
import shutil
import subprocess
from typing import Any


def run_claude(prompt: str, stdin_text: str, schema: dict, timeout: int) -> dict[str, Any]:
    """
    Lance `claude -p` localement, envoie stdin_text sur l'entrée standard
    et renvoie la réponse, forcée au format `schema` via --json-schema.
    """

    if shutil.which("claude") is None:
        raise RuntimeError("La commande 'claude' est introuvable. Claude Code est-il installé ?")

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

    if result.returncode != 0:
        raise RuntimeError(f"Claude a échoué :\n{result.stderr or result.stdout}")

    response = json.loads(result.stdout)

    if response.get("is_error") or "structured_output" not in response:
        raise RuntimeError(f"Réponse inattendue de Claude :\n{result.stdout}")

    return response["structured_output"]

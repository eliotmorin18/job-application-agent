import re
import shutil
import subprocess
from pathlib import Path


ANSWER_MARKER = "Ta réponse :"


def _section(number: int, question: dict) -> str:
    lines = [f"## {number}. {question['field']}"]

    if question.get("reason"):
        lines.append(f"_{question['reason']}_")

    if question.get("options"):
        lines.append("Options : " + " · ".join(question["options"]))
    elif question["kind"] == "text":
        lines.append("(texte libre : écris tes idées en vrac, l'agent rédigera)")

    lines += ["", ANSWER_MARKER, "> ", ""]

    return "\n".join(lines)


def write_questions(path: Path, title: str, questions: list[dict]) -> None:
    """Crée reponses.md avec une section par question (numérotées à partir de 1)."""

    header = [
        f"# {title}",
        "",
        "Écris tes réponses sous chaque question, comme tu veux (en vrac, en français...).",
        "Pour une liste d'options, pas besoin de recopier l'option exacte : dis ce que tu veux dire.",
        "Laisse vide ou écris « moi » pour remplir toi-même dans Chrome.",
        "Enregistre le fichier, puis tape « ok » dans le terminal.",
        "",
    ]

    body = [_section(question["number"], question) for question in questions]

    path.write_text("\n".join(header) + "\n" + "\n".join(body), encoding="utf-8")


def append_questions(path: Path, questions: list[dict]) -> None:
    """Ajoute des questions complémentaires à la fin de reponses.md."""

    text = path.read_text(encoding="utf-8").rstrip() + "\n\n# Questions complémentaires\n\n"
    text += "\n".join(_section(question["number"], question) for question in questions)

    path.write_text(text, encoding="utf-8")


def read_answers(path: Path) -> dict[int, str]:
    """Relit reponses.md et renvoie {numéro de question: ce que le candidat a écrit}."""

    text = path.read_text(encoding="utf-8")
    answers = {}

    # Découpe sur les titres "## 3. ..." ; chaque morceau commence par le numéro
    for chunk in re.split(r"^## (?=\d+\.)", text, flags=re.MULTILINE)[1:]:
        number = int(chunk.split(".", 1)[0])

        if ANSWER_MARKER not in chunk:
            continue

        after = chunk.split(ANSWER_MARKER, 1)[1]
        after = re.split(r"^# ", after, flags=re.MULTILINE)[0]  # s'arrête avant un titre de niveau 1
        lines = [re.sub(r"^>\s?", "", line).rstrip() for line in after.strip().splitlines()]
        answers[number] = "\n".join(lines).strip()

    return answers


def append_summary(path: Path, filled: list[dict]) -> None:
    """Ajoute à la fin de reponses.md ce que l'agent a mis dans le formulaire."""

    text = path.read_text(encoding="utf-8").rstrip() + "\n\n# Ce que l'agent a mis dans le formulaire\n\n"

    for item in filled:
        text += f"## {item['field']}\n{item['value'] or '(à remplir par toi dans Chrome)'}\n\n"

    path.write_text(text, encoding="utf-8")


def open_in_editor(path: Path) -> None:
    """Ouvre le fichier dans VS Code (ou l'éditeur par défaut si VS Code est introuvable)."""

    if shutil.which("code"):
        subprocess.run(["code", "-r", str(path)], check=False)
    elif Path("/Applications/Visual Studio Code.app").exists():
        subprocess.run(["open", "-a", "Visual Studio Code", str(path)], check=False)
    else:
        subprocess.run(["open", str(path)], check=False)


def wait_for_ok(message: str) -> bool:
    """Attend que le candidat tape ok. Renvoie False si personne ne peut répondre (pas de terminal)."""

    while True:
        try:
            answer = input(f"{message} Tape « ok » quand c'est fait : ")
        except EOFError:
            return False

        if answer.strip().lower() in ("ok", "o", "oui", "y", "yes"):
            return True

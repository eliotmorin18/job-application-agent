"""
Comment l'agent de candidature parle au candidat.

L'agent (browser/apply_agent.py) ne sait pas s'il tourne dans le terminal ou derrière
l'interface : il appelle seulement ces méthodes.
- TerminalInteraction : messages dans le terminal, questions dans reponses.md (python main.py)
- ApplicationRun (workflows/application_run.py) : frise et chat de l'interface (python server.py)
"""

from pathlib import Path

from browser import questions_file


class Interaction:
    """Ce que l'agent peut demander au candidat. Chaque façon de lui parler l'implémente."""

    def step(self, key: str, status: str, detail: str | None = None) -> None:
        """Met à jour une étape de la frise (fill_form, your_answers, fill_answers)."""

    def wait_for_action(self, message: str) -> bool:
        """Le site bloque (compte, connexion, captcha) : attend que le candidat le fasse.
        Renvoie False si le candidat a abandonné."""
        raise NotImplementedError

    def ask(self, questions: list[dict], follow_up: bool) -> dict[int, str] | None:
        """Pose des questions et renvoie les notes du candidat : {numéro de question: texte},
        ou {0: texte} si le candidat a répondu à tout d'un coup. None s'il a abandonné."""
        raise NotImplementedError

    def answered(self, numbers: list[int]) -> None:
        """Ces questions ont maintenant une réponse (ou sont laissées au candidat)."""

    def cancelled(self) -> bool:
        """Le candidat a abandonné la candidature."""
        return False


class TerminalInteraction(Interaction):
    """Messages dans le terminal, questions dans reponses.md ouvert dans VS Code."""

    def __init__(self, answers_path: Path, title: str):
        self.answers_path = answers_path
        self.title = title
        self._file_created = False

    def step(self, key: str, status: str, detail: str | None = None) -> None:
        if detail:
            print(f"    {detail}")

    def wait_for_action(self, message: str) -> bool:
        print(f"\n{message}")
        return questions_file.wait_for_ok("    Fais-le dans Chrome.")

    def ask(self, questions: list[dict], follow_up: bool) -> dict[int, str] | None:
        if not self._file_created:
            questions_file.write_questions(self.answers_path, self.title, questions)
            questions_file.open_in_editor(self.answers_path)
            self._file_created = True
            print(f"\nJ'ai besoin de toi pour {len(questions)} question(s) : réponds dans {self.answers_path}")
        else:
            questions_file.append_questions(self.answers_path, questions)
            print(f"    J'ai encore {len(questions)} question(s) : regarde en bas du fichier.")

        if not questions_file.wait_for_ok("    Écris tes réponses dans le fichier et enregistre-le."):
            return None

        print("    Je lis tes réponses...")
        return questions_file.read_answers(self.answers_path)

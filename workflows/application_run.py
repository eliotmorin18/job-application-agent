import copy
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from browser.apply_agent import apply
from browser.read_job import normalize_job_url, read_job
from cv.build_cv import compile_cv, write_cv
from llm.analyze_job import analyze_job
from llm.generate_cv import generate_cv
from llm.verify_cv import verify_cv
from workflows.interaction import Interaction


# Nombre de fois où Claude peut réécrire le CV si la vérification trouve des choses inventées
MAX_CORRECTIONS = 2

# Étapes affichées dans la frise de l'interface, dans l'ordre
STEPS = [
    ("read_offer", "Lecture de l'offre"),
    ("analyze_offer", "Analyse de l'offre"),
    ("write_cv", "Rédaction du CV"),
    ("verify_cv", "Vérification du CV"),
    ("pdf", "Génération du PDF"),
    ("fill_form", "Remplissage du formulaire"),
    ("your_answers", "Tes réponses"),
    ("fill_answers", "Remplissage de tes réponses"),
    ("ready", "Prêt à envoyer"),
]

# Champs de l'offre envoyés à l'interface
OFFER_FIELDS = [
    "company", "job_title", "location", "contract_type", "job_level", "summary",
    "key_points", "must_have", "nice_to_have", "practical_info",
]


class ApplicationRun(Interaction):
    """
    Une candidature pilotée depuis l'interface : fait tourner le pipeline en arrière-plan
    et garde son état (étapes, offre, CV...) pour que le serveur puisse le renvoyer.
    C'est aussi l'« Interaction » de l'agent de candidature : ses questions vont dans le
    chat de l'interface, et ses blocages (compte, connexion) dans la frise.
    """

    def __init__(self, url: str):
        self.id = uuid.uuid4().hex[:12]
        self.url = normalize_job_url(url)
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancelled = threading.Event()  # mis quand le candidat abandonne
        self._continued = threading.Event()  # le candidat a cliqué sur « C'est fait »
        self._answered = threading.Event()   # le candidat a envoyé ses réponses dans le chat
        self._answer_text = ""
        self._waiting_step = "fill_form"     # étape où l'agent attend une action du candidat

        # Résultats intermédiaires : gardés pour reprendre après une erreur sans tout refaire
        self.job: dict | None = None
        self.offer: dict | None = None
        self.cv: dict | None = None
        self.issues: list[dict] = []
        self.main_tex: Path | None = None
        self.pdf: Path | None = None

        self.state = {
            "id": self.id,
            "url": self.url,
            "status": "running",
            "message": None,
            "steps": [{"key": key, "label": label, "status": "pending", "detail": None} for key, label in STEPS],
            "offer": None,
            "questions": [],
            "chat": [],
            "cv": None,
            "strengths": [],
            "gaps": [],
            "answers_filled": [],
            "manual": [],
        }

    # ---------- État partagé avec le serveur ----------

    def snapshot(self) -> dict:
        """Copie de l'état, au format attendu par l'interface."""
        with self._lock:
            return copy.deepcopy(self.state)

    def _update(self, **fields) -> None:
        with self._lock:
            self.state.update(fields)

    def _step(self, key: str, status: str, detail: str | None = None) -> None:
        with self._lock:
            for step in self.state["steps"]:
                if step["key"] == key:
                    step["status"] = status
                    step["detail"] = detail

    def _agent_says(self, text: str) -> None:
        with self._lock:
            self.state["chat"].append({"role": "agent", "text": text, "time": datetime.now().strftime("%H:%M")})

    # ---------- Commandes venant de l'interface ----------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_active(self) -> bool:
        return self.state["status"] not in ("ready", "submitted", "abandoned", "error")

    def retry(self) -> None:
        """Relance le pipeline après une erreur, à partir de l'étape qui a échoué."""
        if self.state["status"] != "error":
            raise ValueError("Il n'y a pas d'erreur à relancer.")
        self._update(status="running", message=None)
        self.start()

    def continue_(self) -> None:
        """Le candidat a fait l'action demandée (compte, connexion...) dans Chrome."""
        if self.state["status"] != "action_required":
            raise ValueError("L'agent n'attend aucune action de ta part.")
        self._continued.set()

    def answer(self, text: str) -> None:
        """Le candidat répond dans le chat aux questions de l'agent."""
        if self.state["status"] != "questions":
            raise ValueError("L'agent n'attend pas de réponse pour le moment.")
        with self._lock:
            self.state["chat"].append({"role": "user", "text": text, "time": datetime.now().strftime("%H:%M")})
        self._answer_text = text
        self._answered.set()

    def mark(self, status: str) -> None:
        """Statut final choisi par le candidat : submitted ou abandoned."""
        if status == "abandoned":
            # L'agent s'arrête à la fin de l'étape en cours et ne touche plus à l'état
            self._cancelled.set()
        self._update(status=status)

    # ---------- Le pipeline ----------

    def _run(self) -> None:
        current = None
        try:
            for key, function in [
                ("read_offer", self._read_offer),
                ("analyze_offer", self._analyze_offer),
                ("write_cv", self._write_cv),
                ("verify_cv", self._verify_cv),
                ("pdf", self._build_pdf),
                ("fill_form", self._apply),
            ]:
                if self._cancelled.is_set():
                    return
                if self._step_status(key) == "done":
                    continue  # déjà fait avant une erreur
                current = key
                self._step(key, "running")
                detail = function()
                if self._cancelled.is_set():
                    return
                if detail is not None:
                    self._step(key, "done", detail)

            if not self._cancelled.is_set():
                self._update(status="ready")

        except Exception as error:  # noqa: BLE001 — toute erreur doit s'afficher dans la frise
            if self._cancelled.is_set():
                return
            traceback.print_exc()
            message = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
            if current:
                self._step(current, "error", message)
            self._update(status="error", message=message)

    def _step_status(self, key: str) -> str:
        with self._lock:
            return next(step["status"] for step in self.state["steps"] if step["key"] == key)

    def _read_offer(self) -> str:
        self.job = read_job(self.url)
        return f"Page lue ({len(self.job['text'])} caractères)."

    def _analyze_offer(self) -> str:
        self.offer = analyze_job(self.job)
        self._update(offer={field: self.offer.get(field) for field in OFFER_FIELDS})
        return f"{self.offer.get('job_title')} — {self.offer.get('company')}"

    def _write_cv(self) -> str:
        self.cv = generate_cv(self.offer)
        self._update(gaps=self.cv["gaps"])
        chosen = len(self.cv["selected_experience_ids"]), len(self.cv["selected_project_ids"])
        return f"{chosen[0]} expérience(s) et {chosen[1]} projet(s) choisis."

    def _verify_cv(self) -> str:
        self.issues = verify_cv(self.cv)

        for attempt in range(1, MAX_CORRECTIONS + 1):
            if not self.issues:
                break
            self._step("verify_cv", "running", f"{len(self.issues)} point(s) à corriger, réécriture {attempt}/{MAX_CORRECTIONS}…")
            self.cv = generate_cv(self.offer, previous_cv=self.cv, issues=self.issues)
            self.issues = verify_cv(self.cv)

        self.cv["verification_issues"] = self.issues
        self._update(gaps=self.cv["gaps"])

        if not self.issues:
            return "Tout ce qui est dans le CV vient de ton profil."
        return f"{len(self.issues)} point(s) à vérifier toi-même."

    def _build_pdf(self) -> str:
        self.main_tex = write_cv(self.cv, self.offer)
        self.pdf, pages = compile_cv(self.main_tex)

        issues = [f"« {issue['cv_text']} » : {issue['problem']}" for issue in self.issues]
        self._update(cv={"pdf_ready": True, "verification_issues": issues})

        return f"CV en PDF ({pages} page{'s' if pages > 1 else ''})."

    def _apply(self) -> None:
        """Remplit la candidature dans Chrome. L'agent met lui-même à jour les étapes suivantes."""
        result = apply(self.url, self.pdf, self.offer, interaction=self)

        if result["status"] == "cancelled":
            return

        messages = []
        if result["status"] == "max_steps":
            messages.append("L'agent s'est arrêté avant la fin : vérifie bien le formulaire.")
        if result["errors"]:
            messages.append(f"{len(result['errors'])} action(s) de l'agent ont échoué : vérifie le formulaire.")
        button = f"« {result['submit_label']} »" if result["submit_label"] else "le bouton d'envoi"
        messages.append(f"Relis tout dans Chrome, puis clique toi-même sur {button}.")

        self._update(
            answers_filled=[{"field": a["field"], "value": a["value"]} for a in result["user_answers"]],
            manual=result["manual"],
            message=" ".join(messages),
        )
        self._step("ready", "done", "Il ne reste qu'à relire et envoyer.")

    # ---------- Interaction : ce que l'agent de candidature demande au candidat ----------

    def step(self, key: str, status: str, detail: str | None = None) -> None:
        if not self._cancelled.is_set():
            self._step(key, status, detail)

    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def _wait(self, event: threading.Event) -> bool:
        """Attend un clic du candidat. Renvoie False s'il abandonne entre-temps."""
        while not event.wait(timeout=1):
            if self._cancelled.is_set():
                return False
        event.clear()
        return not self._cancelled.is_set()

    def wait_for_action(self, message: str) -> bool:
        key = self._current_running_step()
        self._continued.clear()
        self._step(key, "action_required", f"{message} Fais-le dans la fenêtre Chrome de l'agent (sans la fermer), puis clique sur « C'est fait ».")
        self._update(status="action_required", message=None)

        if not self._wait(self._continued):
            return False

        self._step(key, "running", "Je reprends…")
        self._update(status="running")
        return True

    def ask(self, questions: list[dict], follow_up: bool) -> dict[int, str] | None:
        with self._lock:
            self.state["questions"] += [
                {
                    "number": q["number"],
                    "field": q["field"],
                    "kind": q["kind"],
                    "options": q.get("options") or [],
                    "reason": q.get("reason", ""),
                    "answered": False,
                }
                for q in questions
            ]

        if follow_up:
            lines = [f"Merci ! Il me manque encore {len(questions)} précision(s) :"]
            lines += [f"• {q['field']} : {q['reason']}" for q in questions]
        else:
            lines = [
                f"J'ai rempli tout ce que je pouvais. Il me manque {len(questions)} réponse(s), "
                "listées au-dessus. Réponds à tout d'un coup, en vrac : je rédigerai et je choisirai "
                "les bonnes options. Écris « moi » pour une question que tu préfères remplir toi-même."
            ]
        self._agent_says("\n".join(lines))

        self._answered.clear()
        self._step("your_answers", "running", "En attente de tes réponses.")
        self._update(status="questions")

        if not self._wait(self._answered):
            return None

        self._step("your_answers", "running", "Je lis tes réponses…")
        self._update(status="running")
        return {0: self._answer_text}

    def answered(self, numbers: list[int]) -> None:
        with self._lock:
            for question in self.state["questions"]:
                if question["number"] in numbers:
                    question["answered"] = True

    def _current_running_step(self) -> str:
        with self._lock:
            running = [step["key"] for step in self.state["steps"] if step["status"] == "running"]
        return running[-1] if running else "fill_form"

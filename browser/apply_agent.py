import json
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import yaml
from playwright.sync_api import (
    sync_playwright,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)

from browser import questions_file
from llm.claude_cli import run_claude
from llm.compose_answers import compose_answers
from workflows.interaction import Interaction, TerminalInteraction


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "profile" / "private" / "candidate.yaml"

# Le navigateur garde ici cookies et connexions (LinkedIn, Workday...) d'une fois sur l'autre.
# Dossier privé : il est dans .gitignore.
SESSION_DIR = ROOT / "browser" / "session"

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEBUG_PORT = 9222

MAX_STEPS = 40
MAX_PAGE_TEXT = 8000

# Boutons d'envoi final : jamais cliqués par l'agent si l'envoi automatique est désactivé,
# même si Claude ne les a pas signalés comme tels.
FINAL_SUBMIT_PATTERN = re.compile(
    r"submit|soumettre|envoyer|send application|send my application|complete application|"
    r"finaliser|confirmer (ma|la) candidature|valider (ma|la) candidature",
    re.IGNORECASE,
)


# Repère tous les éléments interactifs visibles d'un document, leur donne un
# identifiant (data-agent-id) et renvoie une description lisible par Claude.
SNAPSHOT_JS = r"""
(prefix) => {
  const clean = (t) => (t || "").replace(/\s+/g, " ").trim().slice(0, 150);

  const isVisible = (el) => {
    if (el.type === "file") return true;  // souvent caché derrière un joli bouton
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };

  const labelOf = (el) => {
    if (el.labels && el.labels.length) return clean([...el.labels].map(l => l.innerText).join(" "));
    if (el.getAttribute("aria-label")) return clean(el.getAttribute("aria-label"));
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const t = by.split(" ").map(id => document.getElementById(id)).filter(Boolean).map(e => e.innerText).join(" ");
      if (t) return clean(t);
    }
    if (["BUTTON", "A"].includes(el.tagName) || el.getAttribute("role") === "option") return clean(el.innerText || el.value);
    if (el.placeholder) return clean(el.placeholder);
    if (el.title) return clean(el.title);
    return clean(el.name || el.id);
  };

  // Dernier titre de champ (label, légende, titre) placé avant l'élément dans la page
  const titles = [...document.querySelectorAll("label, legend, h1, h2, h3, h4, h5, h6, [class*=label]")];
  const previousTitle = (el) => {
    const own = labelOf(el);
    let found = "";
    for (const t of titles) {
      if (t.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING && !t.contains(el)) {
        const text = clean(t.innerText);
        if (text && text !== own) found = text;
      }
    }
    return found;
  };

  const groupOf = (el) => {
    if (el.type === "file") return previousTitle(el);

    const fieldset = el.closest("fieldset");
    if (fieldset) {
      const legend = fieldset.querySelector("legend");
      if (legend) return clean(legend.innerText);
    }
    // Remonte jusqu'au premier parent qui contient plus que le libellé de l'élément
    const own = labelOf(el);
    let node = el.parentElement;
    for (let i = 0; node && i < 6; i++, node = node.parentElement) {
      const t = clean(node.innerText);
      if (t && t.replace(new RegExp(own, "g"), "").trim().length > 3) return t.slice(0, 120);
    }
    return "";
  };

  const selector = [
    "input:not([type=hidden])", "textarea", "select", "button", "a[href]",
    "[role=button]", "[role=combobox]", "[role=option]", "[role=radio]", "[role=checkbox]",
  ].join(",");

  // Parcourt aussi les "shadow DOM" (composants web, ex. autocomplétion Google)
  function* walk(root) {
    for (const el of root.querySelectorAll("*")) {
      if (el.matches(selector)) yield el;
      if (el.shadowRoot) yield* walk(el.shadowRoot);
    }
  }

  const elements = [];
  let n = 0;

  for (const el of walk(document)) {
    if (!isVisible(el) || el.disabled) continue;

    const id = `${prefix}${n++}`;
    el.setAttribute("data-agent-id", id);

    const item = {
      id,
      tag: el.tagName.toLowerCase(),
      type: el.type || el.getAttribute("role") || "",
      label: labelOf(el),
    };

    // Libellé absent ou technique (ex. "cards[46d3...][field0]") : on prend le titre affiché au-dessus
    if (!item.label || /[\[\]{}]|^[a-z]+[A-Z][A-Za-z]*$/.test(item.label)) {
      item.label = previousTitle(el) || item.label;
    }

    const role = el.getAttribute("role");
    if (role && role !== item.type) item.role = role;

    // Le libellé seul ne suffit pas toujours (ex. deux champs "Attach" : CV et lettre)
    if (["checkbox", "radio", "file"].includes(el.type) || !item.label) item.group = groupOf(el);

    if (["checkbox", "radio"].includes(el.type)) {
      item.checked = el.checked;
    } else if (el.tagName === "SELECT") {
      item.value = clean(el.selectedOptions[0] ? el.selectedOptions[0].text : "");
      item.options = [...el.options].map(o => clean(o.text)).slice(0, 60);
    } else if (["INPUT", "TEXTAREA"].includes(el.tagName)) {
      item.value = el.type === "file" ? (el.files.length ? el.files[0].name : "") : clean(el.value);
    }

    // Liste déroulante personnalisée : la valeur choisie est affichée à côté du champ, pas dedans
    if (role === "combobox" && el.parentElement && el.parentElement.parentElement) {
      item.shown = clean(el.parentElement.parentElement.innerText);
    }

    if (el.required || el.getAttribute("aria-required") === "true") item.required = true;
    if (el.tagName === "A") item.href = (el.getAttribute("href") || "").slice(0, 100);

    elements.push(item);
  }

  return elements;
}
"""


AGENT_PROMPT = """
You are a browser agent filling a job application form for a candidate.
The candidate is not watching while you fill: never stop to ask. Fill everything you can and
list in todo_for_candidate the fields that need him: they will be asked to him afterwards and
his answers will come back to you as USER ANSWERS. The candidate submits the form himself.

Provided on stdin:
- CANDIDATE: the candidate's personal information, skills and standard form answers
- JOB: the job being applied to
- USER ANSWERS: answers the candidate gave for specific fields (field label, element id
  when known, kind, value). Fill each of them exactly: for a dropdown the value is the exact
  option (" | " separates several options of a multi-select), for a text field the exact
  text, for a checkbox "check" / "uncheck" or the exact label(s) of the box(es) to check in
  a group. Never put them in todo_for_candidate again.
- TODO FOR CANDIDATE: what you already decided the candidate must do himself
- HISTORY: the actions already performed and their result
- PAGE: the current URL, the visible text of the page, and the interactive elements
  (each with an id; ids starting with "f1-", "f2-"... are inside iframes)

Rules:
- Use ONLY information from CANDIDATE and USER ANSWERS. Never invent an answer, never write
  a motivation text or an opinion for the candidate, never guess a date or a preference.
- If a field needs information you do not have (motivation text, personal preferences,
  salary, other recruitment processes, cover letter...), leave it empty and add it to
  todo_for_candidate: field = the field's label (the question as written on the page),
  element_id = the id of the input to fill, kind = "text" (free text), "choice" (dropdown,
  radio buttons), "checkbox" or "other" (e.g. a cover letter file), reason = in French, why
  you need the candidate. Do not add again an item already in TODO FOR CANDIDATE.
- To attach the CV, use an "upload_cv" action on the file input of the resume/CV field.
  Never upload the CV in a cover-letter field.
- Cookie banners: refuse or keep only necessary cookies.
- If the page is a job description, click the button/link that starts the application
  ("Apply", "Postuler", "Candidater"...). It may open a new tab: that is handled for you.
- If applying requires to log in, create an account, enter a password or solve a captcha,
  return status "blocked" and explain in message (French). Never type a password.
- Never click the button that finally sends the application. Mark any click that would
  send the application with "final_submit": true.
- Fill as many fields as possible in one step (several actions). The next step shows the
  updated page: check that the values are right, fix errors shown on the page, and do not
  repeat an action that already succeeded in HISTORY.
- Native <select>: use "select". Custom dropdown (role=combobox, "Select..."): use "choose"
  with the text of the wanted option; it types the text and clicks the matching option.
  Multi-select dropdowns (e.g. languages): one "choose" action per value. The option text must be
  EXACTLY one of the options: if HISTORY shows an error with the list of available options,
  choose again with the exact text of the right option (or leave it to the candidate if
  none fits). "shown" is what the dropdown currently displays.
- A value is only set when the page shows it: if a field you already filled still shows
  "Select..." or "is required", fill it again.
- Education: fill every school of CANDIDATE.education, most recent first, using the
  "Add another" button for each additional school. Map the degree to the closest option.
- Use CANDIDATE for every question it covers, e.g. preferences.preferred_locations for the
  location (the first one offered), personal.nationality and form_answers for visa / work
  authorization questions, form_answers.available_start_date
  for both internship and full-time start dates, skills for programming languages,
  languages with a level of B2 / C1 / Native for "languages you speak fluently".
- Required acknowledgements (certifying the information is true, accepting the privacy
  policy) can be accepted. Demographic questions: answer with CANDIDATE data when it exists
  (e.g. gender), and accept the related consent checkbox; otherwise leave them to the candidate.
- After the CV is uploaded, the file input may be replaced by the file name: that is a
  success, do not upload it again.
- When every field you can fill is filled (what remains is TODO FOR CANDIDATE and the
  final submit button), return status "finished" with the final button's id in
  submit_element_id ("" if you cannot see it).
- Return status "done" only if the page confirms the application was sent.

Each action: type (fill, select, choose, check, click, upload_cv, press_enter), element_id,
value (text to type or option to choose, "" otherwise), final_submit (true/false).
message: one short sentence in French describing what you are doing.
""".strip()


AGENT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["continue", "finished", "blocked", "done"]},
        "message": {"type": "string"},
        "submit_element_id": {"type": "string"},
        "todo_for_candidate": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "element_id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["text", "choice", "checkbox", "other"]},
                    "reason": {"type": "string"},
                },
                "required": ["field", "element_id", "kind", "reason"],
                "additionalProperties": False,
            },
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["fill", "select", "choose", "check", "click", "upload_cv", "press_enter"],
                    },
                    "element_id": {"type": "string"},
                    "value": {"type": "string"},
                    "final_submit": {"type": "boolean"},
                },
                "required": ["type", "element_id", "value", "final_submit"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["status", "message", "submit_element_id", "todo_for_candidate", "actions"],
    "additionalProperties": False,
}


def _wait_for_page(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=5000)
    except PlaywrightTimeoutError:
        pass


def _snapshot(page) -> tuple[str, list[dict]]:
    """Texte visible de la page + éléments interactifs de la page et de ses iframes."""

    elements = []

    for index, frame in enumerate(page.frames):
        try:
            elements += frame.evaluate(SNAPSHOT_JS, f"f{index}-")
        except PlaywrightError:
            pass  # iframe en cours de chargement ou inaccessible

    try:
        text = page.locator("body").inner_text()
    except PlaywrightError:
        text = ""

    text = re.sub(r"\n\s*\n+", "\n", text)[:MAX_PAGE_TEXT]

    return text, elements


def _locate(page, element_id: str):
    frame_index = int(element_id.split("-")[0][1:])
    return page.frames[frame_index].locator(f'[data-agent-id="{element_id}"]').first


def _element_label(elements: list[dict], element_id: str) -> str:
    for element in elements:
        if element["id"] == element_id:
            return element.get("label", "")
    return ""


def _run_action(page, action: dict, cv_path: Path) -> None:
    locator = _locate(page, action["element_id"])
    kind = action["type"]

    if kind == "fill":
        locator.fill(action["value"], timeout=5000)
    elif kind == "select":
        try:
            locator.select_option(label=action["value"], timeout=5000)
        except PlaywrightError:
            locator.select_option(value=action["value"], timeout=5000)
    elif kind == "check":
        try:
            locator.check(timeout=5000)
        except PlaywrightError:
            locator.click(timeout=5000)
    elif kind == "click":
        locator.click(timeout=5000)
    elif kind == "upload_cv":
        locator.set_input_files(str(cv_path), timeout=5000)
    elif kind == "press_enter":
        locator.press("Enter", timeout=5000)
    elif kind == "choose":
        _choose_option(page, action["element_id"], locator, action["value"])


def _choose_option(page, element_id: str, locator, value: str) -> None:
    """
    Liste déroulante personnalisée (combobox) : clique, tape le texte, attend les
    options proposées et clique sur celle qui correspond le mieux.
    """

    frame = page.frames[int(element_id.split("-")[0][1:])]

    locator.click(timeout=5000)
    locator.fill("", timeout=5000)
    locator.press_sequentially(value, delay=20, timeout=10000)

    # Seulement les options visibles : certaines pages gardent d'autres listes cachées
    # (ex. indicatifs téléphoniques) dont les options sont toujours présentes
    options = frame.locator("[role=option]:visible, [id*='-option-']:visible")

    def visible_options() -> list[str]:
        try:
            options.first.wait_for(state="visible", timeout=8000)
        except PlaywrightTimeoutError:
            return []
        # Listes qui cherchent en ligne (ex. écoles) : attendre la fin du chargement
        for _ in range(10):
            texts = [t.strip() for t in options.all_inner_texts()]
            if texts and not any("loading" in t.lower() or "chargement" in t.lower() for t in texts):
                return texts
            page.wait_for_timeout(500)
        return texts

    texts = visible_options()
    not_options = ("no options", "no results found", "aucun résultat")
    texts = [t for t in texts if t.lower() not in not_options]

    if not texts:
        # Rien ne correspond au texte tapé : on vide pour montrer toutes les options à Claude
        locator.fill("", timeout=5000)
        all_texts = [t for t in visible_options() if t.lower() not in not_options]
        locator.press("Escape")
        raise PlaywrightError(f"aucune option pour {value!r}, options disponibles : {all_texts[:30]}")

    def normalize(text: str) -> str:
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
        return re.sub(r"\s+", " ", text).strip().lower()

    # Uniquement une correspondance exacte (ou une seule option qui contient le texte) :
    # "Master" ne doit pas sélectionner "Master of Business Administration"
    wanted = normalize(value)
    match = next((i for i, t in enumerate(texts) if normalize(t) == wanted), None)
    if match is None and len(texts) == 1 and wanted in normalize(texts[0]):
        match = 0

    if match is None:
        locator.press("Escape")
        raise PlaywrightError(f"pas d'option exactement égale à {value!r}, options proposées : {texts[:30]}")

    options.nth(match).click(timeout=5000)


def _is_final_submit(action: dict, label: str) -> bool:
    return action["type"] == "click" and (action["final_submit"] or bool(FINAL_SUBMIT_PATTERN.search(label)))


def _run_actions(context, page, actions, elements, cv_path: Path, auto_submit: bool, history: list[str]) -> tuple[bool, str]:
    """
    Exécute les actions de Claude. Renvoie (True, libellé du bouton) si l'action suivante
    était l'envoi final et que l'envoi automatique est désactivé.
    """

    for action in actions:
        label = _element_label(elements, action["element_id"])

        if _is_final_submit(action, label) and not auto_submit:
            return True, label

        shown_value = cv_path.name if action["type"] == "upload_cv" else action["value"]
        description = f"{action['type']} [{action['element_id']}] {label!r} {shown_value!r}".strip()

        url_before, tabs_before = page.url, len(context.pages)

        try:
            _run_action(page, action, cv_path)
            history.append(f"OK    {description}")
        except PlaywrightError as error:
            history.append(f"ERROR {description}: {str(error).splitlines()[0]}")
            continue

        # Si un clic a changé de page ou ouvert un onglet, les actions suivantes visent des éléments disparus
        if action["type"] == "click":
            page.wait_for_timeout(1000)
            if page.url != url_before or len(context.pages) != tabs_before:
                break

    return False, ""


def _open_chrome(p):
    """
    Ouvre Google Chrome comme un programme indépendant (profil dans browser/session/)
    et s'y connecte. Chrome reste ouvert quand le script se termine.
    Si Chrome a déjà été ouvert par un lancement précédent, on le réutilise.
    """

    endpoint = f"http://127.0.0.1:{DEBUG_PORT}"

    try:
        return p.chromium.connect_over_cdp(endpoint)
    except PlaywrightError:
        pass

    chrome = CHROME_PATH if Path(CHROME_PATH).exists() else p.chromium.executable_path
    SESSION_DIR.mkdir(exist_ok=True)

    subprocess.Popen(
        [
            chrome,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={SESSION_DIR}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # Chrome survit à la fin du script
    )

    for _ in range(30):
        time.sleep(0.5)
        try:
            return p.chromium.connect_over_cdp(endpoint)
        except PlaywrightError:
            continue

    raise RuntimeError("Impossible de se connecter à Chrome.")


def _report(lines: list[str], report_path: Path | None) -> None:
    print("\n" + "\n".join(lines))

    if report_path:
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n(Récapitulatif enregistré dans {report_path})")


def _read_options(page, element: dict, elements: list[dict]) -> list[str]:
    """
    Liste des options d'une question à choix, sans rien choisir : libellés du groupe pour
    des cases / boutons radio, options d'un <select>, sinon en ouvrant le menu puis en le refermant.
    """

    if element.get("type") in ("checkbox", "radio") and element.get("group"):
        return [e["label"] for e in elements if e.get("group") == element["group"] and e.get("type") == element["type"]]

    if element.get("options"):
        return [option for option in element["options"] if option and option.lower() not in ("select...", "--")]

    if element.get("role") != "combobox":
        return []

    try:
        locator = _locate(page, element["id"])
        frame = page.frames[int(element["id"].split("-")[0][1:])]
        locator.click(timeout=5000)
        options = frame.locator("[role=option]:visible, [id*='-option-']:visible")
        options.first.wait_for(state="visible", timeout=5000)
        texts = [text.strip() for text in options.all_inner_texts() if text.strip()]
        locator.press("Escape")
        return texts[:60]
    except PlaywrightError:
        return []


def _live_page(context, url: str):
    """
    L'onglet sur lequel travailler : le plus récent encore ouvert (un clic a pu ouvrir le site
    de l'entreprise dans un nouvel onglet). Si le candidat a fermé tous les onglets, on rouvre
    l'offre. Si toute la fenêtre Chrome a été fermée, on le dit clairement.
    """

    try:
        pages = [page for page in context.pages if not page.is_closed()]
        if pages:
            return pages[-1]

        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        return page
    except PlaywrightError:
        raise RuntimeError(
            "La fenêtre Chrome de l'agent a été fermée pendant la candidature. "
            "Clique sur « Réessayer » et laisse la fenêtre ouverte jusqu'à la fin."
        )


def _fill_loop(context, url: str, cv_path: Path, auto_submit: bool, base_info: str, user_answers: list[dict],
               todo: list[dict], history: list[str], interaction: Interaction,
               step_key: str) -> tuple[str, str, str, list[dict]]:
    """
    Boucle principale : regarde la page, demande à Claude, exécute. Si le site bloque
    (compte, connexion, captcha), attend que le candidat le fasse puis reprend.
    Renvoie (statut final, message, libellé du bouton d'envoi, éléments de la dernière page).
    """

    idle_steps = 0
    elements: list[dict] = []

    for step in range(1, MAX_STEPS + 1):

        if interaction.cancelled():
            return "cancelled", "", "", elements

        # Si un clic a ouvert un nouvel onglet (ex. LinkedIn -> site de l'entreprise), on le suit
        page = _live_page(context, url)
        try:
            page.bring_to_front()
        except PlaywrightError:
            continue  # l'onglet vient d'être fermé : on en prend un autre au tour suivant
        _wait_for_page(page)

        text, elements = _snapshot(page)

        stdin_text = "\n\n".join([
            base_info,
            "=== USER ANSWERS ===\n" + json.dumps(user_answers, indent=2, ensure_ascii=False),
            "=== TODO FOR CANDIDATE ===\n" + json.dumps(todo, indent=2, ensure_ascii=False),
            "=== HISTORY ===\n" + ("\n".join(history[-60:]) or "(none)"),
            f"=== PAGE ===\nURL: {page.url}\n\nVISIBLE TEXT:\n{text}\n\nELEMENTS:\n"
            + json.dumps(elements, ensure_ascii=False),
        ])

        decision = run_claude(AGENT_PROMPT, stdin_text, AGENT_SCHEMA, timeout=300)
        status = decision["status"]

        interaction.step(step_key, "running", decision["message"])

        answered = {answer["field"] for answer in user_answers}
        known = {item["field"] for item in todo} | answered
        todo += [item for item in decision["todo_for_candidate"] if item["field"] not in known]

        if status == "done":
            return "done", decision["message"], "", elements

        if status == "blocked":
            if not interaction.wait_for_action(decision["message"]):
                return "cancelled", decision["message"], "", elements
            history.append(f"candidate did manually: {decision['message']}")
            idle_steps = 0
            continue

        if status == "finished" and auto_submit:
            decision["actions"].append({
                "type": "click",
                "element_id": decision["submit_element_id"],
                "value": "",
                "final_submit": True,
            })

        done_before = len(history)
        stop, label = _run_actions(context, page, decision["actions"], elements, cv_path, auto_submit, history)

        errors = [line for line in history[done_before:] if line.startswith("ERROR")]
        print(f"    {len(history) - done_before - len(errors)} action(s) faite(s), {len(errors)} erreur(s)")

        if stop:
            return "finished", "", label, elements

        if status == "finished":
            return "finished", "", _element_label(elements, decision["submit_element_id"]), elements

        # Claude ne fait plus rien sans le dire : on considère qu'il a fini
        idle_steps = idle_steps + 1 if not decision["actions"] else 0
        if idle_steps >= 2:
            return "finished", "", "", elements

    return "max_steps", "", "", elements


def _ask_candidate(context, todo: list[dict], elements: list[dict], interaction: Interaction,
                   candidate_text: str, offer: dict | None) -> tuple[list[dict], list[dict]]:
    """
    Pose au candidat les questions que l'agent n'a pas pu remplir, transforme ses notes
    en réponses (avec Claude) et redemande si besoin.
    Renvoie (réponses à remplir, questions laissées au candidat).
    """

    page = _live_page(context, (offer or {}).get("url", "about:blank"))
    by_id = {element["id"]: element for element in elements}

    questions = []
    for number, item in enumerate(todo, start=1):
        question = {"number": number, **item}
        if item["kind"] in ("choice", "checkbox") and item["element_id"] in by_id:
            question["options"] = _read_options(page, by_id[item["element_id"]], elements)
        questions.append(question)

    final: dict[int, dict] = {}
    pending = questions
    next_number = len(questions) + 1
    follow_up = False

    while pending:
        notes = interaction.ask(pending, follow_up)
        if notes is None:
            break

        composed = compose_answers(pending, notes, candidate_text, offer)
        by_number = {question["number"]: question for question in pending}

        follow_ups = []
        resolved = []
        for answer in composed:
            question = by_number.get(answer["number"])
            if not question:
                continue

            original = question.get("original_number", question["number"])

            if answer["status"] == "follow_up":
                # Nouvelle question numérotée, qui garde le champ et les options d'origine
                follow_ups.append({
                    **question,
                    "number": next_number,
                    "reason": answer["follow_up"],
                    "original_number": original,
                })
                next_number += 1
            else:
                final[original] = {**question, **answer}
                resolved += [question["number"], original]

        interaction.answered(resolved)
        pending = follow_ups
        follow_up = True

    to_fill = [
        {"field": q["field"], "element_id": q["element_id"], "kind": q["kind"], "value": q["value"]}
        for q in final.values() if q["status"] == "ready"
    ]
    manual = [q for q in questions if final.get(q["number"], {}).get("status") != "ready"]

    return to_fill, manual


def apply(url: str, cv_path: Path, offer: dict | None, interaction: Interaction) -> dict:
    """
    Ouvre l'offre dans Chrome et remplit la candidature pas à pas avec Claude.
    Ce qu'il ne peut pas remplir seul est demandé au candidat (via `interaction`),
    puis rempli à son tour. Chrome reste ouvert : le candidat relit et clique sur l'envoi.
    Renvoie le résultat : statut, réponses remplies, ce qui reste au candidat...
    """

    candidate_text = CANDIDATE_PATH.read_text(encoding="utf-8")
    candidate = yaml.safe_load(candidate_text)
    auto_submit = candidate.get("application_rules", {}).get("allow_automatic_submission", False)

    candidate_info = {
        "personal": candidate["personal"],
        "form_answers": candidate.get("form_answers", {}),
        "languages": candidate.get("languages", []),
        "skills": candidate.get("skills", {}),
        "preferences": candidate.get("preferences", {}),
        "education": [
            {key: school.get(key) for key in ["school", "degree", "specialization", "start_date", "end_date"]}
            for school in candidate.get("education", [])
        ],
        "cv_file": cv_path.name,
    }
    job_info = {key: (offer or {}).get(key) for key in ["company", "job_title", "location", "contract_type"]}
    job_info["url"] = url

    base_info = "\n\n".join([
        "=== CANDIDATE ===\n" + json.dumps(candidate_info, indent=2, ensure_ascii=False),
        "=== JOB ===\n" + json.dumps(job_info, indent=2, ensure_ascii=False),
    ])

    todo: list[dict] = []
    history: list[str] = []
    user_answers: list[dict] = []
    manual: list[dict] = []

    with sync_playwright() as p:
        browser = _open_chrome(p)
        context = browser.contexts[0]
        page = context.new_page()
        page.bring_to_front()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

        interaction.step("fill_form", "running", "J'ouvre l'offre dans Chrome…")
        status, message, submit_label, elements = _fill_loop(
            context, url, cv_path, auto_submit, base_info, user_answers, todo, history, interaction, "fill_form",
        )
        filled_first = sum(1 for line in history if line.startswith("OK"))
        interaction.step("fill_form", "done", f"{filled_first} action(s) faite(s) dans le formulaire.")

        if status == "finished" and todo:
            interaction.step("your_answers", "running", "En attente de tes réponses.")
            user_answers, manual = _ask_candidate(context, todo, elements, interaction, candidate_text, offer)
            interaction.step("your_answers", "done", f"{len(user_answers)} réponse(s) de ta part.")

            if user_answers and not interaction.cancelled():
                todo[:] = [item for item in manual]
                interaction.step("fill_answers", "running", "Je remplis tes réponses…")
                status, message, label, elements = _fill_loop(
                    context, url, cv_path, auto_submit, base_info, user_answers, todo, history, interaction, "fill_answers",
                )
                submit_label = label or submit_label
            interaction.step("fill_answers", "done", "Tes réponses sont dans le formulaire." if user_answers else None)
        else:
            manual = todo
            interaction.step("your_answers", "done", "Aucune question pour toi.")
            interaction.step("fill_answers", "done", None)

        # On se déconnecte de Chrome SANS le fermer : la page reste ouverte pour le candidat

    return {
        "status": status,
        "message": message,
        "submit_label": submit_label,
        "filled": sum(1 for line in history if line.startswith("OK")),
        "errors": [line[6:] for line in history if line.startswith("ERROR")],
        "user_answers": user_answers,
        "manual": [{"field": item["field"], "reason": item["reason"]} for item in manual],
    }


def apply_in_terminal(url: str, cv_path: Path, offer: dict | None = None, report_path: Path | None = None) -> None:
    """Version terminal : questions dans reponses.md, récapitulatif affiché à la fin."""

    # reponses.md va dans le dossier de la candidature (cv/applications/<offre>/)
    work_dir = report_path.parent if report_path else (
        cv_path.parent.parent if cv_path.parent.name == "build" else cv_path.parent
    )
    answers_path = work_dir / "reponses.md"
    title = " — ".join(part for part in [(offer or {}).get("company"), (offer or {}).get("job_title")] if part) or url

    result = apply(url, cv_path, offer, TerminalInteraction(answers_path, title))
    status = result["status"]

    if answers_path.exists():
        questions_file.append_summary(
            answers_path,
            result["user_answers"] + [{"field": item["field"], "value": ""} for item in result["manual"]],
        )

    lines = ["=" * 70, "CANDIDATURE — RÉCAPITULATIF", "=" * 70, f"Offre : {url}",
             f"{result['filled']} action(s) faite(s) par l'agent."]

    if status == "cancelled":
        lines += ["", f"ARRÊTÉ : {result['message'] or 'candidature interrompue.'}"]
    elif status == "done":
        lines += ["", "La page indique que la candidature a été envoyée."]
    elif status == "max_steps":
        lines += ["", f"L'agent s'est arrêté après {MAX_STEPS} étapes sans finir : vérifie la page."]

    if result["user_answers"]:
        lines += ["", f"Tes réponses remplies par l'agent : {len(result['user_answers'])} (détail dans {answers_path})"]

    if result["manual"]:
        lines += ["", "À FAIRE PAR TOI dans la page Chrome :"]
        lines += [f"  - {item['field']} : {item['reason']}" for item in result["manual"]]

    if result["errors"]:
        lines += ["", "Actions qui ont échoué (à vérifier dans la page) :"]
        lines += [f"  - {line}" for line in result["errors"]]

    if status != "done":
        lines += ["", "Relis tout le formulaire dans Chrome (l'agent peut se tromper)."]
        button = f"« {result['submit_label']} »" if result["submit_label"] else "le bouton d'envoi"
        lines.append(f"Puis clique toi-même sur {button}. La page reste ouverte.")

    _report(lines, report_path)


if __name__ == "__main__":

    if len(sys.argv) != 3:
        print('Usage: python -m browser.apply_agent "<URL>" "<chemin du CV .pdf>"')
        sys.exit(1)

    apply_in_terminal(sys.argv[1], Path(sys.argv[2]).resolve())

"""
Conversion du CV structuré (cv.json, voir cv/document.py) en LaTeX.

Produit les six fichiers de section chargés par cv/template/main.tex, avec les macros et la
mise en page du template (\\resumeItemPlain, \\resumeItemListStart, tabular*...). Claude
n'écrit jamais de LaTeX : tout le texte passe par escape_latex(). Seule mise en forme
permise dans les textes : **gras**.
"""

import re


SECTION_FILES = ["heading", "experience", "education", "projects", "technical-skills", "interests"]

# Titres et libellés écrits par Python (et non par Claude), selon la langue du CV
LABELS = {
    "fr": {
        "experience": "Expérience", "education": "Formation", "projects": "Projets",
        "technical-skills": "Compétences Techniques", "interests": "Centres d'intérêt",
        "summary": "Profil", "languages": "Langues", "colon": " :",
    },
    "en": {
        "experience": "Experience", "education": "Education", "projects": "Projects",
        "technical-skills": "Technical Skills", "interests": "Interests",
        "summary": "Profile", "languages": "Languages", "colon": ":",
    },
}

# Caractères spéciaux de LaTeX, et ceux que la police du template (codage OT1) affiche mal
_SPECIAL = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "<": r"\textless{}", ">": r"\textgreater{}", "|": r"\textbar{}",
    # Pas de guillemets français ni d'euro dans ce codage : équivalents sûrs
    "«": "``", "»": "''", "€": "EUR", "°": r"\textdegree{}",
    "\u00a0": "~", "\u202f": "~",          # espaces insécables (« Profil : », 10 %)
}
# « **mot** » : pas d'espace juste après l'ouverture ni juste avant la fermeture (comme en Markdown)
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")


def _escape_plain(text: str) -> str:
    text = re.sub(r"[ \t\r\n\f\v]+", " ", text)   # pas de retour à la ligne dans une puce ; insécables gardés
    return "".join(_SPECIAL.get(char, char) for char in text)


def escape_latex(text) -> str:
    """
    Texte sûr pour LaTeX. « **mot** » devient \\textbf{mot} ; tout le reste est échappé
    (un « ** » sans fermeture reste tel quel).
    """
    text = str(text or "").strip()
    parts, last = [], 0
    for match in _BOLD.finditer(text):
        parts.append(_escape_plain(text[last:match.start()]))
        parts.append(r"\textbf{" + _escape_plain(match.group(1).strip()) + "}")
        last = match.end()
    parts.append(_escape_plain(text[last:]))
    return "".join(parts)


def latex_url(url: str) -> str:
    """URL dans \\href{...} : seuls %, # et \\ doivent être protégés."""
    return str(url).strip().replace("\\", "/").replace("%", r"\%").replace("#", r"\#")


def display_url(url: str) -> str:
    """« https://www.linkedin.com/in/jane/ » -> « linkedin.com/in/jane »"""
    text = re.sub(r"^https?://", "", str(url).strip())
    return re.sub(r"^www\.", "", text).rstrip("/")


def format_dates(start, end) -> str:
    """Années seulement, comme dans les CV actuels : « 2024–2025 », « 2026 » (même année ou fin inconnue)."""
    start, end = str(start or "")[:4], str(end or "")[:4]
    if start and end and start != end:
        return f"{start}–{end}"
    return start or end


def short_location(location) -> str:
    """« Paris, France » -> « Paris » (le lieu court des CV actuels)."""
    return str(location or "").split(",")[0].strip()


# ---------- Sections ----------

def _banner(title: str) -> str:
    return f"%===========================\n%     {title}\n%===========================\n"


def _item_list(bullets: list) -> str:
    """Puces de l'élément ; aucune liste si l'élément n'a pas de puce (une liste vide ferait échouer LaTeX)."""
    if not bullets:
        return ""
    lines = "\n".join(f"    \\resumeItemPlain{{{escape_latex(bullet)}}}" for bullet in bullets)
    return f"\n\\resumeItemListStart\n{lines}\n\\resumeItemListEnd\n"


def _entry(left: str, right: str, bullets: list) -> str:
    return (
        "\\begin{tabular*}{\\textwidth}{l@{\\extracolsep{\\fill}}r}\n"
        f"    {left} & {right} \\\\\n"
        "\\end{tabular*}\n"
        + _item_list(bullets)
    )


def _place_and_dates(entry: dict) -> str:
    text = ", ".join(part for part in (entry.get("location"), entry.get("dates")) if part)
    return f"\\textbf{{{escape_latex(text)}}}" if text else ""


def render_heading(doc: dict) -> str:
    header, labels = doc["header"], LABELS[doc["language"]]
    icons = {"email": r"\faEnvelope", "phone": r"\faPhone", "linkedin": r"\faLinkedin", "github": r"\faGithub"}

    contacts = []
    for contact in header.get("contacts") or []:
        kind, value = contact["type"], contact["value"]
        if kind == "email":
            shown = f"\\href{{mailto:{latex_url(value)}}}{{{escape_latex(value)}}}"
        elif kind == "phone":
            shown = escape_latex(value)
        else:
            shown = f"\\href{{{latex_url(value)}}}{{{escape_latex(display_url(value))}}}"
        contacts.append(f"{icons[kind]}\\ {shown}")

    name = f"\\textbf{{\\Huge \\scshape {escape_latex(header['name'])}}}"
    lines = [name + (" \\\\ \\vspace{2pt}" if contacts else "")]
    if contacts:
        lines.append("\\small " + "\\ $|$\\\n    ".join(contacts))

    text = "%----------HEADING-----------------\n\\begin{center}\n    " + "\n    ".join(lines) + "\n\\end{center}\n"
    if header.get("summary"):
        text += (f"\n\\vspace{{4pt}}\n\\textbf{{{labels['summary']}{labels['colon']}}} "
                 f"{escape_latex(header['summary'])}\n\n\\vspace{{2pt}}\n")
    return text


def render_experiences(doc: dict) -> str:
    entries = []
    for entry in doc["experiences"]:
        title = " — ".join(escape_latex(part) for part in (entry["title"], entry.get("organization")) if part)
        left = f"\\textbf{{{title}}}"
        if entry.get("context"):
            left += f" \\textnormal{{({escape_latex(entry['context'])})}}"
        entries.append(_entry(left, _place_and_dates(entry), entry.get("bullets") or []))
    return _section(doc, "experience", "EXPERIENCE", entries)


def render_education(doc: dict) -> str:
    entries = [
        _entry(f"\\textbf{{{escape_latex(entry['institution'])}}}", _place_and_dates(entry), entry.get("bullets") or [])
        for entry in doc["education"]
    ]
    return _section(doc, "education", "EDUCATION", entries)


def render_projects(doc: dict) -> str:
    entries = []
    for entry in doc["projects"]:
        link = entry.get("link")
        right = f"\\footnotesize\\href{{{latex_url(link['url'])}}}{{{escape_latex(link['label'])}}}" if link else ""
        entries.append(_entry(f"\\textbf{{{escape_latex(entry['name'])}}}", right, entry.get("bullets") or []))
    return _section(doc, "projects", "PROJECTS", entries)


def render_skills(doc: dict) -> str:
    labels = LABELS[doc["language"]]
    rows = [(group["label"], ", ".join(escape_latex(item) for item in group["items"])) for group in doc["skills"]]
    if doc["languages"]:
        spoken = ", ".join(
            escape_latex(lang["name"]) + (f" ({escape_latex(lang['level'])})" if lang.get("level") else "")
            for lang in doc["languages"]
        )
        rows.append((None, spoken))
    if not rows:
        return _section(doc, "technical-skills", "TECHNICAL SKILLS", [])

    lines = []
    for label, items in rows:
        title = labels["languages"] if label is None else escape_latex(label)
        lines.append(f"    \\textbf{{{title}{labels['colon']}}} & {items} \\\\")
    table = "\\begin{tabularx}{\\textwidth}{@{}l@{\\hspace{6pt}}X@{}}\n" + "\n".join(lines) + "\n\\end{tabularx}\n"
    return _section(doc, "technical-skills", "TECHNICAL SKILLS", [table])


def render_interests(doc: dict) -> str:
    if not doc["interests"]:
        return _section(doc, "interests", "INTERESTS", [])
    line = " \\textbullet\\ ".join(escape_latex(interest) for interest in doc["interests"]) + "\n"
    return _section(doc, "interests", "INTERESTS", [line])


def _section(doc: dict, name: str, banner: str, blocks: list) -> str:
    """Une section vide n'est pas affichée (ni son titre) : le fichier ne contient qu'un commentaire."""
    if not blocks:
        return _banner(banner) + "% (section vide : non affichée)\n"
    title = LABELS[doc["language"]][name]
    return _banner(banner) + f"\\section*{{{title}}}\n\n" + "\n".join(blocks)


def render_sections(doc: dict) -> dict[str, str]:
    """Les six fichiers de section du template, à partir du CV structuré."""
    return {
        "heading": render_heading(doc),
        "experience": render_experiences(doc),
        "education": render_education(doc),
        "projects": render_projects(doc),
        "technical-skills": render_skills(doc),
        "interests": render_interests(doc),
    }

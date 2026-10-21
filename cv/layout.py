"""
Zones cliquables du PDF, calculées à partir des marqueurs invisibles \\cvanchor{clé}.

Pendant la compilation, pdfTeX note dans build/<nom>.cvpos la page et la position de chaque
marqueur (voir cv/template/main.tex et cv/render.py), ainsi que les dimensions de la page et
de la zone de texte. read_layout() en déduit une zone par section et par élément :

    {"key": "experiences/0", "level": "item", "json": ["experiences", 0],
     "page": 1, "top": 0.163, "bottom": 0.251, "left": 0.073, "right": 0.927}

Coordonnées normalisées de 0 à 1, origine en haut à gauche de la page (indépendantes du zoom).
Les sections sont empilées dans le template : une section s'étend de son marqueur jusqu'au
marqueur suivant de même niveau, sur toute la largeur du texte ; idem pour les éléments à
l'intérieur de leur section. Une zone coupée par un saut de page donne une zone par page.
Une zone d'élément est prioritaire sur celle de sa section (region_at).
"""

import json
import math
from pathlib import Path


LAYOUT_FILE = "layout.json"
LAYOUT_VERSION = 1

# Clé de zone -> clé(s) du CV structuré (cv.json) modifiées par le panneau correspondant
SECTION_JSON = {
    "profile": ["header"], "experiences": ["experiences"], "education": ["education"],
    "projects": ["projects"], "skills": ["skills", "languages"], "interests": ["interests"],
}


class LayoutError(ValueError):
    """Le fichier de positions est absent ou illisible."""


def _pt(value: str) -> float:
    """« 597.50787pt » -> 597.50787 ; un entier (positions pdfTeX) est en sp (1/65536 pt)."""
    value = value.strip()
    return float(value[:-2]) if value.endswith("pt") else int(value) / 65536


def _read_positions(path: Path):
    lines = [line.split(",") for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or lines[0][0] != "page" or len(lines[0]) != 7:
        raise LayoutError(f"« {path} » n'est pas un fichier de positions (\\cvanchor).")
    width, height, left, text_width, text_top, text_height = map(_pt, lines[0][1:])
    page = {"width": width, "height": height, "left": left, "right": left + text_width,
            "text_top": text_top, "text_bottom": text_top + text_height}
    anchors = []
    for fields in lines[1:]:
        key, number, x, y, ascent = fields
        # Haut de la ligne du marqueur, mesuré depuis le haut de la page
        top = height - _pt(y) - (0 if key == "end" else _pt(ascent))
        anchors.append({"key": key, "page": int(number), "top": top})
    return page, anchors


def _pieces(start: dict, end: dict, page: dict) -> list[tuple[int, float, float]]:
    """(page, haut, bas) en points, de start jusqu'à end, découpé aux sauts de page."""
    pieces = []
    for number in range(start["page"], end["page"] + 1):
        top = start["top"] if number == start["page"] else page["text_top"]
        bottom = end["top"] if number == end["page"] else page["text_bottom"]
        if bottom - top > 0.5:                       # rien de visible en dessous d'un demi-point
            pieces.append((number, top, bottom))
    return pieces


def _region(key: str, level: str, piece: tuple, page: dict) -> dict:
    number, top, bottom = piece
    section, _, index = key.partition("/")
    return {
        "key": key,
        "level": level,
        "json": [SECTION_JSON[section][0], int(index)] if index else SECTION_JSON[section],
        "page": number,
        "top": round(max(0.0, top / page["height"]), 4),
        "bottom": round(min(1.0, bottom / page["height"]), 4),
        # Arrondis vers l'extérieur : la zone ne rogne jamais le texte qui commence sur la marge
        "left": math.floor(page["left"] / page["width"] * 10000) / 10000,
        "right": math.ceil(page["right"] / page["width"] * 10000) / 10000,
    }


def read_layout(positions_file: Path, pages: int | None = None) -> dict:
    """Zones cliquables à partir du fichier .cvpos d'une compilation. Lève LayoutError s'il est illisible."""
    page, anchors = _read_positions(positions_file)
    known = [a for a in anchors if a["key"] == "end" or a["key"].partition("/")[0] in SECTION_JSON]
    end = next((a for a in known if a["key"] == "end"), None)
    if end is None:
        raise LayoutError(f"« {positions_file} » est incomplet (marqueur de fin absent).")
    sections = [a for a in known if "/" not in a["key"] and a["key"] != "end"]

    regions = []
    for n, section in enumerate(sections):
        section_end = sections[n + 1] if n + 1 < len(sections) else end
        regions += [_region(section["key"], "section", piece, page) for piece in _pieces(section, section_end, page)]

        items = [a for a in known if a["key"].startswith(section["key"] + "/")]
        for m, item in enumerate(items):
            item_end = items[m + 1] if m + 1 < len(items) else section_end
            regions += [_region(item["key"], "item", piece, page) for piece in _pieces(item, item_end, page)]

    return {
        "version": LAYOUT_VERSION,
        "pages": pages if pages is not None else end["page"],
        "page_size_pt": {"width": round(page["width"], 2), "height": round(page["height"], 2)},
        "regions": regions,
    }


def region_at(layout: dict, page: int, x: float, y: float) -> dict | None:
    """
    La zone sous un clic (coordonnées normalisées). Un élément l'emporte sur sa section ;
    None si le clic tombe en dehors de toute zone (marges, espace entre deux pages...).
    """
    hits = [r for r in layout["regions"]
            if r["page"] == page and r["left"] <= x <= r["right"] and r["top"] <= y < r["bottom"]]
    return min(hits, key=lambda r: r["level"] != "item", default=None)


def write_layout(build_dir: Path, pdf: Path, pages: int) -> Path | None:
    """
    Écrit build/layout.json à partir du .cvpos de la compilation qui vient de produire `pdf`.
    Rien si le CV n'a pas de marqueurs (CV créés avant) ou si les positions ne viennent pas de
    cette compilation. Renvoie le chemin écrit ou None.
    """
    positions = pdf.with_suffix(".cvpos")
    if not positions.exists() or positions.stat().st_mtime < pdf.stat().st_mtime - 5:
        return None
    layout = read_layout(positions, pages)
    layout["pdf"] = pdf.name
    path = Path(build_dir) / LAYOUT_FILE
    path.write_text(json.dumps(layout, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path

import sys
import re
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import (
    sync_playwright,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)


def normalize_job_url(url: str) -> str:
    """
    Les pages de recherche LinkedIn (jobs/search-results, jobs/search, jobs/collections...)
    exigent d'être connecté. L'offre sélectionnée y est donnée par currentJobId :
    on la remplace par sa page directe, lisible sans connexion.
    """

    parsed = urlparse(url.strip())

    if "linkedin.com" in parsed.netloc:
        job_id = parse_qs(parsed.query).get("currentJobId", [None])[0]
        if job_id and job_id.isdigit():
            return f"https://www.linkedin.com/jobs/view/{job_id}"

    return url.strip()


def clean_text(text: str) -> str:
    """
    Nettoyage léger seulement.
    On enlève surtout les lignes vides,
    espaces inutiles et répétitions simples.
    """

    lines = text.splitlines()

    cleaned_lines = []
    previous_line = None

    for line in lines:
        line = line.strip()

        # supprimer lignes vides
        if not line:
            continue

        # supprimer espaces multiples
        line = re.sub(r"\s+", " ", line)

        # éviter répétitions immédiates
        if line == previous_line:
            continue

        cleaned_lines.append(line)
        previous_line = line

    return "\n".join(cleaned_lines)


def read_job(url: str) -> dict:

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)

        page = browser.new_page()

        # Avec le navigateur visible, la première navigation est parfois
        # annulée (net::ERR_ABORTED) : on réessaie une fois.
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # La plupart des sites d'offres chargent le contenu en JavaScript :
        # on attend que le réseau se calme, sans bloquer si le site ne s'arrête jamais.
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass

        title = page.title()

        raw_text = page.locator("body").inner_text()

        cleaned_text = clean_text(raw_text)

        browser.close()

        return {
            "url": url,
            "title": title,
            "text": cleaned_text
        }


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("Usage: python browser/read_job.py <URL>")
        sys.exit(1)

    url = sys.argv[1]

    job = read_job(url)

    print("\n===== TITLE =====\n")
    print(job["title"])

    print("\n===== CLEANED TEXT =====\n")
    print(job["text"])

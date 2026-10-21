import sys
import re
from urllib.parse import parse_qs, urljoin, urlparse
from playwright.sync_api import (
    sync_playwright,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)

from jobs.url_check import PublicUrlGuard


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


# Redirections suivies au plus (au-delà : lecture refusée)
MAX_REDIRECTS = 5
# Inutiles pour lire le texte d'une offre : non chargés (moins de requêtes à contrôler)
SKIPPED_RESOURCES = {"image", "media", "font"}

# Connexions qui ne passent pas par le contrôle des requêtes (et inutiles pour lire une offre) :
# rendues indisponibles dans chaque page avant ses propres scripts
DISABLE_DIRECT_CONNECTIONS = """
for (const name of ["WebSocket", "WebTransport", "RTCPeerConnection", "webkitRTCPeerConnection"]) {
  try { Object.defineProperty(window, name, {value: undefined, writable: false, configurable: false}); } catch (e) {}
}
"""


class UnsafeNavigationError(RuntimeError):
    """La page de l'offre mène vers une adresse locale ou interne : lecture refusée."""


BLOCKED_MESSAGE = "La page de l'offre mène vers une adresse locale ou interne : lecture refusée."


class _NavigationGuard:
    """
    Contrôle de chaque requête du navigateur. Une requête vers une adresse non publique est
    bloquée. Les redirections ne sont jamais suivies par le navigateur lui-même (il ne repasserait
    pas par ce contrôle) : chaque étape est récupérée sans redirection et vérifiée.
    - page principale : la redirection est interrompue et read_job() navigue vers la nouvelle
      adresse, qui repasse par ce contrôle ;
    - autres requêtes (scripts, styles, cadres, fetch) : redirections suivies ici, étape par étape.
    """

    def __init__(self, is_allowed):
        self.is_allowed = is_allowed
        self.page = None
        self.redirect_to = None
        self.blocked = False

    def _is_main(self, request) -> bool:
        return request.is_navigation_request() and self.page is not None and request.frame == self.page.main_frame

    def handle(self, route, request) -> None:
        url = request.url
        if url.startswith(("data:", "blob:", "about:")):           # pas de réseau
            route.continue_()
            return
        main = self._is_main(request)
        if not self.is_allowed(url):
            self.blocked = self.blocked or main
            route.abort("blockedbyclient")
            return
        if not main and request.resource_type in SKIPPED_RESOURCES:
            route.abort("blockedbyclient")
            return

        current = url
        for _ in range(MAX_REDIRECTS + 1):
            try:
                response = route.fetch(url=current, max_redirects=0)
            except PlaywrightError:
                route.abort("failed")
                return
            location = response.headers.get("location")
            if not (300 <= response.status < 400 and location):
                route.fulfill(response=response)
                return
            current = urljoin(current, location)
            if not self.is_allowed(current):
                self.blocked = self.blocked or main
                route.abort("blockedbyclient")
                return
            if main:                                               # read_job() suit la redirection
                self.redirect_to = current
                route.abort("blockedbyclient")
                return
        route.abort("failed")                                      # trop de redirections


def read_job(url: str, headless: bool = False, is_allowed=None) -> dict:
    """
    Ouvre la page de l'offre et renvoie {url, title, text}. Seules les adresses web publiques
    sont chargées (is_allowed, par défaut jobs.url_check.PublicUrlGuard), redirections comprises.
    Lève UnsafeNavigationError si la page mène vers une adresse locale ou interne.
    """

    guard = _NavigationGuard(is_allowed or PublicUrlGuard().allows)

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=headless)

        # Les service workers échapperaient au contrôle des requêtes
        context = browser.new_context(service_workers="block")
        context.route("**/*", guard.handle)
        context.add_init_script(DISABLE_DIRECT_CONNECTIONS)

        page = context.new_page()
        guard.page = page

        target, retries = url, 0
        for _ in range(MAX_REDIRECTS + 3):
            guard.redirect_to = None
            try:
                page.goto(target, wait_until="domcontentloaded", timeout=60000)
                break
            except PlaywrightError as error:
                if guard.blocked:
                    browser.close()
                    raise UnsafeNavigationError(BLOCKED_MESSAGE)
                if guard.redirect_to:
                    target = guard.redirect_to
                    continue
                # Avec le navigateur visible, la première navigation est parfois annulée (net::ERR_ABORTED),
                # et après une redirection interrompue la page d'erreur du navigateur peut gêner la suivante :
                # on réessaie (deux fois au plus).
                if retries == 2:
                    raise
                retries += 1
                if "interrupted by another navigation" in str(error):
                    page.wait_for_timeout(200)
        else:
            browser.close()
            raise UnsafeNavigationError("La page de l'offre redirige trop de fois : lecture refusée.")

        # La plupart des sites d'offres chargent le contenu en JavaScript :
        # on attend que le réseau se calme, sans bloquer si le site ne s'arrête jamais.
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PlaywrightTimeoutError:
            pass

        # La page a essayé de partir vers une adresse interne (redirection JavaScript...) : refusé
        if guard.blocked:
            browser.close()
            raise UnsafeNavigationError(BLOCKED_MESSAGE)

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
        print("Usage: python -m jobs.read_job <URL>")
        sys.exit(1)

    url = sys.argv[1]

    job = read_job(url)

    print("\n===== TITLE =====\n")
    print(job["title"])

    print("\n===== CLEANED TEXT =====\n")
    print(job["text"])

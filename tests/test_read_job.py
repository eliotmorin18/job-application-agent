"""
Tests de la lecture sécurisée des offres (jobs/read_job.py) : redirections et requêtes vers des
adresses locales ou internes, avec Playwright simulé (aucun navigateur, aucun réseau, aucun appel
à Claude). Le filtre réel des adresses (jobs/url_check.PublicUrlGuard) utilise une fausse
résolution DNS.

Lancement :  python -m unittest discover tests
"""

import socket
import unittest
from unittest import mock
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError

from jobs import read_job as read_job_module
from jobs.read_job import MAX_REDIRECTS, UnsafeNavigationError, _NavigationGuard, read_job
from jobs.url_check import PublicUrlGuard


ADDRESSES = {"jobs.example.com": "93.184.216.34", "cdn.example.com": "93.184.216.35",
             "evil.example.com": "10.0.0.5", "rebind.example.com": "127.0.0.1"}


def fake_resolve(host, port, proto=0):
    if host not in ADDRESSES:
        raise socket.gaierror("introuvable")
    return [(0, 0, 0, "", (ADDRESSES[host], port or 443))]


class FakeResponse:
    def __init__(self, status=200, location=None):
        self.status = status
        self.headers = {"location": location} if location else {}


class FakeRoute:
    """Réponses par URL : (statut, Location). Enregistre ce que le contrôle a fait."""

    def __init__(self, responses):
        self.responses = responses
        self.fetched, self.outcome = [], None

    def fetch(self, url, max_redirects):
        assert max_redirects == 0, "le navigateur ne doit jamais suivre une redirection lui-même"
        self.fetched.append(url)
        status, location = self.responses.get(url, (200, None))
        if status == "error":
            raise PlaywrightError("réseau")
        return FakeResponse(status, location)

    def fulfill(self, response):
        self.outcome = ("fulfill", response.status)

    def abort(self, reason="failed"):
        self.outcome = ("abort", reason)

    def continue_(self):
        self.outcome = ("continue", None)


class FakeRequest:
    def __init__(self, url, frame="main", navigation=False, resource_type="document"):
        self.url, self.frame, self.resource_type = url, frame, resource_type
        self._navigation = navigation

    def is_navigation_request(self):
        return self._navigation


class FakePage:
    main_frame = "main"


class GuardTest(unittest.TestCase):

    def setUp(self):
        self.guard = _NavigationGuard(PublicUrlGuard(resolve=fake_resolve).allows)
        self.guard.page = FakePage()

    def run_request(self, url, responses=None, **request):
        route = FakeRoute(responses or {})
        self.guard.handle(route, FakeRequest(url, **request))
        return route

    def test_public_page_is_loaded_without_letting_the_browser_redirect(self):
        route = self.run_request("https://jobs.example.com/offre", navigation=True)
        self.assertEqual(route.outcome, ("fulfill", 200))
        self.assertEqual(route.fetched, ["https://jobs.example.com/offre"])
        self.assertFalse(self.guard.blocked)

    def test_main_page_redirect_is_handed_back_to_read_job(self):
        route = self.run_request("https://jobs.example.com/a", {"https://jobs.example.com/a": (301, "/b")}, navigation=True)
        self.assertEqual(route.outcome, ("abort", "blockedbyclient"))
        self.assertEqual(self.guard.redirect_to, "https://jobs.example.com/b")    # repasse par le contrôle
        self.assertFalse(self.guard.blocked)

    def test_main_page_redirect_to_internal_address_is_blocked(self):
        for location in ("http://127.0.0.1:8000/api/profile", "http://localhost/", "http://169.254.169.254/latest",
                         "http://192.168.1.1/", "http://[::1]/", "https://evil.example.com/", "file:///etc/passwd"):
            with self.subTest(location):
                self.guard.blocked, self.guard.redirect_to = False, None
                route = self.run_request("https://jobs.example.com/a", {"https://jobs.example.com/a": (302, location)},
                                         navigation=True)
                self.assertEqual(route.outcome, ("abort", "blockedbyclient"))
                self.assertTrue(self.guard.blocked)
                self.assertIsNone(self.guard.redirect_to)

    def test_internal_requests_are_blocked_before_any_network(self):
        for url in ("http://localhost:8000/api/profile", "http://10.0.0.1/", "https://rebind.example.com/x",
                    "http://intranet/", "https://user:pw@jobs.example.com/"):
            with self.subTest(url):
                route = self.run_request(url, resource_type="fetch")
                self.assertEqual(route.outcome, ("abort", "blockedbyclient"))
                self.assertEqual(route.fetched, [])                                   # rien n'est envoyé
        self.assertFalse(self.guard.blocked)                                          # secondaire : la page continue

    def test_secondary_redirects_are_followed_and_checked_step_by_step(self):
        public = {"https://cdn.example.com/app.js": (302, "https://cdn.example.com/v2/app.js"),
                  "https://cdn.example.com/v2/app.js": (200, None)}
        route = self.run_request("https://cdn.example.com/app.js", public, resource_type="script")
        self.assertEqual(route.outcome, ("fulfill", 200))
        self.assertEqual(route.fetched, ["https://cdn.example.com/app.js", "https://cdn.example.com/v2/app.js"])

        internal = {"https://cdn.example.com/app.js": (302, "https://cdn.example.com/x"),
                    "https://cdn.example.com/x": (307, "http://10.0.0.7/admin")}
        route = self.run_request("https://cdn.example.com/app.js", internal, resource_type="script")
        self.assertEqual(route.outcome, ("abort", "blockedbyclient"))
        self.assertNotIn("http://10.0.0.7/admin", route.fetched)

    def test_subframes_are_treated_like_secondary_requests(self):
        responses = {"https://jobs.example.com/frame": (302, "http://127.0.0.1/")}
        route = self.run_request("https://jobs.example.com/frame", responses, frame="iframe", navigation=True)
        self.assertEqual(route.outcome, ("abort", "blockedbyclient"))
        self.assertFalse(self.guard.blocked)

    def test_redirect_loops_and_network_errors(self):
        loop = {"https://cdn.example.com/l": (302, "https://cdn.example.com/l")}
        route = self.run_request("https://cdn.example.com/l", loop, resource_type="stylesheet")
        self.assertEqual(route.outcome, ("abort", "failed"))
        self.assertEqual(len(route.fetched), MAX_REDIRECTS + 1)
        route = self.run_request("https://cdn.example.com/down", {"https://cdn.example.com/down": ("error", None)},
                                 resource_type="script")
        self.assertEqual(route.outcome, ("abort", "failed"))

    def test_images_fonts_and_media_are_not_loaded(self):
        for kind in ("image", "font", "media"):
            route = self.run_request("https://cdn.example.com/x", resource_type=kind)
            self.assertEqual(route.outcome, ("abort", "blockedbyclient"))
            self.assertEqual(route.fetched, [])
        self.assertEqual(self.run_request("https://cdn.example.com/s.css", resource_type="stylesheet").outcome,
                         ("fulfill", 200))

    def test_urls_without_network(self):
        self.assertEqual(self.run_request("data:text/plain,x", resource_type="fetch").outcome, ("continue", None))
        self.assertEqual(self.run_request("blob:https://jobs.example.com/1", resource_type="fetch").outcome,
                         ("continue", None))

    def test_dns_results_are_cached(self):
        calls = []
        guard = PublicUrlGuard(resolve=lambda *a, **k: calls.append(a[0]) or fake_resolve(*a, **k))
        for _ in range(5):
            self.assertTrue(guard.allows("https://cdn.example.com/x"))
        self.assertEqual(calls, ["cdn.example.com"])


class FakeBrowserPage:
    """Page simulée : chaque goto() passe la requête au contrôle, comme le ferait Chromium."""

    main_frame = "main"

    def __init__(self, guard, responses):
        self.guard, self.responses, self.visited = guard, responses, []

    def goto(self, url, wait_until=None, timeout=None):
        self.visited.append(url)
        route = FakeRoute(self.responses)
        self.guard.handle(route, FakeRequest(url, navigation=True))
        if route.outcome[0] == "abort":
            raise PlaywrightError(f"net::ERR_BLOCKED_BY_CLIENT at {url}")

    def wait_for_load_state(self, state, timeout=None):
        pass

    def title(self):
        return "Offre"

    def locator(self, selector):
        return mock.Mock(inner_text=lambda: f"Texte de {self.visited[-1]}")


class ReadJobTest(unittest.TestCase):

    def read(self, url, responses):
        holder = {}

        def new_context(**options):
            self.assertEqual(options, {"service_workers": "block"})       # ils échapperaient au contrôle
            context = mock.Mock()
            self.last_context = context
            context.route.side_effect = lambda pattern, handler: holder.update(guard=handler.__self__)
            context.new_page.side_effect = lambda: holder.setdefault(
                "page", FakeBrowserPage(holder["guard"], responses))
            return context

        browser = mock.Mock(new_context=new_context)
        playwright = mock.MagicMock()
        playwright.__enter__.return_value.chromium.launch.return_value = browser
        with mock.patch.object(read_job_module, "sync_playwright", return_value=playwright):
            job = read_job(url, is_allowed=PublicUrlGuard(resolve=fake_resolve).allows)
        return job, holder["page"].visited, browser

    def test_redirect_chain_between_public_pages(self):
        job, visited, browser = self.read("https://jobs.example.com/a", {
            "https://jobs.example.com/a": (302, "https://jobs.example.com/b"),
            "https://jobs.example.com/b": (301, "https://cdn.example.com/offre")})
        self.assertEqual(visited, ["https://jobs.example.com/a", "https://jobs.example.com/b",
                                   "https://cdn.example.com/offre"])
        self.assertEqual(job, {"url": "https://jobs.example.com/a", "title": "Offre",
                               "text": "Texte de https://cdn.example.com/offre"})
        browser.close.assert_called_once()

    def test_direct_connections_are_disabled_in_pages(self):
        self.read("https://jobs.example.com/a", {})
        self.last_context.add_init_script.assert_called_once_with(read_job_module.DISABLE_DIRECT_CONNECTIONS)
        for name in ("WebSocket", "WebTransport", "RTCPeerConnection"):
            self.assertIn(name, read_job_module.DISABLE_DIRECT_CONNECTIONS)

    def test_redirect_to_an_internal_address_stops_the_reading(self):
        with self.assertRaises(UnsafeNavigationError) as context:
            self.read("https://jobs.example.com/a", {
                "https://jobs.example.com/a": (302, "https://jobs.example.com/b"),
                "https://jobs.example.com/b": (302, "http://192.168.0.10/admin")})
        message = str(context.exception)
        self.assertIn("adresse locale ou interne", message)
        self.assertNotIn("192.168", message)                                       # pas d'adresse interne divulguée

    def test_internal_start_page_and_too_many_redirects(self):
        with self.assertRaises(UnsafeNavigationError):
            self.read("http://127.0.0.1:8000/api/profile", {})
        loop = {f"https://jobs.example.com/{n}": (302, f"https://jobs.example.com/{n + 1}") for n in range(20)}
        with self.assertRaises(UnsafeNavigationError) as context:
            self.read("https://jobs.example.com/0", loop)
        self.assertIn("trop de fois", str(context.exception))


if __name__ == "__main__":
    unittest.main()

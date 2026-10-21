"""
Vérification avec un vrai navigateur (Chromium sans fenêtre) et deux serveurs locaux :
« A » joue un site public, « B » une adresse interne qui ne doit jamais être contactée.
Lancé seulement sur demande (plus lent) : RUN_BROWSER_TESTS=1 python -m unittest tests.test_read_job_browser
Aucun accès à Internet, aucun appel à Claude.
"""

import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from jobs.read_job import UnsafeNavigationError, read_job


@unittest.skipUnless(os.environ.get("RUN_BROWSER_TESTS") == "1", "RUN_BROWSER_TESTS=1 pour lancer les tests navigateur")
class RealBrowserTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.hits = []
        servers = []
        for role in ("public", "internal"):
            server = ThreadingHTTPServer(("127.0.0.1", 0), cls._handler(role))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            servers.append(server)
        cls.servers = servers
        cls.a = f"127.0.0.1:{servers[0].server_port}"
        cls.b = f"localhost:{servers[1].server_port}"            # autre nom : interdit par le filtre du test

    @classmethod
    def tearDownClass(cls):
        for server in cls.servers:
            server.shutdown()
            server.server_close()

    @classmethod
    def _handler(cls, role):
        test = cls

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if role == "internal":
                    test.hits.append(self.path)
                    status, headers, body = 200, {}, "SECRET"
                else:
                    status, headers, body = test._public(self.path)
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body.encode())
        return Handler

    @classmethod
    def _public(cls, path):
        b = cls.b
        page = (f'<html><head><title>Offre A</title><link rel="stylesheet" href="/css"></head><body>Offre publique'
                f'<img src="http://{b}/img"><iframe src="/frame"></iframe><script src="/script"></script>'
                f'<script>fetch("http://{b}/api").catch(()=>{{}}); fetch("/fetch").catch(()=>{{}});'
                f'try {{ new WebSocket("ws://{b}/ws") }} catch (e) {{}}</script></body></html>')
        redirects = {"/redirect": f"http://{b}/secret", "/chain": "/chain2", "/chain2": "/redirect",
                     "/ok": "/ok2", "/ok2": "/page", "/loop": "/loop", "/css": f"http://{b}/css",
                     "/frame": f"http://{b}/frame", "/script": f"http://{b}/js", "/fetch": f"http://{b}/fetch"}
        if path in redirects:
            return 302, {"Location": redirects[path]}, ""
        if path == "/page":
            return 200, {"Content-Type": "text/html"}, page
        if path == "/jsnav":
            return 200, {"Content-Type": "text/html"}, f'<html><body>x<script>location="http://{b}/js"</script></body></html>'
        return 404, {}, ""

    def read(self, path):
        url = path if path.startswith("http") else f"http://{self.a}{path}"
        return read_job(url, headless=True, is_allowed=lambda u: urlsplit(u).netloc == self.a)

    def test_public_pages_are_read(self):
        for path in ("/page", "/ok"):
            with self.subTest(path):
                job = self.read(path)
                self.assertEqual(job["title"], "Offre A")
                self.assertIn("Offre publique", job["text"])
        self.assertEqual(self.hits, [])

    def test_internal_destinations_are_never_contacted(self):
        for path in ("/redirect", "/chain", "/loop", "/jsnav", f"http://{self.b}/direct"):
            with self.subTest(path):
                with self.assertRaises(UnsafeNavigationError):
                    self.read(path)
        self.assertEqual(self.hits, [])


if __name__ == "__main__":
    unittest.main()

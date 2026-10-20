"""
Ouvre le Chrome de l'agent (profil browser/session/) sur une page de connexion,
pour s'y connecter une fois : la session est ensuite gardée sur le disque.

Usage :  python -m browser.login            (LinkedIn par défaut)
         python -m browser.login "<URL>"    (n'importe quel autre site)
"""

import sys

from playwright.sync_api import sync_playwright

from browser.apply_agent import _open_chrome


DEFAULT_URL = "https://www.linkedin.com/login"


if __name__ == "__main__":

    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    with sync_playwright() as p:
        browser = _open_chrome(p)
        page = browser.contexts[0].new_page()
        page.goto(url)
        page.bring_to_front()
        # On se déconnecte de Chrome sans le fermer : la fenêtre reste ouverte

    print("Connecte-toi dans la fenêtre Chrome qui vient de s'ouvrir.")
    print("Une fois connecté, tu peux fermer la fenêtre : la connexion est gardée dans browser/session/.")

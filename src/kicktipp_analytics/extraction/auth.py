"""
Übernimmt ausschließlich den Login-Vorgang über Playwright - getrennt von
der eigentlichen Extraktionslogik (Single Responsibility), damit
Authentifizierung unabhängig geändert/getestet werden kann (z.B. falls
Kicktipp 2FA einführt oder die Login-Maske ändert).

WICHTIG: Die CSS-Selektoren unten sind aus der öffentlich einsehbaren
Struktur von Kicktipp-Login-Formularen abgeleitet, aber NICHT gegen die
echte Seite verifiziert - von dieser Sandbox aus ist kein Netzwerkzugriff
auf kicktipp.de möglich (Netzwerk-Whitelist). Vor dem ersten produktiven
Lauf bitte gegen die echte Login-Seite prüfen und ggf. anpassen.
"""
from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Page


@dataclass(frozen=True, slots=True)
class KicktippCredentials:
    username: str
    password: str
    #: z.B. "https://www.kicktipp.de/eure-wm-runde/" (mit abschließendem Slash)
    community_url: str


class KicktippAuthenticator:
    LOGIN_URL = "https://www.kicktipp.de/info/profil/login"

    # Zentrale Stelle für die Login-Selektoren - bei Änderungen an der
    # Kicktipp-Seite muss im Idealfall nur hier etwas angepasst werden.
    USERNAME_SELECTOR = "#kennung"
    PASSWORD_SELECTOR = "#passwort"
    SUBMIT_SELECTOR = "button[type=submit]"

    def __init__(self, credentials: KicktippCredentials):
        self._credentials = credentials

    def login(self, page: Page) -> None:
        page.goto(self.LOGIN_URL)
        page.fill(self.USERNAME_SELECTOR, self._credentials.username)
        page.fill(self.PASSWORD_SELECTOR, self._credentials.password)
        page.click(self.SUBMIT_SELECTOR)
        page.wait_for_load_state("networkidle")

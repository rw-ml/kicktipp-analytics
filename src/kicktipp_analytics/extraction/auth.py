"""
Übernimmt ausschließlich den Login-Vorgang über Playwright - getrennt von
der eigentlichen Extraktionslogik (Single Responsibility), damit
Authentifizierung unabhängig geändert/getestet werden kann (z.B. falls
Kicktipp 2FA einführt oder die Login-Maske ändert).

Die Selektoren unten sind gegen die echte Kicktipp-Loginseite verifiziert
(via web_fetch der öffentlichen Login-Seite sowie Abgleich mit zwei aktiv
gepflegten Open-Source-Kicktipp-Bots: antonengelhardt/kicktipp-bot und
christianheidorn/kicktipp-agent, beide bestätigen unabhängig voneinander
dieselben Feldnamen). Stand: Juni 2026. Nicht verifiziert werden konnte von
hier aus ausschließlich das tatsächliche Cookie-Consent-Layout für die
deutsche Seite (https://www.kicktipp.de) - die XPath-Variante unten ist von
antonengelhardt/kicktipp-bot übernommen, sollte aber beim ersten echten Lauf
gegenkontrolliert werden.
"""
from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Page


class AuthenticationError(Exception):
    """Wird ausgelöst, wenn der Login fehlschlägt (falsche Zugangsdaten,
    geändertes Seitenlayout, o.ä.)."""


@dataclass(frozen=True, slots=True)
class KicktippCredentials:
    username: str
    password: str
    #: z.B. "https://www.kicktipp.de/eure-wm-runde/" (mit abschließendem Slash)
    community_url: str


class KicktippAuthenticator:
    #: Login ist global, NICHT pro Community - ein Kicktipp-Account deckt
    #: alle Tipprunden ab. Verifiziert über zwei unabhängige, aktiv
    #: gepflegte Open-Source-Projekte, die exakt diese URL produktiv nutzen.
    LOGIN_URL = "https://www.kicktipp.de/info/profil/login"

    # Zentrale Stelle für die Login-Selektoren - bei Änderungen an der
    # Kicktipp-Seite muss im Idealfall nur hier etwas angepasst werden.
    USERNAME_SELECTOR = "#kennung"
    PASSWORD_SELECTOR = "#passwort"
    #: Verifiziert: der Button trägt sowohl name="submitbutton" als auch
    #: type="submit" - wir nutzen den spezifischeren Namen-Selektor.
    SUBMIT_SELECTOR = "button[name='submitbutton']"

    #: Quantcast/Consent-Management-Dialog, der bei manchen Seitenaufrufen
    #: vor dem eigentlichen Inhalt erscheint. Timeout bewusst kurz, da der
    #: Dialog oft gar nicht auftaucht (z.B. bei wiederkehrenden Sessions).
    COOKIE_CONSENT_SELECTOR = "#qc-cmp2-ui button"
    COOKIE_CONSENT_TIMEOUT_MS = 4000

    def __init__(self, credentials: KicktippCredentials):
        self._credentials = credentials

    def login(self, page: Page) -> None:
        page.goto(self.LOGIN_URL)
        self._dismiss_cookie_consent_if_present(page)

        page.fill(self.USERNAME_SELECTOR, self._credentials.username)
        page.fill(self.PASSWORD_SELECTOR, self._credentials.password)
        page.click(self.SUBMIT_SELECTOR)
        page.wait_for_load_state("networkidle")

        if "/profil/login" in page.url:
            raise AuthenticationError(
                "Login fehlgeschlagen - Seite zeigt weiterhin das Login-Formular. "
                "Zugangsdaten prüfen oder Seitenlayout hat sich geändert."
            )

    def _dismiss_cookie_consent_if_present(self, page: Page) -> None:
        try:
            page.click(self.COOKIE_CONSENT_SELECTOR, timeout=self.COOKIE_CONSENT_TIMEOUT_MS)
        except Exception:
            # Dialog nicht aufgetaucht (z.B. bereits zuvor akzeptiert) -
            # das ist der Normalfall bei wiederverwendeten Sessions, kein Fehler.
            pass
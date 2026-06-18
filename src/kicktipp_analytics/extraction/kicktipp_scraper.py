"""
Konkrete IKicktippDataSource-Implementierung auf Basis von Playwright.

================================================================================
WICHTIGER HINWEIS - BITTE VOR DEM ERSTEN LAUF LESEN
================================================================================
Kicktipp bietet keine offizielle API. Diese Klasse liest die Daten von den
HTML-Seiten der Community ab. Aus dieser Entwicklungsumgebung heraus besteht
KEIN Netzwerkzugriff auf kicktipp.de (Netzwerk-Whitelist) - die unten
verwendeten URLs und CSS-Selektoren sind daher ein fachlich sinnvoller,
aber NICHT gegen die echte Seite verifizierter Entwurf.

Vor dem produktiven Einsatz bitte:
  1. Mit echten Zugangsdaten einmal `headless=False` laufen lassen und die
     tatsächlichen Tabellen/Selektoren in `KicktippSelectors` abgleichen.
  2. Insbesondere die URL-Pfade für Tippübersicht/Spielplan/Tabelle prüfen -
     diese können sich je nach Kicktipp-Liga-Konfiguration unterscheiden.

Alle Selektoren sind bewusst in einer einzigen Klasse (`KicktippSelectors`)
zentralisiert, damit bei Änderungen am Kicktipp-HTML im Idealfall nur diese
eine Stelle angepasst werden muss - die restliche Scraping- und
Pipeline-Logik bleibt unberührt.
================================================================================
"""
from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from playwright.sync_api import Page, sync_playwright

from kicktipp_analytics.domain.models import (
    Match,
    MatchResult,
    Matchday,
    MatchType,
    Player,
    ScoreResult,
    Team,
    Tip,
)
from kicktipp_analytics.extraction.auth import KicktippAuthenticator, KicktippCredentials
from kicktipp_analytics.extraction.interfaces import IKicktippDataSource


class KicktippSelectors:
    """Zentrale, anpassbare Stelle für alle Pfade/Selektoren. TODO: gegen echte Seite prüfen."""

    TABELLE_PATH = "tabellen"
    SPIELPLAN_PATH = "spieltagtabelle"
    TIPPABGABE_PATH = "tippabgabe?tag={matchday}"

    TABELLE_ROW_SELECTOR = "table.tabelle tbody tr"
    SPIELPLAN_ROW_SELECTOR = "table.spieltagtabelle tbody tr"
    TIPPABGABE_ROW_SELECTOR = "table.tippabgabeUebersicht tbody tr"


SCORE_PATTERN = re.compile(r"(\d+)\s*:\s*(\d+)")


class KicktippScraper(IKicktippDataSource):
    def __init__(
        self,
        credentials: KicktippCredentials,
        headless: bool = True,
        selectors: KicktippSelectors | None = None,
    ):
        self._credentials = credentials
        self._authenticator = KicktippAuthenticator(credentials)
        self._headless = headless
        self._selectors = selectors or KicktippSelectors()

    @contextmanager
    def _page(self) -> Iterator[Page]:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self._headless)
            context = browser.new_context()
            page = context.new_page()
            self._authenticator.login(page)
            try:
                yield page
            finally:
                context.close()
                browser.close()

    def get_players(self) -> list[Player]:
        with self._page() as page:
            page.goto(self._url(self._selectors.TABELLE_PATH))
            rows = page.locator(self._selectors.TABELLE_ROW_SELECTOR)
            players: list[Player] = []
            for i in range(rows.count()):
                row = rows.nth(i)
                name = row.locator("td").nth(1).inner_text().strip()
                if not name:
                    continue
                player_id = _slugify(name)
                players.append(Player(id=player_id, display_name=name))
            return players

    def get_matches(self, season: str) -> list[Match]:
        with self._page() as page:
            page.goto(self._url(self._selectors.SPIELPLAN_PATH))
            rows = page.locator(self._selectors.SPIELPLAN_ROW_SELECTOR)
            matches: list[Match] = []
            for i in range(rows.count()):
                row = rows.nth(i)
                cells = row.locator("td")
                matchday_number = int(cells.nth(0).inner_text().strip() or 0)
                home_name = cells.nth(2).inner_text().strip()
                away_name = cells.nth(3).inner_text().strip()
                kickoff_text = cells.nth(1).inner_text().strip()

                matches.append(
                    Match(
                        id=f"{season}-{_slugify(home_name)}-{_slugify(away_name)}",
                        matchday=Matchday(number=matchday_number, season=season),
                        home_team=Team(id=_slugify(home_name), name=home_name),
                        away_team=Team(id=_slugify(away_name), name=away_name),
                        kickoff=_parse_kickoff(kickoff_text),
                        # TODO: K.o.-Phase anhand der echten Spieltag-/Rundenbezeichnung
                        # erkennen (z.B. "Achtelfinale", "Halbfinale", "Finale").
                        match_type=MatchType.GROUP,
                    )
                )
            return matches

    def get_results(self, season: str) -> list[MatchResult]:
        # Tatsächliche Ergebnisse stehen i.d.R. auf derselben Spielplan-Seite
        # wie die Begegnungen selbst. Hier getrennt gehalten, damit sich die
        # Pipeline unverändert mit Resultaten "nachfüttern" lässt, sobald sie
        # verfügbar sind (vor Spielbeginn gibt es schlicht noch kein Result).
        with self._page() as page:
            page.goto(self._url(self._selectors.SPIELPLAN_PATH))
            rows = page.locator(self._selectors.SPIELPLAN_ROW_SELECTOR)
            results: list[MatchResult] = []
            for i in range(rows.count()):
                row = rows.nth(i)
                cells = row.locator("td")
                home_name = cells.nth(2).inner_text().strip()
                away_name = cells.nth(3).inner_text().strip()
                score_text = cells.nth(4).inner_text().strip()

                match = SCORE_PATTERN.search(score_text)
                if not match:
                    continue  # Spiel noch nicht gespielt

                match_id = f"{season}-{_slugify(home_name)}-{_slugify(away_name)}"
                results.append(
                    MatchResult(
                        match_id=match_id,
                        score=ScoreResult(int(match.group(1)), int(match.group(2))),
                    )
                )
            return results

    def get_tips(self, season: str) -> list[Tip]:
        tips: list[Tip] = []
        with self._page() as page:
            matchday = 1
            while True:
                page.goto(self._url(self._selectors.TIPPABGABE_PATH.format(matchday=matchday)))
                rows = page.locator(self._selectors.TIPPABGABE_ROW_SELECTOR)
                row_count = rows.count()
                if row_count == 0:
                    break  # keine weiteren Spieltage vorhanden

                for i in range(row_count):
                    row = rows.nth(i)
                    cells = row.locator("td")
                    player_name = cells.nth(0).inner_text().strip()
                    home_name = cells.nth(1).inner_text().strip()
                    away_name = cells.nth(2).inner_text().strip()
                    tip_text = cells.nth(3).inner_text().strip()

                    match_score = SCORE_PATTERN.search(tip_text)
                    if not match_score:
                        continue

                    tips.append(
                        Tip(
                            player_id=_slugify(player_name),
                            match_id=f"{season}-{_slugify(home_name)}-{_slugify(away_name)}",
                            score_tip=ScoreResult(
                                int(match_score.group(1)), int(match_score.group(2))
                            ),
                        )
                    )
                matchday += 1
                if matchday > 64:  # Sicherheitsnetz gegen Endlosschleifen
                    break
        return tips

    def _url(self, path: str) -> str:
        return f"{self._credentials.community_url}{path}"


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _parse_kickoff(text: str) -> datetime:
    # TODO: an das echte Datumsformat der Kicktipp-Spielplanseite anpassen.
    try:
        return datetime.strptime(text, "%d.%m.%Y %H:%M")
    except ValueError:
        return datetime.min

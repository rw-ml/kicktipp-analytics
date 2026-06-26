"""
Konkrete IKicktippDataSource-Implementierung auf Basis von Playwright.

================================================================================
STAND DER VERIFIZIERUNG (Juni 2026) - VOLLSTÄNDIG VERIFIZIERT
================================================================================
Alle URLs, Tabellen-IDs und Selektoren wurden gegen die echte Kicktipp-Seite
verifiziert (Login + Tipp-Zellen-Inspektion mit echten Zugangsdaten).

VERIFIZIERTE SEITENSTRUKTUR:
  - Login: global unter /info/profil/login, Felder #kennung / #passwort,
    Submit via button[name='submitbutton'].
  - Spielplan: Pfad "tippspielplan?spieltagIndex=N", Tabelle "table#spiele",
    Datum in td[0], Heim in td[2], Gast in td[3], Ergebnis in
    span.kicktipp-ergebnis > span.kicktipp-heim / span.kicktipp-gast.
  - Tippübersicht: Pfad "tippuebersicht?spieltagIndex=N&wertung=einzelwertung",
    Tabelle "table#ranking", Spielername in div.mg_name.
  - Tipp-Zellen: CSS-Klasse "ereignis". Struktur:
    <td class="nw t ereignis ereignis0">3:1<sub class="p">3</sub></td>
    Tipp ist direkter Text-Knoten, Punkte-Badge steckt in <sub class="p">.
  - Spieltag-Ende: nicht existierende Spieltage leiten auf den letzten
    bekannten Spieltag um (URL-Check + Fingerprint-Check).
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
from kicktipp_analytics.extraction.interfaces import IKicktippDataSource, ScrapedData


class KicktippSelectors:
    """Zentrale Stelle für alle Pfade/Selektoren - vollständig verifiziert."""

    SPIELPLAN_PATH = "tippspielplan?spieltagIndex={matchday}"
    TIPPUEBERSICHT_PATH = "tippuebersicht?spieltagIndex={matchday}&wertung=einzelwertung"

    SPIELPLAN_ROW_SELECTOR = "table#spiele tbody tr"
    RANKING_ROW_SELECTOR = "table#ranking tbody tr"
    TIPP_CELL_SELECTOR = "td.ereignis"

    RESULT_HOME_SELECTOR = "span.kicktipp-ergebnis span.kicktipp-heim"
    RESULT_AWAY_SELECTOR = "span.kicktipp-ergebnis span.kicktipp-gast"


SCORE_PATTERN = re.compile(r"^\s*(\d+)\s*:\s*(\d+)\s*$")

# Liest nur die direkten Text-Knoten der Zelle (ignoriert <sub class="p">-Badge).
_JS_TIP_TEXT = (
    "el => Array.from(el.childNodes)"
    ".filter(n => n.nodeType === Node.TEXT_NODE)"
    ".map(n => n.textContent)"
    ".join('')"
    ".trim()"
)


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

    # ------------------------------------------------------------------
    # Hauptmethode: eine Browser-Session für alles
    # ------------------------------------------------------------------

    def scrape_all(self, season: str) -> ScrapedData:
        """Scrapt alle Daten in einer einzigen Browser-Session (ein Login)."""
        with self._page() as page:
            players = self._scrape_players(page)
            matches, results = self._scrape_matches_and_results(page, season)
            tips = self._scrape_tips(page, season, matches)
        return ScrapedData(players=players, matches=matches, results=results, tips=tips)

    # ------------------------------------------------------------------
    # Einzelmethoden (für Tests / direkten Aufruf)
    # ------------------------------------------------------------------

    def get_players(self) -> list[Player]:
        with self._page() as page:
            return self._scrape_players(page)

    def get_matches(self, season: str) -> list[Match]:
        with self._page() as page:
            matches, _ = self._scrape_matches_and_results(page, season)
            return matches

    def get_results(self, season: str) -> list[MatchResult]:
        with self._page() as page:
            _, results = self._scrape_matches_and_results(page, season)
            return results

    def get_tips(self, season: str) -> list[Tip]:
        with self._page() as page:
            matches, _ = self._scrape_matches_and_results(page, season)
            return self._scrape_tips(page, season, matches)

    # ------------------------------------------------------------------
    # Private Scraping-Logik
    # ------------------------------------------------------------------

    def _scrape_players(self, page: Page) -> list[Player]:
        page.goto(self._url(self._selectors.TIPPUEBERSICHT_PATH.format(matchday=1)))
        rows = page.locator(self._selectors.RANKING_ROW_SELECTOR)
        players: list[Player] = []
        seen_ids: set[str] = set()
        for i in range(rows.count()):
            name = _safe_inner_text(rows.nth(i).locator("div.mg_name"))
            if not name:
                continue
            player_id = _slugify(name)
            if player_id in seen_ids:
                continue
            seen_ids.add(player_id)
            players.append(Player(id=player_id, display_name=name))
        return players

    def _scrape_matches_and_results(
        self, page: Page, season: str
    ) -> tuple[list[Match], list[MatchResult]]:
        """Liest Spielplan und Ergebnisse in einem Durchgang pro Spieltag."""
        matches: list[Match] = []
        results: list[MatchResult] = []
        for matchday_number in self._iter_spielplan_matchdays(page):
            matchday_title = self._read_matchday_title(page, matchday_number)
            rows = page.locator(self._selectors.SPIELPLAN_ROW_SELECTOR)
            for row_index in range(rows.count()):
                row = rows.nth(row_index)
                cells = row.locator("td")
                if cells.count() < 4:
                    continue
                kickoff_text = cells.nth(0).inner_text().strip()
                home_name = cells.nth(2).inner_text().strip()
                away_name = cells.nth(3).inner_text().strip()
                if not home_name or not away_name:
                    continue

                match_id = _match_id(season, matchday_number, row_index, home_name, away_name)
                matches.append(
                    Match(
                        id=match_id,
                        matchday=Matchday(
                            number=matchday_number,
                            season=season,
                            name=matchday_title,
                        ),
                        home_team=Team(id=_slugify(home_name), name=home_name),
                        away_team=Team(id=_slugify(away_name), name=away_name),
                        kickoff=_parse_kickoff(kickoff_text),
                        match_type=MatchType.GROUP,
                    )
                )

                home_goals = _inner_text_or_none(
                    row.locator(self._selectors.RESULT_HOME_SELECTOR)
                )
                away_goals = _inner_text_or_none(
                    row.locator(self._selectors.RESULT_AWAY_SELECTOR)
                )
                if home_goals is not None and away_goals is not None:
                    results.append(
                        MatchResult(
                            match_id=match_id,
                            score=ScoreResult(int(home_goals), int(away_goals)),
                        )
                    )
        return matches, results

    def _scrape_tips(
        self, page: Page, season: str, matches: list[Match]
    ) -> list[Tip]:
        """Liest alle Tipps aller Spieler aus der Tippübersicht.

        Strategie pro Spieltag:
          1. Match-IDs aus dem bereits gescrapten `matches`-Objekt entnehmen
             (gleiche Reihenfolge wie die Spielplan-Zeilen = Tipp-Spalten).
          2. Tippübersicht aufrufen und Tipp-Spalten per Index zuordnen.
        """
        # Match-IDs nach Spieltag gruppieren (Reihenfolge beibehalten)
        matchday_to_ids: dict[int, list[str]] = {}
        for m in matches:
            matchday_to_ids.setdefault(m.matchday.number, []).append(m.id)

        tips: list[Tip] = []
        for matchday_number, match_ids in matchday_to_ids.items():
            page.goto(
                self._url(self._selectors.TIPPUEBERSICHT_PATH.format(matchday=matchday_number))
            )
            player_rows = page.locator(self._selectors.RANKING_ROW_SELECTOR)

            for i in range(player_rows.count()):
                row = player_rows.nth(i)
                player_name = _safe_inner_text(row.locator("div.mg_name"))
                if not player_name:
                    continue
                player_id = _slugify(player_name)

                tipp_cells = row.locator(self._selectors.TIPP_CELL_SELECTOR)
                for col_index, match_id in enumerate(match_ids):
                    if col_index >= tipp_cells.count():
                        break
                    score = self._extract_tip_score(tipp_cells.nth(col_index))
                    if score is None:
                        continue
                    tips.append(
                        Tip(
                            player_id=player_id,
                            match_id=match_id,
                            score_tip=ScoreResult(*score),
                        )
                    )
        return tips

    def _extract_tip_score(self, cell) -> tuple[int, int] | None:
        """Liest den Tipp aus einer Tipp-Zelle.
        Struktur: <td>3:1<sub class="p">3</sub></td>
        Nur Text-Knoten lesen, Badge ignorieren.
        """
        raw = cell.inner_text().strip()
        if not raw or raw in {"-", "--", "-:-"}:
            return None
        tip_text = cell.evaluate(_JS_TIP_TEXT)
        return _parse_score(tip_text)

    # Bekannte Kicktipp-Tab-Namen für Spieltage und K.o.-Runden.
    # Whitelist verhindert, dass Nicht-Spieltag-Tabs (z.B. 'Bonus') gematcht werden.
    _MATCHDAY_NAME_PATTERN = re.compile(
        r'^\d+\.\s*Spieltag$'
        r'|^(Sechzehntel|Achtel|Viertel|Halb)finale$'
        r'|^Finale$'
        r'|^\d+\.\s*Finale$'
        r'|^Spiel\s+um\s+Platz\s+\d+$',
        re.IGNORECASE,
    )

    def _read_matchday_title(self, page: Page, matchday_number: int) -> str | None:
        """Liest den Phasennamen aus dem Spieltag-Navigations-Tab.
        Akzeptiert nur bekannte Spieltag-Muster (Whitelist), damit Nicht-
        Spieltag-Tabs wie 'Bonus' nicht fälschlich zurückgegeben werden."""
        for selector in [
            f"a[href*='tippspielplan'][href*='spieltagIndex={matchday_number}']",
            f"a[href*='spieltagIndex={matchday_number}']",
        ]:
            loc = page.locator(selector)
            for i in range(loc.count()):
                text = _safe_inner_text(loc.nth(i)).strip()
                if text and self._MATCHDAY_NAME_PATTERN.match(text):
                    return text
        # Fallback: Seitentitel parsen – enthält oft den Rundennamen
        title = page.title()
        for part in re.split(r'[\-–|]', title):
            part = part.strip()
            if part and self._MATCHDAY_NAME_PATTERN.match(part):
                return part
        return None

    def _iter_spielplan_matchdays(self, page: Page, max_matchdays: int = 64) -> Iterator[int]:
        """Iteriert über Spieltage bis Kicktipp auf einen bekannten umleitet
        oder Inhalte sich wiederholen."""
        prev_fingerprint: frozenset[str] = frozenset()
        for matchday_number in range(1, max_matchdays + 1):
            page.goto(
                self._url(self._selectors.SPIELPLAN_PATH.format(matchday=matchday_number))
            )

            # Prüfung 1: URL-Redirect auf anderen Spieltag?
            if f"spieltagIndex={matchday_number}" not in page.url:
                break

            rows = page.locator(self._selectors.SPIELPLAN_ROW_SELECTOR)
            if rows.count() == 0:
                break

            # Prüfung 2: Gleiche Spiele wie letzter Spieltag?
            fingerprint = frozenset(
                rows.nth(i).locator("td").nth(2).inner_text().strip()
                for i in range(rows.count())
                if rows.nth(i).locator("td").count() > 2
            )
            if fingerprint and fingerprint == prev_fingerprint:
                break
            prev_fingerprint = fingerprint

            yield matchday_number

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

    def _url(self, path: str) -> str:
        return f"{self._credentials.community_url}{path}"


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _safe_inner_text(locator) -> str:
    """Gibt Text zurück oder '' wenn kein Element - verhindert Playwright-Timeouts."""
    if locator.count() == 0:
        return ""
    return locator.first.inner_text().strip()


def _inner_text_or_none(locator) -> str | None:
    if locator.count() == 0:
        return None
    text = locator.first.inner_text().strip()
    # Nur echte Zahlen zurückgeben, nicht "-" für nicht gespielte Spiele
    return text if text.lstrip("-").isdigit() else None


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _match_id(
    season: str, matchday_number: int, row_index: int, home_name: str, away_name: str
) -> str:
    """Eindeutige Match-ID inkl. Zeilenindex, damit K.O.-Spiele mit noch
    unbekannten Teams ("Unbekannt vs Unbekannt") keine doppelten IDs erzeugen."""
    return (
        f"{season}-md{matchday_number}-{row_index}"
        f"-{_slugify(home_name)}-{_slugify(away_name)}"
    )


def _parse_score(text: str) -> tuple[int, int] | None:
    if not text:
        return None
    m = SCORE_PATTERN.match(text)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _parse_kickoff(text: str) -> datetime:
    for fmt in ("%d.%m.%y %H:%M", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return datetime.min
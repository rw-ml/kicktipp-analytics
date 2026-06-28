"""
Abstraktion über die Datenquelle Kicktipp.

Kicktipp bietet keine offizielle öffentliche API an - alle bekannten
Community-Tools (Tipp-Bots, CLI-Tools) lesen die Daten per Browser-
Automatisierung (Selenium/Playwright) von den HTML-Seiten ab. Die aktuelle
Implementierung (siehe kicktipp_scraper.py) ist deshalb ein Scraper, kein
klassischer REST-Client.

Der Rest der Pipeline kennt nur dieses Protocol, nicht die konkrete
Scraping-Logik. Bricht Kicktipp das HTML, oder findet sich später eine
bessere/stabilere Quelle, wird nur eine neue Implementierung registriert -
Calculation, Persistence und Pipeline bleiben unverändert
(Dependency Inversion Principle).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from kicktipp_analytics.domain.models import Match, MatchResult, Player, Tip


@dataclass
class ScrapedData:
    """Alle Rohdaten eines Pipeline-Laufs in einer Struktur."""
    players: list[Player] = field(default_factory=list)
    matches: list[Match] = field(default_factory=list)
    results: list[MatchResult] = field(default_factory=list)
    tips: list[Tip] = field(default_factory=list)
    bonus_points: dict[str, int] = field(default_factory=dict)   # player_id → Bonuspunkte
    siege_by_player: dict[str, float] = field(default_factory=dict)  # player_id → Spieltagssiege (Kicktipp-Wert, kann Bruchteile haben)


class IKicktippDataSource(Protocol):
    def get_players(self) -> list[Player]: ...

    def get_matches(self, season: str) -> list[Match]: ...

    def get_results(self, season: str) -> list[MatchResult]: ...

    def get_tips(self, season: str) -> list[Tip]: ...

    def scrape_all(self, season: str) -> ScrapedData:
        """Alle Daten in einem Zug holen (eine Browser-Session).
        Default-Implementierung ruft die Einzelmethoden auf - Scraper
        überschreiben das für eine einzige Session.
        """
        return ScrapedData(
            players=self.get_players(),
            matches=self.get_matches(season),
            results=self.get_results(season),
            tips=self.get_tips(season),
        )
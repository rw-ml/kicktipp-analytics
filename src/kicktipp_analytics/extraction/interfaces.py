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

from typing import Protocol

from kicktipp_analytics.domain.models import Match, MatchResult, Player, Tip


class IKicktippDataSource(Protocol):
    def get_players(self) -> list[Player]: ...

    def get_matches(self, season: str) -> list[Match]: ...

    def get_results(self, season: str) -> list[MatchResult]: ...

    def get_tips(self, season: str) -> list[Tip]: ...

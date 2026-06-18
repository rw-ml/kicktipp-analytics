"""
Abstraktion über das Ziel der aufbereiteten Daten.

Power BI verbindet sich NIE direkt mit der Scraping- oder Berechnungslogik,
sondern ausschließlich mit dem Ergebnis einer IDataSink-Implementierung
(Datenbank-Tabellen oder Dateien). Das macht die Entscheidung
"Power BI Desktop vs. Pro/Premium mit Gateway" komplett unabhängig von der
restlichen Pipeline - es ist reine Konfiguration, welche(s) IDataSink in
scheduler/run_pipeline.py instanziiert wird (siehe dort).
"""
from __future__ import annotations

from typing import Protocol

from kicktipp_analytics.calculation.ranking import RankingSnapshot
from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation
from kicktipp_analytics.calculation.statistics import PlayerStatistics
from kicktipp_analytics.domain.models import Match, MatchResult, Player, Tip


class IDataSink(Protocol):
    def write_dimensions(self, players: list[Player], matches: list[Match]) -> None: ...

    def write_results(self, results: list[MatchResult]) -> None: ...

    def write_tip_evaluations(
        self, tips: list[Tip], evaluations: list[TipEvaluation]
    ) -> None: ...

    def write_ranking_snapshots(self, snapshots: list[RankingSnapshot]) -> None: ...

    def write_statistics(self, statistics: list[PlayerStatistics]) -> None: ...

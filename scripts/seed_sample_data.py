"""
Füllt eine lokale SQLite-Datenbank mit Testdaten (MockKicktippDataSource),
damit das Dashboard sofort ausprobiert werden kann - ganz ohne echte
Kicktipp-Zugangsdaten.

Verwendung:
    python scripts/seed_sample_data.py

Erzeugt `sample.db` im Projektverzeichnis. Das Dashboard liest per
Default genau diese Datei (siehe frontend/app.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Erlaubt den direkten Aufruf "python scripts/seed_sample_data.py", ohne
# dass das src-Package vorher installiert oder PYTHONPATH gesetzt werden muss.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kicktipp_analytics.calculation.evaluators.penalty_winner import PenaltyWinnerCalculator
from kicktipp_analytics.calculation.evaluators.tendenz_tordifferenz_ergebnis import (
    TendenzTordifferenzErgebnisCalculator,
)
from kicktipp_analytics.calculation.ranking import RankingCalculator
from kicktipp_analytics.calculation.scoring_resolver import ScoringResolver
from kicktipp_analytics.calculation.statistics import StatisticsCalculator
from kicktipp_analytics.extraction.mock_data_source import MockKicktippDataSource
from kicktipp_analytics.persistence.sql_sink import SqlDataSink
from kicktipp_analytics.pipeline.orchestrator import PipelineOrchestrator

SEASON = "wm2026"
DB_PATH = "sample.db"


def main() -> None:
    orchestrator = PipelineOrchestrator(
        data_source=MockKicktippDataSource(season=SEASON),
        sinks=[SqlDataSink(f"sqlite:///{DB_PATH}")],
        scoring_resolver=ScoringResolver(
            [TendenzTordifferenzErgebnisCalculator(), PenaltyWinnerCalculator()]
        ),
        ranking_calculator=RankingCalculator(),
        statistics_calculator=StatisticsCalculator(),
        season=SEASON,
    )
    orchestrator.run()
    print(f"Testdaten geschrieben nach {DB_PATH}")


if __name__ == "__main__":
    main()
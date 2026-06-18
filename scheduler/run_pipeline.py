"""
Entry-Point für einen Pipeline-Lauf. Wird vom Scheduler (cron/systemd-Timer
auf dem eigenen Server) periodisch aufgerufen:

    python scheduler/run_pipeline.py

Hier - und nur hier - werden konkrete Implementierungen ausgewählt und
zusammengesteckt (Composition Root). Der Rest des Codes kennt ausschließlich
Abstraktionen.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Erlaubt den direkten Aufruf "python scheduler/run_pipeline.py", ohne dass
# das src-Package vorher installiert oder PYTHONPATH gesetzt werden muss.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kicktipp_analytics.calculation.evaluators.penalty_winner import PenaltyWinnerCalculator
from kicktipp_analytics.calculation.evaluators.tendenz_tordifferenz_ergebnis import (
    TendenzTordifferenzErgebnisCalculator,
)
from kicktipp_analytics.calculation.ranking import RankingCalculator
from kicktipp_analytics.calculation.scoring_resolver import ScoringResolver
from kicktipp_analytics.calculation.statistics import StatisticsCalculator
from kicktipp_analytics.config.settings import Settings
from kicktipp_analytics.extraction.kicktipp_scraper import KicktippScraper
from kicktipp_analytics.persistence.csv_sink import CsvDataSink
from kicktipp_analytics.persistence.interfaces import IDataSink
from kicktipp_analytics.persistence.sql_sink import SqlDataSink
from kicktipp_analytics.pipeline.orchestrator import PipelineOrchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("kicktipp_analytics")


def build_sinks(settings: Settings) -> list[IDataSink]:
    """
    Beide Senken können gleichzeitig aktiv sein: SQL_CONNECTION_URL und
    CSV_OUTPUT_DIR einfach beide in der .env setzen. So bleibt die Pipeline
    unabhängig davon, ob am Ende Power BI Desktop (Dateien oder lokale DB)
    oder Power BI Pro/Premium mit Gateway (zentrale DB) verwendet wird.
    """
    sinks: list[IDataSink] = []
    if settings.sql_connection_url:
        sinks.append(SqlDataSink(settings.sql_connection_url))
    if settings.csv_output_dir:
        sinks.append(CsvDataSink(settings.csv_output_dir))
    if not sinks:
        raise RuntimeError(
            "Keine Senke konfiguriert. Mindestens SQL_CONNECTION_URL oder "
            "CSV_OUTPUT_DIR in der .env setzen."
        )
    return sinks


def main() -> None:
    settings = Settings.from_env()

    data_source = KicktippScraper(
        settings.kicktipp_credentials, headless=settings.headless_browser
    )
    sinks = build_sinks(settings)

    orchestrator = PipelineOrchestrator(
        data_source=data_source,
        sinks=sinks,
        scoring_resolver=ScoringResolver(
            [TendenzTordifferenzErgebnisCalculator(), PenaltyWinnerCalculator()]
        ),
        ranking_calculator=RankingCalculator(),
        statistics_calculator=StatisticsCalculator(),
        season=settings.season,
    )

    logger.info("Starte Pipeline-Lauf für Saison %s", settings.season)
    orchestrator.run()
    logger.info("Pipeline-Lauf abgeschlossen.")


if __name__ == "__main__":
    main()
"""
Einziger Einstiegspunkt für einen Pipeline-Lauf.

Kennt ausschließlich Abstraktionen (IKicktippDataSource, IDataSink,
ScoringResolver, RankingCalculator, StatisticsCalculator) - alle konkreten
Implementierungen werden von außen injiziert (Dependency Inversion). Das
macht die Orchestrierung unabhängig davon, ob die Quelle ein Scraper oder
später eine echte API ist, und unabhängig davon, ob eine oder mehrere
Senken (Postgres, CSV, ...) gleichzeitig bedient werden.
"""
from __future__ import annotations

from kicktipp_analytics.calculation.ranking import RankingCalculator
from kicktipp_analytics.calculation.scoring_resolver import ScoringResolver
from kicktipp_analytics.calculation.statistics import StatisticsCalculator
from kicktipp_analytics.extraction.interfaces import IKicktippDataSource
from kicktipp_analytics.persistence.interfaces import IDataSink


class PipelineOrchestrator:
    def __init__(
        self,
        data_source: IKicktippDataSource,
        sinks: list[IDataSink],
        scoring_resolver: ScoringResolver,
        ranking_calculator: RankingCalculator,
        statistics_calculator: StatisticsCalculator,
        season: str,
    ):
        self._source = data_source
        self._sinks = sinks
        self._scoring_resolver = scoring_resolver
        self._ranking_calculator = ranking_calculator
        self._statistics_calculator = statistics_calculator
        self._season = season

    def run(self) -> None:
        data = self._source.scrape_all(self._season)
        players = data.players
        matches = data.matches
        results = data.results
        tips = data.tips

        match_by_id = {m.id: m for m in matches}
        result_by_match = {r.match_id: r for r in results}

        evaluations = [
            self._scoring_resolver.evaluate(
                tip, match_by_id[tip.match_id], result_by_match[tip.match_id]
            )
            for tip in tips
            if tip.match_id in match_by_id and tip.match_id in result_by_match
        ]

        match_to_matchday = {m.id: m.matchday.number for m in matches}
        match_to_actual_tendency = {
            match_id: result.score.tendency for match_id, result in result_by_match.items()
        }
        standings = self._ranking_calculator.calculate_matchday_standings(
            evaluations, match_to_matchday
        )
        snapshots = self._ranking_calculator.build_snapshots(standings)
        statistics = self._statistics_calculator.calculate(evaluations, match_to_actual_tendency)

        for sink in self._sinks:
            sink.write_dimensions(players, matches)
            sink.write_results(results)
            sink.write_tip_evaluations(tips, evaluations)
            sink.write_ranking_snapshots(snapshots)
            sink.write_statistics(statistics)
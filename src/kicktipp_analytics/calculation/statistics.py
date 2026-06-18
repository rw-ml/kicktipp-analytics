"""
Leitet Performance-Kennzahlen pro Spieler aus den TipEvaluations ab:
Trefferquote, Anzahl exakter Treffer, Anzahl Tendenz-Treffer und die Anzahl
komplett daneben liegender Tipps (0 Punkte) - die Basis für den
"Bremsfett-Pokal".
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation


@dataclass(frozen=True, slots=True)
class PlayerStatistics:
    player_id: str
    total_tips: int
    exact_hits: int
    #: Tendenz-Treffer inkl. exakter Treffer, da ein exakter Treffer immer
    #: auch eine richtige Tendenz beinhaltet.
    tendency_hits: int
    misses: int
    hit_rate: float


class StatisticsCalculator:
    def calculate(self, evaluations: list[TipEvaluation]) -> list[PlayerStatistics]:
        by_player: dict[str, list[TipEvaluation]] = defaultdict(list)
        for ev in evaluations:
            by_player[ev.player_id].append(ev)

        result: list[PlayerStatistics] = []
        for player_id, player_evals in by_player.items():
            total = len(player_evals)
            exact = sum(
                1
                for ev in player_evals
                if (bd := ev.breakdowns.get("score")) and bd.is_exact_hit
            )
            tendency = sum(
                1
                for ev in player_evals
                if (bd := ev.breakdowns.get("score")) and bd.is_tendency_correct
            )
            misses = sum(1 for ev in player_evals if ev.total_points == 0)
            hit_rate = round(tendency / total, 4) if total else 0.0

            result.append(
                PlayerStatistics(
                    player_id=player_id,
                    total_tips=total,
                    exact_hits=exact,
                    tendency_hits=tendency,
                    misses=misses,
                    hit_rate=hit_rate,
                )
            )

        # "Bremsfett"-Ranking: meiste Fehltipps zuerst.
        result.sort(key=lambda s: -s.misses)
        return result

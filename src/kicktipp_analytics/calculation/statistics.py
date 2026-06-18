"""
Leitet Performance-Kennzahlen pro Spieler aus den TipEvaluations ab:
Trefferquote, Anzahl exakter Treffer, Anzahl Tendenz-Treffer (gesamt sowie
aufgeschlüsselt nach Sieg/Unentschieden) und die Anzahl komplett daneben
liegender Tipps (0 Punkte) - die Basis für den "Bremsfett-Pokal".

Hinweis zur Sieg-Kategorie: Heimsieg und Auswärtssieg werden hier bewusst
zu einer gemeinsamen "Sieg"-Kategorie zusammengefasst. Bei einem Turnier
auf neutralem Platz (wie einer WM) ist "Heim/Auswärts" nur ein Artefakt
der Tabellen-Reihenfolge, keine reale, bedeutungsvolle Unterscheidung -
fachlich relevant ist nur, ob ein Spieler richtig auf eine Entscheidung
(Sieg) oder ein Unentschieden getippt hat.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from kicktipp_analytics.calculation.scoring_resolver import TipEvaluation
from kicktipp_analytics.domain.models import Tendency


@dataclass(frozen=True, slots=True)
class PlayerStatistics:
    player_id: str
    total_tips: int
    exact_hits: int
    #: Tendenz-Treffer inkl. exakter Treffer, da ein exakter Treffer immer
    #: auch eine richtige Tendenz beinhaltet.
    tendency_hits: int
    #: Aufschlüsselung der Tendenz-Treffer nach tatsächlichem Spielausgang.
    win_tips_correct: int
    draw_tips_correct: int
    misses: int
    hit_rate: float


class StatisticsCalculator:
    def calculate(
        self,
        evaluations: list[TipEvaluation],
        match_to_actual_tendency: dict[str, Tendency],
    ) -> list[PlayerStatistics]:
        by_player: dict[str, list[TipEvaluation]] = defaultdict(list)
        for ev in evaluations:
            by_player[ev.player_id].append(ev)

        result: list[PlayerStatistics] = []
        for player_id, player_evals in by_player.items():
            total = len(player_evals)
            exact = 0
            tendency = 0
            win_correct = 0
            draw_correct = 0
            misses = 0

            for ev in player_evals:
                breakdown = ev.breakdowns.get("score")
                if breakdown and breakdown.is_exact_hit:
                    exact += 1
                if breakdown and breakdown.is_tendency_correct:
                    tendency += 1
                    actual_tendency = match_to_actual_tendency[ev.match_id]
                    if actual_tendency == Tendency.DRAW:
                        draw_correct += 1
                    else:
                        win_correct += 1
                if ev.total_points == 0:
                    misses += 1

            hit_rate = round(tendency / total, 4) if total else 0.0

            result.append(
                PlayerStatistics(
                    player_id=player_id,
                    total_tips=total,
                    exact_hits=exact,
                    tendency_hits=tendency,
                    win_tips_correct=win_correct,
                    draw_tips_correct=draw_correct,
                    misses=misses,
                    hit_rate=hit_rate,
                )
            )

        # "Bremsfett"-Ranking: meiste Fehltipps zuerst.
        result.sort(key=lambda s: -s.misses)
        return result
"""Combine TV multi-timeframe analyses into a single score [-100, +100].

Why a custom scorer?
--------------------
TV's `Recommendation` is categorical (STRONG_BUY .. STRONG_SELL). Our risk
manager + engine want a continuous signal so we can:
- compare against `entry_score_threshold` (e.g. 60) and `exit_score_threshold` (20)
- weight higher timeframes more (1d > 4h > 1h > 15m > 5m)
- expose a single number to the user (clearer than 5 labels)

The score is signed:
    +100 = strongest possible buy agreement across all TFs
    -100 = strongest possible sell
       0 = perfect neutral / disagreement cancels out

The confidence band reflects how much TFs agree — high score with low
confidence is suspicious (one TF screaming buy, others neutral).

We deliberately keep this simple — overengineering the scorer is a quick
path to overfit. If a user wants different weighting, they can tune the
strategy params (interval list + threshold).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradingview.client import TVAnalysis


# ---------------------------------------------------------------------------
# Per-recommendation numeric score in [-100, +100]
# ---------------------------------------------------------------------------
_REC_SCORE: dict[str, float] = {
    "STRONG_BUY": 100.0,
    "BUY": 50.0,
    "NEUTRAL": 0.0,
    "SELL": -50.0,
    "STRONG_SELL": -100.0,
}


# ---------------------------------------------------------------------------
# Per-timeframe weight (higher TF = higher weight)
# ---------------------------------------------------------------------------
_DEFAULT_TF_WEIGHTS: dict[str, float] = {
    "1m": 0.2,
    "5m": 0.4,
    "15m": 0.6,
    "30m": 0.7,
    "1h": 1.0,
    "2h": 1.2,
    "4h": 1.5,
    "1d": 2.0,
    "1w": 2.5,
}


@dataclass
class CombinedScore:
    """Aggregated multi-TF score."""

    score: float                       # [-100, +100]
    direction: str                     # "BUY" | "SELL" | "NEUTRAL"
    confidence: float                  # [0, 1] — agreement strength
    agreement_pct: float               # [0, 1] — what % TFs agree on direction
    per_tf: list[dict[str, Any]]       # [{interval, recommendation, score, weight}, ...]
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "direction": self.direction,
            "confidence": round(self.confidence, 3),
            "agreement_pct": round(self.agreement_pct, 3),
            "per_tf": self.per_tf,
            "bullish_count": self.bullish_count,
            "bearish_count": self.bearish_count,
            "neutral_count": self.neutral_count,
        }


class Scorer:
    """Stateless scorer — combines TV analyses across intervals."""

    def __init__(self, tf_weights: dict[str, float] | None = None) -> None:
        self.tf_weights = dict(_DEFAULT_TF_WEIGHTS)
        if tf_weights:
            self.tf_weights.update(tf_weights)

    def _weight(self, interval: str) -> float:
        return self.tf_weights.get(interval.lower(), 1.0)

    def score(self, analyses: list[TVAnalysis]) -> CombinedScore:
        """Combine a list of TV analyses into one CombinedScore."""
        if not analyses:
            return CombinedScore(
                score=0.0,
                direction="NEUTRAL",
                confidence=0.0,
                agreement_pct=0.0,
                per_tf=[],
            )

        per_tf: list[dict[str, Any]] = []
        weighted_sum = 0.0
        weight_total = 0.0
        bullish = bearish = neutral = 0

        for a in analyses:
            rec = a.recommendation.upper()
            rec_score = _REC_SCORE.get(rec, 0.0)
            w = self._weight(a.interval)
            weighted_sum += rec_score * w
            weight_total += w
            if rec_score > 0:
                bullish += 1
            elif rec_score < 0:
                bearish += 1
            else:
                neutral += 1
            per_tf.append(
                {
                    "interval": a.interval,
                    "recommendation": rec,
                    "score": rec_score,
                    "weight": w,
                    "buy_signals": a.buy_signals,
                    "sell_signals": a.sell_signals,
                    "neutral_signals": a.neutral_signals,
                }
            )

        final_score = weighted_sum / weight_total if weight_total > 0 else 0.0

        # Agreement % — how many TFs agree on the dominant direction.
        total = len(analyses)
        dominant = max(bullish, bearish, neutral)
        agreement = dominant / total if total > 0 else 0.0

        # Direction label
        if final_score >= 20.0:
            direction = "BUY"
        elif final_score <= -20.0:
            direction = "SELL"
        else:
            direction = "NEUTRAL"

        # Confidence = agreement × |score|/100 — both matter.
        # Strong score with weak agreement = low confidence (one TF outvoting).
        confidence = agreement * (abs(final_score) / 100.0)

        return CombinedScore(
            score=final_score,
            direction=direction,
            confidence=confidence,
            agreement_pct=agreement,
            per_tf=per_tf,
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
        )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------
def combine_recommendations(
    analyses: list[TVAnalysis],
    tf_weights: dict[str, float] | None = None,
) -> CombinedScore:
    """Functional shorthand around `Scorer.score()`."""
    return Scorer(tf_weights=tf_weights).score(analyses)

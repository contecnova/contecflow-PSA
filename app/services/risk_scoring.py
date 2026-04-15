"""Shared risk scoring rules used across risk and analytics modules."""

PROB_SCORE = {
    "very_low": 0.05,
    "low": 0.2,
    "medium": 0.5,
    "high": 0.7,
    "very_high": 0.9,
}
IMPACT_SCORE = {
    "negligible": 1,
    "minor": 2,
    "moderate": 3,
    "major": 4,
    "critical": 5,
}


def risk_score(probability: str, impact: str) -> float:
    return round(PROB_SCORE.get(probability, 0.5) * IMPACT_SCORE.get(impact, 3), 2)


def risk_level(score: float) -> str:
    if score >= 3.0:
        return "critical"
    if score >= 2.0:
        return "high"
    if score >= 1.0:
        return "medium"
    return "low"

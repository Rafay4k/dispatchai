"""
DispatchAI matching engine.

This is the core of the product: given one open load and a pool of carriers,
score and rank which carriers are the best fit. A broker/dispatcher normally
does this by memory and gut feel over dozens of phone calls. We turn it into
an explainable scoring function so it can run automatically and still be
audited by a human.

Scoring factors (each 0-1, then weighted):
  - lane_fit:        has this carrier run this lane (or a similar one) before?
  - equipment_fit:   does the carrier have the right trailer/equipment type?
  - reliability:     historical on-time %, based on past loads
  - deadhead_fit:    how far is the carrier's current location from pickup?
  - rate_fit:        how close is the carrier's typical rate to the target rate?

Weights are configurable because brokers care about different things
(a broker chasing on-time SLAs weighs reliability higher; a broker chasing
margin weighs rate_fit higher).
"""

from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class Load:
    load_id: str
    origin: str
    destination: str
    equipment_type: str          # e.g. "dry_van", "reefer", "flatbed"
    target_rate: float           # USD, what the broker wants to pay
    pickup_lat: float
    pickup_lon: float


@dataclass
class Carrier:
    carrier_id: str
    name: str
    equipment_types: list        # equipment they operate
    lanes_run: list              # list of (origin, destination) tuples, history
    on_time_pct: float           # 0-100
    avg_rate_accepted: float     # USD, historical average
    current_lat: float
    current_lon: float
    active: bool = True


@dataclass
class MatchResult:
    carrier: Carrier
    score: float
    breakdown: dict = field(default_factory=dict)
    reason: str = ""


DEFAULT_WEIGHTS = {
    "lane_fit": 0.30,
    "equipment_fit": 0.25,
    "reliability": 0.20,
    "deadhead_fit": 0.15,
    "rate_fit": 0.10,
}


def _haversine_miles(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in miles between two lat/lon points."""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _lane_fit(load: Load, carrier: Carrier) -> float:
    lane = (load.origin, load.destination)
    if lane in carrier.lanes_run:
        return 1.0
    # partial credit if they've run the same origin OR destination before
    same_origin = any(o == load.origin for o, _ in carrier.lanes_run)
    same_dest = any(d == load.destination for _, d in carrier.lanes_run)
    if same_origin and same_dest:
        return 0.8
    if same_origin or same_dest:
        return 0.4
    return 0.1  # unknown lane isn't disqualifying, just lower confidence


def _equipment_fit(load: Load, carrier: Carrier) -> float:
    return 1.0 if load.equipment_type in carrier.equipment_types else 0.0


def _reliability(carrier: Carrier) -> float:
    return max(0.0, min(1.0, carrier.on_time_pct / 100))


def _deadhead_fit(load: Load, carrier: Carrier) -> float:
    miles = _haversine_miles(load.pickup_lat, load.pickup_lon, carrier.current_lat, carrier.current_lon)
    # 0 miles -> 1.0 score, 300+ miles -> ~0
    return max(0.0, 1.0 - (miles / 300))


def _rate_fit(load: Load, carrier: Carrier) -> float:
    if carrier.avg_rate_accepted <= 0:
        return 0.5  # no history, neutral
    diff_pct = abs(load.target_rate - carrier.avg_rate_accepted) / carrier.avg_rate_accepted
    return max(0.0, 1.0 - diff_pct)


def score_carrier(load: Load, carrier: Carrier, weights: Optional[dict] = None) -> MatchResult:
    weights = weights or DEFAULT_WEIGHTS
    breakdown = {
        "lane_fit": _lane_fit(load, carrier),
        "equipment_fit": _equipment_fit(load, carrier),
        "reliability": _reliability(carrier),
        "deadhead_fit": _deadhead_fit(load, carrier),
        "rate_fit": _rate_fit(load, carrier),
    }
    total = sum(breakdown[k] * weights[k] for k in weights)

    # equipment mismatch is a hard disqualifier in practice
    if breakdown["equipment_fit"] == 0.0:
        total *= 0.15

    reasons = []
    if breakdown["lane_fit"] >= 0.8:
        reasons.append("has run this exact lane before")
    if breakdown["reliability"] >= 0.9:
        reasons.append("excellent on-time record")
    if breakdown["deadhead_fit"] >= 0.8:
        reasons.append("very close to pickup")
    if breakdown["equipment_fit"] == 0.0:
        reasons.append("wrong equipment type")
    reason = "; ".join(reasons) if reasons else "average fit across factors"

    return MatchResult(carrier=carrier, score=round(total, 3), breakdown=breakdown, reason=reason)


def rank_carriers(load: Load, carriers: list, weights: Optional[dict] = None, top_n: int = 5) -> list:
    results = [score_carrier(load, c, weights) for c in carriers if c.active]
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_n]

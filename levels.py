"""Price levels: support/resistance zones and Fibonacci retracements."""
from __future__ import annotations

from dataclasses import dataclass

from structure import Swing

FIB_RATIOS = (0.382, 0.5, 0.618, 0.786)


@dataclass
class Zone:
    low: float
    high: float
    touches: int
    highs: int         # how many swing highs (price rejected from above) formed here
    lows: int          # how many swing lows (price bounced) formed here
    kind: str          # "support" (below price) or "resistance" (above price)
    inside: bool       # price is currently inside the zone
    last_time: int


def find_zones(swings: list[Swing], atr_now: float, price: float, tolerance_atr: float = 0.6,
               min_touches: int = 2, per_side: int = 3) -> tuple[list[Zone], list[Zone]]:
    """Groups swing points that sit at nearly the same price. More turns at a level = stronger zone.
    Returns (supports nearest first, resistances nearest first)."""
    tolerance = atr_now * tolerance_atr
    clusters: list[list[Swing]] = []
    for swing in sorted(swings, key=lambda s: s.price):
        if clusters:
            cluster = clusters[-1]
            center = sum(s.price for s in cluster) / len(cluster)
            if swing.price - center <= tolerance:
                cluster.append(swing)
                continue
        clusters.append([swing])

    zones: list[Zone] = []
    min_width = atr_now * 0.3
    for cluster in clusters:
        if len(cluster) < min_touches:
            continue
        low, high = min(s.price for s in cluster), max(s.price for s in cluster)
        if high - low < min_width:
            mid = (low + high) / 2
            low, high = mid - min_width / 2, mid + min_width / 2
        zones.append(Zone(
            low=low, high=high, touches=len(cluster),
            highs=sum(s.kind == "high" for s in cluster), lows=sum(s.kind == "low" for s in cluster),
            kind="support" if (low + high) / 2 < price else "resistance",
            inside=low <= price <= high,
            last_time=max(s.time for s in cluster),
        ))

    supports = sorted((z for z in zones if z.kind == "support"), key=lambda z: price - z.high)[:per_side]
    resistances = sorted((z for z in zones if z.kind == "resistance"), key=lambda z: z.low - price)[:per_side]
    return supports, resistances


def fibonacci(swings: list[Swing], trend: str, min_leg: float = 0.0) -> dict | None:
    """Retracement levels of the latest meaningful leg in the trend direction (up-leg in uptrends,
    down-leg in downtrends). Legs smaller than `min_leg` are noise and skipped."""
    for k in range(len(swings) - 1, 0, -1):
        end, start = swings[k], swings[k - 1]
        if (trend == "up" and end.kind != "high") or (trend == "down" and end.kind != "low"):
            continue
        move = end.price - start.price
        if abs(move) < min_leg:
            continue
        levels = [{"ratio": r, "price": end.price - move * r} for r in FIB_RATIOS]
        golden = sorted(level["price"] for level in levels if level["ratio"] in (0.5, 0.618))
        return {
            "direction": "up" if move > 0 else "down",
            "start": {"time": start.time, "price": start.price},
            "end": {"time": end.time, "price": end.price},
            "levels": levels,
            "golden": golden,
        }
    return None

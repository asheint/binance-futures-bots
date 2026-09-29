"""Market structure (Dow Theory): swing highs/lows, HH/HL/LH/LL labels, breaks of structure, trend state."""
from __future__ import annotations

from dataclasses import dataclass

from models import Candle, price_text

LABEL_NAMES = {"HH": "Higher High", "HL": "Higher Low", "LH": "Lower High", "LL": "Lower Low"}


@dataclass
class Swing:
    index: int
    time: int
    price: float
    kind: str             # "high" or "low"
    confirmed_index: int  # first candle where this swing is known; later code must not use it earlier
    label: str = ""       # HH / LH for highs, HL / LL for lows (empty for the first of each kind)


@dataclass
class StructureBreak:
    index: int
    time: int
    price: float
    direction: str     # "up" or "down"
    kind: str          # "BOS" = trend continues, "CHoCH" = first break against the previous direction
    swing_index: int   # the swing whose level was broken


def find_swings(candles: list[Candle], atr_values: list[float | None], left: int = 5, right: int = 5,
                min_atr: float = 1.0) -> list[Swing]:
    """A swing high is the highest candle within `left` candles before and `right` after it (lows mirror this).
    Swings alternate high/low, and moves smaller than `min_atr` x ATR are ignored as noise."""
    raw: list[Swing] = []
    for i in range(left, len(candles) - right):
        window = candles[i - left:i + right + 1]
        before = candles[i - left:i]
        c = candles[i]
        if c.high >= max(x.high for x in window) and c.high > max(x.high for x in before):
            raw.append(Swing(i, c.time, c.high, "high", i + right))
        if c.low <= min(x.low for x in window) and c.low < min(x.low for x in before):
            raw.append(Swing(i, c.time, c.low, "low", i + right))

    swings: list[Swing] = []
    for swing in raw:
        if swings and swings[-1].kind == swing.kind:
            last = swings[-1]
            more_extreme = swing.price > last.price if swing.kind == "high" else swing.price < last.price
            if more_extreme:
                swings[-1] = swing
            continue
        if swings:
            noise = (atr_values[swing.index] or 0) * min_atr
            if abs(swing.price - swings[-1].price) < noise:
                continue
        swings.append(swing)

    label_swings(swings)
    return swings


def label_swings(swings: list[Swing]) -> None:
    previous: dict[str, Swing | None] = {"high": None, "low": None}
    for swing in swings:
        prev = previous[swing.kind]
        if prev is not None:
            if swing.kind == "high":
                swing.label = "HH" if swing.price > prev.price else "LH"
            else:
                swing.label = "HL" if swing.price > prev.price else "LL"
        previous[swing.kind] = swing


def find_breaks(candles: list[Candle], swings: list[Swing]) -> list[StructureBreak]:
    """A break happens when a candle CLOSES beyond the latest confirmed swing high or low."""
    confirmed = sorted(swings, key=lambda s: s.confirmed_index)
    events: list[StructureBreak] = []
    last_high = last_low = None
    broken: set[int] = set()
    bias = None
    j = 0
    for i, candle in enumerate(candles):
        while j < len(confirmed) and confirmed[j].confirmed_index <= i:
            if confirmed[j].kind == "high":
                last_high = confirmed[j]
            else:
                last_low = confirmed[j]
            j += 1
        if last_high and last_high.index not in broken and candle.close > last_high.price:
            events.append(StructureBreak(i, candle.time, last_high.price, "up",
                                         "CHoCH" if bias == "down" else "BOS", last_high.index))
            broken.add(last_high.index)
            bias = "up"
        if last_low and last_low.index not in broken and candle.close < last_low.price:
            events.append(StructureBreak(i, candle.time, last_low.price, "down",
                                         "CHoCH" if bias == "up" else "BOS", last_low.index))
            broken.add(last_low.index)
            bias = "down"
    return events


def trend_state(swings: list[Swing], breaks: list[StructureBreak]) -> tuple[str, str]:
    """Returns ("up" | "down" | "range" | "unclear", explanation)."""
    last_high = next((s for s in reversed(swings) if s.kind == "high" and s.label), None)
    last_low = next((s for s in reversed(swings) if s.kind == "low" and s.label), None)
    if not last_high or not last_low:
        return "unclear", "Not enough swings yet to read the structure."

    high_text = f"{LABEL_NAMES[last_high.label]} ({price_text(last_high.price)})"
    low_text = f"{LABEL_NAMES[last_low.label]} ({price_text(last_low.price)})"

    if last_high.label == "HH" and last_low.label == "HL":
        trend = "up"
        text = f"Uptrend: the last high was a {high_text} and the last low a {low_text}. Buyers are in control."
    elif last_high.label == "LH" and last_low.label == "LL":
        trend = "down"
        text = f"Downtrend: the last high was a {high_text} and the last low a {low_text}. Sellers are in control."
    else:
        trend = "range"
        text = (f"Mixed structure: the last high was a {high_text} but the last low a {low_text}. "
                "No clear trend; the market is ranging or turning.")

    latest = breaks[-1] if breaks else None
    if latest and trend == "up" and latest.direction == "down" and latest.swing_index == last_low.index:
        trend = "range"
        text = (f"Uptrend is being challenged: a candle closed below the last Higher Low ({price_text(last_low.price)}). "
                "Wait for new structure before trusting longs.")
    elif latest and trend == "down" and latest.direction == "up" and latest.swing_index == last_high.index:
        trend = "range"
        text = (f"Downtrend is being challenged: a candle closed above the last Lower High ({price_text(last_high.price)}). "
                "Wait for new structure before trusting shorts.")
    return trend, text

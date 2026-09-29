"""Candle patterns that show one side taking control."""
from __future__ import annotations

from dataclasses import dataclass

from models import Candle


@dataclass
class Pattern:
    index: int
    time: int
    name: str
    short: str
    direction: str  # "bull" or "bear"
    meaning: str


def find_patterns(candles: list[Candle], atr_values: list[float | None], lookback: int = 150) -> list[Pattern]:
    found: list[Pattern] = []
    for i in range(max(1, len(candles) - lookback), len(candles)):
        c, prev, size = candles[i], candles[i - 1], atr_values[i]
        candle_range = c.high - c.low
        if not size or candle_range < size * 0.5:  # ignore tiny candles; they mean little
            continue
        body = abs(c.close - c.open)
        prev_body = abs(prev.close - prev.open)
        upper_wick = c.high - max(c.open, c.close)
        lower_wick = min(c.open, c.close) - c.low

        def add(name: str, short: str, direction: str, meaning: str) -> None:
            found.append(Pattern(i, c.time, name, short, direction, meaning))

        if prev.close < prev.open and c.close > c.open and c.close >= prev.open and c.open <= prev.close and body > prev_body:
            add("Bullish engulfing", "Engulf", "bull", "a green candle fully swallowed the previous red one; buyers overpowered sellers.")
        elif prev.close > prev.open and c.close < c.open and c.close <= prev.open and c.open >= prev.close and body > prev_body:
            add("Bearish engulfing", "Engulf", "bear", "a red candle fully swallowed the previous green one; sellers overpowered buyers.")
        elif lower_wick >= 2 * body and upper_wick <= 0.25 * candle_range:
            add("Hammer", "Hammer", "bull", "a long lower wick; sellers pushed price down but buyers rejected it.")
        elif upper_wick >= 2 * body and lower_wick <= 0.25 * candle_range:
            add("Shooting star", "Star", "bear", "a long upper wick; buyers pushed price up but sellers rejected it.")
    return found

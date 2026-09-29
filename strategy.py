"""A simple, well-known strategy for practice: EMA crossover with an ATR-based stop.

It is NOT a proven money maker. Its job is to let you practise the full loop
(signal -> sized entry -> stop-loss/take-profit -> journal) on the demo account.
"""
from __future__ import annotations


def ema(values: list[float], period: int) -> list[float]:
    """Returns EMA values aligned to values[period-1:]."""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    current = sum(values[:period]) / period
    out = [current]
    for value in values[period:]:
        current = value * k + current * (1 - k)
        out.append(current)
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    """Average True Range (Wilder), i.e. how much price typically moves per candle."""
    true_ranges = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    if len(true_ranges) < period:
        raise ValueError("not enough candles for ATR")
    value = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def crossover_signal(closes: list[float], fast: int, slow: int) -> str | None:
    """'LONG' when the fast EMA crosses above the slow EMA on the last candle, 'SHORT' when below."""
    fast_ema = ema(closes, fast)[-2:]
    slow_ema = ema(closes, slow)[-2:]
    if len(fast_ema) < 2 or len(slow_ema) < 2:
        return None
    if fast_ema[0] <= slow_ema[0] and fast_ema[1] > slow_ema[1]:
        return "LONG"
    if fast_ema[0] >= slow_ema[0] and fast_ema[1] < slow_ema[1]:
        return "SHORT"
    return None

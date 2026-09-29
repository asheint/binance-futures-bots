"""Indicator math. Every function returns a list the same length as its input, with None until there is enough data."""
from __future__ import annotations


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = values[i] * k + current * (1 - k)
        out[i] = current
    return out


def rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Wilder's RSI: above 70 = stretched up (overbought), below 30 = stretched down (oversold)."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out

    def value(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        return 100 - 100 / (1 + gain / loss)

    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(max(c, 0) for c in changes[:period]) / period
    avg_loss = sum(max(-c, 0) for c in changes[:period]) / period
    out[period] = value(avg_gain, avg_loss)
    for i in range(period + 1, len(closes)):
        change = changes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0)) / period
        out[i] = value(avg_gain, avg_loss)
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    """Average True Range: how far price typically moves in one candle."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out
    true_ranges = [highs[0] - lows[0]] + [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])) for i in range(1, n)
    ]
    current = sum(true_ranges[1:period + 1]) / period
    out[period] = current
    for i in range(period + 1, n):
        current = (current * (period - 1) + true_ranges[i]) / period
        out[i] = current
    return out


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list[float | None], list[float | None]]:
    """MACD line (fast EMA - slow EMA) and its signal line (EMA of the MACD line)."""
    fast_ema, slow_ema = ema(closes, fast), ema(closes, slow)
    line: list[float | None] = [f - s if f is not None and s is not None else None for f, s in zip(fast_ema, slow_ema)]
    start = next((i for i, v in enumerate(line) if v is not None), len(line))
    signal_part = ema([v for v in line[start:] if v is not None], signal)
    return line, [None] * start + signal_part


def supertrend(highs: list[float], lows: list[float], closes: list[float], period: int = 10,
               mult: float = 3.0) -> list[int | None]:
    """Supertrend direction per candle: 1 = up (price above the band), -1 = down."""
    atr_values = atr(highs, lows, closes, period)
    out: list[int | None] = [None] * len(closes)
    upper = lower = None
    direction = 1
    for i, a in enumerate(atr_values):
        if a is None:
            continue
        mid = (highs[i] + lows[i]) / 2
        new_upper, new_lower = mid + mult * a, mid - mult * a
        if upper is None:
            upper, lower = new_upper, new_lower
        else:
            upper = new_upper if new_upper < upper or closes[i - 1] > upper else upper
            lower = new_lower if new_lower > lower or closes[i - 1] < lower else lower
        if closes[i] > upper:
            direction = 1
        elif closes[i] < lower:
            direction = -1
        out[i] = direction
    return out


def adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    """Wilder's ADX: trend strength regardless of direction. Below ~20 = choppy / sideways, above ~25 = trending."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period * 2:
        return out
    tr, plus_dm, minus_dm = [0.0] * n, [0.0] * n, [0.0] * n
    for i in range(1, n):
        up, down = highs[i] - highs[i - 1], lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr_s, plus_s, minus_s = sum(tr[1:period + 1]), sum(plus_dm[1:period + 1]), sum(minus_dm[1:period + 1])
    dx: list[float] = []
    for i in range(period + 1, n):
        atr_s = atr_s - atr_s / period + tr[i]
        plus_s = plus_s - plus_s / period + plus_dm[i]
        minus_s = minus_s - minus_s / period + minus_dm[i]
        plus_di = 100 * plus_s / atr_s if atr_s else 0.0
        minus_di = 100 * minus_s / atr_s if atr_s else 0.0
        total = plus_di + minus_di
        dx.append(100 * abs(plus_di - minus_di) / total if total else 0.0)
        if len(dx) == period:
            value = sum(dx) / period
            out[i] = value
        elif len(dx) > period:
            value = (out[i - 1] * (period - 1) + dx[-1]) / period  # type: ignore[operator]
            out[i] = value
    return out

"""Reads a chart like a trader: structure, zones, Fibonacci, indicators, candle patterns, with plain-English notes.

  python analysis.py BTCUSDT 4h      # analyse the real market and print the notes
"""
from __future__ import annotations

import sys
from dataclasses import asdict

from indicators import atr, ema, rsi, sma
from levels import Zone, fibonacci, find_zones
from models import Candle, candles_from_klines, price_text
from patterns import Pattern, find_patterns
from structure import StructureBreak, find_breaks, find_swings, trend_state


def analyze(candles: list[Candle], swing_bars: int = 5, detail: bool = True) -> dict:
    """detail=False skips the chart-only parts (notes, EMA line series) for fast backtests."""
    if len(candles) < 60:
        raise ValueError("need at least 60 closed candles to analyse")
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]

    atr_values = atr(highs, lows, closes)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi_values = rsi(closes)
    volume_avg = sma(volumes, 20)

    swings = find_swings(candles, atr_values, swing_bars, swing_bars)
    breaks = find_breaks(candles, swings)
    divergences = find_divergences(swings, rsi_values, len(candles))
    trend, trend_text = trend_state(swings, breaks)
    price = closes[-1]
    atr_now = atr_values[-1] or (highs[-1] - lows[-1])
    supports, resistances = find_zones(swings, atr_now, price)
    fib = fibonacci(swings, trend, min_leg=atr_now * 3)
    patterns = find_patterns(candles, atr_values)
    volume_ratio = volumes[-1] / volume_avg[-1] if volume_avg[-1] else None

    notes = build_notes(len(candles), price, trend, trend_text, breaks, supports, resistances, fib, patterns,
                        divergences, ema50[-1], ema200[-1], rsi_values[-1], volume_ratio) if detail else []

    def series(values: list[float | None]) -> list[dict]:
        if not detail:
            return []
        return [{"time": c.time, "value": v} for c, v in zip(candles, values) if v is not None]

    return {
        "price": price,
        "time": candles[-1].time,
        "trend": trend,
        "swings": [{"time": s.time, "price": s.price, "kind": s.kind, "label": s.label} for s in swings],
        "breaks": [{"time": b.time, "price": b.price, "direction": b.direction, "kind": b.kind,
                    "ago": len(candles) - 1 - b.index} for b in breaks[-10:]],
        "zones": {"support": [asdict(z) for z in supports], "resistance": [asdict(z) for z in resistances]},
        "fib": fib,
        "patterns": [{"time": p.time, "name": p.name, "short": p.short, "direction": p.direction,
                      "ago": len(candles) - 1 - p.index} for p in patterns],
        "divergences": divergences,
        "ema50": series(ema50),
        "ema200": series(ema200),
        "indicators": {"rsi": rsi_values[-1], "atr": atr_now, "ema50": ema50[-1], "ema200": ema200[-1],
                       "volume_ratio": volume_ratio},
        "notes": notes,
    }


RECENT_DIVERGENCE = 15  # candles


def find_divergences(swings: list, rsi_values: list[float | None], count: int, lookback: int = 150,
                     min_rsi_gap: float = 3.0) -> list[dict]:
    """Price and RSI disagreeing at two consecutive swing highs (or lows).
    Regular divergence = momentum fading, the trend may reverse.
    Hidden divergence = momentum says the pullback is over and the trend should continue."""
    found = []
    previous = {"high": None, "low": None}
    for swing in swings:
        prev = previous[swing.kind]
        previous[swing.kind] = swing
        if prev is None or swing.index < count - lookback:
            continue
        rsi_prev, rsi_now = rsi_values[prev.index], rsi_values[swing.index]
        if rsi_prev is None or rsi_now is None or abs(rsi_now - rsi_prev) < min_rsi_gap:
            continue
        if swing.kind == "high":
            if swing.price > prev.price and rsi_now < rsi_prev:
                kind, variant = "bearish", "regular"
            elif swing.price < prev.price and rsi_now > rsi_prev:
                kind, variant = "bearish", "hidden"
            else:
                continue
        else:
            if swing.price < prev.price and rsi_now > rsi_prev:
                kind, variant = "bullish", "regular"
            elif swing.price > prev.price and rsi_now < rsi_prev:
                kind, variant = "bullish", "hidden"
            else:
                continue
        found.append({"kind": kind, "variant": variant, "swing": swing.kind,
                      "time": swing.time, "price": swing.price, "rsi": rsi_now,
                      "prev_time": prev.time, "prev_price": prev.price, "prev_rsi": rsi_prev,
                      "ago": count - 1 - swing.index})
    return found


def divergence_text(d: dict) -> str:
    move = f"({price_text(d['prev_price'])} → {price_text(d['price'])}, RSI {d['prev_rsi']:.0f} → {d['rsi']:.0f})"
    if d["kind"] == "bearish" and d["variant"] == "regular":
        return f"Bearish divergence {d['ago']} candles ago: price made a higher high but RSI a lower high {move}. Buyers are losing strength; the rise may be tiring."
    if d["kind"] == "bullish" and d["variant"] == "regular":
        return f"Bullish divergence {d['ago']} candles ago: price made a lower low but RSI a higher low {move}. Sellers are losing strength; the drop may be tiring."
    if d["kind"] == "bearish":
        return f"Hidden bearish divergence {d['ago']} candles ago: price made a lower high but RSI a higher high {move}. In a downtrend this often means the bounce is weak and the drop continues."
    return f"Hidden bullish divergence {d['ago']} candles ago: price made a higher low but RSI a lower low {move}. In an uptrend this often means the pullback is done and the rise continues."


def note(topic: str, text: str, tone: str = "neutral") -> dict:
    return {"topic": topic, "text": text, "tone": tone}


def build_notes(count: int, price: float, trend: str, trend_text: str, breaks: list[StructureBreak],
                supports: list[Zone], resistances: list[Zone], fib: dict | None, patterns: list[Pattern],
                divergences: list[dict], ema50: float | None, ema200: float | None, rsi_now: float | None,
                volume_ratio: float | None) -> list[dict]:
    notes = [note("Structure", trend_text, {"up": "bull", "down": "bear"}.get(trend, "neutral"))]

    if breaks:
        b = breaks[-1]
        ago = count - 1 - b.index
        up = b.direction == "up"
        meaning = ("the trend continuing" if b.kind == "BOS"
                   else "a possible trend change, the first break against the previous direction")
        where = "above the last swing high" if up else "below the last swing low"
        notes.append(note("Structure break",
                          f"{b.kind} {'up' if up else 'down'} {ago} candles ago: a candle closed {where} at "
                          f"{price_text(b.price)}. This signals {meaning}.", "bull" if up else "bear"))

    if ema50 is not None and ema200 is not None:
        above, stacked_up = price > ema200, ema50 > ema200
        text = (f"Price is {'above' if above else 'below'} EMA 200 ({price_text(ema200)}) and EMA 50 is "
                f"{'above' if stacked_up else 'below'} EMA 200.")
        if trend == "up" and above and stacked_up:
            text, tone = text + " The EMA filter agrees with the uptrend.", "bull"
        elif trend == "down" and not above and not stacked_up:
            text, tone = text + " The EMA filter agrees with the downtrend.", "bear"
        elif trend in ("up", "down"):
            text, tone = text + " The EMA filter does NOT fully agree with the structure, so be more careful.", "warn"
        else:
            tone = "bull" if above and stacked_up else "bear" if not above and not stacked_up else "neutral"
        notes.append(note("EMA 50/200", text, tone))
    else:
        notes.append(note("EMA 50/200", "Not enough candles for EMA 200 yet."))

    for zones, side in ((supports, "support"), (resistances, "resistance")):
        if not zones:
            notes.append(note(side.title(), f"No {side} zone with 2+ touches in view."))
            continue
        z = zones[0]
        touches = f"price turned here {z.touches} times"
        if z.highs and z.lows:
            touches += f" ({z.lows} bounce{'s' if z.lows > 1 else ''}, {z.highs} rejection{'s' if z.highs > 1 else ''}; the level has flipped roles)"
        if z.inside:
            where = f"Price is inside this zone right now; this is where {'buyers' if side == 'support' else 'sellers'} stepped in before."
        else:
            edge = z.high if side == "support" else z.low
            where = f"Price is {abs(price - edge) / price * 100:.2f}% {'above' if side == 'support' else 'below'} it."
        notes.append(note(side.title(), f"Nearest {side} {price_text(z.low)}–{price_text(z.high)}: {touches}. {where}",
                          "bull" if side == "support" else "bear"))

    if fib:
        low, high = fib["golden"]
        up = fib["direction"] == "up"
        leg = f"{price_text(fib['start']['price'])} → {price_text(fib['end']['price'])}"
        text = (f"Last {'up' if up else 'down'}-leg {leg}. A {'pullback' if up else 'bounce'} often "
                f"{'pauses' if up else 'stalls'} in the 0.5–0.618 golden zone {price_text(low)}–{price_text(high)}.")
        tone = "neutral"
        if low <= price <= high:
            text += " Price is in the golden zone now."
            tone = "bull" if up else "bear"
        overlap = next((z for z in supports + resistances if z.low <= high and z.high >= low), None)
        if overlap:
            text += (f" Confluence: it overlaps the {overlap.kind} zone {price_text(overlap.low)}–{price_text(overlap.high)} "
                     f"({overlap.touches} touches), so there are two reasons for price to react there.")
        notes.append(note("Fibonacci", text, tone))

    recent = [p for p in patterns if p.index >= count - 3]
    if recent:
        p = recent[-1]
        ago = count - 1 - p.index
        when = "on the last closed candle" if ago == 0 else f"{ago} candle{'s' if ago > 1 else ''} ago"
        notes.append(note("Candles", f"{p.name} {when}: {p.meaning}", "bull" if p.direction == "bull" else "bear"))
    else:
        notes.append(note("Candles", "No engulfing, hammer or shooting star on the last 3 candles."))

    recent_divergences = [d for d in divergences if d["ago"] <= RECENT_DIVERGENCE]
    if recent_divergences:
        d = recent_divergences[-1]
        notes.append(note("Divergence", divergence_text(d), "bull" if d["kind"] == "bullish" else "bear"))
    else:
        notes.append(note("Divergence", "No RSI divergence at the recent swings: price and momentum agree."))

    if rsi_now is not None:
        if rsi_now >= 70:
            text, tone = f"RSI {rsi_now:.0f}: overbought. The move up is stretched; buying here is chasing.", "warn"
        elif rsi_now <= 30:
            text, tone = f"RSI {rsi_now:.0f}: oversold. The move down is stretched; selling here is chasing.", "warn"
        else:
            text, tone = f"RSI {rsi_now:.0f}: neutral momentum, not stretched either way.", "neutral"
        notes.append(note("RSI", text, tone))

    if volume_ratio is not None:
        if volume_ratio >= 1.5:
            text = f"Last candle volume is {volume_ratio:.1f}× the 20-candle average: strong participation behind the move."
        elif volume_ratio <= 0.7:
            text = f"Last candle volume is only {volume_ratio:.1f}× average: quiet market, moves are less reliable."
        else:
            text = f"Volume is normal ({volume_ratio:.1f}× average)."
        notes.append(note("Volume", text))

    return notes


if __name__ == "__main__":
    from client import FuturesClient
    from config import BASE_URLS

    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
    interval = sys.argv[2] if len(sys.argv) > 2 else "4h"
    market = FuturesClient("", "", BASE_URLS["live"])
    result = analyze(candles_from_klines(market.klines(symbol, interval, limit=1000)))

    print(f"{symbol} {interval} | price {price_text(result['price'])} | trend {result['trend'].upper()}\n")
    for n in result["notes"]:
        print(f"[{n['topic']}] {n['text']}")
    print("\nLast 8 swings:", ", ".join(f"{s['label'] or s['kind']} {price_text(s['price'])}" for s in result["swings"][-8:]))
    for side in ("support", "resistance"):
        print(f"{side.title()} zones:", ", ".join(f"{price_text(z['low'])}–{price_text(z['high'])} ×{z['touches']}"
                                                  for z in result["zones"][side]) or "none")

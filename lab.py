"""Strategy lab: tests several different trading ideas under the same honest rules.

  python lab.py            (run `python data.py` first)

Rules for every strategy:
- signal on a candle close, entry at the NEXT candle's open
- stop at least 1.2% away (lesson from backtest v1); if stop and target are both touched in a candle, stop first
- fees 0.05% per side, slippage 0.02%, funding 0.01% per 8h
- one position at a time per strategy and coin
- every idea is run with several settings; the settings are picked on 2023-24 and judged on 2025-26
- an idea only passes if MOST of its settings also make money on 2025-26 (not one lucky combination)
- RANDOM entries with the same stop/target rules are the control group a real edge must beat
"""
from __future__ import annotations

import bisect
import csv
import math
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import product

from data import DATA_DIR, load_candles, load_funding
from indicators import atr, ema
from models import Candle

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())
TAKER_FEE = 0.0005
SLIPPAGE = 0.0002
FUNDING_PER_8H = 0.0001
MIN_STOP_PCT = 0.012
RISK_PER_TRADE = 0.01
MIN_TRADES = 30
TIMEFRAMES = {
    "1h": {"seconds": 3_600, "bars_per_8h": 8, "max_hold": 72},
    "4h": {"seconds": 14_400, "bars_per_8h": 2, "max_hold": 42},
    "1d": {"seconds": 86_400, "bars_per_8h": 1 / 3, "max_hold": 120},
}
LAB_DIR = DATA_DIR / "lab"


@dataclass
class Signal:
    index: int                    # candle whose close produced the signal
    side: str                     # "long" / "short"
    stop_dist: float              # distance from price to stop
    rr: float | None = None       # fixed target in R, or None
    trail_atr: float | None = None  # trailing stop distance in ATRs, or None


@dataclass
class Market:
    symbol: str
    tf: str
    candles: list[Candle]
    closes: list[float] = field(default_factory=list)
    highs: list[float] = field(default_factory=list)
    lows: list[float] = field(default_factory=list)
    atr: list[float | None] = field(default_factory=list)
    funding_rate: list[float | None] = field(default_factory=list)
    funding_pct: list[float | None] = field(default_factory=list)


# ---- data ----------------------------------------------------------------------------

def daily_from_4h(candles: list[Candle]) -> list[Candle]:
    days: dict[int, list[Candle]] = {}
    for c in candles:
        days.setdefault(c.time - c.time % 86_400, []).append(c)
    return [Candle(day, g[0].open, max(x.high for x in g), min(x.low for x in g), g[-1].close, sum(x.volume for x in g))
            for day, g in sorted(days.items()) if len(g) == 6]


def market_from_candles(symbol: str, tf: str, candles: list[Candle]) -> Market:
    m = Market(symbol, tf, candles)
    m.closes = [c.close for c in candles]
    m.highs = [c.high for c in candles]
    m.lows = [c.low for c in candles]
    m.atr = atr(m.highs, m.lows, m.closes)
    m.funding_rate = [None] * len(candles)
    m.funding_pct = [None] * len(candles)
    return m


def build_market(symbol: str, tf: str) -> Market:
    candles = daily_from_4h(load_candles(symbol, "4h")) if tf == "1d" else load_candles(symbol, tf)
    m = market_from_candles(symbol, tf, candles)

    funding = load_funding(symbol)
    times = [t for t, _ in funding]
    rates = [r for _, r in funding]
    window = 270  # ~90 days of 8h funding
    pct = [None] * len(rates)
    for k in range(window, len(rates)):
        pct[k] = sum(1 for x in rates[k - window:k] if x < rates[k]) / window * 100
    m.funding_rate = [None] * len(candles)
    m.funding_pct = [None] * len(candles)
    seconds = TIMEFRAMES[tf]["seconds"]
    for i, c in enumerate(candles):
        k = bisect.bisect_right(times, c.time + seconds) - 1  # latest funding known at this candle's close
        if k >= 0:
            m.funding_rate[i], m.funding_pct[i] = rates[k], pct[k]
    return m


# ---- strategies (each only looks at candles up to the signal candle) --------------------

def liquidity_sweep(m: Market, lookback: int, trend_filter: bool, rr: float) -> list[Signal]:
    """Price pokes beyond an obvious high/low (where stops sit) and closes back inside: the sweep failed."""
    trend = ema(m.closes, 200) if trend_filter else None
    out = []
    for i in range(lookback + 2, len(m.candles)):
        a, c = m.atr[i], m.candles[i]
        if not a or (trend_filter and trend[i] is None):
            continue
        low_level = min(m.lows[i - lookback:i - 2])
        high_level = max(m.highs[i - lookback:i - 2])
        if c.low < low_level < c.close and (not trend_filter or c.close > trend[i]):
            out.append(Signal(i, "long", c.close - c.low + 0.5 * a, rr))
        elif c.high > high_level > c.close and (not trend_filter or c.close < trend[i]):
            out.append(Signal(i, "short", c.high - c.close + 0.5 * a, rr))
    return out


def trend_pullback(m: Market, fast: int, stop_atr: float, rr: float) -> list[Signal]:
    """In a trend (fast EMA beyond EMA 200), price dips into the fast EMA and closes back out with a trend candle."""
    ema_fast, ema_slow = ema(m.closes, fast), ema(m.closes, 200)
    out = []
    for i in range(5, len(m.candles)):
        a, c = m.atr[i], m.candles[i]
        if not a or ema_fast[i] is None or ema_slow[i] is None:
            continue
        if ema_fast[i] > ema_slow[i] and c.low <= ema_fast[i] < c.close and c.close > c.open:
            out.append(Signal(i, "long", c.close - (min(m.lows[i - 4:i + 1]) - stop_atr * a), rr))
        elif ema_fast[i] < ema_slow[i] and c.high >= ema_fast[i] > c.close and c.close < c.open:
            out.append(Signal(i, "short", (max(m.highs[i - 4:i + 1]) + stop_atr * a) - c.close, rr))
    return out


def breakout_retest(m: Market, lookback: int, window: int, rr: float) -> list[Signal]:
    """Close breaks the range high/low, then within `window` candles price comes back to the level and holds it."""
    out = []
    pending = {"long": None, "short": None}  # (level, expires_at)
    for i in range(lookback, len(m.candles)):
        a, c = m.atr[i], m.candles[i]
        if not a:
            continue
        long_p, short_p = pending["long"], pending["short"]
        if long_p:
            level, expires = long_p
            if i > expires or c.close < level - 0.5 * a:
                pending["long"] = None
            elif c.low <= level + 0.25 * a and c.close > level and c.close > c.open:
                out.append(Signal(i, "long", c.close - (min(c.low, level) - a), rr))
                pending["long"] = None
        if short_p:
            level, expires = short_p
            if i > expires or c.close > level + 0.5 * a:
                pending["short"] = None
            elif c.high >= level - 0.25 * a and c.close < level and c.close < c.open:
                out.append(Signal(i, "short", (max(c.high, level) + a) - c.close, rr))
                pending["short"] = None
        range_high = max(m.highs[i - lookback:i])
        range_low = min(m.lows[i - lookback:i])
        if c.close > range_high:
            pending["long"] = (range_high, i + window)
        elif c.close < range_low:
            pending["short"] = (range_low, i + window)
    return out


def trend_following(m: Market, lookback: int, trail: float) -> list[Signal]:
    """Classic trend following: buy a new `lookback` high above EMA 100 (sell new lows below it),
    no fixed target, exit with a trailing stop `trail` ATRs behind the best price."""
    trend = ema(m.closes, 100)
    out = []
    for i in range(lookback, len(m.candles)):
        a, c = m.atr[i], m.candles[i]
        if not a or trend[i] is None:
            continue
        if c.close > max(m.highs[i - lookback:i]) and c.close > trend[i]:
            out.append(Signal(i, "long", 2 * a, None, trail))
        elif c.close < min(m.lows[i - lookback:i]) and c.close < trend[i]:
            out.append(Signal(i, "short", 2 * a, None, trail))
    return out


def funding_extreme(m: Market, pct: int, confirm: bool, rr: float) -> list[Signal]:
    """When funding is unusually high the crowd is heavily long (and vice versa): bet against the crowd,
    optionally only after a candle in our direction confirms."""
    out = []
    for i in range(len(m.candles)):
        a, c, p, rate = m.atr[i], m.candles[i], m.funding_pct[i], m.funding_rate[i]
        if not a or p is None:
            continue
        if p >= pct and rate > 0 and (not confirm or c.close < c.open):
            out.append(Signal(i, "short", 1.5 * a, rr))
        elif p <= 100 - pct and rate < 0 and (not confirm or c.close > c.open):
            out.append(Signal(i, "long", 1.5 * a, rr))
    return out


def random_entries(m: Market, seed: int, rr: float) -> list[Signal]:
    """Control group: random time, random direction, same stop and target rules."""
    rng = random.Random(seed * 1000 + len(m.candles))
    return [Signal(i, rng.choice(("long", "short")), 1.5 * m.atr[i], rr)
            for i in range(200, len(m.candles)) if m.atr[i] and rng.random() < 0.02]


STRATEGIES = [
    ("Liquidity sweep reversal", liquidity_sweep, ["1h", "4h"],
     {"lookback": [24, 48, 96], "trend_filter": [False, True], "rr": [1.5, 2.0]}),
    ("Trend pullback to EMA", trend_pullback, ["1h", "4h"],
     {"fast": [20, 50], "stop_atr": [0.5, 1.0], "rr": [1.5, 2.0, 3.0]}),
    ("Breakout + retest", breakout_retest, ["1h", "4h"],
     {"lookback": [20, 55], "window": [5, 10], "rr": [1.5, 2.0, 3.0]}),
    ("Trend following (trailing stop)", trend_following, ["4h", "1d"],
     {"lookback": [20, 40, 55], "trail": [2.0, 3.0, 4.0]}),
    ("Funding rate extremes", funding_extreme, ["1h", "4h"],
     {"pct": [90, 95, 98], "confirm": [False, True], "rr": [1.5, 2.0]}),
    ("RANDOM entries (control)", random_entries, ["1h", "4h", "1d"],
     {"seed": [1, 2, 3, 4, 5, 6], "rr": [2.0]}),
]


# ---- simulation ------------------------------------------------------------------------

def simulate(m: Market, signals: list[Signal]) -> list[dict]:
    cfg = TIMEFRAMES[m.tf]
    trades = []
    busy_until = -1
    for s in signals:
        start = s.index + 1
        if s.index <= busy_until or start >= len(m.candles):
            continue
        long = s.side == "long"
        entry = m.candles[start].open * (1 + SLIPPAGE if long else 1 - SLIPPAGE)
        dist = max(s.stop_dist, entry * MIN_STOP_PCT)
        stop = entry - dist if long else entry + dist
        target = None if s.rr is None else (entry + s.rr * dist if long else entry - s.rr * dist)
        best = entry
        last = min(start + cfg["max_hold"], len(m.candles)) - 1
        exit_index, exit_price, reason = last, m.candles[last].close, "time"
        for j in range(start, last + 1):
            c = m.candles[j]
            if long and c.low <= stop or not long and c.high >= stop:
                gap = (c.open < stop if long else c.open > stop) and j > start
                fill = c.open if gap else stop
                exit_index, exit_price = j, fill * (1 - SLIPPAGE if long else 1 + SLIPPAGE)
                reason = "stop" if (stop - entry) * (1 if long else -1) < 0 else "trail"
                break
            if target is not None and (long and c.high >= target or not long and c.low <= target):
                exit_index, exit_price, reason = j, target, "target"
                break
            if s.trail_atr and m.atr[j]:
                if long:
                    best = max(best, c.high)
                    stop = max(stop, best - s.trail_atr * m.atr[j])
                else:
                    best = min(best, c.low)
                    stop = min(stop, best + s.trail_atr * m.atr[j])
        bars = exit_index - start + 1
        gross = (exit_price - entry) / dist if long else (entry - exit_price) / dist
        costs = ((entry + exit_price) * TAKER_FEE + entry * FUNDING_PER_8H * bars / cfg["bars_per_8h"]) / dist
        trades.append({"symbol": m.symbol, "side": s.side, "time": m.candles[start].time,
                       "exit_time": m.candles[exit_index].time + TIMEFRAMES[m.tf]["seconds"],
                       "date": datetime.fromtimestamp(m.candles[start].time, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                       "entry": entry, "exit": exit_price, "reason": reason, "bars": bars,
                       "stop_pct": dist / entry * 100, "r_gross": gross, "r": gross - costs})
        busy_until = exit_index
    return trades


def metrics(trades: list[dict]) -> dict:
    rs = [t["r"] for t in sorted(trades, key=lambda t: t["time"])]
    if not rs:
        return {"trades": 0, "win": 0.0, "avg": 0.0, "pf": 0.0, "dd": 0.0}
    wins = [r for r in rs if r > 0]
    loss = abs(sum(r for r in rs if r <= 0))
    equity = peak = dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return {"trades": len(rs), "win": len(wins) / len(rs) * 100, "avg": sum(rs) / len(rs),
            "pf": sum(wins) / loss if loss else math.inf, "dd": dd}


def account(trades: list[dict]) -> tuple[float, float]:
    """Compounded return and worst drop at 1% risk per trade (both coins traded side by side)."""
    equity = peak = 1.0
    worst = 0.0
    for t in sorted(trades, key=lambda t: t["exit_time"]):
        equity *= 1 + RISK_PER_TRADE * t["r"]
        peak = max(peak, equity)
        worst = max(worst, 1 - equity / peak)
    return (equity - 1) * 100, worst * 100


# ---- report -----------------------------------------------------------------------------

def table(headers: list[str], rows: list[list]) -> str:
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
                     + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows])


def short_stats(st: dict) -> str:
    if not st["trades"]:
        return "no trades"
    pf = "∞" if st["pf"] == math.inf else f"{st['pf']:.2f}"
    return f"{st['trades']} trades, {st['win']:.0f}% win, {st['avg']:+.2f}R, PF {pf}"


def params_text(params: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in params.items())


def main() -> None:
    started = time.time()
    markets = {(s, tf): build_market(s, tf) for s in SYMBOLS for tf in ("1h", "4h", "1d")}
    print("Data loaded:", ", ".join(f"{s} {tf}: {len(m.candles)}" for (s, tf), m in markets.items()), flush=True)

    summary_rows, details, picked_trades = [], [], []
    for name, fn, timeframes, grid in STRATEGIES:
        for tf in timeframes:
            combos = []
            for values in product(*grid.values()):
                params = dict(zip(grid.keys(), values))
                trades = [t for s in SYMBOLS for t in simulate(markets[(s, tf)], fn(markets[(s, tf)], **params))]
                in_sample = [t for t in trades if t["time"] < SPLIT]
                out_sample = [t for t in trades if t["time"] >= SPLIT]
                combos.append({"params": params, "trades": trades, "is": metrics(in_sample), "oos": metrics(out_sample),
                               "oos_trades": out_sample})

            eligible = [c for c in combos if c["is"]["trades"] >= 20] or combos
            pick = max(eligible, key=lambda c: c["is"]["avg"])
            with_trades = [c for c in combos if c["oos"]["trades"]]
            profitable = sum(1 for c in with_trades if c["oos"]["avg"] > 0)
            share = profitable / len(with_trades) if with_trades else 0
            median_oos = statistics.median(c["oos"]["avg"] for c in with_trades) if with_trades else 0.0
            ret, worst = account(pick["oos_trades"])

            if name.startswith("RANDOM"):
                verdict = "control"
            elif pick["is"]["avg"] > 0 and pick["oos"]["avg"] >= 0.15 and pick["oos"]["trades"] >= MIN_TRADES and share >= 0.6:
                verdict = "✅ PASS"
            elif pick["oos"]["avg"] > 0 and share >= 0.5:
                verdict = "🟡 PROMISING"
            else:
                verdict = "❌ FAIL"

            summary_rows.append([name, tf, f"{profitable}/{len(with_trades)}", f"{median_oos:+.2f}R",
                                 f"{pick['is']['avg']:+.2f}R", short_stats(pick["oos"]),
                                 f"{ret:+.0f}% / {worst:.0f}%", verdict])
            print(f"{name} {tf}: {verdict} | picked {params_text(pick['params'])} | 2023-24 {short_stats(pick['is'])} | "
                  f"2025-26 {short_stats(pick['oos'])} | profitable settings {profitable}/{len(with_trades)}", flush=True)

            grid_rows = [[params_text(c["params"]), short_stats(c["is"]), short_stats(c["oos"])]
                         for c in sorted(combos, key=lambda c: -c["is"]["avg"])]
            by_group = []
            for symbol in SYMBOLS:
                for side in ("long", "short"):
                    group = [t for t in pick["oos_trades"] if t["symbol"] == symbol and t["side"] == side]
                    by_group.append([f"{symbol} {side}", short_stats(metrics(group))])
            details.append(f"\n### {name} ({tf}): {verdict}\n\nPicked on 2023–24: `{params_text(pick['params'])}`\n\n"
                           + table(["2025–26 group", "Result"], by_group) + "\n\nAll settings (sorted by 2023–24 result):\n\n"
                           + table(["Settings", "2023–24", "2025–26"], grid_rows) + "\n")
            picked_trades += [{"strategy": name, "tf": tf, **t} for t in pick["trades"]]

    report = ["# Strategy lab report\n",
              f"BTCUSDT + ETHUSDT · settings picked on data before {datetime.fromtimestamp(SPLIT, timezone.utc):%Y-%m-%d}, "
              "judged on data after it · costs: 0.05% fee per side, 0.02% slippage, 0.01% funding per 8h · stops at least 1.2% away\n",
              "**PASS** = the picked settings made ≥ +0.15R per trade on 2025–26 with ≥ 30 trades, AND at least 60% of all settings "
              "were profitable on 2025–26. **PROMISING** = profitable but not all conditions met. "
              "The RANDOM rows show what a strategy with no edge looks like.\n",
              table(["Strategy", "TF", "Settings profitable 2025–26", "Median 2025–26", "Picked: 2023–24",
                     "Picked: 2025–26", "Account 2025–26 (return / worst drop)", "Verdict"], summary_rows),
              "\n## Details", *details]
    LAB_DIR.mkdir(parents=True, exist_ok=True)
    (LAB_DIR / "report.md").write_text("\n".join(report), encoding="utf-8")
    with (LAB_DIR / "picked_trades.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(picked_trades[0].keys()))
        writer.writeheader()
        writer.writerows(picked_trades)
    print("\n" + table(["Strategy", "TF", "Settings profitable 2025–26", "Median 2025–26", "Picked: 2023–24",
                        "Picked: 2025–26", "Account 2025–26", "Verdict"], summary_rows))
    print(f"\nDone in {time.time() - started:.0f}s. Full report: {LAB_DIR / 'report.md'}")


if __name__ == "__main__":
    main()

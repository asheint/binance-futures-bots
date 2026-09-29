"""Intraday momentum lab: can a fast "volume-spike breakout" catch moves like FIL's +22% day?

  python intraday_lab.py

Signal on a candle close (long only):
  close breaks the highest high of the previous L candles
  volume >= V x its 50-candle average
  the candle closes in the top 30% of its range
  optional trend filter: close above EMA 200 (same timeframe)
Entry at the next open. Stop: signal candle low - 0.2 ATR (at least 1.2% away).
Exits tested: fixed 2R target, or a stop following the lowest low of the last 10 / 20 candles; time exit after max_hold.

Honest rules (same as lab.py): fees, slippage, funding, one position per coin, portfolio max 6 open at 0.75% risk,
settings picked on the older data and judged on the last 12 months, random entries with the same stop/exit as control.
"""
from __future__ import annotations

import random
import statistics
import time
from collections import deque
from datetime import datetime, timezone
from itertools import product

from client import FuturesClient
from config import BASE_URLS
from data import DATA_DIR, download, load_candles
from indicators import atr, ema, sma
from train_trend import portfolio

INTRADAY_DIR = DATA_DIR / "intraday"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT",
           "AVAXUSDT", "LTCUSDT", "DOTUSDT", "TRXUSDT", "ATOMUSDT", "NEARUSDT", "FILUSDT", "UNIUSDT",
           "AAVEUSDT", "ETCUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "BCHUSDT", "XLMUSDT"]
TIMEFRAMES = {"1h": {"years": 3, "bars_per_8h": 8, "max_hold": 48},
              "15m": {"years": 2, "bars_per_8h": 32, "max_hold": 96}}
OOS_START = int(datetime(2025, 9, 13, tzinfo=timezone.utc).timestamp())
TAKER_FEE, SLIPPAGE, FUNDING_PER_8H, MIN_STOP_PCT = 0.0005, 0.0002, 0.0001, 0.012
VOLUME_MULTS, LOOKBACKS, TREND_FILTER = (3, 5), (48, 96), (False, True)
EXITS = ("2R target", "trail 10-candle low", "trail 20-candle low")
RANDOM_SEEDS = 5


def rolling_max_before(values: list[float], n: int) -> list[float | None]:
    """out[i] = max(values[i-n:i]), excluding candle i."""
    out: list[float | None] = [None] * len(values)
    window: deque[int] = deque()
    for i, v in enumerate(values):
        if i >= n:
            out[i] = values[window[0]]
        while window and values[window[-1]] <= v:
            window.pop()
        window.append(i)
        if window[0] <= i - n:
            window.popleft()
    return out


def rolling_min_including(values: list[float], n: int) -> list[float]:
    """out[i] = min(values[i-n+1:i+1])."""
    out = [0.0] * len(values)
    window: deque[int] = deque()
    for i, v in enumerate(values):
        while window and values[window[-1]] >= v:
            window.pop()
        window.append(i)
        if window[0] <= i - n:
            window.popleft()
        out[i] = values[window[0]]
    return out


class Series:
    def __init__(self, symbol: str, tf: str):
        candles = load_candles(symbol, tf, directory=INTRADAY_DIR)
        self.symbol, self.tf = symbol, tf
        self.time = [c.time for c in candles]
        self.open = [c.open for c in candles]
        self.high = [c.high for c in candles]
        self.low = [c.low for c in candles]
        self.close = [c.close for c in candles]
        self.volume = [c.volume for c in candles]
        del candles
        self.n = len(self.close)
        self.atr = atr(self.high, self.low, self.close)
        self.ema200 = ema(self.close, 200)
        self.vol_avg = sma(self.volume, 50)
        self.highest = {lb: rolling_max_before(self.high, lb) for lb in LOOKBACKS}
        self.lowest = {10: rolling_min_including(self.low, 10), 20: rolling_min_including(self.low, 20)}


def signals(s: Series, vol_mult: float, lookback: int, trend: bool) -> list[tuple[int, float]]:
    """[(candle index, stop distance from close)]"""
    out = []
    highest = s.highest[lookback]
    for i in range(200, s.n - 1):
        a, avg = s.atr[i], s.vol_avg[i - 1]
        if not a or not avg or highest[i] is None:
            continue
        rng = s.high[i] - s.low[i]
        if (s.close[i] > highest[i] and s.volume[i] >= vol_mult * avg and rng > 0
                and (s.close[i] - s.low[i]) / rng >= 0.7 and (not trend or s.close[i] > s.ema200[i])):
            out.append((i, s.close[i] - (s.low[i] - 0.2 * a)))
    return out


def random_signals(s: Series, seed: int, probability: float) -> list[tuple[int, float]]:
    rng = random.Random(seed * 7919 + sum(map(ord, s.symbol + s.tf)))
    return [(i, max(s.close[i] - (s.low[i] - 0.2 * s.atr[i]), 0)) for i in range(200, s.n - 1)
            if s.atr[i] and rng.random() < probability]


def simulate(s: Series, sigs: list[tuple[int, float]], exit_mode: str) -> list[dict]:
    cfg = TIMEFRAMES[s.tf]
    trail = 10 if "10" in exit_mode else 20 if "20" in exit_mode else None
    trades, busy = [], -1
    for i, raw_dist in sigs:
        start = i + 1
        if i <= busy or start >= s.n:
            continue
        entry = s.open[start] * (1 + SLIPPAGE)
        dist = max(raw_dist, entry * MIN_STOP_PCT)
        stop = entry - dist
        target = entry + 2 * dist if trail is None else None
        last = min(start + cfg["max_hold"], s.n) - 1
        fill, j = s.close[last], last
        for j in range(start, last + 1):
            if s.low[j] <= stop:
                fill = (s.open[j] if (s.open[j] < stop and j > start) else stop) * (1 - SLIPPAGE)
                break
            if target is not None and s.high[j] >= target:
                fill = target
                break
            if trail:
                stop = max(stop, s.lowest[trail][j])
        bars = j - start + 1
        r = ((fill - entry) - ((entry + fill) * TAKER_FEE + entry * FUNDING_PER_8H * bars / cfg["bars_per_8h"])) / dist
        trades.append({"symbol": s.symbol, "time": s.time[start], "exit_time": s.time[j] + (s.time[1] - s.time[0]),
                       "r": r, "bars": bars})
        busy = j
    return trades


def stats(trades: list[dict]) -> dict:
    rs = [t["r"] for t in trades]
    if not rs:
        return {"trades": 0, "win": 0.0, "avg": 0.0, "pf": 0.0}
    loss = abs(sum(r for r in rs if r <= 0))
    return {"trades": len(rs), "win": sum(r > 0 for r in rs) / len(rs) * 100, "avg": statistics.mean(rs),
            "pf": sum(r for r in rs if r > 0) / loss if loss else 99.0}


def text(st: dict) -> str:
    return "no trades" if not st["trades"] else f"{st['trades']} trades, {st['win']:.0f}% win, {st['avg']:+.2f}R, PF {st['pf']:.2f}"


def main() -> None:
    started = time.time()
    client = FuturesClient("", "", BASE_URLS["live"])
    client.sync_time()
    for tf, cfg in TIMEFRAMES.items():
        for symbol in SYMBOLS:
            added, total = download(client, symbol, tf, cfg["years"], directory=INTRADAY_DIR)
            print(f"data {symbol} {tf}: +{added}, {total} candles ({time.time() - started:.0f}s)", flush=True)

    report = ["# Intraday momentum lab (volume-spike breakout)\n",
              f"24 coins · long only · settings picked on data before {datetime.fromtimestamp(OOS_START, timezone.utc):%Y-%m-%d}, "
              "judged on the 12 months after · fees 0.05%/side, slippage 0.02%, funding · stops ≥ 1.2% · max 6 open at 0.75% risk\n"]
    summary_rows = []
    fil_lines = []

    for tf in TIMEFRAMES:
        results: dict[tuple, list[dict]] = {}
        control: dict[str, list[list[dict]]] = {e: [[] for _ in range(RANDOM_SEEDS)] for e in EXITS}
        signal_count = bar_count = 0
        for symbol in SYMBOLS:
            s = Series(symbol, tf)
            bar_count += s.n - 200
            for vm, lb, tr in product(VOLUME_MULTS, LOOKBACKS, TREND_FILTER):
                sigs = signals(s, vm, lb, tr)
                if (vm, lb, tr) == (3, 48, False):
                    signal_count += len(sigs)
                for exit_mode in EXITS:
                    results.setdefault((vm, lb, tr, exit_mode), []).extend(simulate(s, sigs, exit_mode))
            probability = max(signal_count / max(bar_count, 1), 0.0005)
            for exit_mode in EXITS:
                for seed in range(RANDOM_SEEDS):
                    control[exit_mode][seed].extend(simulate(s, random_signals(s, seed, probability), exit_mode))
            print(f"{tf} {symbol} tested ({time.time() - started:.0f}s)", flush=True)
            del s

        rows = []
        for key, trades in results.items():
            ins = [t for t in trades if t["time"] < OOS_START]
            oos = [t for t in trades if t["time"] >= OOS_START]
            rows.append({"key": key, "is": stats(ins), "oos": stats(oos), "oos_trades": oos, "all": trades})
        eligible = [r for r in rows if r["is"]["trades"] >= 30] or rows
        pick = max(eligible, key=lambda r: r["is"]["avg"])
        with_trades = [r for r in rows if r["oos"]["trades"]]
        profitable = sum(1 for r in with_trades if r["oos"]["avg"] > 0)
        median_oos = statistics.median(r["oos"]["avg"] for r in with_trades) if with_trades else 0.0
        _, equity, worst, _ = portfolio(pick["oos_trades"]) if pick["oos_trades"] else ([], 1.0, 0.0, {})
        random_oos = [stats([t for t in control[pick["key"][3]][seed] if t["time"] >= OOS_START])["avg"] for seed in range(RANDOM_SEEDS)]
        random_median = statistics.median(random_oos)

        passed = (pick["is"]["avg"] > 0 and pick["oos"]["avg"] >= 0.15 and pick["oos"]["trades"] >= 50
                  and profitable / max(len(with_trades), 1) >= 0.6 and pick["oos"]["avg"] > random_median + 0.15)
        verdict = "✅ PASS" if passed else ("🟡 PROMISING" if pick["oos"]["avg"] > 0 and profitable / max(len(with_trades), 1) >= 0.5 else "❌ FAIL")
        vm, lb, tr, ex = pick["key"]
        picked = f"volume ≥{vm}×, {lb}-candle high, trend filter {'on' if tr else 'off'}, {ex}"
        summary_rows.append(f"| {tf} | {profitable}/{len(with_trades)} | {median_oos:+.2f}R | {picked} | {pick['is']['avg']:+.2f}R | "
                            f"{text(pick['oos'])} | {(equity - 1) * 100:+.0f}% / {worst:.0f}% | {random_median:+.2f}R | {verdict} |")
        print(f"\n{tf}: {verdict} | picked {picked} | older data {text(pick['is'])} | last 12 months {text(pick['oos'])} | "
              f"account {(equity - 1) * 100:+.0f}% (worst drop {worst:.0f}%) | profitable settings {profitable}/{len(with_trades)} | "
              f"random same exit {random_median:+.2f}R", flush=True)

        report.append(f"\n## {tf}: all settings (sorted by older-data result)\n")
        report.append("| Settings | Older data | Last 12 months |\n|---|---|---|")
        for r in sorted(rows, key=lambda r: -r["is"]["avg"]):
            v, l, t_, e = r["key"]
            report.append(f"| vol ≥{v}×, {l}-candle high, trend {'on' if t_ else 'off'}, {e} | {text(r['is'])} | {text(r['oos'])} |")

        fil_recent = [t for t in pick["all"] if t["symbol"] == "FILUSDT" and t["time"] >= OOS_START + 360 * 86_400]
        for t in fil_recent:
            fil_lines.append(f"- {tf}: entry {datetime.fromtimestamp(t['time'], timezone.utc):%Y-%m-%d %H:%M} UTC → "
                             f"{t['bars']} candles, result {t['r']:+.2f}R")

    report.insert(2, "| TF | Settings profitable (last 12 months) | Median | Picked on older data | Picked: older | "
                     "Picked: last 12 months | Account (return / worst drop) | Random, same exit | Verdict |\n|---|---|---|---|---|---|---|---|---|\n"
                  + "\n".join(summary_rows) + "\n")
    report.append("\n## FIL trades in the last few days (picked settings)\n")
    report.append("\n".join(fil_lines) if fil_lines else "None: the picked settings did not trade FIL in the last days.")
    INTRADAY_DIR.mkdir(parents=True, exist_ok=True)
    (INTRADAY_DIR / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\nFIL recent:\n" + ("\n".join(fil_lines) if fil_lines else "none"))
    print(f"\nDone in {time.time() - started:.0f}s. Report: {INTRADAY_DIR / 'report.md'}")


if __name__ == "__main__":
    main()

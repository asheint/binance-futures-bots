"""Stress test for the strategy that passed the lab (daily trend following), on data it has never seen:

1. 10 more coins it was never tested on
2. BTC and ETH history from BEFORE the lab's data (the lab used Sep 2023 onwards)
3. longs and shorts separately (is it just riding crypto's long-term rise?)
4. a permutation test: 300 random-entry runs with the SAME stop and trailing exit show how often luck does as well

  python validate_trend.py
"""
from __future__ import annotations

import random
import statistics
import time
from datetime import datetime, timezone

from client import FuturesClient
from config import BASE_URLS
from data import DATA_DIR, download, load_candles
from lab import Market, Signal, account, market_from_candles, metrics, short_stats, simulate, table, trend_following

VALIDATION_DIR = DATA_DIR / "validation"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT", "TRXUSDT"]
LAB_COINS = {"BTCUSDT", "ETHUSDT"}
LAB_START = int(datetime(2023, 9, 13, tzinfo=timezone.utc).timestamp())
GRID = [(lookback, trail) for lookback in (20, 40, 55) for trail in (2.0, 3.0, 4.0)]
PICK = (20, 2.0)  # the settings the lab picked on 2023-24
RANDOM_RUNS = 300


def random_like(m: Market, seed: int, trail: float, prob: float, long_only: bool = False) -> list[Signal]:
    """Random days and directions, but the exact same 2x ATR stop and trailing exit as the strategy."""
    rng = random.Random(seed * 7919 + sum(map(ord, m.symbol)))
    return [Signal(i, "long" if long_only else rng.choice(("long", "short")), 2 * m.atr[i], None, trail)
            for i in range(100, len(m.candles)) if m.atr[i] and rng.random() < prob]


def max_concurrent(trades: list[dict]) -> int:
    events = sorted([(t["time"], 1) for t in trades] + [(t["exit_time"], -1) for t in trades])
    running = peak = 0
    for _, change in events:
        running += change
        peak = max(peak, running)
    return peak


def main() -> None:
    started = time.time()
    client = FuturesClient("", "", BASE_URLS["live"])
    client.sync_time()
    for symbol in SYMBOLS:
        added, total = download(client, symbol, "1d", 7, directory=VALIDATION_DIR)
        print(f"{symbol} 1d: +{added} new, {total} total", flush=True)
    markets = {s: market_from_candles(s, "1d", load_candles(s, "1d", directory=VALIDATION_DIR)) for s in SYMBOLS}

    out = ["# Daily trend following: stress test\n",
           f"Settings picked by the lab: lookback {PICK[0]} days, trailing stop {PICK[1]}× ATR. "
           "Same costs as the lab (0.05% fee per side, 0.02% slippage, 0.01% funding per 8h), stops at least 1.2% away.\n"]

    # 1. every coin, all history
    pooled = {p: [] for p in GRID}
    rows = []
    for s in SYMBOLS:
        m = markets[s]
        results = {}
        for lookback, trail in GRID:
            trades = simulate(m, trend_following(m, lookback, trail))
            pooled[(lookback, trail)] += trades
            results[(lookback, trail)] = trades
        profitable = sum(1 for trades in results.values() if trades and metrics(trades)["avg"] > 0)
        picked = results[PICK]
        unseen = picked if s not in LAB_COINS else [t for t in picked if t["time"] < LAB_START]
        start = datetime.fromtimestamp(m.candles[0].time, timezone.utc).strftime("%Y-%m")
        rows.append([s + (" (lab coin)" if s in LAB_COINS else ""), start, short_stats(metrics(picked)),
                     short_stats(metrics(unseen)), f"{profitable}/9"])
    out.append("## 1. Every coin, all available history\n")
    out.append(table(["Coin", "Data from", "Picked settings: all history", "Picked settings: never-seen part",
                      "Settings profitable"], rows))

    # 2. pooled across coins: all settings
    rows = []
    for params in GRID:
        trades = pooled[params]
        unseen = [t for t in trades if t["symbol"] not in LAB_COINS or t["time"] < LAB_START]
        ret, worst = account(trades)
        rows.append([f"lookback {params[0]}, trail {params[1]}" + (" ← picked" if params == PICK else ""),
                     short_stats(metrics(trades)), short_stats(metrics(unseen)), f"{ret:+.0f}% / {worst:.0f}%",
                     max_concurrent(trades)])
    out.append("\n## 2. All 12 coins together, every setting\n")
    out.append(table(["Settings", "All trades", "Never-seen trades only", "Account (1% risk): return / worst drop",
                      "Max open at once"], rows))

    # 3. longs vs shorts, and by year
    picked_trades = pooled[PICK]
    rows = [[side, short_stats(metrics([t for t in picked_trades if t["side"] == side]))] for side in ("long", "short")]
    out.append("\n## 3. Longs vs shorts (picked settings, all coins)\n")
    out.append(table(["Side", "Result"], rows))
    years = sorted({datetime.fromtimestamp(t["time"], timezone.utc).year for t in picked_trades})
    rows = [[y, short_stats(metrics([t for t in picked_trades
                                     if datetime.fromtimestamp(t["time"], timezone.utc).year == y]))] for y in years]
    out.append("\n### By year\n")
    out.append(table(["Year", "Result"], rows))

    # 4. permutation test against random entries with the same exits
    strategy_avg = metrics(picked_trades)["avg"]
    grid_median = statistics.median(metrics(pooled[p])["avg"] for p in GRID)
    prob = len(picked_trades) / sum(len(m.candles) - 100 for m in markets.values()) * 1.6  # similar trade count
    random_avgs, random_counts = [], []
    for seed in range(RANDOM_RUNS):
        trades = [t for s in SYMBOLS for t in simulate(markets[s], random_like(markets[s], seed, PICK[1], prob))]
        random_avgs.append(metrics(trades)["avg"])
        random_counts.append(len(trades))
    long_only = [metrics([t for s in SYMBOLS for t in simulate(markets[s], random_like(markets[s], 10_000 + seed, PICK[1], prob, True))])["avg"]
                 for seed in range(50)]
    beaten = sum(1 for x in random_avgs if x >= strategy_avg)
    out.append("\n## 4. Could luck do this? (random entries, same stop and trailing exit)\n")
    out.append(table(["", "Avg per trade"], [
        ["Strategy (picked settings)", f"{strategy_avg:+.3f}R ({len(picked_trades)} trades)"],
        ["Strategy (median of all 9 settings)", f"{grid_median:+.3f}R"],
        [f"Random direction, {RANDOM_RUNS} runs: median", f"{statistics.median(random_avgs):+.3f}R (~{statistics.median(random_counts):.0f} trades each)"],
        ["Random direction: best 5%", f"{sorted(random_avgs)[int(RANDOM_RUNS * 0.95)]:+.3f}R"],
        ["Random LONG-only, 50 runs: median", f"{statistics.median(long_only):+.3f}R"],
        ["Random runs that matched or beat the strategy", f"{beaten}/{RANDOM_RUNS} (p = {beaten / RANDOM_RUNS:.3f})"],
    ]))

    report = "\n".join(out) + "\n"
    (VALIDATION_DIR / "report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"Done in {time.time() - started:.0f}s. Report: {VALIDATION_DIR / 'report.md'}")


if __name__ == "__main__":
    main()

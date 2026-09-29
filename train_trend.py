"""Walk-forward training for the trend bot on 24 coins (2020 -> yesterday).

  python train_trend.py

1. Updates daily candles for all 24 coins up to yesterday.
2. Walk-forward: for each year from 2022, picks the settings that were best on the years BEFORE it,
   then trades that year with them (no hindsight).
3. Prints every setting on all data and on the last 3 years, and saves data/validation/walkforward_summary.json.

Use it every few months. Only change trend_bot.py if the walk-forward keeps picking a different setting.
"""
import json
import statistics
from datetime import datetime, timedelta, timezone

from client import FuturesClient
from config import BASE_URLS
from data import DATA_DIR, download, load_candles
from indicators import ema
from lab import FUNDING_PER_8H, MIN_STOP_PCT, SLIPPAGE, TAKER_FEE, market_from_candles

ORIGINAL = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT", "TRXUSDT"]
FRESH = ["ATOMUSDT", "NEARUSDT", "FILUSDT", "UNIUSDT", "AAVEUSDT", "ETCUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "BCHUSDT", "XLMUSDT"]
DIRS = {**{s: DATA_DIR / "validation" for s in ORIGINAL}, **{s: DATA_DIR / "validation_fresh" for s in FRESH}}
MAX_HOLD, MAX_OPEN, RISK = 120, 6, 0.0075
EXITS = {
    "trail 3x ATR": lambda m, j, best: best - 3.0 * m.atr[j],
    "trail 4x ATR": lambda m, j, best: best - 4.0 * m.atr[j],
    "10-day low": lambda m, j, best: min(m.lows[max(0, j - 9):j + 1]),
    "20-day low": lambda m, j, best: min(m.lows[max(0, j - 19):j + 1]),
}
CONFIGS = [(lookback, exit_name) for lookback in (20, 40, 55) for exit_name in EXITS]


def year_of(ts: float) -> int:
    return datetime.fromtimestamp(ts, timezone.utc).year


def label(cfg: tuple) -> str:
    return f"{cfg[0]}-day breakout + {cfg[1]}"


def trades_for(m, lookback: int, exit_name: str) -> list[dict]:
    rule = EXITS[exit_name]
    trend = ema(m.closes, 100)
    out, busy = [], -1
    for i in range(lookback, len(m.candles) - 1):
        a, c = m.atr[i], m.candles[i]
        if i <= busy or not a or trend[i] is None or not (c.close > max(m.highs[i - lookback:i]) and c.close > trend[i]):
            continue
        start = i + 1
        entry = m.candles[start].open * (1 + SLIPPAGE)
        dist = max(2 * a, entry * MIN_STOP_PCT)
        stop, best = entry - dist, entry
        last = min(start + MAX_HOLD, len(m.candles)) - 1
        exit_price, j, still_open = m.candles[last].close, last, last == len(m.candles) - 1
        for j in range(start, last + 1):
            bar = m.candles[j]
            if bar.low <= stop:
                exit_price = (bar.open if (bar.open < stop and j > start) else stop) * (1 - SLIPPAGE)
                still_open = False
                break
            best = max(best, bar.high)
            if m.atr[j]:
                stop = max(stop, rule(m, j, best))
        if still_open:
            break  # trade not finished yet: don't count it
        bars = j - start + 1
        r = ((exit_price - entry) - ((entry + exit_price) * TAKER_FEE + entry * FUNDING_PER_8H * bars * 3)) / dist
        out.append({"symbol": m.symbol, "time": m.candles[start].time, "exit_time": m.candles[j].time + 86_400, "r": r, "bars": bars})
        busy = j
    return out


def portfolio(trades: list[dict]) -> tuple[list[dict], float, float, dict]:
    open_until, taken = [], []
    for t in sorted(trades, key=lambda t: t["time"]):
        open_until = [x for x in open_until if x > t["time"]]
        if len(open_until) < MAX_OPEN:
            taken.append(t)
            open_until.append(t["exit_time"])
    equity = peak = 1.0
    worst = 0.0
    yearly: dict[int, float] = {}
    for t in sorted(taken, key=lambda t: t["exit_time"]):
        before = equity
        equity *= 1 + RISK * t["r"]
        peak = max(peak, equity)
        worst = max(worst, 1 - equity / peak)
        yearly[year_of(t["exit_time"])] = yearly.get(year_of(t["exit_time"]), 1.0) * equity / before
    return taken, equity, worst * 100, {y: (v - 1) * 100 for y, v in sorted(yearly.items())}


def summary(trades: list[dict], markets: dict, since: float | None = None) -> dict:
    selected = [t for t in trades if since is None or t["time"] >= since]
    taken, equity, worst, yearly = portfolio(selected)
    span = (max(t["exit_time"] for t in taken) - min(t["time"] for t in taken)) / 31_557_600
    rs = [t["r"] for t in taken]
    return {"trades": len(taken), "win": sum(r > 0 for r in rs) / len(rs) * 100, "avg": statistics.mean(rs),
            "cagr": (equity ** (1 / span) - 1) * 100, "worst": worst, "yearly": yearly, "per_month": len(taken) / (span * 12),
            "hold": statistics.mean(t["bars"] for t in taken), "losing_years": sum(v < 0 for v in yearly.values()),
            "best_trade": max(rs),
            "coins_positive": sum(1 for s in markets if statistics.mean([t["r"] for t in selected if t["symbol"] == s] or [0]) > 0)}


def main() -> None:
    client = FuturesClient("", "", BASE_URLS["live"])
    client.sync_time()
    markets = {}
    for symbol, directory in DIRS.items():
        download(client, symbol, "1d", 7, directory=directory)
        markets[symbol] = market_from_candles(symbol, "1d", load_candles(symbol, "1d", directory=directory))
    last_day = max(m.candles[-1].time for m in markets.values())
    print(f"Data up to {datetime.fromtimestamp(last_day, timezone.utc):%Y-%m-%d} for {len(markets)} coins")

    all_trades = {cfg: [t for m in markets.values() for t in trades_for(m, *cfg)] for cfg in CONFIGS}

    print("\n=== Walk-forward: each year uses the settings that were best on all years before it ===")
    walk = []
    for year in range(2022, datetime.now(timezone.utc).year + 1):
        start = datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp()

        def train_score(cfg):
            past = [t["r"] for t in all_trades[cfg] if t["exit_time"] < start]
            return statistics.mean(past) if len(past) >= 50 else -9

        pick = max(CONFIGS, key=train_score)
        test = [t for t in all_trades[pick] if start <= t["time"] < end]
        walk += test
        print(f"{year}: picked '{label(pick)}' (earlier years avg {train_score(pick):+.2f}R) -> "
              f"{len(test)} trades, year {(portfolio(test)[1] - 1) * 100:+.1f}%")
    _, equity, worst, _ = portfolio(walk)
    print(f"Walk-forward total since 2022: {(equity - 1) * 100:+.1f}%, worst drop {worst:.0f}%")

    recent = (datetime.now(timezone.utc) - timedelta(days=3 * 365)).timestamp()
    print(f"\n=== All settings, 24 coins (max {MAX_OPEN} open, {RISK * 100}% risk) ===")
    print(f"{'Settings':<36} {'ALL /yr':>8} {'drop':>5} {'lose yrs':>8} {'avgR':>6} {'coins+':>6} | {'LAST 3Y /yr':>11} {'drop':>5} {'avgR':>6}")
    rows = {}
    for cfg in CONFIGS:
        a, r = summary(all_trades[cfg], markets), summary(all_trades[cfg], markets, recent)
        rows[label(cfg)] = {"all": a, "recent": r}
        print(f"{label(cfg):<36} {a['cagr']:>+7.1f}% {a['worst']:>4.0f}% {a['losing_years']:>5}/{len(a['yearly'])} "
              f"{a['avg']:>+5.2f} {a['coins_positive']:>4}/24 | {r['cagr']:>+10.1f}% {r['worst']:>4.0f}% {r['avg']:>+5.2f}")
    path = DATA_DIR / "validation" / "walkforward_summary.json"
    path.write_text(json.dumps(rows, indent=1, default=float), encoding="utf-8")
    print(f"\nSaved {path}")


if __name__ == "__main__":
    main()

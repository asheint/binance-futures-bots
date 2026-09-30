"""Backtest of the sniper bot: replays its real plan_coin() on every closed 15m candle of the past months, then
manages each trade the way the live bot does, and compares it with the daily trend bot on the same coins and window.

- signals: sniper_bot.plan_coin() itself (4h context + 1h levels + 15m/1h trigger), BTC filter included
- entry: the trigger candle's close (+ slippage); skipped when the target is under MIN_RR or funding is crowded
- management: half off at +1R and stop to break-even, full exit at the target, stop or after MAX_HOLD_H hours
  (inside a candle the stop is checked first: pessimistic)
- at most SNIPER_MAX_ALT_SAME_SIDE altcoin trades open in the same direction, one trade per coin
- R includes fees like the live bot: a full stop = -1R
Settings come from .env (SNIPER_*), candles from the REAL market (cached in data/sniper_backtest/).

  python sniper_backtest.py                          # trend bot's 24 coins, last 12 months
  python sniper_backtest.py --months 6 --coins SOLUSDT XRPUSDT
"""
from __future__ import annotations

import argparse
import bisect
import statistics
import time
from datetime import datetime, timezone
from multiprocessing import Pool

from client import FuturesClient
from config import BASE_URLS
from data import DATA_DIR, download, download_funding, load_candles, load_funding
from lab import FUNDING_PER_8H, SLIPPAGE, TAKER_FEE, market_from_candles, table
from models import Candle
from train_trend import portfolio, trades_for
from trend_bot import EXIT_LOW_DAYS, LOOKBACK, SYMBOLS

BACKTEST_DIR = DATA_DIR / "sniper_backtest"
INTERVALS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
WARMUP_DAYS = 60     # 300 4h candles for the 200 EMA and swings
TREND_YEARS = 7      # daily history for the trend bot's long-run numbers
CROWDED_FUNDING = 0.0005  # same as sniper_bot.fire()


# ---- data --------------------------------------------------------------------------------

def load_market(client: FuturesClient, symbol: str, months: float) -> dict[str, list[Candle]]:
    years = {"15m": months / 12, "1h": months / 12, "4h": months / 12 + WARMUP_DAYS / 365, "1d": TREND_YEARS}
    out = {}
    for interval, span in years.items():
        download(client, symbol, interval, span + 0.01, BACKTEST_DIR)
        out[interval] = load_candles(symbol, interval, BACKTEST_DIR)
    download_funding(client, symbol, months / 12 + 0.01)
    return out


# ---- replay (one coin per process) -----------------------------------------------------------

def replay(job: tuple) -> list[dict]:
    symbol, candles, funding, btc, start, end = job
    import sniper_bot as sb
    # the 4h reading only changes when a 4h candle closes: cache it (plan_coin looks these up as module globals)
    real_context, real_golden, memo = sb.context, sb.golden_zone, {}

    def cached(key, fn, *args):
        if key not in memo:
            memo[key] = fn(*args)
        return memo[key]
    sb.context = lambda h4: cached(("context", h4[-1].time), real_context, h4)
    sb.golden_zone = lambda h4, trend: cached(("golden", h4[-1].time, trend), real_golden, h4, trend)

    s = sb.Settings()
    h4, h1, m15 = candles["4h"], candles["1h"], candles["15m"]
    closes4, closes1 = [c.time + 14400 for c in h4], [c.time + 3600 for c in h1]
    funding_times = [t for t, _ in funding]
    trades, fired, busy_until = [], set(), 0
    for i in range(120, len(m15)):
        close_t = m15[i].time + 900
        if not start <= close_t < end or close_t < busy_until:
            continue
        a4, a1 = bisect.bisect_right(closes4, close_t), bisect.bisect_right(closes1, close_t)
        if a4 < 210 or a1 < 120:
            continue
        p = sb.plan_coin(symbol, h4[max(0, a4 - 300):a4], h1[max(0, a1 - 300):a1], m15[i - 119:i + 1],
                         btc.get(close_t, {}), s)
        f = p["fire"]
        if not f or (f["kind"], f["candle"]) in fired:
            continue
        fired.add((f["kind"], f["candle"]))
        k = bisect.bisect_right(funding_times, close_t) - 1
        rate = funding[k][1] if k >= 0 else 0.0
        if (f["side"] == "LONG" and rate > CROWDED_FUNDING) or (f["side"] == "SHORT" and rate < -CROWDED_FUNDING):
            continue
        trade = manage(symbol, f, m15, i, s)
        if trade:
            trades.append(trade)
            busy_until = trade["exit_time"]
    return trades


def manage(symbol: str, f: dict, m15: list[Candle], i: int, s) -> dict | None:
    sign = 1 if f["side"] == "LONG" else -1
    entry = m15[i].close * (1 + SLIPPAGE * sign)
    stop = f["stop"]
    risk = (entry - stop) * sign
    if risk <= 0:
        return None
    target = next((level for level, _ in f["targets"] if (level - entry) * sign >= risk * 0.3), entry + 3 * risk * sign)
    rr = (target - entry) * sign / risk
    if rr < s.min_rr:
        return None
    one_r = entry + risk * sign
    parts: list[tuple[float, float]] = []  # (share of the position, exit price)
    left, partial, reason = 1.0, False, "time"
    last = min(i + int(s.max_hold * 4), len(m15) - 1)
    j = i
    for j in range(i + 1, last + 1):
        c = m15[j]
        if (c.low <= stop) if sign > 0 else (c.high >= stop):
            gap = (c.open < stop) if sign > 0 else (c.open > stop)
            parts.append((left, (c.open if gap else stop) * (1 - SLIPPAGE * sign)))
            left, reason = 0.0, "break-even" if partial else "stop"
            break
        if not partial and ((c.high >= one_r) if sign > 0 else (c.low <= one_r)):
            parts.append((0.5, one_r))  # the resting half order
            left, partial, stop = 0.5, True, entry * (1 + 0.0012 * sign)
        if (c.high >= target) if sign > 0 else (c.low <= target):
            parts.append((left, target))
            left, reason = 0.0, "target"
            break
    if left:
        parts.append((left, m15[j].close * (1 - SLIPPAGE * sign)))
    gross = sum(share * (price - entry) * sign for share, price in parts)
    costs = TAKER_FEE * (entry + sum(share * price for share, price in parts)) + entry * FUNDING_PER_8H * (j - i) / 32
    return {"symbol": symbol, "side": f["side"], "kind": f["kind"], "reason": reason, "rr": rr,
            "time": m15[i].time + 900, "exit_time": m15[j].time + 900,
            "r": (gross - costs) / (risk + 2 * TAKER_FEE * entry)}


def cap_same_side(trades: list[dict], cap: int) -> list[dict]:
    taken, open_ = [], []
    for t in sorted(trades, key=lambda t: t["time"]):
        open_ = [x for x in open_ if x["exit_time"] > t["time"]]
        if t["symbol"] != "BTCUSDT" and sum(x["symbol"] != "BTCUSDT" and x["side"] == t["side"] for x in open_) >= cap:
            continue
        taken.append(t)
        open_.append(t)
    return taken


# ---- report -----------------------------------------------------------------------------------

def stats(trades: list[dict], risk: float = 0.01) -> dict:
    rs = [t["r"] for t in sorted(trades, key=lambda t: t["exit_time"])]
    if not rs:
        return {"n": 0}
    wins, losses = sum(r for r in rs if r > 0), abs(sum(r for r in rs if r <= 0))
    equity = peak = 1.0
    worst = total = top = drop_r = 0.0
    streak = longest = 0
    for r in rs:
        equity *= 1 + risk * r
        peak = max(peak, equity)
        worst = max(worst, 1 - equity / peak)
        total += r
        top = max(top, total)
        drop_r = max(drop_r, top - total)
        streak = streak + 1 if r <= 0 else 0
        longest = max(longest, streak)
    return {"n": len(rs), "win": sum(r > 0 for r in rs) / len(rs) * 100, "avg": statistics.mean(rs), "total": total,
            "pf": wins / losses if losses else float("inf"), "drop_r": drop_r, "streak": longest,
            "ret": (equity - 1) * 100, "dd": worst * 100}


def row(name: str, st: dict) -> list:
    if not st["n"]:
        return [name, 0, "", "", "", "", "", "", ""]
    return [name, st["n"], f"{st['win']:.0f}%", f"{st['avg']:+.2f}R", f"{st['pf']:.2f}", f"{st['total']:+.0f}R",
            f"{st['drop_r']:.0f}R", st["streak"], f"{st['ret']:+.0f}% / {st['dd']:.0f}%"]


def by(trades: list[dict], field: str) -> list[list]:
    rows = []
    for value in sorted({t[field] for t in trades}):
        st = stats([t for t in trades if t[field] == value])
        rows.append([value, st["n"], f"{st['win']:.0f}%", f"{st['avg']:+.2f}R", f"{st['total']:+.0f}R"])
    return rows


def per_month(trades: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in trades:
        month = datetime.fromtimestamp(t["time"], timezone.utc).strftime("%Y-%m")
        out[month] = out.get(month, 0.0) + t["r"]
    return dict(sorted(out.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the sniper bot and compare it with the daily trend bot")
    parser.add_argument("--months", type=float, default=12)
    parser.add_argument("--coins", nargs="+", type=str.upper, default=SYMBOLS)
    args = parser.parse_args()
    coins = ["BTCUSDT"] + [c for c in args.coins if c != "BTCUSDT"]  # BTC is needed for the altcoin filter
    started = time.time()

    import sniper_bot as sb
    s = sb.Settings()
    client = FuturesClient("", "", BASE_URLS["live"])
    client.sync_time()
    markets = {}
    for n, symbol in enumerate(coins, 1):
        markets[symbol] = load_market(client, symbol, args.months)
        print(f"  candles ready: {symbol} ({n}/{len(coins)})", flush=True)
    end = min(m["15m"][-1].time for m in markets.values()) + 900 - int(s.max_hold * 3600)  # room to finish trades
    start = int(end - args.months * 30.44 * 86_400)
    first = max(m["15m"][0].time for m in markets.values())
    if first > start - 86_400:
        start = first + 86_400
        print(f"  note: cached 15m history only starts {datetime.fromtimestamp(first, timezone.utc):%Y-%m-%d}; "
              f"delete {BACKTEST_DIR} to download more", flush=True)

    # BTC's reading for the altcoin filter at every 15m close (same as SniperBot.cycle)
    btc, memo = {}, {}
    b = markets["BTCUSDT"]
    closes4, closes1 = [c.time + 14400 for c in b["4h"]], [c.time + 3600 for c in b["1h"]]
    for c in b["15m"]:
        t = c.time + 900
        if start <= t < end:
            a4, a1 = bisect.bisect_right(closes4, t), bisect.bisect_right(closes1, t)
            if b["4h"][a4 - 1].time not in memo:
                memo[b["4h"][a4 - 1].time] = sb.context(b["4h"][max(0, a4 - 300):a4])[0]
            btc[t] = {"bias": memo[b["4h"][a4 - 1].time], "move": b["1h"][a1 - 1].close / b["1h"][a1 - 5].close - 1}

    print(f"Replaying the sniper on {len(coins)} coins, "
          f"{datetime.fromtimestamp(start, timezone.utc):%Y-%m-%d} -> {datetime.fromtimestamp(end, timezone.utc):%Y-%m-%d}...", flush=True)
    jobs = [(sym, {k: markets[sym][k] for k in ("4h", "1h", "15m")}, load_funding(sym), btc if sym != "BTCUSDT" else {}, start, end)
            for sym in coins]
    with Pool() as pool:
        raw = [t for coin_trades in pool.map(replay, jobs) for t in coin_trades]
    sniper = cap_same_side(raw, s.max_alt_side)

    trend_window, trend_all = [], []
    for sym in coins:
        ts = trades_for(market_from_candles(sym, "1d", markets[sym]["1d"]), LOOKBACK, f"{EXIT_LOW_DAYS}-day low")
        trend_all += ts
        trend_window += [t for t in ts if start <= t["time"] < end]
    trend_window, *_ = portfolio(trend_window)
    trend_all, *_ = portfolio(trend_all)
    since = datetime.fromtimestamp(min(t["time"] for t in trend_all), timezone.utc).year if trend_all else "-"

    window = f"{datetime.fromtimestamp(start, timezone.utc):%Y-%m-%d} → {datetime.fromtimestamp(end, timezone.utc):%Y-%m-%d}"
    months_s, months_t = per_month(sniper), per_month(trend_window)
    report = "\n".join([
        "# Sniper bot backtest",
        "",
        f"Window {window}, {len(coins)} coins: {', '.join(c.removesuffix('USDT') for c in coins)}.",
        f"Settings: min target {s.min_rr:g}R, ADX ≥ {s.adx_min:g}, max hold {s.max_hold:g} h, "
        f"at most {s.max_alt_side} same-side altcoin trades. Fees {float(TAKER_FEE) * 100:.2f}% per side, "
        f"slippage {SLIPPAGE * 100:.2f}%. R includes fees (a full stop = -1R).",
        "",
        "## Sniper vs daily trend bot",
        "",
        table(["Bot", "Trades", "Win", "Avg", "PF", "Total", "Worst drop", "Losing streak", "Account at 1% risk: return / worst drop"], [
            row("Sniper, no altcoin cap", stats(raw)),
            row(f"Sniper, altcoin cap {s.max_alt_side} (as live)", stats(sniper)),
            row("Trend bot, same window", stats(trend_window)),
            row(f"Trend bot, all history since {since}", stats(trend_all)),
        ]),
        "",
        "## Sniper details (as live)",
        "",
        table(["Kind", "Trades", "Win", "Avg", "Total"], by(sniper, "kind")),
        "",
        table(["Exit", "Trades", "Win", "Avg", "Total"], by(sniper, "reason")),
        "",
        table(["Side", "Trades", "Win", "Avg", "Total"], by(sniper, "side")),
        "",
        table(["Month", "Sniper", "Trend bot"], [[m, f"{months_s.get(m, 0):+.1f}R", f"{months_t.get(m, 0):+.1f}R" if m in months_t else ""]
                                                  for m in sorted(set(months_s) | set(months_t))]),
        "",
        "Trend bot months are by entry date. Its all-history line is partly in-sample: the exit rule was chosen on these coins.",
    ])
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    (BACKTEST_DIR / "report.md").write_text(report + "\n", encoding="utf-8")
    print("\n" + report)
    print(f"\nSaved {BACKTEST_DIR / 'report.md'} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()

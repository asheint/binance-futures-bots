"""Backtester: replays history candle by candle and tests the setup cards.

  python backtest.py                         # BTCUSDT + ETHUSDT, all downloaded history
  python backtest.py BTCUSDT --split 2025-01-01

How it avoids fooling itself:
- at each 1h close the bot only sees candles that had already closed (no future data)
- entry is the NEXT candle's open, not the signal candle's close
- if the stop and target are both touched inside one candle, the stop is assumed to be hit first
- fees, slippage and funding are charged on every trade
- results are reported separately before and after the split date (in-sample vs out-of-sample)
"""
from __future__ import annotations

import argparse
import bisect
import csv
import math
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

from analysis import analyze
from data import DATA_DIR, load_candles
from models import Candle
from setups import WEIGHTS, evaluate

LTF, HTF = "1h", "4h"
LTF_SECONDS, HTF_SECONDS = 3_600, 14_400
LTF_WINDOW, HTF_WINDOW = 500, 300   # candles the bot "sees" at each step
TAKER_FEE = 0.0005                   # per side
SLIPPAGE = 0.0002                    # on market entries and stop exits
FUNDING_PER_8H = 0.0001              # charged as a cost on the position value
MAX_HOLD = 72                        # candles (3 days); then exit at the close
RISK_PER_TRADE = 0.01
RESULTS_DIR = DATA_DIR / "backtest"


# ---- simulation ------------------------------------------------------------------

def simulate_trade(candles: list[Candle], start: int, side: str, stop: float, target: float) -> dict | None:
    """Enters at candles[start].open. Returns None if the plan is already invalid at that open."""
    long = side == "long"
    entry = candles[start].open * (1 + SLIPPAGE if long else 1 - SLIPPAGE)
    if (long and not stop < entry < target) or (not long and not target < entry < stop):
        return None
    risk = abs(entry - stop)
    last = min(start + MAX_HOLD, len(candles)) - 1

    exit_index, exit_price, reason = last, candles[last].close, "time"
    for j in range(start, last + 1):
        c = candles[j]
        if long and c.low <= stop or not long and c.high >= stop:
            gap = c.open <= stop if long else c.open >= stop  # opened beyond the stop: filled at the open
            fill = c.open if gap and j > start else stop
            exit_index, exit_price, reason = j, fill * (1 - SLIPPAGE if long else 1 + SLIPPAGE), "stop"
            break
        if long and c.high >= target or not long and c.low <= target:
            exit_index, exit_price, reason = j, target, "target"
            break

    bars = exit_index - start + 1
    gross = (exit_price - entry) / risk if long else (entry - exit_price) / risk
    costs = ((entry + exit_price) * TAKER_FEE + entry * FUNDING_PER_8H * bars / 8) / risk
    return {"entry": entry, "exit_price": exit_price, "exit_reason": reason, "exit_index": exit_index,
            "exit_time": candles[exit_index].time + LTF_SECONDS, "bars": bars,
            "r_gross": gross, "r": gross - costs, "risk_pct": risk / entry * 100}


def run_symbol(symbol: str) -> list[dict]:
    ltf = load_candles(symbol, LTF)
    htf = load_candles(symbol, HTF)
    htf_close_times = [c.time + HTF_SECONDS for c in htf]
    signals: list[dict] = []
    htf_seen, htf_analysis = -1, None
    started = time.time()
    total = len(ltf) - 1 - LTF_WINDOW
    next_report = 0.1

    for i in range(LTF_WINDOW - 1, len(ltf) - 1):
        now = ltf[i].time + LTF_SECONDS
        closed_htf = bisect.bisect_right(htf_close_times, now)
        if closed_htf < HTF_WINDOW:
            continue
        if closed_htf != htf_seen:
            htf_analysis = analyze(htf[closed_htf - HTF_WINDOW:closed_htf], detail=False)
            htf_seen = closed_htf
        ltf_analysis = analyze(ltf[i - LTF_WINDOW + 1:i + 1], detail=False)

        for card in evaluate(htf_analysis, ltf_analysis):
            if not all(g["pass"] for g in card["gates"]):
                continue
            plan = card["plan"]
            outcome = simulate_trade(ltf, i + 1, card["side"], plan["stop"], plan["target"])
            if outcome is None:
                continue
            signals.append({
                "symbol": symbol, "side": card["side"], "time": now,
                "date": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "score": card["score"], "planned_rr": round(plan["rr"], 2),
                **{f"c_{c['key']}": int(c["status"] == "pass") for c in card["checks"]},
                "stop": plan["stop"], "target": plan["target"],
                **{k: v for k, v in outcome.items() if k != "exit_index"},
            })

        done = (i - LTF_WINDOW + 1) / total
        if done >= next_report:
            print(f"  {symbol}: {done:.0%} ({len(signals)} signals, {time.time() - started:.0f}s)", flush=True)
            next_report += 0.1
    return signals


# ---- statistics ----------------------------------------------------------------------

def dedupe(signals: list[dict]) -> list[dict]:
    """A setup often stays valid for several candles in a row. Count it once: skip a signal while an
    earlier counted one on the same symbol and side is still open."""
    busy: dict[tuple, int] = {}
    kept = []
    for s in sorted(signals, key=lambda s: s["time"]):
        key = (s["symbol"], s["side"])
        if busy.get(key, 0) > s["time"]:
            continue
        kept.append(s)
        busy[key] = s["exit_time"]
    return kept


def stats(signals: list[dict]) -> dict:
    rs = [s["r"] for s in sorted(signals, key=lambda s: s["time"])]
    if not rs:
        return {"trades": 0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    equity = peak = drawdown = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    loss_sum = abs(sum(losses))
    return {"trades": len(rs), "win_rate": len(wins) / len(rs) * 100, "avg_r": sum(rs) / len(rs),
            "total_r": sum(rs), "profit_factor": sum(wins) / loss_sum if loss_sum else math.inf, "max_dd_r": drawdown}


def account(signals: list[dict], threshold: int) -> dict:
    """One position per symbol at a time, risking 1% of equity per trade."""
    free_at: dict[str, int] = {}
    taken = []
    for s in sorted(signals, key=lambda s: s["time"]):
        if s["score"] < threshold or free_at.get(s["symbol"], 0) > s["time"]:
            continue
        taken.append(s)
        free_at[s["symbol"]] = s["exit_time"]
    equity = peak = 1.0
    max_dd = 0.0
    for s in taken:
        equity *= 1 + RISK_PER_TRADE * s["r"]
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
    return {**stats(taken), "return_pct": (equity - 1) * 100, "max_dd_pct": max_dd * 100}


# ---- report --------------------------------------------------------------------------

def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def fmt_stats(st: dict, extra: bool = False) -> list:
    if not st.get("trades"):
        return ["0", "-", "-", "-", "-"] + (["-", "-"] if extra else [])
    pf = "∞" if st["profit_factor"] == math.inf else f"{st['profit_factor']:.2f}"
    verdict = "✅" if st["avg_r"] >= 0.15 and st["trades"] >= 30 else ("❌" if st["avg_r"] < 0 else "➖")
    row = [st["trades"], f"{st['win_rate']:.0f}%", f"{st['avg_r']:+.2f}R {verdict}", pf, f"{st['max_dd_r']:.1f}R"]
    if extra:
        row += [f"{st['return_pct']:+.1f}%", f"{st['max_dd_pct']:.1f}%"]
    return row


def build_report(signals: list[dict], split_ts: int, split_label: str) -> str:
    periods = {
        f"In-sample (before {split_label})": [s for s in signals if s["time"] < split_ts],
        f"Out-of-sample (from {split_label})": [s for s in signals if s["time"] >= split_ts],
    }
    first = min((s["date"] for s in signals), default="-")
    last = max((s["date"] for s in signals), default="-")
    out = [f"# Backtest report\n",
           f"Signals that passed all required gates: **{len(signals)}** ({first} → {last} UTC). "
           f"Costs: {TAKER_FEE * 100:.2f}% fee per side, {SLIPPAGE * 100:.2f}% slippage, funding {FUNDING_PER_8H * 100:.2f}%/8h. "
           f"Max hold {MAX_HOLD} candles.\n",
           "✅ = at least 30 trades and +0.15R or better per trade · ➖ = small or unproven edge · ❌ = loses money\n"]
    stat_headers = ["Trades", "Win rate", "Avg per trade", "Profit factor", "Max drawdown"]

    for name, subset in periods.items():
        unique = dedupe(subset)
        out.append(f"\n## {name}\n")

        out.append("### Results by score (each setup counted once)\n")
        rows = []
        for low, high, label in ((0, 4, "≤ 4"), (5, 5, "5"), (6, 6, "6"), (7, 7, "7"), (8, 8, "8"), (9, 99, "9+")):
            rows.append([label] + fmt_stats(stats([s for s in unique if low <= s["score"] <= high])))
        rows.append(["**all**"] + fmt_stats(stats(unique)))
        out.append(table(["Score"] + stat_headers, rows))

        out.append("\n### Account simulation: trade only when score ≥ threshold (1% risk, one position per coin)\n")
        rows = [[f"≥ {t}"] + fmt_stats(account(subset, t), extra=True) for t in range(4, 10)]
        out.append(table(["Threshold"] + stat_headers + ["Account return", "Worst drop"], rows))

        out.append("\n### By coin and side (all scores)\n")
        rows = []
        for symbol in sorted({s["symbol"] for s in unique}):
            for side in ("long", "short"):
                rows.append([f"{symbol} {side}"] + fmt_stats(stats([s for s in unique if s["symbol"] == symbol and s["side"] == side])))
        out.append(table(["Group"] + stat_headers, rows))

        out.append("\n### Does each confirmation help? (average result when it passed vs failed)\n")
        rows = []
        for key in WEIGHTS:
            passed = [s for s in unique if s.get(f"c_{key}") == 1]
            failed = [s for s in unique if s.get(f"c_{key}") == 0]
            p, f = stats(passed), stats(failed)
            if p.get("trades") and f.get("trades"):
                lift = p["avg_r"] - f["avg_r"]
                verdict = "helps" if lift > 0.1 else ("hurts" if lift < -0.1 else "no real effect")
                rows.append([key, p["trades"], f"{p['avg_r']:+.2f}R", f["trades"], f"{f['avg_r']:+.2f}R", f"{lift:+.2f}R {verdict}"])
            else:
                rows.append([key, p.get("trades", 0), "-", f.get("trades", 0), "-", "not enough data"])
        out.append(table(["Confirmation", "Passed", "Avg R", "Failed", "Avg R", "Difference"], rows))

        reasons = {r: sum(1 for s in unique if s["exit_reason"] == r) for r in ("target", "stop", "time")}
        out.append(f"\nExits: {reasons['target']} hit target, {reasons['stop']} hit stop, {reasons['time']} closed after {MAX_HOLD} candles.")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the setup cards on downloaded history")
    parser.add_argument("symbols", nargs="*", default=["BTCUSDT", "ETHUSDT"], type=str.upper)
    parser.add_argument("--split", default="2025-01-01", help="out-of-sample starts at this date (UTC)")
    args = parser.parse_args()

    split_ts = int(datetime.strptime(args.split, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    started = time.time()
    print(f"Backtesting {', '.join(args.symbols)} ({LTF} entries, {HTF} trend)...", flush=True)
    with ProcessPoolExecutor(max_workers=len(args.symbols)) as pool:
        signals = [s for result in pool.map(run_symbol, args.symbols) for s in result]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    signals_path = RESULTS_DIR / "signals.csv"
    if signals:
        fields = list(dict.fromkeys(k for s in signals for k in s))
        with signals_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(sorted(signals, key=lambda s: s["time"]))

    report = build_report(signals, split_ts, args.split)
    report_path = RESULTS_DIR / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Done in {time.time() - started:.0f}s. Report: {report_path} | every trade: {signals_path}")


if __name__ == "__main__":
    main()

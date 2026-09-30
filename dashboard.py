"""Local web dashboard for the bot.

  python dashboard.py        then open http://127.0.0.1:8000

Runs only on this computer (127.0.0.1). API keys stay in this Python process, never in the browser.
"""
from __future__ import annotations

import csv
import json
import re
import threading
import time
from datetime import datetime, timezone
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

import bot
from analysis import analyze
from client import BinanceAPIError, FuturesClient
from config import BASE_URLS, load_config
from models import candles_from_klines
from risk import SymbolRules, plan_trade
from setups import evaluate
from indicators import ema
from lab import market_from_candles
from models import price_text
from train_trend import trades_for
from trend_bot import (CHECK_FLAG, DAY, EXIT_LOW_DAYS, INITIAL_STOP_ATR, LOOKBACK, MAX_OPEN, MIN_STOP_PCT, RISK_PCT,
                       LAST_SCAN, SETTINGS_PATH, TRADE_REQUEST, TRADE_RESULT, TREND_EMA, TrendBot, load_settings)
from trend_bot import SYMBOLS as TREND_SYMBOLS
import copy_bot
import crazy_bot
import news_bot
import sniper_bot

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "static" / "dashboard.html"
BOT_PAGE = ROOT / "static" / "bot.html"  # the crazy bot's robot page
NEWS_PAGE = ROOT / "static" / "news.html"  # the news bot's page
SNIPER_PAGE = ROOT / "static" / "sniper.html"  # the sniper bot's page
COPY_PAGE = ROOT / "static" / "copy.html"  # the copy bot's page
HOST, PORT = "127.0.0.1", 8000
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,20}$")

cfg = load_config()
client = bot.make_client(cfg)
market = FuturesClient("", "", BASE_URLS["live"])  # real-market candles: public data, no keys used
trend = TrendBot(cfg)  # read-only here: the dashboard shows its state, trend_bot.py does the trading
lock = threading.Lock()  # one Binance call at a time through the shared session
_cache: dict[tuple, tuple[float, object]] = {}


def cached_call(key: tuple, ttl: float, fn):
    """Serve recent results without waiting for the lock; refresh at most once per `ttl` seconds."""
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    with lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        value = fn()
        _cache[key] = (time.time(), value)
        return value


def journal_opens() -> dict[str, dict]:
    """Latest still-open OPEN row per symbol from the journal: entry time (unix) and the stop at entry."""
    opens: dict[str, dict] = {}
    if cfg.journal_path.exists():
        with cfg.journal_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                symbol = row.get("symbol")
                if not symbol:
                    continue
                if row.get("event") == "OPEN":
                    try:
                        opens[symbol] = {"time": int(datetime.fromisoformat(row["time"]).timestamp()),
                                         "stop": float(row["stop"]) if row.get("stop") else None}
                    except ValueError:
                        continue
                elif row.get("event") == "CLOSE":
                    opens.pop(symbol, None)
    return opens


def summary() -> dict:
    balance, available = bot.wallet(client)
    positions = [p for p in client.position_risk() if float(p["positionAmt"]) != 0]
    try:
        algo_orders, orders_error = client.open_algo_orders(), None
    except BinanceAPIError as err:
        algo_orders, orders_error = [], err.msg

    def trigger(symbol: str, order_type: str) -> float | None:
        return next((float(o["triggerPrice"]) for o in algo_orders
                     if o["symbol"] == symbol and o.get("orderType") == order_type), None)

    opens = journal_opens()
    rows = []
    for p in positions:
        amount = float(p["positionAmt"])
        rows.append({
            "symbol": p["symbol"],
            "side": "LONG" if amount > 0 else "SHORT",
            "qty": abs(amount),
            "entry": float(p["entryPrice"]),
            "mark": float(p["markPrice"]),
            "upnl": float(p["unRealizedProfit"]),
            "liq": float(p["liquidationPrice"]),
            "leverage": int(float(p["leverage"])),
            "margin_type": p["marginType"],
            "margin": float(p.get("isolatedMargin") or 0),
            "stop": trigger(p["symbol"], "STOP_MARKET"),
            "take_profit": trigger(p["symbol"], "TAKE_PROFIT_MARKET"),
            "entry_time": opens.get(p["symbol"], {}).get("time") or int(p.get("updateTime", 0)) // 1000,
            "initial_stop": opens.get(p["symbol"], {}).get("stop"),
        })

    return {
        "env": cfg.env,
        "balance": balance,
        "available": available,
        "unrealized": sum(r["upnl"] for r in rows),
        "positions": rows,
        "orders": [{"symbol": o["symbol"], "type": o.get("orderType"), "side": o["side"],
                    "trigger": float(o["triggerPrice"])} for o in algo_orders],
        "orders_error": orders_error,
    }


def history(days: int) -> dict:
    rows = client.income(start_time=client.now_ms() - days * 86_400_000)
    totals: dict[str, float] = defaultdict(float)
    wins = losses = 0
    for r in rows:
        value = float(r["income"])
        totals[r["incomeType"]] += value
        if r["incomeType"] == "REALIZED_PNL":
            wins += value > 0
            losses += value < 0

    wanted = ("REALIZED_PNL", "COMMISSION", "FUNDING_FEE")
    recent = [{"time": r["time"], "symbol": r["symbol"], "type": r["incomeType"], "income": float(r["income"])}
              for r in rows if r["incomeType"] in wanted][-100:][::-1]

    journal = []
    if cfg.journal_path.exists():
        with cfg.journal_path.open(newline="", encoding="utf-8") as f:
            journal = list(csv.DictReader(f))[-100:][::-1]

    return {
        "days": days,
        "realized": totals["REALIZED_PNL"],
        "fees": totals["COMMISSION"],
        "funding": totals["FUNDING_FEE"],
        "net": sum(totals[t] for t in wanted),
        "wins": wins,
        "losses": losses,
        "income": recent,
        "journal": journal,
    }


def klines(symbol: str, interval: str, source: str) -> list[dict]:
    feed = market if source == "real" else client
    return [{"time": k[0] // 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4])}
            for k in feed.klines(symbol, interval, limit=1000)]


def chart_analysis(symbol: str, interval: str, source: str) -> dict:
    feed = market if source == "real" else client
    return analyze(candles_from_klines(feed.klines(symbol, interval, limit=1000)))


def setups(symbol: str, source: str) -> dict:
    """Long and short setup cards: 4h for trend, 1h for location and trigger, sized with the account's risk settings."""
    feed = market if source == "real" else client
    htf = analyze(candles_from_klines(feed.klines(symbol, "4h", limit=1000)))
    ltf = analyze(candles_from_klines(feed.klines(symbol, "1h", limit=1000)))
    cards = evaluate(htf, ltf, has_position=bot.open_position(client, symbol) is not None)

    balance, available = bot.wallet(client)
    rules = SymbolRules.from_symbol_info(client.symbol_info(symbol))
    for card in cards:
        plan = card["plan"]
        try:
            sized = plan_trade(rules, balance, available, cfg.risk_pct, plan["entry"], plan["stop"], plan["rr"], cfg.leverage)
            plan.update(qty=float(sized.qty), risk_usdt=float(sized.risk_usdt), reward_usdt=float(sized.reward_usdt),
                        margin=float(sized.margin), risk_pct=cfg.risk_pct, leverage=cfg.leverage)
        except ValueError as err:
            plan["size_error"] = f"Can't size this trade: {err}"
    return {"symbol": symbol, "time": ltf["time"], "cards": cards}


def trend_status() -> dict:
    trend.state = trend.load_state()  # trend_bot.py may have updated it
    coins = []
    for symbol in TREND_SYMBOLS:
        try:
            s = trend.signal(trend.daily(symbol))
        except (BinanceAPIError, requests.RequestException) as err:
            coins.append({"symbol": symbol, "error": str(err)})
            continue
        pos = trend.state["positions"].get(symbol)
        if pos:
            pos = {**pos, "entry_date": datetime.fromtimestamp(pos["entry_day"], timezone.utc).strftime("%Y-%m-%d")}
        coins.append({"symbol": symbol, "close": s["close"], "level": s["level"], "ema": s["ema"], "long": s["long"],
                      "below_ema": bool(s["ema"] and s["close"] < s["ema"]),
                      "gap_pct": (s["level"] - s["close"]) / s["close"] * 100, "position": pos})
    log_path = ROOT / "data" / "trend_bot.log"
    log_line = log_time = None
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        log_line = lines[-1] if lines else None
        log_time = int(log_path.stat().st_mtime)
    return {"risk_pct": RISK_PCT, "max_open": MAX_OPEN, "last_cycle_day": trend.state.get("last_cycle_day"),
            "coins": coins, "log_line": log_line, "log_time": log_time, "open_count": len(trend.open_positions())}


crazy_cfg = crazy_bot.crazy_config(cfg)
crazy_client = client if crazy_cfg is cfg else bot.make_client(crazy_cfg)  # its own account when it has keys


def crazy_status() -> dict:
    """The crazy bot's heartbeat, open trades with live PnL, closed trades and the end of its log."""
    try:
        state = json.loads(crazy_bot.STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"positions": {}}
    lines: list[str] = []
    if crazy_bot.LOG_PATH.exists():
        lines = crazy_bot.LOG_PATH.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-60:]

    def account() -> tuple[dict, float]:
        live = {p["symbol"]: p for p in crazy_client.position_risk() if float(p["positionAmt"]) != 0}
        return live, bot.wallet(crazy_client)[0]

    live, balance = cached_call(("crazy_account",), 4, account)
    positions = []
    for symbol, pos in state.get("positions", {}).items():
        p = live.get(symbol)
        positions.append({"symbol": symbol, "side": pos["side"], "entry": pos["entry"], "tp": pos["tp"], "sl": pos["sl"],
                          "opened_at": pos["opened_at"] / 1000, "reasons": pos.get("reasons", []),
                          "mode": pos.get("mode", "normal"), "mark": float(p["markPrice"]) if p else None,
                          "upnl": float(p["unRealizedProfit"]) if p else 0.0})

    closed = crazy_bot.closed_trades(crazy_cfg)
    pnls = [c["pnl"] for c in closed]

    def mode_stats(mode: str) -> dict:
        rows = [c["pnl"] for c in closed if c["mode"] == mode]
        return {"wins": sum(p > 0 for p in rows), "losses": sum(p <= 0 for p in rows), "net": sum(rows)}

    control = crazy_bot.load_control()
    return {"heartbeat": state.get("heartbeat"), "scanning": state.get("scanning", False),
            "auto": control["auto"], "reverse": control["reverse"], "scan_requested": crazy_bot.SCAN_FLAG.exists(),
            "close_pending": crazy_bot.CLOSE_REQUEST.exists(),
            "by_mode": {"normal": mode_stats("normal"), "reverse": mode_stats("reverse")},
            "next_scan": state.get("next_scan"), "last_scan": state.get("last_scan"),
            "own_account": crazy_cfg is not cfg, "balance": balance,
            "positions": positions, "closed_count": len(closed), "closed": closed[-40:][::-1],
            "wins": sum(p > 0 for p in pnls), "losses": sum(p <= 0 for p in pnls), "net": sum(pnls),
            "best": max(pnls, default=0), "worst": min(pnls, default=0),
            "unrealized": sum(p["upnl"] for p in positions), "log": lines[::-1]}


def news_status() -> dict:
    """The news bot's heartbeat, open shorts with live PnL, results, headline feed and the end of its log."""
    try:
        state = json.loads(news_bot.STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"positions": {}, "feed": []}
    lines: list[str] = []
    if news_bot.LOG_PATH.exists():
        lines = news_bot.LOG_PATH.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-40:]
    live = cached_call(("news_account",), 4, lambda: {p["symbol"]: p for p in client.position_risk()
                                                      if float(p["positionAmt"]) != 0}) if state.get("positions") else {}
    positions = []
    for symbol, pos in state.get("positions", {}).items():
        p = live.get(symbol)
        positions.append({"symbol": symbol, "entry": pos["entry"], "sl": pos["sl"], "headline": pos.get("headline", ""),
                          "opened_at": pos["opened_at"] / 1000, "close_at": pos["close_at"], "test": pos.get("test", False),
                          "mark": float(p["markPrice"]) if p else None,
                          "upnl": float(p["unRealizedProfit"]) if p else 0.0})
    pnls = []
    if cfg.journal_path.exists():
        with cfg.journal_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                note = row.get("note") or ""
                if row.get("event") == "CLOSE" and note.startswith(news_bot.NOTE) and "self-test" not in note                         and row.get("pnl_usdt"):
                    pnls.append(float(row["pnl_usdt"]))
    rules = news_bot.Settings()
    return {"heartbeat": state.get("heartbeat"), "last_poll": state.get("last_poll"), "positions": positions,
            "closed_count": len(pnls), "wins": sum(p > 0 for p in pnls), "losses": sum(p <= 0 for p in pnls),
            "net": sum(pnls), "best": max(pnls, default=0), "worst": min(pnls, default=0),
            "rules": {"risk": rules.risk, "stop": rules.stop, "hold": rules.hold, "poll": rules.poll,
                      "leverage": rules.leverage},
            "feed": state.get("feed", [])[::-1], "log": lines[::-1]}


def sniper_status() -> dict:
    """The sniper bot's plans (lines per coin), open trades with live PnL, results and the end of its log."""
    try:
        state = json.loads(sniper_bot.STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"positions": {}, "watch": []}
    lines: list[str] = []
    if sniper_bot.LOG_PATH.exists():
        lines = sniper_bot.LOG_PATH.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-60:]
    live = cached_call(("sniper_account",), 4, lambda: {p["symbol"]: p for p in client.position_risk()
                                                        if float(p["positionAmt"]) != 0}) if state.get("positions") else {}
    positions = []
    for symbol, pos in state.get("positions", {}).items():
        p = live.get(symbol)
        positions.append({**{k: pos.get(k) for k in ("side", "kind", "grade", "entry", "sl", "tp", "initial_sl", "rr", "why",
                                                       "bonuses", "target_label", "partial", "leverage", "risk_usdt")},
                          "symbol": symbol, "opened_at": pos["opened_at"] / 1000,
                          "mark": float(p["markPrice"]) if p else None, "upnl": float(p["unRealizedProfit"]) if p else 0.0})
    closed = []
    if cfg.journal_path.exists():
        with cfg.journal_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                note = (row.get("note") or "").split()
                if row.get("event") == "CLOSE" and note[:1] == [sniper_bot.NOTE] and row.get("pnl_usdt"):
                    closed.append({"symbol": row["symbol"], "pnl": float(row["pnl_usdt"]), "grade": note[1] if len(note) > 1 else "",
                                   "outcome": " ".join(note[2:])})
    pnls = [c["pnl"] for c in closed]
    s = sniper_bot.Settings()
    return {"heartbeat": state.get("heartbeat"), "trading": sniper_bot.load_control()["trading"],
            "next_cycle": state.get("next_cycle"), "cycle_running": state.get("cycle_running", False),
            "last_cycle": state.get("last_cycle"), "watch": state.get("watch", []), "positions": positions,
            "closed_count": len(closed), "closed": closed[-30:][::-1], "wins": sum(p > 0 for p in pnls),
            "losses": sum(p <= 0 for p in pnls), "net": sum(pnls), "unrealized": sum(p["upnl"] for p in positions),
            "close_pending": sniper_bot.CLOSE_REQUEST.exists(), "check_requested": sniper_bot.CHECK_FLAG.exists(),
            "rules": {"risk": s.risk, "min_rr": s.min_rr, "max_leverage": s.max_leverage, "coins": s.max_coins,
                      "adx_min": s.adx_min, "max_hold": s.max_hold},
            "log": lines[::-1]}


def copy_status() -> dict:
    """The copy bot's followed traders, paper copies, per-trader results, the last scout's ranking and its log."""
    def read(path: Path, default: dict) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default
    state = read(copy_bot.STATE_PATH, {})
    scout = read(copy_bot.SCOUT_PATH, {"rows": []})
    lines: list[str] = []
    if copy_bot.LOG_PATH.exists():
        lines = copy_bot.LOG_PATH.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-60:]
    closed = state.get("closed", [])
    opened = list(state.get("open", {}).values())
    traders = []
    for trader in state.get("following", []):
        info = state.get("traders", {}).get(trader, {})
        mine = [c["pnl"] for c in closed if c["trader"] == trader]
        traders.append({"id": trader, **info, "picked": trader in state.get("picked", []),
                        "open": sum(p["trader"] == trader for p in opened), "closed": len(mine),
                        "wins": sum(p > 0 for p in mine), "net": sum(mine),
                        "unrealized": sum(p.get("upnl", 0.0) for p in opened if p["trader"] == trader)})
    groups = (("too new", "too new"), ("deep drawdown", "deep drawdown"), ("hides", "hides positions"),
              ("not active", "not active"), ("idle", "idle"), ("small account", "small account"), ("only", "few trades"),
              ("profit factor", "low profit factor"), ("too perfect", "too perfect (losers held open)"),
              ("no-stop", "no-stop pattern"), ("one lucky", "one lucky trade"), ("high leverage", "high leverage"),
              ("holding big losers", "holding big losers"), ("data error", "data error"))
    reasons: dict[str, int] = defaultdict(int)
    for r in scout.get("rows", []):
        if r.get("reason"):
            reasons[next((label for prefix, label in groups if r["reason"].startswith(prefix)), r["reason"])] += 1
    pnls = [c["pnl"] for c in closed]
    s = copy_bot.Settings()
    return {"heartbeat": state.get("heartbeat"), "scouting": state.get("scouting", False),
            "scout_requested": copy_bot.SCOUT_FLAG.exists(), "last_scout": state.get("last_scout"),
            "next_scout": state.get("next_scout"), "last_poll": state.get("last_poll"), "traders": traders,
            "positions": sorted(opened, key=lambda p: -p["opened_at"]), "closed": closed[-40:][::-1],
            "closed_count": len(pnls), "wins": sum(p > 0 for p in pnls), "losses": sum(p <= 0 for p in pnls),
            "net": sum(pnls), "unrealized": sum(p.get("upnl", 0.0) for p in opened),
            "scout": {"time": scout.get("time"), "candidates": scout.get("candidates", 0), "passed": scout.get("passed", 0),
                      "rows": scout.get("rows", [])[:80], "reasons": sorted(reasons.items(), key=lambda kv: -kv[1])},
            "rules": {"follow": s.follow, "notional": s.notional, "stop_pct": s.stop_pct, "poll": s.poll,
                      "min_days": s.min_days, "min_trades": s.min_trades, "max_mdd": s.max_mdd,
                      "max_leverage": s.max_leverage, "min_balance": s.min_balance},
            "log": lines[::-1]}


def symbol_ticker(symbol: str, source: str) -> dict:
    """Header stats for one symbol, like the bar above Binance's chart."""
    feed = market if source == "real" else client
    t = feed.ticker_24h(symbol)
    p = feed.premium_index(symbol)
    try:
        open_interest = feed.open_interest(symbol) * float(p["markPrice"])
    except BinanceAPIError:
        open_interest = None
    return {"symbol": symbol, "last": float(t["lastPrice"]), "change": float(t["priceChange"]),
            "change_pct": float(t["priceChangePercent"]), "high": float(t["highPrice"]), "low": float(t["lowPrice"]),
            "quote_volume": float(t["quoteVolume"]), "mark": float(p["markPrice"]), "index": float(p["indexPrice"]),
            "funding": float(p["lastFundingRate"]), "next_funding": int(p["nextFundingTime"]) // 1000,
            "open_interest_usdt": open_interest}


def bot_view(symbol: str) -> dict:
    """Everything the trend bot looks at for one coin, to draw on the daily chart and explain its decision."""
    if symbol not in TREND_SYMBOLS:
        raise ValueError(f"{symbol} is not one of the bot's 24 coins")
    trend.state = trend.load_state()
    candles = candles_from_klines(market.klines(symbol, "1d", limit=500))
    m = market_from_candles(symbol, "1d", candles)
    n = len(candles)
    ema_values = ema(m.closes, TREND_EMA)
    breakout = [max(m.highs[i - LOOKBACK:i]) if i >= LOOKBACK else None for i in range(n)]
    low20 = [min(m.lows[i - EXIT_LOW_DAYS + 1:i + 1]) if i >= EXIT_LOW_DAYS - 1 else None for i in range(n)]

    def series(values: list) -> list[dict]:
        return [{"time": c.time, "value": v} for c, v in zip(candles, values) if v is not None]

    history = [{"entry_time": t["time"], "exit_candle": t["exit_time"] - DAY, "r": t["r"]}
               for t in trades_for(m, LOOKBACK, "20-day low")]

    s = trend.signal(trend.daily(symbol))
    positions = trend.open_positions()
    pos = trend.state["positions"].get(symbol)
    coin = symbol.replace("USDT", "")
    close, level, ema_now, atr_now, low_now = s["close"], s["level"], s["ema"], s["atr"], low20[-1]
    gap = (level - close) / close * 100

    if pos:
        idx = next((i for i, c in enumerate(candles) if c.time == pos["entry_day"] - DAY), None)
        signal_detail = (f"signal candle {datetime.fromtimestamp(candles[idx].time, timezone.utc):%d %b}: close "
                         f"{price_text(candles[idx].close)} > 55-day high {price_text(breakout[idx])}") if idx is not None and breakout[idx] else "signal before the bot bought"
    elif s["long"]:
        when = "yesterday's close" if s.get("days_ago", 0) == 0 else f"close {s['days_ago'] + 1} days ago"
        signal_detail = f"{when}: {price_text(s['signal_close'])} > {price_text(s['signal_level'])}"
    else:
        signal_detail = f"last close {price_text(close)} vs {price_text(level)} ({gap:.1f}% away)"

    manual = symbol in positions and not pos
    checks = [
        {"ok": bool(pos) or s["long"], "label": "Daily close above the 55-day high (breakout)", "detail": signal_detail},
        {"ok": bool(ema_now and close > ema_now), "label": "Price above EMA 100 (uptrend filter)",
         "detail": f"close {price_text(close)} vs EMA 100 {price_text(ema_now) if ema_now else '—'}"},
        {"ok": bool(pos) or len(positions) < MAX_OPEN, "label": "Free position slot", "detail": f"{len(positions)} of {MAX_OPEN} slots used"},
        {"ok": not manual, "label": "Bot is in this trade" if pos else "No other position on this coin",
         "detail": f"since {datetime.fromtimestamp(pos['entry_day'], timezone.utc):%d %b %Y}" if pos
         else ("a manual position is open here" if manual else "free to trade")},
    ]

    if pos:
        entry, stop = pos["entry"], pos["stop"]
        status, cls = "In trade", "info"
        decision = (f"Bought {coin} at {price_text(entry)} because its daily candle closed above the 55-day high while above "
                    f"EMA 100. The stop follows the 20-day low and only moves up; profit is taken when price falls to it.")
        plan = [("Entry", price_text(entry), ""), ("First stop (2× ATR)", price_text(pos["initial_stop"]), "down"),
                ("Current stop", price_text(stop), "down"), ("20-day low now", price_text(low_now), ""),
                ("Profit locked", "yes" if stop > entry else "not yet (stop below entry)", "up" if stop > entry else "")]
    elif s["long"]:
        planned_stop = close - max(INITIAL_STOP_ATR * atr_now, close * MIN_STOP_PCT)
        status, cls = "Buy signal", "up"
        decision = "All buy rules pass. The bot buys at its next check (or press Check now while the bot is running)."
        plan = [("Buy near", price_text(close), ""), ("First stop (2× ATR)", price_text(planned_stop), "down"),
                ("Risk", f"{RISK_PCT}% of balance", "")]
    elif ema_now and close < ema_now:
        status, cls = "No trade", ""
        decision = "Price is below EMA 100, so the coin is not in an uptrend. The bot won't buy, even on a breakout."
        plan = [("EMA 100", price_text(ema_now), "down"), ("Breakout level", price_text(level), "")]
    else:
        status, cls = "Waiting for breakout", "warn"
        decision = f"The uptrend filter passes, but a daily close must rise {gap:.1f}% to break the 55-day high."
        plan = [("Breakout level", price_text(level), ""), ("Needs", f"+{gap:.1f}%", "warn")]

    return {
        "symbol": symbol, "status": status, "status_class": cls, "decision": decision, "checks": checks,
        "plan": [{"label": a, "value": b, "cls": c} for a, b, c in plan],
        "levels": {"breakout": level, "ema": ema_now, "low20": low_now},
        "series": {"breakout": series(breakout), "ema": series(ema_values), "low20": series(low20)},
        "history": history,
        "position": {"entry": pos["entry"], "stop": pos["stop"], "signal_day": pos["entry_day"] - DAY} if pos else None,
        "signal": {"day": s["day"]} if s["long"] and not pos else None,
    }


def trade_preview(symbol: str) -> dict:
    """The exact order the bot would place right now: size, stop, risk and reference profit levels."""
    if symbol not in TREND_SYMBOLS:
        raise ValueError(f"{symbol} is not one of the bot's 24 coins")
    d = trend.daily(symbol)
    s = trend.signal(d)
    positions = trend.open_positions()
    mark = client.mark_price(symbol)
    stop = mark - max(INITIAL_STOP_ATR * s["atr"], mark * MIN_STOP_PCT)
    balance, available = bot.wallet(client)
    base = {"symbol": symbol, "signal": s["long"], "price": mark, "slots_used": len(positions), "max_open": MAX_OPEN,
            "in_position": symbol in positions, "low20": min(d["lows"][-EXIT_LOW_DAYS:]), "leverage": cfg.leverage,
            "risk_pct": RISK_PCT, "auto_trade": load_settings()["auto_trade"]}
    try:
        rules = SymbolRules.from_symbol_info(client.symbol_info(symbol))
        plan = plan_trade(rules, balance, available, RISK_PCT, mark, stop, 1.0, cfg.leverage)
    except ValueError as err:
        return {**base, "error": f"Can't size this trade: {err}"}
    per_unit = mark - float(plan.stop)
    return {**base, "stop": float(plan.stop), "stop_pct": per_unit / mark * 100, "qty": float(plan.qty),
            "notional": float(plan.notional), "margin": float(plan.margin), "risk_usdt": float(plan.risk_usdt),
            "levels": [{"r": k, "price": mark + k * per_unit, "profit_usdt": k * float(plan.qty) * per_unit} for k in (1, 2, 3)]}


def market_overview() -> dict:
    """24h stats for the bot's coins (real market) for the heatmap."""
    wanted = set(TREND_SYMBOLS)
    return {"coins": [{"symbol": t["symbol"], "price": float(t["lastPrice"]), "change_pct": float(t["priceChangePercent"]),
                       "quote_volume": float(t["quoteVolume"]), "high": float(t["highPrice"]), "low": float(t["lowPrice"])}
                      for t in market.ticker_24h() if t["symbol"] in wanted]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep the console quiet
        pass

    def send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        try:
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass  # the browser closed the request (refresh / switched coin): nothing to do

    def send_json(self, data: object, status: int = 200) -> None:
        self.send(json.dumps(data).encode(), "application/json", status)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        arg = lambda name, default: query.get(name, [default])[0]
        try:
            if url.path == "/":
                self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/copy":
                self.send(COPY_PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/copy":
                self.send_json(copy_status())
            elif url.path == "/bot":
                self.send(BOT_PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/news":
                self.send(NEWS_PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/sniper":
                self.send(SNIPER_PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/sniper":
                self.send_json(sniper_status())
            elif url.path == "/api/summary":
                with lock:
                    self.send_json(summary())
            elif url.path == "/api/history":
                days = min(max(int(arg("days", "7")), 1), 90)
                with lock:
                    self.send_json(history(days))
            elif url.path == "/api/ticker":
                symbol, source = arg("symbol", "BTCUSDT").upper(), arg("source", "real")
                if not SYMBOL_RE.match(symbol) or source not in ("real", "demo"):
                    raise ValueError("bad symbol or source")
                self.send_json(cached_call(("ticker", symbol, source), 4, lambda: symbol_ticker(symbol, source)))
            elif url.path == "/api/trade_preview":
                symbol = arg("symbol", "").upper()
                if not SYMBOL_RE.match(symbol):
                    raise ValueError("bad symbol")
                with lock:
                    self.send_json(trade_preview(symbol))
            elif url.path == "/api/trade_result":
                self.send_json(json.loads(TRADE_RESULT.read_text(encoding="utf-8")) if TRADE_RESULT.exists() else {})
            elif url.path == "/api/settings":
                self.send_json(load_settings())
            elif url.path == "/api/last_scan":
                self.send_json(json.loads(LAST_SCAN.read_text(encoding="utf-8")) if LAST_SCAN.exists() else {})
            elif url.path == "/api/botview":
                symbol = arg("symbol", "BTCUSDT").upper()
                if not SYMBOL_RE.match(symbol):
                    raise ValueError("bad symbol")
                self.send_json(cached_call(("botview", symbol), 50, lambda: bot_view(symbol)))
            elif url.path == "/api/market":
                self.send_json(cached_call(("market",), 20, market_overview))
            elif url.path == "/api/news":
                self.send_json(news_status())
            elif url.path == "/api/crazy":
                self.send_json(crazy_status())
            elif url.path == "/api/trend":
                self.send_json(cached_call(("trend",), 20, trend_status))
            elif url.path == "/api/setups":
                symbol, source = arg("symbol", "BTCUSDT").upper(), arg("source", "real")
                if not SYMBOL_RE.match(symbol) or source not in ("real", "demo"):
                    raise ValueError("bad symbol or source")
                self.send_json(cached_call(("setups", symbol, source), 60, lambda: setups(symbol, source)))
            elif url.path in ("/api/klines", "/api/analysis"):
                symbol, interval = arg("symbol", "BTCUSDT").upper(), arg("interval", "15m")
                source = arg("source", "real")
                if not SYMBOL_RE.match(symbol) or interval not in bot.INTERVALS or source not in ("real", "demo"):
                    raise ValueError("bad symbol, interval or source")
                handler = klines if url.path == "/api/klines" else chart_analysis
                ttl = 8 if url.path == "/api/klines" else 60
                self.send_json(cached_call((url.path, symbol, interval, source), ttl, lambda: handler(symbol, interval, source)))
            else:
                self.send_json({"error": "not found"}, 404)
        except (BinanceAPIError, requests.RequestException, ValueError) as err:
            self.send_json({"error": str(err)}, 502)

    def do_POST(self) -> None:
        if self.headers.get("X-Dashboard") != "1":  # blocks cross-site form posts
            self.send_json({"error": "forbidden"}, 403)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/check":
                # The running trend bot picks this up within ~30 seconds and runs a full cycle.
                CHECK_FLAG.parent.mkdir(parents=True, exist_ok=True)
                CHECK_FLAG.write_text(str(time.time()), encoding="utf-8")
                _cache.pop(("trend",), None)  # so the dashboard sees the bot's answer right away
                self.send_json({"ok": True})
                return
            if path == "/api/trade_request":
                # The running bot picks this up within ~30 seconds, re-checks the rules and places entry + stop.
                symbol = str(body.get("symbol", "")).upper()
                if symbol not in TREND_SYMBOLS:
                    raise ValueError("not one of the bot's coins")
                TRADE_REQUEST.parent.mkdir(parents=True, exist_ok=True)
                TRADE_REQUEST.write_text(json.dumps({"symbol": symbol, "requested_at": time.time()}), encoding="utf-8")
                _cache.pop(("trend",), None)
                _cache.pop(("botview", symbol), None)
                self.send_json({"ok": True})
                return
            if path == "/api/crazy/control":
                # Auto / Manual and Normal / Reverse switches on the bot page; the crazy bot reads them every few seconds.
                control = crazy_bot.load_control()
                control.update({k: bool(body[k]) for k in ("auto", "reverse") if k in body})
                crazy_bot.CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
                crazy_bot.CONTROL_PATH.write_text(json.dumps(control), encoding="utf-8")
                self.send_json(control)
                return
            if path == "/api/crazy/close":
                # Close by hand: one symbol, or {"all": true}. The running crazy bot does it within a few seconds.
                if body.get("all"):
                    symbols = "all"
                else:
                    symbol = str(body.get("symbol", "")).upper()
                    if not SYMBOL_RE.match(symbol):
                        raise ValueError("bad symbol")
                    symbols = [symbol]
                    if crazy_bot.CLOSE_REQUEST.exists():  # merge with a request the bot hasn't picked up yet
                        try:
                            pending = json.loads(crazy_bot.CLOSE_REQUEST.read_text(encoding="utf-8")).get("symbols")
                            symbols = "all" if pending == "all" else sorted(set(pending or []) | {symbol})
                        except (OSError, ValueError):
                            pass
                crazy_bot.CLOSE_REQUEST.parent.mkdir(parents=True, exist_ok=True)
                crazy_bot.CLOSE_REQUEST.write_text(json.dumps({"symbols": symbols, "time": time.time()}), encoding="utf-8")
                self.send_json({"ok": True, "symbols": symbols})
                return
            if path == "/api/sniper/control":
                # Trading on / paused switch on the sniper page; the sniper bot reads it every few seconds.
                control = sniper_bot.load_control()
                control.update({k: bool(body[k]) for k in ("trading",) if k in body})
                sniper_bot.CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
                sniper_bot.CONTROL_PATH.write_text(json.dumps(control), encoding="utf-8")
                self.send_json(control)
                return
            if path == "/api/sniper/check":
                # "Check now": the running sniper bot reads every chart within a few seconds
                sniper_bot.CHECK_FLAG.parent.mkdir(parents=True, exist_ok=True)
                sniper_bot.CHECK_FLAG.write_text(str(time.time()), encoding="utf-8")
                self.send_json({"ok": True})
                return
            if path == "/api/sniper/close":
                if body.get("all"):
                    symbols = "all"
                else:
                    symbol = str(body.get("symbol", "")).upper()
                    if not SYMBOL_RE.match(symbol):
                        raise ValueError("bad symbol")
                    symbols = [symbol]
                    if sniper_bot.CLOSE_REQUEST.exists():
                        try:
                            pending = json.loads(sniper_bot.CLOSE_REQUEST.read_text(encoding="utf-8")).get("symbols")
                            symbols = "all" if pending == "all" else sorted(set(pending or []) | {symbol})
                        except (OSError, ValueError):
                            pass
                sniper_bot.CLOSE_REQUEST.parent.mkdir(parents=True, exist_ok=True)
                sniper_bot.CLOSE_REQUEST.write_text(json.dumps({"symbols": symbols, "time": time.time()}), encoding="utf-8")
                self.send_json({"ok": True, "symbols": symbols})
                return
            if path == "/api/copy/scout":
                # "Scout now": the running copy bot re-ranks the lead traders within a few seconds
                copy_bot.SCOUT_FLAG.parent.mkdir(parents=True, exist_ok=True)
                copy_bot.SCOUT_FLAG.write_text(str(time.time()), encoding="utf-8")
                self.send_json({"ok": True})
                return
            if path == "/api/crazy/scan":
                # "Scan now": the running crazy bot picks this up within a few seconds, scans and trades.
                crazy_bot.SCAN_FLAG.parent.mkdir(parents=True, exist_ok=True)
                crazy_bot.SCAN_FLAG.write_text(str(time.time()), encoding="utf-8")
                self.send_json({"ok": True})
                return
            if path == "/api/settings":
                settings = {**load_settings(), "auto_trade": bool(body.get("auto_trade"))}
                SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
                SETTINGS_PATH.write_text(json.dumps(settings), encoding="utf-8")
                self.send_json(settings)
                return
            if path != "/api/close":
                self.send_json({"error": "not found"}, 404)
                return
            symbol = str(body.get("symbol", "")).upper()
            if not SYMBOL_RE.match(symbol):
                raise ValueError("bad symbol")
            with lock:
                bot.close_trade(cfg, client, symbol, reason="dashboard")
            self.send_json({"ok": True})
        except (BinanceAPIError, requests.RequestException, ValueError) as err:
            self.send_json({"error": str(err)}, 502)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Dashboard ({cfg.env.upper()}) running at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")

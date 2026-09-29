"""Live daily trend-following bot: the strategy that passed the lab and the 12-coin stress test.

Rules (identical to the backtest):
- universe: 24 coins; signals use REAL Binance daily candles, orders go to the account in .env (demo by default)
- entry: a daily candle CLOSES above the highest high of the previous 55 days AND above EMA 100 -> buy at the next open
- long only (shorts lost money in the stress test)
- initial stop: 2x ATR below entry (at least 1.2%)
- exit: after every daily close, stop = lowest low of the last 20 days (it only moves up)
  (chosen by walk-forward training on 24 coins, 2020 -> Sep 2026; see BOT_GUIDE.md)
- time exit after 120 days
- risk 0.75% of balance per trade, at most 6 open positions

  python trend_bot.py scan          # show signals, positions and stops; places nothing
  python trend_bot.py run --once    # do one daily cycle now (enter / trail / exit)
  python trend_bot.py run           # keep running: daily cycle just after 00:00 UTC, stop check every hour
  python trend_bot.py tick          # one scheduler step (Windows Task Scheduler runs this hourly)
  python trend_bot.py selftest      # demo only: checks entry, stop, trailing move, stop repair and close
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

import bot
import journal
from client import BinanceAPIError, FuturesClient
from config import BASE_URLS, Config, load_config
from indicators import atr, ema
from models import candles_from_klines, price_text
from risk import SymbolRules, fmt, plan_trade

SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "DOTUSDT", "TRXUSDT",
           "ATOMUSDT", "NEARUSDT", "FILUSDT", "UNIUSDT", "AAVEUSDT", "ETCUSDT",
           "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "BCHUSDT", "XLMUSDT"]
LOOKBACK = 55        # breakout: close above the highest high of the previous 55 days
TREND_EMA = 100
INITIAL_STOP_ATR = 2.0
EXIT_LOW_DAYS = 20   # exit: stop follows the lowest low of the last 20 days
MIN_STOP_PCT = 0.012
MAX_HOLD_DAYS = 120
RISK_PCT = 0.75
MAX_OPEN = 6
CATCH_UP_DAYS = 3  # the bot runs only when you start it; joining a breakout up to 3 days late backtested as well as on time
DAY = 86_400
STATE_NOTE = "trend-d1"


LOG_PATH = Path(__file__).resolve().parent / "data" / "trend_bot.log"
CHECK_FLAG = LOG_PATH.parent / "check_now.flag"  # written by the dashboard's "Check now" button
TRADE_REQUEST = LOG_PATH.parent / "trade_request.json"  # dashboard: "place this trade" (the bot re-checks the rules first)
TRADE_RESULT = LOG_PATH.parent / "trade_result.json"    # bot: outcome of the last request, read by the dashboard
SETTINGS_PATH = LOG_PATH.parent / "bot_settings.json"   # dashboard switches, e.g. auto-buy on/off


LAST_SCAN = LOG_PATH.parent / "last_scan.json"         # bot: what the last full check found on every coin


def load_settings() -> dict:
    """auto_trade True (default) = the bot buys signals by itself; False = it waits for your approval on the dashboard."""
    try:
        return {"auto_trade": True, **json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {"auto_trade": True}


def log(message: str) -> None:
    """Prints (when there is a console) and always appends to data/trend_bot.log, so it also works windowless."""
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {message}"
    print(line, flush=True)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


class TrendBot:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client = bot.make_client(cfg)
        self.market = FuturesClient("", "", BASE_URLS["live"])
        self.state_path = cfg.journal_path.parent / "data" / "trend_state.json"
        self.state = self.load_state()

    # ---- state -----------------------------------------------------------------

    def load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"positions": {}, "last_cycle_day": None}

    def save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    # ---- market data ----------------------------------------------------------

    def daily(self, symbol: str) -> dict:
        """Closed daily candles from the real market plus the indicators the strategy needs."""
        candles = candles_from_klines(self.market.klines(symbol, "1d", limit=400))
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        return {"candles": candles, "highs": highs, "lows": lows, "ema": ema(closes, TREND_EMA), "atr": atr(highs, lows, closes)}

    def signal(self, d: dict) -> dict:
        """Today's numbers, plus the newest breakout among the last CATCH_UP_DAYS closed days that is still valid
        (price hasn't fallen back to where that trade's initial stop would be)."""
        candles, highs = d["candles"], d["highs"]
        latest = candles[-1]
        result = {"close": latest.close, "level": max(highs[-LOOKBACK - 1:-1]), "ema": d["ema"][-1], "atr": d["atr"][-1],
                  "day": latest.time, "long": False, "days_ago": 0}
        for ago in range(CATCH_UP_DAYS):
            i = len(candles) - 1 - ago
            level, trend, a, c = max(highs[i - LOOKBACK:i]), d["ema"][i], d["atr"][i], candles[i]
            if trend and a and c.close > level and c.close > trend:
                if latest.close > c.close - INITIAL_STOP_ATR * a:
                    result.update(long=True, day=c.time, days_ago=ago, signal_close=c.close, signal_level=level)
                break
        return result

    # ---- exchange helpers -------------------------------------------------------

    def open_positions(self) -> dict[str, dict]:
        return {p["symbol"]: p for p in self.client.position_risk() if float(p["positionAmt"]) != 0}

    def rules(self, symbol: str) -> SymbolRules:
        return SymbolRules.from_symbol_info(self.client.symbol_info(symbol))

    def place_stop(self, symbol: str, stop: float) -> int:
        order = self.client.new_algo_order(symbol=symbol, side="SELL", type="STOP_MARKET",
                                           triggerPrice=fmt(self.rules(symbol).round_price(stop)),
                                           closePosition=True, workingType="MARK_PRICE", priceProtect=True)
        return order["algoId"]

    def move_stop(self, symbol: str, pos: dict, new_stop: float) -> None:
        """Place the new stop first, then cancel the old one, so the position is never unprotected."""
        try:
            new_id = self.place_stop(symbol, new_stop)
            if pos.get("algo_id"):
                try:
                    self.client.cancel_algo_order(pos["algo_id"])
                except BinanceAPIError:
                    pass
        except BinanceAPIError:
            self.client.cancel_all_algo_orders(symbol)  # exchange refused two stops: swap them quickly
            new_id = self.place_stop(symbol, new_stop)
        pos["algo_id"], pos["stop"] = new_id, new_stop

    # ---- daily cycle --------------------------------------------------------------

    def cycle(self) -> None:
        log(f"Daily cycle ({self.cfg.env.upper()})")
        exchange_positions = self.open_positions()
        tracked = self.state["positions"]

        # 1. positions closed by their stop since the last cycle
        for symbol in list(tracked):
            if symbol not in exchange_positions:
                pos = tracked.pop(symbol)
                log(f"{symbol}: position is no longer open (stop hit around {price_text(pos['stop'])}, or closed by hand)")
                journal.log(self.cfg.journal_path, "CLOSE", env=self.cfg.env, symbol=symbol, side="LONG",
                            qty=pos["qty"], price=fmt(self.rules(symbol).round_price(pos["stop"])),
                            note=f"{STATE_NOTE} stop")

        # 2. trail stops and time exits for open positions
        for symbol, pos in list(tracked.items()):
            d = self.daily(symbol)
            since_entry = [c for c in d["candles"] if c.time >= pos["entry_day"]]
            best = max([pos["best"]] + [c.high for c in since_entry])
            pos["best"] = best
            held_days = (d["candles"][-1].time - pos["entry_day"]) // DAY + 1
            if held_days >= MAX_HOLD_DAYS:
                log(f"{symbol}: {held_days} days held, time exit")
                bot.close_trade(self.cfg, self.client, symbol, reason=f"{STATE_NOTE} time exit")
                tracked.pop(symbol)
                continue
            trail = min(d["lows"][-EXIT_LOW_DAYS:])
            if trail > pos["stop"] * 1.001:
                log(f"{symbol}: stop raised {price_text(pos['stop'])} -> {price_text(trail)} "
                    f"(lowest low of the last {EXIT_LOW_DAYS} days; best high so far {price_text(best)})")
                self.move_stop(symbol, pos, trail)
            else:
                log(f"{symbol}: stop stays {price_text(pos['stop'])} ({EXIT_LOW_DAYS}-day low is {price_text(trail)})")
        self.save_state()

        # 3. new entries, plus a report of what was found on every coin (shown on the dashboard)
        exchange_positions = self.open_positions()
        slots = MAX_OPEN - len(exchange_positions)
        balance, available = bot.wallet(self.client)
        auto = load_settings()["auto_trade"]
        report: list[dict] = []
        for symbol in SYMBOLS:
            row: dict = {"symbol": symbol}
            report.append(row)
            try:
                d = self.daily(symbol)
            except (BinanceAPIError, requests.RequestException) as err:
                log(f"{symbol}: no data ({err})")
                row.update(status="Data error", action=str(err))
                continue
            s = self.signal(d)
            row.update(close=s["close"], level=s["level"], ema=s["ema"], gap_pct=(s["level"] - s["close"]) / s["close"] * 100)
            if symbol in self.state["positions"]:
                row.update(status="In trade", action=f"holding · stop {price_text(self.state['positions'][symbol]['stop'])}")
                continue
            if not s["long"]:
                below = bool(s["ema"] and s["close"] < s["ema"])
                row.update(status="No uptrend" if below else "Uptrend, waiting",
                           action="below EMA 100, no buy" if below else f"needs a daily close {row['gap_pct']:.1f}% higher")
                continue
            row["status"] = "Buy signal"
            if symbol in exchange_positions:
                log(f"{symbol}: signal, but a position is already open")
                row["action"] = "not bought: a position is already open"
                continue
            if slots <= 0:
                log(f"{symbol}: signal skipped, already {MAX_OPEN} positions open")
                row["action"] = f"not bought: all {MAX_OPEN} slots in use"
                continue
            if not auto:
                log(f"{symbol}: BUY SIGNAL. Auto-buy is off, so waiting for your approval on the dashboard")
                row["action"] = "waiting for your approval (auto-buy is off)"
                continue
            if self.enter(symbol, s, balance, available):
                slots -= 1
                balance, available = bot.wallet(self.client)
                pos = self.state["positions"][symbol]
                row["action"] = f"BOUGHT {pos['qty']} at {price_text(pos['entry'])} · stop {price_text(pos['stop'])}"
            else:
                row["action"] = "not bought: see the bot log"
        self.state["last_cycle_day"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.save_state()
        LAST_SCAN.write_text(json.dumps({"time": time.time(), "auto_trade": auto, "coins": report}), encoding="utf-8")
        bought = sum(1 for r in report if str(r.get("action", "")).startswith("BOUGHT"))
        log(f"Cycle done · {bought} bought · {sum(r.get('status') == 'Buy signal' for r in report)} buy signals · "
            f"{sum(r.get('status') == 'In trade' for r in report)} in trade")

    def enter(self, symbol: str, s: dict, balance: float, available: float) -> bool:
        try:
            rules = self.rules(symbol)
        except ValueError:
            log(f"{symbol}: not tradable on this account")
            return False
        mark = self.client.mark_price(symbol)
        distance = max(INITIAL_STOP_ATR * s["atr"], mark * MIN_STOP_PCT)
        stop = mark - distance
        try:
            plan = plan_trade(rules, balance, available, RISK_PCT, mark, stop, 1.0, self.cfg.leverage)
        except ValueError as err:
            log(f"{symbol}: signal, but can't size it: {err}")
            return False

        when = "yesterday's close" if s.get("days_ago", 0) == 0 else f"close {s['days_ago'] + 1} days ago (catch-up)"
        log(f"{symbol}: ENTRY {when} {price_text(s.get('signal_close', s['close']))} > 20-day high "
            f"{price_text(s.get('signal_level', s['level']))} and EMA100 | buy {fmt(plan.qty)} @ ~{price_text(mark)}, "
            f"stop {price_text(stop)}, risk {plan.risk_usdt:.2f} USDT")
        bot.prepare_account(self.client, symbol, self.cfg.leverage)
        self.client.new_order(symbol=symbol, side="BUY", type="MARKET", quantity=fmt(plan.qty), newOrderRespType="RESULT")
        position = bot.open_position(self.client, symbol)
        if position is None:
            log(f"{symbol}: entry order did not open a position")
            return False
        entry = float(position["entryPrice"])
        stop = entry - max(INITIAL_STOP_ATR * s["atr"], entry * MIN_STOP_PCT)
        try:
            algo_id = self.place_stop(symbol, stop)
        except BinanceAPIError as err:
            log(f"{symbol}: could not place the stop ({err}); closing the position for safety")
            bot.close_trade(self.cfg, self.client, symbol, reason=f"{STATE_NOTE} protection-failed")
            return False

        self.state["positions"][symbol] = {"entry_day": s["day"] + DAY, "entry": entry, "qty": fmt(plan.qty),
                                           "initial_stop": stop, "stop": stop, "best": entry, "algo_id": algo_id}
        self.save_state()
        journal.log(self.cfg.journal_path, "OPEN", env=self.cfg.env, symbol=symbol, side="LONG", qty=fmt(plan.qty),
                    price=fmt(rules.round_price(entry)), stop=fmt(rules.round_price(stop)),
                    leverage=self.cfg.leverage, risk_usdt=f"{plan.risk_usdt:.2f}", note=STATE_NOTE)
        log(f"{symbol}: opened @ {price_text(entry)}, stop {price_text(stop)}")
        return True

    # ---- safety check ---------------------------------------------------------------

    def protect(self) -> None:
        """Every tracked position must have a stop on the exchange; re-place it if it's missing."""
        tracked = self.state["positions"]
        if not tracked:
            return
        exchange_positions = self.open_positions()
        algo = self.client.open_algo_orders()
        for symbol, pos in tracked.items():
            if symbol not in exchange_positions:
                continue
            if not any(o["symbol"] == symbol and o.get("orderType") == "STOP_MARKET" for o in algo):
                log(f"{symbol}: stop order missing! Re-placing at {price_text(pos['stop'])}")
                pos["algo_id"] = self.place_stop(symbol, pos["stop"])
        self.save_state()

    # ---- self-test (demo) ------------------------------------------------------------------

    def selftest(self, symbol: str) -> None:
        """Exercises the real order path on the demo account: entry, stop, trailing move, missing-stop repair, close."""
        if self.cfg.env != "demo":
            sys.exit("Self-test only runs on the demo account.")
        if symbol in self.open_positions():
            sys.exit(f"{symbol} already has an open position; pick another coin for the self-test.")
        log(f"SELF-TEST on {symbol}: forcing an entry signal")
        s = {**self.signal(self.daily(symbol)), "long": True}
        balance, available = bot.wallet(self.client)
        if not self.enter(symbol, s, balance, available):
            sys.exit("SELF-TEST FAILED: entry did not complete")

        def stops() -> list[str]:
            return [o["triggerPrice"] for o in self.client.open_algo_orders(symbol) if o.get("orderType") == "STOP_MARKET"]

        pos = self.state["positions"][symbol]
        log(f"Stop orders after entry: {stops()} (expected one at {price_text(pos['stop'])})")
        new_stop = pos["stop"] + (pos["entry"] - pos["stop"]) * 0.25
        self.move_stop(symbol, pos, new_stop)
        self.save_state()
        log(f"Stop orders after trailing move: {stops()} (expected one at {price_text(new_stop)})")
        self.client.cancel_all_algo_orders(symbol)
        log(f"Deleted the stop on purpose: {stops()} (expected none)")
        self.protect()
        log(f"Stop orders after safety check: {stops()} (expected one at {price_text(new_stop)})")
        bot.close_trade(self.cfg, self.client, symbol, reason=f"{STATE_NOTE} self-test")
        self.state["positions"].pop(symbol, None)
        self.save_state()
        log(f"Position after close: {'still open!' if bot.open_position(self.client, symbol) else 'closed'} | "
            f"stop orders left: {stops()}")
        log("SELF-TEST done")

    # ---- scan (read-only) ---------------------------------------------------------------

    def scan(self) -> None:
        exchange_positions = self.open_positions()
        print(f"Account {self.cfg.env.upper()} | open positions {len(exchange_positions)}/{MAX_OPEN} | "
              f"risk {RISK_PCT}% per trade\n")
        print(f"{'Coin':<10} {'Close':>12} {f'{LOOKBACK}d high':>12} {'EMA100':>12} {'ATR':>10}  Status")
        for symbol in SYMBOLS:
            try:
                s = self.signal(self.daily(symbol))
            except (BinanceAPIError, requests.RequestException) as err:
                print(f"{symbol:<10} error: {err}")
                continue
            if symbol in self.state["positions"]:
                pos = self.state["positions"][symbol]
                status = f"IN TRADE since {datetime.fromtimestamp(pos['entry_day'], timezone.utc):%Y-%m-%d}, stop {price_text(pos['stop'])}"
            elif s["long"]:
                status = "SIGNAL: buy at next daily open"
            elif s["ema"] and s["close"] < s["ema"]:
                status = "below EMA100: no longs"
            else:
                gap = (s["level"] - s["close"]) / s["close"] * 100
                status = f"waiting: {gap:.1f}% below the breakout level"
            print(f"{symbol:<10} {price_text(s['close']):>12} {price_text(s['level']):>12} "
                  f"{price_text(s['ema'] or 0):>12} {price_text(s['atr'] or 0):>10}  {status}")
        last = self.state.get("last_cycle_day")
        print(f"\nLast daily cycle: {last or 'never'}")

    # ---- loop ----------------------------------------------------------------------------

    def handle_trade_request(self) -> None:
        """A trade approved on the dashboard: re-check every rule now, then place it (entry + stop)."""
        if not TRADE_REQUEST.exists():
            return
        try:
            request = json.loads(TRADE_REQUEST.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            request = {}
        TRADE_REQUEST.unlink(missing_ok=True)
        symbol = str(request.get("symbol", ""))

        def result(ok: bool, message: str) -> None:
            log(f"{symbol}: {message}")
            TRADE_RESULT.write_text(json.dumps({"symbol": symbol, "ok": ok, "message": message, "time": time.time()}),
                                    encoding="utf-8")

        if time.time() - float(request.get("requested_at", 0)) > 600:
            return result(False, "approval was older than 10 minutes, ignored")
        if symbol not in SYMBOLS:
            return result(False, "not one of the bot's coins")
        log(f"{symbol}: trade approved on the dashboard, re-checking the rules")
        positions = self.open_positions()
        if symbol in positions:
            return result(False, "not placed: a position is already open on this coin")
        if len(positions) >= MAX_OPEN:
            return result(False, f"not placed: all {MAX_OPEN} position slots are in use")
        s = self.signal(self.daily(symbol))
        if not s["long"]:
            return result(False, "not placed: the buy rules no longer pass (price moved)")
        balance, available = bot.wallet(self.client)
        if not self.enter(symbol, s, balance, available):
            return result(False, "not placed: see the bot log for the reason")
        pos = self.state["positions"][symbol]
        result(True, f"bought {pos['qty']} at {price_text(pos['entry'])}, stop-loss {price_text(pos['stop'])} placed on Binance")

    def daily_due(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.state.get("last_cycle_day") != now.strftime("%Y-%m-%d") and (now.hour, now.minute) >= (0, 2)

    def manual_check_requested(self) -> bool:
        """The dashboard's "Check now" button writes this file; requests older than 10 minutes are ignored."""
        if not CHECK_FLAG.exists():
            return False
        try:
            requested = float(CHECK_FLAG.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            requested = 0
        CHECK_FLAG.unlink(missing_ok=True)
        return time.time() - requested < 600

    def tick(self) -> None:
        """One step: the daily cycle if today's hasn't run yet, then the stop safety check."""
        if self.daily_due():
            self.cycle()
        else:
            log(f"Hourly check: {len(self.state['positions'])} bot position(s), stops verified. "
                f"Last daily cycle: {self.state.get('last_cycle_day') or 'never'}; next after 00:02 UTC.")
        self.protect()

    def run(self) -> None:
        log(f"Trend bot STARTED on {self.cfg.env.upper()}. Daily cycle once per UTC day (now if not done yet), "
            "stop check hourly. Close the window or press Ctrl+C to stop.")
        next_hourly = 0.0
        while True:
            try:
                self.handle_trade_request()
                if self.manual_check_requested():
                    log("Check requested from the dashboard: running a full cycle now")
                    self.cycle()
                    self.protect()
                    next_hourly = time.time() + 3600
                elif self.daily_due() or time.time() >= next_hourly:
                    self.tick()
                    next_hourly = time.time() + 3600
            except (BinanceAPIError, requests.RequestException, ValueError) as err:
                log(f"Error: {err}. Will retry.")
            time.sleep(30)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily trend-following bot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="show signals and positions (read-only)")
    sub.add_parser("tick", help="for a scheduler (run hourly): daily cycle once per UTC day + stop check")
    selftest = sub.add_parser("selftest", help="demo only: open, trail, repair and close a small position")
    selftest.add_argument("symbol", nargs="?", default="DOGEUSDT", type=str.upper)
    run = sub.add_parser("run", help="trade the strategy")
    run.add_argument("--once", action="store_true", help="run one daily cycle now and exit")
    args = parser.parse_args()

    trend_bot = TrendBot(load_config())
    try:
        if args.command == "scan":
            trend_bot.scan()
        elif args.command == "selftest":
            trend_bot.selftest(args.symbol)
        elif args.command == "tick":
            trend_bot.tick()
        elif args.once:
            trend_bot.cycle()
            trend_bot.protect()
        else:
            trend_bot.run()
    except KeyboardInterrupt:
        log("Stopped. Open positions keep their stop orders on Binance.")
    except (BinanceAPIError, requests.RequestException) as err:
        log(f"Binance error: {err}")
        sys.exit(1)
    except Exception:
        log("Unexpected error:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()

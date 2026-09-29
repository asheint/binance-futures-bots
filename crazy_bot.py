"""Aggressive scalp bot (DEMO ONLY): scans every liquid USDT perpetual, longs and shorts, takes every setup it finds.

Each scan, for every coin (closed candles, real Binance prices):
- scores the classic confirmations traders use, for BOTH directions:
    1. EMA trend       close vs EMA 200, and EMA 50 vs EMA 200
    2. EMA 9/21        fast EMA above/below slow EMA
    3. RSI             50-70 for longs, 30-50 for shorts (momentum without being stretched)
    4. MACD            MACD above/below its signal line and the histogram growing that way
    5. Volume          last candle closed in the trade's direction on 1.2x+ average volume
    6. Higher TF       the higher timeframe trend (EMA 20 vs 50) agrees
    7. Supertrend      Supertrend (10, 3) points the same way
    8. Structure       the latest break of structure (BOS/CHoCH) was in that direction
    9. Candle          engulfing / hammer / shooting star in the last 2 candles
- a side needs at least MIN_CONFIRMATIONS and more than the other side -> market entry
- size: the position is sized so the stop-loss loses LOSS_USDT (after fees), at up to MAX_LEVERAGE
- stop-loss: STOP_AT_LIQ (80%) of the way from the entry to Binance's liquidation price for that leverage
  (liquidation is about 1/leverage - maintenance margin rate away), so each trade only holds ~LOSS_USDT of margin
- take-profit: the price where the trade nets TARGET_USDT after both fees
- no limit on the number of trades; it only stops when the margin runs out
- coins that already have a position (for example from trend_bot.py) are skipped, one position per coin

  python crazy_bot.py scan                      # show every signal now; places nothing
  python crazy_bot.py run                       # scan every 60 min (Auto) or on "Scan now" (Manual); checks trades every minute
  python crazy_bot.py run --every 15 --tf 15m --htf 1h   # faster, for testing
  python crazy_bot.py run --once                # one scan and trade, then exit
  python crazy_bot.py stats                     # wins, losses and net result of the bot's closed trades
  python crazy_bot.py closeall                  # close every position this bot opened
  python crazy_bot.py selftest DOGEUSDT         # open a tiny long, check TP/SL on Binance, close it
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
from dataclasses import replace
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

import requests

import bot
import journal
from client import BinanceAPIError, FuturesClient
from config import BASE_URLS, Config, load_config
from indicators import atr, ema, macd, rsi, sma, supertrend
from models import candles_from_klines, price_text
from patterns import find_patterns
from risk import TAKER_FEE, SymbolRules, dec, fmt
from structure import find_breaks, find_swings

NOTE = "crazy"
DATA_DIR = Path(__file__).resolve().parent / "data"
LOG_PATH = DATA_DIR / "crazy_bot.log"
STATE_PATH = DATA_DIR / "crazy_state.json"
LAST_SCAN = DATA_DIR / "crazy_last_scan.json"
CANDLES = 300
HOUSEKEEPING_SECONDS = 60
LOOP_SECONDS = 3  # how quickly the bot notices the bot page's switch and "Scan now" button
CONTROL_PATH = DATA_DIR / "crazy_control.json"  # bot page: Auto (scan every hour) or Manual (only on "Scan now")
SCAN_FLAG = DATA_DIR / "crazy_scan_now.flag"    # bot page: "Scan now" was pressed at this unix time
CLOSE_REQUEST = DATA_DIR / "crazy_close_request.json"  # bot page: close these trades by hand ({"symbols": [...] or "all"})
# The TP triggers on the traded (last) price, so it fills near the TP level. On the demo account the mark price
# follows the real market while fills happen on the thinner demo book, so a mark-price TP could fill at a loss.
TP_TRIGGER = "CONTRACT_PRICE"


def setting(name: str, default: str) -> str:
    return os.getenv(name, default).split("#")[0].strip() or default


class Settings:
    def __init__(self) -> None:
        self.loss = float(setting("CRAZY_LOSS_USDT", "2"))               # lost when the stop is hit, after fees
        self.target = float(setting("CRAZY_TARGET_USDT", "2"))           # won when the take-profit is hit, after fees
        self.max_leverage = int(setting("CRAZY_MAX_LEVERAGE", "20"))     # less where the coin allows less
        self.stop_at = float(setting("CRAZY_STOP_AT_LIQ", "0.8"))        # stop = this far along the way to liquidation
        self.min_conf = int(setting("CRAZY_MIN_CONFIRMATIONS", "5"))     # out of 9
        self.min_volume = float(setting("CRAZY_MIN_VOLUME_M", "30")) * 1e6  # 24h USDT volume to be scanned


def load_control() -> dict:
    """auto: scan every hour by itself. reverse: trade the OPPOSITE side of every signal (an experiment)."""
    defaults = {"auto": False, "reverse": False}  # Manual by default: trades only when "Scan now" is pressed
    try:
        return {**defaults, **json.loads(CONTROL_PATH.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return defaults


def close_requested() -> list[str] | str | None:
    """Symbols to close by hand ("all" for every trade), once per press; presses older than 10 minutes are ignored."""
    if not CLOSE_REQUEST.exists():
        return None
    try:
        request = json.loads(CLOSE_REQUEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        request = {}
    CLOSE_REQUEST.unlink(missing_ok=True)
    if time.time() - float(request.get("time", 0)) > 600:
        return None
    return request.get("symbols")


def scan_requested() -> bool:
    """True once per press of "Scan now"; presses older than 10 minutes are ignored."""
    if not SCAN_FLAG.exists():
        return False
    try:
        requested = float(SCAN_FLAG.read_text(encoding="utf-8").strip() or 0)
    except (OSError, ValueError):
        requested = 0
    SCAN_FLAG.unlink(missing_ok=True)
    return time.time() - requested < 600


def log(message: str) -> None:
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC] {message}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode(), flush=True)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---- signals ---------------------------------------------------------------------

def confirmations(candles: list, htf_candles: list) -> dict:
    """Scores both directions. Returns {"long": [names], "short": [names], "atr": float, "close": float}."""
    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]
    last = candles[-1]

    ema9, ema21, ema50, ema200 = ema(closes, 9), ema(closes, 21), ema(closes, 50), ema(closes, 200)
    rsi_values = rsi(closes)
    macd_line, macd_signal = macd(closes)
    atr_values = atr(highs, lows, closes)
    volume_avg = sma(volumes, 20)
    st = supertrend(highs, lows, closes)
    htf_closes = [c.close for c in htf_candles]
    htf20, htf50 = ema(htf_closes, 20), ema(htf_closes, 50)

    long: list[str] = []
    short: list[str] = []

    def vote(name: str, up: bool, down: bool) -> None:
        if up:
            long.append(name)
        elif down:
            short.append(name)

    if ema200[-1] and ema50[-1]:
        vote("EMA trend", last.close > ema200[-1] and ema50[-1] > ema200[-1],
             last.close < ema200[-1] and ema50[-1] < ema200[-1])
    if ema9[-1] and ema21[-1]:
        vote("EMA 9/21", ema9[-1] > ema21[-1], ema9[-1] < ema21[-1])
    if rsi_values[-1] is not None:
        vote("RSI", 50 < rsi_values[-1] < 70, 30 < rsi_values[-1] < 50)
    if None not in (macd_line[-1], macd_signal[-1], macd_line[-2], macd_signal[-2]):
        hist, prev_hist = macd_line[-1] - macd_signal[-1], macd_line[-2] - macd_signal[-2]
        vote("MACD", hist > 0 and hist > prev_hist, hist < 0 and hist < prev_hist)
    if volume_avg[-1]:
        loud = last.volume > 1.2 * volume_avg[-1]
        vote("Volume", loud and last.close > last.open, loud and last.close < last.open)
    if htf20[-1] and htf50[-1]:
        vote("Higher TF", htf_closes[-1] > htf50[-1] and htf20[-1] > htf50[-1],
             htf_closes[-1] < htf50[-1] and htf20[-1] < htf50[-1])
    if st[-1] is not None:
        vote("Supertrend", st[-1] == 1, st[-1] == -1)
    breaks = find_breaks(candles, find_swings(candles, atr_values, 3, 3))
    if breaks:
        vote("Structure", breaks[-1].direction == "up", breaks[-1].direction == "down")
    recent = find_patterns(candles, atr_values, lookback=2)
    if recent:
        vote("Candle", recent[-1].direction == "bull", recent[-1].direction == "bear")

    return {"long": long, "short": short, "atr": atr_values[-1] or (last.high - last.low), "close": last.close,
            "rsi": rsi_values[-1]}


def decide(conf: dict, min_conf: int) -> str | None:
    n_long, n_short = len(conf["long"]), len(conf["short"])
    if n_long >= min_conf and n_long > n_short:
        return "LONG"
    if n_short >= min_conf and n_short > n_long:
        return "SHORT"
    return None


# ---- bot -----------------------------------------------------------------------

class CrazyBot:
    def __init__(self, cfg: Config, tf: str = "1h", htf: str = "4h"):
        if cfg.env != "demo":
            sys.exit("crazy_bot.py only runs on the demo account (BINANCE_ENV=demo).")
        self.cfg = crazy_config(cfg)
        self.s = Settings()
        self.tf, self.htf = tf, htf
        self.client = bot.make_client(self.cfg)
        self.market = FuturesClient("", "", BASE_URLS["live"])  # real candles for the signals
        self.state = self.load_state()
        # open trades belong to the account that opened them; don't mix them up after a key change
        account, saved = self.cfg.api_key[:12], self.state.get("account", cfg.api_key[:12])
        if self.state["positions"] and saved != account:
            sys.exit(f"The bot's {len(self.state['positions'])} open trades are on the other account. Switch the keys back and "
                     "run 'python crazy_bot.py closeall' (or wait until they have all closed), then switch again.")
        self.state["account"] = account
        self._prepared: dict[str, int] = {}  # symbol -> leverage already set on the exchange
        self._brackets: dict[str, list] | None = None

    # ---- state --------------------------------------------------------------------

    def load_state(self) -> dict:
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"positions": {}}

    def save_state(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    # ---- market ---------------------------------------------------------------------

    def universe(self) -> list[str]:
        """USDT perpetuals tradable on the demo account with enough real 24h volume, most traded first."""
        self.client.symbol_info("BTCUSDT")  # loads exchangeInfo
        tradable = {s for s, i in (self.client._symbols or {}).items()
                    if s.isascii() and i.get("status") == "TRADING" and i.get("contractType") == "PERPETUAL" and i.get("quoteAsset") == "USDT"}
        tickers = self.market.ticker_24h()
        liquid = [(float(t["quoteVolume"]), t["symbol"]) for t in tickers
                  if t["symbol"] in tradable and float(t["quoteVolume"]) >= self.s.min_volume]
        return [symbol for _, symbol in sorted(liquid, reverse=True)]

    def candles(self, symbol: str, interval: str) -> list:
        return candles_from_klines(self.market.klines(symbol, interval, limit=CANDLES))

    def rules(self, symbol: str) -> SymbolRules:
        return SymbolRules.from_symbol_info(self.client.symbol_info(symbol))

    def positions(self) -> dict[str, dict]:
        return {p["symbol"]: p for p in self.client.position_risk() if float(p["positionAmt"]) != 0}

    # ---- scan -------------------------------------------------------------------------

    def scan(self, trade: bool) -> None:
        symbols = self.universe()
        open_now = self.positions()
        balance, available = bot.wallet(self.client)
        log(f"Scan {self.tf} (trend check {self.htf}) on {len(symbols)} coins | balance {balance:.2f}, "
            f"available {available:.2f} USDT | need {self.s.min_conf}/9 confirmations | "
            f"{'TRADING' if trade else 'read-only'}")
        report, opened, signals = [], 0, 0
        self._brackets = None  # refreshed every scan
        self.state["scanning"] = trade  # the bot page shows the robot scanning
        self.save_state()
        for symbol in symbols:
            try:
                candles = self.candles(symbol, self.tf)
                htf_candles = self.candles(symbol, self.htf)
                if len(candles) < 210 or len(htf_candles) < 60:
                    continue
                conf = confirmations(candles, htf_candles)
            except (BinanceAPIError, requests.RequestException, ValueError) as err:
                log(f"{symbol}: no data ({err})")
                continue
            side = decide(conf, self.s.min_conf)
            row = {"symbol": symbol, "long": conf["long"], "short": conf["short"], "side": side, "action": ""}
            report.append(row)
            if not side:
                continue
            signals += 1
            reasons = ", ".join(conf[side.lower()])
            if symbol in open_now or symbol in self.state["positions"]:
                row["action"] = "skipped: position already open"
                if not trade:
                    log(f"{symbol}: {side} {len(conf[side.lower()])}/9 [{reasons}] (already in a position)")
                continue
            if not trade:
                log(f"{symbol}: {side} {len(conf[side.lower()])}/9 [{reasons}] @ {price_text(conf['close'])}")
                continue
            if available < 5:
                row["action"] = "skipped: out of margin"
                log(f"{symbol}: {side} signal, but only {available:.2f} USDT margin left")
                continue
            signal_side = side
            if load_control()["reverse"]:
                side = "SHORT" if side == "LONG" else "LONG"  # reverse mode: do the opposite of the signal
            try:
                if self.enter(symbol, side, conf, signal_side):
                    opened += 1
                    row["action"] = "opened"
                    _, available = bot.wallet(self.client)
            except BinanceAPIError as err:
                row["action"] = f"error: {err.msg}"
                log(f"{symbol}: entry failed ({err})")
        LAST_SCAN.write_text(json.dumps({"time": time.time(), "tf": self.tf, "coins": report}), encoding="utf-8")
        self.state.update(scanning=False, last_scan={"time": time.time(), "coins": len(symbols), "signals": signals,
                                                     "opened": opened})
        self.save_state()
        log(f"Scan done: {signals} signals, {opened} trades opened, {len(self.state['positions'])} bot positions open")

    # ---- trading ------------------------------------------------------------------------

    def brackets(self, symbol: str) -> list[dict]:
        if self._brackets is None:
            self._brackets = {b["symbol"]: b["brackets"] for b in self.client.leverage_brackets()}
        return self._brackets.get(symbol, [])

    def size(self, symbol: str, rules: SymbolRules, mark: Decimal) -> tuple[int, Decimal, float]:
        """Leverage, quantity and stop distance (fraction of price) so that the stop, placed STOP_AT_LIQ of the way
        to the liquidation price, loses LOSS_USDT including fees. Raises ValueError when the coin can't fit that."""
        brackets = self.brackets(symbol)
        if not brackets:
            raise ValueError("no leverage brackets")
        first = brackets[0]
        leverage = min(self.s.max_leverage, int(first["initialLeverage"]))
        # liquidation sits about 1/leverage - MMR from the entry (Binance's isolated-margin formula, first bracket)
        to_liquidation = 1 / leverage - float(first["maintMarginRatio"])
        if to_liquidation <= 0.003:
            raise ValueError(f"liquidation too close at {leverage}x")
        stop = self.s.stop_at * to_liquidation
        notional = dec(self.s.loss) / (dec(stop) + TAKER_FEE * 2)
        qty = rules.round_qty(notional / mark)
        if qty * mark < rules.min_notional:
            qty += rules.step_size
        if qty < rules.min_qty or qty * mark < rules.min_notional:
            raise ValueError(f"the smallest order ({fmt(rules.min_notional)} USDT) would lose more than {self.s.loss:g} USDT")
        if qty * mark >= dec(first["notionalCap"]):
            raise ValueError("position would be above the first margin bracket")
        return leverage, qty, stop

    def enter(self, symbol: str, side: str, conf: dict, signal_side: str | None = None) -> bool:
        """Opens `side`. In reverse mode `signal_side` is the direction the confirmations actually pointed."""
        signal_side = signal_side or side
        reverse = signal_side != side
        rules = self.rules(symbol)
        mark = dec(self.client.mark_price(symbol))
        try:
            leverage, qty, stop_frac = self.size(symbol, rules, mark)
        except ValueError as err:
            log(f"{symbol}: skipped ({err})")
            return False
        _, available = bot.wallet(self.client)
        if qty * mark / leverage > dec(available) * dec("0.95"):
            log(f"{symbol}: {side} signal, but only {available:.2f} USDT margin left")
            return False
        try:
            if self._prepared.get(symbol) != leverage:
                bot.prepare_account(self.client, symbol, leverage)
                self._prepared[symbol] = leverage
        except BinanceAPIError as err:
            log(f"{symbol}: can't set {leverage}x isolated ({err.msg}); skipped")
            return False
        bot.cancel_symbol_orders(self.client, symbol)  # no position here, so any order left is an orphan

        entry_side, exit_side = ("BUY", "SELL") if side == "LONG" else ("SELL", "BUY")
        self.client.new_order(symbol=symbol, side=entry_side, type="MARKET", quantity=fmt(qty), newOrderRespType="RESULT")
        pos = bot.open_position(self.client, symbol)
        if pos is None:
            log(f"{symbol}: entry order did not open a position")
            return False
        entry = dec(pos["entryPrice"])
        qty = abs(dec(pos["positionAmt"]))
        sign = 1 if side == "LONG" else -1

        # take-profit: net TARGET after paying the taker fee on the way in and out
        fees = entry * qty * TAKER_FEE * 2
        tp_distance = (dec(self.s.target) + fees) / qty
        # stop-loss: STOP_AT_LIQ of the way to the liquidation price Binance reports for this position
        liquidation = dec(pos.get("liquidationPrice") or 0)
        sl_distance = (abs(liquidation - entry) if liquidation > 0 else entry / leverage) * dec(self.s.stop_at)
        sl_distance = min(sl_distance, entry * dec(stop_frac) * dec("1.1"))
        tp_raw, sl_raw = entry + sign * tp_distance, entry - sign * sl_distance
        # round the TP away from entry so the profit is never below target
        tick = rules.tick_size
        tp = (tp_raw / tick).to_integral_value(ROUND_CEILING if side == "LONG" else ROUND_FLOOR) * tick
        sl = rules.round_price(sl_raw)

        try:
            sl_order = self.client.new_algo_order(symbol=symbol, side=exit_side, type="STOP_MARKET", triggerPrice=fmt(sl),
                                                  closePosition=True, workingType="MARK_PRICE", priceProtect=True)
            tp_order = self.client.new_algo_order(symbol=symbol, side=exit_side, type="TAKE_PROFIT_MARKET",
                                                  triggerPrice=fmt(tp), closePosition=True, workingType=TP_TRIGGER)
        except BinanceAPIError as err:
            log(f"{symbol}: could not place TP/SL ({err.msg}); closing the position")
            bot.close_trade(self.cfg, self.client, symbol, reason=f"{NOTE} protection-failed")
            return False

        loss_at_sl = qty * sl_distance + fees
        reasons = conf[signal_side.lower()]
        mode = "reverse" if reverse else "normal"
        self.state["positions"][symbol] = {
            "side": side, "entry": float(entry), "qty": fmt(qty), "sl": float(sl), "tp": float(tp),
            "opened_at": int(time.time() * 1000), "reasons": reasons, "mode": mode,
            "sl_id": sl_order.get("algoId"), "tp_id": tp_order.get("algoId"),
        }
        self.save_state()
        journal.log(self.cfg.journal_path, "OPEN", env=self.cfg.env, symbol=symbol, side=side, qty=fmt(qty),
                    price=fmt(rules.round_price(entry)), stop=fmt(sl), take_profit=fmt(tp), leverage=leverage,
                    risk_usdt=f"{loss_at_sl:.2f}",
                    note=f"{NOTE}{' reverse' if reverse else ''} {len(reasons)}/9: {', '.join(reasons)}")
        log(f"{symbol}: OPENED {side}{f' (REVERSE of a {signal_side} signal)' if reverse else ''} {fmt(qty)} @ {price_text(float(entry))} {leverage}x | TP {fmt(tp)} (+{self.s.target:.2f}) | "
            f"SL {fmt(sl)} (-{loss_at_sl:.2f}) | liq {price_text(float(liquidation))} | {len(reasons)}/9 {', '.join(reasons)}")
        return True

    # ---- housekeeping -------------------------------------------------------------------

    def realized(self, symbol: str, since_ms: int, side: str) -> float | None:
        """Net result since the entry (PnL + fees + funding); None until Binance has booked the closing PnL."""
        rows = self.client.income(symbol, start_time=since_ms)
        if not any(r["incomeType"] == "REALIZED_PNL" for r in rows):
            # a trade closed at exactly its entry price has zero PnL, and Binance books no REALIZED_PNL for it:
            # it's finished if a closing fill exists, and its result is just the fees
            closing_side = "SELL" if side == "LONG" else "BUY"
            if not any(t["side"] == closing_side for t in self.client.user_trades(symbol, start_time=since_ms)):
                return None
        return sum(float(r["income"]) for r in rows if r["incomeType"] in ("REALIZED_PNL", "COMMISSION", "FUNDING_FEE"))

    def exit_price(self, symbol: str, pos: dict) -> float | None:
        """Average fill price of the closing trades."""
        closing_side = "SELL" if pos["side"] == "LONG" else "BUY"
        fills = [t for t in self.client.user_trades(symbol, start_time=pos["opened_at"]) if t["side"] == closing_side]
        qty = sum(float(t["qty"]) for t in fills)
        return sum(float(t["price"]) * float(t["qty"]) for t in fills) / qty if qty else None

    def housekeeping(self) -> None:
        """Logs closed trades, cancels the leftover TP or SL, and re-places missing TP/SL on open ones."""
        tracked = self.state["positions"]
        self.state["heartbeat"] = time.time()  # the dashboard uses this to show "running"
        if not tracked:
            self.save_state()
            return
        open_now = self.positions()
        algo = self.client.open_algo_orders()
        for symbol, pos in list(tracked.items()):
            if symbol not in open_now:
                bot.cancel_symbol_orders(self.client, symbol)
                pnl = self.realized(symbol, pos["opened_at"], pos["side"])
                if pnl is None and time.time() * 1000 - pos["opened_at"] < 86_400_000:
                    continue  # closing PnL not booked yet; check again next minute
                pnl = pnl or 0.0
                exit_price = self.exit_price(symbol, pos) or (pos["tp"] if pnl > 0 else pos["sl"])
                # which order closed it: the exit is nearer to that order's level
                outcome = pos.get("closing") or ("TP" if abs(exit_price - pos["tp"]) < abs(exit_price - pos["sl"]) else "SL")
                journal.log(self.cfg.journal_path, "CLOSE", env=self.cfg.env, symbol=symbol, side=pos["side"],
                            qty=pos["qty"], price=f"{exit_price:.8g}", pnl_usdt=f"{pnl:.2f}",
                            note=f"{NOTE}{' reverse' if pos.get('mode') == 'reverse' else ''} {outcome}")
                log(f"{symbol}: {pos['side']} CLOSED by {outcome} @ {price_text(exit_price)} | "
                    f"net {pnl:+.2f} USDT (after fees)")
                tracked.pop(symbol)
                continue
            if (float(open_now[symbol]["positionAmt"]) > 0) != (pos["side"] == "LONG"):
                # another bot (the news bot) closed this trade and opened the other side: that coin is its now
                log(f"{symbol}: taken over by another bot (now the opposite side); no longer tracked here")
                journal.log(self.cfg.journal_path, "CLOSE", env=self.cfg.env, symbol=symbol, side=pos["side"],
                            qty=pos["qty"], pnl_usdt=f"{(self.realized(symbol, pos['opened_at'], pos['side']) or 0):.2f}",
                            note=f"{NOTE} taken over")
                tracked.pop(symbol)
                continue
            exit_side = "SELL" if pos["side"] == "LONG" else "BUY"
            mine = [o for o in algo if o["symbol"] == symbol]
            for o in mine:
                if o.get("orderType") == "TAKE_PROFIT_MARKET" and o.get("workingType") != TP_TRIGGER:
                    self.client.cancel_algo_order(o["algoId"])  # older TP on the mark price: re-placed below
            kinds = {o.get("orderType") for o in mine
                     if not (o.get("orderType") == "TAKE_PROFIT_MARKET" and o.get("workingType") != TP_TRIGGER)}
            for kind, price, trigger in (("STOP_MARKET", pos["sl"], "MARK_PRICE"),
                                         ("TAKE_PROFIT_MARKET", pos["tp"], TP_TRIGGER)):
                if kind not in kinds:
                    log(f"{symbol}: {kind} missing, re-placing at {price_text(price)}")
                    try:
                        self.client.new_algo_order(symbol=symbol, side=exit_side, type=kind,
                                                   triggerPrice=fmt(self.rules(symbol).round_price(price)),
                                                   closePosition=True, workingType=trigger)
                    except BinanceAPIError as err:
                        log(f"{symbol}: re-place failed ({err.msg}); closing the position")
                        bot.close_trade(self.cfg, self.client, symbol, reason=f"{NOTE} protection-failed")
                        break
        self.save_state()

    def close_by_hand(self, symbols: list[str] | str) -> None:
        """Closes the chosen trades at market right now (button on the bot page). Housekeeping then books the result."""
        chosen = list(self.state["positions"]) if symbols == "all" else [s for s in symbols if s in self.state["positions"]]
        log(f"Closing by hand: {', '.join(chosen) or 'nothing to close'}")
        for symbol in chosen:
            pos = self.state["positions"][symbol]
            pos["closing"] = "manual"
            try:
                bot.cancel_symbol_orders(self.client, symbol)
                live = bot.open_position(self.client, symbol)
                if live:
                    amount = float(live["positionAmt"])
                    self.client.new_order(symbol=symbol, side="SELL" if amount > 0 else "BUY", type="MARKET",
                                          quantity=live["positionAmt"].lstrip("-"), reduceOnly=True, newOrderRespType="RESULT")
            except BinanceAPIError as err:
                log(f"{symbol}: close failed ({err.msg}); will retry on the next check")
                pos.pop("closing", None)
        self.save_state()
        time.sleep(1)
        self.housekeeping()

    def close_all(self) -> None:
        for symbol in list(self.state["positions"]):
            bot.close_trade(self.cfg, self.client, symbol, reason=f"{NOTE} closeall")
            self.state["positions"].pop(symbol)
        self.save_state()

    # ---- loop ---------------------------------------------------------------------------

    def run(self, every_minutes: float) -> None:
        log(f"Crazy bot STARTED on DEMO: {self.tf} signals, scan every {every_minutes:g} min, "
            f"TP +{self.s.target:g} / SL -{self.s.loss:g} USDT net per trade, up to {self.s.max_leverage}x, "
            f"stop {self.s.stop_at:.0%} of the way to liquidation. Ctrl+C to stop (open trades keep their TP/SL on Binance).")
        every = every_minutes * 60
        # a restart keeps the hourly rhythm instead of scanning again straight away
        last_started = float(self.state.get("last_scan_started") or self.state.get("last_scan", {}).get("time", 0))
        next_housekeeping, was_auto = 0.0, None
        while True:
            try:
                auto = load_control()["auto"]
                if auto != was_auto:
                    log("Auto mode: scanning every hour by myself" if auto else "Manual mode: scanning only when 'Scan now' is pressed")
                    was_auto = auto
                to_close = close_requested()
                if to_close:
                    self.close_by_hand(to_close)
                pressed = scan_requested()
                self.state["auto"] = auto
                self.state["next_scan"] = last_started + every if auto else None
                if pressed or (auto and time.time() >= last_started + every):
                    if pressed:
                        log("Scan requested from the bot page")
                    last_started = time.time()
                    self.state.update(last_scan_started=last_started, next_scan=last_started + every if auto else None)
                    self.housekeeping()
                    self.scan(trade=True)
                    next_housekeeping = time.time() + HOUSEKEEPING_SECONDS
                elif time.time() >= next_housekeeping:
                    self.housekeeping()
                    next_housekeeping = time.time() + HOUSEKEEPING_SECONDS
            except (BinanceAPIError, requests.RequestException, ValueError) as err:
                log(f"Error: {err}. Will retry.")
                next_housekeeping = time.time() + HOUSEKEEPING_SECONDS
            time.sleep(LOOP_SECONDS)

    # ---- self-test -------------------------------------------------------------------------

    def selftest(self, symbol: str) -> None:
        if symbol in self.positions():
            sys.exit(f"{symbol} already has a position; pick another coin.")
        log(f"SELF-TEST on {symbol}: forcing a small LONG")
        conf = confirmations(self.candles(symbol, self.tf), self.candles(symbol, self.htf))
        conf["long"] = ["self-test"]
        if not self.enter(symbol, "LONG", conf):
            sys.exit("SELF-TEST FAILED: entry did not complete")
        orders = [(o.get("orderType"), o.get("triggerPrice")) for o in self.client.open_algo_orders(symbol)]
        log(f"Orders on Binance: {orders} (expected one STOP_MARKET and one TAKE_PROFIT_MARKET)")
        bot.close_trade(self.cfg, self.client, symbol, reason=f"{NOTE} self-test")
        self.state["positions"].pop(symbol, None)
        self.save_state()
        left = self.client.open_algo_orders(symbol)
        log(f"After close: position {'still open!' if bot.open_position(self.client, symbol) else 'closed'}, "
            f"orders left {len(left)}")
        log("SELF-TEST done")


def crazy_config(cfg: Config) -> Config:
    """The crazy bot's own account when CRAZY_API_KEY and CRAZY_API_SECRET are set in .env (with its own journal,
    crazy_trades.csv); otherwise it shares the main account and trades.csv."""
    key, secret = setting("CRAZY_API_KEY", ""), setting("CRAZY_API_SECRET", "")
    if not (key and secret):
        return cfg
    return replace(cfg, api_key=key, api_secret=secret, base_url=setting("CRAZY_BASE_URL", cfg.base_url),
                   journal_path=cfg.journal_path.parent / "crazy_trades.csv")


def closed_trades(cfg: Config) -> list[dict]:
    """Every closed crazy-bot trade in the journal, oldest first (self-tests excluded)."""
    if not cfg.journal_path.exists():
        return []
    out = []
    with cfg.journal_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            note = row.get("note") or ""
            if row.get("event") != "CLOSE" or not note.startswith(NOTE) or "self-test" in note or not row.get("pnl_usdt"):
                continue
            words = note.split()
            outcome = next((w for w in words if w in ("TP", "SL")), "closed")
            out.append({"time": int(datetime.fromisoformat(row["time"]).timestamp()), "symbol": row["symbol"],
                        "side": row["side"], "pnl": float(row["pnl_usdt"]), "outcome": outcome,
                        "mode": "reverse" if "reverse" in words else "normal"})
    return out


def closed_results(cfg: Config) -> list[float]:
    return [t["pnl"] for t in closed_trades(cfg)]


def stats(cfg: Config) -> None:
    pnls = closed_results(cfg)
    if not pnls:
        print("No closed crazy-bot trades yet.")
        return
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    print(f"Closed trades: {len(pnls)} | wins {len(wins)} ({len(wins) / len(pnls):.0%}) | losses {len(losses)}")
    print(f"Average win {sum(wins) / len(wins) if wins else 0:+.2f} | average loss {sum(losses) / len(losses) if losses else 0:+.2f}")
    print(f"Net result {sum(pnls):+.2f} USDT (after fees)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggressive long/short scalp bot (demo only)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--tf", default="1h", help="signal timeframe (default 1h)")
        p.add_argument("--htf", default="4h", help="higher timeframe for the trend check (default 4h)")
        p.add_argument("--min-conf", type=int, help="confirmations needed out of 9 (default from .env, 5)")
        if name == "run":
            p.add_argument("--every", type=float, default=60, help="minutes between scans (default 60)")
            p.add_argument("--once", action="store_true", help="one scan, then exit")
    sub.add_parser("stats")
    sub.add_parser("closeall")
    st = sub.add_parser("selftest")
    st.add_argument("symbol", nargs="?", default="DOGEUSDT", type=str.upper)
    args = parser.parse_args()

    cfg = load_config()
    if args.command == "stats":
        return stats(crazy_config(cfg))
    crazy = CrazyBot(cfg, getattr(args, "tf", "1h"), getattr(args, "htf", "4h"))
    if getattr(args, "min_conf", None):
        crazy.s.min_conf = args.min_conf
    try:
        if args.command == "scan":
            crazy.scan(trade=False)
        elif args.command == "closeall":
            crazy.close_all()
        elif args.command == "selftest":
            crazy.selftest(args.symbol)
        elif args.once:
            crazy.housekeeping()
            crazy.scan(trade=True)
        else:
            crazy.run(args.every)
    except KeyboardInterrupt:
        log("Stopped. Open trades keep their TP/SL orders on Binance.")
    except (BinanceAPIError, requests.RequestException) as err:
        log(f"Binance error: {err}")
        sys.exit(1)
    except Exception:
        log("Unexpected error:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()

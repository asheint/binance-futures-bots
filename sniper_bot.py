"""Sniper bot (DEMO ONLY): trades the way discretionary traders do. It marks its lines, waits, and only fires
when price actually reaches them.

Every 15 minutes (right after a 15m candle closes), for each liquid coin:
1. Context (4h): trend = market structure (higher highs/lows or lower highs/lows) AND the 200 EMA agree.
   No trend -> no plan. Altcoins also need BTC not trending or dumping against the trade.
2. Location (1h): key levels = support/resistance zones built from swing points, plus the previous day's
   high/low. The Fibonacci 0.5-0.618 zone of the last 4h leg is a bonus when it overlaps a level.
3. Lines (only in the trend's direction), e.g. in an uptrend:
   - BOUNCE:   LONG if a 15m candle dips into the nearest support zone and closes back above it
   - BREAKOUT: LONG if a 1h candle closes above the nearest resistance (not too far above it)
4. Trigger: only a CLOSED candle counts, never a touch.
5. Risk plan: stop just beyond the level/wick, target = the next level (or 3R in open air).
   Skipped unless the target is at least MIN_RR times the risk. Sized so the stop loses RISK_USDT.
   At +1R half is taken off and the stop moves to break-even. Closed after MAX_HOLD_H hours.
6. "Not now" filters: choppy market (1h ADX < ADX_MIN), crowded funding, BTC against the trade.
Grade shown per trade: A+ with 2+ bonuses (sweep, volume, Fibonacci), A with 1, B with none.

  python sniper_bot.py run          # plan every 15 minutes, fire on triggers, manage trades
  python sniper_bot.py plan         # print every coin's context and lines now; places nothing
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

import bot
import journal
from client import BinanceAPIError, FuturesClient
from config import BASE_URLS, Config, load_config
from indicators import adx, atr, ema, sma
from levels import fibonacci, find_zones
from models import Candle, candles_from_klines, price_text
from patterns import find_patterns
from risk import TAKER_FEE, SymbolRules, dec, fmt
from structure import find_breaks, find_swings, trend_state

NOTE = "sniper"
DATA_DIR = Path(__file__).resolve().parent / "data"
LOG_PATH = DATA_DIR / "sniper_bot.log"
STATE_PATH = DATA_DIR / "sniper_state.json"
CONTROL_PATH = DATA_DIR / "sniper_control.json"          # page: {"trading": true/false}
CLOSE_REQUEST = DATA_DIR / "sniper_close_request.json"   # page: close these trades by hand
CYCLE = 900            # plan every 15 minutes
CYCLE_DELAY = 20       # seconds after the 15m candle closes (let the exchange finish the candle)
HOUSEKEEPING_SECONDS = 30
LOOP_SECONDS = 3


def setting(name: str, default: str) -> str:
    return os.getenv(name, default).split("#")[0].strip() or default


class Settings:
    def __init__(self) -> None:
        self.risk = float(setting("SNIPER_RISK_USDT", "10"))           # lost when the stop is hit, after fees
        self.min_rr = float(setting("SNIPER_MIN_RR", "2"))             # skip unless target >= this x risk
        self.max_leverage = int(setting("SNIPER_MAX_LEVERAGE", "10"))
        self.min_volume = float(setting("SNIPER_MIN_VOLUME_M", "50")) * 1e6
        self.max_coins = int(setting("SNIPER_MAX_COINS", "40"))
        self.max_hold = float(setting("SNIPER_MAX_HOLD_H", "48"))
        self.adx_min = float(setting("SNIPER_ADX_MIN", "20"))


def load_control() -> dict:
    defaults = {"trading": True}
    try:
        return {**defaults, **json.loads(CONTROL_PATH.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return defaults


def close_requested() -> list[str] | str | None:
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


# ---- reading the chart -------------------------------------------------------------------

@dataclass
class Level:
    low: float
    high: float
    label: str
    touches: int = 0


def context(candles: list[Candle]) -> tuple[str | None, str]:
    """4h trend: 'up' / 'down' when market structure and the 200 EMA agree, else None."""
    closes = [c.close for c in candles]
    a = atr([c.high for c in candles], [c.low for c in candles], closes)
    swings = find_swings(candles, a, 5, 5)
    trend, _ = trend_state(swings, find_breaks(candles, swings))
    e200 = ema(closes, 200)[-1]
    if e200 is None:
        return None, "not enough history"
    if trend == "up" and closes[-1] > e200:
        return "up", "4h uptrend: higher highs and lows, above EMA 200"
    if trend == "down" and closes[-1] < e200:
        return "down", "4h downtrend: lower highs and lows, below EMA 200"
    reason = {"range": "4h structure is mixed (ranging)", "unclear": "4h structure unclear"}.get(trend, "")
    return None, reason or f"4h {trend}trend but on the wrong side of EMA 200"


def key_levels(h1: list[Candle], price: float) -> tuple[list[Level], list[Level], float]:
    """(supports nearest first, resistances nearest first, 1h ATR)."""
    highs, lows, closes = [c.high for c in h1], [c.low for c in h1], [c.close for c in h1]
    a_values = atr(highs, lows, closes)
    a = a_values[-1] or (highs[-1] - lows[-1])
    supports_z, resistances_z = find_zones(find_swings(h1, a_values, 5, 5), a, price, per_side=4)
    supports = [Level(z.low, z.high, f"support zone ({z.touches} touches)", z.touches) for z in supports_z]
    resistances = [Level(z.low, z.high, f"resistance zone ({z.touches} touches)", z.touches) for z in resistances_z]
    # previous UTC day's high and low
    today = h1[-1].time // 86400
    prev = [c for c in h1 if c.time // 86400 == today - 1]
    if prev:
        pdh, pdl = max(c.high for c in prev), min(c.low for c in prev)
        pad = a * 0.15
        for value, label in ((pdh, "previous day high"), (pdl, "previous day low")):
            level = Level(value - pad, value + pad, label, 1)
            (supports if value < price else resistances).append(level)
    supports.sort(key=lambda z: price - z.high)
    resistances.sort(key=lambda z: z.low - price)
    return supports, resistances, a


def golden_zone(h4: list[Candle], trend: str) -> tuple[float, float] | None:
    closes = [c.close for c in h4]
    a = atr([c.high for c in h4], [c.low for c in h4], closes)
    fib = fibonacci(find_swings(h4, a, 5, 5), trend, min_leg=(a[-1] or 0) * 3)
    if not fib or len(fib["golden"]) < 2:
        return None
    return fib["golden"][0], fib["golden"][1]


def overlaps(level: Level, zone: tuple[float, float] | None) -> bool:
    return bool(zone) and level.low <= zone[1] and level.high >= zone[0]


def plan_coin(symbol: str, h4: list[Candle], h1: list[Candle], m15: list[Candle], btc: dict, s: Settings) -> dict:
    """Everything the page shows for one coin, plus a 'fire' entry when a trigger candle just closed."""
    price = m15[-1].close
    out: dict = {"symbol": symbol, "price": price, "bias": None, "context": "", "plans": [], "skip": "", "fire": None}
    bias, why = context(h4)
    out["context"] = why
    if not bias:
        out["skip"] = "no trend on 4h"
        return out
    out["bias"] = bias
    if symbol != "BTCUSDT":
        if bias == "up" and (btc.get("bias") == "down" or btc.get("move", 0) < -0.02):
            out["skip"] = "BTC is falling: no altcoin longs"
            return out
        if bias == "down" and (btc.get("bias") == "up" or btc.get("move", 0) > 0.02):
            out["skip"] = "BTC is rising: no altcoin shorts"
            return out
    adx_now = adx([c.high for c in h1], [c.low for c in h1], [c.close for c in h1])[-1] or 0
    out["adx"] = adx_now
    if adx_now < s.adx_min:
        out["skip"] = f"choppy market (1h ADX {adx_now:.0f} < {s.adx_min:.0f})"
        return out

    supports, resistances, a1 = key_levels(h1, price)
    fib = golden_zone(h4, bias)
    up = bias == "up"
    side = "LONG" if up else "SHORT"
    # levels the price comes back to (bounce) and levels it breaks (breakout), in the trend's direction
    pullback_levels = supports if up else resistances
    break_levels = resistances if up else supports
    targets = resistances if up else supports

    bounce = next((z for z in pullback_levels if abs(price - (z.high if up else z.low)) <= 4 * a1), None)
    breakout = next((z for z in break_levels if abs((z.high if up else z.low) - price) <= 3 * a1), None)
    edge = lambda z: z.high if up else z.low  # noqa: E731  the side of the zone price must close beyond
    if bounce:
        out["plans"].append({"kind": "bounce", "side": side, "low": bounce.low, "high": bounce.high, "label": bounce.label,
                             "fib": overlaps(bounce, fib),
                             "text": f"{side} if a 15m candle dips into {price_text(bounce.low)}–{price_text(bounce.high)} "
                                     f"and closes back {'above' if up else 'below'} {price_text(edge(bounce))}"})
    if breakout:
        out["plans"].append({"kind": "breakout", "side": side, "low": breakout.low, "high": breakout.high, "label": breakout.label,
                             "fib": False,
                             "text": f"{side} if a 1h candle closes {'above' if up else 'below'} {price_text(edge(breakout))}"})
    if not out["plans"]:
        out["skip"] = "no key level near price: waiting for price to come to a level"
        return out

    # ---- triggers: the candle that just closed
    k = m15[-1]
    m15_atr = atr([c.high for c in m15], [c.low for c in m15], [c.close for c in m15])[-1] or (k.high - k.low)
    vol15 = sma([c.volume for c in m15], 20)[-1] or 0
    if bounce:
        dipped = k.low <= bounce.high if up else k.high >= bounce.low
        reclaimed = (k.close > bounce.high and k.close > k.open) if up else (k.close < bounce.low and k.close < k.open)
        if dipped and reclaimed:
            sweep = k.low < bounce.low if up else k.high > bounce.high
            stop = (min(k.low, bounce.low) - 0.25 * m15_atr) if up else (max(k.high, bounce.high) + 0.25 * m15_atr)
            pats = [p for p in find_patterns(m15, [m15_atr] * len(m15), lookback=1) if p.direction == ("bull" if up else "bear")]
            bonuses = [b for b, ok in (("liquidity sweep", sweep), ("volume", vol15 and k.volume > 1.5 * vol15),
                                       ("Fibonacci 0.5–0.618", overlaps(bounce, fib)),
                                       (pats[0].name.lower() if pats else "", bool(pats))) if ok and b]
            out["fire"] = {"kind": "bounce", "candle": k.time, "stop": stop, "level": bounce.label, "bonuses": bonuses,
                           "why": f"dipped into the {bounce.label} {price_text(bounce.low)}–{price_text(bounce.high)} "
                                  f"and closed back {'above' if up else 'below'} it"}
    last_h = h1[-1]
    if not out["fire"] and last_h.time + 3600 >= k.time + 900:  # a 1h candle closed together with this 15m one
        prev_close = h1[-2].close
        # the level it broke now sits on the other side of price, so look at every level, not just those ahead
        crossed = [z for z in supports + resistances
                   if ((prev_close <= z.high < last_h.close) if up else (prev_close >= z.low > last_h.close))
                   and abs(last_h.close - edge(z)) <= a1]  # not chasing: closed close to the level
        if crossed:
            broken = max(crossed, key=edge) if up else min(crossed, key=edge)
            vol1 = sma([c.volume for c in h1], 20)[-1] or 0
            stop = (broken.low - 0.25 * a1) if up else (broken.high + 0.25 * a1)
            bonuses = ["volume"] if vol1 and last_h.volume > 1.5 * vol1 else []
            out["fire"] = {"kind": "breakout", "candle": last_h.time, "stop": stop, "level": broken.label, "bonuses": bonuses,
                           "why": f"1h candle closed {'above' if up else 'below'} the {broken.label} at {price_text(edge(broken))}"}
    if out["fire"]:
        out["fire"]["side"] = side
        out["fire"]["targets"] = [(t.low if up else t.high, t.label) for t in targets]
        out["fire"]["a1"] = a1
    return out


# ---- the bot -----------------------------------------------------------------------------

class SniperBot:
    def __init__(self, cfg: Config):
        if cfg.env != "demo":
            sys.exit("sniper_bot.py only runs on the demo account (BINANCE_ENV=demo).")
        self.cfg = cfg
        self.s = Settings()
        self.client = bot.make_client(cfg)
        self.market = FuturesClient("", "", BASE_URLS["live"])  # real candles for the chart reading
        self.state = self.load_state()
        self._brackets: dict[str, list] | None = None

    def load_state(self) -> dict:
        try:
            return {"positions": {}, "fired": [], "watch": [], **json.loads(STATE_PATH.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            return {"positions": {}, "fired": [], "watch": []}

    def save_state(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.state["fired"] = self.state["fired"][-400:]
        STATE_PATH.write_text(json.dumps(self.state, indent=1), encoding="utf-8")

    # ---- market -------------------------------------------------------------------------

    def universe(self) -> list[str]:
        self.client.symbol_info("BTCUSDT")
        tradable = {s for s, i in (self.client._symbols or {}).items()
                    if s.isascii() and i.get("status") == "TRADING" and i.get("contractType") == "PERPETUAL"
                    and i.get("quoteAsset") == "USDT"}
        liquid = sorted(((float(t["quoteVolume"]), t["symbol"]) for t in self.market.ticker_24h()
                         if t["symbol"] in tradable and float(t["quoteVolume"]) >= self.s.min_volume), reverse=True)
        symbols = [sym for _, sym in liquid[:self.s.max_coins]]
        return ["BTCUSDT"] + [x for x in symbols if x != "BTCUSDT"]

    def candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        return candles_from_klines(self.market.klines(symbol, interval, limit=limit))

    def positions(self) -> dict[str, dict]:
        return {p["symbol"]: p for p in self.client.position_risk() if float(p["positionAmt"]) != 0}

    def rules(self, symbol: str) -> SymbolRules:
        return SymbolRules.from_symbol_info(self.client.symbol_info(symbol))

    # ---- the 15-minute cycle ------------------------------------------------------------------

    def cycle(self, trade: bool) -> None:
        self.state["cycle_running"] = True
        self.save_state()
        self._brackets = None
        symbols = self.universe()
        open_now = self.positions()
        btc: dict = {}
        watch, fired = [], 0
        for symbol in symbols:
            try:
                h4 = self.candles(symbol, "4h", 300)
                h1 = self.candles(symbol, "1h", 300)
                m15 = self.candles(symbol, "15m", 120)
                if len(h4) < 210 or len(h1) < 120 or len(m15) < 60:
                    continue
                if symbol == "BTCUSDT":
                    btc = {"bias": context(h4)[0], "move": h1[-1].close / h1[-5].close - 1}
                p = plan_coin(symbol, h4, h1, m15, btc, self.s)
            except (BinanceAPIError, requests.RequestException, ValueError, ZeroDivisionError) as err:
                log(f"{symbol}: no data ({err})")
                continue
            fire = p.pop("fire")
            p["status"] = "in a trade" if symbol in self.state["positions"] else ("busy: another bot holds it" if symbol in open_now else "")
            watch.append(p)
            if not fire:
                continue
            key = f"{symbol}:{fire['kind']}:{fire['candle']}"
            if key in self.state["fired"]:
                continue
            self.state["fired"].append(key)
            if not trade:
                log(f"{symbol}: TRIGGER {fire['side']} {fire['kind']} ({fire['why']}) - trading is paused, not fired")
                continue
            if symbol in open_now:
                log(f"{symbol}: TRIGGER {fire['side']} {fire['kind']}, but a position is already open on this coin")
                continue
            try:
                if self.fire(symbol, fire):
                    fired += 1
                    open_now = self.positions()
            except BinanceAPIError as err:
                log(f"{symbol}: entry failed ({err.msg})")
        ranked = sorted(watch, key=lambda w: (0 if w["plans"] else 1, w["symbol"] != "BTCUSDT"))
        self.state.update(watch=ranked, cycle_running=False,
                          last_cycle={"time": time.time(), "coins": len(watch), "plans": sum(bool(w["plans"]) for w in watch),
                                      "fired": fired})
        self.save_state()
        log(f"Cycle done: {len(watch)} coins read, {sum(bool(w['plans']) for w in watch)} with lines, {fired} fired")

    # ---- entering ----------------------------------------------------------------------------

    def leverage_for(self, symbol: str, stop_frac: float) -> int:
        if self._brackets is None:
            self._brackets = {b["symbol"]: b["brackets"] for b in self.client.leverage_brackets()}
        first = (self._brackets.get(symbol) or [{"initialLeverage": 5, "maintMarginRatio": 0.02}])[0]
        mmr = float(first["maintMarginRatio"])
        for lev in range(min(self.s.max_leverage, int(first["initialLeverage"])), 0, -1):
            if 1 / lev - mmr >= stop_frac * 1.5:  # liquidation comfortably beyond the stop
                return lev
        return 1

    def fire(self, symbol: str, f: dict) -> bool:
        rules = self.rules(symbol)
        side = f["side"]
        long = side == "LONG"
        mark = float(self.client.mark_price(symbol))
        stop = f["stop"]
        risk_per_unit = (mark - stop) if long else (stop - mark)
        if risk_per_unit <= 0:
            log(f"{symbol}: price already beyond the stop, skipped")
            return False
        # target: the next level beyond entry that's worth it, else 3R in open air
        target, target_label = None, ""
        for level, label in f["targets"]:
            if (level - mark if long else mark - level) >= risk_per_unit * 0.3:
                target, target_label = level, label
                break
        if target is None:
            target, target_label = (mark + 3 * risk_per_unit) if long else (mark - 3 * risk_per_unit), "open air (3R)"
        rr = abs(target - mark) / risk_per_unit
        if rr < self.s.min_rr:
            log(f"{symbol}: {side} {f['kind']} trigger ({f['why']}), but target {price_text(target)} is only {rr:.1f}R: skipped")
            return False
        # funding: don't join a crowded side
        try:
            funding = float(self.market.premium_index(symbol).get("lastFundingRate", 0))
        except (BinanceAPIError, requests.RequestException, ValueError):
            funding = 0.0
        if (long and funding > 0.0005) or (not long and funding < -0.0005):
            log(f"{symbol}: {side} trigger skipped, funding {funding:+.3%} per 8h is crowded on that side")
            return False

        stop_frac = risk_per_unit / mark
        leverage = self.leverage_for(symbol, stop_frac)
        qty = rules.round_qty(dec(self.s.risk) / (dec(risk_per_unit) + dec(mark) * TAKER_FEE * 2))
        if qty < rules.min_qty or qty * dec(mark) < rules.min_notional:
            log(f"{symbol}: position too small for Binance's minimum order, skipped")
            return False
        _, available = bot.wallet(self.client)
        if float(qty) * mark / leverage > available * 0.95:
            log(f"{symbol}: not enough free margin, skipped")
            return False
        bot.prepare_account(self.client, symbol, leverage)
        bot.cancel_symbol_orders(self.client, symbol)
        self.client.new_order(symbol=symbol, side="BUY" if long else "SELL", type="MARKET", quantity=fmt(qty),
                              newOrderRespType="RESULT")
        pos = bot.open_position(self.client, symbol)
        if pos is None:
            log(f"{symbol}: entry did not open a position")
            return False
        entry = float(pos["entryPrice"])
        qty = abs(dec(pos["positionAmt"]))
        sl, tp = rules.round_price(stop), rules.round_price(target)
        try:
            sl_id = self.place(symbol, "STOP_MARKET", sl, long)
            tp_id = self.place(symbol, "TAKE_PROFIT_MARKET", tp, long)
        except BinanceAPIError as err:
            log(f"{symbol}: could not place stop/target ({err.msg}); closing")
            self.market_close(symbol)
            return False
        grade = "A+" if len(f["bonuses"]) >= 2 else "A" if f["bonuses"] else "B"
        risk = float(qty) * abs(entry - float(sl)) + entry * float(qty) * float(TAKER_FEE) * 2
        self.state["positions"][symbol] = {
            "side": side, "kind": f["kind"], "grade": grade, "entry": entry, "qty": fmt(qty), "sl": float(sl),
            "tp": float(tp), "initial_sl": float(sl), "risk_usdt": risk, "rr": rr, "leverage": leverage,
            "why": f["why"], "bonuses": f["bonuses"], "target_label": target_label,
            "opened_at": int(time.time() * 1000), "sl_id": sl_id, "tp_id": tp_id, "partial": False,
        }
        self.save_state()
        journal.log(self.cfg.journal_path, "OPEN", env=self.cfg.env, symbol=symbol, side=side, qty=fmt(qty),
                    price=f"{entry:.8g}", stop=fmt(sl), take_profit=fmt(tp), leverage=leverage, risk_usdt=f"{risk:.2f}",
                    note=f"{NOTE} {grade} {f['kind']}: {f['why']}"[:180])
        log(f"{symbol}: FIRED {side} ({grade} {f['kind']}) {fmt(qty)} @ {price_text(entry)} {leverage}x | stop {fmt(sl)} "
            f"(-{risk:.2f}) | target {fmt(tp)} ({target_label}, {rr:.1f}R) | {f['why']}"
            + (f" | bonus: {', '.join(f['bonuses'])}" if f["bonuses"] else ""))
        return True

    def place(self, symbol: str, kind: str, price: Decimal, long: bool) -> int | None:
        order = self.client.new_algo_order(symbol=symbol, side="SELL" if long else "BUY", type=kind, triggerPrice=fmt(price),
                                           closePosition=True,
                                           workingType="MARK_PRICE" if kind == "STOP_MARKET" else "CONTRACT_PRICE")
        return order.get("algoId")

    def market_close(self, symbol: str, qty: Decimal | None = None) -> None:
        live = bot.open_position(self.client, symbol)
        if not live:
            return
        amount = float(live["positionAmt"])
        quantity = fmt(qty) if qty is not None else live["positionAmt"].lstrip("-")
        self.client.new_order(symbol=symbol, side="SELL" if amount > 0 else "BUY", type="MARKET", quantity=quantity,
                              reduceOnly=True, newOrderRespType="RESULT")

    # ---- managing trades ------------------------------------------------------------------------

    def realized(self, symbol: str, since_ms: int, side: str) -> float | None:
        rows = self.client.income(symbol, start_time=since_ms)
        if not any(r["incomeType"] == "REALIZED_PNL" for r in rows):
            closing = "SELL" if side == "LONG" else "BUY"
            if not any(t["side"] == closing for t in self.client.user_trades(symbol, start_time=since_ms)):
                return None
        return sum(float(r["income"]) for r in rows if r["incomeType"] in ("REALIZED_PNL", "COMMISSION", "FUNDING_FEE"))

    def housekeeping(self) -> None:
        self.state["heartbeat"] = time.time()
        tracked = self.state["positions"]
        if tracked:
            open_now = self.positions()
            algo = self.client.open_algo_orders()
            for symbol, pos in list(tracked.items()):
                long = pos["side"] == "LONG"
                live = open_now.get(symbol)
                if not live:
                    bot.cancel_symbol_orders(self.client, symbol)
                    pnl = self.realized(symbol, pos["opened_at"], pos["side"])
                    if pnl is None and time.time() * 1000 - pos["opened_at"] < 86_400_000:
                        continue
                    pnl = pnl or 0.0
                    mark = float(self.client.mark_price(symbol))
                    outcome = pos.get("closing") or (
                        "target" if abs(mark - pos["tp"]) < abs(mark - pos["sl"]) else
                        "break-even" if pos.get("partial") else "stop")
                    journal.log(self.cfg.journal_path, "CLOSE", env=self.cfg.env, symbol=symbol, side=pos["side"],
                                qty=pos["qty"], pnl_usdt=f"{pnl:.2f}", note=f"{NOTE} {pos['grade']} {outcome}")
                    log(f"{symbol}: {pos['side']} CLOSED ({outcome}) | net {pnl:+.2f} USDT after fees")
                    tracked.pop(symbol)
                    continue
                mark = float(live["markPrice"])
                one_r = abs(pos["entry"] - pos["initial_sl"])
                # +1R: take half off and move the stop to break-even
                if not pos["partial"] and ((mark - pos["entry"]) if long else (pos["entry"] - mark)) >= one_r:
                    self.take_half(symbol, pos, live)
                    continue
                if time.time() * 1000 - pos["opened_at"] > self.s.max_hold * 3600_000 and not pos.get("closing"):
                    log(f"{symbol}: held {self.s.max_hold:g} h without reaching stop or target, closing")
                    pos["closing"] = "time exit"
                    bot.cancel_symbol_orders(self.client, symbol)
                    self.market_close(symbol)
                    continue
                kinds = {o.get("orderType") for o in algo if o["symbol"] == symbol}
                for kind, price in (("STOP_MARKET", pos["sl"]), ("TAKE_PROFIT_MARKET", pos["tp"])):
                    if kind not in kinds:
                        log(f"{symbol}: {kind} missing, re-placing at {price_text(price)}")
                        try:
                            self.place(symbol, kind, self.rules(symbol).round_price(price), long)
                        except BinanceAPIError as err:
                            log(f"{symbol}: re-place failed ({err.msg}); closing")
                            pos["closing"] = "protection failed"
                            bot.cancel_symbol_orders(self.client, symbol)
                            self.market_close(symbol)
                            break
        self.save_state()

    def take_half(self, symbol: str, pos: dict, live: dict) -> None:
        rules = self.rules(symbol)
        long = pos["side"] == "LONG"
        half = rules.round_qty(abs(dec(live["positionAmt"])) / 2)
        entry = pos["entry"]
        be = rules.round_price(entry * (1 + 0.0012) if long else entry * (1 - 0.0012))  # covers the fees
        try:
            if half >= rules.min_qty and half * dec(entry) >= rules.min_notional:
                self.market_close(symbol, half)
                pos["qty"] = fmt(abs(dec(live["positionAmt"])) - half)
            if pos.get("sl_id"):
                try:
                    self.client.cancel_algo_order(pos["sl_id"])
                except BinanceAPIError:
                    pass
            pos["sl_id"] = self.place(symbol, "STOP_MARKET", be, long)
            pos["sl"], pos["partial"] = float(be), True
            log(f"{symbol}: +1R reached: took half off, stop moved to break-even {fmt(be)}")
        except BinanceAPIError as err:
            log(f"{symbol}: +1R management failed ({err.msg}); will retry")
        self.save_state()

    def close_by_hand(self, symbols: list[str] | str) -> None:
        chosen = list(self.state["positions"]) if symbols == "all" else [s for s in symbols if s in self.state["positions"]]
        log(f"Closing by hand: {', '.join(chosen) or 'nothing to close'}")
        for symbol in chosen:
            self.state["positions"][symbol]["closing"] = "manual"
            try:
                bot.cancel_symbol_orders(self.client, symbol)
                self.market_close(symbol)
            except BinanceAPIError as err:
                log(f"{symbol}: close failed ({err.msg}); will retry")
                self.state["positions"][symbol].pop("closing", None)
        self.save_state()
        time.sleep(1)
        self.housekeeping()

    # ---- loop ---------------------------------------------------------------------------------------

    def run(self) -> None:
        log(f"Sniper bot STARTED on DEMO: plans every 15 min on the top {self.s.max_coins} coins | trend + level + "
            f"closed trigger candle | lose {self.s.risk:g} USDT at the stop, target >= {self.s.min_rr:g}R, "
            f"half off at +1R, up to {self.s.max_leverage}x")
        next_cycle, next_housekeeping = 0.0, 0.0
        while True:
            try:
                to_close = close_requested()
                if to_close:
                    self.close_by_hand(to_close)
                if time.time() >= next_cycle:
                    now = time.time()
                    next_cycle = now - now % CYCLE + CYCLE + CYCLE_DELAY
                    self.state["next_cycle"] = next_cycle
                    self.housekeeping()
                    self.cycle(trade=load_control()["trading"])
                    next_housekeeping = time.time() + HOUSEKEEPING_SECONDS
                elif time.time() >= next_housekeeping:
                    self.state["trading"] = load_control()["trading"]
                    self.housekeeping()
                    next_housekeeping = time.time() + HOUSEKEEPING_SECONDS
            except (BinanceAPIError, requests.RequestException, ValueError) as err:
                log(f"Error: {err}. Will retry.")
                self.state["cycle_running"] = False
                next_housekeeping = time.time() + HOUSEKEEPING_SECONDS
            time.sleep(LOOP_SECONDS)

    def show_plans(self) -> None:
        self.cycle(trade=False)
        for w in self.state["watch"]:
            print(f"\n{w['symbol']:<14} {price_text(w['price']):>12}  {w['context']}")
            for p in w["plans"]:
                print(f"    -> {p['text']}  [{p['label']}{', Fibonacci' if p['fib'] else ''}]")
            if w["skip"]:
                print(f"    (no lines: {w['skip']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sniper bot: trend + key level + trigger candle (demo only)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="plan every 15 minutes and trade the triggers")
    sub.add_parser("plan", help="print every coin's context and lines now (no trades)")
    args = parser.parse_args()
    sniper = SniperBot(load_config())
    try:
        if args.command == "run":
            sniper.run()
        else:
            sniper.show_plans()
    except KeyboardInterrupt:
        log("Stopped. Open trades keep their stop and target on Binance; restart to manage +1R and time exits.")
    except Exception:
        log("Unexpected error:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()

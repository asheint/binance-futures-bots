"""Binance USDⓈ-M Futures practice bot. Runs on the DEMO (fake money) account by default.

  python bot.py plan BTCUSDT --stop 59400 --balance 1000   # calculator only, no keys needed
  python bot.py status                                     # balance, positions, SL/TP orders
  python bot.py trade BTCUSDT --stop 59400                 # sized entry + stop-loss + take-profit
  python bot.py close BTCUSDT                              # close position, cancel its orders
  python bot.py history --days 7                           # realized PnL, fees, funding
  python bot.py run BTCUSDT --interval 15m                 # automatic EMA-crossover strategy
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict

import requests

import journal
import strategy
from client import BinanceAPIError, FuturesClient
from config import Config, load_config
from risk import SymbolRules, TradePlan, dec, fmt, plan_trade

INTERVALS = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"]


# ---- helpers ----------------------------------------------------------------

def make_client(cfg: Config, signed: bool = True) -> FuturesClient:
    if signed and not (cfg.api_key and cfg.api_secret):
        sys.exit("Missing BINANCE_API_KEY / BINANCE_API_SECRET in .env (see README.md).")
    client = FuturesClient(cfg.api_key, cfg.api_secret, cfg.base_url)
    client.sync_time()
    return client


def wallet(client: FuturesClient) -> tuple[float, float]:
    for asset in client.balance():
        if asset["asset"] == "USDT":
            return float(asset["balance"]), float(asset["availableBalance"])
    return 0.0, 0.0


def open_position(client: FuturesClient, symbol: str) -> dict | None:
    for pos in client.position_risk(symbol):
        if float(pos["positionAmt"]) != 0:
            return pos
    return None


def resolve_limits(cfg: Config, args: argparse.Namespace) -> tuple[float, float, int]:
    risk = args.risk if args.risk is not None else cfg.risk_pct
    rr = args.rr if args.rr is not None else cfg.rr
    leverage = args.leverage if args.leverage is not None else cfg.leverage
    if not 0 < risk <= cfg.max_risk_pct:
        sys.exit(f"Risk must be between 0 and {cfg.max_risk_pct}% (MAX_RISK_PCT in .env).")
    if not 1 <= leverage <= cfg.max_leverage:
        sys.exit(f"Leverage must be between 1 and {cfg.max_leverage}x (MAX_LEVERAGE in .env).")
    if rr <= 0:
        sys.exit("Reward/risk must be above 0.")
    return risk, rr, leverage


def print_plan(plan: TradePlan, env: str, balance: float) -> None:
    stop_pct = float(abs(plan.entry - plan.stop) / plan.entry * 100)
    print(f"\n=== {plan.symbol} {plan.side} plan ({env.upper()}) ===")
    print(f"Entry (~mark price) {fmt(plan.entry)}")
    print(f"Stop-loss           {fmt(plan.stop)}  ({stop_pct:.2f}% away)")
    print(f"Take-profit         {fmt(plan.take_profit)}  ({plan.rr:g}R)")
    print(f"Quantity            {fmt(plan.qty)}")
    print(f"Position value      {plan.notional:.2f} USDT")
    print(f"Margin used         {plan.margin:.2f} USDT at {plan.leverage}x isolated")
    print(f"Max loss if SL hit  ~{plan.risk_usdt:.2f} USDT incl. fees ({float(plan.risk_usdt) / balance * 100:.2f}% of balance)")
    print(f"Profit if TP hit    ~{plan.reward_usdt:.2f} USDT after fees")
    print(f"Approx liquidation  {plan.approx_liq_price:.2f}  (stop triggers well before this)")
    for warning in plan.warnings:
        print(f"WARNING: {warning}")


def cancel_symbol_orders(client: FuturesClient, symbol: str) -> None:
    for cancel in (client.cancel_all_orders, client.cancel_all_algo_orders):
        try:
            cancel(symbol)
        except BinanceAPIError:
            pass  # nothing to cancel


def prepare_account(client: FuturesClient, symbol: str, leverage: int) -> None:
    if client.is_hedge_mode():
        try:
            client.set_hedge_mode(False)
        except BinanceAPIError as err:
            sys.exit(f"Account is in Hedge mode and couldn't switch to One-way ({err.msg}). Change it in Futures settings.")
    try:
        client.set_margin_type(symbol, "ISOLATED")
    except BinanceAPIError as err:
        if err.code != -4046:  # -4046 = already isolated
            raise
    client.set_leverage(symbol, leverage)


# ---- trading actions ---------------------------------------------------------

def open_trade(cfg: Config, client: FuturesClient, symbol: str, stop: float, risk: float, rr: float,
               leverage: int, assume_yes: bool, expected_side: str | None = None, note: str = "manual") -> bool:
    if open_position(client, symbol):
        print(f"You already have an open {symbol} position. Close it first: python bot.py close {symbol}")
        return False

    rules = SymbolRules.from_symbol_info(client.symbol_info(symbol))
    balance, available = wallet(client)
    plan = plan_trade(rules, balance, available, risk, client.mark_price(symbol), stop, rr, leverage)
    if expected_side and plan.side != expected_side:
        print(f"Skipped: price already moved past the stop (wanted {expected_side}, plan says {plan.side}).")
        return False

    print_plan(plan, cfg.env, balance)
    if not assume_yes and input("\nPlace this trade? [y/N] ").strip().lower() != "y":
        print("Cancelled.")
        return False

    prepare_account(client, symbol, leverage)
    cancel_symbol_orders(client, symbol)  # clear a leftover TP/SL from an earlier trade

    entry_side, exit_side = ("BUY", "SELL") if plan.side == "LONG" else ("SELL", "BUY")
    client.new_order(symbol=symbol, side=entry_side, type="MARKET", quantity=fmt(plan.qty), newOrderRespType="RESULT")

    pos = open_position(client, symbol)
    if pos is None:
        print("The entry order did not open a position. Check the order history on Binance.")
        return False
    fill = rules.round_price(pos["entryPrice"])
    take_profit = rules.round_price(fill + dec(rr) * (fill - plan.stop))

    try:
        client.new_algo_order(symbol=symbol, side=exit_side, type="STOP_MARKET", triggerPrice=fmt(plan.stop),
                              closePosition=True, workingType="MARK_PRICE", priceProtect=True)
        client.new_algo_order(symbol=symbol, side=exit_side, type="TAKE_PROFIT_MARKET", triggerPrice=fmt(take_profit),
                              closePosition=True, workingType="MARK_PRICE")
    except BinanceAPIError as err:
        print(f"\n!! Could not place stop-loss/take-profit: {err}")
        print("!! Closing the position now so it is never left without a stop.")
        close_trade(cfg, client, symbol, reason="protection-failed")
        return False

    journal.log(cfg.journal_path, "OPEN", env=cfg.env, symbol=symbol, side=plan.side, qty=fmt(plan.qty),
                price=fmt(fill), stop=fmt(plan.stop), take_profit=fmt(take_profit), leverage=leverage,
                risk_usdt=f"{plan.risk_usdt:.2f}", note=note)
    print(f"\nOpened {plan.side} {fmt(plan.qty)} {symbol} @ {fmt(fill)} | SL {fmt(plan.stop)} | TP {fmt(take_profit)}")
    return True


def close_trade(cfg: Config, client: FuturesClient, symbol: str, reason: str = "manual") -> None:
    cancel_symbol_orders(client, symbol)
    pos = open_position(client, symbol)
    if pos is None:
        print(f"No open {symbol} position (open SL/TP orders were cancelled).")
        return

    amount = dec(pos["positionAmt"])
    entry = dec(pos["entryPrice"])
    order = client.new_order(symbol=symbol, side="SELL" if amount > 0 else "BUY", type="MARKET",
                             quantity=fmt(abs(amount)), reduceOnly=True, newOrderRespType="RESULT")
    rules = SymbolRules.from_symbol_info(client.symbol_info(symbol))
    exit_price = rules.round_price(client.filled_avg_price(order) or client.mark_price(symbol))
    entry = rules.round_price(entry)
    pnl = (exit_price - entry) * amount

    journal.log(cfg.journal_path, "CLOSE", env=cfg.env, symbol=symbol, side="LONG" if amount > 0 else "SHORT",
                qty=fmt(abs(amount)), price=fmt(exit_price), pnl_usdt=f"{pnl:.2f}", note=reason)
    print(f"Closed {symbol} @ {fmt(exit_price)} | PnL before fees ~{pnl:.2f} USDT")


# ---- commands ------------------------------------------------------------------

def cmd_plan(cfg: Config, args: argparse.Namespace) -> None:
    risk, rr, leverage = resolve_limits(cfg, args)
    client = make_client(cfg, signed=args.balance is None)
    rules = SymbolRules.from_symbol_info(client.symbol_info(args.symbol))
    entry = args.entry if args.entry is not None else client.mark_price(args.symbol)
    balance, available = (args.balance, args.balance) if args.balance is not None else wallet(client)
    print_plan(plan_trade(rules, balance, available, risk, entry, args.stop, rr, leverage), cfg.env, balance)


def cmd_trade(cfg: Config, args: argparse.Namespace) -> None:
    risk, rr, leverage = resolve_limits(cfg, args)
    open_trade(cfg, make_client(cfg), args.symbol, args.stop, risk, rr, leverage, assume_yes=args.yes)


def cmd_close(cfg: Config, args: argparse.Namespace) -> None:
    close_trade(cfg, make_client(cfg), args.symbol)


def cmd_status(cfg: Config, args: argparse.Namespace) -> None:
    client = make_client(cfg)
    balance, available = wallet(client)
    print(f"Account ({cfg.env.upper()}): balance {balance:.2f} USDT | available {available:.2f} USDT\n")

    positions = [p for p in client.position_risk() if float(p["positionAmt"]) != 0]
    if not positions:
        print("No open positions.")
    for p in positions:
        amount = float(p["positionAmt"])
        print(f"{p['symbol']:<10} {'LONG' if amount > 0 else 'SHORT':<5} qty {abs(amount):g}  entry {float(p['entryPrice']):g}  "
              f"mark {float(p['markPrice']):g}  uPnL {float(p['unRealizedProfit']):+.2f}  "
              f"liq {float(p['liquidationPrice']):g}  {p['leverage']}x {p['marginType']}")

    try:
        algo_orders = client.open_algo_orders()
    except BinanceAPIError as err:
        print(f"\n(could not load SL/TP orders: {err.msg})")
        return
    if algo_orders:
        print("\nOpen stop-loss / take-profit orders:")
    for o in algo_orders:
        print(f"  {o['symbol']:<10} {o.get('orderType', o.get('type', '?')):<20} {o['side']:<4} trigger {o.get('triggerPrice')}")


def cmd_history(cfg: Config, args: argparse.Namespace) -> None:
    client = make_client(cfg)
    start = client.now_ms() - args.days * 86_400_000
    rows = client.income(symbol=args.symbol, start_time=start)

    totals: dict[str, float] = defaultdict(float)
    pnls = []
    for row in rows:
        totals[row["incomeType"]] += float(row["income"])
        if row["incomeType"] == "REALIZED_PNL":
            pnls.append(float(row["income"]))

    wins = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    net = totals["REALIZED_PNL"] + totals["COMMISSION"] + totals["FUNDING_FEE"]
    print(f"Last {args.days} days ({cfg.env.upper()}{', ' + args.symbol if args.symbol else ''})")
    print(f"Realized PnL  {totals['REALIZED_PNL']:+.2f} USDT")
    print(f"Fees          {totals['COMMISSION']:+.2f} USDT")
    print(f"Funding       {totals['FUNDING_FEE']:+.2f} USDT")
    print(f"NET           {net:+.2f} USDT")
    if pnls:
        print(f"Winning fills {wins}, losing fills {losses}, win rate {wins / max(wins + losses, 1) * 100:.0f}%")


def cmd_run(cfg: Config, args: argparse.Namespace) -> None:
    risk, rr, leverage = resolve_limits(cfg, args)
    if args.fast >= args.slow:
        sys.exit("--fast must be smaller than --slow")
    client = make_client(cfg)
    symbol = args.symbol
    print(f"EMA {args.fast}/{args.slow} crossover on {symbol} {args.interval} | risk {risk}% | {leverage}x | "
          f"{rr}R | {cfg.env.upper()}")
    print("Ctrl+C stops the bot. Open positions keep their SL/TP on Binance.\n")

    last_candle = None
    try:
        while True:
            try:
                candles = client.klines(symbol, args.interval, limit=max(args.slow * 3, 100))
                closed = candles[:-1]  # the last candle is still forming
                if closed[-1][6] != last_candle:
                    last_candle = closed[-1][6]
                    closes = [float(c[4]) for c in closed]
                    signal = strategy.crossover_signal(closes, args.fast, args.slow)
                    pos = open_position(client, symbol)
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] close {closes[-1]:g} | signal {signal or '-'} | "
                          f"position {'open' if pos else 'none'}")
                    if signal and pos is None:
                        highs = [float(c[2]) for c in closed]
                        lows = [float(c[3]) for c in closed]
                        distance = args.atr_mult * strategy.atr(highs, lows, closes)
                        stop = closes[-1] - distance if signal == "LONG" else closes[-1] + distance
                        open_trade(cfg, client, symbol, stop, risk, rr, leverage, assume_yes=True,
                                   expected_side=signal, note=f"ema{args.fast}/{args.slow}")
                wait = (candles[-1][6] - client.now_ms()) / 1000 + 3
                time.sleep(max(wait, 5))
            except (BinanceAPIError, requests.RequestException, ValueError) as err:
                print(f"Error: {err}. Retrying in 30s.")
                time.sleep(30)
    except KeyboardInterrupt:
        print("\nBot stopped.")


# ---- CLI -------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Binance futures practice bot (demo account by default)")
    sub = parser.add_subparsers(dest="command", required=True)

    def risk_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--risk", type=float, help="percent of balance to risk (default RISK_PCT)")
        p.add_argument("--rr", type=float, help="take-profit as a multiple of risk (default REWARD_RISK)")
        p.add_argument("--leverage", type=int, help="leverage (default LEVERAGE)")

    p = sub.add_parser("plan", help="calculate size/SL/TP without trading")
    p.add_argument("symbol", type=str.upper)
    p.add_argument("--stop", type=float, required=True, help="stop-loss price (below entry = long, above = short)")
    p.add_argument("--entry", type=float, help="entry price (default: current mark price)")
    p.add_argument("--balance", type=float, help="pretend balance in USDT (no API keys needed)")
    risk_args(p)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("trade", help="open a sized position with stop-loss and take-profit")
    p.add_argument("symbol", type=str.upper)
    p.add_argument("--stop", type=float, required=True, help="stop-loss price (below price = long, above = short)")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    risk_args(p)
    p.set_defaults(func=cmd_trade)

    p = sub.add_parser("close", help="market-close a position and cancel its orders")
    p.add_argument("symbol", type=str.upper)
    p.set_defaults(func=cmd_close)

    p = sub.add_parser("status", help="balance, positions and SL/TP orders")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("history", help="realized PnL, fees and funding")
    p.add_argument("--symbol", type=str.upper)
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("run", help="run the EMA crossover strategy automatically")
    p.add_argument("symbol", type=str.upper)
    p.add_argument("--interval", choices=INTERVALS, default="15m")
    p.add_argument("--fast", type=int, default=9)
    p.add_argument("--slow", type=int, default=21)
    p.add_argument("--atr-mult", type=float, default=1.5, help="stop distance = ATR x this")
    risk_args(p)
    p.set_defaults(func=cmd_run)

    args = parser.parse_args()
    cfg = load_config()
    try:
        args.func(cfg, args)
    except ValueError as err:
        sys.exit(f"Can't do that: {err}")
    except BinanceAPIError as err:
        sys.exit(f"Binance error: {err}")
    except requests.RequestException as err:
        sys.exit(f"Network error: {err}")


if __name__ == "__main__":
    main()

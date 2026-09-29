"""Position sizing: decide HOW MUCH to trade so a stop-loss only costs a fixed % of the account."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

TAKER_FEE = Decimal("0.0005")         # 0.05% per side (default, non-VIP)
MAINT_MARGIN_RATE = Decimal("0.004")  # rough value for small BTC/ETH positions; real value depends on tier


def dec(value: float | str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def fmt(value: Decimal) -> str:
    return format(value.normalize(), "f")


@dataclass(frozen=True)
class SymbolRules:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal

    @classmethod
    def from_symbol_info(cls, info: dict) -> "SymbolRules":
        filters = {f["filterType"]: f for f in info["filters"]}
        lot = filters.get("MARKET_LOT_SIZE")
        if not lot or dec(lot["stepSize"]) == 0:
            lot = filters["LOT_SIZE"]
        return cls(
            symbol=info["symbol"],
            tick_size=dec(filters["PRICE_FILTER"]["tickSize"]),
            step_size=dec(lot["stepSize"]),
            min_qty=dec(lot["minQty"]),
            max_qty=dec(lot["maxQty"]),
            min_notional=dec(filters.get("MIN_NOTIONAL", {}).get("notional", "0")),
        )

    def round_qty(self, qty: float | Decimal) -> Decimal:
        return (dec(qty) / self.step_size).to_integral_value(ROUND_DOWN) * self.step_size

    def round_price(self, price: float | Decimal) -> Decimal:
        return (dec(price) / self.tick_size).to_integral_value(ROUND_HALF_UP) * self.tick_size


@dataclass
class TradePlan:
    symbol: str
    side: str
    entry: Decimal
    stop: Decimal
    take_profit: Decimal
    rr: float
    qty: Decimal
    notional: Decimal
    margin: Decimal
    leverage: int
    risk_usdt: Decimal
    reward_usdt: Decimal
    fees_usdt: Decimal
    approx_liq_price: Decimal
    warnings: list[str] = field(default_factory=list)


def plan_trade(
    rules: SymbolRules,
    balance: float,
    available: float,
    risk_pct: float,
    entry: float,
    stop: float,
    rr: float,
    leverage: int,
) -> TradePlan:
    entry_d = rules.round_price(entry)
    stop_d = rules.round_price(stop)
    if stop_d == entry_d:
        raise ValueError("stop-loss can't equal the entry price")
    side = "LONG" if stop_d < entry_d else "SHORT"
    distance = abs(entry_d - stop_d)

    risk_budget = dec(balance) * dec(risk_pct) / 100
    qty = rules.round_qty(risk_budget / distance)
    if qty < rules.min_qty:
        raise ValueError(
            f"size {fmt(qty)} is below the minimum {fmt(rules.min_qty)} for {rules.symbol}. "
            "Use a closer stop, a higher risk %, or a bigger balance."
        )
    if qty > rules.max_qty:
        raise ValueError(f"size {fmt(qty)} is above the max {fmt(rules.max_qty)}; your stop is far too tight")

    notional = qty * entry_d
    if notional < rules.min_notional:
        raise ValueError(
            f"position value {notional:.2f} USDT is below Binance's minimum of {fmt(rules.min_notional)} USDT "
            f"for {rules.symbol}. Use a closer stop or a higher risk %."
        )

    lev = dec(leverage)
    margin = notional / lev
    if margin > dec(available):
        raise ValueError(
            f"needs {margin:.2f} USDT margin but only {available:.2f} is available. "
            "Widen the stop (smaller position) or raise leverage a little."
        )

    # Isolated-margin liquidation estimate. The stop MUST trigger before this.
    if side == "LONG":
        liq = entry_d * (1 - 1 / lev + MAINT_MARGIN_RATE)
        stop_before_liq = stop_d > liq
    else:
        liq = entry_d * (1 + 1 / lev - MAINT_MARGIN_RATE)
        stop_before_liq = stop_d < liq
    if not stop_before_liq:
        raise ValueError(f"stop-loss {fmt(stop_d)} is beyond the liquidation price (~{liq:.2f}). Lower the leverage.")

    take_profit = rules.round_price(entry_d + dec(rr) * (entry_d - stop_d))
    if take_profit <= 0:
        raise ValueError("take-profit would be below zero; use a smaller reward/risk")

    fees = notional * TAKER_FEE * 2
    plan = TradePlan(
        symbol=rules.symbol,
        side=side,
        entry=entry_d,
        stop=stop_d,
        take_profit=take_profit,
        rr=rr,
        qty=qty,
        notional=notional,
        margin=margin,
        leverage=leverage,
        risk_usdt=qty * distance + fees,
        reward_usdt=qty * abs(take_profit - entry_d) - fees,
        fees_usdt=fees,
        approx_liq_price=liq,
    )
    if fees > risk_budget * Decimal("0.3"):
        plan.warnings.append("Stop is very tight: fees are over 30% of your risk. Consider a wider stop.")
    return plan

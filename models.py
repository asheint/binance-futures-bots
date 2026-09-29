"""Shared data types."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candle:
    time: int  # open time, unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float


def candles_from_klines(rows: list[list], drop_last: bool = True) -> list[Candle]:
    """Converts Binance kline rows. drop_last removes the still-forming candle so analysis only uses closed ones."""
    rows = rows[:-1] if drop_last else rows
    return [Candle(int(r[0]) // 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in rows]


def price_text(price: float) -> str:
    return f"{price:,.2f}" if price >= 1 else f"{price:.6g}"

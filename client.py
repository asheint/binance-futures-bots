"""Minimal signed REST client for Binance USDⓈ-M Futures.

Docs: https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import requests


class BinanceAPIError(Exception):
    def __init__(self, status: int, code: int | None, msg: str):
        super().__init__(f"HTTP {status}, code {code}: {msg}")
        self.status = status
        self.code = code
        self.msg = msg


class FuturesClient:
    def __init__(self, api_key: str, api_secret: str, base_url: str, recv_window: int = 5000, timeout: int = 10):
        self.api_secret = api_secret.encode()
        self.has_keys = bool(api_key and api_secret)
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.timeout = timeout
        self.time_offset_ms = 0
        self.session = requests.Session()
        if api_key:
            self.session.headers["X-MBX-APIKEY"] = api_key
        self._symbols: dict[str, dict] | None = None

    # ---- plumbing -------------------------------------------------------

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None, signed: bool = False,
                 resync: bool = True) -> Any:
        clean: dict[str, Any] = {}
        for key, value in (params or {}).items():
            if value is None:
                continue
            clean[key] = ("true" if value else "false") if isinstance(value, bool) else value

        if signed:
            if not self.has_keys:
                raise RuntimeError("This request needs BINANCE_API_KEY and BINANCE_API_SECRET in .env")
            clean["recvWindow"] = self.recv_window
            clean["timestamp"] = self.now_ms()
            query = urlencode(clean)
            signature = hmac.new(self.api_secret, query.encode(), hashlib.sha256).hexdigest()
            query = f"{query}&signature={signature}"
        else:
            query = urlencode(clean)

        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        resp = self.session.request(method, url, timeout=self.timeout)
        try:
            data = resp.json()
        except ValueError:
            data = {"msg": resp.text}

        if resp.status_code >= 400 or (isinstance(data, dict) and isinstance(data.get("code"), int) and data["code"] < 0):
            code = data.get("code") if isinstance(data, dict) else None
            msg = data.get("msg", resp.text) if isinstance(data, dict) else resp.text
            if signed and code == -1021 and resync:
                # the PC clock drifted since the last sync; Binance rejected the request unprocessed, so retrying is safe
                self.sync_time()
                return self._request(method, path, params, signed, resync=False)
            raise BinanceAPIError(resp.status_code, code, msg)
        return data

    def now_ms(self) -> int:
        return int(time.time() * 1000) + self.time_offset_ms

    def sync_time(self) -> None:
        server = self._request("GET", "/fapi/v1/time")["serverTime"]
        self.time_offset_ms = server - int(time.time() * 1000)

    # ---- market data (no keys needed) ------------------------------------

    def symbol_info(self, symbol: str) -> dict:
        if self._symbols is None:
            info = self._request("GET", "/fapi/v1/exchangeInfo")
            self._symbols = {s["symbol"]: s for s in info["symbols"]}
        if symbol not in self._symbols:
            raise ValueError(f"Unknown futures symbol '{symbol}'")
        return self._symbols[symbol]

    def mark_price(self, symbol: str) -> float:
        return float(self._request("GET", "/fapi/v1/premiumIndex", {"symbol": symbol})["markPrice"])

    def ticker_24h(self, symbol: str | None = None) -> list[dict] | dict:
        return self._request("GET", "/fapi/v1/ticker/24hr", {"symbol": symbol})

    def premium_index(self, symbol: str) -> dict:
        """Mark price, index price, last funding rate and next funding time."""
        return self._request("GET", "/fapi/v1/premiumIndex", {"symbol": symbol})

    def open_interest(self, symbol: str) -> float:
        return float(self._request("GET", "/fapi/v1/openInterest", {"symbol": symbol})["openInterest"])

    def klines(self, symbol: str, interval: str, limit: int = 200, start_time: int | None = None) -> list[list]:
        params = {"symbol": symbol, "interval": interval, "limit": limit, "startTime": start_time}
        return self._request("GET", "/fapi/v1/klines", params)

    def funding_rates(self, symbol: str, start_time: int | None = None, limit: int = 1000) -> list[dict]:
        params = {"symbol": symbol, "startTime": start_time, "limit": limit}
        return self._request("GET", "/fapi/v1/fundingRate", params)

    # ---- account ----------------------------------------------------------

    def balance(self) -> list[dict]:
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def position_risk(self, symbol: str | None = None) -> list[dict]:
        return self._request("GET", "/fapi/v2/positionRisk", {"symbol": symbol}, signed=True)

    def is_hedge_mode(self) -> bool:
        return bool(self._request("GET", "/fapi/v1/positionSide/dual", signed=True)["dualSidePosition"])

    def set_hedge_mode(self, enabled: bool) -> None:
        self._request("POST", "/fapi/v1/positionSide/dual", {"dualSidePosition": enabled}, signed=True)

    def set_margin_type(self, symbol: str, margin_type: str) -> None:
        self._request("POST", "/fapi/v1/marginType", {"symbol": symbol, "marginType": margin_type}, signed=True)

    def set_leverage(self, symbol: str, leverage: int) -> None:
        self._request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}, signed=True)

    def user_trades(self, symbol: str, start_time: int | None = None, limit: int = 500) -> list[dict]:
        params = {"symbol": symbol, "startTime": start_time, "limit": limit}
        return self._request("GET", "/fapi/v1/userTrades", params, signed=True)

    def leverage_brackets(self) -> list[dict]:
        """Every symbol's leverage and margin brackets: max leverage and maintenance margin rate per position size."""
        return self._request("GET", "/fapi/v1/leverageBracket", signed=True)

    def income(self, symbol: str | None = None, start_time: int | None = None, limit: int = 1000) -> list[dict]:
        params = {"symbol": symbol, "startTime": start_time, "limit": limit}
        return self._request("GET", "/fapi/v1/income", params, signed=True)

    # ---- orders -----------------------------------------------------------

    def new_order(self, **params: Any) -> dict:
        """Plain orders: MARKET / LIMIT."""
        return self._request("POST", "/fapi/v1/order", params, signed=True)

    def get_order(self, symbol: str, order_id: int) -> dict:
        return self._request("GET", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id}, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> None:
        self._request("DELETE", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id}, signed=True)

    def filled_avg_price(self, order: dict, retries: int = 5) -> float:
        """Market order responses can arrive before the fill; poll until avgPrice is known (0 if never)."""
        for attempt in range(retries):
            price = float(order.get("avgPrice") or 0)
            if price > 0:
                return price
            time.sleep(0.3 * (attempt + 1))
            order = self.get_order(order["symbol"], order["orderId"])
        return float(order.get("avgPrice") or 0)

    def new_algo_order(self, **params: Any) -> dict:
        """Conditional orders (STOP_MARKET, TAKE_PROFIT_MARKET, ...). Required since 2025-12-09."""
        params.setdefault("algoType", "CONDITIONAL")
        return self._request("POST", "/fapi/v1/algoOrder", params, signed=True)

    def open_algo_orders(self, symbol: str | None = None) -> list[dict]:
        return self._request("GET", "/fapi/v1/openAlgoOrders", {"symbol": symbol}, signed=True)

    def cancel_algo_order(self, algo_id: int) -> None:
        self._request("DELETE", "/fapi/v1/algoOrder", {"algoId": algo_id}, signed=True)

    def cancel_all_orders(self, symbol: str) -> None:
        self._request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol}, signed=True)

    def cancel_all_algo_orders(self, symbol: str) -> None:
        self._request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": symbol}, signed=True)

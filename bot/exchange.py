"""Binance USDT-M futures client via ccxt (testnet by default)."""

from __future__ import annotations

from typing import Any

import ccxt

from bot.config import Settings


class ExchangeError(RuntimeError):
    """Wrap exchange / network failures with a short context."""


class BinanceFuturesExchange:
    """
    Thin wrapper over ccxt.binanceusdm.

    - Public market data works without API keys.
    - Private calls (balance / order) need credentials.
    - Sandbox (testnet) is ON whenever Settings.testnet is True.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        options: dict[str, Any] = {
            "defaultType": "swap",  # USDT-M perpetual
            "adjustForTimeDifference": True,
        }
        params: dict[str, Any] = {
            "enableRateLimit": True,
            "options": options,
        }
        if settings.has_credentials:
            params["apiKey"] = settings.api_key
            params["secret"] = settings.api_secret

        self._client = ccxt.binanceusdm(params)
        # Official sandbox switch for futures testnet.
        self._client.set_sandbox_mode(settings.testnet)

    @property
    def client(self) -> ccxt.binanceusdm:
        return self._client

    @property
    def mode_label(self) -> str:
        net = "TESTNET" if self.settings.testnet else "MAINNET"
        trade = "LIVE" if self.settings.live else "DRY-RUN"
        return f"{net}/{trade}"

    def load_markets(self) -> dict[str, Any]:
        try:
            return self._client.load_markets()
        except ccxt.BaseError as exc:
            raise ExchangeError(f"load_markets failed: {exc}") from exc

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 120,
    ) -> list[list[float]]:
        """Return OHLCV rows: [ts, open, high, low, close, volume]."""
        try:
            rows = self._client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except ccxt.BaseError as exc:
            raise ExchangeError(f"fetch_ohlcv({symbol},{timeframe}) failed: {exc}") from exc
        if not rows:
            raise ExchangeError(f"empty OHLCV for {symbol} {timeframe}")
        return rows

    def fetch_ticker_last(self, symbol: str) -> float:
        try:
            ticker = self._client.fetch_ticker(symbol)
            last = ticker.get("last")
            if last is None:
                raise ExchangeError(f"ticker missing last price for {symbol}")
            return float(last)
        except ccxt.BaseError as exc:
            raise ExchangeError(f"fetch_ticker({symbol}) failed: {exc}") from exc

    def fetch_balance_usdt(self) -> float:
        if not self.settings.has_credentials:
            raise ExchangeError("balance requires API credentials")
        try:
            bal = self._client.fetch_balance()
            usdt = bal.get("USDT") or {}
            free = usdt.get("free")
            if free is None:
                # Some responses nest under total/info; fall back carefully.
                free = bal.get("free", {}).get("USDT", 0)
            return float(free or 0)
        except ccxt.BaseError as exc:
            raise ExchangeError(f"fetch_balance failed: {exc}") from exc

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        *,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """
        Place a market order. Caller must gate with Settings.live.

        side: 'buy' | 'sell' (ccxt style).
        """
        if not self.settings.live:
            raise ExchangeError("refusing create_order: live=False (dry-run)")
        if not self.settings.has_credentials:
            raise ExchangeError("create_order requires API credentials")
        params: dict[str, Any] = {}
        if reduce_only:
            params["reduceOnly"] = True
        try:
            return self._client.create_order(
                symbol,
                type="market",
                side=side,
                amount=amount,
                params=params,
            )
        except ccxt.BaseError as exc:
            raise ExchangeError(f"create_order failed: {exc}") from exc

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        try:
            return float(self._client.amount_to_precision(symbol, amount))
        except Exception as exc:  # noqa: BLE001 — precision helpers vary by market
            raise ExchangeError(f"amount_to_precision failed: {exc}") from exc

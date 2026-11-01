"""One-shot / loop runner: klines → signal → dry-run or live order."""

from __future__ import annotations

import logging
import time
from typing import Callable

from bot.config import Settings
from bot.exchange import BinanceFuturesExchange, ExchangeError
from bot.risk import OrderIntent, RiskManager
from bot.strategy import Strategy, build_strategy

logger = logging.getLogger(__name__)


class BotRunner:
    def __init__(
        self,
        settings: Settings,
        exchange: BinanceFuturesExchange | None = None,
        strategy: Strategy | None = None,
        risk: RiskManager | None = None,
    ) -> None:
        self.settings = settings
        self.exchange = exchange or BinanceFuturesExchange(settings)
        self.strategy = strategy or build_strategy(settings.strategy)
        self.risk = risk or RiskManager(settings)

    def _resolve_equity(self) -> float:
        """
        Prefer real free USDT when credentials exist.

        Without keys (typical dry-run), invent equity so that
        risk_per_trade * equity ≈ MAX_POSITION_USDT — i.e. the printed
        notional lands near the configured cap, which is easier to read.
        """
        if self.settings.has_credentials:
            try:
                return self.exchange.fetch_balance_usdt()
            except ExchangeError as exc:
                logger.warning("balance unavailable (%s); falling back to max_position proxy", exc)
        risk = max(self.settings.risk_per_trade, 1e-9)
        return self.settings.max_position_usdt / risk

    def once(self) -> OrderIntent | None:
        symbol = self.settings.symbol
        timeframe = self.settings.timeframe
        logger.info(
            "tick mode=%s strategy=%s symbol=%s tf=%s",
            self.exchange.mode_label,
            getattr(self.strategy, "name", type(self.strategy).__name__),
            symbol,
            timeframe,
        )

        ohlcv = self.exchange.fetch_ohlcv(
            symbol,
            timeframe,
            limit=self.settings.candle_limit,
        )
        signal = self.strategy.evaluate(ohlcv)
        logger.info(
            "signal=%s price=%.4f reason=%s meta=%s",
            signal.side.value,
            signal.price,
            signal.reason,
            signal.meta,
        )

        equity = self._resolve_equity()
        intent = self.risk.build_intent(
            symbol=symbol,
            signal=signal,
            equity_usdt=equity,
            amount_precision_fn=self.exchange.amount_to_precision,
        )
        if intent is None:
            logger.info("no order intent (flat or zero size)")
            return None

        self._dispatch(intent)
        return intent

    def _dispatch(self, intent: OrderIntent) -> None:
        line = intent.summary()
        if not self.settings.live:
            logger.info("[DRY-RUN] would place: %s", line)
            print(f"[DRY-RUN] {line}")
            return

        if not self.settings.testnet:
            # Extra loud guard for mainnet live.
            logger.warning("MAINNET LIVE order: %s", line)
        else:
            logger.info("TESTNET LIVE order: %s", line)

        order = self.exchange.create_market_order(
            intent.symbol,
            intent.side.value,
            intent.amount,
            reduce_only=intent.reduce_only,
        )
        oid = order.get("id") or order.get("info", {}).get("orderId")
        print(f"[LIVE] placed order id={oid} | {line}")
        logger.info("order response keys=%s id=%s", list(order.keys()), oid)

    def loop(
        self,
        *,
        iterations: int | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        """
        Poll forever (or N times). KeyboardInterrupt exits cleanly.
        """
        n = 0
        try:
            while iterations is None or n < iterations:
                try:
                    self.once()
                except ExchangeError as exc:
                    logger.error("exchange error: %s", exc)
                except ValueError as exc:
                    logger.error("strategy/config error: %s", exc)
                n += 1
                if iterations is not None and n >= iterations:
                    break
                sleep_fn(self.settings.poll_interval_sec)
        except KeyboardInterrupt:
            logger.info("stopped by user")
            print("stopped.")

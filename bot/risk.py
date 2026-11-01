"""Position sizing / stop-loss placeholders. Not production risk mgmt."""

from __future__ import annotations

from dataclasses import dataclass

from bot.config import Settings
from bot.strategy import Side, Signal


@dataclass(frozen=True)
class OrderIntent:
    """What the bot *would* send to the exchange."""

    symbol: str
    side: Side
    amount: float
    notional_usdt: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    reason: str
    reduce_only: bool = False

    def summary(self) -> str:
        sl = f"{self.stop_loss:.4f}" if self.stop_loss is not None else "-"
        tp = f"{self.take_profit:.4f}" if self.take_profit is not None else "-"
        return (
            f"{self.side.value.upper()} {self.amount} {self.symbol} "
            f"~{self.notional_usdt:.2f} USDT @ {self.entry_price:.4f} "
            f"SL={sl} TP={tp} | {self.reason}"
        )


class RiskManager:
    """
    Skeleton risk layer.

    Current behaviour:
      - Cap notional by MAX_POSITION_USDT and RISK_PER_TRADE * equity.
      - Attach fixed-percentage SL/TP levels (not placed as exchange orders yet).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def size_from_equity(self, equity_usdt: float, price: float) -> float:
        if price <= 0:
            raise ValueError("price must be > 0")
        by_risk = equity_usdt * self.settings.risk_per_trade
        notional = min(by_risk, self.settings.max_position_usdt)
        # Soft floor so dry-run still prints a tiny intent when equity unknown.
        notional = max(notional, 0.0)
        if notional <= 0:
            return 0.0
        return notional / price

    def build_intent(
        self,
        *,
        symbol: str,
        signal: Signal,
        equity_usdt: float,
        amount_precision_fn=None,
    ) -> OrderIntent | None:
        if not signal.is_actionable:
            return None

        raw_amount = self.size_from_equity(equity_usdt, signal.price)
        if raw_amount <= 0:
            return None

        amount = raw_amount
        if amount_precision_fn is not None:
            amount = float(amount_precision_fn(symbol, raw_amount))
            if amount <= 0:
                return None

        sl: float | None = None
        tp: float | None = None
        if signal.side is Side.BUY:
            sl = signal.price * (1.0 - self.settings.stop_loss_pct)
            tp = signal.price * (1.0 + self.settings.take_profit_pct)
        elif signal.side is Side.SELL:
            sl = signal.price * (1.0 + self.settings.stop_loss_pct)
            tp = signal.price * (1.0 - self.settings.take_profit_pct)

        return OrderIntent(
            symbol=symbol,
            side=signal.side,
            amount=amount,
            notional_usdt=amount * signal.price,
            entry_price=signal.price,
            stop_loss=sl,
            take_profit=tp,
            reason=signal.reason,
        )

"""Strategy skeletons: MA crossover + simple price breakout."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


@dataclass(frozen=True)
class Signal:
    side: Side
    reason: str
    price: float
    meta: dict[str, float]

    @property
    def is_actionable(self) -> bool:
        return self.side in {Side.BUY, Side.SELL}


class Strategy(Protocol):
    name: str

    def evaluate(self, ohlcv: list[list[float]]) -> Signal:
        """Consume OHLCV rows and emit the latest signal."""


def _closes(ohlcv: list[list[float]]) -> list[float]:
    return [float(row[4]) for row in ohlcv]


def _sma(values: list[float], period: int) -> list[float | None]:
    """Simple moving average; None until enough bars."""
    out: list[float | None] = [None] * len(values)
    if period <= 0:
        raise ValueError("SMA period must be > 0")
    if len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


@dataclass
class MACrossoverStrategy:
    """
    Fast SMA crosses slow SMA.

    - Golden cross (fast rises above slow) → BUY
    - Death cross (fast falls below slow) → SELL
    Uses the last *closed* bar relative to previous bar for cross detection.
    """

    fast: int = 7
    slow: int = 25
    name: str = "ma_crossover"

    def __post_init__(self) -> None:
        if self.fast >= self.slow:
            raise ValueError("fast period must be < slow period")

    def evaluate(self, ohlcv: list[list[float]]) -> Signal:
        need = self.slow + 2
        if len(ohlcv) < need:
            raise ValueError(f"{self.name}: need >= {need} candles, got {len(ohlcv)}")

        closes = _closes(ohlcv)
        # Ignore forming candle: use closed bars only.
        closed = closes[:-1]
        fast = _sma(closed, self.fast)
        slow = _sma(closed, self.slow)
        i, j = -1, -2
        f0, f1 = fast[i], fast[j]
        s0, s1 = slow[i], slow[j]
        price = closed[-1]

        if None in (f0, f1, s0, s1):
            return Signal(Side.FLAT, "SMA not ready", price, {})

        assert f0 is not None and f1 is not None and s0 is not None and s1 is not None
        meta = {"fast": f0, "slow": s0, "prev_fast": f1, "prev_slow": s1}

        crossed_up = f1 <= s1 and f0 > s0
        crossed_down = f1 >= s1 and f0 < s0

        if crossed_up:
            return Signal(Side.BUY, f"golden cross SMA{self.fast}/{self.slow}", price, meta)
        if crossed_down:
            return Signal(Side.SELL, f"death cross SMA{self.fast}/{self.slow}", price, meta)
        return Signal(Side.FLAT, "no cross", price, meta)


@dataclass
class BreakoutStrategy:
    """
    Close breaks N-bar high/low (Donchian-style, skeleton).

    - Close > prior N-bar high → BUY
    - Close < prior N-bar low → SELL
    """

    lookback: int = 20
    name: str = "breakout"

    def evaluate(self, ohlcv: list[list[float]]) -> Signal:
        need = self.lookback + 2
        if len(ohlcv) < need:
            raise ValueError(f"{self.name}: need >= {need} candles, got {len(ohlcv)}")

        # Closed bars only (drop forming candle).
        bars = ohlcv[:-1]
        window = bars[-(self.lookback + 1) : -1]
        last = bars[-1]
        high = max(float(r[2]) for r in window)
        low = min(float(r[3]) for r in window)
        close = float(last[4])
        meta = {"breakout_high": high, "breakout_low": low, "lookback": float(self.lookback)}

        if close > high:
            return Signal(Side.BUY, f"close>{self.lookback}bar high", close, meta)
        if close < low:
            return Signal(Side.SELL, f"close<{self.lookback}bar low", close, meta)
        return Signal(Side.FLAT, "inside range", close, meta)


def build_strategy(name: str) -> Strategy:
    key = name.strip().lower()
    if key in {"ma", "ma_crossover", "macrossover"}:
        return MACrossoverStrategy()
    if key in {"breakout", "price_breakout"}:
        return BreakoutStrategy()
    raise ValueError(
        f"unknown strategy '{name}'. Choose: ma_crossover | breakout"
    )

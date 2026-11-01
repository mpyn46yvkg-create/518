"""Load settings from environment + CLI. Secrets never hard-coded."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. Testnet is the safe default."""

    api_key: str
    api_secret: str
    testnet: bool
    symbol: str
    timeframe: str
    strategy: str
    # Risk knobs (placeholders until sizing is wired)
    risk_per_trade: float
    stop_loss_pct: float
    take_profit_pct: float
    max_position_usdt: float
    leverage: int
    # Runner
    candle_limit: int
    poll_interval_sec: float
    live: bool

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def require_credentials_for_live(self) -> None:
        if self.live and not self.has_credentials:
            raise ValueError(
                "LIVE mode requires BINANCE_API_KEY and BINANCE_API_SECRET "
                "in the environment (see .env.example)."
            )
        if self.live and not self.testnet:
            # Explicit mainnet: still require the operator to have flipped the switch.
            # We do not auto-enable mainnet from CLI alone.
            pass


def load_settings(
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    strategy: str | None = None,
    live: bool = False,
    env_file: str | Path | None = None,
) -> Settings:
    """
    Load `.env` then environment variables.

    Defaults:
      - BINANCE_TESTNET=true
      - dry-run (live=False) unless caller passes live=True
    """
    # Prefer project-local .env when present.
    root = Path(__file__).resolve().parent.parent
    dotenv_path = Path(env_file) if env_file else root / ".env"
    if dotenv_path.is_file():
        load_dotenv(dotenv_path)
    else:
        load_dotenv()  # still allow process env / cwd .env

    settings = Settings(
        api_key=os.getenv("BINANCE_API_KEY", "").strip(),
        api_secret=os.getenv("BINANCE_API_SECRET", "").strip(),
        testnet=_env_bool("BINANCE_TESTNET", True),
        symbol=(symbol or os.getenv("SYMBOL") or "BTC/USDT:USDT").strip(),
        timeframe=(timeframe or os.getenv("TIMEFRAME") or "15m").strip(),
        strategy=(strategy or os.getenv("STRATEGY") or "ma_crossover").strip().lower(),
        risk_per_trade=float(os.getenv("RISK_PER_TRADE", "0.01")),
        stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0.01")),
        take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0.02")),
        max_position_usdt=float(os.getenv("MAX_POSITION_USDT", "100")),
        leverage=int(os.getenv("LEVERAGE", "5")),
        candle_limit=int(os.getenv("CANDLE_LIMIT", "120")),
        poll_interval_sec=float(os.getenv("POLL_INTERVAL_SEC", "15")),
        live=live,
    )
    settings.require_credentials_for_live()
    return settings

#!/usr/bin/env python3
"""CLI entry: Binance USDT-M futures bot (dry-run by default)."""

from __future__ import annotations

import argparse
import logging
import sys

from bot.config import load_settings
from bot.runner import BotRunner


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Binance USDT-M futures bot skeleton. "
            "Defaults to Futures Testnet + dry-run (prints order intents only)."
        )
    )
    p.add_argument(
        "--symbol",
        default=None,
        help="ccxt symbol, e.g. BTC/USDT:USDT (default from env SYMBOL)",
    )
    p.add_argument(
        "--timeframe",
        default=None,
        help="candle timeframe, e.g. 1m/5m/15m/1h (default from env TIMEFRAME)",
    )
    p.add_argument(
        "--strategy",
        default=None,
        choices=["ma_crossover", "breakout"],
        help="strategy skeleton (default from env STRATEGY or ma_crossover)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="actually place market orders (still testnet unless BINANCE_TESTNET=false)",
    )
    p.add_argument(
        "--loop",
        action="store_true",
        help="poll continuously using POLL_INTERVAL_SEC",
    )
    p.add_argument(
        "--iterations",
        type=int,
        default=None,
        help="with --loop, stop after N ticks (default: forever)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="DEBUG logging",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = load_settings(
            symbol=args.symbol,
            timeframe=args.timeframe,
            strategy=args.strategy,
            live=bool(args.live),
        )
    except ValueError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if settings.live and not settings.testnet:
        print(
            "WARNING: BINANCE_TESTNET=false and --live set → MAINNET LIVE ORDERS.",
            file=sys.stderr,
        )

    print(
        f"mode={'TESTNET' if settings.testnet else 'MAINNET'}/"
        f"{'LIVE' if settings.live else 'DRY-RUN'} "
        f"strategy={settings.strategy} symbol={settings.symbol} tf={settings.timeframe}",
        flush=True,
    )

    runner = BotRunner(settings)
    try:
        # Ensure markets are cached for precision helpers.
        runner.exchange.load_markets()
        if args.loop:
            runner.loop(iterations=args.iterations)
        else:
            runner.once()
    except Exception as exc:  # noqa: BLE001 — top-level CLI boundary
        logging.getLogger(__name__).exception("fatal: %s", exc)
        print(f"fatal: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

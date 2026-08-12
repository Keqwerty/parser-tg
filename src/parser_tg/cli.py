from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from parser_tg.config import ConfigError, Settings, load_rules
from parser_tg.telegram import TelegramService, healthcheck, login


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parser-tg")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="run the channel listener")
    subparsers.add_parser("login", help="authorize the dedicated Telegram account")
    validate = subparsers.add_parser("validate", help="validate a rules file")
    validate.add_argument("path", nargs="?", default=os.getenv("CONFIG_PATH", "config/rules.yaml"))
    health = subparsers.add_parser("healthcheck", help="check the service heartbeat")
    health.add_argument("--max-age", type=float, default=120.0)
    return parser


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    os.umask(0o077)
    args = _parser().parse_args()
    try:
        if args.command == "validate":
            rules = load_rules(Path(args.path))
            print(f"valid: {len(rules.sources)} sources, {len(rules.filters)} filters")
            return
        if args.command == "healthcheck":
            path = Path(os.getenv("HEALTH_PATH", "/data/healthy"))
            raise SystemExit(0 if healthcheck(path, max_age_seconds=args.max_age) else 1)

        settings = Settings.from_env(require_recipient=args.command == "run")
        _configure_logging(settings.log_level)
        if args.command == "login":
            asyncio.run(login(settings))
            return
        rules = load_rules(settings.config_path)
        asyncio.run(TelegramService(settings, rules).run())
    except (ConfigError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()

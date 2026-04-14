#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from dailyresearchfeeder.config import load_settings
from dailyresearchfeeder.orchestrator import run_scheduled_day
from dailyresearchfeeder.pipeline import run_backfill_digest, run_digest


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date: {value}. Expected YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Daily Research Feeder pipeline.")
    parser.add_argument(
        "--mode",
        choices=["digest", "scheduled_day"],
        default="digest",
        help="Run the one-shot digest pipeline or the staged scheduled-day pipeline.",
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--days", type=int, default=None, help="Override lookback window in days")
    parser.add_argument(
        "--backfill-date",
        type=_parse_iso_date,
        default=None,
        help="Generate and optionally send a backfill digest for a specific local date (YYYY-MM-DD).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Generate preview only, do not send email")
    parser.add_argument("--email-to", default=None, help="Override recipient email for this run")
    parser.add_argument(
        "--llm-provider",
        choices=["copilot_cli", "azure_openai", "openai"],
        default=None,
        help="Override the LLM provider for this run",
    )
    parser.add_argument(
        "--email-provider",
        choices=["azure_cli_graph", "resend", "gmail_smtp", "smtp", "file"],
        default=None,
        help="Override the email provider for this run",
    )
    return parser


async def _amain(args: argparse.Namespace) -> None:
    config_path = Path(args.config).resolve()
    load_dotenv(config_path.parent / ".env")

    if args.llm_provider:
        os.environ["LLM_PROVIDER"] = args.llm_provider

    if args.email_provider:
        os.environ["EMAIL_PROVIDER"] = args.email_provider

    if args.email_to:
        os.environ["EMAIL_TO"] = args.email_to

    settings = load_settings(config_path)
    if args.backfill_date is not None:
        digest = await run_backfill_digest(settings, target_date=args.backfill_date, dry_run=args.dry_run)
    elif args.mode == "scheduled_day":
        digest = await run_scheduled_day(settings, dry_run=args.dry_run, days_override=args.days)
    else:
        digest = await run_digest(settings, dry_run=args.dry_run, days_override=args.days)

    print(f"Fetched items: {digest.stats.get('fetched', 0)}")
    print(f"After dedupe/seen suppression: {digest.stats.get('after_seen_filter', 0)}")
    print(f"Keyword-assisted matches: {digest.stats.get('keyword_hits', 0)}")
    print(f"Review candidates: {digest.stats.get('review_candidates', 0)}")
    print(f"Selected papers: {len(digest.paper_picks)}")
    print(f"Selected updates: {len(digest.news_picks)}")
    print(f"Preview written to: {settings.delivery.preview_path}")


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
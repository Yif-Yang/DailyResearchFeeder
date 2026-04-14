from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from importlib import resources
from pathlib import Path

from dotenv import load_dotenv

from dailyresearchfeeder.config import load_settings
from dailyresearchfeeder.orchestrator import run_scheduled_day
from dailyresearchfeeder.pipeline import run_backfill_digest, run_digest


TEMPLATE_FILES = (
    "config.yaml",
    ".env.example",
    "user/keywords.txt",
    "user/exclude_keywords.txt",
    "user/research_interests.txt",
    "user/arxiv_categories.txt",
    "user/feeds.yaml",
)


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date: {value}. Expected YYYY-MM-DD") from exc


def build_run_parser() -> argparse.ArgumentParser:
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


def build_init_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold a Daily Research Feeder workspace.")
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Destination directory for the scaffolded config and user files.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing scaffold files.")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Also create .env from the .env.example template.",
    )
    return parser


def _template_resource(relative_path: str):
    resource = resources.files("dailyresearchfeeder.templates")
    for part in Path(relative_path).parts:
        resource = resource.joinpath(part)
    return resource


def scaffold_project(destination: str | Path, *, force: bool = False, write_env: bool = False) -> dict[str, str]:
    destination = Path(destination).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)

    for relative_dir in ("user", "artifacts", "runtime", "state"):
        (destination / relative_dir).mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}
    for relative_path in TEMPLATE_FILES:
        target_path = destination / relative_path
        existed_before = target_path.exists()
        if target_path.exists() and not force:
            results[relative_path] = "skipped"
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(_template_resource(relative_path).read_text(encoding="utf-8"), encoding="utf-8")
        results[relative_path] = "overwritten" if existed_before and force else "created"

    if write_env:
        env_target = destination / ".env"
        env_existed_before = env_target.exists()
        if env_target.exists() and not force:
            results[".env"] = "skipped"
        else:
            env_target.write_text(_template_resource(".env.example").read_text(encoding="utf-8"), encoding="utf-8")
            results[".env"] = "overwritten" if env_existed_before and force else "created"

    return results


async def _run_digest_from_args(args: argparse.Namespace) -> None:
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


def run_init(args: argparse.Namespace) -> None:
    destination = Path(args.path).expanduser().resolve()
    results = scaffold_project(destination, force=args.force, write_env=args.write_env)
    print(f"Scaffolded Daily Research Feeder workspace at: {destination}")
    for relative_path in sorted(results):
        print(f"{results[relative_path]:>11}  {relative_path}")
    if not args.write_env:
        print("Next: copy .env.example to .env and add your provider credentials.")


def run_main(args: argparse.Namespace) -> None:
    asyncio.run(_run_digest_from_args(args))


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "init":
        args = build_init_parser().parse_args(argv[1:])
        run_init(args)
        return

    args = build_run_parser().parse_args(argv)
    run_main(args)


if __name__ == "__main__":
    main()

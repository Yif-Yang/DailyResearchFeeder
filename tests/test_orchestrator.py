from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dailyresearchfeeder.config import load_settings
from dailyresearchfeeder.models import CandidateItem, ItemKind
from dailyresearchfeeder.orchestrator import (
    SOURCE_KEY_ARXIV,
    SOURCE_KEY_HUGGINGFACE,
    estimate_remaining_minutes,
    summarize_paper_source_status,
)
from dailyresearchfeeder.state import SeenStateStore


def test_summarize_paper_source_status_marks_target_day_sources_fresh(tmp_path) -> None:
    state_store = SeenStateStore(path=tmp_path / "seen.json")
    state_store.items = {}
    target_day = date(2026, 4, 13)

    arxiv_item = CandidateItem(
        title="Fresh arXiv paper",
        summary="A new agent systems paper.",
        url="https://arxiv.org/abs/2604.00001",
        source_name="arXiv",
        kind=ItemKind.PAPER,
        source_group="arxiv",
        published_at=datetime(2026, 4, 13, 1, 0, tzinfo=timezone.utc),
    )
    hf_item = CandidateItem(
        title="Fresh HF daily paper",
        summary="Curated paper of the day.",
        url="https://huggingface.co/papers/2604.00001",
        source_name="Hugging Face Daily Papers",
        kind=ItemKind.PAPER,
        source_group="huggingface_daily",
        published_at=datetime(2026, 4, 12, 18, 0, tzinfo=timezone.utc),
    )

    status = summarize_paper_source_status(
        {
            SOURCE_KEY_ARXIV: [arxiv_item],
            SOURCE_KEY_HUGGINGFACE: [hf_item],
        },
        state_store,
        "Asia/Shanghai",
        target_day,
    )

    assert status[SOURCE_KEY_ARXIV]["fresh"] is True
    assert status[SOURCE_KEY_ARXIV]["unseen"] == 1
    assert status[SOURCE_KEY_ARXIV]["errors"] == 0
    assert status[SOURCE_KEY_HUGGINGFACE]["fresh"] is True
    assert status[SOURCE_KEY_HUGGINGFACE]["unseen"] == 1
    assert status[SOURCE_KEY_HUGGINGFACE]["errors"] == 0


def test_summarize_paper_source_status_does_not_treat_old_unseen_papers_as_fresh(tmp_path) -> None:
    state_store = SeenStateStore(path=tmp_path / "seen.json")
    state_store.items = {}
    target_day = date(2026, 4, 14)

    old_arxiv_item = CandidateItem(
        title="Old arXiv paper",
        summary="An older agent paper.",
        url="https://arxiv.org/abs/2604.00002",
        source_name="arXiv",
        kind=ItemKind.PAPER,
        source_group="arxiv",
        published_at=datetime(2026, 4, 12, 12, 0, tzinfo=timezone.utc),
    )

    status = summarize_paper_source_status(
        {
            SOURCE_KEY_ARXIV: [old_arxiv_item],
            SOURCE_KEY_HUGGINGFACE: [],
        },
        state_store,
        "Asia/Shanghai",
        target_day,
    )

    assert status[SOURCE_KEY_ARXIV]["fresh"] is False
    assert status[SOURCE_KEY_ARXIV]["fetched"] == 0
    assert status[SOURCE_KEY_ARXIV]["unseen"] == 0


def test_summarize_paper_source_status_includes_fetch_errors(tmp_path) -> None:
    state_store = SeenStateStore(path=tmp_path / "seen.json")
    state_store.items = {}

    status = summarize_paper_source_status(
        {
            SOURCE_KEY_ARXIV: [],
            SOURCE_KEY_HUGGINGFACE: [],
        },
        state_store,
        "Asia/Shanghai",
        date(2026, 4, 14),
        fetch_stats={
            "arxiv_errors": 1,
            "huggingface_daily_errors": 2,
        },
    )

    assert status[SOURCE_KEY_ARXIV]["errors"] == 1
    assert status[SOURCE_KEY_HUGGINGFACE]["errors"] == 2


def test_estimate_remaining_minutes_accounts_for_next_check() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    settings = load_settings(repo_root / "config.yaml")
    now_local = datetime(2026, 4, 13, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    next_check_at = now_local + timedelta(minutes=15)

    eta = estimate_remaining_minutes(
        now_local,
        next_check_at,
        news_done=True,
        paper_review_started=False,
        settings=settings,
    )

    assert eta == 45
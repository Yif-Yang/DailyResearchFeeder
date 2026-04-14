from datetime import date, datetime, timezone

from pathlib import Path

from dailyresearchfeeder.config import load_settings
from dailyresearchfeeder.models import CandidateItem, ItemKind
from dailyresearchfeeder.pipeline import (
    _select_items,
    dedupe_items,
    filter_paper_source_batches_for_target_day,
    keyword_filter,
)


def test_keyword_filter_matches_relevant_items() -> None:
    item = CandidateItem(
        title="Tool Call RL for Agent Skill Learning",
        summary="A new RL environment for tool-using agents and evaluation harnesses.",
        url="https://example.com/paper-1",
        source_name="arXiv",
        kind=ItemKind.PAPER,
        source_group="arxiv",
    )

    filtered = keyword_filter([item], ["agent skill", "tool call rl", "rl environment"], [])

    assert len(filtered) == 1
    assert "agent skill" in filtered[0].matched_keywords
    assert "tool call rl" in filtered[0].matched_keywords


def test_dedupe_items_normalizes_tracking_parameters() -> None:
    first = CandidateItem(
        title="Same item",
        summary="first",
        url="https://example.com/post?utm_source=x",
        source_name="feed",
        kind=ItemKind.BLOG,
        source_group="blogs",
    )
    second = CandidateItem(
        title="Same item duplicate",
        summary="second",
        url="https://example.com/post",
        source_name="feed",
        kind=ItemKind.BLOG,
        source_group="blogs",
    )

    deduped = dedupe_items([first, second])

    assert len(deduped) == 1


def test_keyword_filter_soft_prioritizes_instead_of_dropping_unmatched_items() -> None:
    matched = CandidateItem(
        title="Agent skill training for tool use",
        summary="Evaluation harness and RL environment design.",
        url="https://example.com/matched",
        source_name="arXiv",
        kind=ItemKind.PAPER,
        source_group="arxiv",
    )
    unmatched = CandidateItem(
        title="General multimodal systems paper",
        summary="Still worth LLM review when budget is not the constraint.",
        url="https://example.com/unmatched",
        source_name="arXiv",
        kind=ItemKind.PAPER,
        source_group="arxiv",
    )

    filtered = keyword_filter([unmatched, matched], ["agent skill", "rl environment"], [])

    assert len(filtered) == 2
    assert filtered[0].url == "https://example.com/matched"
    assert "agent skill" in filtered[0].matched_keywords


def test_keyword_filter_boosts_major_ai_news_from_top_labs() -> None:
    major_news = CandidateItem(
        title="OpenAI launches new reasoning API for agent workflows",
        summary="A major release with tool use and production workflow support.",
        url="https://example.com/openai-news",
        source_name="OpenAI News",
        kind=ItemKind.RELEASE,
        source_group="company_blogs",
    )
    generic = CandidateItem(
        title="General ML notes",
        summary="Miscellaneous update with no strong signal.",
        url="https://example.com/generic-news",
        source_name="Some Feed",
        kind=ItemKind.BLOG,
        source_group="other",
    )

    filtered = keyword_filter([generic, major_news], ["agent skill"], [])

    assert filtered[0].url == "https://example.com/openai-news"
    assert "major-ai-news" in filtered[0].matched_keywords


def test_keyword_filter_boosts_major_company_news_from_industry_sites() -> None:
    third_party_news = CandidateItem(
        title="OpenAI acquires startup to expand agent platform stack",
        summary="TechCrunch reports a major acquisition tied to enterprise agent tooling and workflow infrastructure.",
        url="https://example.com/industry-news",
        source_name="TechCrunch AI",
        kind=ItemKind.BLOG,
        source_group="industry_news",
    )
    generic = CandidateItem(
        title="Weekly AI links",
        summary="A mixed collection of unrelated AI headlines.",
        url="https://example.com/weekly-links",
        source_name="Random Feed",
        kind=ItemKind.BLOG,
        source_group="other",
    )

    filtered = keyword_filter([generic, third_party_news], ["agent skill"], [])

    assert filtered[0].url == "https://example.com/industry-news"
    assert "major-ai-news" in filtered[0].matched_keywords


def test_filter_paper_source_batches_for_target_day_keeps_only_target_local_date() -> None:
    target_day = date(2026, 4, 14)
    today_paper = CandidateItem(
        title="Today paper",
        summary="Fresh paper for today's digest.",
        url="https://example.com/today-paper",
        source_name="arXiv",
        kind=ItemKind.PAPER,
        source_group="arxiv",
        published_at=datetime(2026, 4, 13, 18, 0, tzinfo=timezone.utc),
    )
    old_paper = CandidateItem(
        title="Old paper",
        summary="Yesterday's paper should be excluded.",
        url="https://example.com/old-paper",
        source_name="Hugging Face Daily Papers",
        kind=ItemKind.PAPER,
        source_group="huggingface_daily",
        published_at=datetime(2026, 4, 12, 15, 0, tzinfo=timezone.utc),
    )
    blog = CandidateItem(
        title="News stays untouched",
        summary="Feed items should not be day-filtered here.",
        url="https://example.com/news",
        source_name="Feed",
        kind=ItemKind.BLOG,
        source_group="feeds",
        published_at=datetime(2026, 4, 11, 8, 0, tzinfo=timezone.utc),
    )

    filtered = filter_paper_source_batches_for_target_day(
        {
            "arxiv": [today_paper],
            "huggingface_daily": [old_paper],
            "feeds": [blog],
        },
        "Asia/Shanghai",
        target_day,
    )

    assert [item.url for item in filtered["arxiv"]] == ["https://example.com/today-paper"]
    assert filtered["huggingface_daily"] == []
    assert [item.url for item in filtered["feeds"]] == ["https://example.com/news"]


def test_select_items_keeps_keyword_news_and_hot_industry_news() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    settings = load_settings(repo_root / "config.yaml")
    settings.pipeline.max_news = 3

    top_tool_news = CandidateItem(
        title="Reward functions for agent infrastructure",
        summary="General tooling guidance.",
        url="https://example.com/tool-news-1",
        source_name="AWS ML Blog",
        kind=ItemKind.BLOG,
        source_group="tooling_blogs",
        relevance_score=8.2,
        decision="keep",
    )
    second_tool_news = CandidateItem(
        title="Bedrock runtime updates",
        summary="A broad platform update.",
        url="https://example.com/tool-news-2",
        source_name="AWS ML Blog",
        kind=ItemKind.BLOG,
        source_group="tooling_blogs",
        relevance_score=7.9,
        decision="keep",
    )
    keyword_news = CandidateItem(
        title="Presentation agent adds design copilot workflow for slide generation",
        summary="A new presentation agent feature set for workplace decks.",
        url="https://example.com/keyword-news",
        source_name="LangChain Blog",
        kind=ItemKind.BLOG,
        source_group="tooling_blogs",
        relevance_score=5.4,
        decision="maybe",
    )
    hot_industry_news = CandidateItem(
        title="OpenAI leaked memo hints at a new agent platform launch",
        summary="Industry coverage points to a major upcoming product release.",
        url="https://example.com/hot-industry-news",
        source_name="TechCrunch AI",
        kind=ItemKind.BLOG,
        source_group="industry_news",
        matched_keywords=["major-ai-news"],
        relevance_score=5.2,
        decision="maybe",
    )

    _, news_picks, _ = _select_items(
        [top_tool_news, second_tool_news, keyword_news, hot_industry_news],
        settings,
    )

    selected_urls = {item.url for item in news_picks}
    assert "https://example.com/keyword-news" in selected_urls
    assert "https://example.com/hot-industry-news" in selected_urls
    assert len(news_picks) == 3
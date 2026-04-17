from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import date
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dailyresearchfeeder.config import Settings
from dailyresearchfeeder.emailer import AzureCliGraphEmailer, FileEmailer, ResendEmailer, SMTPEmailer
from dailyresearchfeeder.llm import ReasoningClient
from dailyresearchfeeder.models import CandidateItem, DailyDigest, ItemKind
from dailyresearchfeeder.renderer import render_digest_html
from dailyresearchfeeder.sources import ArxivSource, FeedSource, HuggingFaceDailySource
from dailyresearchfeeder.state import SeenStateStore, normalize_url


SOURCE_KEY_ARXIV = "arxiv"
SOURCE_KEY_HUGGINGFACE = "huggingface_daily"
SOURCE_KEY_FEEDS = "feeds"
PAPER_SOURCE_KEYS = (SOURCE_KEY_ARXIV, SOURCE_KEY_HUGGINGFACE)
NEWS_SOURCE_KEYS = (SOURCE_KEY_FEEDS,)


RELATED_TOPIC_HINTS: dict[str, tuple[str, ...]] = {
    "agentic-systems": (
        "agent", "agentic", "assistant", "workflow", "planner", "orchestrator", "multi-step",
        "browser use", "computer use", "autonomous", "deep research",
    ),
    "tool-use": (
        "tool use", "tool-use", "tool calling", "function calling", "api use", "grounded actions",
        "web agent", "computer agent", "toolformer",
    ),
    "eval-harness": (
        "harness", "benchmark", "grader", "eval", "evaluation", "arena", "simulator",
        "environment", "test-time", "reward", "agent benchmark",
    ),
    "rl-agents": (
        "reinforcement learning", "rl ", "rlhf", "policy", "rollout", "trajectory", "environment",
        "self-play", "verifier", "agent training",
    ),
    "presentation-design": (
        "ppt", "powerpoint", "presentation", "slide", "deck", "design", "figma", "canvas",
        "document generation", "office", "report generation",
    ),
    "major-ai-news": (
        "open-source", "open source", "launch", "launched", "released", "release", "introduces",
        "announces", "announced", "api", "reasoning model", "frontier model", "breakthrough",
        "acquire", "acquires", "acquired", "bought", "buying", "funding", "raised", "raises",
        "partnership", "deal", "merger", "memo", "leak", "leaked", "rumor", "rumored",
        "preview", "beta", "general availability", "ga", "roadmap", "agentic workflow", "infrastructure",
    ),
}

MAJOR_SOURCE_HINTS = (
    "openai", "anthropic", "deepmind", "google ai", "google deepmind", "microsoft research",
    "nvidia", "hugging face", "meta ai", "bair", "amazon science", "aws", "microsoft",
    "xai", "openrouter", "langchain", "together ai", "mistral",
)

HIGH_SIGNAL_SOURCE_GROUPS = {
    "huggingface_daily": 3.0,
    "company_blogs": 2.0,
    "research_blogs": 1.5,
    "tooling_blogs": 1.8,
    "industry_news": 1.8,
    "arxiv": 1.0,
    "social_watch": 0.5,
}

HOT_NEWS_SOURCE_GROUPS = {"company_blogs", "industry_news"}
MIN_NEWS_PICK_TARGET = 5
RELAXED_NEWS_SCORE_FLOOR = 4.8
KEYWORD_MATCH_STOPWORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}


def _normalize_text(value: str) -> str:
    lowered = (value or "").lower()
    lowered = lowered.replace("_", " ")
    lowered = re.sub(r"[^a-z0-9+/\-.# ]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _tokenize(value: str) -> list[str]:
    return [token for token in _normalize_text(value).split(" ") if token]


def _item_text_blob(item: CandidateItem) -> str:
    return " ".join([item.title, item.summary, item.source_name, item.source_group, " ".join(item.raw_tags)])


def _token_matches(keyword_token: str, text_tokens: set[str]) -> bool:
    if keyword_token in text_tokens:
        return True
    if len(keyword_token) < 4:
        return False
    return any(
        text_token.startswith(keyword_token) or keyword_token.startswith(text_token)
        for text_token in text_tokens
        if len(text_token) >= 4
    )


def _match_keywords(text: str, keywords: list[str]) -> list[str]:
    normalized_text = _normalize_text(text)
    text_tokens = set(_tokenize(normalized_text))
    matched: list[str] = []

    for keyword in keywords:
        normalized_keyword = _normalize_text(keyword)
        if not normalized_keyword:
            continue
        if normalized_keyword in normalized_text:
            matched.append(keyword)
            continue

        keyword_tokens = [token for token in _tokenize(normalized_keyword) if len(token) > 1]
        if not keyword_tokens:
            continue

        matched_count = sum(1 for token in keyword_tokens if _token_matches(token, text_tokens))
        required_matches = len(keyword_tokens) if len(keyword_tokens) <= 2 else len(keyword_tokens) - 1
        if matched_count >= required_matches:
            matched.append(keyword)

    return matched


def _match_related_topics(text: str) -> list[str]:
    normalized_text = _normalize_text(text)
    labels: list[str] = []
    for label, phrases in RELATED_TOPIC_HINTS.items():
        if any(_normalize_text(phrase) in normalized_text for phrase in phrases):
            labels.append(label)
    return labels


def _source_priority_boost(item: CandidateItem) -> float:
    text = _normalize_text(f"{item.source_name} {item.source_group} {item.title} {item.summary}")
    boost = HIGH_SIGNAL_SOURCE_GROUPS.get(item.source_group, 0.0)
    if any(hint in text for hint in MAJOR_SOURCE_HINTS):
        boost += 2.5
    if item.kind == ItemKind.RELEASE:
        boost += 1.0
    return boost


def _recency_boost(item: CandidateItem) -> float:
    if not item.published_at:
        return 0.0
    age_hours = max(0.0, (datetime.now(timezone.utc) - item.published_at.astimezone(timezone.utc)).total_seconds() / 3600)
    if age_hours <= 12:
        return 2.5
    if age_hours <= 24:
        return 2.0
    if age_hours <= 72:
        return 1.0
    return 0.0


def _pre_review_priority(item: CandidateItem, matched: list[str], related: list[str]) -> float:
    priority = 4.0 * len(matched)
    priority += 2.0 * len(related)
    priority += _source_priority_boost(item)
    priority += _recency_boost(item)
    if item.kind != ItemKind.PAPER and "major-ai-news" in related:
        priority += 1.5
    if item.kind == ItemKind.PAPER:
        priority += 0.6
    return priority


def keyword_filter(
    items: list[CandidateItem],
    keywords: list[str],
    exclude_keywords: list[str],
) -> list[CandidateItem]:
    if not items:
        return []

    prioritized: list[CandidateItem] = []
    for item in items:
        text = _item_text_blob(item)
        if _match_keywords(text, exclude_keywords):
            continue

        matched = _match_keywords(text, keywords)
        related = _match_related_topics(text)
        item.matched_keywords = list(dict.fromkeys(item.matched_keywords + matched + related))
        item.debug_payload["pre_review_priority"] = _pre_review_priority(item, matched, related)
        prioritized.append(item)

    return sorted(prioritized, key=_priority_sort_key, reverse=True)


def dedupe_items(items: list[CandidateItem]) -> list[CandidateItem]:
    ordered = sorted(items, key=_sort_key, reverse=True)
    seen: set[str] = set()
    deduped: list[CandidateItem] = []
    for item in ordered:
        key = normalize_url(item.url) or _normalize_text(item.title)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _sort_key(item: CandidateItem) -> tuple[float, int]:
    published = item.published_at.timestamp() if item.published_at else 0.0
    kind_weight = {
        ItemKind.PAPER: 4,
        ItemKind.RELEASE: 3,
        ItemKind.BLOG: 2,
        ItemKind.SOCIAL: 1,
    }[item.kind]
    return (published, kind_weight)


def _priority_sort_key(item: CandidateItem) -> tuple[int, float, int]:
    published, kind_weight = _sort_key(item)
    priority = float(item.debug_payload.get("pre_review_priority", len(item.matched_keywords)))
    return (int(priority * 1000), published, kind_weight)


def create_state_store(settings: Settings) -> SeenStateStore:
    state_store = SeenStateStore(
        path=settings.state.seen_items_path,
        ttl_days=settings.state.seen_ttl_days,
        max_items=settings.state.max_items,
    )
    state_store.load()
    state_store.prune()
    return state_store


def build_llm_client(
    settings: Settings,
    *,
    model_override: str | None = None,
    reasoning_effort_override: str | None = None,
) -> ReasoningClient:
    return ReasoningClient(
        provider=settings.llm.provider,
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        azure_endpoint=settings.llm.azure_endpoint,
        azure_api_version=settings.llm.azure_api_version,
        azure_deployment=settings.llm.azure_deployment,
        model=model_override or settings.llm.model,
        reasoning_effort=reasoning_effort_override or settings.llm.reasoning_effort,
        timeout_seconds=settings.llm.timeout_seconds,
        copilot_command=settings.llm.copilot_command,
    )


def build_emailer(settings: Settings):
    if settings.email.provider == "resend":
        if not settings.email.resend_api_key:
            raise ValueError("RESEND_API_KEY is required when email provider is resend")
        return ResendEmailer(api_key=settings.email.resend_api_key, from_email=settings.email.from_email)
    if settings.email.provider == "azure_cli_graph":
        return AzureCliGraphEmailer(azure_cli_command=settings.email.azure_cli_command)
    if settings.email.provider in {"gmail_smtp", "smtp"}:
        return SMTPEmailer(
            host=settings.email.smtp_host,
            port=settings.email.smtp_port,
            username=settings.email.smtp_username,
            password=settings.email.smtp_password,
            from_email=settings.email.from_email or settings.email.smtp_username,
            use_starttls=settings.email.smtp_use_starttls,
        )
    if settings.email.provider == "file":
        return FileEmailer(settings.delivery.preview_path)
    raise ValueError(f"Unsupported email provider: {settings.email.provider}")


def _item_local_date(item: CandidateItem, timezone_name: str) -> date | None:
    if item.published_at is None:
        return None
    return item.published_at.astimezone(ZoneInfo(timezone_name)).date()


async def collect_source_batches(
    settings: Settings,
    days_back: int,
    source_keys: tuple[str, ...] | None = None,
    paper_days_back: int | None = None,
) -> tuple[dict[str, list[CandidateItem]], dict[str, int]]:
    requested = set(source_keys or (SOURCE_KEY_ARXIV, SOURCE_KEY_HUGGINGFACE, SOURCE_KEY_FEEDS))
    tasks: dict[str, asyncio.Future] = {}
    effective_paper_days_back = paper_days_back if paper_days_back is not None else days_back

    if settings.sources.arxiv_enabled and SOURCE_KEY_ARXIV in requested:
        tasks[SOURCE_KEY_ARXIV] = ArxivSource(settings.arxiv_categories).fetch(
            days_back=effective_paper_days_back,
            max_results=settings.sources.arxiv_max_results,
        )
    if settings.sources.huggingface_enabled and SOURCE_KEY_HUGGINGFACE in requested:
        tasks[SOURCE_KEY_HUGGINGFACE] = HuggingFaceDailySource().fetch(days_back=effective_paper_days_back)
    if settings.sources.feeds_enabled and SOURCE_KEY_FEEDS in requested:
        tasks[SOURCE_KEY_FEEDS] = FeedSource(settings.feeds).fetch(
            days_back=days_back,
            max_entries_per_feed=settings.sources.feed_max_entries_per_feed,
        )

    if not tasks:
        return {key: [] for key in requested}, {"fetched": 0}

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    source_batches: dict[str, list[CandidateItem]] = {key: [] for key in requested}
    stats: dict[str, int] = {"fetched": 0}

    for source_key, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            source_batches[source_key] = []
            stats[f"{source_key}_errors"] = stats.get(f"{source_key}_errors", 0) + 1
            print(f"Paper/news source fetch failed for {source_key}: {result}", file=sys.stderr)
            continue

        source_batches[source_key] = list(result)
        stats[f"{source_key}_fetched"] = len(result)
        stats["fetched"] += len(result)

    return source_batches, stats


def flatten_source_batches(
    source_batches: dict[str, list[CandidateItem]],
    source_keys: tuple[str, ...] | None = None,
) -> list[CandidateItem]:
    keys = source_keys or tuple(source_batches.keys())
    combined: list[CandidateItem] = []
    for source_key in keys:
        combined.extend(source_batches.get(source_key, []))
    return dedupe_items(combined)


def filter_seen_items(items: list[CandidateItem], state_store: SeenStateStore) -> list[CandidateItem]:
    return [item for item in items if not state_store.has_seen(item.url)]


def filter_items_to_target_local_day(
    items: list[CandidateItem],
    timezone_name: str,
    target_day: date,
) -> list[CandidateItem]:
    return [item for item in items if _item_local_date(item, timezone_name) == target_day]


def filter_paper_source_batches_for_target_day(
    source_batches: dict[str, list[CandidateItem]],
    timezone_name: str,
    target_day: date,
) -> dict[str, list[CandidateItem]]:
    filtered_batches = {key: list(items) for key, items in source_batches.items()}
    for source_key in PAPER_SOURCE_KEYS:
        filtered_batches[source_key] = filter_items_to_target_local_day(
            filtered_batches.get(source_key, []),
            timezone_name,
            target_day,
        )
    return filtered_batches


def recompute_fetch_stats(
    source_batches: dict[str, list[CandidateItem]],
    *,
    source_keys: tuple[str, ...] | None = None,
    base_stats: dict[str, int] | None = None,
) -> dict[str, int]:
    refreshed = {
        key: value
        for key, value in (base_stats or {}).items()
        if key.endswith("_errors")
    }
    requested_keys = source_keys or tuple(source_batches.keys())
    refreshed["fetched"] = 0
    for source_key in requested_keys:
        count = len(source_batches.get(source_key, []))
        refreshed[f"{source_key}_fetched"] = count
        refreshed["fetched"] += count
    return refreshed


async def review_candidates(
    settings: Settings,
    candidates: list[CandidateItem],
) -> tuple[list[CandidateItem], dict[str, int]]:
    prioritized = keyword_filter(candidates, settings.keywords, settings.exclude_keywords)
    if len(prioritized) > settings.pipeline.max_review_items:
        prioritized = prioritized[: settings.pipeline.max_review_items]
    stats = {
        "keyword_hits": sum(1 for item in prioritized if item.matched_keywords),
        "review_candidates": len(prioritized),
    }

    final_candidates = prioritized
    if settings.llm.enable_fast_mode and len(prioritized) > settings.llm.fast_mode_threshold:
        scan_client = build_llm_client(
            settings,
            model_override=settings.llm.scan_model,
            reasoning_effort_override=settings.llm.scan_reasoning_effort,
        )
        scanned_items = await scan_client.score_candidates(
            items=prioritized,
            research_interests=settings.research_interests,
            keywords=settings.keywords,
            language=settings.language,
            batch_size=settings.pipeline.llm_batch_size,
        )
        final_candidates = scanned_items[: settings.llm.fast_mode_shortlist_size]
        stats["fast_mode_scanned"] = len(scanned_items)
        stats["fast_mode_shortlist"] = len(final_candidates)

    llm_client = build_llm_client(settings)
    reviewed_items = await llm_client.score_candidates(
        items=final_candidates,
        research_interests=settings.research_interests,
        keywords=settings.keywords,
        language=settings.language,
        batch_size=settings.pipeline.llm_batch_size,
    )
    stats["reviewed"] = len(reviewed_items)
    return reviewed_items, stats


async def assemble_digest(
    settings: Settings,
    reviewed_items: list[CandidateItem],
    stats: dict[str, int],
    *,
    subject: str | None = None,
) -> DailyDigest:
    now_local = datetime.now(ZoneInfo(settings.timezone))
    digest_subject = subject or f"{settings.delivery.subject_prefix} | {now_local:%Y-%m-%d}"
    paper_picks, news_picks, watchlist = _select_items(reviewed_items, settings)

    llm_client = build_llm_client(settings)
    overview, takeaways = await llm_client.compose_overview(
        papers=paper_picks,
        news=news_picks,
        keywords=settings.keywords,
        research_interests=settings.research_interests,
    )

    digest = DailyDigest(
        generated_at=datetime.now(timezone.utc),
        keywords=settings.keywords,
        overview=overview,
        takeaways=takeaways,
        paper_picks=paper_picks,
        news_picks=news_picks,
        watchlist=watchlist,
        reviewed_items=reviewed_items,
        subject=digest_subject,
        stats=stats,
    )
    digest.html = render_digest_html(digest, settings)
    return digest


async def deliver_digest(
    settings: Settings,
    digest: DailyDigest,
    *,
    dry_run: bool,
    state_store: SeenStateStore | None,
) -> None:
    preview_email = FileEmailer(settings.delivery.preview_path)
    await preview_email.send(settings.email.to_email or "preview@example.com", digest.subject, digest.html)
    _write_run_artifact(settings, digest)

    if dry_run:
        return

    if not settings.email.to_email:
        raise ValueError("EMAIL_TO is required when dry_run is false")

    emailer = build_emailer(settings)
    await emailer.send(settings.email.to_email, digest.subject, digest.html)

    if state_store is not None:
        state_store.mark_seen([item.url for item in digest.paper_picks + digest.news_picks + digest.watchlist])
        state_store.prune()
        state_store.save()


def _select_items(reviewed_items: list[CandidateItem], settings: Settings) -> tuple[list[CandidateItem], list[CandidateItem], list[CandidateItem]]:
    threshold = settings.pipeline.score_threshold
    qualified = [
        item
        for item in reviewed_items
        if item.relevance_score >= threshold or item.decision == "keep"
    ]
    qualified.sort(key=lambda item: item.relevance_score, reverse=True)

    paper_picks = [item for item in qualified if item.kind == ItemKind.PAPER][: settings.pipeline.max_papers]
    news_picks = _select_news_items(reviewed_items, qualified, settings)

    selected = {normalize_url(item.url) for item in paper_picks + news_picks}
    watch_candidates = [
        item
        for item in reviewed_items
        if normalize_url(item.url) not in selected and item.relevance_score >= max(5.5, threshold - 1.0)
    ]
    watch_candidates.sort(key=lambda item: item.relevance_score, reverse=True)
    watchlist = watch_candidates[: settings.pipeline.max_watchlist]
    return paper_picks, news_picks, watchlist


def _has_user_keyword_match(item: CandidateItem, keywords: list[str]) -> bool:
    normalized_text = _normalize_text(_item_text_blob(item))
    text_tokens = set(_tokenize(normalized_text))

    for keyword in keywords:
        normalized_keyword = _normalize_text(keyword)
        if not normalized_keyword:
            continue
        if normalized_keyword in normalized_text:
            return True

        keyword_tokens = [
            token
            for token in _tokenize(normalized_keyword)
            if len(token) > 2 and token not in KEYWORD_MATCH_STOPWORDS
        ]
        if not keyword_tokens:
            continue

        matched_count = sum(1 for token in keyword_tokens if _token_matches(token, text_tokens))
        required_matches = len(keyword_tokens) if len(keyword_tokens) <= 2 else len(keyword_tokens) - 1
        if matched_count >= required_matches:
            return True

    return False


def _is_hot_industry_news(item: CandidateItem) -> bool:
    if item.kind == ItemKind.PAPER:
        return False
    if item.source_group not in HOT_NEWS_SOURCE_GROUPS:
        return False
    return "major-ai-news" in item.matched_keywords or item.kind == ItemKind.RELEASE


def _news_sort_key(item: CandidateItem) -> tuple[int, int, int, float, int]:
    published, kind_weight = _sort_key(item)
    return (
        int(_is_hot_industry_news(item)),
        int("major-ai-news" in item.matched_keywords),
        int(item.kind == ItemKind.RELEASE),
        item.relevance_score,
        published + kind_weight / 10,
    )


def _append_first_matching(
    selected: list[CandidateItem],
    seen_urls: set[str],
    pools: tuple[list[CandidateItem], ...],
    predicate,
) -> None:
    for pool in pools:
        for item in pool:
            normalized_url = normalize_url(item.url)
            if normalized_url in seen_urls or not predicate(item):
                continue
            selected.append(item)
            seen_urls.add(normalized_url)
            return


def _append_all_unique(
    selected: list[CandidateItem],
    seen_urls: set[str],
    pool: list[CandidateItem],
    limit: int,
) -> None:
    for item in pool:
        if len(selected) >= limit:
            return
        normalized_url = normalize_url(item.url)
        if normalized_url in seen_urls:
            continue
        selected.append(item)
        seen_urls.add(normalized_url)


def _select_news_items(
    reviewed_items: list[CandidateItem],
    qualified_items: list[CandidateItem],
    settings: Settings,
) -> list[CandidateItem]:
    max_news = settings.pipeline.max_news
    if max_news <= 0:
        return []

    qualified_news = [item for item in qualified_items if item.kind != ItemKind.PAPER]
    qualified_news.sort(key=_news_sort_key, reverse=True)

    relaxed_threshold = max(RELAXED_NEWS_SCORE_FLOOR, settings.pipeline.score_threshold - 1.6)
    fallback_news = [
        item
        for item in reviewed_items
        if item.kind != ItemKind.PAPER
        and item.relevance_score >= relaxed_threshold
        and (
            _has_user_keyword_match(item, settings.keywords)
            or _is_hot_industry_news(item)
            or item.decision == "keep"
        )
    ]
    fallback_news.sort(key=_news_sort_key, reverse=True)

    selected: list[CandidateItem] = []
    seen_urls: set[str] = set()
    pools = (qualified_news, fallback_news)

    _append_first_matching(selected, seen_urls, pools, lambda item: _has_user_keyword_match(item, settings.keywords))
    _append_first_matching(selected, seen_urls, pools, _is_hot_industry_news)
    _append_all_unique(selected, seen_urls, qualified_news, max_news)

    minimum_news = min(max_news, MIN_NEWS_PICK_TARGET)
    if len(selected) < minimum_news:
        _append_all_unique(selected, seen_urls, fallback_news, minimum_news)

    return selected[:max_news]


async def _collect_candidates(
    settings: Settings,
    days_back: int,
    state_store: SeenStateStore,
    *,
    target_day: date | None = None,
    paper_days_back: int | None = None,
) -> tuple[list[CandidateItem], dict[str, int]]:
    source_batches, stats = await collect_source_batches(settings, days_back, paper_days_back=paper_days_back)
    if target_day is not None:
        source_batches = filter_paper_source_batches_for_target_day(source_batches, settings.timezone, target_day)
        stats = recompute_fetch_stats(source_batches, base_stats=stats)
    deduped = flatten_source_batches(source_batches)
    active = filter_seen_items(deduped, state_store)
    stats.update(
        {
            "deduped": len(deduped),
            "seen_suppressed": len(deduped) - len(active),
            "after_seen_filter": len(active),
        }
    )
    return active, stats


def _write_run_artifact(settings: Settings, digest: DailyDigest) -> None:
    settings.delivery.run_log_path.parent.mkdir(parents=True, exist_ok=True)
    settings.delivery.run_log_path.write_text(
        json.dumps(digest.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def run_digest(settings: Settings, dry_run: bool = False, days_override: int | None = None) -> DailyDigest:
    now_local = datetime.now(ZoneInfo(settings.timezone))
    subject = f"{settings.delivery.subject_prefix} | {now_local:%Y-%m-%d}"
    state_store = create_state_store(settings)

    days_back = days_override or settings.pipeline.lookback_days
    candidates, stats = await _collect_candidates(
        settings,
        days_back,
        state_store,
        target_day=now_local.date(),
        paper_days_back=1,
    )
    reviewed_items, review_stats = await review_candidates(settings, candidates)
    stats.update(review_stats)

    digest = await assemble_digest(settings, reviewed_items, stats, subject=subject)
    await deliver_digest(settings, digest, dry_run=dry_run, state_store=state_store)

    return digest


async def run_backfill_digest(
    settings: Settings,
    target_date: date,
    dry_run: bool = False,
) -> DailyDigest:
    state_store = create_state_store(settings)
    now_local = datetime.now(ZoneInfo(settings.timezone)).date()
    day_gap = max(0, (now_local - target_date).days)
    days_back = max(settings.pipeline.lookback_days, day_gap + settings.pipeline.lookback_days)

    candidates, stats = await _collect_candidates(
        settings,
        days_back,
        state_store,
        target_day=target_date,
        paper_days_back=days_back,
    )
    candidates = [
        item
        for item in candidates
        if (_item_local_date(item, settings.timezone) or target_date) <= target_date
    ]
    stats["backfill_target_candidates"] = len(candidates)
    reviewed_items, review_stats = await review_candidates(settings, candidates)
    stats.update(review_stats)

    subject = f"{settings.delivery.subject_prefix} | {target_date:%Y-%m-%d} | 补发"
    digest = await assemble_digest(settings, reviewed_items, stats, subject=subject)
    await deliver_digest(settings, digest, dry_run=dry_run, state_store=state_store)
    return digest
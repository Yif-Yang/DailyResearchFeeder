from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("config.yaml")


@dataclass
class LLMSettings:
    provider: str
    api_key: str
    base_url: str
    azure_endpoint: str
    azure_api_version: str
    azure_deployment: str
    model: str
    reasoning_effort: str
    scan_model: str
    scan_reasoning_effort: str
    enable_fast_mode: bool
    fast_mode_threshold: int
    fast_mode_shortlist_size: int
    timeout_seconds: int
    copilot_command: str


@dataclass
class EmailSettings:
    provider: str
    resend_api_key: str
    to_email: str
    from_email: str
    azure_cli_command: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_starttls: bool


@dataclass
class PipelineSettings:
    lookback_days: int
    llm_batch_size: int
    max_review_items: int
    score_threshold: float
    max_papers: int
    max_news: int
    max_watchlist: int


@dataclass
class SourceSettings:
    arxiv_enabled: bool
    arxiv_max_results: int
    huggingface_enabled: bool
    feeds_enabled: bool
    feed_max_entries_per_feed: int
    internet_insights_enabled: bool = True
    internet_insights_hackernews_enabled: bool = True
    internet_insights_hackernews_front_page_size: int = 30
    internet_insights_hackernews_min_points: int = 40
    internet_insights_github_enabled: bool = True
    internet_insights_github_queries: list[str] = field(default_factory=lambda: [
        "agent LLM",
        "tool use reinforcement learning",
        "presentation agent",
    ])
    internet_insights_github_max_per_query: int = 6
    internet_insights_github_min_stars: int = 5


@dataclass
class DeliverySettings:
    subject_prefix: str
    preview_path: Path
    run_log_path: Path
    status_path: Path


@dataclass
class ScheduleSettings:
    start_hour: int
    send_hour: int
    paper_check_offsets_minutes: list[int]
    paper_poll_interval_minutes: int
    weekend_fallback_days: int
    review_poll_seconds: int


@dataclass
class StateSettings:
    seen_items_path: Path
    seen_ttl_days: int
    max_items: int


@dataclass
class Settings:
    root_dir: Path
    timezone: str
    language: str
    keywords: list[str]
    exclude_keywords: list[str]
    research_interests: str
    arxiv_categories: list[str]
    feeds: dict[str, list[dict[str, Any]]]
    llm: LLMSettings
    email: EmailSettings
    pipeline: PipelineSettings
    sources: SourceSettings
    delivery: DeliverySettings
    state: StateSettings
    schedule: ScheduleSettings


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    return content or {}


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _resolve_path(root_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (root_dir / path).resolve()


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _env_bool(*names: str, default: bool = False) -> bool:
    value = _env(*names, default="")
    if not value:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _int_list(raw_value: Any, default: list[int]) -> list[int]:
    if raw_value is None:
        return default
    if isinstance(raw_value, list):
        values = [int(value) for value in raw_value]
        return values or default
    if isinstance(raw_value, str):
        values = [segment.strip() for segment in raw_value.split(",") if segment.strip()]
        return [int(value) for value in values] or default
    return default


def load_settings(config_path: str | Path = DEFAULT_CONFIG_PATH) -> Settings:
    config_path = Path(config_path).resolve()
    root_dir = config_path.parent
    raw = _read_yaml(config_path)

    user_files = raw.get("user_files", {})
    llm_raw = raw.get("llm") or raw.get("openai", {})
    pipeline_raw = raw.get("pipeline", {})
    sources_raw = raw.get("sources", {})
    delivery_raw = raw.get("delivery", {})
    email_raw = raw.get("email", {})
    state_raw = raw.get("state", {})
    schedule_raw = raw.get("schedule", {})

    keywords = _read_lines(_resolve_path(root_dir, user_files.get("keywords_path", "user/keywords.txt")))
    exclude_keywords = _read_lines(
        _resolve_path(root_dir, user_files.get("exclude_keywords_path", "user/exclude_keywords.txt"))
    )
    research_interests = _read_text(
        _resolve_path(root_dir, user_files.get("research_interests_path", "user/research_interests.txt"))
    )
    arxiv_categories = _read_lines(
        _resolve_path(root_dir, user_files.get("arxiv_categories_path", "user/arxiv_categories.txt"))
    )
    feeds = _read_yaml(_resolve_path(root_dir, user_files.get("feeds_path", "user/feeds.yaml")))

    llm_provider = _env("LLM_PROVIDER", default=str(llm_raw.get("provider", "copilot_cli")))
    if llm_provider == "azure_openai":
        llm_api_key = _env("AZURE_OPENAI_API_KEY", "LLM_API_KEY")
    elif llm_provider == "openai":
        llm_api_key = _env("OPENAI_API_KEY", "LLM_API_KEY")
    else:
        llm_api_key = ""

    llm_settings = LLMSettings(
        provider=llm_provider,
        api_key=llm_api_key,
        base_url=_env(
            "OPENAI_BASE_URL",
            "LLM_BASE_URL",
            default=str(llm_raw.get("base_url", "https://api.openai.com/v1")),
        ),
        azure_endpoint=_env(
            "AZURE_OPENAI_ENDPOINT",
            default=str(llm_raw.get("azure_endpoint", "https://your-resource-name.openai.azure.com/")),
        ),
        azure_api_version=_env(
            "AZURE_OPENAI_API_VERSION",
            default=str(llm_raw.get("azure_api_version", "2024-12-01-preview")),
        ),
        azure_deployment=_env(
            "AZURE_OPENAI_DEPLOYMENT",
            default=str(llm_raw.get("azure_deployment", llm_raw.get("model", "gpt-5.4"))),
        ),
        model=_env("LLM_MODEL", "OPENAI_MODEL", default=str(llm_raw.get("model", "gpt-5.4"))),
        reasoning_effort=_env(
            "LLM_REASONING_EFFORT",
            "OPENAI_REASONING_EFFORT",
            default=str(llm_raw.get("reasoning_effort", "xhigh")),
        ),
        scan_model=_env("LLM_SCAN_MODEL", default=str(llm_raw.get("scan_model", "gpt-5.4-mini"))),
        scan_reasoning_effort=_env(
            "LLM_SCAN_REASONING_EFFORT",
            default=str(llm_raw.get("scan_reasoning_effort", "medium")),
        ),
        enable_fast_mode=_env_bool(
            "LLM_ENABLE_FAST_MODE",
            default=bool(llm_raw.get("enable_fast_mode", False)),
        ),
        fast_mode_threshold=int(
            _env(
                "LLM_FAST_MODE_THRESHOLD",
                default=str(llm_raw.get("fast_mode_threshold", 180)),
            )
        ),
        fast_mode_shortlist_size=int(
            _env(
                "LLM_FAST_MODE_SHORTLIST_SIZE",
                default=str(llm_raw.get("fast_mode_shortlist_size", pipeline_raw.get("max_review_items", 100))),
            )
        ),
        timeout_seconds=int(llm_raw.get("timeout_seconds", 240)),
        copilot_command=_env("COPILOT_COMMAND", default=str(llm_raw.get("copilot_command", "copilot"))),
    )

    email_provider = _env("EMAIL_PROVIDER", default=str(email_raw.get("provider", "gmail_smtp")))
    if email_provider == "gmail_smtp":
        smtp_username = _env("GMAIL_SMTP_USERNAME", "SMTP_USERNAME")
        smtp_password = _env("GMAIL_SMTP_PASSWORD", "SMTP_PASSWORD")
        smtp_host = _env("SMTP_HOST", default=str(email_raw.get("smtp_host", "smtp.gmail.com")))
        smtp_port = int(_env("SMTP_PORT", default=str(email_raw.get("smtp_port", 587))))
        smtp_use_starttls = _env(
            "SMTP_USE_STARTTLS",
            default=str(email_raw.get("smtp_use_starttls", True)),
        ).strip().lower() not in {"0", "false", "no", "off"}
        default_from_email = smtp_username or str(email_raw.get("from_email", ""))
    else:
        smtp_username = _env("SMTP_USERNAME", "GMAIL_SMTP_USERNAME")
        smtp_password = _env("SMTP_PASSWORD", "GMAIL_SMTP_PASSWORD")
        smtp_host = _env("SMTP_HOST", default=str(email_raw.get("smtp_host", "smtp.gmail.com")))
        smtp_port = int(_env("SMTP_PORT", default=str(email_raw.get("smtp_port", 587))))
        smtp_use_starttls = _env(
            "SMTP_USE_STARTTLS",
            default=str(email_raw.get("smtp_use_starttls", True)),
        ).strip().lower() not in {"0", "false", "no", "off"}
        default_from_email = str(email_raw.get("from_email", ""))

    email_settings = EmailSettings(
        provider=email_provider,
        resend_api_key=_env("RESEND_API_KEY"),
        to_email=_env("EMAIL_TO", default=str(email_raw.get("to_email", ""))),
        from_email=_env("EMAIL_FROM", default=default_from_email),
        azure_cli_command=_env("AZURE_CLI_COMMAND", default=str(email_raw.get("azure_cli_command", "az"))),
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_use_starttls=smtp_use_starttls,
    )

    pipeline_settings = PipelineSettings(
        lookback_days=int(_env("PIPELINE_LOOKBACK_DAYS", "DAILY_FEEDER_DAYS", default=str(pipeline_raw.get("lookback_days", 2)))),
        llm_batch_size=int(_env("PIPELINE_LLM_BATCH_SIZE", "DAILY_FEEDER_LLM_BATCH_SIZE", default=str(pipeline_raw.get("llm_batch_size", 8)))),
        max_review_items=int(_env("PIPELINE_MAX_REVIEW_ITEMS", "DAILY_FEEDER_MAX_REVIEW_ITEMS", default=str(pipeline_raw.get("max_review_items", 80)))),
        score_threshold=float(_env("PIPELINE_SCORE_THRESHOLD", default=str(pipeline_raw.get("score_threshold", 7.0)))),
        max_papers=int(_env("PIPELINE_MAX_PAPERS", default=str(pipeline_raw.get("max_papers", 8)))),
        max_news=int(_env("PIPELINE_MAX_NEWS", default=str(pipeline_raw.get("max_news", 6)))),
        max_watchlist=int(_env("PIPELINE_MAX_WATCHLIST", default=str(pipeline_raw.get("max_watchlist", 6)))),
    )

    arxiv_raw = sources_raw.get("arxiv", {})
    hf_raw = sources_raw.get("huggingface_daily", {})
    feeds_raw = sources_raw.get("feeds", {})
    internet_raw = sources_raw.get("internet_insights", {}) or {}
    internet_hn_raw = internet_raw.get("hackernews", {}) if isinstance(internet_raw, dict) else {}
    internet_github_raw = internet_raw.get("github", {}) if isinstance(internet_raw, dict) else {}
    raw_queries = internet_github_raw.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        raw_queries = [
            "agent LLM",
            "tool use reinforcement learning",
            "presentation agent",
        ]
    source_settings = SourceSettings(
        arxiv_enabled=bool(arxiv_raw.get("enabled", True)),
        arxiv_max_results=int(arxiv_raw.get("max_results", 160)),
        huggingface_enabled=bool(hf_raw.get("enabled", True)),
        feeds_enabled=bool(feeds_raw.get("enabled", True)),
        feed_max_entries_per_feed=int(feeds_raw.get("max_entries_per_feed", 6)),
        internet_insights_enabled=bool(internet_raw.get("enabled", True)) if isinstance(internet_raw, dict) else True,
        internet_insights_hackernews_enabled=bool(internet_hn_raw.get("enabled", True)),
        internet_insights_hackernews_front_page_size=int(internet_hn_raw.get("front_page_size", 30)),
        internet_insights_hackernews_min_points=int(internet_hn_raw.get("min_points", 40)),
        internet_insights_github_enabled=bool(internet_github_raw.get("enabled", True)),
        internet_insights_github_queries=[str(q).strip() for q in raw_queries if str(q).strip()],
        internet_insights_github_max_per_query=int(internet_github_raw.get("max_per_query", 6)),
        internet_insights_github_min_stars=int(internet_github_raw.get("min_stars", 5)),
    )

    delivery_settings = DeliverySettings(
        subject_prefix=str(delivery_raw.get("subject_prefix", "Daily Research Feeder")),
        preview_path=_resolve_path(root_dir, str(delivery_raw.get("preview_path", "artifacts/report_preview.html"))),
        run_log_path=_resolve_path(root_dir, str(delivery_raw.get("run_log_path", "artifacts/latest_run.json"))),
        status_path=_resolve_path(root_dir, str(delivery_raw.get("status_path", "artifacts/daily_status.json"))),
    )

    state_settings = StateSettings(
        seen_items_path=_resolve_path(root_dir, str(state_raw.get("seen_items_path", "state/seen_items.json"))),
        seen_ttl_days=int(state_raw.get("seen_ttl_days", 14)),
        max_items=int(state_raw.get("max_items", 4000)),
    )

    schedule_settings = ScheduleSettings(
        start_hour=int(schedule_raw.get("start_hour", 8)),
        send_hour=int(schedule_raw.get("send_hour", 10)),
        paper_check_offsets_minutes=_int_list(schedule_raw.get("paper_check_offsets_minutes"), [0, 30, 60]),
        paper_poll_interval_minutes=int(schedule_raw.get("paper_poll_interval_minutes", 15)),
        weekend_fallback_days=int(schedule_raw.get("weekend_fallback_days", 7)),
        review_poll_seconds=int(schedule_raw.get("review_poll_seconds", 30)),
    )

    return Settings(
        root_dir=root_dir,
        timezone=str(raw.get("timezone", "Asia/Shanghai")),
        language=str(raw.get("language", "zh-CN")),
        keywords=keywords,
        exclude_keywords=exclude_keywords,
        research_interests=research_interests,
        arxiv_categories=arxiv_categories,
        feeds={key: value or [] for key, value in feeds.items()},
        llm=llm_settings,
        email=email_settings,
        pipeline=pipeline_settings,
        sources=source_settings,
        delivery=delivery_settings,
        state=state_settings,
        schedule=schedule_settings,
    )
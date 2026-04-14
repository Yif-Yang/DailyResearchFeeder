from __future__ import annotations

import asyncio
import html
import json
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dailyresearchfeeder.config import Settings
from dailyresearchfeeder.emailer import FileEmailer
from dailyresearchfeeder.models import CandidateItem, DailyDigest
from dailyresearchfeeder.pipeline import (
    NEWS_SOURCE_KEYS,
    PAPER_SOURCE_KEYS,
    SOURCE_KEY_ARXIV,
    SOURCE_KEY_HUGGINGFACE,
    assemble_digest,
    build_emailer,
    collect_source_batches,
    create_state_store,
    deliver_digest,
    filter_seen_items,
    filter_paper_source_batches_for_target_day,
    flatten_source_batches,
    recompute_fetch_stats,
    review_candidates,
)
from dailyresearchfeeder.state import SeenStateStore


@dataclass
class PreparedChannel:
    reviewed_items: list[CandidateItem]
    stats: dict[str, int]


def _now_local(settings: Settings) -> datetime:
    return datetime.now(ZoneInfo(settings.timezone))


def _local_anchor(settings: Settings, target_day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(target_day.year, target_day.month, target_day.day, hour, minute, tzinfo=ZoneInfo(settings.timezone))


def _local_date(value: datetime | None, timezone_name: str) -> date | None:
    if value is None:
        return None
    return value.astimezone(ZoneInfo(timezone_name)).date()


def _merge_stats(*stats_groups: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for stats in stats_groups:
        for key, value in stats.items():
            merged[key] = merged.get(key, 0) + int(value)
    return merged


def _source_status(
    source_items: list[CandidateItem],
    state_store: SeenStateStore,
    timezone_name: str,
    target_day: date,
) -> dict[str, Any]:
    target_day_items = [item for item in source_items if _local_date(item.published_at, timezone_name) == target_day]
    unseen_items = filter_seen_items(target_day_items, state_store)
    local_dates = [local_day for local_day in (_local_date(item.published_at, timezone_name) for item in source_items) if local_day]
    latest_local_day = max(local_dates) if local_dates else None
    return {
        "fetched": len(target_day_items),
        "unseen": len(unseen_items),
        "latest_local_day": latest_local_day.isoformat() if latest_local_day else "",
        "fresh": latest_local_day == target_day,
    }


def summarize_paper_source_status(
    paper_batches: dict[str, list[CandidateItem]],
    state_store: SeenStateStore,
    timezone_name: str,
    target_day: date,
) -> dict[str, dict[str, Any]]:
    return {
        SOURCE_KEY_ARXIV: _source_status(paper_batches.get(SOURCE_KEY_ARXIV, []), state_store, timezone_name, target_day),
        SOURCE_KEY_HUGGINGFACE: _source_status(
            paper_batches.get(SOURCE_KEY_HUGGINGFACE, []),
            state_store,
            timezone_name,
            target_day,
        ),
    }


def papers_fresh_enough(source_status: dict[str, dict[str, Any]]) -> bool:
    arxiv_status = source_status.get(SOURCE_KEY_ARXIV, {})
    hf_status = source_status.get(SOURCE_KEY_HUGGINGFACE, {})
    return bool(arxiv_status.get("fresh")) and bool(hf_status.get("fresh"))


def estimate_remaining_minutes(
    now_local: datetime,
    next_check_at: datetime | None,
    news_done: bool,
    paper_review_started: bool,
    settings: Settings,
) -> int:
    eta_minutes = 10
    if not news_done:
        eta_minutes += 20
    if not paper_review_started:
        if next_check_at and next_check_at > now_local:
            eta_minutes += max(5, int((next_check_at - now_local).total_seconds() // 60))
        else:
            eta_minutes += settings.schedule.paper_poll_interval_minutes
        eta_minutes += 20
    else:
        eta_minutes += 20
    return eta_minutes


def _status_snapshot(
    *,
    target_day: date,
    stage: str,
    started_at: datetime,
    now_local: datetime,
    send_at: datetime,
    next_check_at: datetime | None,
    source_status: dict[str, dict[str, Any]],
    news_stats: dict[str, int],
    paper_stats: dict[str, int],
    reminder_sent: bool,
    paper_mode: str,
    eta_minutes: int,
) -> dict[str, Any]:
    return {
        "target_day": target_day.isoformat(),
        "stage": stage,
        "started_at": started_at.isoformat(),
        "updated_at": now_local.isoformat(),
        "send_at": send_at.isoformat(),
        "next_paper_check_at": next_check_at.isoformat() if next_check_at else "",
        "paper_source_status": source_status,
        "news_stats": news_stats,
        "paper_stats": paper_stats,
        "reminder_sent": reminder_sent,
        "paper_mode": paper_mode,
        "eta_minutes": eta_minutes,
    }


def _write_status(settings: Settings, payload: dict[str, Any]) -> None:
    settings.delivery.status_path.parent.mkdir(parents=True, exist_ok=True)
    settings.delivery.status_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def _sleep_until(target_time: datetime) -> None:
    delay = (target_time - datetime.now(target_time.tzinfo)).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)


async def _prepare_channel_from_sources(
    settings: Settings,
    state_store: SeenStateStore,
    *,
    source_keys: tuple[str, ...],
    days_back: int,
) -> PreparedChannel:
    source_batches, fetch_stats = await collect_source_batches(settings, days_back, source_keys=source_keys)
    deduped = flatten_source_batches(source_batches, source_keys)
    active = filter_seen_items(deduped, state_store)
    fetch_stats.update(
        {
            "deduped": len(deduped),
            "seen_suppressed": len(deduped) - len(active),
            "after_seen_filter": len(active),
        }
    )
    reviewed_items, review_stats = await review_candidates(settings, active)
    fetch_stats.update(review_stats)
    return PreparedChannel(reviewed_items=reviewed_items, stats=fetch_stats)


async def _prepare_channel_from_items(
    settings: Settings,
    state_store: SeenStateStore,
    *,
    items: list[CandidateItem],
    base_stats: dict[str, int],
) -> PreparedChannel:
    deduped = flatten_source_batches({"items": items}, source_keys=("items",))
    active = filter_seen_items(deduped, state_store)
    stats = dict(base_stats)
    stats.update(
        {
            "deduped": len(deduped),
            "seen_suppressed": len(deduped) - len(active),
            "after_seen_filter": len(active),
        }
    )
    reviewed_items, review_stats = await review_candidates(settings, active)
    stats.update(review_stats)
    return PreparedChannel(reviewed_items=reviewed_items, stats=stats)


def _render_progress_email(
    settings: Settings,
    *,
    target_day: date,
    eta_minutes: int,
    next_check_at: datetime | None,
    source_status: dict[str, dict[str, Any]],
    news_preview: list[CandidateItem],
    paper_mode: str,
) -> str:
    next_check_label = next_check_at.strftime("%H:%M") if next_check_at else "等待当前评审批次完成"
    news_items = "".join(
        f"<li><a href=\"{html.escape(item.url)}\">{html.escape(item.title)}</a>"
        f" <span style=\"color:#5b6b7b\">({html.escape(item.source_name)})</span></li>"
        for item in news_preview[:5]
    ) or "<li>新闻整理仍在进行中。</li>"

    source_rows = []
    for label, key in (("arXiv", SOURCE_KEY_ARXIV), ("Hugging Face Daily Papers", SOURCE_KEY_HUGGINGFACE)):
        status = source_status.get(key, {})
        source_rows.append(
            "<tr>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #d8e2ec;\">{html.escape(label)}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #d8e2ec;\">{'已就绪' if status.get('fresh') else '等待刷新'}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #d8e2ec;\">{int(status.get('unseen', 0))}</td>"
            f"<td style=\"padding:10px 12px;border-bottom:1px solid #d8e2ec;\">{html.escape(status.get('latest_local_day', '') or '-')}</td>"
            "</tr>"
        )

    paper_mode_label = {
        "daily_refresh": "等待当日论文源刷新",
        "no_daily_papers": "当天论文源暂无新论文，将按新闻与动态先发送",
    }.get(paper_mode, paper_mode)

    return f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{html.escape(settings.delivery.subject_prefix)} 进度提醒</title>
</head>
<body style=\"margin:0;padding:24px;background:#f3f7fb;color:#16324a;font-family:'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;\">
  <div style=\"max-width:860px;margin:0 auto;background:#ffffff;border:1px solid #d8e2ec;border-radius:24px;overflow:hidden;box-shadow:0 14px 40px rgba(15,23,42,0.08);\">
    <div style=\"padding:28px 28px 20px;background:linear-gradient(135deg,#ebf6ff 0%,#f9fcff 56%,#effcf6 100%);border-bottom:1px solid #d8e2ec;\">
      <h1 style=\"margin:0;font-size:30px;color:#0c5a87;\">{html.escape(settings.delivery.subject_prefix)} 进度提醒</h1>
      <p style=\"margin:12px 0 0;color:#5b6b7b;font-size:16px;\">{target_day:%Y-%m-%d} 的正式日报还在处理中，预计还需要约 {eta_minutes} 分钟。</p>
    </div>
    <div style=\"padding:24px 28px;\">
      <div style=\"background:#f8fbfe;border:1px solid #d8e2ec;border-radius:18px;padding:18px 20px;\">
        <p style=\"margin:0 0 8px;font-size:17px;\"><strong>当前状态</strong></p>
        <p style=\"margin:0;color:#38546a;\">新闻部分已优先整理，论文部分目前为：{html.escape(paper_mode_label)}。下一次检查或可见结果时间：{html.escape(next_check_label)}。</p>
      </div>

      <h2 style=\"margin:24px 0 12px;font-size:22px;\">论文源刷新状态</h2>
      <table style=\"width:100%;border-collapse:collapse;border:1px solid #d8e2ec;border-radius:16px;overflow:hidden;\">
        <thead style=\"background:#eef5fb;\">
          <tr>
            <th style=\"padding:10px 12px;text-align:left;\">来源</th>
            <th style=\"padding:10px 12px;text-align:left;\">状态</th>
            <th style=\"padding:10px 12px;text-align:left;\">未推送条目</th>
            <th style=\"padding:10px 12px;text-align:left;\">最新本地日期</th>
          </tr>
        </thead>
        <tbody>{''.join(source_rows)}</tbody>
      </table>

      <h2 style=\"margin:24px 0 12px;font-size:22px;\">已整理好的新闻头条</h2>
      <ol style=\"margin:0;padding-left:22px;color:#16324a;line-height:1.8;\">{news_items}</ol>

      <p style=\"margin:24px 0 0;color:#5b6b7b;font-size:14px;\">正式邮件会在论文源刷新完成并整理完毕后自动补发。</p>
    </div>
  </div>
</body>
</html>
"""


async def _send_progress_email(
    settings: Settings,
    *,
    dry_run: bool,
    target_day: date,
    eta_minutes: int,
    next_check_at: datetime | None,
    source_status: dict[str, dict[str, Any]],
    news_preview: list[CandidateItem],
    paper_mode: str,
) -> None:
    subject = f"{settings.delivery.subject_prefix} | {target_day:%Y-%m-%d} | 10:00进度提醒"
    html_content = _render_progress_email(
        settings,
        target_day=target_day,
        eta_minutes=eta_minutes,
        next_check_at=next_check_at,
        source_status=source_status,
        news_preview=news_preview,
        paper_mode=paper_mode,
    )
    preview = FileEmailer(settings.delivery.preview_path)
    await preview.send(settings.email.to_email or "preview@example.com", subject, html_content)

    if dry_run:
        return
    if not settings.email.to_email:
        raise ValueError("EMAIL_TO is required when dry_run is false")
    emailer = build_emailer(settings)
    await emailer.send(settings.email.to_email, subject, html_content)


def _next_check_time(
    initial_checks: deque[datetime],
    now_local: datetime,
    settings: Settings,
) -> datetime:
    while initial_checks and initial_checks[0] <= now_local:
        initial_checks.popleft()
    if initial_checks:
        return initial_checks.popleft()
    return now_local + timedelta(minutes=settings.schedule.paper_poll_interval_minutes)


async def run_scheduled_day(
    settings: Settings,
    *,
    dry_run: bool = False,
    days_override: int | None = None,
) -> DailyDigest:
    days_back = days_override or settings.pipeline.lookback_days
    paper_days_back = 1
    initial_now = _now_local(settings)
    target_day = initial_now.date()
    start_at = _local_anchor(settings, target_day, settings.schedule.start_hour)
    send_at = _local_anchor(settings, target_day, settings.schedule.send_hour)
    if initial_now < start_at:
        await _sleep_until(start_at)

    started_at = _now_local(settings)
    state_store = create_state_store(settings)
    stage = "preparing_news"
    reminder_sent = False
    paper_mode = "daily_refresh"
    news_result: PreparedChannel | None = None
    paper_result: PreparedChannel | None = None
    source_status = summarize_paper_source_status({}, state_store, settings.timezone, target_day)
    next_check_at = started_at

    initial_checks = deque(
        _local_anchor(settings, target_day, settings.schedule.start_hour) + timedelta(minutes=offset)
        for offset in sorted(settings.schedule.paper_check_offsets_minutes)
    )
    while initial_checks and initial_checks[0] < started_at:
        initial_checks.popleft()

    news_task = asyncio.create_task(
        _prepare_channel_from_sources(
            settings,
            state_store,
            source_keys=NEWS_SOURCE_KEYS,
            days_back=days_back,
        )
    )
    paper_task: asyncio.Task[PreparedChannel] | None = None

    while True:
        now_local = _now_local(settings)

        if paper_task is None and next_check_at and now_local >= next_check_at:
            paper_batches, paper_fetch_stats = await collect_source_batches(
                settings,
                days_back,
                source_keys=PAPER_SOURCE_KEYS,
                paper_days_back=paper_days_back,
            )
            source_status = summarize_paper_source_status(paper_batches, state_store, settings.timezone, target_day)

            if papers_fresh_enough(source_status):
                stage = "reviewing_papers"
                target_day_batches = filter_paper_source_batches_for_target_day(paper_batches, settings.timezone, target_day)
                paper_fetch_stats = recompute_fetch_stats(
                    target_day_batches,
                    source_keys=PAPER_SOURCE_KEYS,
                    base_stats=paper_fetch_stats,
                )
                unseen_papers = filter_seen_items(flatten_source_batches(target_day_batches, PAPER_SOURCE_KEYS), state_store)
                paper_task = asyncio.create_task(
                    _prepare_channel_from_items(
                        settings,
                        state_store,
                        items=unseen_papers,
                        base_stats=paper_fetch_stats,
                    )
                )
                next_check_at = None
            else:
                stage = "waiting_paper_refresh"
                next_check_at = _next_check_time(initial_checks, now_local, settings)

        if news_result is None and news_task.done():
            news_result = await news_task
            if paper_task is None:
                stage = "waiting_paper_refresh"

        if paper_result is None and paper_task is not None and paper_task.done():
            paper_result = await paper_task
            if news_result is None:
                stage = "waiting_news_completion"
            else:
                stage = "ready_to_send"

        if (
            not reminder_sent
            and now_local >= send_at
            and target_day.weekday() >= 5
            and paper_task is None
            and paper_result is None
            and not papers_fresh_enough(source_status)
        ):
            paper_mode = "no_daily_papers"
            stage = "ready_without_papers"
            paper_result = PreparedChannel(
                reviewed_items=[],
                stats={
                    "fetched": 0,
                    "deduped": 0,
                    "seen_suppressed": 0,
                    "after_seen_filter": 0,
                    "keyword_hits": 0,
                    "review_candidates": 0,
                    "reviewed": 0,
                },
            )
            next_check_at = None

        if news_result is not None and paper_result is not None:
            digest_stats = _merge_stats(news_result.stats, paper_result.stats)
            if settings.llm.enable_fast_mode:
                digest_stats["fast_mode_enabled"] = 1
            digest = await assemble_digest(
                settings,
                news_result.reviewed_items + paper_result.reviewed_items,
                digest_stats,
                subject=f"{settings.delivery.subject_prefix} | {target_day:%Y-%m-%d}",
            )
            if not reminder_sent and _now_local(settings) < send_at:
                stage = "waiting_send_window"
                status_payload = _status_snapshot(
                    target_day=target_day,
                    stage=stage,
                    started_at=started_at,
                    now_local=_now_local(settings),
                    send_at=send_at,
                    next_check_at=next_check_at,
                    source_status=source_status,
                    news_stats=news_result.stats,
                    paper_stats=paper_result.stats,
                    reminder_sent=reminder_sent,
                    paper_mode=paper_mode,
                    eta_minutes=max(0, int((send_at - _now_local(settings)).total_seconds() // 60)),
                )
                _write_status(settings, status_payload)
                await _sleep_until(send_at)

            await deliver_digest(settings, digest, dry_run=dry_run, state_store=state_store)
            status_payload = _status_snapshot(
                target_day=target_day,
                stage="final_sent",
                started_at=started_at,
                now_local=_now_local(settings),
                send_at=send_at,
                next_check_at=None,
                source_status=source_status,
                news_stats=news_result.stats,
                paper_stats=paper_result.stats,
                reminder_sent=reminder_sent,
                paper_mode=paper_mode,
                eta_minutes=0,
            )
            _write_status(settings, status_payload)
            return digest

        eta_minutes = estimate_remaining_minutes(
            now_local,
            next_check_at,
            news_done=news_result is not None,
            paper_review_started=paper_task is not None,
            settings=settings,
        )

        status_payload = _status_snapshot(
            target_day=target_day,
            stage=stage,
            started_at=started_at,
            now_local=now_local,
            send_at=send_at,
            next_check_at=next_check_at,
            source_status=source_status,
            news_stats=news_result.stats if news_result else {},
            paper_stats=paper_result.stats if paper_result else {},
            reminder_sent=reminder_sent,
            paper_mode=paper_mode,
            eta_minutes=eta_minutes,
        )
        _write_status(settings, status_payload)

        if not reminder_sent and now_local >= send_at:
            await _send_progress_email(
                settings,
                dry_run=dry_run,
                target_day=target_day,
                eta_minutes=eta_minutes,
                next_check_at=next_check_at,
                source_status=source_status,
                news_preview=news_result.reviewed_items if news_result else [],
                paper_mode=paper_mode,
            )
            reminder_sent = True

        sleep_seconds = settings.schedule.review_poll_seconds
        if paper_task is None and next_check_at is not None:
            seconds_until_check = max(1, int((next_check_at - _now_local(settings)).total_seconds()))
            sleep_seconds = min(sleep_seconds, seconds_until_check)
        elif not reminder_sent:
            seconds_until_deadline = max(1, int((send_at - _now_local(settings)).total_seconds()))
            sleep_seconds = min(sleep_seconds, seconds_until_deadline)

        await asyncio.sleep(max(1, sleep_seconds))
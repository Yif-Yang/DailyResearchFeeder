from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from dailyresearchfeeder.models import CandidateItem, ItemKind
from dailyresearchfeeder.sources.base import BaseSource, SourceFetchError


HACKERNEWS_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
HEADERS = {
    "User-Agent": "DailyResearchFeeder/0.0.3 (+https://github.com/Yif-Yang/DailyResearchFeeder)",
    "Accept": "application/json",
}


@dataclass
class InternetInsightsConfig:
    hackernews_enabled: bool = True
    hackernews_front_page_size: int = 30
    hackernews_min_points: int = 40
    github_enabled: bool = True
    github_queries: list[str] = field(default_factory=list)
    github_max_per_query: int = 6
    github_min_stars: int = 5


class InternetInsightsSource(BaseSource):
    """Fetch broader "internet observation" items (HN front page, GitHub trending)
    that complement the existing paper and blog/news feeds.

    Inspired by Agent-Reach's idea of giving agents one-stop web reach; here we
    keep it dependency-free by calling public JSON endpoints directly.
    """

    def __init__(self, config: InternetInsightsConfig | None = None) -> None:
        self.config = config or InternetInsightsConfig()

    async def fetch(self, days_back: int = 2) -> list[CandidateItem]:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days_back))

        items: list[CandidateItem] = []
        errors: list[str] = []

        async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
            if self.config.hackernews_enabled:
                try:
                    items.extend(await self._fetch_hackernews(session, cutoff))
                except Exception as exc:
                    errors.append(f"hackernews: {exc}")

            if self.config.github_enabled and self.config.github_queries:
                try:
                    items.extend(await self._fetch_github(session, cutoff))
                except Exception as exc:
                    errors.append(f"github: {exc}")

        if not items and errors:
            raise SourceFetchError("internet_insights", "; ".join(errors[-3:]))

        # Dedupe by URL within this source before handing off to the pipeline.
        seen: set[str] = set()
        unique_items: list[CandidateItem] = []
        for item in items:
            key = item.url.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique_items.append(item)
        return unique_items

    async def _fetch_hackernews(self, session: Any, cutoff: datetime) -> list[CandidateItem]:
        params = {
            "tags": "front_page",
            "hitsPerPage": max(1, self.config.hackernews_front_page_size),
        }
        async with session.get(HACKERNEWS_SEARCH_URL, params=params) as response:
            if response.status != 200:
                raise SourceFetchError(
                    "internet_insights", f"HN HTTP {response.status}"
                )
            payload = await response.json()

        items: list[CandidateItem] = []
        for hit in payload.get("hits", []) or []:
            url = str(hit.get("url") or "").strip()
            title = str(hit.get("title") or "").strip()
            story_id = str(hit.get("objectID") or hit.get("story_id") or "").strip()
            if not title or not story_id:
                continue
            story_url = f"https://news.ycombinator.com/item?id={story_id}"
            points = int(hit.get("points") or 0)
            comments = int(hit.get("num_comments") or 0)
            if points < self.config.hackernews_min_points:
                continue

            published_at = _parse_timestamp(hit.get("created_at"))
            if published_at and published_at < cutoff:
                continue

            external_url = url or story_url
            summary = (
                f"Hacker News 首页热度 {points} 赞 / {comments} 条评论。"
                f" 讨论入口：{story_url}"
            )
            if url:
                summary = f"原文链接：{url} | {summary}"

            items.append(
                CandidateItem(
                    title=title,
                    summary=summary,
                    url=external_url,
                    source_name="Hacker News Front Page",
                    kind=ItemKind.BLOG,
                    source_group="internet_insights",
                    published_at=published_at,
                    authors=[str(hit.get("author") or "").strip() or "hackernews"],
                    raw_tags=["internet_insights", "hackernews", *(hit.get("_tags") or [])],
                    debug_payload={
                        "points": points,
                        "num_comments": comments,
                        "hn_item": story_url,
                    },
                )
            )
        return items

    async def _fetch_github(self, session: Any, cutoff: datetime) -> list[CandidateItem]:
        lookback_date = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
        items: list[CandidateItem] = []

        for query in self.config.github_queries:
            q = f"{query} created:>={lookback_date} stars:>={self.config.github_min_stars}"
            params = {
                "q": q,
                "sort": "stars",
                "order": "desc",
                "per_page": max(1, self.config.github_max_per_query),
            }
            try:
                async with session.get(GITHUB_SEARCH_URL, params=params) as response:
                    if response.status == 403:
                        # Rate-limited (unauthenticated has 10 req/min). Stop early; what we
                        # already have is still useful.
                        break
                    if response.status != 200:
                        continue
                    payload = await response.json()
            except Exception:
                continue

            for repo in payload.get("items", []) or []:
                title = str(repo.get("full_name") or "").strip()
                html_url = str(repo.get("html_url") or "").strip()
                if not title or not html_url:
                    continue
                description = str(repo.get("description") or "").strip()
                stars = int(repo.get("stargazers_count") or 0)
                language = str(repo.get("language") or "").strip()
                published_at = _parse_timestamp(repo.get("created_at"))
                if published_at and published_at < cutoff - timedelta(days=7):
                    # The search window is 7d; still skip anything older than that.
                    continue

                summary = (
                    f"GitHub 新热门仓库（{query}）: {description or '无描述'}"
                    f" · ⭐{stars}"
                )
                if language:
                    summary += f" · 语言 {language}"

                items.append(
                    CandidateItem(
                        title=f"GitHub 热门 · {title}",
                        summary=summary,
                        url=html_url,
                        source_name="GitHub Trending",
                        kind=ItemKind.RELEASE,
                        source_group="internet_insights",
                        published_at=published_at,
                        authors=[str((repo.get("owner") or {}).get("login") or "")],
                        raw_tags=[
                            "internet_insights",
                            "github_trending",
                            f"query:{query}",
                            *(
                                [f"lang:{language.lower()}"]
                                if language
                                else []
                            ),
                        ],
                        debug_payload={
                            "stars": stars,
                            "query": query,
                            "language": language,
                        },
                    )
                )

            # Gentle pacing between queries to stay under the 10/min anonymous cap.
            await asyncio.sleep(0.5)

        return items


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

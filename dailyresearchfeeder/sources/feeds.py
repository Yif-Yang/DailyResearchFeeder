from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
import feedparser

from dailyresearchfeeder.models import CandidateItem, ItemKind
from dailyresearchfeeder.sources.base import BaseSource


class FeedSource(BaseSource):
    def __init__(self, feeds_by_group: dict[str, list[dict[str, Any]]]):
        self.feeds_by_group = feeds_by_group

    async def fetch(self, days_back: int = 2, max_entries_per_feed: int = 6) -> list[CandidateItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        tasks = []
        for group_name, feed_configs in self.feeds_by_group.items():
            for feed_config in feed_configs:
                tasks.append(self._fetch_feed(group_name, feed_config, cutoff, max_entries_per_feed))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[CandidateItem] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            items.extend(result)
        return items

    async def _fetch_feed(
        self,
        group_name: str,
        feed_config: dict[str, Any],
        cutoff: datetime,
        max_entries_per_feed: int,
    ) -> list[CandidateItem]:
        import aiohttp

        feed_url = str(feed_config.get("url", "")).strip()
        feed_name = str(feed_config.get("name", group_name)).strip() or group_name
        if not feed_url:
            return []

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
            "Accept-Encoding": "identity",
        }
        timeout = aiohttp.ClientTimeout(total=45, connect=15, sock_read=30)

        try:
            async with aiohttp.ClientSession(timeout=timeout, trust_env=True, headers=headers) as session:
                async with session.get(feed_url) as response:
                    if response.status != 200:
                        return []
                    content = await response.text()
        except Exception:
            return []

        parsed = feedparser.parse(content)
        if parsed.bozo and not parsed.entries:
            return []

        kind = ItemKind.from_value(str(feed_config.get("kind", "blog")))
        items: list[CandidateItem] = []
        for entry in parsed.entries[:max_entries_per_feed]:
            published_at = self._parse_entry_datetime(entry)
            if published_at and published_at < cutoff:
                continue

            title = self._clean_text(getattr(entry, "title", ""))
            summary = self._extract_summary(entry)
            url = str(getattr(entry, "link", "")).strip()
            author = self._extract_author(entry)
            if not title or not url:
                continue

            raw_tags = []
            for tag in getattr(entry, "tags", []) or []:
                term = tag.get("term") if isinstance(tag, dict) else getattr(tag, "term", "")
                if term:
                    raw_tags.append(str(term))

            items.append(
                CandidateItem(
                    title=title,
                    summary=summary,
                    url=url,
                    source_name=feed_name,
                    kind=kind,
                    source_group=group_name,
                    published_at=published_at,
                    authors=[author] if author else [],
                    raw_tags=raw_tags,
                )
            )

        return items

    @staticmethod
    def _parse_entry_datetime(entry: Any) -> datetime | None:
        for attribute in ("published", "updated", "created"):
            value = getattr(entry, attribute, None)
            if value:
                try:
                    parsed = parsedate_to_datetime(value)
                except (TypeError, ValueError, IndexError):
                    continue
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)

        for attribute in ("published_parsed", "updated_parsed"):
            value = getattr(entry, attribute, None)
            if value:
                return datetime(*value[:6], tzinfo=timezone.utc)
        return None

    @staticmethod
    def _extract_summary(entry: Any) -> str:
        for attribute in ("summary", "description"):
            value = getattr(entry, attribute, None)
            if value:
                return FeedSource._clean_text(str(value))[:1800]

        content = getattr(entry, "content", None)
        if content:
            first = content[0]
            raw_value = first.get("value", "") if isinstance(first, dict) else getattr(first, "value", "")
            return FeedSource._clean_text(str(raw_value))[:1800]
        return ""

    @staticmethod
    def _extract_author(entry: Any) -> str:
        author = getattr(entry, "author", None)
        if author:
            return str(author).strip()

        authors = getattr(entry, "authors", None)
        if authors:
            first = authors[0]
            if isinstance(first, dict):
                return str(first.get("name", "")).strip()
            return str(getattr(first, "name", "")).strip()
        return ""

    @staticmethod
    def _clean_text(value: str) -> str:
        without_tags = re.sub(r"<[^>]+>", " ", value or "")
        return re.sub(r"\s+", " ", without_tags).strip()
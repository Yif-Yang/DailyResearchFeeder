from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from dailyresearchfeeder.models import CandidateItem, ItemKind
from dailyresearchfeeder.sources.base import BaseSource, SourceFetchError


class HuggingFaceDailySource(BaseSource):
    API_URLS = [
        "https://huggingface.co/api/daily_papers",
        "https://hf-mirror.com/api/daily_papers",
    ]
    HEADERS = {
        "User-Agent": "DailyResearchFeeder/0.0.1 (+https://github.com/Yif-Yang/DailyResearchFeeder)"
    }

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @classmethod
    def _effective_published_at(cls, paper: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
        daily_listed_at = cls._parse_timestamp(paper.get("submittedOnDailyAt"))
        original_published_at = cls._parse_timestamp(paper.get("publishedAt"))
        return daily_listed_at or original_published_at, original_published_at

    async def fetch(self, days_back: int = 2) -> list[CandidateItem]:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
        data = None
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        errors: list[str] = []
        async with aiohttp.ClientSession(timeout=timeout, headers=self.HEADERS) as session:
            for url in self.API_URLS:
                for attempt in range(3):
                    try:
                        async with session.get(url) as response:
                            if response.status != 200:
                                errors.append(f"{url} returned HTTP {response.status}")
                            else:
                                data = await response.json()
                                break
                    except Exception as exc:
                        errors.append(f"{url} attempt {attempt + 1} failed: {exc}")

                    if data is not None:
                        break
                    if attempt < 2:
                        await asyncio.sleep(2)

                if data is not None:
                    break

        if data is None:
            detail = "; ".join(errors[-3:]) if errors else "no daily paper data returned"
            raise SourceFetchError("huggingface_daily", detail)
        if not isinstance(data, list):
            raise SourceFetchError("huggingface_daily", f"unexpected payload type: {type(data).__name__}")

        items: list[CandidateItem] = []
        for record in data:
            paper = record.get("paper", {})
            paper_id = str(paper.get("id", "")).strip()
            title = str(paper.get("title", "")).strip()
            summary = str(paper.get("summary", "") or "").strip()
            if not title:
                continue

            published_at, original_published_at = self._effective_published_at(paper)

            if published_at and published_at < cutoff:
                continue

            items.append(
                CandidateItem(
                    title=title,
                    summary=summary,
                    url=f"https://huggingface.co/papers/{paper_id}" if paper_id else "https://huggingface.co/papers",
                    source_name="Hugging Face Daily Papers",
                    kind=ItemKind.PAPER,
                    source_group="huggingface_daily",
                    published_at=published_at,
                    authors=[author.get("name", "") for author in paper.get("authors", []) if author.get("name")],
                    raw_tags=["huggingface_daily"],
                    debug_payload={
                        "original_published_at": original_published_at.isoformat() if original_published_at else None,
                        "submitted_on_daily_at": paper.get("submittedOnDailyAt"),
                    },
                )
            )

        return items
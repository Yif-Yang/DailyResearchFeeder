from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aiohttp

from dailyresearchfeeder.models import CandidateItem, ItemKind
from dailyresearchfeeder.sources.base import BaseSource


class HuggingFaceDailySource(BaseSource):
    API_URLS = [
        "https://huggingface.co/api/daily_papers",
        "https://hf-mirror.com/api/daily_papers",
    ]

    async def fetch(self, days_back: int = 2) -> list[CandidateItem]:
        timeout = aiohttp.ClientTimeout(total=30)
        data = None
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        for url in self.API_URLS:
            try:
                async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            continue
                        data = await response.json()
                        break
            except Exception:
                continue

        if not data:
            return []

        items: list[CandidateItem] = []
        for record in data:
            paper = record.get("paper", {})
            paper_id = str(paper.get("id", "")).strip()
            title = str(paper.get("title", "")).strip()
            summary = str(paper.get("summary", "") or "").strip()
            if not title:
                continue

            published_at = None
            published_raw = paper.get("publishedAt")
            if published_raw:
                try:
                    published_at = datetime.fromisoformat(str(published_raw).replace("Z", "+00:00"))
                except ValueError:
                    published_at = None

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
                )
            )

        return items
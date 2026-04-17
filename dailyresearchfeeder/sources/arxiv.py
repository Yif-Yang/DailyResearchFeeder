from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from dailyresearchfeeder.models import CandidateItem, ItemKind
from dailyresearchfeeder.sources.base import BaseSource, SourceFetchError


class ArxivSource(BaseSource):
    BASE_URL = "http://export.arxiv.org/api/query"
    HEADERS = {
        "User-Agent": "DailyResearchFeeder/0.0.1 (+https://github.com/Yif-Yang/DailyResearchFeeder)"
    }

    def __init__(self, categories: list[str]):
        self.categories = categories

    async def fetch(self, days_back: int = 2, max_results: int = 160) -> list[CandidateItem]:
        import aiohttp

        if not self.categories:
            return []
        timeout = aiohttp.ClientTimeout(total=120, connect=30, sock_read=90)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        batch_size = max(1, max_results)
        start = 0
        items: list[CandidateItem] = []

        async with aiohttp.ClientSession(timeout=timeout, headers=self.HEADERS) as session:
            while True:
                params = {
                    "search_query": " OR ".join(f"cat:{category}" for category in self.categories),
                    "start": start,
                    "max_results": batch_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
                xml_content = ""

                for attempt in range(3):
                    try:
                        async with session.get(self.BASE_URL, params=params) as response:
                            if response.status != 200:
                                if attempt == 2:
                                    if items:
                                        return items
                                    raise SourceFetchError("arxiv", f"HTTP {response.status} for start={start}")
                                await asyncio.sleep(3)
                                continue
                            xml_content = await response.text()
                            break
                    except Exception as exc:
                        if attempt == 2:
                            if items:
                                return items
                            raise SourceFetchError("arxiv", f"request failed for start={start}: {exc}") from exc
                        await asyncio.sleep(3)

                if not xml_content:
                    break

                try:
                    root = ET.fromstring(xml_content)
                except ET.ParseError as exc:
                    if items:
                        return items
                    raise SourceFetchError("arxiv", f"invalid XML response for start={start}: {exc}") from exc
                entries = root.findall("atom:entry", ns)
                if not entries:
                    break

                reached_cutoff = False

                for entry in entries:
                    published_raw = entry.findtext("atom:published", default="", namespaces=ns)
                    try:
                        published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                    except ValueError:
                        published_at = None

                    if published_at and published_at < cutoff:
                        reached_cutoff = True
                        break

                    title = entry.findtext("atom:title", default="", namespaces=ns).replace("\n", " ").strip()
                    summary = entry.findtext("atom:summary", default="", namespaces=ns).replace("\n", " ").strip()
                    url = entry.findtext("atom:id", default="", namespaces=ns).strip()
                    authors = [
                        author.findtext("atom:name", default="", namespaces=ns).strip()
                        for author in entry.findall("atom:author", ns)
                    ]
                    tags = [tag.get("term", "") for tag in entry.findall("atom:category", ns)]

                    if not title or not url:
                        continue

                    items.append(
                        CandidateItem(
                            title=title,
                            summary=summary,
                            url=url,
                            source_name="arXiv",
                            kind=ItemKind.PAPER,
                            source_group="arxiv",
                            published_at=published_at,
                            authors=[author for author in authors if author],
                            raw_tags=[tag for tag in tags if tag],
                        )
                    )

                if reached_cutoff or len(entries) < batch_size:
                    break

                start += batch_size

        return items
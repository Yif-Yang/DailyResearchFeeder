from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ItemKind(Enum):
    PAPER = "paper"
    BLOG = "blog"
    SOCIAL = "social"
    RELEASE = "release"

    @classmethod
    def from_value(cls, value: str) -> "ItemKind":
        normalized = (value or "blog").strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.BLOG


@dataclass
class CandidateItem:
    title: str
    summary: str
    url: str
    source_name: str
    kind: ItemKind
    source_group: str
    published_at: datetime | None = None
    authors: list[str] = field(default_factory=list)
    raw_tags: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    decision: str = "pending"
    importance: str = ""
    why_now: str = ""
    digest_summary: str = ""
    reasoning: str = ""
    debug_payload: dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> str:
        return self.url.strip().lower() or self.title.strip().lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "source_name": self.source_name,
            "kind": self.kind.value,
            "source_group": self.source_group,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "authors": self.authors,
            "raw_tags": self.raw_tags,
            "matched_keywords": self.matched_keywords,
            "relevance_score": self.relevance_score,
            "decision": self.decision,
            "importance": self.importance,
            "why_now": self.why_now,
            "digest_summary": self.digest_summary,
            "reasoning": self.reasoning,
        }


@dataclass
class DailyDigest:
    generated_at: datetime
    keywords: list[str]
    overview: str
    takeaways: list[str]
    paper_picks: list[CandidateItem]
    news_picks: list[CandidateItem]
    watchlist: list[CandidateItem]
    reviewed_items: list[CandidateItem]
    subject: str = ""
    html: str = ""
    stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "keywords": self.keywords,
            "overview": self.overview,
            "takeaways": self.takeaways,
            "paper_picks": [item.to_dict() for item in self.paper_picks],
            "news_picks": [item.to_dict() for item in self.news_picks],
            "watchlist": [item.to_dict() for item in self.watchlist],
            "reviewed_items": [item.to_dict() for item in self.reviewed_items],
            "subject": self.subject,
            "stats": self.stats,
        }
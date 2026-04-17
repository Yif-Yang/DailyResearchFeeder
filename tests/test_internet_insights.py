from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from dailyresearchfeeder.models import ItemKind
from dailyresearchfeeder.sources.base import SourceFetchError
from dailyresearchfeeder.sources.internet_insights import (
    InternetInsightsConfig,
    InternetInsightsSource,
)


class _FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self._responses = responses

    def get(self, url, params=None):
        for key, response in self._responses.items():
            if key in url:
                return response
        raise AssertionError(f"Unexpected URL {url}")


def _install_fake_aiohttp(session):
    class _StubClientSession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self_inner):
            return session

        async def __aexit__(self_inner, *a):
            return False

    class _StubTimeout:
        def __init__(self, *a, **kw):
            pass

    sys.modules["aiohttp"] = SimpleNamespace(
        ClientSession=_StubClientSession,
        ClientTimeout=_StubTimeout,
    )


def test_hackernews_parsing_maps_fields():
    hn_payload = {
        "hits": [
            {
                "objectID": "42",
                "title": "Claude Opus 4.7 released",
                "url": "https://www.anthropic.com/news/claude-opus-4-7",
                "points": 1670,
                "num_comments": 312,
                "author": "meetpateltech",
                "created_at": "2026-04-16T14:23:50Z",
                "_tags": ["story"],
            },
            {
                "objectID": "low",
                "title": "Weak story below threshold",
                "url": "https://example.com/x",
                "points": 3,
                "num_comments": 0,
                "author": "anon",
                "created_at": "2026-04-16T12:00:00Z",
            },
        ]
    }
    session = _FakeSession({
        "hn.algolia.com": _FakeResponse(200, hn_payload),
        "api.github.com": _FakeResponse(200, {"items": []}),
    })
    _install_fake_aiohttp(session)

    config = InternetInsightsConfig(
        hackernews_enabled=True,
        hackernews_min_points=40,
        github_enabled=False,
        github_queries=[],
    )
    items = asyncio.run(InternetInsightsSource(config).fetch(days_back=30))

    assert len(items) == 1
    item = items[0]
    assert item.source_group == "internet_insights"
    assert item.source_name == "Hacker News Front Page"
    assert item.kind == ItemKind.BLOG
    assert "Claude Opus 4.7" in item.title
    assert item.url == "https://www.anthropic.com/news/claude-opus-4-7"
    assert item.published_at == datetime(2026, 4, 16, 14, 23, 50, tzinfo=timezone.utc)
    assert item.debug_payload["points"] == 1670
    assert "hackernews" in item.raw_tags


def test_github_parsing_maps_fields():
    github_payload = {
        "items": [
            {
                "full_name": "AMAP-ML/SkillClaw",
                "html_url": "https://github.com/AMAP-ML/SkillClaw",
                "description": "A library for teaching agents new tools.",
                "stargazers_count": 691,
                "language": "Python",
                "created_at": "2026-04-14T10:00:00Z",
                "owner": {"login": "AMAP-ML"},
            },
        ]
    }
    session = _FakeSession({
        "hn.algolia.com": _FakeResponse(200, {"hits": []}),
        "api.github.com": _FakeResponse(200, github_payload),
    })
    _install_fake_aiohttp(session)

    config = InternetInsightsConfig(
        hackernews_enabled=False,
        github_enabled=True,
        github_queries=["agent LLM"],
        github_max_per_query=3,
        github_min_stars=5,
    )
    items = asyncio.run(InternetInsightsSource(config).fetch(days_back=30))

    assert len(items) == 1
    item = items[0]
    assert item.source_name == "GitHub Trending"
    assert item.kind == ItemKind.RELEASE
    assert item.source_group == "internet_insights"
    assert item.url == "https://github.com/AMAP-ML/SkillClaw"
    assert item.debug_payload["stars"] == 691
    assert "github_trending" in item.raw_tags


def test_fetch_raises_when_both_endpoints_fail():
    session = _FakeSession({
        "hn.algolia.com": _FakeResponse(500, {}),
        "api.github.com": _FakeResponse(500, {}),
    })
    _install_fake_aiohttp(session)

    config = InternetInsightsConfig(
        hackernews_enabled=True,
        github_enabled=True,
        github_queries=["agent"],
    )
    with pytest.raises(SourceFetchError):
        asyncio.run(InternetInsightsSource(config).fetch(days_back=2))

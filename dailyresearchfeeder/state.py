from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"ref", "source", "spm"}
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query, doseq=True), ""))


@dataclass
class SeenStateStore:
    path: Path
    ttl_days: int = 14
    max_items: int = 4000
    items: dict[str, str] = field(default_factory=dict)

    def load(self) -> None:
        if not self.path.exists():
            self.items = {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.items = {}
            return
        self.items = dict(payload.get("items", {}))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": self.items}
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def prune(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.ttl_days)
        removed = 0
        kept: dict[str, str] = {}
        for key, seen_at in self.items.items():
            try:
                parsed = datetime.fromisoformat(seen_at)
            except ValueError:
                removed += 1
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed >= cutoff:
                kept[key] = parsed.isoformat()
            else:
                removed += 1

        if len(kept) > self.max_items:
            ordered = sorted(kept.items(), key=lambda item: item[1], reverse=True)
            kept = dict(ordered[: self.max_items])
            removed += max(0, len(ordered) - self.max_items)

        self.items = kept
        return removed

    def has_seen(self, url: str) -> bool:
        return normalize_url(url) in self.items

    def mark_seen(self, urls: list[str]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        for url in urls:
            key = normalize_url(url)
            if key:
                self.items[key] = now
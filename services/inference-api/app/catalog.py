from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContentItem:
    content_id: str
    genre: str
    title: str


def build_catalog(settings: Settings) -> list[ContentItem]:
    return [
        ContentItem(
            content_id=item["content_id"],
            genre=item["genre"],
            title=item["title"],
        )
        for item in settings.content_catalog
    ]


def build_trending(settings: Settings, catalog: list[ContentItem]) -> list[ContentItem]:
    """Return the trending fallback list in config order, preserving catalog metadata."""
    by_id = {item.content_id: item for item in catalog}
    result = []
    for cid in settings.trending_content_ids:
        if cid in by_id:
            result.append(by_id[cid])
        else:
            log.warning("Trending content_id '%s' not found in catalog — skipping", cid)
    return result

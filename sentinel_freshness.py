"""Publication evidence checks for GameCode Sentinel.

A dated mention is *not* proof of redemption validity. Old posts are marked
for review, not declared expired; the database keeps their history.
Only explicit article/reddit timestamps count. Never infer a publication date
from arbitrary dates in article text or from the time we fetched the URL.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from bs4 import BeautifulSoup


MAX_AGE_DAYS = {"Genshin Impact": 30, "AION 2": 90, "Aniimo": 90}
MAX_FUTURE_SKEW = timedelta(days=1)


def parse_publication_time(raw: object, *, now: datetime | None = None) -> str:
    """Normalized UTC ISO-8601 timestamp; empty string for unreliable input."""
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    try:
        if isinstance(raw, bool) or raw is None:
            return ""
        if isinstance(raw, (int, float)):
            if not math.isfinite(raw) or not (946684800 <= raw <= 4102444800):
                return ""
            stamp = datetime.fromtimestamp(raw, tz=timezone.utc)
        elif isinstance(raw, str):
            value = raw.strip()
            if not value or len(value) > 90:
                return ""
            try:
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
        else:
            return ""
        stamp = stamp.astimezone(timezone.utc)
        if stamp.year < 2000 or stamp > reference + MAX_FUTURE_SKEW:
            return ""
        return stamp.isoformat(timespec="seconds")
    except (ValueError, TypeError, OverflowError, OSError):
        return ""


def _jsonld_article_dates(node: object) -> tuple[str, str]:
    if isinstance(node, list):
        for element in node:
            pub, modified = _jsonld_article_dates(element)
            if pub or modified:
                return pub, modified
    elif isinstance(node, dict):
        types = node.get("@type", "")
        if isinstance(types, str):
            types = [types]
        article_types = {"Article", "NewsArticle", "BlogPosting", "Report", "SocialMediaPosting"}
        if isinstance(types, list) and any(str(t).rsplit("/", 1)[-1] in article_types for t in types):
            return str(node.get("datePublished") or ""), str(node.get("dateModified") or "")
        for item in (node.get("@graph"), node.get("mainEntity")):
            pub, modified = _jsonld_article_dates(item)
            if pub or modified:
                return pub, modified
    return "", ""


def extract_page_dates(html: str) -> tuple[str, str]:
    """Return publication/last edit dates only from explicit article metadata."""
    soup = BeautifulSoup(html, "html.parser")

    def meta_value(keys: tuple[str, ...]) -> str:
        for tag in soup.find_all("meta"):
            key = (tag.get("property") or tag.get("name") or tag.get("itemprop") or "").casefold()
            if key in keys and tag.get("content"):
                return str(tag["content"])
        return ""

    published = meta_value(("article:published_time", "datepublished", "pubdate",
                            "article:publication_date", "publish_date"))
    modified = meta_value(("article:modified_time", "datemodified", "article:updated_time"))
    if not published or not modified:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                article_pub, article_mod = _jsonld_article_dates(json.loads(script.string or script.get_text()))
            except (ValueError, TypeError):
                continue
            published = published or article_pub
            modified = modified or article_mod
            if published and modified:
                break
    if not published:
        # Explicit authoring datetime; never use arbitrary <time> elements from
        # site navigation / recommended articles / embedded comments.
        tag = soup.select_one('time[itemprop="datePublished"][datetime], '
                              'article time.published[datetime], '
                              'article time[pubdate][datetime]')
        if tag:
            published = tag.get("datetime", "")
    return parse_publication_time(published), parse_publication_time(modified)


def age_days(publication: str, *, now: datetime | None = None) -> Optional[int]:
    parsed = parse_publication_time(publication, now=now)
    if not parsed:
        return None
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    delta = reference - datetime.fromisoformat(parsed)
    return max(0, int(delta.total_seconds() // 86400))


def is_old_post(game: str, publication: str, *, now: datetime | None = None) -> bool:
    age = age_days(publication, now=now)
    return age is not None and age > MAX_AGE_DAYS.get(game, 60)


# An active listing is an explicit section on a currently fetched editorial
# tracker page, not an arbitrary article that happens to contain the word
# "active" somewhere. The website still does NOT prove that redemption works.
import re

_CURRENT_CODES = re.compile(
    r"(?i)\\b(?:active|working|valid|current|available|new)\\b"
    r".{0,65}\\b(?:codes?|coupons?)\\b"
    r"|\\b(?:codes?|coupons?)\\b.{0,35}\\b(?:active|working|valid)\\b"
)
_INACTIVE_CODES = re.compile(
    r"(?i)\\b(?:expired|inactive|invalid|old|outdated|previous|"
    r"no longer|not working|non validi|scadut[oaie])\\b"
)


def is_active_tracker_heading(heading: str, *, source_kind: str, source_mode: str) -> bool:
    if source_kind != "secondary" or source_mode != "page":
        return False
    heading = (heading or "").strip()
    return (
        len(heading) <= 150
        and not _INACTIVE_CODES.search(heading)
        and bool(_CURRENT_CODES.search(heading))
    )

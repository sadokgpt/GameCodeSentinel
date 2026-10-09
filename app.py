from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import html as html_lib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from sentinel_runtime import operation_lock, backup_sqlite, restore_sqlite, plausible_tracker_page

try:
    from dateparser.search import search_dates
except Exception:
    search_dates = None

APP_NAME = "GameCodeSentinel"
APP_VERSION = "1.4.0"
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (+local Windows code tracker; contact: local-user)"
REQUEST_TIMEOUT = 18
MAX_CRAWL_LINKS = 14
MAX_SCAN_WORKERS = 3

GAME_GENSHIN = "Genshin Impact"
GAME_ANIIMO = "Aniimo"
GAME_AION2 = "AION 2"
GAMES = [GAME_GENSHIN, GAME_ANIIMO, GAME_AION2]

LOCAL_APPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
DATA_DIR = LOCAL_APPDATA / APP_NAME
DB_PATH = DATA_DIR / "codes.db"
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "app.log"

DEFAULT_CONFIG = {
    "schedule_time": "08:00",
    "notify_pc": True,
    "notify_phone": False,
    "notify_min_score": 85,
    "ntfy_server": "https://ntfy.sh",
    "ntfy_topic": "",
    "show_unverified": False,
    "reddit_days": "month",
}

STOPWORDS = {
    "REDEEM", "REDEEMCODE", "REDEMPTION", "COUPON", "COUPONCODE", "CODE", "CODES",
    "ACTIVE", "EXPIRED", "WORKING", "AVAILABLE", "REWARDS", "REWARD", "SETTINGS",
    "ACCOUNT", "OFFICIAL", "GLOBAL", "VERSION", "DOWNLOAD", "SUPPORT", "PRIMOGEMS",
    "GLIMMER", "CREDITS", "ADVENTURER", "EXPERIENCE", "OCTOBER", "SEPTEMBER",
    "GENSHIN", "ANIIMO", "AION", "AION2", "TWITTER", "DISCORD", "REDDIT",
}

POSITIVE_REDDIT = re.compile(r"\b(worked|works|working|redeemed|redeem(?:ed)? successfully|funziona|funzionato|valido)\b", re.I)
NEGATIVE_REDDIT = re.compile(r"\b(expired|doesn.?t work|not working|invalid|scadut|non funziona|non valido)\b", re.I)


@dataclass(frozen=True)
class Source:
    game: str
    name: str
    url: str
    kind: str  # official | secondary | community
    mode: str = "page"  # page | crawl | reddit
    link_hint: str = ""
    subreddit: str = ""


SOURCES = [
    Source(GAME_GENSHIN, "HoYoverse - News", "https://genshin.hoyoverse.com/en/news", "official", "crawl", "/en/news/detail/"),
    Source(GAME_GENSHIN, "Pocket Tactics", "https://www.pockettactics.com/genshin-impact/codes", "secondary", "page"),
    Source(GAME_GENSHIN, "Destructoid", "https://www.destructoid.com/all-genshin-impact-codes-and-how-to-redeem-them/", "secondary", "page"),
    Source(GAME_GENSHIN, "Reddit r/Genshin_Impact", "", "community", "reddit", subreddit="Genshin_Impact"),
    Source(GAME_GENSHIN, "Reddit r/GenshinImpact", "", "community", "reddit", subreddit="GenshinImpact"),

    Source(GAME_ANIIMO, "Aniimo - News ufficiali", "https://www.aniimo.com/newslist", "official", "crawl", "/newslist/detail/"),
    Source(GAME_ANIIMO, "Pocket Tactics", "https://www.pockettactics.com/aniimo/codes", "secondary", "page"),
    Source(GAME_ANIIMO, "Pocket Gamer", "https://www.pocketgamer.com/aniimo/codes/", "secondary", "page"),
    Source(GAME_ANIIMO, "Aniimo Wiki", "https://aniimo.io/en/guide/codes", "secondary", "page"),
    Source(GAME_ANIIMO, "Reddit r/AniimoGuide", "", "community", "reddit", subreddit="AniimoGuide"),

    Source(GAME_AION2, "AION 2 - PURPLE Lounge ufficiale", "https://lounge.plaync.com/tag/13519", "official", "crawl", "/feed/"),
    Source(GAME_AION2, "Steam - Annunci ufficiali AION 2", "https://steamcommunity.com/app/3393110/announcements/", "official", "page"),
    Source(GAME_AION2, "AION 2 - Notice ufficiali", "https://aion2.plaync.com/en-us/board/notice/list", "official", "crawl", "/board/notice/view"),
    Source(GAME_AION2, "NCSOFT - News", "https://about.ncsoft.com/en/news", "official", "crawl", "/en/news/article/aion2"),
    Source(GAME_AION2, "Pro Game Guides", "https://progameguides.com/codes/aion-2-codes/", "secondary", "page"),
    Source(GAME_AION2, "AION 2 - Destructoid", "https://www.destructoid.com/aion-2-codes/", "secondary", "page"),
    Source(GAME_AION2, "Reddit r/Aion2", "", "community", "reddit", subreddit="Aion2"),
]


@dataclass
class Candidate:
    game: str
    code: str
    reward: str
    source_name: str
    source_url: str
    source_kind: str
    status: str = "active"
    expires_at: str = ""
    context: str = ""
    reddit_confirmations: int = 0
    reddit_negatives: int = 0

    @property
    def normalized(self) -> str:
        return normalize_code(self.code)


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    ensure_dirs()
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {msg}\n")


def load_config() -> dict:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()
    try:
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        return cfg
    except Exception as exc:
        log(f"Config non leggibile: {exc}")
        return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    ensure_dirs()
    tmp = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def connect_db() -> sqlite3.Connection:
    ensure_dirs()
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    # Preserve an online WAL-safe backup before touching schema or records.
    try:
        backup_sqlite(DB_PATH)
    except Exception as exc:
        log(f"Backup periodico non riuscito: {exc}")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=20000")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT NOT NULL,
            code TEXT NOT NULL,
            normalized TEXT NOT NULL,
            rewards TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            confidence TEXT DEFAULT '',
            score INTEGER DEFAULT 0,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            expires_at TEXT DEFAULT '',
            used INTEGER DEFAULT 0,
            notified INTEGER DEFAULT 0,
            notified_pc INTEGER DEFAULT 0,
            notified_phone INTEGER DEFAULT 0,
            source_count INTEGER DEFAULT 0,
            confirmations INTEGER DEFAULT 0,
            negatives INTEGER DEFAULT 0,
            miss_count INTEGER DEFAULT 0,
            sources_json TEXT DEFAULT '[]',
            UNIQUE(game, normalized)
        )
        """
    )
    # Migrazione trasparente da versioni precedenti.
    existing_cols = {row[1] for row in con.execute("PRAGMA table_info(codes)")}
    added_columns: set[str] = set()
    for column in ("notified_pc", "notified_phone", "miss_count"):
        if column not in existing_cols:
            con.execute(f"ALTER TABLE codes ADD COLUMN {column} INTEGER DEFAULT 0")
            added_columns.add(column)
    # If upgrading from v1, preserve the old generic 'notified' flag so already-seen
    # codes do not suddenly generate duplicate alerts after the upgrade.
    if "notified_pc" in added_columns:
        con.execute("UPDATE codes SET notified_pc=COALESCE(notified, 0)")
    if "notified_phone" in added_columns:
        con.execute("UPDATE codes SET notified_phone=COALESCE(notified, 0)")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at TEXT NOT NULL,
            ok_sources INTEGER DEFAULT 0,
            failed_sources INTEGER DEFAULT 0,
            candidates INTEGER DEFAULT 0,
            error_summary TEXT DEFAULT ''
        )
        """
    )
    con.execute("""
        CREATE TABLE IF NOT EXISTS source_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at TEXT NOT NULL,
            source_name TEXT NOT NULL,
            game TEXT NOT NULL,
            status TEXT NOT NULL,
            candidates INTEGER NOT NULL DEFAULT 0,
            elapsed_ms INTEGER NOT NULL DEFAULT 0,
            error TEXT DEFAULT ''
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_source_checks_name_id ON source_checks(source_name,id)")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    # AION 2 in v1.1 was parsed by a very permissive word scanner. Previously saved
    # "official" results must not stay visible without being checked by the new parser.
    # Keep them and all user flags; a subsequent verified sighting restores the status.
    migration = con.execute("SELECT value FROM meta WHERE key='aion_strict_parser_v12'").fetchone()
    if migration is None:
        con.commit()
        # Consistent snapshot (including WAL) before first v1.2 migration.
        backup_path = DB_PATH.with_name("codes.before_v1.2.sqlite3")
        if not backup_path.exists() and con.execute("SELECT COUNT(*) FROM codes").fetchone()[0] > 0:
            backup_con = sqlite3.connect(backup_path)
            try:
                con.backup(backup_con)
            finally:
                backup_con.close()
        if {"game", "status", "used", "score", "confidence", "expires_at"} <= existing_cols:
            con.execute(
                "UPDATE codes SET status='review', score=0, expires_at='', "
                "confidence='RIVERIFICA NECESSARIA' "
                "WHERE game=? AND status='active' AND used=0", (GAME_AION2,)
            )
        con.execute("INSERT INTO meta(key, value) VALUES('aion_strict_parser_v12','1')")
    # v1.3.0 could misread reward nouns as coupon codes in Reddit posts.
    # Recheck previously stored suspicious unredeemed entries conservatively,
    # preserving official-source evidence and all user/notified history.
    needs_shape_review = con.execute(
        "SELECT value FROM meta WHERE key='aion_code_shape_review_v131'"
    ).fetchone()
    if needs_shape_review is None and {"game", "code", "status", "used", "sources_json"} <= existing_cols:
        for row in con.execute(
            "SELECT id, code, sources_json FROM codes "
            "WHERE game=? AND status='active' AND used=0", (GAME_AION2,)
        ).fetchall():
            if looks_like_code(GAME_AION2, row["code"]):
                continue
            try:
                sources = json.loads(row["sources_json"] or "[]")
            except (TypeError, ValueError):
                sources = []
            if any(isinstance(src, dict) and src.get("kind") == "official" for src in sources):
                continue
            con.execute(
                "UPDATE codes SET status='review', score=0, "
                "confidence='RIVERIFICA NECESSARIA (FORMA CODICE SOSPETTA)' "
                "WHERE id=?", (row["id"],)
            )
        con.execute("INSERT INTO meta(key, value) VALUES('aion_code_shape_review_v131','1')")
    con.commit()
    return con


def normalize_code(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", code.strip()).upper()


def looks_like_code(game: str, token: str, context: str = "") -> bool:
    token = token.strip().strip("`'\"“”.,;:()[]{}<>")
    if not (5 <= len(token) <= 28):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        return False
    up = token.upper()
    if up in STOPWORDS:
        return False
    if up in {"EXAMPLE", "EXAMPLES", "PLACEHOLDER", "SAMPLE", "SAMPLES", "PROMOTION",
              "REGISTRATION", "REDEMPTIONCODE", "COUPONREGISTRATION", "CONFIRMATION"}:
        return False
    if token.lower().startswith(("http", "www")):
        return False
    # Game name and alphanumeric strings are not sufficient evidence for an AION coupon.
    if game == GAME_AION2:
        # Reward names (e.g. "Resurrection Spiritstone") can appear after
        # "code:" in user-submitted posts. TitleCase words are not coupons.
        # Support uppercase codes and codes containing digits without a whitelist.
        return (len(token) >= 8 and bool(re.search(r"[A-Za-z]", token))
                and (token.isupper() or any(ch.isdigit() for ch in token)))
    if game == GAME_ANIIMO and (
        token.lower().startswith("aniimo") or token.lower().startswith("any") or token.lower().startswith("twine")
    ):
        return True
    if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
        return True
    # Word-like promo codes exist in Genshin (e.g. mixed-case names). Require strong code context.
    strong_context = re.search(r"\b(code|coupon|redeem|gift|codice)\b", context, re.I)
    camelish = bool(re.search(r"[a-z].*[A-Z]|[A-Z].*[a-z]", token))
    all_caps_long = token.isupper() and len(token) >= 9
    if strong_context and (camelish or all_caps_long):
        return True
    return False


def clean_reward(text: str, code: str) -> str:
    # If the sentence is "Redeem code X for: ...", keep only what comes after X for:.
    m_after = re.search(re.escape(code) + r"\s+for\s*[:\-–—]?\s*", text, re.I)
    t = text[m_after.end():] if m_after else re.sub(re.escape(code), "", text, flags=re.I)
    # Never let redemption instructions / expiry paragraphs leak into the reward column.
    t = re.split(r"(?i)\b(?:how to redeem|coupon period|redemption period|expires?|expiry|valid until|scadenza)\b", t, maxsplit=1)[0]
    t = re.sub(r"(?i)\b(redeem\s+code|gift\s+code|coupon\s+code|code|coupon|codice|new|active|working|rewards?)\b\s*[:\-–—]?", "", t)
    t = re.sub(r"(?i)^\s*for\s*[:\-–—]?\s*", "", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\s*\|\s*", "; ", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—:|•\t;")
    if len(t) > 280:
        t = t[:277] + "..."
    # Reward text is useful only if it contains quantities/items or an explicit reward term.
    if len(t) < 3:
        return ""
    if not (re.search(r"\d", t) or re.search(r"reward|primogem|mora|glimmer|credit|aniipod|flower|energy|scroll|stone|ore|wit|egg|voucher", t, re.I)):
        return ""
    return t


def extract_expiry(context: str) -> str:
    # Only inspect the date immediately linked to an expiry expression.
    # Looking across a whole paragraph could mistake article dates for expiry.
    clause = re.search(
        r"(?i)\b(?:expires?|expiry|ends?|valid\s+(?:through|until)|scadenza)\b"
        r"\s*(?:on|at|by|:|is|the)?\s*([A-Za-z0-9,/:.\s-]{5,65})", context,
    )
    if not clause:
        return ""
    if not search_dates:
        return ""
    nearby = clause.group(1).split("|")[0].strip()
    if not re.search(
        r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)|"
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}",
        nearby, re.I,
    ):
        return ""
    try:
        # "future" would silently assign next year to an already expired
        # yearless date (for example "Expires Oct 2" scanned on Oct 8).
        # Anchor yearless dates to this calendar year, never to next year.
        found = search_dates(
            nearby,
            settings={
                "PREFER_DATES_FROM": "current_period",
                "RELATIVE_BASE": datetime(datetime.now().year, 1, 1),
                "RETURN_AS_TIMEZONE_AWARE": False,
            },
            languages=["en", "it"],
        )
        if not found:
            return ""
        # Prefer a future date with year or month near expiry language.
        now = datetime.now()
        has_time = bool(re.search(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", nearby))
        for _, dt in found:
            if dt.year >= now.year - 1:
                if not has_time:
                    dt = dt.replace(hour=23, minute=59)
                return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    return ""


def expiry_has_passed(game: str, expiry: str) -> bool:
    """AION EU deadlines are expressed in Europe/Rome time."""
    if not expiry:
        return False
    try:
        end = datetime.strptime(expiry, "%Y-%m-%d %H:%M")
        clock = (datetime.now(ZoneInfo("Europe/Rome")).replace(tzinfo=None)
                 if game == GAME_AION2 else datetime.now())
        return end <= clock
    except ValueError:
        return False


def context_status(context: str) -> str:
    if re.search(r"\b(expired|scadut[oaie]|no longer works?|invalid)\b", context, re.I):
        return "expired"
    return "active"


def get_context(text: str, start: int, end: int, radius: int = 180) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def reward_window(lines: list[str], idx: int, max_following: int = 7) -> str:
    """Collect reward lines following a code without swallowing the next section/code."""
    collected = [lines[idx]]
    stop = re.compile(r"(?i)^(?:how to redeem|redeem(?:ing)?|coupon period|redemption period|expiry|expires?|valid until|scadenza|notes?\b)")
    next_code = re.compile(r"(?i)\b(?:redeem\s+code|gift\s+code|coupon\s+code|coupon|code|codice)\s*(?:is|è|:|=|\-|–|—)?\s*[`'\"“”]*[A-Za-z0-9][A-Za-z0-9_-]{4,27}")
    for line in lines[idx + 1: idx + 1 + max_following]:
        if stop.search(line):
            break
        if next_code.search(line):
            break
        collected.append(line)
    return " | ".join(collected)


def aion_eu_expiry(text: str) -> str:
    """Read a publisher's explicit EU deadline, never a launch or article date.

    Absence of a deadline is not proof that a coupon remains valid indefinitely.
    """
    pattern = re.search(
        r"(?i)\bends?\s*\(EU\)\s*:\s*(\d{1,2}\s+[A-Za-z]+)\s*,?\s*"
        r"(?:at\s*)?(\d{1,2}:\d{2})\s*(CEST|CET)?",
        text,
    )
    if not pattern:
        return ""
    try:
        year_match = re.search(r"\b20\d{2}\b", text)
        year = int(year_match.group()) if year_match else datetime.now().year
        day_month = datetime.strptime(pattern.group(1) + f" {year}", "%d %B %Y")
        hours, minutes = map(int, pattern.group(2).split(":"))
        return datetime(year, day_month.month, day_month.day, hours, minutes).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ""


def extract_aion_candidates_html(html: str, source: Source, page_url: str) -> list[Candidate]:
    """Strict coupon extraction; NO generic words or arbitrary AION2* tokens.

    A code needs a local redemption statement OR an item in a labelled code list.
    A page being on an official domain does not make all its text valid coupons.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    full_text = soup.get_text("\n", strip=True)
    lines = [line.strip() for line in full_text.splitlines() if line.strip()]
    explicit = re.compile(
        r"(?i)\b(?:redeem|use|enter|type|apply)\s+(?:the\s+)?"
        r"(?:(?:promo(?:tional)?|gift|coupon)\s+)?code\s*(?:is|:|=|–|—|-)?\s+"
        r"[`'\"“”]*([A-Za-z0-9][A-Za-z0-9_-]{7,27})\b"
        r"|\b(?:coupon|promo(?:tional)?|gift)\s+code\s*(?:number|is|:|=|-)?\s+"
        r"[`'\"“”]*([A-Za-z0-9][A-Za-z0-9_-]{7,27})\b"
        r"|\bcode\s*[:=]\s*[`'\"“”]*([A-Za-z0-9][A-Za-z0-9_-]{7,27})\b"
    )
    # Only accept a bare code followed by a reward when it is in an actual code list.
    list_entry = re.compile(
        r"^\s*[•*\-]?\s*([A-Za-z0-9][A-Za-z0-9_-]{7,27})\s*"
        r"(?:[—–\-:|]\s*|\s+)(.{3,250})$"
    )
    heading_code_list = re.compile(r"(?i)\b(?:active|working|current|valid|expired|new)\b.*\b(?:codes?|coupons?)\b")
    misleading = re.compile(
        r"(?i)\b(?:example|placeholder|dummy|fake|made.up|test\s+code|"
        r"not\s+(?:a\s+)?(?:real|valid|working)?\s*(?:coupon|code)|"
        r"not\s+coupons?|invalid\s+code|do\s+not\s+use)\b"
    )
    candidates: dict[str, Candidate] = {}

    def add(token: str, context: str, reward: str, status: str, position: int = -1) -> None:
        token = token.strip().strip("`'\"“”.,;:()[]{}<>")
        if not looks_like_code(GAME_AION2, token, context):
            return
        if misleading.search(context):
            return
        expiry = ""
        if position >= 0:
            # Publisher's coupon period typically appears after the reward bullets.
            expiry = aion_eu_expiry(full_text[position:position + 1400])
        candidate = Candidate(
            game=GAME_AION2, code=token, reward=clean_reward(reward, token),
            source_name=source.name, source_url=page_url, source_kind=source.kind,
            status=status, expires_at=expiry, context=context[:500],
        )
        key = candidate.normalized
        old = candidates.get(key)
        if old is None or (old.status != "active" and status == "active") or (
            old.status == status and len(candidate.reward) > len(old.reward)
        ):
            if old is not None and not candidate.expires_at:
                candidate.expires_at = old.expires_at
            candidates[key] = candidate

    # Paragraphs/tables/list items: keep local context, not the entire news page.
    for tag in soup.find_all(["p", "li", "tr", "code"]):
        block = tag.get_text(" ", strip=True)
        if not block or len(block) > 700:
            continue
        heading = tag.find_previous(["h1", "h2", "h3", "h4"])
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        is_list = bool(heading_code_list.search(heading_text))
        status = "expired" if re.search(r"(?i)\b(?:expired|old\s+codes|scadut[oaie]?)\b", heading_text) else "active"
        if re.search(r"(?i)\b(?:is\s+expired|code\s+expired|no\s+longer\s+valid)\b", block):
            status = "expired"
        position = full_text.find(block)  # -1 for markup-separated phrases; safe fallback
        for match in explicit.finditer(block):
            code = next(x for x in match.groups() if x)
            # Explicit statement itself must not call this code a dummy/sample.
            add(code, block, block, status, position)
        if tag.name in {"li", "tr", "code"} and is_list:
            if tag.name == "tr":
                cells = [c.get_text(" ", strip=True) for c in tag.find_all(["td", "th"])]
                code = cells[0] if cells else ""
                rest = " ".join(cells[1:])
            else:
                match = list_entry.match(block)
                code, rest = (match.group(1), match.group(2)) if match else ("", "")
            if code and (rest or tag.name == "code"):
                add(code, heading_text + " | " + block, rest, status, position)

    # Publisher CMS may use styled <div> rather than <p>; in this fallback the
    # *only* pattern accepted is an explicit instruction on one short text line.
    section_status = "active"
    for idx, line in enumerate(lines):
        if len(line) > 400:
            continue
        if re.search(r"(?i)^\s*(?:expired|old|scadut[ieoa]?)\s+(?:codes?|coupons?)\b", line):
            section_status = "expired"
        elif re.search(r"(?i)^\s*(?:active|working|new|current|valid)\s+(?:codes?|coupons?)\b", line):
            section_status = "active"
        for match in explicit.finditer(line):
            code = next(x for x in match.groups() if x)
            reward = reward_window(lines, idx)
            pos = full_text.find(line)
            status = "expired" if section_status == "expired" or context_status(line) == "expired" else "active"
            add(code, line, reward, status, pos)

    if source.kind == "official":
        for idx, label in enumerate(lines[:-1]):
            if label.casefold().strip(": ") in {"coupon code", "gift code", "promo code"}:
                token = lines[idx + 1]
                if looks_like_code(GAME_AION2, token, label):
                    add(token, label + " " + token, reward_window(lines, idx + 1),
                        "active", full_text.find(token))

    return list(candidates.values())


def extract_candidates_html(game: str, html: str, source: Source, page_url: str) -> list[Candidate]:
    if game == GAME_AION2:
        return extract_aion_candidates_html(html, source, page_url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    out: dict[str, Candidate] = {}

    def add(code: str, ctx: str, reward_hint: str = "", status_override: str = "") -> None:
        code = code.strip().strip("`'\"“”.,;:()[]{}<>")
        if not looks_like_code(game, code, ctx):
            return
        norm = normalize_code(code)
        reward = clean_reward(reward_hint or ctx, code)
        cand = Candidate(
            game=game,
            code=code,
            reward=reward,
            source_name=source.name,
            source_url=page_url,
            source_kind=source.kind,
            status=status_override or context_status(ctx),
            expires_at=extract_expiry(ctx),
            context=ctx[:500],
        )
        prev = out.get(norm)
        if (
            prev is None
            or (cand.status == "active" and prev.status != "active")
            or (cand.status == prev.status and len(cand.reward) > len(prev.reward))
        ):
            out[norm] = cand

    # <code> tags and URLs with ?code=...
    for tag in soup.find_all("code"):
        token = tag.get_text(" ", strip=True)
        heading = tag.find_previous(["h1", "h2", "h3", "h4"])
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        status_override = "expired" if re.search(r"expired|scadut", heading_text, re.I) else ""
        ctx = (heading_text + " | " + (tag.parent.get_text(" ", strip=True) if tag.parent else token)).strip(" |")
        add(token, ctx, status_override=status_override)
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        try:
            qs = parse_qs(urlparse(href).query)
            for key in ("code", "redeemCode", "coupon"):
                for token in qs.get(key, []):
                    add(token, a.parent.get_text(" ", strip=True) if a.parent else href)
        except Exception:
            pass

    explicit = re.compile(
        r"(?i)\b(?:redeem\s+code|gift\s+code|coupon\s+code|coupon|code|codice)\s*(?:is|è|:|=|\-|–|—)?\s*[`'\"“”]*([A-Za-z0-9][A-Za-z0-9_-]{4,27})"
    )
    line_pat = re.compile(r"^\s*[•*\-]?\s*([A-Za-z0-9][A-Za-z0-9_-]{4,27})\s*(?:[-–—:|])\s*(.{3,260})$")

    # List items / paragraphs often contain styled spans that get split by plain-text extraction.
    for block in soup.find_all(["li", "p"]):
        block_text = block.get_text(" ", strip=True)
        if not block_text or len(block_text) > 600:
            continue
        heading = block.find_previous(["h1", "h2", "h3", "h4"])
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        status_override = ""
        if re.search(r"expired|scadut|old codes", heading_text + " | " + block_text, re.I):
            status_override = "expired"
        elif re.search(r"active|working|current|valid|available", heading_text, re.I):
            status_override = "active"
        for m in explicit.finditer(block_text):
            add(m.group(1), f"{status_override} {heading_text} | {block_text}", status_override=status_override)
        lm = line_pat.match(block_text)
        if lm:
            add(lm.group(1), f"{status_override} code {heading_text} | {block_text}", lm.group(2), status_override)

    # Table rows are common on code trackers. Preserve Active/Expired section context.
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        heading = tr.find_previous(["h1", "h2", "h3", "h4"])
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        status_override = ""
        row_text = " | ".join(cells)
        if re.search(r"expired|scadut|old codes", heading_text + " | " + row_text, re.I):
            status_override = "expired"
        elif re.search(r"active|working|current|valid|available", heading_text, re.I):
            status_override = "active"
        token = cells[0].strip().strip("`'\"“”")
        row_ctx = "code " + heading_text + " | " + row_text
        if looks_like_code(game, token, row_ctx):
            add(token, row_ctx, " | ".join(cells[1:]), status_override)

    # Parse line-by-line so an Expired/Active heading is carried into list entries.
    section_status = "active"
    text_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for idx, line in enumerate(text_lines):
        if not line or len(line) > 340:
            continue
        if re.search(r"\b(expired|scadut[ioa]?|non validi|old codes)\b", line, re.I):
            section_status = "expired"
        elif re.search(r"\b(active|working|new|current|live|valid|codici attivi|available)\b.*\b(code|codes|codici|coupon)", line, re.I):
            section_status = "active"

        nearby = " | ".join(text_lines[idx:idx+10])
        reward_nearby = reward_window(text_lines, idx)
        for m in explicit.finditer(line):
            add(m.group(1), f"{section_status} {nearby}", reward_hint=reward_nearby, status_override=section_status)

        m = line_pat.match(line)
        if m:
            add(m.group(1), f"{section_status} code {line}", m.group(2), section_status)

    # Fallback for strongly code-shaped tokens near code/reward wording.
    # Deliberately excludes ordinary TitleCase words to reduce false positives.
    for m in re.finditer(r"\b[A-Za-z0-9][A-Za-z0-9_-]{7,20}\b", text):
        token = m.group(0)
        token_shape = (
            (any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token))
            or token.isupper()
            or (game == GAME_ANIIMO and token.lower().startswith(("aniimo", "any", "twine")))
            or (game == GAME_AION2 and "AION2" in token.upper())
        )
        if not token_shape:
            continue
        ctx = get_context(text, m.start(), m.end(), 100)
        if re.search(r"\b(code|codes|coupon|redeem|gift|reward|codice)\b", ctx, re.I):
            add(token, ctx)

    return list(out.values())


def build_http_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    })
    return session


def http_get(session: requests.Session, url: str) -> requests.Response:
    resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    origin = (urlparse(url).hostname or "").lower().removeprefix("www.")
    destination = (urlparse(resp.url).hostname or "").lower().removeprefix("www.")
    # A source labelled "official" cannot remain official after an arbitrary
    # redirect to a different website. In particular avoid detecting coupons
    # on anti-bot interstitials or advertising landing pages.
    related = origin == destination or (
        origin.endswith(".plaync.com") and destination.endswith(".plaync.com")
    )
    if not related or not resp.url.lower().startswith("https://"):
        raise ValueError(f"Reindirizzamento non attendibile da {origin} a {destination}")
    preview = resp.text[:15000].lower()
    if any(marker in preview for marker in (
        "cf-browser-verification", "checking your browser before accessing",
        "attention required! | cloudflare", "enable javascript and cookies to continue",
        "verify you are human to proceed", "captcha challenge",
    )):
        raise ValueError("Pagina di verifica anti-bot: non è una fonte utilizzabile")
    return resp


def discover_crawl_links(base_url: str, raw_html: str, link_hint: str = "") -> list[str]:
    # Find article links in anchors and in SPA hydration/JSON markup.
    soup = BeautifulSoup(raw_html, "html.parser")
    host = urlparse(base_url).netloc.lower()
    links: list[str] = []

    def add_link(raw: str) -> None:
        if len(links) >= MAX_CRAWL_LINKS:
            return
        raw = html_lib.unescape(raw or "").replace("\\/", "/").replace("\\u002F", "/")
        raw = raw.strip().strip("\"' ")
        if not raw:
            return
        href = urljoin(base_url, raw)
        parsed = urlparse(href)
        if parsed.netloc.lower() != host:
            return
        if link_hint and link_hint.lower() not in href.lower():
            return
        href = parsed._replace(fragment="").geturl()
        if href not in links:
            links.append(href)

    for a in soup.find_all("a", href=True):
        add_link(a.get("href", ""))
        if len(links) >= MAX_CRAWL_LINKS:
            return links

    if link_hint:
        decoded = html_lib.unescape(raw_html).replace("\\/", "/").replace("\\u002F", "/")
        pat = re.compile("[\"']([^\"']*" + re.escape(link_hint) + "[^\"']*)[\"']", re.I)
        for match in pat.finditer(decoded):
            add_link(match.group(1))
            if len(links) >= MAX_CRAWL_LINKS:
                break
    return links


def fetch_page_source(session: requests.Session, source: Source) -> tuple[list[Candidate], int]:
    resp = http_get(session, source.url)
    found = extract_candidates_html(source.game, resp.text, source, resp.url)
    # A soft-404 / cookie wall returning HTTP 200 is NOT reliable evidence
    # that codes previously listed by a tracker have gone away.
    if source.kind == "secondary" and not found and not plausible_tracker_page(resp.text, source.game):
        raise ValueError("Pagina tracker non riconoscibile: assenza codici non verificabile")
    return found, 1


def fetch_crawl_source(session: requests.Session, source: Source) -> tuple[list[Candidate], int]:
    resp = http_get(session, source.url)
    first_html = resp.text
    links = discover_crawl_links(resp.url, first_html, source.link_hint)

    all_candidates = extract_candidates_html(source.game, first_html, source, resp.url)
    fetched = 1
    for href in links:
        try:
            r = http_get(session, href)
            all_candidates.extend(extract_candidates_html(source.game, r.text, source, r.url))
            fetched += 1
            time.sleep(0.12)
        except Exception as exc:
            log(f"Crawl skip {href}: {exc}")
    return all_candidates, fetched


def flatten_reddit_comments(node, texts: list[str]) -> None:
    if isinstance(node, dict):
        data = node.get("data")
        if node.get("kind") == "t1" and isinstance(data, dict):
            body = data.get("body")
            if body:
                texts.append(body)
        for value in node.values():
            flatten_reddit_comments(value, texts)
    elif isinstance(node, list):
        for item in node:
            flatten_reddit_comments(item, texts)


def reddit_comment_texts(session: requests.Session, permalink: str) -> list[str]:
    if not permalink:
        return []
    url = "https://www.reddit.com" + permalink.rstrip("/") + ".json?limit=35&depth=2&raw_json=1"
    r = http_get(session, url)
    payload = r.json()
    texts: list[str] = []
    flatten_reddit_comments(payload, texts)
    return texts[:120]


def reddit_confirmation_counts_from_texts(texts: list[str], code: str = "", unique_code_in_post: bool = True) -> tuple[int, int]:
    pos, neg = 0, 0
    for t in texts:
        # Unqualified "works" is useful only for a thread with exactly one code.
        # For multi-code threads, require that the specific code is named.
        if code and not unique_code_in_post:
            # Don't attribute ABC1234 or ABC123-EXTRA feedback to ABC123.
            if not re.search(r"(?<![A-Za-z0-9_-])" + re.escape(code) +
                             r"(?![A-Za-z0-9_-])", t, re.I):
                continue
        bad = bool(NEGATIVE_REDDIT.search(t))
        if bad:
            neg += 1
        elif POSITIVE_REDDIT.search(t):
            pos += 1  # "not working" must NEVER count as a positive vote too
    return min(pos, 20), min(neg, 20)


def reddit_confirmation_counts(session: requests.Session, permalink: str) -> tuple[int, int]:
    try:
        return reddit_confirmation_counts_from_texts(reddit_comment_texts(session, permalink))
    except Exception as exc:
        log(f"Reddit comment check fallito: {exc}")
        return 0, 0

def fetch_reddit_source(session: requests.Session, source: Source, cfg: dict) -> tuple[list[Candidate], int]:
    query_raw = '("redeem code" OR "gift code" OR coupon OR code)'
    query = quote_plus(query_raw)
    url = (
        f"https://www.reddit.com/r/{source.subreddit}/search.json?"
        f"q={query}&restrict_sr=on&sort=new&t={cfg.get('reddit_days','month')}&limit=50&raw_json=1"
    )
    candidates: list[Candidate] = []

    try:
        r = http_get(session, url)
        payload = r.json()
        children = payload.get("data", {}).get("children", [])
        for idx, item in enumerate(children):
            data = item.get("data", {})
            title = data.get("title", "")
            body = data.get("selftext", "")
            permalink = data.get("permalink", "")
            post_url = "https://www.reddit.com" + permalink if permalink else data.get("url", url)
            post_html = f"<h1>{html_lib.escape(title)}</h1><p>{html_lib.escape(body)}</p>"
            found = extract_candidates_html(source.game, post_html, source, post_url)

            # Search a small number of relevant recent comment threads too. This catches
            # codes posted only in megathread comments while keeping the daily request load low.
            comment_found: list[Candidate] = []
            comment_texts: list[str] = []
            if permalink and idx < 5:
                try:
                    comment_texts = reddit_comment_texts(session, permalink)
                    if comment_texts:
                        comment_html = "<div>" + "".join(
                            f"<p>{html_lib.escape(t)}</p>" for t in comment_texts
                        ) + "</div>"
                        comment_found = extract_candidates_html(source.game, comment_html, source, post_url)
                except Exception as exc:
                    log(f"Reddit comment scan fallito {post_url}: {exc}")

            all_found = found + comment_found
            if all_found:
                unique_codes = {c.normalized for c in all_found}
                for cand in all_found:
                    pos, neg = reddit_confirmation_counts_from_texts(
                        comment_texts, cand.code, len(unique_codes) == 1
                    ) if comment_texts else (0, 0)
                    cand.reddit_confirmations = pos
                    cand.reddit_negatives = neg
                candidates.extend(all_found)
    except Exception as json_exc:
        # Reddit may rate-limit JSON for unauthenticated desktop tools. RSS is a read-only fallback.
        log(f"Reddit JSON non disponibile per r/{source.subreddit}, provo RSS: {json_exc}")
        rss_url = (
            f"https://www.reddit.com/r/{source.subreddit}/search.rss?"
            f"q={query}&restrict_sr=on&sort=new&t={cfg.get('reddit_days','month')}"
        )
        rr = http_get(session, rss_url)
        root = ET.fromstring(rr.text)
        entries = root.findall(".//{*}entry")[:40]
        for entry in entries:
            title_node = entry.find("{*}title")
            content_node = entry.find("{*}content")
            if content_node is None:
                content_node = entry.find("{*}summary")
            link_node = entry.find("{*}link")
            title = "" if title_node is None else "".join(title_node.itertext()).strip()
            body = "" if content_node is None else "".join(content_node.itertext()).strip()
            post_url = rss_url if link_node is None else link_node.attrib.get("href", rss_url)
            post_html = f"<h1>{title}</h1><div>{body}</div>"
            candidates.extend(extract_candidates_html(source.game, post_html, source, post_url))
        return candidates, 1

    return candidates, 1


def merge_candidates(candidates: Iterable[Candidate]) -> dict[tuple[str, str], dict]:
    merged: dict[tuple[str, str], dict] = {}
    rank_map = {"official": 3, "secondary": 2, "community": 1}
    weight_map = {"official": 3.0, "secondary": 2.0, "community": 0.5}

    for c in candidates:
        key = (c.game, c.normalized)
        if not c.normalized:
            continue
        item = merged.setdefault(
            key,
            {
                "game": c.game,
                "code": c.code,
                "normalized": c.normalized,
                "rewards": "",
                "status": "active",
                "expires_at": "",
                "expiry_source_kind": "",
                "sources": [],
                "confirmations": 0,
                "negatives": 0,
                "reward_rank": -1,
                "code_rank": -1,
                "source_states": {},
            },
        )

        src_key = (c.source_name, c.source_url)
        if not any((src["name"], src["url"]) == src_key for src in item["sources"]):
            item["sources"].append({"name": c.source_name, "url": c.source_url, "kind": c.source_kind})

        rank = rank_map.get(c.source_kind, 0)
        # Important for case-sensitive games such as Aniimo: preserve spelling from
        # the most authoritative source, not from whichever source happened to run first.
        if rank > item["code_rank"]:
            item["code"] = c.code
            item["code_rank"] = rank
        if c.reward and (rank > item["reward_rank"] or (rank == item["reward_rank"] and len(c.reward) > len(item["rewards"]))):
            item["rewards"] = c.reward
            item["reward_rank"] = rank

        state = item["source_states"].get(c.source_name)
        # Multiple posts/pages from the same source do not get multiple votes.
        # If the same source contains both an active and historical expired occurrence,
        # prefer the current active occurrence.
        if state is None or (state[1] != "active" and c.status == "active"):
            item["source_states"][c.source_name] = (c.source_kind, c.status)

        if c.expires_at:
            # Prefer an official expiry over tracker/community dates. When
            # equally authoritative sources disagree, use the earlier deadline
            # instead of silently keeping a potentially expired code active.
            prior_kind = item["expiry_source_kind"]
            if (
                not item["expires_at"]
                or (c.source_kind == "official" and prior_kind != "official")
                or (c.source_kind == prior_kind and c.expires_at < item["expires_at"])
            ):
                item["expires_at"] = c.expires_at
                item["expiry_source_kind"] = c.source_kind
        item["confirmations"] = max(item["confirmations"], c.reddit_confirmations)
        item["negatives"] = max(item["negatives"], c.reddit_negatives)

    for item in merged.values():
        unique_sources = {name: kind_status[0] for name, kind_status in item["source_states"].items()}
        kinds = list(unique_sources.values())
        official = "official" in kinds
        source_count = len(unique_sources)
        positives = item["confirmations"]
        negatives = item["negatives"]

        def editorial_group(name: str) -> str:
            # Verified 2026: Destructoid and Pro Game Guides are GAMURS titles.
            # Their articles may be separate, but they are not independent
            # publishing organizations for the stricter auto-notify threshold.
            if "destructoid" in name.lower() or "pro game guides" in name.lower():
                return "publisher:gamurs"
            return "source:" + name.casefold()

        secondary_count = len({editorial_group(name) for name, kind in unique_sources.items() if kind == "secondary"})
        community_count = sum(1 for kind in kinds if kind == "community")

        if official:
            score, conf = 100, "UFFICIALE"
        elif secondary_count >= 2:
            score, conf = 90, "CONFERMATO (2+ fonti note)"
        elif secondary_count >= 1 and community_count >= 1:
            score, conf = 80, "RISCONTRO MISTO (fonte nota + community)"
        elif community_count >= 2:
            score, conf = 70, "CONFERMATO COMMUNITY (2 fonti)"
        elif secondary_count >= 1:
            score, conf = 60, "SEGNALATO (fonte nota)"
        elif positives >= 3 and positives > negatives:
            score, conf = 65, "COMMUNITY CONFERMATA"
        else:
            score, conf = 30, "COMMUNITY / DA VERIFICARE"

        if negatives >= 3 and negatives > positives:
            score = min(score, 25)
            conf = "CONTESTATO / DA VERIFICARE"

        active_weight = 0.0
        expired_weight = 0.0
        for kind, status in item["source_states"].values():
            if status == "expired":
                expired_weight += weight_map.get(kind, 0.5)
            else:
                active_weight += weight_map.get(kind, 0.5)
        item["status"] = "expired" if expired_weight >= active_weight and expired_weight > 0 else "active"

        if item["expires_at"]:
            try:
                if expiry_has_passed(item["game"], item["expires_at"]):
                    item["status"] = "expired"
            except ValueError:
                pass
        item["score"] = score
        item["confidence"] = conf
        item["source_count"] = source_count
        item.pop("source_states", None)
        item.pop("reward_rank", None)
        item.pop("code_rank", None)
    return merged


def upsert_candidates(con: sqlite3.Connection, merged: dict[tuple[str, str], dict]) -> tuple[int, list[sqlite3.Row]]:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    inserted = 0
    new_ids: list[int] = []
    for item in merged.values():
        row = con.execute(
            "SELECT * FROM codes WHERE game=? AND normalized=?",
            (item["game"], item["normalized"]),
        ).fetchone()
        if row is None:
            sources_json = json.dumps(item["sources"], ensure_ascii=False)
            cur = con.execute(
                """
                INSERT INTO codes
                (game, code, normalized, rewards, status, confidence, score, first_seen, last_seen,
                 expires_at, used, notified, notified_pc, notified_phone, source_count,
                 confirmations, negatives, miss_count, sources_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?, ?, ?, 0, ?)
                """,
                (
                    item["game"], item["code"], item["normalized"], item["rewards"], item["status"],
                    item["confidence"], item["score"], now, now, item["expires_at"], item["source_count"],
                    item["confirmations"], item["negatives"], sources_json,
                ),
            )
            inserted += 1
            new_ids.append(cur.lastrowid)
            continue

        # Preserve the user's state and previously verified evidence when a site is
        # temporarily unreachable or stops showing a code on one particular run.
        try:
            old_sources = json.loads(row["sources_json"] or "[]")
        except Exception:
            old_sources = []
        source_map = {(src.get("name", ""), src.get("url", "")): src for src in old_sources if isinstance(src, dict)}
        for src in item["sources"]:
            source_map[(src.get("name", ""), src.get("url", ""))] = src
        sources_json = json.dumps(list(source_map.values()), ensure_ascii=False)

        # Confidence describes *current* evidence, never a historical maximum:
        # otherwise two transient/incorrect reports could make a bogus code
        # permanently "confirmed", even after they disappear.
        score = int(item["score"] or 0)
        confidence = item["confidence"]
        code = item["code"]
        if item["game"] == GAME_ANIIMO and row["code"] != item["code"]:
            # Do not overwrite casing from an authoritative old observation with
            # a low-trust repost which happened to capitalize it differently.
            old_sources_kinds = {s.get("kind") for s in old_sources if isinstance(s, dict)}
            new_sources_kinds = {s.get("kind") for s in item["sources"]}
            if ("official" in old_sources_kinds and "official" not in new_sources_kinds) or (
                "secondary" in old_sources_kinds and new_sources_kinds == {"community"}
            ):
                code = row["code"]

        reward = item["rewards"] if len(item["rewards"] or "") >= len(row["rewards"] or "") else row["rewards"]
        old_expiry = row["expires_at"] or ""
        new_expiry = item["expires_at"] or ""
        official_new_expiry = item.get("expiry_source_kind") == "official"
        # A stored deadline must not disappear on a weak repost. Only an
        # explicitly dated *official* extension can supersede an old deadline.
        expires = old_expiry or new_expiry
        extended = bool(
            old_expiry and new_expiry and official_new_expiry
            and new_expiry > old_expiry
        )
        if extended:
            expires = new_expiry
        status = item["status"]
        if row["used"] and row["status"] == "invalid":
            status = "invalid"
        elif row["status"] == "expired" and status == "active":
            if old_expiry:
                # Expired coupons do not become active just because an old
                # news article or a Reddit post still mentions them.
                # A new *official* deadline beyond the old one is required.
                if not extended:
                    status = "expired"
            else:
                # Without a known end date, demand stronger fresh corroboration
                # before undoing the explicit expired classification.
                kinds_now = {s.get("kind") for s in item["sources"]}
                if not ("official" in kinds_now or (
                    "secondary" in kinds_now and score >= 85
                )):
                    status = "expired"
        elif row["status"] in {"stale", "review"} and status == "active":
            kinds_now = {s.get("kind") for s in item["sources"]}
            reliable = "official" in kinds_now or (
                "secondary" in kinds_now and (row["status"] == "stale" or score >= 85)
            )
            if not reliable:
                status = row["status"]
        if expires:
            try:
                if expiry_has_passed(item["game"], expires):
                    status = "expired"
            except ValueError:
                pass

        # A code that was already notified must never become a duplicate alert merely
        # because it disappeared and later reappeared. The user explicitly controls
        # personal redemption state with "Segna come usato".
        notified_pc = int(row["notified_pc"] or 0)
        notified_phone = int(row["notified_phone"] or 0)

        con.execute(
            """
            UPDATE codes SET code=?, rewards=?, status=?, confidence=?, score=?, last_seen=?,
                expires_at=?, source_count=?, confirmations=?, negatives=?, sources_json=?,
                notified_pc=?, notified_phone=?
            WHERE id=?
            """,
            (
                code, reward, status, confidence, score, now, expires,
                int(item["source_count"] or 0),
                int(item["confirmations"] or 0),
                int(item["negatives"] or 0),
                sources_json, notified_pc, notified_phone, row["id"],
            ),
        )
    con.commit()
    rows = []
    if new_ids:
        marks = ",".join("?" for _ in new_ids)
        rows = con.execute(f"SELECT * FROM codes WHERE id IN ({marks})", new_ids).fetchall()
    return inserted, rows


def update_missing_codes(
    con: sqlite3.Connection,
    merged: dict[tuple[str, str], dict],
    successful_source_names: set[str],
    stale_after_misses: int = 3,
) -> int:
    """Hide codes that disappear repeatedly from a tracker that previously listed them.

    Discovery sources (official news/Reddit) are intentionally ignored for staleness:
    an old announcement falling out of a news feed does not prove that a code expired.
    """
    present = set(merged.keys())
    stale_marked = 0
    rows = con.execute("SELECT * FROM codes WHERE used=0 AND status='active'").fetchall()
    for row in rows:
        key = (row["game"], row["normalized"])
        current = merged.get(key)
        # An official statement still reporting the coupon is decisive.  A
        # Reddit repost is NOT proof that a tracker still lists an old code.
        if current and any(src.get("kind") == "official" for src in current["sources"]):
            if int(row["miss_count"] or 0):
                con.execute("UPDATE codes SET miss_count=0 WHERE id=?", (row["id"],))
            continue
        try:
            sources = json.loads(row["sources_json"] or "[]")
        except Exception:
            sources = []
        tracker_names = {
            src.get("name", "") for src in sources
            if isinstance(src, dict) and src.get("kind") == "secondary"
        }
        if not (tracker_names & successful_source_names):
            continue
        listed_by_tracker_now = current and any(
            src.get("kind") == "secondary" and src.get("name") in tracker_names
            for src in current["sources"]
        )
        if listed_by_tracker_now:
            if int(row["miss_count"] or 0):
                con.execute("UPDATE codes SET miss_count=0 WHERE id=?", (row["id"],))
            continue
        misses = int(row["miss_count"] or 0) + 1
        new_status = "stale" if misses >= stale_after_misses else "active"
        con.execute("UPDATE codes SET miss_count=?, status=? WHERE id=?", (misses, new_status, row["id"]))
        if new_status == "stale":
            stale_marked += 1
    con.commit()
    return stale_marked


def expire_stored_codes(con: sqlite3.Connection) -> int:
    """Enforce explicit deadlines with the appropriate game clock."""
    ids = [(row["id"],) for row in con.execute(
        "SELECT id, game, expires_at FROM codes WHERE status='active' AND expires_at!=''"
    ) if expiry_has_passed(row["game"], row["expires_at"])]
    if ids:
        con.executemany("UPDATE codes SET status='expired' WHERE id=?", ids)
        con.commit()
    return len(ids)


def run_check(cfg: Optional[dict] = None) -> dict:
    """Skip overlapping manual/scheduled scans, preserving notifications and DB state."""
    with operation_lock(DATA_DIR, "scan") as acquired:
        if not acquired:
            return {
                "ok_sources": 0, "failed_sources": 0, "failures": [],
                "candidates": 0, "inserted": 0, "stale_marked": 0,
                "expired_marked": 0, "new_rows": [], "notify_rows": [],
                "notify_rows_pc": [], "notify_rows_phone": [],
                "skipped": True, "reason": "Controllo gia' in corso su un'altra istanza",
            }
        return _run_check_unlocked(cfg)


def _run_check_unlocked(cfg: Optional[dict] = None) -> dict:
    cfg = cfg or load_config()
    all_candidates: list[Candidate] = []
    failures: list[str] = []
    successful_source_names: set[str] = set()
    details: list[tuple[str, str, str, int, int, str]] = []

    # At most one concurrent request group per host, and only three workers.
    # A separate Session per source avoids thread-shared requests.Session state.
    host_locks: dict[str, threading.Lock] = {}
    for source in SOURCES:
        host = urlparse(source.url).hostname or ("reddit.com" if source.mode == "reddit" else source.name)
        host_locks.setdefault(host.lower(), threading.Lock())

    def scan_one(source: Source) -> tuple[list[Candidate], int]:
        host = (urlparse(source.url).hostname or
                ("reddit.com" if source.mode == "reddit" else source.name)).lower()
        with host_locks[host]:
            with build_http_session() as session:
                if source.mode == "page":
                    return fetch_page_source(session, source)
                if source.mode == "crawl":
                    return fetch_crawl_source(session, source)
                if source.mode == "reddit":
                    return fetch_reddit_source(session, source, cfg)
                raise ValueError(f"Modalita' fonte non supportata: {source.mode}")

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with ThreadPoolExecutor(max_workers=MAX_SCAN_WORKERS) as executor:
        pending = {executor.submit(scan_one, source): (source, time.monotonic())
                   for source in SOURCES}
        for future in as_completed(pending):
            source, start_clock = pending[future]
            elapsed = int((time.monotonic() - start_clock) * 1000)
            try:
                found, _ = future.result()
                all_candidates.extend(found)
                successful_source_names.add(source.name)
                details.append((started_at, source.name, source.game, len(found), elapsed, ""))
                log(f"OK {source.name}: {len(found)} candidati")
            except Exception as exc:
                message = f"{source.name}: {exc}"
                failures.append(message)
                details.append((started_at, source.name, source.game, 0, elapsed, str(exc)[:500]))
                log(f"ERRORE {message}")

    merged = merge_candidates(all_candidates)
    con = connect_db()
    try:
        inserted, new_rows = upsert_candidates(con, merged)
        stale_marked = update_missing_codes(con, merged, successful_source_names)
        expired_marked = expire_stored_codes(con)
        for checked_at, name, game, count, elapsed, error in details:
            con.execute(
                "INSERT INTO source_checks(checked_at, source_name, game, status, candidates, elapsed_ms, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (checked_at, name, game, "error" if error else "ok", count, elapsed, error),
            )
        # Keep diagnostics bounded on long-lived installations.
        con.execute("DELETE FROM source_checks WHERE id NOT IN "
                    "(SELECT id FROM source_checks ORDER BY id DESC LIMIT 3000)")
        con.execute(
            "INSERT INTO checks (checked_at, ok_sources, failed_sources, candidates, error_summary) VALUES (?, ?, ?, ?, ?)",
            (started_at, len(successful_source_names), len(failures), len(merged),
             " | ".join(failures)[:4000]),
        )
        con.commit()

        threshold = int(cfg.get("notify_min_score", 85))
        base_sql = "SELECT * FROM codes WHERE used=0 AND status='active' AND score>=?"
        pc_rows: list[sqlite3.Row] = []
        phone_rows: list[sqlite3.Row] = []
        if cfg.get("notify_pc"):
            pc_rows = [r for r in con.execute(base_sql + " AND notified_pc=0 ORDER BY score DESC, first_seen DESC", (threshold,))
                       if (r["game"], r["normalized"]) in merged]
        if cfg.get("notify_phone") and cfg.get("ntfy_topic"):
            phone_rows = [r for r in con.execute(base_sql + " AND notified_phone=0 ORDER BY score DESC, first_seen DESC", (threshold,))
                          if (r["game"], r["normalized"]) in merged]
    finally:
        con.close()

    union = {r["id"]: r for r in pc_rows}
    union.update({r["id"]: r for r in phone_rows})
    return {
        "ok_sources": len(successful_source_names),
        "failed_sources": len(failures), "failures": failures,
        "candidates": len(merged), "inserted": inserted,
        "stale_marked": stale_marked, "expired_marked": expired_marked,
        "new_rows": new_rows, "notify_rows": list(union.values()),
        "notify_rows_pc": pc_rows, "notify_rows_phone": phone_rows,
        "skipped": False,
    }

def deliver_notifications(result: dict, cfg: dict) -> dict:
    """Serialize delivery and re-check flags under a cross-process lock.

    Failures leave flags unset for a later eligible scan. A crash after a provider
    accepts a notification but before commit can still cause one retry.
    """
    delivered = {"pc": 0, "phone": 0}
    with operation_lock(DATA_DIR, "notifications", timeout=5) as acquired:
        if not acquired:
            log("Notifiche rimandate: un'altra istanza le sta inviando")
            return delivered
        for channel in ("pc", "phone"):
            incoming = result.get("notify_rows_" + channel, [])
            if not incoming:
                continue
            con = connect_db()
            try:
                column = "notified_pc" if channel == "pc" else "notified_phone"
                eligible = []
                for row in incoming:
                    fresh = con.execute("SELECT * FROM codes WHERE id=?", (row["id"],)).fetchone()
                    if fresh is not None and not fresh[column] and not fresh["used"] and fresh["status"] == "active":
                        eligible.append(fresh)
                ok = (notify_pc(eligible) if channel == "pc"
                      else notify_phone(eligible, cfg)) if eligible else False
                if ok:
                    con.executemany(f"UPDATE codes SET {column}=1 WHERE id=?",
                                    [(r["id"],) for r in eligible])
                    con.commit()
                    delivered[channel] = len(eligible)
            finally:
                con.close()
    return delivered


def notify_pc(rows: list[sqlite3.Row]) -> bool:
    if not rows:
        return True
    try:
        from winotify import Notification
        title = f"{APP_NAME}: {len(rows)} nuovi codici"
        lines = []
        for r in rows[:5]:
            lines.append(f"{r['game']}: {r['code']} — {r['rewards'] or r['confidence']}")
        if len(rows) > 5:
            lines.append(f"+ altri {len(rows)-5}")
        toast = Notification(app_id=APP_NAME, title=title, msg="\n".join(lines), duration="long")
        toast.show()
        return True
    except Exception as exc:
        log(f"Notifica PC fallita: {exc}")
        return False


def publish_ntfy(cfg: dict, title: str, message: str) -> bool:
    if not cfg.get("ntfy_topic"):
        return False
    server = str(cfg.get("ntfy_server") or "https://ntfy.sh").rstrip("/")
    topic = re.sub(r"[^A-Za-z0-9_-]", "", str(cfg.get("ntfy_topic")))
    if not topic:
        return False
    try:
        requests.post(
            f"{server}/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": "high", "Tags": "video_game,gift"},
            timeout=12,
        ).raise_for_status()
        return True
    except Exception as exc:
        # requests' exception messages can include the URL (and secret topic).
        log(f"Notifica telefono fallita: {str(exc).replace(topic, '[topic nascosto]')}")
        return False


def notify_phone(rows: list[sqlite3.Row], cfg: dict) -> bool:
    if not rows or not cfg.get("notify_phone") or not cfg.get("ntfy_topic"):
        return True if not rows else False
    body_lines = []
    for r in rows[:8]:
        reward = r["rewards"] or r["confidence"]
        body_lines.append(f"{r['game']}: {r['code']} — {reward}")
    if len(rows) > 8:
        body_lines.append(f"+ altri {len(rows)-8}")
    return publish_ntfy(cfg, f"{len(rows)} nuovi codici gioco", "\n".join(body_lines))


def mark_channel_notified(rows: list[sqlite3.Row], channel: str) -> None:
    if not rows:
        return
    if channel not in {"pc", "phone"}:
        raise ValueError("Canale notifica non valido")
    column = "notified_pc" if channel == "pc" else "notified_phone"
    con = connect_db()
    con.executemany(f"UPDATE codes SET {column}=1 WHERE id=?", [(r["id"],) for r in rows])
    con.commit()
    con.close()


def update_code_state(con: sqlite3.Connection, row_ids: list[int], action: str) -> int:
    """Update redeemed codes in one transaction while preserving code history."""
    if action not in {"used", "invalid", "restore"}:
        raise ValueError("Azione sui codici non valida")
    if any(type(row_id) is not int or row_id <= 0 for row_id in row_ids):
        raise ValueError("ID codice non valido")
    ids = list(dict.fromkeys(row_ids))
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    if action == "used":
        sql = f"UPDATE codes SET used=1 WHERE used=0 AND id IN ({placeholders})"
    elif action == "invalid":
        sql = (f"UPDATE codes SET status='invalid', used=1 WHERE "
               f"(status!='invalid' OR used=0) AND id IN ({placeholders})")
    else:
        # Restore only genuinely redeemed codes. Never reactivate invalid ones.
        sql = (f"UPDATE codes SET used=0 WHERE used=1 AND status!='invalid' "
               f"AND id IN ({placeholders})")
    with con:
        cursor = con.execute(sql, ids)
    return cursor.rowcount


def redeem_url_for(game: str, code: str) -> Optional[str]:
    if game == GAME_GENSHIN:
        return "https://genshin.hoyoverse.com/en/gift?code=" + quote_plus(code)
    return None


def current_launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --check --notify --headless'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    pyexe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{pyexe}" "{Path(__file__).resolve()}" --check --notify --headless'


def install_daily_task(schedule_time: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "La pianificazione automatica è disponibile solo su Windows."
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule_time):
        return False, "Orario non valido. Usa HH:MM."
    cmd = current_launch_command()
    daily_args = [
        "schtasks", "/Create", "/SC", "DAILY", "/TN", f"{APP_NAME} Daily Check",
        "/TR", cmd, "/ST", schedule_time, "/F",
    ]
    login_args = [
        "schtasks", "/Create", "/SC", "ONLOGON", "/TN", f"{APP_NAME} Login Catch-up",
        "/TR", cmd, "/F",
    ]
    try:
        daily = subprocess.run(daily_args, capture_output=True, text=True, timeout=20)
        if daily.returncode != 0:
            return False, (daily.stderr or daily.stdout or "Errore sconosciuto").strip()
        # Best-effort catch-up: if the PC was off/asleep at the scheduled time, the
        # next user logon performs another deduplicated check. Failure here must not
        # invalidate a correctly created daily task.
        login = subprocess.run(login_args, capture_output=True, text=True, timeout=20)
        if login.returncode == 0:
            return True, f"Controllo giornaliero impostato alle {schedule_time} + recupero all'accesso a Windows."
        warning = (login.stderr or login.stdout or "errore sconosciuto").strip()
        log(f"Task catch-up all'accesso non creato: {warning}")
        return True, f"Controllo giornaliero impostato alle {schedule_time}. Recupero all'accesso non disponibile: {warning}"
    except Exception as exc:
        return False, str(exc)


def remove_daily_task() -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponibile solo su Windows."
    results = []
    errors = []
    try:
        for task_name in (f"{APP_NAME} Daily Check", f"{APP_NAME} Login Catch-up"):
            p = subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True, text=True, timeout=20)
            if p.returncode == 0:
                results.append(task_name)
            else:
                msg = (p.stderr or p.stdout or "").strip()
                # A missing optional task is not a fatal removal error.
                if msg:
                    errors.append(f"{task_name}: {msg}")
        if results:
            return True, "Controlli automatici rimossi."
        if errors:
            return False, " | ".join(errors)
        return True, "Nessun controllo automatico presente."
    except Exception as exc:
        return False, str(exc)


def gui_main() -> None:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    import secrets

    cfg = load_config()
    con = connect_db()
    con.close()

    root = tk.Tk()
    root.title(f"{APP_NAME} {APP_VERSION}")
    root.geometry("1160x680")
    root.minsize(920, 560)

    status_var = tk.StringVar(value="Pronto. I codici usati sono nascosti per impostazione predefinita.")
    show_used = tk.BooleanVar(value=False)
    show_unverified = tk.BooleanVar(value=bool(cfg.get("show_unverified", False)))
    show_archived = tk.BooleanVar(value=False)
    game_filter = tk.StringVar(value="Tutti")
    search_var = tk.StringVar(value="")
    order = {"column": "", "desc": False}

    top = ttk.Frame(root, padding=10)
    top.pack(fill="x")
    ttk.Label(top, text="GameCode Sentinel", font=("Segoe UI", 18, "bold")).pack(side="left")
    ttk.Label(top, text="  Codici reali, deduplicati, con livello di verifica", font=("Segoe UI", 10)).pack(side="left", pady=(6, 0))

    controls = ttk.Frame(root, padding=(10, 0, 10, 8))
    controls.pack(fill="x")

    check_btn = ttk.Button(controls, text="Controlla ora")
    check_btn.pack(side="left", padx=(0, 6))
    ttk.Button(controls, text="Copia codice", command=lambda: copy_selected()).pack(side="left", padx=3)
    ttk.Button(controls, text="Riscatta / istruzioni", command=lambda: redeem_selected()).pack(side="left", padx=3)
    ttk.Button(controls, text="Segna usati", command=lambda: mark_selected("used")).pack(side="left", padx=3)
    ttk.Button(controls, text="Segna non valido", command=lambda: mark_selected("invalid")).pack(side="left", padx=3)
    ttk.Button(controls, text="Fonti", command=lambda: show_sources_selected()).pack(side="left", padx=3)
    ttk.Button(controls, text="Impostazioni", command=lambda: open_settings()).pack(side="right")
    ttk.Button(controls, text="Stato fonti", command=lambda: show_source_health()).pack(side="right", padx=5)
    ttk.Button(controls, text="Backup", command=lambda: show_backups()).pack(side="right", padx=5)

    filters = ttk.Frame(root, padding=(10, 0, 10, 8))
    filters.pack(fill="x")
    ttk.Label(filters, text="Gioco:").pack(side="left")
    combo = ttk.Combobox(filters, state="readonly", width=20, textvariable=game_filter, values=["Tutti"] + GAMES)
    combo.pack(side="left", padx=(5, 14))
    ttk.Label(filters, text="Cerca:").pack(side="left")
    ttk.Entry(filters, textvariable=search_var, width=19).pack(side="left", padx=(5, 12))
    ttk.Checkbutton(filters, text="Mostra usati", variable=show_used, command=lambda: refresh()).pack(side="left", padx=5)
    ttk.Checkbutton(filters, text="Mostra da verificare", variable=show_unverified, command=lambda: refresh()).pack(side="left", padx=5)
    ttk.Checkbutton(filters, text="Mostra storico/scaduti", variable=show_archived, command=lambda: refresh()).pack(side="left", padx=5)

    bulk_controls = ttk.Frame(root, padding=(10, 0, 10, 8))
    bulk_controls.pack(fill="x")
    ttk.Label(bulk_controls, text="Selezione: Ctrl+clic, Maiusc+clic oppure Ctrl+A").pack(side="left")
    ttk.Button(bulk_controls, text="Seleziona tutti visibili",
               command=lambda: select_all_visible()).pack(side="left", padx=(12, 4))
    ttk.Button(bulk_controls, text="Deseleziona",
               command=lambda: clear_selection()).pack(side="left", padx=4)
    ttk.Button(bulk_controls, text="Ripristina usati",
               command=lambda: mark_selected("restore")).pack(side="right")

    cols = ("game", "code", "status", "reward", "verify", "expires", "seen", "last", "sources")
    tree = ttk.Treeview(root, columns=cols, show="headings", selectmode="extended")
    headings = {
        "game": "Gioco", "code": "Codice", "status": "Stato", "reward": "Ricompensa", "verify": "Verifica",
        "expires": "Scadenza (IT AION)", "seen": "Prima rilevazione", "last": "Ultima vista", "sources": "Fonti",
    }
    widths = {"game": 110, "code": 170, "status": 130, "reward": 310, "verify": 185, "expires": 145, "seen": 135, "last": 135, "sources": 60}
    for c in cols:
        tree.heading(c, text=headings[c], command=lambda col=c: sort_by(col))
        tree.column(c, width=widths[c], anchor="w")
    tree.pack(fill="both", expand=True, padx=10)
    tree.tag_configure("official", background="#e8f5e9")
    tree.tag_configure("confirmed", background="#eef6ff")
    tree.tag_configure("unverified", background="#fff8e1")
    tree.tag_configure("used", foreground="#777777")
    tree.tag_configure("archived", foreground="#888888")

    sb = ttk.Scrollbar(tree, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")

    bottom = ttk.Frame(root, padding=10)
    bottom.pack(fill="x")
    ttk.Label(bottom, textvariable=status_var).pack(side="left")
    selection_var = tk.StringVar(value="Selezionati: 0")
    ttk.Label(bottom, textvariable=selection_var).pack(side="left", padx=(12, 0))
    ttk.Label(bottom, text="Verde=ufficiale · Azzurro=confermato · Giallo=da verificare", foreground="#555").pack(side="right")

    def selected_ids() -> list[int]:
        return [int(item) for item in tree.selection()]

    def selected_id() -> Optional[int]:
        ids = selected_ids()
        return ids[0] if len(ids) == 1 else None

    def update_selection_count(event=None):
        selection_var.set(f"Selezionati: {len(tree.selection())}")

    def select_all_visible():
        items = tree.get_children("")
        if items:
            tree.selection_set(*items)
            tree.focus(items[0])
        update_selection_count()

    def clear_selection():
        tree.selection_remove(*tree.selection())
        update_selection_count()

    def select_all_shortcut(event):
        select_all_visible()
        return "break"

    def get_row(row_id: int):
        con = connect_db()
        row = con.execute("SELECT * FROM codes WHERE id=?", (row_id,)).fetchone()
        con.close()
        return row

    def show_backups():
        window = tk.Toplevel(root)
        window.title("Backup e ripristino")
        window.geometry("540x180")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Copie locali dello storico codici; le ultime sette sono conservate.").pack(pady=10)

        def create():
            with operation_lock(DATA_DIR, "scan") as allowed:
                if not allowed:
                    messagebox.showwarning(APP_NAME, "Scansione in corso.", parent=window)
                    return
                try:
                    path = backup_sqlite(DB_PATH, force=True)
                    messagebox.showinfo(APP_NAME, f"Backup salvato: {path}", parent=window)
                except Exception as exc:
                    messagebox.showerror(APP_NAME, str(exc), parent=window)

        ttk.Button(frame, text="Crea backup", command=create).pack(side="left", padx=8)
        ttk.Button(frame, text="Chiudi", command=window.destroy).pack(side="right")

    def show_source_health():
        con = connect_db()
        try:
            data = con.execute(
                "SELECT a.* FROM source_checks a WHERE id=("
                "SELECT MAX(id) FROM source_checks WHERE source_name=a.source_name)"
                " ORDER BY game, source_name"
            ).fetchall()
        finally:
            con.close()
        window = tk.Toplevel(root)
        window.title("Diagnostica fonti")
        window.geometry("1010x440")
        columns = ("gioco", "fonte", "stato", "codici", "durata", "data", "errore")
        table = ttk.Treeview(window, columns=columns, show="headings")
        for col, width in zip(columns, (120, 240, 75, 70, 65, 175, 240)):
            table.heading(col, text=col.capitalize())
            table.column(col, width=width)
        table.pack(fill="both", expand=True, padx=10, pady=10)
        for row in data:
            table.insert("", "end", values=(
                row["game"], row["source_name"], row["status"],
                row["candidates"], row["elapsed_ms"], row["checked_at"][:19], row["error"]
            ))
        ttk.Button(window, text="Chiudi", command=window.destroy).pack(pady=5)

    def sort_by(col):
        if order["column"] == col:
            order["desc"] = not order["desc"]
        else:
            order["column"], order["desc"] = col, False
        refresh()

    def refresh():
        for i in tree.get_children():
            tree.delete(i)
        con = connect_db()
        expire_stored_codes(con)
        sql = "SELECT * FROM codes WHERE 1=1"
        params = []
        if not show_used.get():
            sql += " AND used=0"
        if game_filter.get() != "Tutti":
            sql += " AND game=?"
            params.append(game_filter.get())
        if search_var.get().strip():
            sql += " AND (instr(lower(code), lower(?)) > 0 OR instr(lower(rewards), lower(?)) > 0)"
            params.extend([search_var.get().strip()] * 2)
        if not show_archived.get():
            sql += " AND status='active'"
        if not show_unverified.get():
            sql += " AND (score>=85 OR status!='active')"
        columns = {"game": "game", "code": "code", "status": "status",
                   "reward": "rewards", "verify": "score", "expires": "expires_at",
                   "seen": "first_seen", "last": "last_seen", "sources": "source_count"}
        col = columns.get(order["column"])
        if col:
            sql += " ORDER BY " + col + (" DESC" if order["desc"] else " ASC")
        else:
            sql += " ORDER BY used ASC, CASE WHEN status='active' THEN 0 ELSE 1 END, score DESC, first_seen DESC"
        rows = con.execute(sql, params).fetchall()
        con.close()
        for r in rows:
            if r["status"] != "active":
                tag = "archived"
            elif r["used"]:
                tag = "used"
            elif r["score"] >= 100:
                tag = "official"
            elif r["score"] >= 85:
                tag = "confirmed"
            else:
                tag = "unverified"
            try:
                src_count = len(json.loads(r["sources_json"] or "[]"))
            except Exception:
                src_count = r["source_count"]
            seen = (r["first_seen"] or "").replace("T", " ")[:16]
            display_status = {"active": "Segnalato (non garantito)", "expired": "Scaduto", "stale": "Non più rilevato",
                              "review": "Da riverificare", "invalid": "Non valido"}.get(r["status"], r["status"])
            tree.insert("", "end", iid=str(r["id"]), values=(
                r["game"], r["code"], display_status, r["rewards"] or "—", r["confidence"], r["expires_at"] or "—", seen, (r["last_seen"] or "").replace("T", " ")[:16], r["source_count"],
            ), tags=(tag,))
        status_var.set(f"{len(rows)} codici visibili. Database: {DB_PATH}")
        update_selection_count()

    def copy_selected():
        rid = selected_id()
        if rid is None:
            messagebox.showinfo(APP_NAME, "Seleziona un solo codice.")
            return
        r = get_row(rid)
        root.clipboard_clear()
        root.clipboard_append(r["code"])
        status_var.set(f"Copiato: {r['code']}")

    def mark_selected(action: str):
        ids = selected_ids()
        if not ids:
            messagebox.showinfo(APP_NAME, "Seleziona almeno un codice.")
            return
        actions = {
            "used": ("segnare come usati", "Segnati come usati"),
            "invalid": ("segnare come non validi", "Segnati come non validi"),
            "restore": ("ripristinare come non usati", "Ripristinati"),
        }
        if action not in actions:
            raise ValueError("Azione sui codici non valida")
        prompt, result_label = actions[action]
        if len(ids) > 1 and not messagebox.askyesno(
            APP_NAME,
            f"Vuoi {prompt} i {len(ids)} codici selezionati?\n"
            "L'operazione non elimina i codici dal database.",
            parent=root,
        ):
            return
        con = connect_db()
        try:
            changed = update_code_state(con, ids, action)
        finally:
            con.close()
        refresh()
        note = " I codici non validi non vengono riattivati." if action == "restore" else ""
        status_var.set(f"{result_label}: {changed} codici.{note}")

    def show_sources_selected():
        rid = selected_id()
        if rid is None:
            messagebox.showinfo(APP_NAME, "Seleziona un solo codice.")
            return
        r = get_row(rid)
        try:
            sources = json.loads(r["sources_json"] or "[]")
        except Exception:
            sources = []
        if not sources:
            messagebox.showinfo(APP_NAME, "Nessuna fonte salvata per questo codice.")
            return
        w = tk.Toplevel(root)
        w.title(f"Fonti - {r['code']}")
        w.geometry("760x360")
        w.transient(root)
        frm = ttk.Frame(w, padding=10); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"{r['game']} · {r['code']} · {r['confidence']}", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0,8))
        lb = tk.Listbox(frm, height=12)
        lb.pack(fill="both", expand=True)
        for src in sources:
            lb.insert("end", f"[{src.get('kind','')}] {src.get('name','')} — {src.get('url','')}")
        def open_src():
            sel = lb.curselection()
            if not sel:
                return
            url = sources[sel[0]].get("url", "")
            if url:
                webbrowser.open(url)
        bf = ttk.Frame(frm); bf.pack(fill="x", pady=(8,0))
        ttk.Button(bf, text="Apri fonte selezionata", command=open_src).pack(side="left")
        ttk.Button(bf, text="Chiudi", command=w.destroy).pack(side="right")
        lb.bind("<Double-1>", lambda e: open_src())

    def redeem_selected():
        rid = selected_id()
        if rid is None:
            messagebox.showinfo(APP_NAME, "Seleziona un solo codice.")
            return
        r = get_row(rid)
        if r["status"] != "active":
            messagebox.showwarning(APP_NAME, "Questo codice non è segnalato come attivo. Controlla le fonti prima di usarlo.")
            return
        root.clipboard_clear(); root.clipboard_append(r["code"])
        url = redeem_url_for(r["game"], r["code"])
        if url:
            webbrowser.open(url)
            messagebox.showinfo(APP_NAME, f"Ho aperto la pagina ufficiale e copiato {r['code']} negli appunti.\n\nDopo il riscatto premi 'Segna come usato'.")
        elif r["game"] == GAME_ANIIMO:
            messagebox.showinfo(APP_NAME, f"Codice copiato: {r['code']}\n\nAniimo: Settings → Account → Gift Code Redemption.\nDopo il riscatto premi 'Segna come usato'.")
        elif r["game"] == GAME_AION2:
            messagebox.showinfo(APP_NAME, f"Codice copiato: {r['code']}\n\nAION 2: Settings → Miscellaneous/Other → Account → Coupon Registration.\nDopo il riscatto premi 'Segna come usato'.")

    def do_check():
        check_btn.config(state="disabled")
        status_var.set("Controllo fonti in corso…")

        def worker():
            try:
                result = run_check(load_config())
                cfg2 = load_config()
                pc_rows = result["notify_rows_pc"]
                phone_rows = result["notify_rows_phone"]
                if not result.get("skipped"):
                    deliver_notifications(result, cfg2)
                msg = ("Controllo gia' in corso" if result.get("skipped") else
                       f"Controllo completato: {result['ok_sources']} fonti OK, {result['inserted']} nuovi codici")
                if result.get("stale_marked"):
                    msg += f", {result['stale_marked']} non più rilevati nascosti"
                if result["failed_sources"]:
                    msg += f", {result['failed_sources']} fonti non raggiunte"
                root.after(0, lambda: [refresh(), status_var.set(msg), check_btn.config(state="normal")])
            except Exception as exc:
                log(f"Check GUI error: {exc}")
                root.after(0, lambda: [status_var.set(f"Errore: {exc}"), check_btn.config(state="normal")])

        threading.Thread(target=worker, daemon=True).start()

    def open_settings():
        nonlocal cfg
        cfg = load_config()
        w = tk.Toplevel(root)
        w.title("Impostazioni")
        w.geometry("590x430")
        w.transient(root)
        w.grab_set()

        schedule = tk.StringVar(value=cfg.get("schedule_time", "08:00"))
        pc = tk.BooleanVar(value=bool(cfg.get("notify_pc", True)))
        phone = tk.BooleanVar(value=bool(cfg.get("notify_phone", False)))
        topic = tk.StringVar(value=cfg.get("ntfy_topic", ""))
        server = tk.StringVar(value=cfg.get("ntfy_server", "https://ntfy.sh"))
        min_score = tk.IntVar(value=int(cfg.get("notify_min_score", 85)))

        frm = ttk.Frame(w, padding=14); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Controllo automatico giornaliero", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,8))
        ttk.Label(frm, text="Ora (HH:MM):").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=schedule, width=10).grid(row=1, column=1, sticky="w")

        ttk.Checkbutton(frm, text="Notifica su Windows", variable=pc).grid(row=2, column=0, columnspan=2, sticky="w", pady=(12,2))
        ttk.Checkbutton(frm, text="Notifica sul telefono via ntfy", variable=phone).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(frm, text="Server ntfy:").grid(row=4, column=0, sticky="w", pady=(10,0))
        ttk.Entry(frm, textvariable=server, width=42).grid(row=4, column=1, columnspan=2, sticky="we", pady=(10,0))
        ttk.Label(frm, text="Topic privato:").grid(row=5, column=0, sticky="w", pady=(6,0))
        ttk.Entry(frm, textvariable=topic, width=42).grid(row=5, column=1, sticky="we", pady=(6,0))

        def gen_topic():
            topic.set("gcs-" + secrets.token_urlsafe(18).replace("-", "x").replace("_", "y"))

        def test_phone():
            test_cfg = {
                "ntfy_server": server.get().strip(),
                "ntfy_topic": topic.get().strip(),
            }
            if not test_cfg["ntfy_topic"]:
                messagebox.showwarning(APP_NAME, "Genera o inserisci prima un topic ntfy.", parent=w)
                return
            ok = publish_ntfy(test_cfg, "GameCode Sentinel - test", "Notifica di prova ricevuta correttamente.")
            if ok:
                messagebox.showinfo(APP_NAME, "Notifica di prova inviata. Controlla il telefono.", parent=w)
            else:
                messagebox.showwarning(APP_NAME, "Invio non riuscito. Controlla server, topic e connessione Internet.", parent=w)

        ttk.Button(frm, text="Genera", command=gen_topic).grid(row=5, column=2, padx=(6,0), pady=(6,0))
        ttk.Button(frm, text="Prova telefono", command=test_phone).grid(row=4, column=2, padx=(6,0), pady=(10,0))

        ttk.Label(frm, text="Notifica solo se punteggio ≥").grid(row=6, column=0, sticky="w", pady=(12,0))
        ttk.Spinbox(frm, from_=0, to=100, increment=5, textvariable=min_score, width=7).grid(row=6, column=1, sticky="w", pady=(12,0))
        ttk.Label(frm, text="85 = ufficiale o confermato da almeno 2 fonti editoriali indipendenti (consigliato)", foreground="#555").grid(row=7, column=0, columnspan=3, sticky="w")

        help_txt = (
            "Telefono: installa l'app ntfy sul telefono e iscriviti allo stesso topic. "
            "Il topic funziona come un indirizzo: usa quello casuale generato e non condividerlo."
        )
        ttk.Label(frm, text=help_txt, wraplength=535, foreground="#555").grid(row=8, column=0, columnspan=3, sticky="w", pady=(14,10))

        buttons = ttk.Frame(frm); buttons.grid(row=9, column=0, columnspan=3, sticky="we", pady=(8,0))

        def save_and_schedule():
            newcfg = load_config()
            newcfg.update({
                "schedule_time": schedule.get().strip(), "notify_pc": pc.get(), "notify_phone": phone.get(),
                "ntfy_server": server.get().strip(), "ntfy_topic": topic.get().strip(),
                "notify_min_score": int(min_score.get()),
            })
            save_config(newcfg)
            ok, msg = install_daily_task(newcfg["schedule_time"])
            if ok:
                messagebox.showinfo(APP_NAME, msg, parent=w)
            else:
                messagebox.showwarning(APP_NAME, "Impostazioni salvate, ma Task Scheduler non è stato configurato:\n" + msg, parent=w)
            w.destroy()

        ttk.Button(buttons, text="Salva + attiva controllo giornaliero", command=save_and_schedule).pack(side="left")
        ttk.Button(buttons, text="Rimuovi pianificazione", command=lambda: messagebox.showinfo(APP_NAME, remove_daily_task()[1], parent=w)).pack(side="left", padx=6)
        ttk.Button(buttons, text="Chiudi", command=w.destroy).pack(side="right")
        frm.columnconfigure(1, weight=1)

    combo.bind("<<ComboboxSelected>>", lambda e: refresh())
    search_var.trace_add("write", lambda *_: refresh())
    tree.bind("<Double-1>", lambda e: copy_selected())
    tree.bind("<<TreeviewSelect>>", update_selection_count)
    tree.bind("<Control-a>", select_all_shortcut)
    check_btn.config(command=do_check)
    refresh()
    root.after(750, do_check)  # first launch refreshes current codes immediately
    root.mainloop()


def cli_main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--version", action="store_true", help="Mostra la versione senza aprire GUI/database")
    parser.add_argument("--backup", action="store_true", help="Backup immediato")
    parser.add_argument("--game", choices=GAMES, help="Controlla solo un gioco")
    parser.add_argument("--report-json", type=Path, help="Salva rapporto della scansione in JSON")
    parser.add_argument("--check", action="store_true", help="Controlla le fonti e aggiorna il database")
    parser.add_argument("--notify", action="store_true", help="Invia notifiche per i nuovi codici affidabili")
    parser.add_argument("--headless", action="store_true", help="Non avvia la GUI")
    parser.add_argument("--install-task", action="store_true", help="Installa il controllo giornaliero")
    args = parser.parse_args()

    if args.version:
        if sys.stdout is not None:
            print(f"{APP_NAME} {APP_VERSION}")
        return 0

    cfg = load_config()
    connect_db().close()

    if args.backup:
        with operation_lock(DATA_DIR, "scan", timeout=5) as acquired:
            if not acquired:
                print("Backup non disponibile: scansione in corso")
                return 3
            print("Backup:", backup_sqlite(DB_PATH, force=True))
        return 0

    if args.install_task:
        ok, msg = install_daily_task(cfg.get("schedule_time", "08:00"))
        print(msg)
        return 0 if ok else 1

    if args.check:
        # --game filters only the scanning sources, not the stored database.
        if args.game:
            global SOURCES
            SOURCES = [source for source in SOURCES if source.game == args.game]
        result = run_check(cfg)
        if args.report_json:
            summary = {k: v for k, v in result.items()
                       if k not in {"new_rows", "notify_rows", "notify_rows_pc", "notify_rows_phone"}}
            summary["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            summary["game_filter"] = args.game or "all"
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.notify and not result.get("skipped"):
            deliver_notifications(result, cfg)
        if not args.headless:
            print(json.dumps({k: v for k, v in result.items() if not k.startswith("notify_rows") and k != "new_rows"}, ensure_ascii=False, indent=2))
        # If all sources failed, exit nonzero: otherwise a CI scan looks green
        # while having inspected nothing. Partial failure remains reportable.
        return 3 if result.get("skipped") else (2 if result["ok_sources"] == 0 else 0)

    if not args.headless:
        gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())

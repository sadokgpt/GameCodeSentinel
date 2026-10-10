"""Regression checks: origin dates, Reddit provenance and no false 'valid' claims."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import json

import app
from sentinel_freshness import (
    extract_page_dates, parse_publication_time, age_days, is_old_post,
)


def _timestamp(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _c(name, kind, days, status="active"):
    return app.Candidate(
        app.GAME_GENSHIN, "TESTABCD123", "60 primogems", name,
        f"https://example.com/{name}", kind, status=status,
        published_at=_timestamp(days),
    )


def test_article_meta_publication_precedes_updated_page():
    html = '''
      <meta property="article:published_time" content="2023-04-03T08:00:00Z">
      <meta property="article:modified_time" content="2026-10-09T09:00:00Z">
      <time datetime="2026-10-10">Sale</time>
      <p>Offer expires on 2026-12-01</p>'''
    published, updated = extract_page_dates(html)
    assert published == "2023-04-03T08:00:00+00:00"
    assert updated == "2026-10-09T09:00:00+00:00"


def test_jsonld_article_dates_and_unrelated_dates_ignored():
    html = '''
    <script type="application/ld+json">
      {"@graph": [{"@type": "WebSite", "name": "Example"}, {
       "@type": "NewsArticle", "datePublished": "2026-09-29T10:00:00Z",
       "dateModified": "2026-10-01T10:00:00Z"}]}
    </script><p>Offer expires in 2029</p>
    '''
    published, updated = extract_page_dates(html)
    assert published.startswith("2026-09-29")
    assert updated.startswith("2026-10-01")
    assert extract_page_dates("<p>Updated today! 2026-10-10</p>") == ("", "")


def test_reddit_epoch_and_unknown_future_dates_are_rejected():
    assert parse_publication_time(1609459200) == "2021-01-01T00:00:00+00:00"
    assert parse_publication_time("not a date") == ""
    assert parse_publication_time("2089-01-01") == ""
    assert parse_publication_time(None) == ""
    assert parse_publication_time(0) == ""
    assert age_days("") is None


def test_stale_official_post_is_review_not_expired_or_100_points():
    item = app.merge_candidates([_c("official-old", "official", 80)])
    rec = item[(app.GAME_GENSHIN, "TESTABCD123")]
    assert rec["status"] == "review"
    assert rec["score"] == 0
    assert rec["sources"][0]["published_at"]
    assert rec["confidence"].startswith("DATA POST")


def test_fresh_official_post_can_override_old_mention():
    item = app.merge_candidates([
        _c("official-old", "official", 100),
        _c("official-new", "official", 1),
    ])[(app.GAME_GENSHIN, "TESTABCD123")]
    assert item["status"] == "active"
    assert item["score"] == 100


def test_two_old_editorial_articles_do_not_confirm_code():
    item = app.merge_candidates([
        _c("A", "secondary", 200),
        _c("B", "secondary", 200),
    ])[(app.GAME_GENSHIN, "TESTABCD123")]
    assert item["score"] == 0
    assert item["status"] == "review"
    assert len(item["sources"]) == 2


def test_known_expiry_not_reopened_by_old_post(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    con = app.connect_db()
    expired = _c("already-expired", "official", 1, status="expired")
    app.upsert_candidates(con, app.merge_candidates([expired]))
    app.upsert_candidates(con, app.merge_candidates([_c("old-repost", "official", 80)]))
    rec = con.execute("SELECT status FROM codes WHERE code='TESTABCD123'").fetchone()
    assert rec["status"] == "expired"
    con.close()


def test_reddit_comment_uses_own_date_not_parent_post(monkeypatch):
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=300)).timestamp()
    recent = (now - timedelta(days=2)).timestamp()
    payload = [
        {"data": {"children": [{"kind": "t3", "data": {"title": "Old"}}]}},
        {"data": {"children": [
            {"kind": "t1", "data": {"body": "Gift code TESTABCD123",
                                     "created_utc": recent}},
            {"kind": "t1", "data": {"body": "Gift code NO123CDDD",
                                     "created_utc": old}},
        ]}},
    ]
    mock = Mock()
    mock.json.return_value = payload
    monkeypatch.setattr(app, "http_get", lambda sess, url: mock)
    found = app.reddit_comment_entries(Mock(), "/r/Genshin_Impact/comments/abc/something/")
    assert len(found) == 2
    assert age_days(found[0][1]) <= 3
    assert age_days(found[1][1]) >= 299


def test_age_boundary_is_explicit():
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    assert not is_old_post(app.GAME_GENSHIN, "2026-09-11T12:00:00Z", now=now)
    assert is_old_post(app.GAME_GENSHIN, "2026-09-08T12:00:00Z", now=now)
    assert not is_old_post(app.GAME_GENSHIN, "", now=now)


def test_preupgrade_active_history_is_quarantined_without_losing_user_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    monkeypatch.setattr(app, "LOG_PATH", tmp_path / "app.log")
    con = app.connect_db()
    recent_undated = app.Candidate(app.GAME_GENSHIN, "OLDHISTORY123", "",
                                   "Old tracker", "https://example.org",
                                   "secondary")
    app.upsert_candidates(con, app.merge_candidates([recent_undated]))
    con.execute("UPDATE codes SET notified_pc=1 WHERE normalized='OLDHISTORY123'")
    con.execute("DELETE FROM meta WHERE key='post_provenance_review_v160'")
    con.commit()
    con.close()

    con = app.connect_db()
    row = con.execute("SELECT status, score, notified_pc FROM codes WHERE normalized='OLDHISTORY123'").fetchone()
    assert row["status"] == "review" and row["score"] == 0
    assert row["notified_pc"] == 1
    assert list((tmp_path / "backups").glob("codes-*.sqlite3"))
    con.close()

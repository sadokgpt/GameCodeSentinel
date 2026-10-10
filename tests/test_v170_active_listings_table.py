"""1.7: explicit live-list evidence and advanced table controls."""
import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import inspect
import textwrap
from unittest.mock import Mock

import pytest

import app
from sentinel_freshness import is_active_tracker_heading
from sentinel_table import (
    DEFAULT_COLUMNS, DEFAULT_WIDTHS, restore_column_order,
    restore_column_widths, move_column, latest_post_date,
    is_recent_code, sort_rows_by_post_date,
)


def _time(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _cand(name, age, active_list=False, kind="secondary"):
    return app.Candidate(
        app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", name,
        f"https://test.example/{name}", kind, published_at=_time(age),
        active_listing=active_list,
    )


@pytest.mark.parametrize("heading, expected", [
    ("Active codes", True),
    ("Working coupon codes", True),
    ("Current Genshin Impact codes", True),
    ("Codes that are still working", True),
    ("Expired codes", False),
    ("Old active codes", False),
    ("Not working codes", False),
    ("All Genshin Codes", False),
    ("Last updated today", False),
    ("", False),
])
def test_list_heading_requires_explicit_current_codes(heading, expected):
    assert is_active_tracker_heading(
        heading, source_kind="secondary", source_mode="page") is expected


@pytest.mark.parametrize("kind,mode", [
    ("official", "page"), ("official", "crawl"),
    ("secondary", "crawl"), ("community", "page"),
])
def test_an_article_is_not_a_live_tracker_listing(kind, mode):
    assert not is_active_tracker_heading(
        "Active codes", source_kind=kind, source_mode=mode)


def test_old_published_tracker_listed_active_is_a_current_mention_not_validated():
    result = app.merge_candidates([_cand("Tracker", 300, active_list=True)])
    row = result[(app.GAME_GENSHIN, "ABC123XYZ")]
    assert row["status"] == "active" and row["score"] == 60
    assert "NON GARANTITO" in row["confidence"]
    assert row["sources"][0]["listed_active"] is True


def test_old_article_only_even_with_updated_stamp_is_reviewed():
    src = app.Source(app.GAME_GENSHIN, "Old tracker", "https://test.example", "secondary")
    html = (f'<meta property="article:published_time" content="{_time(300)}">'
            f'<meta property="article:modified_time" content="{_time(1)}">'
            '<h2>Redeem codes guide</h2><p>Redeem code ABC123XYZ for 60 primogems</p>')
    candidates = app.enrich_with_page_dates(
        app.extract_candidates_html(src.game, html, src, src.url), html, src)
    assert candidates and all(not c.active_listing for c in candidates)
    result = app.merge_candidates(candidates)[(app.GAME_GENSHIN, "ABC123XYZ")]
    assert result["status"] == "review" and result["score"] == 0


def test_old_tracker_active_section_does_not_resurrect_expired_section():
    src = app.Source(app.GAME_GENSHIN, "Tracker", "https://test.example", "secondary")
    html = (f'<meta property="article:published_time" content="{_time(200)}">'
            '<h2>Active codes</h2><ul><li>ABC123XYZ - 60 Primogems</li></ul>'
            '<h2>Expired codes</h2><ul><li>OLD123XYZ - 10 Primogems</li></ul>')
    candidates = app.enrich_with_page_dates(
        app.extract_candidates_html(src.game, html, src, src.url), html, src)
    rows = {c.code: c for c in candidates}
    assert rows["ABC123XYZ"].active_listing is True
    assert rows["OLD123XYZ"].active_listing is False
    assert rows["OLD123XYZ"].status == "expired"


def test_undated_article_not_counted_as_new_or_current():
    src = app.Source(app.GAME_GENSHIN, "Tracker", "https://test.example", "secondary")
    html = '<h2>Archive</h2><p>Redeem code ABC123XYZ for 60 Primogems</p>'
    candidates = app.enrich_with_page_dates(
        app.extract_candidates_html(src.game, html, src, src.url), html, src)
    assert candidates and all(c.status == "review" for c in candidates)


def test_independent_current_tracker_lists_confirm_but_old_static_articles_do_not():
    result = app.merge_candidates([
        _cand("Tracker one", 300, True), _cand("Tracker two", 400, True),
        _cand("Old article", 700, False),
    ])[(app.GAME_GENSHIN, "ABC123XYZ")]
    assert result["status"] == "active"
    assert result["score"] == 90


def test_previous_expiry_stays_expired_even_when_tracker_now_lists_active(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    monkeypatch.setattr(app, "LOG_PATH", tmp_path / "app.log")
    con = app.connect_db()
    old = _cand("Original", 12)
    old.expires_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    app.upsert_candidates(con, app.merge_candidates([old]))
    app.upsert_candidates(con, app.merge_candidates([_cand("Tracker now", 1, True)]))
    row = con.execute("SELECT status FROM codes WHERE normalized='ABC123XYZ'").fetchone()
    con.close()
    assert row["status"] == "expired"


def test_tracker_listing_can_restore_review_without_deleting_history(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    monkeypatch.setattr(app, "LOG_PATH", tmp_path / "app.log")
    con = app.connect_db()
    app.upsert_candidates(con, app.merge_candidates([_cand("Old article", 150)]))
    row = con.execute("SELECT status FROM codes").fetchone()
    assert row["status"] == "review"
    app.upsert_candidates(con, app.merge_candidates([_cand("Tracker", 150, True)]))
    record = con.execute("SELECT status, source_count FROM codes").fetchone()
    assert record["status"] == "active" and record["source_count"] == 1
    con.close()


def test_table_restores_only_safe_complete_layouts():
    assert restore_column_order(list(reversed(DEFAULT_COLUMNS))) == tuple(reversed(DEFAULT_COLUMNS))
    assert restore_column_order(["code", "code"]) == DEFAULT_COLUMNS
    assert restore_column_order(["invalid"] * len(DEFAULT_COLUMNS)) == DEFAULT_COLUMNS
    assert restore_column_order("game") == DEFAULT_COLUMNS
    assert restore_column_widths({"game": 260, "reward": 10000, "code": True})["game"] == 260
    assert restore_column_widths({"game": 260, "reward": 10000, "code": True})["reward"] == DEFAULT_WIDTHS["reward"]


def test_drag_column_order_logic():
    moved = move_column(DEFAULT_COLUMNS, "reward", "code")
    assert moved[1] == "reward"
    assert moved[2] == "code"
    assert set(moved) == set(DEFAULT_COLUMNS)


def test_recent_filter_uses_publication_not_modification_or_last_download():
    now = datetime.now(timezone.utc)
    old = {"game": app.GAME_GENSHIN, "sources_json": json.dumps([
        {"published_at": _time(60), "updated_at": _time(1), "checked_at": _time(0)}
    ])}
    recent = {"game": app.GAME_GENSHIN, "sources_json": json.dumps([
        {"published_at": _time(2)}
    ])}
    no_date = {"game": app.GAME_GENSHIN, "sources_json": "[]"}
    assert not is_recent_code(old, now)
    assert is_recent_code(recent, now)
    assert not is_recent_code(no_date, now)


def test_date_sort_handles_unknown_last_and_both_directions():
    old = {"game": app.GAME_GENSHIN, "sources_json": json.dumps([{"published_at": _time(18)}])}
    newer = {"game": app.GAME_GENSHIN, "sources_json": json.dumps([{"published_at": _time(2)}])}
    unknown = {"game": app.GAME_GENSHIN, "sources_json": "[]"}
    assert sort_rows_by_post_date([unknown, old, newer]) == [newer, old, unknown]
    assert sort_rows_by_post_date([unknown, old, newer], descending=False) == [old, newer, unknown]


def test_gui_calls_recent_filter_date_sort_and_opens_sources_on_double_click():
    source = inspect.getsource(app.gui_main)
    assert "Solo codici recenti" in source
    assert "sort_rows_by_post_date(rows," in source
    assert "is_recent_code(row)" in source
    assert "show_sources_selected() if tree.identify_region" in source
    assert 'stored["table_columns"]' in source
    assert 'stored["table_widths"]' in source

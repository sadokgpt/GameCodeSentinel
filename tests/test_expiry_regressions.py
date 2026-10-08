"""Regression tests for codes incorrectly revived after expiration."""
from datetime import datetime, timedelta

import pytest

import app


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    monkeypatch.setattr(app, "LOG_PATH", tmp_path / "app.log")
    return app.connect_db()


def candidate(code="OLD123CODE", kind="official", expiry="", status="active", source="Official"):
    return app.Candidate(
        app.GAME_GENSHIN, code, "", source, "https://example.org/" + source,
        kind, status=status, expires_at=expiry,
    )


def record(db):
    return db.execute("SELECT * FROM codes WHERE normalized='OLD123CODE'").fetchone()


def test_expired_dated_code_stays_expired_when_reposted(database):
    past = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
    app.upsert_candidates(database, app.merge_candidates([candidate(expiry=past)]))
    assert record(database)["status"] == "expired"
    app.upsert_candidates(database, app.merge_candidates([
        candidate(kind="community", source="Reddit"),
        candidate(kind="secondary", source="Tracker A"),
        candidate(kind="secondary", source="Tracker B"),
    ]))
    assert record(database)["status"] == "expired"
    assert record(database)["expires_at"] == past


def test_dated_expired_code_requires_new_official_extension(database):
    past = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
    future = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
    app.upsert_candidates(database, app.merge_candidates([candidate(expiry=past)]))
    app.upsert_candidates(database, app.merge_candidates([
        candidate(kind="secondary", expiry=future, source="Tracker")
    ]))
    assert record(database)["status"] == "expired"
    assert record(database)["expires_at"] == past
    app.upsert_candidates(database, app.merge_candidates([
        candidate(expiry=future, source="Official renewal")
    ]))
    assert record(database)["status"] == "active"
    assert record(database)["expires_at"] == future


def test_expired_undated_code_ignores_single_weak_repost(database):
    app.upsert_candidates(database, app.merge_candidates([
        candidate(kind="secondary", status="expired", source="Tracker")
    ]))
    app.upsert_candidates(database, app.merge_candidates([
        candidate(kind="community", source="Reddit")
    ]))
    assert record(database)["status"] == "expired"


def test_expired_undated_code_can_be_reconfirmed_by_official(database):
    app.upsert_candidates(database, app.merge_candidates([
        candidate(kind="secondary", status="expired", source="Tracker")
    ]))
    app.upsert_candidates(database, app.merge_candidates([candidate()]))
    assert record(database)["status"] == "active"


def test_equal_source_expirations_prefer_earliest():
    early = "2026-10-12 09:00"
    late = "2026-10-25 09:00"
    merged = app.merge_candidates([
        candidate(kind="secondary", expiry=late, source="A"),
        candidate(kind="secondary", expiry=early, source="B"),
    ])
    assert merged[(app.GAME_GENSHIN, "OLD123CODE")]["expires_at"] == early


def test_yearless_expiry_not_rolled_to_next_year(monkeypatch):
    if app.search_dates is None:
        pytest.skip("dateparser is optional")
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 8, 12, 0)
    monkeypatch.setattr(app, "datetime", Clock)
    actual = app.extract_expiry("The code expires October 2, 2026.")
    assert actual.startswith("2026-10-02")
    yearless = app.extract_expiry("The code expires October 2.")
    assert yearless.startswith("2026-10-02")

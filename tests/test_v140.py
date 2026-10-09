"""Regression tests for release 1.4.0 safeguards."""
import json
import sqlite3
import pytest
import app
from sentinel_runtime import backup_sqlite, plausible_tracker_page, operation_lock


def test_reject_soft_404_as_absent_tracker():
    assert not plausible_tracker_page("<html><title>Home</title><body>Welcome</body></html>", app.GAME_AION2)
    assert plausible_tracker_page(
        "<html><title>AION 2 Codes</title><body>" +
        "AION 2 gift code list and redemption instructions. " * 7 + "</body></html>",
        app.GAME_AION2,
    )


def test_sqlite_backup_is_consistent_and_rate_limited(tmp_path):
    path = tmp_path / "codes.db"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE items(value TEXT)")
        con.execute("INSERT INTO items VALUES('used-code')")
    backup = backup_sqlite(path)
    assert backup is not None and backup.is_file()
    assert backup_sqlite(path) is None
    with sqlite3.connect(backup) as con:
        assert con.execute("SELECT value FROM items").fetchone()[0] == "used-code"


def test_cross_process_lock_nonblocking(tmp_path):
    with operation_lock(tmp_path, "scan") as held:
        assert held
        with operation_lock(tmp_path, "scan") as other:
            assert not other
    with operation_lock(tmp_path, "scan") as acquired:
        assert acquired


def test_expiry_clock_handles_bad_dates_and_end_of_day():
    assert not app.expiry_has_passed(app.GAME_AION2, "")
    assert not app.expiry_has_passed(app.GAME_AION2, "not-a-date")
    assert app.expiry_has_passed(app.GAME_AION2, "2020-01-01 23:59")


def test_concurrent_scan_is_skipped_without_changing_db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    with operation_lock(tmp_path, "scan") as held:
        assert held
        result = app.run_check()
        assert result["skipped"]
        assert result["notify_rows_pc"] == []
        assert not app.DB_PATH.exists()


def test_source_diagnostics_populated(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    monkeypatch.setattr(app, "LOG_PATH", tmp_path / "app.log")
    monkeypatch.setattr(app, "SOURCES", [
        app.Source(app.GAME_AION2, "Mock official", "https://example.org/news", "official"),
    ])
    monkeypatch.setattr(app, "fetch_page_source", lambda sess, source: ([], 1))
    data = app.run_check({**app.DEFAULT_CONFIG, "notify_pc": False})
    assert data["ok_sources"] == 1 and not data["skipped"]
    with app.connect_db() as con:
        line = con.execute("SELECT source_name,status FROM source_checks").fetchone()
        assert tuple(line) == ("Mock official", "ok")

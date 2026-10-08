"""Regression tests for Genshin active / expired section isolation."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def tracker(html):
    src = app.Source(app.GAME_GENSHIN, "Pocket Tactics",
                     "https://example.com/genshin", "secondary")
    return app.extract_candidates_html(app.GAME_GENSHIN, html, src, src.url)


def test_expired_section_not_reactivated_by_fallback():
    html = "<h2>Expired codes</h2><ul><li>GENSHINOLD2025 - 60 Primogems</li></ul>"
    found = {x.code: x.status for x in tracker(html)}
    assert found["GENSHINOLD2025"] == "expired"


def test_active_and_expired_table_sections():
    html = """<h2>Active codes</h2><table><tr><td>NEWA2026</td><td>60 Primogems</td></tr></table>
    <h2>Expired codes</h2><table><tr><td>OLDG2025</td><td>60 Primogems</td></tr></table>"""
    found = {x.code: x.status for x in tracker(html)}
    assert found == {"NEWA2026": "active", "OLDG2025": "expired"}


def test_expired_tracker_outweighs_historical_official_news():
    candidates = [
        app.Candidate(app.GAME_GENSHIN, "OLDG2025", "", "HoYoverse - News",
                      "https://example.com/old", "official", status="active"),
        app.Candidate(app.GAME_GENSHIN, "OLDG2025", "", "Pocket Tactics",
                      "https://example.com/current", "secondary", status="expired"),
    ]
    item = app.merge_candidates(candidates)[(app.GAME_GENSHIN, "OLDG2025")]
    assert item["status"] == "expired"


def test_genshin_legacy_quarantine_with_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    con = app.connect_db()
    item = app.merge_candidates([
        app.Candidate(app.GAME_GENSHIN, "GENSHINOLD2025", "",
                      "Tracker", "https://example.com", "secondary")
    ])
    app.upsert_candidates(con, item)
    con.execute("DELETE FROM meta WHERE key='genshin_section_review_v132'")
    con.commit()
    con.close()
    con = app.connect_db()
    assert con.execute("SELECT status FROM codes").fetchone()[0] == "review"
    assert (tmp_path / "codes.before_v1.3.2.sqlite3").exists()
    con.close()

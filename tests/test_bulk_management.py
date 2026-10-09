"""Regression tests for bulk code management."""
import pytest
import app

@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "codes.db")
    con = app.connect_db()
    for code in ("CODEA2026", "CODEB2026", "CODEC2026"):
        con.execute("INSERT INTO codes (game, code, normalized, first_seen, last_seen) VALUES (?, ?, ?, ?, ?)",
                    (app.GAME_AION2, code, code, "2026-10-09", "2026-10-09"))
    con.commit()
    yield con
    con.close()

def test_bulk_used_preserves_all_rows(db):
    ids = [r["id"] for r in db.execute("SELECT id FROM codes ORDER BY id")]
    assert app.update_code_state(db, ids[:2], "used") == 2
    assert app.update_code_state(db, ids[:2], "used") == 0
    assert [r["used"] for r in db.execute("SELECT used FROM codes ORDER BY id")] == [1, 1, 0]
    assert db.execute("SELECT COUNT(*) FROM codes").fetchone()[0] == 3

def test_restore_does_not_reactivate_invalid_codes(db):
    ids = [r["id"] for r in db.execute("SELECT id FROM codes ORDER BY id")]
    assert app.update_code_state(db, ids, "used") == 3
    assert app.update_code_state(db, [ids[1]], "invalid") == 1
    assert app.update_code_state(db, ids, "restore") == 2
    assert [(r["status"], r["used"]) for r in db.execute("SELECT status, used FROM codes ORDER BY id")] == [
        ("active", 0), ("invalid", 1), ("active", 0)]

def test_bulk_invalid_and_duplicate_ids(db):
    ids = [r["id"] for r in db.execute("SELECT id FROM codes ORDER BY id")]
    assert app.update_code_state(db, [ids[0], ids[0], ids[2]], "invalid") == 2
    assert [r["status"] for r in db.execute("SELECT status FROM codes ORDER BY id")] == [
        "invalid", "active", "invalid"]

def test_empty_and_missing_ids_are_noop(db):
    assert app.update_code_state(db, [], "used") == 0
    assert app.update_code_state(db, [999999], "used") == 0

@pytest.mark.parametrize("ids", [[0], [-7], ["1"], [True], [1, "2"]])
def test_invalid_ids_rejected(db, ids):
    with pytest.raises(ValueError):
        app.update_code_state(db, ids, "used")
    assert db.execute("SELECT SUM(used) FROM codes").fetchone()[0] == 0

def test_invalid_action_does_not_modify_db(db):
    with pytest.raises(ValueError):
        app.update_code_state(db, [1], "delete")
    assert db.execute("SELECT COUNT(*) FROM codes").fetchone()[0] == 3

def test_redeemed_flag_survives_scan(db):
    row_id = db.execute("SELECT id FROM codes WHERE code='CODEA2026'").fetchone()[0]
    app.update_code_state(db, [row_id], "used")
    merged = app.merge_candidates([
        app.Candidate(app.GAME_AION2, "CODEA2026", "Rewards", "Official", "https://example.com", "official")])
    app.upsert_candidates(db, merged)
    assert db.execute("SELECT used FROM codes WHERE id=?", (row_id,)).fetchone()[0] == 1

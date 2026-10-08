import tempfile
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location("app", Path(__file__).resolve().parents[1] / "app.py")
app = importlib.util.module_from_spec(spec)
import sys
sys.modules["app"] = app
spec.loader.exec_module(app)


def test_extract_list_code_reward():
    src = app.Source(app.GAME_GENSHIN, "Test", "https://example.com", "secondary")
    html = "<h2>Active codes</h2><p>ABC123XYZ - 60 Primogems and 5 Adventurer's Experience</p>"
    out = app.extract_candidates_html(app.GAME_GENSHIN, html, src, src.url)
    assert any(c.code == "ABC123XYZ" and "60" in c.reward for c in out)


def test_aniimo_lowercase_code():
    src = app.Source(app.GAME_ANIIMO, "Test", "https://example.com", "community")
    html = "<p>Code: aniimofreetoplay</p><p>Rewards: Glimmer x50, Growth Flower x5</p>"
    out = app.extract_candidates_html(app.GAME_ANIIMO, html, src, src.url)
    assert any(c.code.lower() == "aniimofreetoplay" for c in out)


def test_secondary_plus_community_is_visible_but_below_auto_notify_threshold():
    c1 = app.Candidate(app.GAME_AION2, "TAKEFLIGHTAION2", "Energy x4", "A", "u1", "secondary")
    c2 = app.Candidate(app.GAME_AION2, "TAKEFLIGHTAION2", "Energy x4", "B", "u2", "community")
    merged = app.merge_candidates([c1, c2])
    item = merged[(app.GAME_AION2, "TAKEFLIGHTAION2")]
    assert item["score"] == 80
    assert item["score"] < app.DEFAULT_CONFIG["notify_min_score"]
    assert item["source_count"] == 2


def test_two_independent_known_sources_are_auto_notifiable():
    c1 = app.Candidate(app.GAME_ANIIMO, "Aniimo2026", "20 Glimmers", "Tracker A", "u1", "secondary")
    c2 = app.Candidate(app.GAME_ANIIMO, "Aniimo2026", "20 Glimmers", "Tracker B", "u2", "secondary")
    item = app.merge_candidates([c1, c2])[(app.GAME_ANIIMO, "ANIIMO2026")]
    assert item["score"] == 90
    assert item["score"] >= app.DEFAULT_CONFIG["notify_min_score"]


def test_no_false_plain_word():
    assert not app.looks_like_code(app.GAME_GENSHIN, "Available", "codes available")


def test_expired_table_is_not_active():
    src = app.Source(app.GAME_GENSHIN, "Tracker", "https://example.com", "secondary")
    html = """
    <h2>Expired codes</h2>
    <table><tr><td>OLD123CODE</td><td>60 Primogems</td></tr></table>
    """
    out = app.extract_candidates_html(app.GAME_GENSHIN, html, src, src.url)
    row = next(c for c in out if c.code == "OLD123CODE")
    assert row.status == "expired"


def test_same_subreddit_posts_do_not_fake_independent_sources():
    c1 = app.Candidate(app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", "Reddit r/Test", "post1", "community")
    c2 = app.Candidate(app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", "Reddit r/Test", "post2", "community")
    item = app.merge_candidates([c1, c2])[(app.GAME_GENSHIN, "ABC123XYZ")]
    assert item["source_count"] == 1
    assert item["score"] < 70


def test_multiline_reddit_reward_is_captured():
    src = app.Source(app.GAME_ANIIMO, "Reddit r/AniimoGuide", "https://reddit.test", "community")
    html = "<p>Code: aniimofreetoplay\nRewards: Glimmer x50, Growth Flower x5, Aniipod Pro x5</p>"
    out = app.extract_candidates_html(app.GAME_ANIIMO, html, src, src.url)
    row = next(c for c in out if c.code.lower() == "aniimofreetoplay")
    assert "50" in row.reward and "Glimmer" in row.reward


def test_styled_list_item_is_parsed():
    src = app.Source(app.GAME_GENSHIN, "Tracker", "https://example.com", "secondary")
    html = "<h2>Active codes</h2><ul><li><strong>OPERACOLLAB</strong> - 30 Primogems, 2 Hero's Wit</li></ul>"
    out = app.extract_candidates_html(app.GAME_GENSHIN, html, src, src.url)
    row = next(c for c in out if c.code == "OPERACOLLAB")
    assert "30" in row.reward
    assert row.status == "active"


def test_authoritative_casing_wins_for_case_sensitive_aniimo():
    community = app.Candidate(app.GAME_ANIIMO, "ANIIMO2026", "20 Glimmers", "Reddit r/AniimoGuide", "u1", "community")
    secondary = app.Candidate(app.GAME_ANIIMO, "Aniimo2026", "20 Glimmers", "Aniimo Wiki", "u2", "secondary")
    item = app.merge_candidates([community, secondary])[(app.GAME_ANIIMO, "ANIIMO2026")]
    assert item["code"] == "Aniimo2026"


def test_aion_multiline_official_reward_is_captured_cleanly():
    src = app.Source(app.GAME_AION2, "AION 2 official", "https://lounge.plaync.com/feed/82955", "official")
    html = """
    <p>A gift for the road ahead. Redeem code TAKEFLIGHTAION2 for:</p>
    <ul>
      <li>Odyle Energy (Bound) x4</li>
      <li>Resurrection Spiritstone (Bound) x5</li>
      <li>Battle Enhance Scroll (Bound) x10</li>
    </ul>
    <p>How to redeem:</p><p>Open Settings.</p>
    """
    out = app.extract_candidates_html(app.GAME_AION2, html, src, src.url)
    row = next(c for c in out if c.code == "TAKEFLIGHTAION2")
    assert "Odyle Energy" in row.reward
    assert "Spiritstone" in row.reward
    assert "Battle Enhance Scroll" in row.reward
    assert "How to redeem" not in row.reward
    assert "gift for the road" not in row.reward.lower()


def test_spa_embedded_crawl_links_are_discovered_and_limited_to_host():
    html = r'''<script>{"url":"\/feed\/82955?country=US","other":"https:\/\/evil.example\/feed\/99"}</script>'''
    links = app.discover_crawl_links("https://lounge.plaync.com/tag/13519", html, "/feed/")
    assert "https://lounge.plaync.com/feed/82955?country=US" in links
    assert all("evil.example" not in x for x in links)


def test_same_source_multiple_pages_do_not_get_multiple_status_votes():
    active = app.Candidate(app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", "HoYoverse - News", "u1", "official", status="active")
    old1 = app.Candidate(app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", "HoYoverse - News", "u2", "official", status="expired")
    old2 = app.Candidate(app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", "HoYoverse - News", "u3", "official", status="expired")
    item = app.merge_candidates([active, old1, old2])[(app.GAME_GENSHIN, "ABC123XYZ")]
    assert item["status"] == "active"
    assert item["source_count"] == 1


def test_default_notification_threshold_is_conservative():
    assert app.DEFAULT_CONFIG["notify_min_score"] == 85


def test_database_has_separate_notification_channels():
    old_data_dir, old_db = app.DATA_DIR, app.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            app.DATA_DIR = Path(td)
            app.DB_PATH = Path(td) / "codes.db"
            con = app.connect_db()
            cols = {r[1] for r in con.execute("PRAGMA table_info(codes)")}
            con.close()
            assert "notified_pc" in cols
            assert "notified_phone" in cols
    finally:
        app.DATA_DIR, app.DB_PATH = old_data_dir, old_db


def test_upsert_downgrades_score_on_weaker_run_but_preserves_authoritative_casing():
    old_data_dir, old_db = app.DATA_DIR, app.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            app.DATA_DIR = Path(td)
            app.DB_PATH = Path(td) / "codes.db"
            con = app.connect_db()
            strong = app.merge_candidates([
                app.Candidate(app.GAME_ANIIMO, "Aniimo2026", "20 Glimmers", "Tracker A", "u1", "secondary"),
                app.Candidate(app.GAME_ANIIMO, "Aniimo2026", "20 Glimmers", "Tracker B", "u2", "secondary"),
            ])
            app.upsert_candidates(con, strong)
            weak = app.merge_candidates([
                app.Candidate(app.GAME_ANIIMO, "ANIIMO2026", "20 Glimmers", "Reddit r/AniimoGuide", "u3", "community"),
            ])
            app.upsert_candidates(con, weak)
            row = con.execute("SELECT * FROM codes WHERE game=?", (app.GAME_ANIIMO,)).fetchone()
            con.close()
            assert row["score"] == 30
            assert row["code"] == "Aniimo2026"
    finally:
        app.DATA_DIR, app.DB_PATH = old_data_dir, old_db


def test_expired_text_inside_neutral_paragraph_is_not_forced_active():
    src = app.Source(app.GAME_GENSHIN, "Tracker", "https://example.com", "secondary")
    html = "<h2>Codes</h2><p>Code OLD123CODE - 60 Primogems - expired</p>"
    out = app.extract_candidates_html(app.GAME_GENSHIN, html, src, src.url)
    row = next(c for c in out if c.code == "OLD123CODE")
    assert row.status == "expired"


def test_current_codes_heading_resets_expired_section():
    src = app.Source(app.GAME_GENSHIN, "Tracker", "https://example.com", "secondary")
    html = "<h2>Expired codes</h2><p>OLD123CODE - 60 Primogems</p><h2>Current codes</h2><p>NEW123CODE - 60 Primogems</p>"
    out = app.extract_candidates_html(app.GAME_GENSHIN, html, src, src.url)
    status = {c.code: c.status for c in out}
    assert status["OLD123CODE"] == "expired"
    assert status["NEW123CODE"] == "active"


def test_missing_tracker_code_becomes_stale_after_three_successful_misses():
    old_data_dir, old_db = app.DATA_DIR, app.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            app.DATA_DIR = Path(td)
            app.DB_PATH = Path(td) / "codes.db"
            con = app.connect_db()
            merged = app.merge_candidates([
                app.Candidate(app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", "Tracker A", "u1", "secondary")
            ])
            app.upsert_candidates(con, merged)
            for _ in range(2):
                assert app.update_missing_codes(con, {}, {"Tracker A"}) == 0
            assert app.update_missing_codes(con, {}, {"Tracker A"}) == 1
            row = con.execute("SELECT status, miss_count FROM codes WHERE normalized='ABC123XYZ'").fetchone()
            con.close()
            assert row["status"] == "stale"
            assert row["miss_count"] == 3
    finally:
        app.DATA_DIR, app.DB_PATH = old_data_dir, old_db


def test_upgrade_from_v1_preserves_generic_notified_flag():
    import sqlite3
    old_data_dir, old_db = app.DATA_DIR, app.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            app.DATA_DIR = Path(td)
            app.DB_PATH = Path(td) / "codes.db"
            con0 = sqlite3.connect(app.DB_PATH)
            con0.execute("CREATE TABLE codes (id INTEGER PRIMARY KEY, notified INTEGER DEFAULT 0)")
            con0.execute("INSERT INTO codes (notified) VALUES (1)")
            con0.commit(); con0.close()
            con = app.connect_db()
            row = con.execute("SELECT notified_pc, notified_phone FROM codes WHERE id=1").fetchone()
            con.close()
            assert row["notified_pc"] == 1
            assert row["notified_phone"] == 1
    finally:
        app.DATA_DIR, app.DB_PATH = old_data_dir, old_db


def test_reappearing_code_does_not_reset_notification_flags():
    old_data_dir, old_db = app.DATA_DIR, app.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            app.DATA_DIR = Path(td)
            app.DB_PATH = Path(td) / "codes.db"
            con = app.connect_db()
            merged = app.merge_candidates([
                app.Candidate(app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", "Tracker A", "u1", "secondary"),
                app.Candidate(app.GAME_GENSHIN, "ABC123XYZ", "60 Primogems", "Tracker B", "u2", "secondary"),
            ])
            app.upsert_candidates(con, merged)
            con.execute("UPDATE codes SET notified_pc=1, notified_phone=1, status='stale' WHERE normalized='ABC123XYZ'")
            con.commit()
            app.upsert_candidates(con, merged)
            row = con.execute("SELECT status, notified_pc, notified_phone FROM codes WHERE normalized='ABC123XYZ'").fetchone()
            con.close()
            assert row["status"] == "active"
            assert row["notified_pc"] == 1
            assert row["notified_phone"] == 1
    finally:
        app.DATA_DIR, app.DB_PATH = old_data_dir, old_db


def test_mark_channel_notified_does_not_touch_other_channel():
    old_data_dir, old_db = app.DATA_DIR, app.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as td:
            app.DATA_DIR = Path(td)
            app.DB_PATH = Path(td) / "codes.db"
            con = app.connect_db()
            merged = app.merge_candidates([
                app.Candidate(app.GAME_AION2, "TAKEFLIGHTAION2", "Energy x4", "Official", "u1", "official")
            ])
            app.upsert_candidates(con, merged)
            row = con.execute("SELECT * FROM codes LIMIT 1").fetchone()
            con.close()
            app.mark_channel_notified([row], "pc")
            con = app.connect_db()
            state = con.execute("SELECT notified_pc, notified_phone FROM codes LIMIT 1").fetchone()
            con.close()
            assert state["notified_pc"] == 1
            assert state["notified_phone"] == 0
    finally:
        app.DATA_DIR, app.DB_PATH = old_data_dir, old_db


def test_reddit_comment_only_code_can_be_extracted_without_extra_source_vote():
    src = app.Source(app.GAME_ANIIMO, "Reddit r/AniimoGuide", "", "community", "reddit", subreddit="AniimoGuide")
    texts = [
        "Megathread discussion",
        "New gift code: aniimofreetoplay - Glimmer x50, Growth Flower x5",
        "worked for me",
    ]
    comment_html = "<div>" + "".join(f"<p>{app.html_lib.escape(t)}</p>" for t in texts) + "</div>"
    out = app.extract_candidates_html(app.GAME_ANIIMO, comment_html, src, "https://reddit.test/post")
    row = next(c for c in out if c.code.lower() == "aniimofreetoplay")
    pos, neg = app.reddit_confirmation_counts_from_texts(texts)
    row.reddit_confirmations, row.reddit_negatives = pos, neg
    merged = app.merge_candidates([row])[(app.GAME_ANIIMO, "ANIIMOFREETOPLAY")]
    assert merged["source_count"] == 1
    assert merged["score"] < app.DEFAULT_CONFIG["notify_min_score"]

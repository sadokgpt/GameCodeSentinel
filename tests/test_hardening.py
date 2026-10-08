"""v1.2 regression tests for actual v1.1 false positives and safer lifecycle."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(app, 'DB_PATH', tmp_path / 'codes.db')
    monkeypatch.setattr(app, 'LOG_PATH', tmp_path / 'app.log')
    monkeypatch.setattr(app, 'CONFIG_PATH', tmp_path / 'config.json')
    return tmp_path


def aion(html, kind='official'):
    source = app.Source(app.GAME_AION2, 'AION official' if kind == 'official' else 'Codes Tracker',
                        'https://example.com/aion2', kind)
    return app.extract_candidates_html(app.GAME_AION2, html, source, source.url)


def test_aion_noise_on_official_page_must_not_become_coupon():
    html = '''<h2>AION 2 codes</h2>
    <p>Codes for AION 2 GLOBAL2026 players are available. AION2GLOBAL and
    EVENT2026 are not coupons, they are examples in a guide.</p>
    <p>Use a coupon registration menu to confirm your account and server.</p>'''
    assert aion(html) == []


def test_aion_stray_identifiers_near_code_word_are_not_codes():
    html = '<h2>Account instructions</h2><p>AION2UPDATE2000 is a product ID for the code settings page; redeem is a button.</p>'
    assert aion(html) == []


def test_aion_one_real_code_with_official_eu_expiration_and_rewards():
    html = '''<h2>A Thank You Gift</h2><p>Redeem code TAKEFLIGHTAION2 for:</p>
    <ul><li>Odyle Energy (Bound) x4</li><li>Resurrection Spiritstone (Bound) x5</li>
    <li>Battle Enhance Scroll (Bound) x10</li></ul>
    <p>How to redeem: Settings &gt; Miscellaneous &gt; Account.</p>
    <p>Coupon period:</p><p>Starts: October 1</p>
    <p>Ends (NA): October 13, 11:00 PM PDT</p><p>Ends (EU): 14 October, 08:00 CEST</p>'''
    result = aion(html)
    assert [c.code for c in result] == ['TAKEFLIGHTAION2']
    assert 'Odyle Energy' in result[0].reward and 'Battle Enhance Scroll' in result[0].reward
    assert result[0].expires_at == f'{datetime.now().year}-10-14 08:00'


def test_aion_secondary_active_bullet_and_expired_section():
    html = '''<h2>Active AION 2 codes</h2><ul>
    <li>TAKEFLIGHTAION2—Redeem for 4x Odyle Energy, 5x Resurrection Spiritstone</li></ul>
    <h2>Expired AION 2 codes</h2><ul><li>OLDPROMO2025 - 3x Ores</li></ul>'''
    data = {x.code: x.status for x in aion(html, 'secondary')}
    assert data == {'TAKEFLIGHTAION2': 'active', 'OLDPROMO2025': 'expired'}


def test_aion_explicit_expired_then_active_preserves_sections():
    html = '''<h2>Expired codes</h2><p>Redeem code OLDPROMO2025 for 5 stones</p>
    <h2>Active codes</h2><p>Redeem code TAKEFLIGHTAION2 for 4x Odyle</p>'''
    assert {c.code:c.status for c in aion(html)} == {
        'OLDPROMO2025': 'expired', 'TAKEFLIGHTAION2': 'active'
    }


def test_aion_pure_examples_not_accepted_even_with_explicit_keyword():
    assert aion('<p>Example: redeem code EXAMPLE2026 (dummy test code, not a real coupon).</p>') == []


def test_aion_is_not_a_fixed_whitelist_new_coupon_format_supported():
    vals = aion('<h2>Active codes</h2><p>Enter coupon code NEWDAEVAGIFT for rewards.</p>')
    assert [c.code for c in vals] == ['NEWDAEVAGIFT']


def test_non_aion_code_extraction_still_works():
    src = app.Source(app.GAME_GENSHIN, 'Tracker', 'https://test', 'secondary')
    out = app.extract_candidates_html(app.GAME_GENSHIN,
                                      '<h2>Active codes</h2><li>ABC123XYZ - 60 Primogems</li>', src, src.url)
    assert any(c.code == 'ABC123XYZ' for c in out)


def test_reddit_not_working_is_negative_not_positive():
    assert app.reddit_confirmation_counts_from_texts(['not working', 'invalid', "doesn't work"]) == (0, 3)


def test_reddit_multi_code_discussion_votes_do_not_leak():
    pos, neg = app.reddit_confirmation_counts_from_texts(
        ['ABC123 works for me', 'XYZ123 invalid', 'works', 'not working'], 'ABC123', False)
    assert (pos, neg) == (1, 0)


def test_explicit_deadline_is_enforced_on_database_scan(isolated_db):
    con = app.connect_db()
    date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M')
    item = app.merge_candidates([app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', 'Odyle x4',
                            'AION official', 'https://official.example', 'official', expires_at=date)])
    app.upsert_candidates(con, item)
    assert con.execute("SELECT status FROM codes").fetchone()['status'] == 'expired'
    con.execute("UPDATE codes SET status='active'")
    con.commit()
    assert app.expire_stored_codes(con) == 1
    assert con.execute("SELECT status FROM codes").fetchone()['status'] == 'expired'
    con.close()


def test_old_aion_records_quarantined_and_database_backed_up(isolated_db):
    con = app.connect_db()
    strong = app.merge_candidates([app.Candidate(app.GAME_AION2, 'AION2GLOBAL', '', 'Bad', 'badurl', 'official')])
    app.upsert_candidates(con, strong)
    con.execute("UPDATE codes SET expires_at='2026-10-09 10:00'")
    con.execute("DELETE FROM meta WHERE key='aion_strict_parser_v12'")
    con.commit(); con.close()
    con = app.connect_db()
    row = con.execute("SELECT status, score, expires_at FROM codes").fetchone()
    assert tuple(row) == ('review', 0, '')
    con.close()
    assert (isolated_db / 'codes.before_v1.2.sqlite3').exists()
    # The backup retains the original row and score.
    with sqlite3.connect(isolated_db / 'codes.before_v1.2.sqlite3') as back:
        assert back.execute("SELECT score FROM codes").fetchone()[0] == 100
    con = app.connect_db()
    assert con.execute("SELECT status FROM codes").fetchone()[0] == 'review'
    con.close()


def test_old_aion_is_reactivated_when_strictly_verified(isolated_db):
    con = app.connect_db()
    # Simulate a v1.1 row requiring revalidation.
    item = app.merge_candidates([app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'Old', '', 'official')])
    app.upsert_candidates(con, item)
    con.execute("UPDATE codes SET status='review', score=0 WHERE game=?", (app.GAME_AION2,))
    con.commit()
    real_html = '<p>Redeem code TAKEFLIGHTAION2 for 4 Odyle Energy.</p>'
    new = app.merge_candidates(aion(real_html))
    app.upsert_candidates(con, new)
    assert con.execute("SELECT status, score FROM codes").fetchone()['score'] == 100
    assert con.execute("SELECT status FROM codes").fetchone()['status'] == 'active'
    con.close()


def test_score_is_lowered_after_independent_source_disappears(isolated_db):
    con = app.connect_db()
    a = app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'A', '', 'secondary')
    b = app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'B', '', 'secondary')
    app.upsert_candidates(con, app.merge_candidates([a,b]))
    assert con.execute('SELECT score FROM codes').fetchone()[0] == 90
    app.upsert_candidates(con, app.merge_candidates([a]))
    assert con.execute('SELECT score FROM codes').fetchone()[0] == 60
    con.close()


def test_tracker_missing_even_when_reddit_reposts_code(isolated_db):
    con = app.connect_db()
    tracker = app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'Tracker', '', 'secondary')
    app.upsert_candidates(con, app.merge_candidates([tracker]))
    reposts = app.merge_candidates([app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'Reddit', '', 'community')])
    for i in range(3):
        app.upsert_candidates(con, reposts)
        app.update_missing_codes(con, reposts, {'Tracker'})
    assert con.execute('SELECT status FROM codes').fetchone()[0] == 'stale'
    con.close()


def test_official_current_evidence_blocks_stale(isolated_db):
    con = app.connect_db()
    tracker = app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'Tracker', '', 'secondary')
    app.upsert_candidates(con, app.merge_candidates([tracker]))
    official = app.merge_candidates([app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'Official', '', 'official')])
    for i in range(5):
        app.upsert_candidates(con, official)
        assert app.update_missing_codes(con, official, {'Tracker'}) == 0
    assert con.execute('SELECT status FROM codes').fetchone()[0] == 'active'
    con.close()


def test_not_notifications_for_historical_rows_when_all_sites_offline(isolated_db, monkeypatch):
    con = app.connect_db()
    reported = app.merge_candidates([app.Candidate(app.GAME_GENSHIN, 'ABC123XYZ', '', 'A', '', 'secondary'),
                                     app.Candidate(app.GAME_GENSHIN, 'ABC123XYZ', '', 'B', '', 'secondary')])
    app.upsert_candidates(con, reported)
    con.close()
    monkeypatch.setattr(app, 'SOURCES', [])
    result = app.run_check(app.DEFAULT_CONFIG.copy())
    assert result['notify_rows_pc'] == []
    assert result['inserted'] == 0


def test_cli_report_json_serializable(isolated_db, monkeypatch, capsys):
    import argparse
    from unittest.mock import Mock
    fake_row = {'code': 'TEST'}
    fake = {'ok_sources': 1, 'failed_sources': 0, 'failures': [], 'candidates': 1,
            'new_rows': [fake_row], 'notify_rows': [fake_row],
            'notify_rows_pc': [fake_row], 'notify_rows_phone': [fake_row]}
    monkeypatch.setattr(app, 'run_check', lambda cfg: fake)
    monkeypatch.setattr(sys, 'argv', ['app.py', '--check'])
    assert app.cli_main() == 0
    assert json.loads(capsys.readouterr().out)['ok_sources'] == 1


def test_stale_absences_do_not_count_failed_tracker(isolated_db):
    con = app.connect_db()
    reported = app.merge_candidates([app.Candidate(app.GAME_GENSHIN, 'ABC123XYZ', '', 'A', '', 'secondary')])
    app.upsert_candidates(con, reported)
    assert app.update_missing_codes(con, {}, set()) == 0
    assert con.execute('SELECT miss_count FROM codes').fetchone()[0] == 0
    con.close()


def test_same_publisher_pgg_and_destructoid_do_not_count_as_independent():
    a = app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'Pro Game Guides',
                      'https://progameguides.com/codes/aion-2-codes/', 'secondary')
    b = app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'AION 2 - Destructoid',
                      'https://www.destructoid.com/aion-2-codes/', 'secondary')
    item = app.merge_candidates([a, b])[(app.GAME_AION2, 'TAKEFLIGHTAION2')]
    assert item['source_count'] == 2  # Sources can still be inspected separately
    assert item['score'] == 60  # One publisher, not two independent publishers


def test_different_independent_publishers_still_can_confirm():
    a = app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'Pro Game Guides', '', 'secondary')
    b = app.Candidate(app.GAME_AION2, 'TAKEFLIGHTAION2', '', 'Publisher X', '', 'secondary')
    item = app.merge_candidates([a, b])[(app.GAME_AION2, 'TAKEFLIGHTAION2')]
    assert item['score'] == 90


def test_single_tracker_can_reactivate_previous_stale_record(isolated_db):
    con = app.connect_db()
    item = app.merge_candidates([app.Candidate(app.GAME_GENSHIN, 'ABC123XYZ', '', 'Tracker A', '', 'secondary')])
    app.upsert_candidates(con, item)
    con.execute("UPDATE codes SET status='stale', miss_count=3")
    con.commit()
    app.upsert_candidates(con, item)
    app.update_missing_codes(con, item, {'Tracker A'})
    assert tuple(con.execute("SELECT status, miss_count FROM codes").fetchone()) == ('active', 0)
    con.close()


def test_full_scan_keeps_one_real_coupon_not_noise(isolated_db, monkeypatch):
    source = app.Source(app.GAME_AION2, 'Official AION Steam',
                        'https://steamcommunity.com/app/3393110/announcements/', 'official')
    sample = '''<h2>A Thank You Gift to All Daevas</h2>
       <p>AION2GLOBAL2026 is a player identifier; EVENT2026 marks this update.</p>
       <p>Redeem code TAKEFLIGHTAION2 for:</p>
       <ul><li>Odyle Energy (Bound) x4</li><li>Resurrection Spiritstone (Bound) x5</li></ul>
       <p>Ends (EU): 14 October, 08:00 CEST</p>'''
    monkeypatch.setattr(app, 'SOURCES', [source])
    monkeypatch.setattr(app, 'fetch_page_source',
                        lambda session, src: (app.extract_candidates_html(src.game, sample, src, src.url), 1))
    config = dict(app.DEFAULT_CONFIG, notify_pc=True, notify_phone=False)
    result = app.run_check(config)
    assert result['inserted'] == 1
    assert [r['code'] for r in result['notify_rows_pc']] == ['TAKEFLIGHTAION2']
    con = app.connect_db()
    assert [r['normalized'] for r in con.execute('SELECT * FROM codes')] == ['TAKEFLIGHTAION2']
    con.close()
    app.mark_channel_notified(result['notify_rows_pc'], 'pc')
    assert app.run_check(config)['notify_rows_pc'] == []


def test_aion_official_cms_div_markup_still_works():
    html = '''<div data-contents-type="text"><span>
       A gift for the road ahead. Redeem code TAKEFLIGHTAION2 for:
       </span></div><ul><li>Odyle Energy (Bound) x4</li></ul>'''
    assert [c.code for c in aion(html)] == ['TAKEFLIGHTAION2']


def test_redirect_to_unrelated_domain_rejected():
    from unittest.mock import Mock
    resp = Mock(status_code=200, url='https://some-other-site.example/fake', text='<p>Redeem code FAKECODE2026</p>')
    resp.raise_for_status.return_value = None
    sess = Mock()
    sess.get.return_value = resp
    with pytest.raises(ValueError, match='Reindirizzamento'):
        app.http_get(sess, 'https://steamcommunity.com/app/3393110/announcements/')


def test_cloudflare_challenge_not_counted_as_success():
    from unittest.mock import Mock
    resp = Mock(status_code=200, url='https://www.destructoid.com/aion-2-codes/',
                text='<html><title>Attention Required! | Cloudflare</title></html>')
    resp.raise_for_status.return_value = None
    sess = Mock()
    sess.get.return_value = resp
    with pytest.raises(ValueError, match='anti-bot'):
        app.http_get(sess, 'https://www.destructoid.com/aion-2-codes/')


def test_www_redirect_stays_allowed():
    from unittest.mock import Mock
    resp = Mock(status_code=200, url='https://www.destructoid.com/aion-2-codes/', text='<p>Codes</p>')
    resp.raise_for_status.return_value = None
    sess = Mock()
    sess.get.return_value = resp
    assert app.http_get(sess, 'https://destructoid.com/aion-2-codes/') is resp

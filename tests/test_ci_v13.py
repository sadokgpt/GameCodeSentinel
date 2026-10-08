"""Regression tests for CI exit codes, isolated JSON reports and community votes."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def test_reddit_feedback_not_attributed_to_longer_code():
    assert app.reddit_confirmation_counts_from_texts(
        ["ABC1234 works", "ABC123 works", "ABC123-EXTRA invalid"], "ABC123", False
    ) == (1, 0)


def test_version_does_not_touch_database(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, 'argv', ['app.py', '--version'])
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path / 'database')
    assert app.cli_main() == 0
    assert app.APP_VERSION in capsys.readouterr().out
    assert not (tmp_path / 'database').exists()


@pytest.mark.parametrize('sources,expected', [(0,2), (1,0)])
def test_ci_scan_exit_and_json_report(monkeypatch, tmp_path, sources, expected):
    monkeypatch.setattr(sys, 'argv', ['app.py', '--check', '--headless', '--game', 'AION 2',
                                    '--report-json', str(tmp_path / 'scan' / 'report.json')])
    monkeypatch.setattr(app, 'DATA_DIR', tmp_path / 'data')
    monkeypatch.setattr(app, 'DB_PATH', tmp_path / 'data' / 'codes.db')
    monkeypatch.setattr(app, 'CONFIG_PATH', tmp_path / 'data' / 'config.json')
    monkeypatch.setattr(app, 'LOG_PATH', tmp_path / 'data' / 'app.log')
    monkeypatch.setattr(app, 'SOURCES', [app.Source(app.GAME_AION2, 'A', 'https://official.example', 'official'),
                                       app.Source(app.GAME_GENSHIN, 'B', 'https://other.example', 'secondary')])
    def fake_check(cfg):
        assert len(app.SOURCES) == 1 and app.SOURCES[0].game == app.GAME_AION2
        return dict(ok_sources=sources, failed_sources=1-sources, failures=[], candidates=0,
                    inserted=0, stale_marked=0, expired_marked=0, new_rows=[], notify_rows=[],
                    notify_rows_pc=[], notify_rows_phone=[])
    monkeypatch.setattr(app, 'run_check', fake_check)
    assert app.cli_main() == expected
    obj=json.loads((tmp_path / 'scan' / 'report.json').read_text())
    assert obj['game_filter'] == 'AION 2'
    assert obj['ok_sources'] == sources
    assert 'new_rows' not in obj

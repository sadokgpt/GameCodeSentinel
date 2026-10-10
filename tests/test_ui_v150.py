"""Safety and compatibility regressions for the 1.5.0 UI/redemption flow.

These tests intentionally do not log in or contact HoYoverse.
"""
from urllib.parse import parse_qs, urlsplit

import pytest

import app
import sentinel_ui


def test_genshin_redemption_is_official_prefilled_url():
    url = app.redeem_url_for(app.GAME_GENSHIN, "  GeNShIn123  ")
    parsed = urlsplit(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "genshin.hoyoverse.com"
    assert parsed.path == "/en/gift"
    assert parse_qs(parsed.query) == {"code": ["GeNShIn123"]}


@pytest.mark.parametrize("code", [
    "", "    ", "A B C D", "a&confirm=true", "abc#fragment",
    "x" * 65, "aaa\\nbbb", "https://evil.example",
])
def test_no_invalid_codes_are_put_in_link(code):
    assert app.redeem_url_for(app.GAME_GENSHIN, code) is None


def test_other_games_have_no_unverified_redemption_urls():
    assert app.redeem_url_for(app.GAME_ANIIMO, "ABCD1234") is None
    assert app.redeem_url_for(app.GAME_AION2, "ABCD1234") is None


def test_theme_is_available_without_creating_a_window():
    assert sentinel_ui.PALETTE["background"].startswith("#")
    assert callable(sentinel_ui.apply_theme)
    assert callable(sentinel_ui.metric_card)
    assert app.APP_VERSION == "1.5.0"

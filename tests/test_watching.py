"""E2E tests for watch-page features: autoplay off, clear player, no hover previews."""
from __future__ import annotations

import time

from selenium.webdriver.common.by import By


def t(name: str) -> str:
    return f'[data-test="{name}"]'


def autonav_state(b) -> tuple[str, str]:
    return tuple(b.js(
        "const a = document.querySelector('[data-test=\"autonav\"]');"
        "return [a.querySelector('.ytp-autonav-toggle-button').getAttribute('aria-checked'), a.dataset.clicks];"
    ))


# ---- Autoplay off ----------------------------------------------------------------------------

def test_autoplay_switched_off_once(browser):
    browser.open("/watch?v=aaaaaaaaaa1")
    browser.wait_for(lambda: autonav_state(browser) == ("false", "1"), message="autoplay flipped off once")
    time.sleep(1.5)
    assert autonav_state(browser) == ("false", "1"), "no repeated clicking"


def test_autoplay_trusted_click_is_respected(browser):
    browser.open("/watch?v=aaaaaaaaaa1")
    browser.wait_for(lambda: autonav_state(browser)[0] == "false", message="autoplay off")
    # A real user click (WebDriver clicks are trusted) turns it back on...
    browser.driver.find_element(By.CSS_SELECTOR, t("autonav")).click()
    assert autonav_state(browser)[0] == "true"
    # ...and it stays on, even after an in-app navigation to another video.
    browser.js("__fx.navigate('/watch?v=aaaaaaaaaa2')")
    time.sleep(1.5)
    assert autonav_state(browser)[0] == "true"


def test_autoplay_leaves_playlists_alone(browser):
    browser.open("/watch?v=aaaaaaaaaa1&list=PLxxxxxxxx")
    time.sleep(1)
    assert autonav_state(browser) == ("true", "0")


def test_autoplay_toggle_off(browser):
    browser.set_settings(autoplayOff=False)
    browser.open("/watch?v=aaaaaaaaaa1")
    time.sleep(1)
    assert autonav_state(browser) == ("true", "0")


def test_autoplay_countdown_cancelled_as_fallback(browser):
    browser.open("/watch?v=aaaaaaaaaa1")
    browser.js("__fx.countdown()")
    browser.wait_for(
        lambda: browser.js("return document.querySelector('[data-test=\"countdown-cancel\"]').dataset.cancelled") == "yes",
        message="countdown cancelled",
    )


def test_autoplay_countdown_kept_when_user_wants_autoplay(browser):
    browser.open("/watch?v=aaaaaaaaaa1")
    browser.wait_for(lambda: autonav_state(browser)[0] == "false", message="autoplay off")
    browser.driver.find_element(By.CSS_SELECTOR, t("autonav")).click()  # trusted: user wants autoplay
    browser.js("__fx.countdown()")
    time.sleep(1.5)
    assert browser.js("return document.querySelector('[data-test=\"countdown-cancel\"]').dataset.cancelled") is None


# ---- Clear player ----------------------------------------------------------------------------

SUGGESTIONS = ["videowall", "pause-overlay", "fullscreen-grid"]
CREATOR = ["ce-element", "cards-teaser", "cards-button", "watermark"]
KEEP = ["countdown", "paid-promo", "captions", "controls", "main-video"]


def test_clear_player_hides_overlays_and_keeps_disclosures(browser):
    browser.open("/watch?v=aaaaaaaaaa1")
    for name in SUGGESTIONS + CREATOR:
        assert not browser.any_visible(t(name)), name
    for name in KEEP:
        assert browser.all_visible(t(name)), f"{name} must never be hidden"


def test_clear_player_creator_overlays_separate(browser):
    browser.set_settings(hideCreatorOverlays=False)
    browser.open("/watch?v=aaaaaaaaaa1")
    for name in CREATOR:
        assert browser.all_visible(t(name)), name
    for name in SUGGESTIONS:
        assert not browser.any_visible(t(name)), name


def test_clear_player_off(browser):
    browser.set_settings(hideSuggestions=False, hideCreatorOverlays=False)
    browser.open("/watch?v=aaaaaaaaaa1")
    for name in SUGGESTIONS + CREATOR + KEEP:
        assert browser.all_visible(t(name)), name


# ---- No hover previews -----------------------------------------------------------------------

def test_hover_preview_hidden_and_paused(browser):
    browser.open("/watch?v=aaaaaaaaaa1")
    assert not browser.any_visible(t("hover-preview"))
    assert not browser.any_visible(t("moving-thumb"))
    started = browser.driver.execute_async_script(
        "const done = arguments[0]; __fx.playable('[data-test=\"preview-video\"]').then(done);"
    )
    assert started in ("playing", "aborted"), started  # aborted = paused by the add-on mid-play()
    assert browser.js("return document.querySelector('[data-test=\"preview-video\"]').dataset.playEvents") != "0", \
        "play must actually have started, or this test proves nothing"
    browser.wait_for(lambda: browser.js("return document.querySelector('[data-test=\"preview-video\"]').paused"),
                     message="preview paused")
    assert browser.js("return document.querySelector('[data-test=\"preview-video\"]').muted")


def test_hover_main_player_never_paused(browser):
    browser.open("/watch?v=aaaaaaaaaa1")
    started = browser.driver.execute_async_script(
        "const done = arguments[0]; __fx.playable('[data-test=\"main-video\"]').then(done);"
    )
    assert started == "playing", started
    time.sleep(0.8)
    assert browser.js("return document.querySelector('[data-test=\"main-video\"]').paused") is False


def test_hover_preview_off(browser):
    browser.set_settings(noHoverPreviews=False)
    browser.open("/watch?v=aaaaaaaaaa1")
    assert browser.all_visible(t("moving-thumb"))
    started = browser.driver.execute_async_script(
        "const done = arguments[0]; __fx.playable('[data-test=\"preview-video\"]').then(done);"
    )
    assert started == "playing"
    time.sleep(0.8)
    assert browser.js("return document.querySelector('[data-test=\"preview-video\"]').paused") is False

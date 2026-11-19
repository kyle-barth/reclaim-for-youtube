"""E2E tests for Original audio, against a stub of the player's audio-track API."""
from __future__ import annotations

import time

import pytest


def open_audio(b, scenario: str, v: str = "aaaaaaaaaa1"):
    b.open(f"/watch?v={v}&fx=audio_watch&scenario={scenario}", settle=0.3)


def calls(b) -> int:
    return b.js("return __audio.calls()")


def last_set(b) -> str | None:
    return b.js("return document.getElementById('movie_player').dataset.lastSet || null")


def test_ai_dub_switched_to_original_exactly_once(browser):
    open_audio(browser, "auto")
    browser.wait_for(lambda: calls(browser) == 1, message="one switch")
    assert last_set(browser).startswith("en.1;")
    time.sleep(1)  # the loadedmetadata our switch triggers must not cause a second call
    assert calls(browser) == 1


@pytest.mark.parametrize("scenario", ["creator", "original", "no-original", "two-originals", "malformed", "nomethods"])
def test_no_switch_when_rule_does_not_apply(browser, scenario):
    open_audio(browser, scenario)
    time.sleep(1.2)
    assert calls(browser) == 0
    assert browser.js("return document.documentElement.dataset.rfyPage") == "watch"


def test_users_own_choice_is_respected(browser):
    open_audio(browser, "auto")
    browser.wait_for(lambda: calls(browser) == 1, message="first switch")
    # The user picks the dub again in the player; nothing switches it back for this video.
    browser.js("__audio.selectDub(); document.querySelector('#movie_player video').dispatchEvent(new Event('loadedmetadata'))")
    browser.js("document.querySelector('ytd-app').dispatchEvent(new CustomEvent('yt-navigate-finish', {bubbles: true}))")
    time.sleep(1)
    assert calls(browser) == 1


def test_next_video_is_a_new_start(browser):
    open_audio(browser, "auto")
    browser.wait_for(lambda: calls(browser) == 1, message="first switch")
    browser.js("__audio.selectDub(); __fx.navigate('/watch?v=bbbbbbbbbb2&fx=audio_watch&scenario=auto')")
    browser.wait_for(lambda: calls(browser) == 2, message="switch on the next video")


def test_tracks_that_arrive_late(browser):
    open_audio(browser, "late")
    browser.wait_for(lambda: calls(browser) == 1, timeout=3, message="switch after tracks populate")


def test_tracks_never_populated_gives_up(browser):
    open_audio(browser, "never")
    time.sleep(3.6)
    assert calls(browser) == 0


def test_refused_switch_is_not_retried(browser):
    open_audio(browser, "refuses")
    browser.wait_for(lambda: calls(browser) == 1, message="one attempt")
    time.sleep(1)
    assert calls(browser) == 1


def test_reentrant_player_cannot_loop_the_decision(browser):
    """Security review R-01: page getters run inside the add-on's decision. A player whose getters
    re-fire loadedmetadata must not re-enter it: one switch and a handful of reads, not a recursion
    (one switch per nesting level) that runs until the stack overflows."""
    open_audio(browser, "reentrant")
    browser.wait_for(lambda: calls(browser) == 1, message="one switch")
    time.sleep(1)
    assert calls(browser) == 1
    assert browser.js("return __audio.reads()") < 50


def test_original_audio_off(browser):
    browser.set_settings(originalAudio=False)
    open_audio(browser, "auto")
    time.sleep(1.2)
    assert calls(browser) == 0

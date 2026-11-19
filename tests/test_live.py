"""Live tests: the shipped add-on against the real www.youtube.com (signed out).

Run with:  pytest -m live
These need network access and depend on what YouTube serves today, so they are kept out of
the default run. The canary tests switch features off and assert our hooks still match
something: when one fails, YouTube changed its markup and a selector needs updating.
"""
from __future__ import annotations

import time

import pytest
from selenium.webdriver.common.by import By

pytestmark = pytest.mark.live

# YouTube A/B-tests search: results are either yt-lockup-view-model or ytd-video-renderer.
SEARCH = "/results?search_query=guitar+lesson"
CHANNEL = "/@veritasium"
WATCH = "/watch?v=jNQXAC9IVRw"  # "Me at the zoo", the first YouTube video

SHORTS_SHELF = "grid-shelf-view-model:has(ytm-shorts-lockup-view-model-v2, ytm-shorts-lockup-view-model), ytd-reel-shelf-renderer"
SHORTS_TAB = 'yt-tab-shape[tab-title="Shorts"]'
GUIDE_SHORTS = 'ytd-guide-entry-renderer:has(> a#endpoint[title="Shorts"])'


@pytest.fixture()
def yt(live_browser):
    live_browser.reset_settings()
    return live_browser


def open_live(b, path: str, settle: float = 4.0):
    """Open a YouTube page, declining the regional consent screen if one appears."""
    b.driver.get(b.base + path)
    if "consent." in b.driver.current_url:
        for button in b.driver.find_elements(By.CSS_SELECTOR, "button"):
            if "Reject all" in (button.text or ""):
                button.click()
                break
        b.wait_for(lambda: "consent." not in b.driver.current_url, timeout=15, message="consent dismissed")
    b.wait_ready(timeout=15)
    time.sleep(settle)
    b.js("window.scrollTo(0, 1600)")
    time.sleep(1.5)


# ---- Canary: our hooks still exist on today's YouTube --------------------------------------

def test_canary_core_hooks_exist(yt):
    yt.set_settings(enabled=False)
    open_live(yt, SEARCH)
    assert yt.js("return document.querySelectorAll(arguments[0]).length", SHORTS_SHELF) > 0, "search Shorts shelf hook"
    assert yt.js("return document.querySelectorAll(':is(yt-lockup-view-model, ytd-video-renderer) a[href^=\"/watch\"]').length") > 3, "result lockups"
    assert yt.js("return document.querySelectorAll(arguments[0]).length", GUIDE_SHORTS) == 1, "guide Shorts entry"
    assert yt.js("return document.querySelectorAll('ytd-app > yt-ephemeral-actions').length") == 1,         "interruptions popup host (yt-ephemeral-actions)"
    open_live(yt, CHANNEL)
    assert yt.js("return document.querySelectorAll(arguments[0]).length", SHORTS_TAB) == 1, "channel Shorts tab"


# ---- Core 2 on the real site ------------------------------------------------------------------

def test_live_search_has_no_shorts(yt):
    open_live(yt, SEARCH)
    assert yt.js("return document.documentElement.dataset.rfyPage") == "search"
    assert not yt.any_visible(SHORTS_SHELF)
    assert not yt.any_visible('a[href^="/shorts/"]')
    assert yt.js(
        "return [...document.querySelectorAll('ytd-search :is(yt-lockup-view-model, ytd-video-renderer)')].filter(e => e.checkVisibility()).length"
    ) > 3, "normal results still visible"


def test_live_contain_keeps_channel_shorts_tab(yt):
    open_live(yt, CHANNEL)
    assert yt.all_visible(SHORTS_TAB)


def test_live_remove_hides_ways_in(yt):
    yt.set_settings(shorts="remove")
    open_live(yt, CHANNEL)
    assert yt.visible(SHORTS_TAB) == [False]
    assert yt.visible(GUIDE_SHORTS) == [False]


def test_live_remove_redirects_short_to_watch(yt):
    yt.set_settings(shorts="remove")
    yt.driver.get(yt.base + "/shorts/jNQXAC9IVRw")
    yt.wait_for(lambda: "/watch?v=jNQXAC9IVRw" in yt.driver.current_url, timeout=15,
                message="redirect to the normal player")


def test_live_watch_page_boots(yt):
    open_live(yt, WATCH)
    assert yt.js("return document.documentElement.dataset.rfyPage") == "watch"
    assert not yt.any_visible('ytd-watch-next-secondary-results-renderer a[href^="/shorts/"]')


# ---- Extra features on the real site ------------------------------------------------------------

AUTONAV = "#movie_player .ytp-autonav-toggle-button"


def test_canary_watch_and_guide_hooks(yt):
    yt.set_settings(enabled=False)
    open_live(yt, WATCH)
    assert yt.js("return document.querySelectorAll(arguments[0]).length", AUTONAV) == 1, "autoplay switch"
    for sel in [".ytp-endscreen-content", ".ytp-autonav-endscreen-countdown-overlay", "ytd-video-preview",
                "ytd-watch-next-secondary-results-renderer ytd-continuation-item-renderer"]:
        assert yt.js("return document.querySelectorAll(arguments[0]).length", sel) >= 1, sel
    open_live(yt, SEARCH)
    sections = yt.js("""
      return [...document.querySelectorAll('ytd-guide-section-renderer')].map(s =>
        [...s.querySelectorAll('a#endpoint[href]')].map(a => a.getAttribute('href')));
    """)
    explore = [s for s in sections if any(h.startswith("/feed/storefront") for h in s)]
    more = [s for s in sections if any(h.startswith("https://music.youtube.com") for h in s)]
    assert len(explore) == 1, "Quiet guide: Explore key matches exactly one section"
    assert len(more) == 1, "Quiet guide: More-from-YouTube key matches exactly one section"
    assert not any("/feed/subscriptions" in s for s in explore + more), "never the main section"


def test_live_autoplay_switched_off(yt):
    open_live(yt, WATCH)
    yt.wait_for(lambda: yt.js("return document.querySelector(arguments[0]).getAttribute('aria-checked')", AUTONAV) == "false",
                timeout=10, message="autoplay switched off")


def test_live_up_next_finite_behaviour(yt):
    """Behavioural canary: scrolling must not load a second batch of Up next."""
    open_live(yt, WATCH)
    sel = "ytd-watch-next-secondary-results-renderer yt-lockup-view-model"
    first = yt.js("return document.querySelectorAll(arguments[0]).length", sel)
    for _ in range(4):
        yt.js("window.scrollTo(0, document.documentElement.scrollHeight)")
        time.sleep(1.5)
    assert first > 0
    assert yt.js("return document.querySelectorAll(arguments[0]).length", sel) == first


def test_live_quiet_guide(yt):
    open_live(yt, SEARCH)
    hidden = yt.js("""
      return [...document.querySelectorAll('ytd-guide-section-renderer')]
        .filter(s => s.querySelector('a#endpoint[href^="/feed/storefront"], a#endpoint[href^="https://music.youtube.com"]'))
        .map(s => s.checkVisibility());
    """)
    assert hidden and not any(hidden)
    assert yt.all_visible('ytd-guide-entry-renderer:has(> a#endpoint[href="/feed/subscriptions"])')


def test_canary_audio_track_tags(yt):
    """Original audio's hook: track ids carry an acont tag (original / dubbed / dubbed-auto)."""
    yt.set_settings(enabled=False)
    open_live(yt, "/watch?v=26P1KyvrmjI&hl=es")  # widely dubbed video
    ids = yt.js("""
      const mp = document.getElementById('movie_player');
      return mp && mp.getAvailableAudioTracks ? mp.getAvailableAudioTracks().map(t => t.id) : [];
    """)
    import base64, re
    kinds = set()
    for i in ids:
        if ";" in i:
            raw = base64.b64decode(i.split(";", 1)[1] + "==", altchars=b"-_", validate=False).decode("latin-1")
            m = re.search(r"acont[^a-z]{0,4}(dubbed-auto|dubbed|original|descriptive|secondary)", raw)
            if m:
                kinds.add(m.group(1))
    assert "original" in kinds, f"no acont=original among {len(ids)} tracks"

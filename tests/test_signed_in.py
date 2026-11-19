"""Signed-in canary: checks the hooks that only exist for a signed-in account.

Several features (chronological Subscriptions, the home feed, watched-video dimming, search
shelves) only show their real markup to a signed-in account. These tests run the shipped add-on
in a COPY of a Firefox profile you are already signed in to. Your password is never needed or
touched; Selenium copies the profile to a temporary folder and deletes the copy afterwards.

    1. Close Firefox (so the profile isn't locked), or make a dedicated profile for this.
    2. Find the profile folder in about:profiles ("Root Directory").
    3. Run:
         set RFY_FIREFOX_PROFILE=C:\\path\\to\\profile        (PowerShell: $env:RFY_FIREFOX_PROFILE=...)
         pytest -m signedin

Run it before each release; when a test fails, YouTube changed the markup that feature uses.
"""
from __future__ import annotations

import os
import time

import pytest

from conftest import Browser, build_addon, make_driver

pytestmark = pytest.mark.signedin

PROFILE = os.environ.get("RFY_FIREFOX_PROFILE")


@pytest.fixture(scope="module")
def me(tmp_path_factory):
    if not PROFILE:
        pytest.skip("set RFY_FIREFOX_PROFILE to a signed-in Firefox profile folder")
    addon = build_addon(tmp_path_factory.mktemp("addon-signedin") / "addon", allow_localhost=False)
    driver = make_driver(addon, profile=PROFILE)
    b = Browser(driver, "https://www.youtube.com")
    yield b
    driver.quit()


def open_page(b, path, settle=5.0):
    b.driver.get(b.base + path)
    b.wait_ready(timeout=15)
    time.sleep(settle)


def test_signed_in(me):
    open_page(me, "/feed/subscriptions")
    assert me.js("return !!document.querySelector('#avatar-btn, ytd-topbar-menu-button-renderer img')"), \
        "profile does not look signed in"


def test_subscriptions_grid_and_sections(me):
    me.set_settings(enabled=False)
    open_page(me, "/feed/subscriptions")
    grid_items = me.js("return document.querySelectorAll('ytd-browse[page-subtype=\"subscriptions\"] ytd-rich-grid-renderer ytd-rich-item-renderer').length")
    assert grid_items > 5, "Subscriptions grid hook"
    me.set_settings(enabled=True)
    time.sleep(1)
    assert not me.any_visible('ytd-browse[page-subtype="subscriptions"] ytd-rich-section-renderer')


def test_home_finite(me):
    open_page(me, "/")
    sel = 'ytd-browse[page-subtype="home"] ytd-rich-item-renderer'
    first = me.js("return document.querySelectorAll(arguments[0]).length", sel)
    for _ in range(4):
        me.js("window.scrollTo(0, document.documentElement.scrollHeight)")
        time.sleep(1.5)
    assert first >= 8, "home grid hook"
    assert me.js("return document.querySelectorAll(arguments[0]).length", sel) == first, "home kept loading"


def test_watched_progress_bars_parse(me):
    me.set_settings(enabled=False)
    open_page(me, "/feed/history")
    widths = me.js("""
      return [...document.querySelectorAll('yt-thumbnail-overlay-progress-bar-view-model [style*="width"], ytd-thumbnail-overlay-resume-playback-renderer [style*="width"]')]
        .map(e => e.style.width).slice(0, 10);
    """)
    assert widths and all(w.endswith("%") for w in widths), f"progress bar widths: {widths}"


def test_search_has_no_injected_shelves(me):
    open_page(me, "/results?search_query=music")
    visible = me.js("""
      return [...document.querySelectorAll('ytd-search ytd-item-section-renderer > #contents > *')]
        .filter(e => e.checkVisibility() && !/^(yt-lockup-view-model|ytd-video-renderer|ytd-channel-renderer|ytd-playlist-renderer|ytd-ad-slot-renderer|ytd-continuation-item-renderer)$/i.test(e.tagName))
        .map(e => e.tagName.toLowerCase());
    """)
    assert visible == [], f"unexpected visible containers in search results: {visible}"

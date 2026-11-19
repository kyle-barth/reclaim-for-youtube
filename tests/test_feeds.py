"""E2E tests for feeds & navigation: search results only, home & Up next, quiet guide, watched videos."""
from __future__ import annotations

import time

import pytest
from selenium.webdriver.common.by import By


def t(name: str) -> str:
    return f'[data-test="{name}"]'


def count(b, selector: str) -> int:
    return b.js("return document.querySelectorAll(arguments[0]).length", selector)


# ---- Search results only -----------------------------------------------------------------

def test_search_injected_shelves_removed(browser):
    browser.open("/results?search_query=guitar")
    for name in ["search-people-also", "search-also-search", "search-for-you"]:
        assert not browser.any_visible(t(name)), name
    assert browser.all_visible(t("search-video"))
    assert browser.all_visible(t("search-channel"))
    assert browser.all_visible(t("search-latest-from")), "'Latest from' right after a channel result stays"
    assert browser.all_visible(t("search-video-legacy"))
    assert browser.all_visible(t("search-chapters")), "a result's own chapter carousel is never a shelf"


def test_search_shelves_back_when_off_but_shorts_still_contained(browser):
    browser.set_settings(searchResultsOnly=False)
    browser.open("/results?search_query=guitar")
    for name in ["search-people-also", "search-also-search", "search-for-you"]:
        assert browser.all_visible(t(name)), name
    assert not browser.any_visible(t("search-shorts-shelf")), "Shorts are the Shorts setting's call"


def test_search_does_not_own_shorts_shelves(browser):
    browser.set_settings(shorts="show")
    browser.open("/results?search_query=guitar")
    assert browser.all_visible(t("search-shorts-shelf")), "Search results only must not hide Shorts shelves"


# ---- Home page ----------------------------------------------------------------------------

def scroll_bottom(b, times=3):
    for _ in range(times):
        b.js("window.scrollTo(0, document.documentElement.scrollHeight)")
        time.sleep(0.4)


def test_home_finite_stops_after_first_page(browser):
    browser.open("/?fx=feed_grid")
    scroll_bottom(browser)
    assert browser.js("return window.__loads") == 0
    assert count(browser, t("tile")) == 24
    assert not browser.any_visible(t("home-section")), "injected home sections go under finite"
    assert browser.all_visible(t("grid"))


def test_home_default_keeps_loading(browser):
    # The section holds the history-off nudge, which Nag scrubber owns; switch that off here.
    browser.set_settings(homePage="default", nagScrubber=False)
    browser.open("/?fx=feed_grid")
    scroll_bottom(browser)
    assert browser.js("return window.__loads") >= 1
    assert browser.all_visible(t("home-section"))


@pytest.mark.parametrize("subtype", ["subscriptions", "channels"])
def test_finite_never_affects_other_grids(browser, subtype):
    browser.open(f"/feed/subscriptions?fx=feed_grid&subtype={subtype}")
    scroll_bottom(browser)
    assert browser.js("return window.__loads") >= 1


def test_home_search_box_only(browser):
    browser.set_settings(homePage="search")
    browser.open("/?fx=feed_grid")
    assert not browser.any_visible(t("grid"))
    assert not browser.any_visible(t("chips"))
    assert not browser.any_visible(t("nudge"))
    assert browser.all_visible(t("searchbox"))


def test_home_subscriptions_direct_load_redirects(browser):
    browser.set_settings(homePage="subscriptions")
    browser.driver.get(browser.base + "/")
    browser.wait_for(lambda: browser.driver.current_url == browser.base + "/feed/subscriptions",
                     message="redirect to subscriptions")


def test_home_subscriptions_logo_click_uses_router(browser):
    browser.set_settings(homePage="subscriptions")
    browser.open("/watch?v=fxvideo0001&fx=feed_grid")
    browser.driver.find_element(By.CSS_SELECTOR, t("logo")).click()
    browser.wait_for(lambda: browser.driver.current_url.startswith(browser.base + "/feed/subscriptions"),
                     message="logo goes to subscriptions")
    assert browser.js("return window.__routerClicks") == 1, "in-app navigation through the guide link"
    assert browser.js("return window.__noReload === true"), "no page reload"
    # Back returns to where we were, and stays there.
    browser.driver.back()
    time.sleep(2)
    assert "/watch?v=fxvideo0001" in browser.driver.current_url


def test_home_subscriptions_two_clicks_are_never_throttled(browser):
    browser.set_settings(homePage="subscriptions")
    browser.open("/watch?v=fxvideo0001&fx=feed_grid")
    for _ in range(2):
        browser.driver.find_element(By.CSS_SELECTOR, t("logo")).click()
        browser.wait_for(lambda: "/feed/subscriptions" in browser.driver.current_url, message="landed")
        browser.js("__fx.navigate('/watch?v=fxvideo0002&fx=feed_grid')")
        time.sleep(0.5)
    assert browser.js("return window.__routerClicks") == 2


def test_home_subscriptions_typed_load_back(browser):
    browser.set_settings(homePage="subscriptions")
    browser.open("/watch?v=fxvideo0001&fx=feed_grid")
    browser.driver.get(browser.base + "/")
    browser.wait_for(lambda: browser.driver.current_url == browser.base + "/feed/subscriptions", message="redirected")
    browser.driver.back()
    time.sleep(2)
    assert "/watch?v=fxvideo0001" in browser.driver.current_url, "Back is not bounced forward again"


def test_modified_click_on_logo_not_intercepted(browser):
    browser.set_settings(homePage="subscriptions")
    browser.open("/watch?v=fxvideo0001&fx=feed_grid")
    prevented = browser.js("""
      const a = document.querySelector('[data-test="logo"]');
      let prevented = null;
      a.addEventListener('click', e => { prevented = e.defaultPrevented; e.preventDefault(); }, {once: true});
      a.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, ctrlKey: true, button: 0}));
      return prevented;
    """)
    assert prevented is False


def test_default_settings_never_redirect(browser):
    browser.driver.get(browser.base + "/?fx=feed_grid")
    browser.wait_ready()
    time.sleep(1)
    assert browser.driver.current_url == browser.base + "/?fx=feed_grid"


# ---- Up next ---------------------------------------------------------------------------------

def test_up_next_finite(browser):
    browser.open("/watch?v=aaaaaaaaaa1&fx=upnext_watch", settle=1.2)
    assert browser.js("return window.__relatedLoads") == 0
    assert count(browser, t("related-video")) == 20
    assert browser.js("return window.__commentLoads") >= 1, "comments keep loading"


def test_up_next_hidden_keeps_other_panels(browser):
    browser.set_settings(upNext="hidden")
    browser.open("/watch?v=aaaaaaaaaa1&fx=upnext_watch")
    assert not browser.any_visible(t("related"))
    assert browser.all_visible(t("playlist"))
    assert browser.all_visible(t("panel"))


def test_up_next_default_keeps_loading(browser):
    browser.set_settings(upNext="default")
    browser.open("/watch?v=aaaaaaaaaa1&fx=upnext_watch", settle=1.2)
    assert browser.js("return window.__relatedLoads") >= 1


# ---- Quiet guide ----------------------------------------------------------------------------

def test_quiet_guide(browser):
    browser.open("/?fx=guide")
    for name in ["sec-explore", "sec-more", "main-premium"]:
        assert not browser.any_visible(t(name)), name
    for name in ["home", "shorts", "subs", "sec-subscriptions", "sub-music-topic", "sec-you", "sec-settings", "footer"]:
        assert browser.all_visible(t(name)), name


@pytest.mark.parametrize("shorts", ["contain", "show"])
def test_quiet_guide_never_touches_shorts_entry(browser, shorts):
    browser.set_settings(shorts=shorts)
    browser.open("/?fx=guide")
    assert browser.all_visible(t("shorts"))


def test_quiet_guide_off(browser):
    browser.set_settings(quietGuide=False)
    browser.open("/?fx=guide")
    for name in ["sec-explore", "sec-more", "main-premium"]:
        assert browser.all_visible(t(name)), name


# ---- Watched videos ---------------------------------------------------------------------------

def opacity(b, name: str) -> float:
    return float(b.js("return getComputedStyle(document.querySelector(arguments[0])).opacity", t(name)))


WATCHED = ["w100", "w95", "w92", "legacy100"]
UNWATCHED = ["w89", "w40", "wnone"]


def test_watched_dim_default(browser):
    browser.open("/feed/subscriptions?fx=watched", settle=1)
    for name in WATCHED:
        assert opacity(browser, name) < 0.5, name
    for name in UNWATCHED:
        assert opacity(browser, name) == 1, name


def test_watched_hide_with_legacy_row_fallback(browser):
    browser.set_settings(watchedVideos="hide")
    browser.open("/feed/subscriptions?fx=watched", settle=1)
    for name in WATCHED:
        assert not browser.any_visible(t(name)), name
    for name in UNWATCHED:
        assert browser.all_visible(t(name)), name
    assert browser.all_visible(t("row100")), "legacy row grids dim instead of leaving holes"
    assert opacity(browser, "row100") < 0.5


def test_watched_late_overlay_and_recycling(browser):
    browser.open("/feed/subscriptions?fx=watched", settle=1)
    browser.js("document.querySelector('#contents').append(__fx.lockupTile(97, 'late'))")
    browser.wait_for(lambda: opacity(browser, "late") < 0.5, message="late tile dimmed")
    # Recycled tile: now a different video at 10%.
    browser.js("document.querySelector('[data-test=\"w100\"] [style*=width]').style.width = '10%'")
    browser.js("document.querySelector('#contents').append(document.createElement('span'))")  # nudge a scan
    browser.wait_for(lambda: opacity(browser, "w100") == 1, message="recycled tile un-dimmed")


@pytest.mark.parametrize("scope", ["search", "channels", "history", "playlist"])
def test_watched_never_on_excluded_surfaces(browser, scope):
    browser.set_settings(watchedVideos="hide")
    browser.open(f"/feed/subscriptions?fx=watched&scope={scope}", settle=1)
    for name in WATCHED:
        assert browser.all_visible(t(name)), f"{scope}: {name}"


def test_watched_show_writes_nothing(browser):
    browser.set_settings(watchedVideos="show")
    browser.open("/feed/subscriptions?fx=watched", settle=1)
    assert count(browser, "[data-rfy-watched]") == 0

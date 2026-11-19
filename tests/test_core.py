"""E2E tests for the three core features, against YouTube-shaped fixtures."""
from __future__ import annotations

import time

import pytest

INTERRUPTIONS_TOAST = """
<yt-notification-action-renderer>
  <span id="text">Experiencing interruptions?</span>
  <yt-button-renderer id="action-button">
    <a href="https://support.google.com/youtube/answer/0000000?p=ad_blocker">Find out why</a>
  </yt-button-renderer>
</yt-notification-action-renderer>
"""

TEXT_ONLY_TOAST = """
<yt-notification-action-renderer><span id="text">Experiencing interruptions?</span>
<yt-button-renderer id="action-button"><a href="https://support.google.com/youtube/answer/1">Find out why</a></yt-button-renderer>
</yt-notification-action-renderer>
"""

OTHER_TOAST = """
<yt-notification-action-renderer><span id="text">Saved to Watch later</span>
<yt-button-renderer id="action-button"><a href="/playlist?list=WL">View</a></yt-button-renderer>
</yt-notification-action-renderer>
"""


def t(name: str) -> str:
    return f'[data-test="{name}"]'


# ---- Boot / plumbing ---------------------------------------------------------------------

def test_content_script_marks_page_type(browser):
    for path, page in [
        ("/", "home"),
        ("/feed/subscriptions", "subscriptions"),
        ("/results?search_query=guitar", "search"),
        ("/watch?v=aaaaaaaaaa1", "watch"),
        ("/shorts/abcdefghijk", "shorts"),
        ("/@somechannel", "channel"),
        ("/@somechannel/shorts", "channel-shorts"),
        ("/feed/history", "history"),
    ]:
        browser.open(path, settle=0.2)
        assert browser.js("return document.documentElement.dataset.rfyPage") == page, path


def test_master_switch_off_restores_youtube(browser):
    browser.set_settings(enabled=False)
    browser.open("/results?search_query=guitar")
    assert browser.all_visible(t("search-shorts-shelf"))
    assert browser.all_visible(t("chip-shorts"))
    assert not browser.js("return document.documentElement.hasAttribute('data-rfy')")


# ---- Core 1: "Experiencing interruptions?" -----------------------------------------------

def test_interruptions_toast_hidden_and_not_blocking_clicks(browser):
    browser.open("/")
    browser.js("__fx.toast(arguments[0])", INTERRUPTIONS_TOAST)
    browser.wait_for(lambda: not browser.any_visible("tp-yt-paper-toast#toast"), message="toast hidden")
    # Nothing invisible left over the page: the element under the toast's spot is what's beneath it.
    under = browser.js(
        "const r = document.querySelector('[data-test=\"under-toast\"]').getBoundingClientRect();"
        "return document.elementFromPoint(r.left + 20, r.top + 20).dataset.test;"
    )
    assert under == "under-toast"


def test_interruptions_text_fallback(browser):
    browser.open("/")
    browser.js("__fx.toast(arguments[0])", TEXT_ONLY_TOAST)
    browser.wait_for(lambda: not browser.any_visible("tp-yt-paper-toast#toast"), message="toast hidden by text")


def test_reused_toast_shows_other_messages(browser):
    browser.open("/")
    browser.js("__fx.toast(arguments[0])", INTERRUPTIONS_TOAST)
    browser.wait_for(lambda: not browser.any_visible("tp-yt-paper-toast#toast"), message="toast hidden")
    browser.js("__fx.toast(arguments[0])", OTHER_TOAST)
    browser.wait_for(lambda: browser.all_visible("tp-yt-paper-toast#toast"), message="other toast visible")


def test_interruptions_ephemeral_host_hidden_then_reused(browser):
    """Current form (captured live 2026-11): a reused yt-ephemeral-actions host with only text."""
    browser.open("/")
    eph = '[data-test="ephemeral"]'
    browser.js("document.querySelector(arguments[0]).textContent = 'Experiencing interruptions?'", eph)
    browser.wait_for(lambda: browser.visible(eph) == [False], message="ephemeral popup hidden")
    # YouTube reuses the host for other messages: those must show.
    browser.js("document.querySelector(arguments[0]).textContent = 'Saved to Watch later'", eph)
    browser.wait_for(lambda: browser.visible(eph) == [True], message="other message visible")


def test_interruptions_ephemeral_text_changed_in_place(browser):
    """The text node's data changing in place (characterData) is caught too."""
    browser.open("/")
    eph = '[data-test="ephemeral"]'
    browser.js("document.querySelector(arguments[0]).textContent = 'Saved to Watch later'", eph)
    time.sleep(0.4)
    assert browser.visible(eph) == [True]
    browser.js("document.querySelector(arguments[0]).firstChild.data = 'Experiencing interruptions?'", eph)
    browser.wait_for(lambda: browser.visible(eph) == [False], message="hidden after in-place text change")


def test_interruptions_ephemeral_toggle_off(browser):
    browser.set_settings(hideInterruptions=False)
    browser.open("/")
    eph = '[data-test="ephemeral"]'
    browser.js("document.querySelector(arguments[0]).textContent = 'Experiencing interruptions?'", eph)
    time.sleep(0.6)
    assert browser.visible(eph) == [True]


def test_interruptions_toggle_off(browser):
    browser.set_settings(hideInterruptions=False)
    browser.open("/")
    browser.js("__fx.toast(arguments[0])", INTERRUPTIONS_TOAST)
    time.sleep(0.5)
    assert browser.all_visible("tp-yt-paper-toast#toast")


# ---- Core 2: Shorts containment ------------------------------------------------------------

def test_contain_hides_shorts_on_home(browser):
    browser.open("/")
    assert not browser.any_visible(t("home-shorts-shelf"))
    assert not browser.any_visible(t("home-short-item"))
    assert browser.all_visible(t("home-video"))
    assert browser.all_visible(t("home-video-2"))
    # Contain keeps the way into the Shorts tab.
    assert browser.all_visible(t("guide-shorts"))
    assert browser.all_visible(t("mini-shorts"))


def test_contain_hides_shorts_in_search(browser):
    browser.open("/results?search_query=guitar")
    for name in ["search-shorts-shelf", "search-reel-shelf", "search-short-result", "search-short-lockup", "chip-shorts"]:
        assert not browser.any_visible(t(name)), name
    assert browser.all_visible(t("search-video"))
    assert browser.all_visible(t("chip-all"))
    assert browser.all_visible(t("search-ad")), "ads are uBlock Origin's job; we leave them alone"


def test_contain_hides_shorts_on_watch_and_history(browser):
    browser.open("/watch?v=aaaaaaaaaa1")
    assert not browser.any_visible(t("watch-reel-shelf"))
    assert not browser.any_visible(t("related-short"))
    assert browser.all_visible(t("related-video"))
    browser.open("/feed/history")
    assert not browser.any_visible(t("history-reel-shelf"))
    assert browser.all_visible(t("history-video"))


def test_contain_keeps_shorts_in_shorts_tabs(browser):
    browser.open("/shorts/abcdefghijk")
    assert browser.all_visible(t("shorts-player"))
    assert browser.all_visible(t("shorts-page-lockup"))
    browser.open("/@somechannel/shorts")
    assert browser.all_visible(t("channel-short-tile"))
    assert browser.all_visible(t("tab-shorts"))


def test_contain_channel_home_hides_shorts_shelf_but_keeps_tab(browser):
    browser.open("/@somechannel")
    assert not browser.any_visible(t("channel-shorts-section"))
    assert browser.all_visible(t("tab-shorts"))
    assert browser.all_visible(t("channel-video"))


def test_show_mode_leaves_shorts_alone(browser):
    browser.set_settings(shorts="show")
    browser.open("/results?search_query=guitar")
    assert browser.all_visible(t("search-shorts-shelf"))
    assert browser.all_visible(t("chip-shorts"))
    browser.open("/")
    assert browser.all_visible(t("home-shorts-shelf"))


def test_remove_mode_hides_ways_in(browser):
    browser.set_settings(shorts="remove")
    browser.open("/")
    assert not browser.any_visible(t("guide-shorts"))
    assert not browser.any_visible(t("mini-shorts"))
    assert browser.all_visible(t("guide-home"))
    assert browser.all_visible(t("guide-subs"))
    browser.open("/@somechannel")
    assert not browser.any_visible(t("tab-shorts"))
    assert browser.all_visible(t("tab-videos"))


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/shorts/abcdefghijk", "/watch?v=abcdefghijk"),
        ("/shorts", "/"),
        ("/@somechannel/shorts", "/@somechannel/videos"),
    ],
)
def test_remove_mode_redirects(browser, path, expected):
    browser.set_settings(shorts="remove")
    browser.driver.get(browser.base + path)
    browser.wait_for(
        lambda: browser.driver.current_url == browser.base + expected,
        message=f"redirect to {expected} (now {browser.driver.current_url})",
    )


def test_remove_mode_opens_short_links_in_normal_player(browser):
    browser.set_settings(shorts="remove")
    browser.open("/watch?v=aaaaaaaaaa1")
    browser.js("document.querySelector('[data-test=\"desc-short-link\"]').click()")
    browser.wait_for(
        lambda: browser.driver.current_url == browser.base + "/watch?v=dddddddddd1",
        message="short link opened in the normal player",
    )


def test_spa_navigation_and_lazy_content(browser):
    """Shorts that arrive after an in-app navigation or a lazy load are hidden too."""
    browser.open("/")
    browser.js(
        "__fx.navigate('/results?search_query=x', arguments[0]);",
        """<ytd-search><ytd-item-section-renderer><div id="contents">
             <yt-lockup-view-model data-test="spa-video"><a href="/watch?v=zzzzzzzzzz1">v</a></yt-lockup-view-model>
           </div></ytd-item-section-renderer></ytd-search>""",
    )
    browser.wait_for(lambda: browser.js("return document.documentElement.dataset.rfyPage") == "search",
                     message="page type follows SPA navigation")
    browser.js(
        "__fx.append('#contents', arguments[0], 300);",
        """<grid-shelf-view-model data-test="spa-shorts-shelf"><ytm-shorts-lockup-view-model-v2>
             <a href="/shorts/zzzzzzzzzz2">s</a></ytm-shorts-lockup-view-model-v2></grid-shelf-view-model>""",
    )
    browser.wait_for(lambda: browser.visible(t("spa-shorts-shelf")) == [False], message="lazy shelf hidden")
    assert browser.all_visible(t("spa-video"))


def test_settings_apply_live_without_reload(browser):
    browser.open("/results?search_query=guitar")
    assert not browser.any_visible(t("search-shorts-shelf"))
    # Settings are written from the extension tab; the YouTube tab updates without a reload.
    browser.js("window.__noReload = true")
    browser.set_settings(shorts="show")
    browser.wait_for(lambda: browser.all_visible(t("search-shorts-shelf")), message="shelf back after toggle")
    browser.wait_for(lambda: browser.all_visible(t("chip-shorts")), message="chip back after toggle")
    assert browser.js("return window.__noReload === true")


# ---- Core 3: chronological subscriptions ---------------------------------------------------

def test_subscriptions_only_chronological_videos(browser):
    browser.open("/feed/subscriptions")
    for name in ["subs-most-relevant", "subs-shorts-shelf", "subs-playables", "subs-recommended", "subs-post", "subs-short-item"]:
        assert not browser.any_visible(t(name)), name
    order = browser.js(
        "return [...document.querySelectorAll('ytd-rich-item-renderer[data-order]')]"
        ".filter(e => e.checkVisibility()).map(e => e.dataset.order)"
    )
    assert order == ["1", "2", "3", "4"]


def test_subscriptions_toggle_off(browser):
    browser.set_settings(subscriptionsChronological=False, shorts="show")
    browser.open("/feed/subscriptions")
    for name in ["subs-most-relevant", "subs-shorts-shelf", "subs-playables", "subs-recommended", "subs-post"]:
        assert browser.all_visible(t(name)), name

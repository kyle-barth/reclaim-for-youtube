"""E2E tests for the Nag scrubber, against YouTube-shaped fixtures.

Letters refer to the E2E table in process/ideation/round3-attention.md (#6).
Fixtures: nags_home (inline banners, mealbars, the home nudge, static popup dialogs),
nags_subs (the nudge under Subscriptions) and nags_watch (dialogs with an iron-overlay stand-in).
"""
from __future__ import annotations

import time

import pytest
from selenium.webdriver.common.by import By

HOME = "/?fx=nags_home"
SUBS = "/feed/subscriptions?fx=nags_subs"
WATCH = "/watch?v=x&fx=nags_watch"

PROMOS = [
    "banner-premium",
    "promo-premium-query",
    "promo-premium-absolute",
    "promo-paid-memberships",
    "promo-music",
    "promo-music-premium",
    "promo-tv",
    "promo-notifications",
    "promo-app-ios",
    "promo-app-android",
    "promo-inline-mealbar",
]
KEEP = ["banner-trending", "keep-premium-lookalike", "keep-tos-inline", "keep-no-link", "keep-plain-link"]

ENFORCEMENT = (
    "<ytd-enforcement-message-view-model><span>Ad blockers are not allowed on YouTube</span>"
    '<a href="/premium">Try YouTube Premium</a></ytd-enforcement-message-view-model>'
)
BLOCKER_TOAST = (
    '<yt-notification-action-renderer><span id="text">Experiencing interruptions?</span>'
    '<yt-button-renderer id="action-button"><a href="https://support.google.com/youtube/answer/0000000?p=ad_blocker">'
    "Find out why</a></yt-button-renderer></yt-notification-action-renderer>"
)


def t(name: str) -> str:
    return f'[data-test="{name}"]'


def isolate(browser, **extra):
    """Switch off the features that also hide home/subscriptions sections, so only ours acts."""
    browser.set_settings(homePage="default", subscriptionsChronological=False, **extra)


def probe(browser, name: str) -> tuple[int, int]:
    """(frames observed, frames hidden) from the fixture's per-frame probe."""
    return tuple(browser.js(
        "return [window.__probe.frames[arguments[0]] || 0, window.__probe.hidden[arguments[0]] || 0];", name
    ))


def calls(browser, name: str) -> int:
    return browser.js("return __fx.calls(arguments[0])", name)


def is_open(browser, name: str) -> bool:
    return browser.js("return __fx.isOpen(arguments[0])", name)


def backdrop(browser) -> bool:
    return browser.js("return __fx.backdrop()")


def body_overflow(browser) -> str:
    return browser.js("return getComputedStyle(document.body).overflowY")


def start_video(browser):
    assert browser.driver.execute_async_script("__fx.play().then(arguments[0])") == "playing"
    assert browser.js("return document.querySelector('#movie_player video').paused") is False


def video_paused(browser) -> bool:
    return browser.js("return document.querySelector('#movie_player video').paused")


def show_dialog(browser, name: str, markup: str | None = None, **opts):
    browser.js(
        "__fx.dialog(arguments[0], arguments[1] || __fx.MEALBAR, arguments[2]); __fx.open(arguments[0]);",
        name, markup, opts,
    )


def real_click(browser, name: str):
    """A WebDriver click: trusted, so it counts as the user asking."""
    browser.driver.find_element(By.CSS_SELECTOR, t(name)).click()


# ---- Inline promos and the home nudge (CSS) -------------------------------------------------

def test_c_banners_hidden_only_with_a_promo_link(browser):
    isolate(browser)
    browser.open(HOME)
    assert not browser.any_visible(t("banner-premium"))
    assert browser.all_visible(t("banner-trending"))


def test_every_promo_destination_hidden_and_near_misses_kept(browser):
    isolate(browser)
    browser.open(HOME)
    for name in PROMOS:
        assert browser.visible(t(name)) == [False], name
    for name in KEEP:
        assert browser.visible(t(name)) == [True], name
    assert browser.all_visible(t("home-video"))


def test_a_mealbar_dialog_without_backdrop_hidden(browser):
    isolate(browser)
    browser.open(HOME)
    assert browser.visible(t("static-mealbar-dialog")) == [False]


def test_b_tos_notice_in_mealbar_kept(browser):
    isolate(browser)
    browser.open(HOME)
    assert browser.visible(t("static-tos-dialog")) == [True]


def test_h_history_nudge_hidden_on_home_only(browser):
    isolate(browser)
    browser.open(HOME)
    assert browser.visible(t("home-nudge")) == [False]
    assert browser.visible(t("home-other-section")) == [True], "only the nudge's section"
    browser.open(SUBS)
    assert browser.visible(t("subs-nudge")) == [True]


# ---- Solicited promos ---------------------------------------------------------------------

def test_d_promo_shown_right_after_a_click_stays(browser):
    browser.open(WATCH)
    real_click(browser, "stub-mealbar")  # handler shows the mealbar dialog 200 ms later
    browser.wait_for(lambda: browser.visible(t("solicited")) == [True], message="solicited mealbar visible")
    time.sleep(0.5)
    assert browser.visible(t("solicited")) == [True]
    frames, hidden = probe(browser, "solicited")
    assert frames > 0 and hidden == 0, "never hidden, not even for a frame"


def test_d_promo_shown_long_after_a_click_hidden(browser):
    browser.open(WATCH)
    browser.js("document.querySelector(arguments[0]).dataset.delay = '3000';"
               "document.querySelector(arguments[0]).dataset.name = 'late';", t("stub-mealbar"))
    real_click(browser, "stub-mealbar")
    browser.wait_for(lambda: browser.js("return !!document.querySelector(arguments[0])", t("late")),
                     timeout=6, message="late mealbar inserted")
    time.sleep(0.3)
    assert browser.visible(t("late")) == [False]
    assert calls(browser, "late") == 0, "a non-modal mealbar is CSS's job, never dismissed"


def test_d_inline_banner_after_a_click_stays(browser):
    isolate(browser)
    browser.open(HOME)
    real_click(browser, "stub-banner")
    browser.wait_for(lambda: browser.visible(t("inserted-banner")) == [True], message="solicited banner visible")
    time.sleep(0.3)
    frames, hidden = probe(browser, "inserted-banner")
    assert frames > 0 and hidden == 0
    # The same element re-inserted later with no input is a new, unsolicited show.
    time.sleep(1.5)
    browser.js("const b = document.querySelector(arguments[0]); b.parentElement.append(b);", t("inserted-banner"))
    browser.wait_for(lambda: browser.visible(t("inserted-banner")) == [False], message="re-shown banner hidden")


def test_k_reused_element_judged_on_every_show(browser):
    browser.open(WATCH)
    # First show, no recent input: hidden.
    show_dialog(browser, "reused")
    time.sleep(0.4)
    assert is_open(browser, "reused")
    assert browser.visible(t("reused")) == [False]
    # Closed, then re-shown 200 ms after a real click: visible.
    browser.js("__fx.userClose('reused')")
    time.sleep(0.2)
    frames_before, hidden_before = probe(browser, "reused")
    real_click(browser, "stub-reopen")
    browser.wait_for(lambda: is_open(browser, "reused"), message="re-shown")
    browser.wait_for(lambda: browser.visible(t("reused")) == [True], message="solicited re-show visible")
    time.sleep(0.4)
    frames_after, hidden_after = probe(browser, "reused")
    assert frames_after > frames_before and hidden_after == hidden_before, "visible for the whole second show"
    # Closed, then re-shown 3 s later with no input: hidden again.
    browser.js("__fx.userClose('reused')")
    time.sleep(3)
    browser.js("__fx.open('reused')")
    time.sleep(0.4)
    assert is_open(browser, "reused")
    assert browser.visible(t("reused")) == [False]
    assert calls(browser, "reused") == 0


# ---- Modal promos (JS only) ------------------------------------------------------------------

def test_e_modal_promo_dismissed_through_its_own_path(browser):
    browser.open(WATCH)
    start_video(browser)
    assert body_overflow(browser) != "hidden"
    show_dialog(browser, "modal-promo", modal=True, pausesVideo=True)
    browser.wait_for(lambda: calls(browser, "modal-promo") == 1, message="dismiss called")
    browser.wait_for(lambda: not is_open(browser, "modal-promo"), message="dialog closed")
    assert browser.visible(t("modal-promo")) == [False]
    assert not backdrop(browser), "backdrop released"
    assert body_overflow(browser) != "hidden", "scroll restored"
    browser.wait_for(lambda: not video_paused(browser), timeout=4, message="video resumed")
    time.sleep(1.5)
    assert calls(browser, "modal-promo") == 1
    _, hidden = probe(browser, "modal-promo")
    assert hidden == 0, "CSS never hid the modal while it was open"


def test_e_video_the_user_paused_stays_paused(browser):
    browser.open(WATCH)
    start_video(browser)
    browser.js("document.querySelector('#movie_player video').pause()")
    time.sleep(1.5)  # paused well before the promo: not the dialog's doing
    show_dialog(browser, "modal-promo", modal=True, pausesVideo=True)
    browser.wait_for(lambda: not is_open(browser, "modal-promo"), message="dialog closed")
    time.sleep(1.5)
    assert video_paused(browser)


def test_j_failed_dismissal_leaves_dialog_visible_and_closable(browser):
    browser.open(WATCH)
    show_dialog(browser, "stuck-promo", modal=True, noop=True)
    browser.wait_for(lambda: calls(browser, "stuck-promo") == 1, message="dismiss called")
    time.sleep(2)
    assert is_open(browser, "stuck-promo")
    assert browser.visible(t("stuck-promo")) == [True]
    assert backdrop(browser), "backdrop untouched"
    assert calls(browser, "stuck-promo") == 1, "no retries"
    frames, hidden = probe(browser, "stuck-promo")
    assert frames > 0 and hidden == 0, "visible every frame it was open"
    # Still closable by hand, and then nothing is left behind.
    browser.js("__fx.userClose('stuck-promo')")
    assert not backdrop(browser)
    assert body_overflow(browser) != "hidden"


def test_l_users_own_dialog_is_never_disturbed(browser):
    browser.open(WATCH)
    # An earlier, non-modal promo mealbar: hidden by CSS.
    show_dialog(browser, "earlier")
    time.sleep(0.4)
    assert browser.visible(t("earlier")) == [False]
    # The user opens Share (modal). While its backdrop is attached, CSS steps back.
    real_click(browser, "share-button")
    browser.wait_for(lambda: backdrop(browser), message="share backdrop")
    browser.wait_for(lambda: browser.visible(t("earlier")) == [True], message="earlier mealbar shows (accepted edge)")
    time.sleep(1.6)  # well past the solicited window
    show_dialog(browser, "modal-promo", modal=True)
    time.sleep(2)
    assert calls(browser, "modal-promo") == 0, "promo over the user's dialog is left alone"
    assert browser.visible(t("modal-promo")) == [True]
    assert calls(browser, "share") == 0 and is_open(browser, "share")
    assert browser.visible(t("share")) == [True]
    assert backdrop(browser)
    # The user closes both: the earlier mealbar is hidden again.
    browser.js("__fx.userClose('modal-promo'); __fx.userClose('share');")
    assert not backdrop(browser)
    browser.wait_for(lambda: browser.visible(t("earlier")) == [False], message="earlier mealbar hidden again")
    assert calls(browser, "earlier") == 0


def test_solicited_modal_promo_left_alone(browser):
    browser.open(WATCH)
    # A Premium-only button whose explanation is a modal promo.
    browser.js("const b = document.createElement('button'); b.dataset.test = 'stub-modal'; b.textContent = 'Premium only';"
               "b.addEventListener('click', () => setTimeout(() => {"
               "  __fx.dialog('asked', __fx.MEALBAR, {modal: true}); __fx.open('asked'); }, 200));"
               "document.querySelector('#primary').prepend(b);")
    real_click(browser, "stub-modal")
    browser.wait_for(lambda: browser.js("return !!document.querySelector(arguments[0])", t("asked")), message="shown")
    time.sleep(2)
    assert calls(browser, "asked") == 0
    assert browser.visible(t("asked")) == [True]


# ---- Traps: things the Nag scrubber must never touch ---------------------------------------

def test_f_core1_toast_untouched_when_core1_is_off(browser):
    browser.set_settings(hideInterruptions=False)
    browser.open(WATCH)
    browser.js("__fx.toast(arguments[0])", BLOCKER_TOAST)
    time.sleep(0.5)
    assert browser.all_visible("tp-yt-paper-toast#toast")
    # Not even with a promo link inside: a toast is not a listed container.
    browser.js("__fx.toast(arguments[0])", '<span>Saved</span><a href="/premium">Premium</a>')
    time.sleep(0.5)
    assert browser.all_visible("tp-yt-paper-toast#toast")


def test_g_enforcement_dialog_untouched(browser):
    browser.open(WATCH)
    show_dialog(browser, "enforcement", ENFORCEMENT, modal=True)
    time.sleep(2)
    assert calls(browser, "enforcement") == 0
    assert is_open(browser, "enforcement")
    assert browser.visible(t("enforcement")) == [True]
    assert backdrop(browser)


def test_g_enforcement_dialog_untouched_even_with_a_mealbar_inside(browser):
    browser.open(WATCH)
    browser.js("__fx.dialog('enforcement', arguments[0] + __fx.MEALBAR, {modal: true}); __fx.open('enforcement');",
               ENFORCEMENT)
    time.sleep(2)
    assert calls(browser, "enforcement") == 0
    assert browser.visible(t("enforcement")) == [True]


# ---- Off -------------------------------------------------------------------------------------

@pytest.mark.parametrize("patch", [{"nagScrubber": False}, {"enabled": False}], ids=["feature-off", "master-off"])
def test_i_off_everything_visible(browser, patch):
    isolate(browser, **patch)
    browser.open(HOME)
    for name in PROMOS + KEEP + ["home-nudge", "static-mealbar-dialog", "static-tos-dialog"]:
        assert browser.visible(t(name)) == [True], name
    browser.open(WATCH)
    show_dialog(browser, "modal-promo", modal=True)
    show_dialog(browser, "mealbar")
    time.sleep(2)
    assert calls(browser, "modal-promo") == 0
    assert browser.visible(t("modal-promo")) == [True]
    assert browser.visible(t("mealbar")) == [True]


def test_i_toggle_applies_live(browser):
    isolate(browser)
    browser.open(HOME)
    assert not browser.any_visible(t("banner-premium"))
    browser.js("window.__noReload = true")
    browser.set_settings(nagScrubber=False)
    browser.wait_for(lambda: browser.all_visible(t("banner-premium")), message="banner back")
    browser.set_settings(nagScrubber=True)
    browser.wait_for(lambda: not browser.any_visible(t("banner-premium")), message="banner hidden again")
    assert browser.js("return window.__noReload === true")

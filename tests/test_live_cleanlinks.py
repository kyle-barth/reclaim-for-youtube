"""Live spike and canary for Clean links: the shipped add-on against the real www.youtube.com.

Run with:  pytest -m live tests/test_live_cleanlinks.py

The spike is the gate from process/ideation/round3-control.md (#10). It passes if both hold:
  - YouTube's Share → Copy produces a clean link with the toggle on (through the writeText
    wrapper, or, if YouTube uses execCommand, through the copy listener);
  - copying still works when the wrapper is forced to throw.
Real WebDriver clicks (trusted, with user activation) drive Share and Copy; the clipboard is read
from the privileged browser context. Page-side spies record which clipboard API YouTube used.
"""
from __future__ import annotations

import time

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from conftest import Browser, make_driver
from test_cleanlinks import SENTINEL, build_fault_addon, read_clipboard, write_clipboard

pytestmark = pytest.mark.live

WATCH = "/watch?v=jNQXAC9IVRw"  # "Me at the zoo"
SHARE_BUTTON = 'ytd-watch-metadata button[aria-label="Share"]'
SHARE_BOX = "ytd-popup-container input#share-url"
COPY_BUTTON = "ytd-popup-container #copy-button button"


@pytest.fixture()
def yt(live_browser):
    live_browser.reset_settings()
    return live_browser


@pytest.fixture(scope="module")
def yt_fault(tmp_path_factory):
    """A second live Firefox with the fault-injected test build (see test_cleanlinks.py)."""
    addon = build_fault_addon(tmp_path_factory.mktemp("addon-live-fault") / "addon", allow_localhost=False)
    driver = make_driver(addon)
    b = Browser(driver, "https://www.youtube.com")
    yield b
    driver.quit()


def open_live(b, path: str, settle: float = 4.0):
    """Open a YouTube page, declining the regional consent screen or lightbox if one appears."""
    b.driver.get(b.base + path)
    if "consent." in b.driver.current_url:
        for button in b.driver.find_elements(By.CSS_SELECTOR, "button"):
            if "Reject all" in (button.text or ""):
                button.click()
                break
        b.wait_for(lambda: "consent." not in b.driver.current_url, timeout=15, message="consent dismissed")
    b.wait_ready(timeout=15)
    time.sleep(settle)
    for button in b.driver.find_elements(By.CSS_SELECTOR, "ytd-consent-bump-v2-lightbox button"):
        if button.is_displayed() and "Reject all" in (button.text or ""):
            button.click()
            time.sleep(2)
            break


SPIES = """
window.__spy = [];
const log = (...a) => window.__spy.push(a.join(' '));
const clip = navigator.clipboard;
const writeText = clip.writeText;
clip.writeText = function (t) { log('writeText', t); return writeText.call(clip, t); };
const write = clip.write;
clip.write = function (...a) { log('write'); return write.apply(clip, a); };
const exec = document.execCommand.bind(document);
document.execCommand = function (c, ...r) { log('execCommand', c); return exec(c, ...r); };
"""


def visible_element(b, selector: str, timeout: float = 15):
    def find():
        for el in b.driver.find_elements(By.CSS_SELECTOR, selector):
            if el.is_displayed():
                return el
        return None
    return b.wait_for(find, timeout=timeout, message=selector)


def share_and_copy(b) -> tuple[str, str | None, list[str]]:
    """Click Share, then Copy, with real clicks. Returns (share box value, clipboard, spy log)."""
    b.js(SPIES)
    write_clipboard(b.driver, SENTINEL)
    visible_element(b, SHARE_BUTTON).click()
    box = visible_element(b, SHARE_BOX)
    b.wait_for(lambda: "youtu" in (box.get_attribute("value") or ""), message="share link")
    shown = box.get_attribute("value")
    visible_element(b, COPY_BUTTON).click()
    b.wait_for(lambda: read_clipboard(b.driver) != SENTINEL, timeout=5, message="clipboard written")
    copied = read_clipboard(b.driver)
    spy = b.js("return window.__spy.slice()")
    ActionChains(b.driver).send_keys(Keys.ESCAPE).perform()
    return shown, copied, spy


# ---- The spike ---------------------------------------------------------------------------------

def test_spike_share_copy_is_clean(yt):
    open_live(yt, WATCH)
    shown, copied, spy = share_and_copy(yt)
    print(f"\nshare box: {shown}\nclipboard: {copied}\nYouTube used: {spy}")
    assert "si=" in shown, "the share box itself shows the tracking token"
    assert copied and "si=" not in copied
    assert copied == shown.split("?")[0], "only the tracking token is removed"


def test_spike_control_toggle_off_keeps_si(yt):
    """Control run: the same clicks with Clean links off put si= on the clipboard."""
    yt.set_settings(cleanLinks=False)
    open_live(yt, WATCH)
    shown, copied, _ = share_and_copy(yt)
    assert "si=" in shown
    assert copied == shown


def test_spike_copy_survives_a_throwing_cleaner(yt_fault):
    b = yt_fault
    b.reset_settings()
    open_live(b, WATCH)
    b.js("sessionStorage.setItem('rfyFault', 'clean')")
    try:
        shown, copied, spy = share_and_copy(b)
        print(f"\n[cleaner throws] share box: {shown}\nclipboard: {copied}\nYouTube used: {spy}")
        assert copied == shown, "copying still works; the link is just not cleaned"
    finally:
        b.js("sessionStorage.removeItem('rfyFault')")


def test_spike_copy_survives_a_failed_wrapper_install(yt_fault):
    b = yt_fault
    b.reset_settings()
    open_live(b, WATCH)
    b.js("sessionStorage.setItem('rfyFault', 'install')")
    try:
        open_live(b, WATCH)  # reload: the fault must be in place at document_start
        assert b.js("return Object.getOwnPropertyDescriptor(navigator.clipboard, 'writeText') === undefined"), \
            "native writeText in place"
        shown, copied, spy = share_and_copy(b)
        print(f"\n[install fails] share box: {shown}\nclipboard: {copied}\nYouTube used: {spy}")
        assert copied and copied.startswith("https://youtu.be/"), "copying still works"
    finally:
        b.js("sessionStorage.removeItem('rfyFault')")


# ---- Address bar and canary ------------------------------------------------------------------

def test_live_address_bar_cleaned(yt):
    open_live(yt, WATCH + "&pp=ygUFaGVsbG8%3D&si=abcdef&t=5")
    url = yt.driver.current_url
    assert "v=jNQXAC9IVRw" in url and "t=5" in url
    assert "pp=" not in url and "si=" not in url


def test_canary_search_links_still_carry_pp(yt):
    """With the toggle off, search results still link with pp=: the deny-list still matters."""
    yt.set_settings(cleanLinks=False)
    open_live(yt, "/results?search_query=guitar+lesson")
    assert yt.js("return document.querySelectorAll('a[href*=\"pp=\"]').length") > 0

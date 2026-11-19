"""E2E tests for Clean links, against a YouTube-shaped fixture.

Spec: process/ideation/round3-control.md (#10). The clipboard is read from the privileged
browser context (headless Firefox has its own isolated clipboard). WebDriver clicks are trusted,
so they carry the user activation navigator.clipboard.writeText needs.

The wrapper-failure tests run a second Firefox with a test build of the add-on in which the two
"test-fault" comments in cleanlinks.js are replaced by code that throws when the page's
sessionStorage asks for it. The shipped file only has the comments.
"""
from __future__ import annotations

import time

import pytest
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from conftest import ADDON_ID, Browser, build_addon, make_driver

PAGE = "/watch?v=x&fx=cleanlinks_watch"
SENTINEL = "sentinel: nothing copied yet"

# (input, expected). The cleaner itself is tested through the real clipboard path.
CASES = [
    # strips the deny-list
    ("https://youtu.be/abc123XYZ00?si=TRACK", "https://youtu.be/abc123XYZ00"),
    ("https://www.youtube.com/watch?v=abc123XYZ00&pp=ygUDZm9v", "https://www.youtube.com/watch?v=abc123XYZ00"),
    ("https://www.youtube.com/watch?v=abc123XYZ00&feature=shared", "https://www.youtube.com/watch?v=abc123XYZ00"),
    ("https://www.youtube.com/watch?v=abc123XYZ00&utm_source=x&utm_medium=y&utm_campaign=z",
     "https://www.youtube.com/watch?v=abc123XYZ00"),
    ("https://www.youtube.com/watch?v=abc123XYZ00&gclid=1&fbclid=2&source_ve_path=MjM&embeds_referring_euri=a"
     "&embeds_referring_origin=b&embeds_widget_referrer=c", "https://www.youtube.com/watch?v=abc123XYZ00"),
    # keeps everything else, in order, byte for byte
    ("https://youtu.be/abc123XYZ00?si=TRACK&t=42", "https://youtu.be/abc123XYZ00?t=42"),
    ("https://www.youtube.com/watch?v=abc123XYZ00&list=PLabcdef1234&index=3&pp=x",
     "https://www.youtube.com/watch?v=abc123XYZ00&list=PLabcdef1234&index=3"),
    ("https://www.youtube.com/watch?si=X&v=abc123XYZ00&start=10&end=20&lc=UgxAbc",
     "https://www.youtube.com/watch?v=abc123XYZ00&start=10&end=20&lc=UgxAbc"),
    ("https://www.youtube.com/results?search_query=a+b%2Fc&pp=x", "https://www.youtube.com/results?search_query=a+b%2Fc"),
    ("https://m.youtube.com/watch?v=abc123XYZ00&pp=x#t=30", "https://m.youtube.com/watch?v=abc123XYZ00#t=30"),
    # other YouTube URL shapes
    ("https://youtube.com/shorts/abc123XYZ00?si=TRACK", "https://youtube.com/shorts/abc123XYZ00"),
    ("https://www.youtube.com/shorts/abc123XYZ00?si=TRACK&feature=share", "https://www.youtube.com/shorts/abc123XYZ00"),
    ("https://music.youtube.com/watch?v=abc123XYZ00&si=X", "https://music.youtube.com/watch?v=abc123XYZ00"),
    ("https://www.youtube-nocookie.com/embed/abc123XYZ00?si=X", "https://www.youtube-nocookie.com/embed/abc123XYZ00"),
    # the src inside an embed snippet (HTML, so & is written &amp;)
    ('<iframe width="560" height="315" src="https://www.youtube.com/embed/abc123XYZ00?si=TRACK&amp;start=5" '
     'title="YouTube video player" frameborder="0" allowfullscreen></iframe>',
     '<iframe width="560" height="315" src="https://www.youtube.com/embed/abc123XYZ00?start=5" '
     'title="YouTube video player" frameborder="0" allowfullscreen></iframe>'),
    ('<iframe src="https://www.youtube.com/embed/abc123XYZ00?si=TRACK"></iframe>',
     '<iframe src="https://www.youtube.com/embed/abc123XYZ00"></iframe>'),
    # a link inside text
    ("Watch this: https://youtu.be/abc123XYZ00?si=TRACK. And https://youtu.be/def456UVW11?si=X&t=9!",
     "Watch this: https://youtu.be/abc123XYZ00. And https://youtu.be/def456UVW11?t=9!"),
    # never touched
    ("https://example.com/watch?v=abc123XYZ00&si=X&pp=Y", None),
    ("https://youtube.com.evil.example/watch?si=X", None),
    ("https://notyoutube.com/watch?si=X", None),
    ("https://www.youtube.com/watch?v=abc123XYZ00&t=42", None),
    ("not a url ?si=1&pp=2", None),
    ("https://[::1/watch?si=X", None),
    ("http://", None),
]


def t(name: str) -> str:
    return f'[data-test="{name}"]'


# ---- Clipboard plumbing (privileged context) --------------------------------------------------

def read_clipboard(driver) -> str | None:
    with driver.context(driver.CONTEXT_CHROME):
        return driver.execute_script(
            """
            const trans = Components.classes['@mozilla.org/widget/transferable;1']
              .createInstance(Components.interfaces.nsITransferable);
            trans.init(null);
            trans.addDataFlavor('text/plain');
            Services.clipboard.getData(trans, Services.clipboard.kGlobalClipboard);
            const data = {};
            try { trans.getTransferData('text/plain', data); } catch (e) { return null; }
            return data.value.QueryInterface(Components.interfaces.nsISupportsString).data;
            """
        )


def write_clipboard(driver, text: str):
    with driver.context(driver.CONTEXT_CHROME):
        driver.execute_script(
            "Components.classes['@mozilla.org/widget/clipboardhelper;1']"
            ".getService(Components.interfaces.nsIClipboardHelper).copyString(arguments[0]);",
            text,
        )


def results(b) -> list[str]:
    return b.js("return window.__results.slice()")


def click_and_read(b, button: str) -> str:
    """Real-click a fixture copy button; wait for the page's promise; return the clipboard."""
    write_clipboard(b.driver, SENTINEL)
    before = len(results(b))
    b.driver.find_element(By.CSS_SELECTOR, t(button)).click()
    b.wait_for(lambda: len(results(b)) > before, message=f"{button} settled")
    assert results(b)[-1] in ("resolved", "copied"), results(b)[-1]
    return read_clipboard(b.driver)


def copy_via_wrapper(b, text: str) -> str:
    b.js("window.__text = arguments[0]", text)
    return click_and_read(b, "write")


def paste(b) -> str:
    area = b.driver.find_element(By.CSS_SELECTOR, t("paste"))
    b.js("arguments[0].value = ''", area)
    area.click()
    area.send_keys(Keys.CONTROL, "v")
    return b.js("return arguments[0].value", area)


def drag_data(b, prefill: dict[str, str] | None = None) -> dict[str, str]:
    """Dispatch dragstart on the tracked link with a constructed DataTransfer (optionally
    pre-filled the way Firefox fills a link drag) and return what's in it afterwards."""
    return b.js(
        """
        const [selector, prefill] = arguments;
        const dt = new DataTransfer();
        for (const [type, value] of Object.entries(prefill || {})) dt.setData(type, value);
        document.querySelector(selector).dispatchEvent(
          new DragEvent('dragstart', {dataTransfer: dt, bubbles: true, cancelable: true}));
        const out = {};
        for (const type of ['text/uri-list', 'text/plain', 'text/x-moz-url', 'text/html']) out[type] = dt.getData(type);
        return out;
        """,
        t("link"), prefill,
    )


def firefox_link_drag(b) -> dict[str, str]:
    href = b.js("return document.querySelector(arguments[0]).href", t("link"))
    return {
        "text/x-moz-url": f"{href}\nA search result",
        "text/uri-list": href,
        "text/plain": href,
        "text/html": f'<a href="{href}">A search result</a>',
    }


# ---- The cleaner, table-driven ---------------------------------------------------------------

def test_cleaner_table(browser):
    browser.open(PAGE)
    failures = []
    for text, expected in CASES:
        got = copy_via_wrapper(browser, text)
        want = text if expected is None else expected
        if got != want:
            failures.append(f"{text!r}\n   got  {got!r}\n   want {want!r}")
    assert not failures, "\n".join(failures)


# ---- 1. Clipboard (writeText wrapper) --------------------------------------------------------

def test_wrapper_installed_on_the_page_clipboard(browser):
    browser.open(PAGE)
    assert browser.js("return Object.getOwnPropertyDescriptor(navigator.clipboard, 'writeText') !== undefined")


def test_clipboard_write_is_cleaned_and_promise_resolves(browser):
    browser.open(PAGE)
    assert click_and_read(browser, "write") == "https://youtu.be/abc123XYZ00?t=42"
    assert results(browser)[-1] == "resolved"
    assert paste(browser) == "https://youtu.be/abc123XYZ00?t=42"


@pytest.mark.parametrize("button", ["detached", "wrong-this"])
def test_wrong_this_passes_through(browser, button):
    browser.open(PAGE)
    assert click_and_read(browser, button) == "https://youtu.be/abc123XYZ00"
    assert not any(r.startswith(("threw", "rejected")) for r in results(browser)), results(browser)
    assert paste(browser) == "https://youtu.be/abc123XYZ00"


# ---- 2. Copying from the page ---------------------------------------------------------------

def test_ctrl_c_in_the_share_box_is_cleaned(browser):
    browser.open(PAGE)
    write_clipboard(browser.driver, SENTINEL)
    box = browser.driver.find_element(By.CSS_SELECTOR, t("share"))
    box.click()
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(Keys.CONTROL, "c")
    browser.wait_for(lambda: read_clipboard(browser.driver) != SENTINEL, message="copied")
    assert paste(browser) == "https://www.youtube.com/watch?v=abc123XYZ00"


def test_execcommand_copy_is_cleaned(browser):
    """YouTube's Share → Copy (live, 2026-11-19) selects the share box and runs execCommand('copy')."""
    browser.open(PAGE)
    assert click_and_read(browser, "copy-command") == "https://www.youtube.com/watch?v=abc123XYZ00"


def test_copying_a_selected_link_in_the_page_is_cleaned(browser):
    browser.open(PAGE)
    browser.js(
        "const p = document.createElement('p'); p.dataset.test = 'desc';"
        "p.append('See ', Object.assign(document.createElement('span'), {textContent: 'https://youtu.be/abc123XYZ00?si=TRACK'}));"
        "document.querySelector('ytd-watch-flexy').append(p);"
        "getSelection().selectAllChildren(p.querySelector('span'));"
    )
    write_clipboard(browser.driver, SENTINEL)
    ActionChains(browser.driver).key_down(Keys.CONTROL).send_keys("c").key_up(Keys.CONTROL).perform()
    browser.wait_for(lambda: read_clipboard(browser.driver) != SENTINEL, message="copied")
    assert read_clipboard(browser.driver) == "https://youtu.be/abc123XYZ00"


# ---- 3. Address bar ----------------------------------------------------------------------------

def test_address_bar_cleaned_on_navigation_keeping_state(browser):
    browser.open(PAGE)
    browser.js(
        "history.replaceState({n: 1}, '', '/watch?v=abc123XYZ00&pp=ygUDZm9v&t=42');"
        "document.querySelector('ytd-app').dispatchEvent(new CustomEvent('yt-navigate-finish', {bubbles: true}));"
    )
    browser.wait_for(lambda: browser.js("return location.search") == "?v=abc123XYZ00&t=42", message="URL cleaned")
    assert browser.js("return history.state && history.state.n") == 1


def test_address_bar_cleaned_at_load(browser):
    browser.open("/watch?v=abc123XYZ00&pp=ygUDZm9v&si=x&t=42&fx=cleanlinks_watch")
    browser.wait_for(
        lambda: browser.js("return location.search") == "?v=abc123XYZ00&t=42&fx=cleanlinks_watch",
        message="URL cleaned at load",
    )


# ---- 4. Links handed to Firefox ----------------------------------------------------------------

def test_context_menu_cleans_the_link(browser):
    browser.open(PAGE)
    link = browser.driver.find_element(By.CSS_SELECTOR, t("link"))
    ActionChains(browser.driver).context_click(link).perform()
    ActionChains(browser.driver).send_keys(Keys.ESCAPE).perform()
    assert link.get_attribute("href").endswith("/watch?v=x")
    assert browser.js("return document.querySelector(arguments[0]).getAttribute('href')", t("link")) == "/watch?v=x"
    # Someone else's link is never touched.
    external = browser.driver.find_element(By.CSS_SELECTOR, t("external"))
    ActionChains(browser.driver).context_click(external).perform()
    ActionChains(browser.driver).send_keys(Keys.ESCAPE).perform()
    assert external.get_attribute("href") == "https://example.com/page?si=1&pp=2"


def test_drag_data_cleaned(browser):
    browser.open(PAGE)
    clean = browser.base + "/watch?v=x"
    data = drag_data(browser)
    assert data["text/uri-list"] == clean
    assert data["text/plain"] == clean
    assert data["text/x-moz-url"].split("\n")[0] == clean
    # As Firefox fills it for a real link drag: the three link flavours are overwritten.
    data = drag_data(browser, firefox_link_drag(browser))
    assert data["text/uri-list"] == clean
    assert data["text/plain"] == clean
    assert data["text/x-moz-url"] == clean + "\nA search result"


def test_drag_of_selected_text_left_alone(browser):
    browser.open(PAGE)
    data = drag_data(browser, {"text/plain": "A search", "text/html": "A search"})
    assert data["text/plain"] == "A search"
    assert data["text/uri-list"] == ""


# ---- Off, or master switch off ---------------------------------------------------------------

@pytest.mark.parametrize("patch", [{"cleanLinks": False}, {"enabled": False}], ids=["feature-off", "master-off"])
def test_off_everything_keeps_its_parameters(browser, patch):
    browser.set_settings(**patch)
    browser.open("/watch?v=abc123XYZ00&pp=ygUDZm9v&fx=cleanlinks_watch")
    assert click_and_read(browser, "write") == "https://youtu.be/abc123XYZ00?si=TRACK&t=42"
    assert results(browser)[-1] == "resolved"
    assert click_and_read(browser, "copy-command") == "https://www.youtube.com/watch?v=abc123XYZ00&pp=ygUDZm9v"
    time.sleep(0.3)
    assert browser.js("return location.search") == "?v=abc123XYZ00&pp=ygUDZm9v&fx=cleanlinks_watch"
    link = browser.driver.find_element(By.CSS_SELECTOR, t("link"))
    ActionChains(browser.driver).context_click(link).perform()
    ActionChains(browser.driver).send_keys(Keys.ESCAPE).perform()
    assert "pp=y" in link.get_attribute("href")
    prefill = firefox_link_drag(browser)
    assert drag_data(browser, prefill)["text/uri-list"] == prefill["text/uri-list"]


def test_toggle_applies_live(browser):
    browser.open(PAGE)
    assert click_and_read(browser, "write") == "https://youtu.be/abc123XYZ00?t=42"
    browser.set_settings(cleanLinks=False)
    time.sleep(0.3)
    assert click_and_read(browser, "write") == "https://youtu.be/abc123XYZ00?si=TRACK&t=42"
    browser.set_settings(cleanLinks=True)
    time.sleep(0.3)
    assert click_and_read(browser, "write") == "https://youtu.be/abc123XYZ00?t=42"


# ---- Wrapper failure (fault-injected test build) -------------------------------------------

FAULTS = {
    "clean": "if (sessionStorage.getItem('rfyFault') === 'clean') throw new Error('test fault: clean');",
    "install": "if (sessionStorage.getItem('rfyFault') === 'install') throw new Error('test fault: install');",
}


def build_fault_addon(dest, *, allow_localhost: bool):
    addon = build_addon(dest, allow_localhost=allow_localhost)
    script = addon / "src" / "content" / "features" / "cleanlinks.js"
    text = script.read_text(encoding="utf-8")
    for name, code in FAULTS.items():
        marker = f"/* test-fault: {name} */"
        assert text.count(marker) == 1, f"fault marker {marker!r} missing from cleanlinks.js"
        text = text.replace(marker, code)
    script.write_text(text, encoding="utf-8")
    return addon


@pytest.fixture(scope="module")
def fault_browser(tmp_path_factory, fixture_base):
    addon = build_fault_addon(tmp_path_factory.mktemp("addon-fault") / "addon", allow_localhost=True)
    driver = make_driver(addon)
    b = Browser(driver, fixture_base)
    yield b
    driver.quit()


def open_with_fault(b, fault: str):
    b.reset_settings()
    b.open(PAGE)
    b.js("sessionStorage.setItem('rfyFault', arguments[0])", fault)
    b.open(PAGE)  # reload: the install fault must be in place at document_start


def test_fault_cleaner_throws_original_text_goes_through(fault_browser):
    b = fault_browser
    open_with_fault(b, "clean")
    try:
        assert b.js("return Object.getOwnPropertyDescriptor(navigator.clipboard, 'writeText') !== undefined"), \
            "wrapper installed"
        assert click_and_read(b, "write") == "https://youtu.be/abc123XYZ00?si=TRACK&t=42"
        assert results(b)[-1] == "resolved"
        # The copy listener falls back the same way.
        assert click_and_read(b, "copy-command") == "https://www.youtube.com/watch?v=abc123XYZ00&pp=ygUDZm9v"
    finally:
        b.js("sessionStorage.removeItem('rfyFault')")


def test_fault_install_throws_native_writetext_stays(fault_browser):
    b = fault_browser
    open_with_fault(b, "install")
    try:
        assert b.js(
            "return Object.getOwnPropertyDescriptor(navigator.clipboard, 'writeText') === undefined"
            " && navigator.clipboard.writeText === Clipboard.prototype.writeText"
        ), "native writeText untouched"
        assert click_and_read(b, "write") == "https://youtu.be/abc123XYZ00?si=TRACK&t=42"
        assert results(b)[-1] == "resolved"
        # The other paths don't depend on the wrapper.
        assert click_and_read(b, "copy-command") == "https://www.youtube.com/watch?v=abc123XYZ00"
    finally:
        b.js("sessionStorage.removeItem('rfyFault')")


def test_fault_build_without_faults_behaves_normally(fault_browser):
    b = fault_browser
    b.reset_settings()
    b.open(PAGE)
    b.js("sessionStorage.removeItem('rfyFault')")
    b.open(PAGE)
    assert click_and_read(b, "write") == "https://youtu.be/abc123XYZ00?t=42"


# ---- Add-on update / re-enable (security review R-02) -----------------------------------------

@pytest.fixture(scope="module")
def lifecycle_browser(tmp_path_factory, fixture_base):
    """Its own Firefox: these tests disable and re-enable the add-on."""
    addon = build_addon(tmp_path_factory.mktemp("addon-lifecycle") / "addon", allow_localhost=True)
    driver = make_driver(addon)
    yield Browser(driver, fixture_base)
    driver.quit()


def set_addon_enabled(driver, enabled: bool):
    with driver.context(driver.CONTEXT_CHROME):
        result = driver.execute_async_script(
            """
            const [id, enable, done] = arguments;
            const { AddonManager } = ChromeUtils.importESModule('resource://gre/modules/AddonManager.sys.mjs');
            AddonManager.getAddonByID(id)
              .then((addon) => (enable ? addon.enable() : addon.disable()))
              .then(() => done(true), (e) => done(String(e)));
            """,
            ADDON_ID, enabled,
        )
    assert result is True, result


def test_writetext_works_after_addon_update(lifecycle_browser):
    """An update or re-enable (disable + enable here) nukes the old content script and Firefox
    injects the new one into open tabs. The page's writeText must then be the new wrapper around
    the browser's own writeText, not around the old wrapper (a dead object that throws)."""
    b = lifecycle_browser
    b.open(PAGE)
    b.js("document.documentElement.removeAttribute('data-rfy-page')")  # so re-injection is visible
    set_addon_enabled(b.driver, False)
    set_addon_enabled(b.driver, True)
    b.wait_ready()
    time.sleep(0.6)  # settings loaded
    assert click_and_read(b, "write") == "https://youtu.be/abc123XYZ00?t=42"
    assert results(b)[-1] == "resolved"

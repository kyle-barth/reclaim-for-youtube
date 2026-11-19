"""Shared pytest fixtures: build a test copy of the add-on, serve fixtures, drive Firefox.

Fixture tests run the real add-on against local pages that mimic YouTube's markup.
The only difference from the shipped add-on is that the test copy's content script
also matches http://localhost/* (the manifest is patched in a temp directory; the
source tree is never modified).

Live tests (marked `live`) run the shipped add-on against www.youtube.com.

Environment:
  FIREFOX_BIN   path to firefox.exe (default: standard install locations)
  HEADED=1      show the browser window
"""
from __future__ import annotations

import json
import os
import shutil
import time
import warnings
from pathlib import Path

import pytest
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

import server as fixture_server

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
ADDON_ID = MANIFEST["browser_specific_settings"]["gecko"]["id"]
ADDON_UUID = "6f1e2d3c-4b5a-4987-8a6b-5c4d3e2f1a0b"  # fixed so tests can open extension pages
EXT_ORIGIN = f"moz-extension://{ADDON_UUID}"
SHIP_PATHS = ["manifest.json", "src", "icons", "_locales"]


def firefox_binary() -> str | None:
    if os.environ.get("FIREFOX_BIN"):
        return os.environ["FIREFOX_BIN"]
    for candidate in (
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        "/Applications/Firefox.app/Contents/MacOS/firefox",
        "/usr/bin/firefox",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def build_addon(dest: Path, *, allow_localhost: bool) -> Path:
    """Copy the shippable files to dest, optionally letting the content script run on localhost."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in SHIP_PATHS:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, dest / name)
        elif src.exists():
            shutil.copy2(src, dest / name)
    if allow_localhost:
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        for block in manifest["content_scripts"]:
            block["matches"].append("http://localhost/*")
        manifest["host_permissions"].append("http://localhost/*")
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dest


def make_driver(addon_dir: Path, profile: str | None = None) -> webdriver.Firefox:
    opts = Options()
    if profile:
        opts.profile = profile  # Selenium copies it; the original is never modified
    binary = firefox_binary()
    if binary:
        opts.binary_location = binary
    if not os.environ.get("HEADED"):
        opts.add_argument("-headless")
    opts.set_preference("extensions.webextensions.uuids", json.dumps({ADDON_ID: ADDON_UUID}))
    opts.set_preference("intl.accept_languages", "en-US, en")
    # Allow programmatic play() so the hover-preview test isn't vacuous (blocked play never fires).
    opts.set_preference("media.autoplay.default", 0)
    opts.set_preference("media.autoplay.blocking_policy", 0)
    # WebDriver may not navigate a content tab to moz-extension:// pages, so extension pages
    # are opened from the privileged browser context, which geckodriver must allow explicitly.
    service = Service(service_args=["--allow-system-access"])
    driver = webdriver.Firefox(options=opts, service=service)
    try:
        driver.set_window_size(1400, 1000)
        with warnings.catch_warnings():
            # install_addon is the only API that supports temporary (unsigned) installs.
            warnings.simplefilter("ignore", DeprecationWarning)
            driver.install_addon(str(addon_dir), temporary=True)
    except Exception:
        driver.quit()
        raise
    return driver


def open_privileged_tab(driver: webdriver.Firefox, url: str) -> str:
    """Open url (e.g. a moz-extension:// page) in a new tab and return its window handle."""
    before = set(driver.window_handles)
    with driver.context(driver.CONTEXT_CHROME):
        driver.execute_script(
            """
            const win = Services.wm.getMostRecentWindow('navigator:browser');
            const tab = win.gBrowser.addTab(arguments[0], {
              triggeringPrincipal: Services.scriptSecurityManager.getSystemPrincipal(),
            });
            win.gBrowser.selectedTab = tab;
            """,
            url,
        )
    end = time.time() + 5
    while time.time() < end:
        new = [h for h in driver.window_handles if h not in before]
        if new:
            return new[0]
        time.sleep(0.05)
    raise AssertionError(f"could not open {url}")


class Browser:
    """Thin helper around the driver with the operations tests need.

    Keeps two tabs: the content tab (YouTube or a fixture) and an extension tab used to
    read/write settings through the real browser.storage API.
    """

    def __init__(self, driver: webdriver.Firefox, base: str):
        self.driver = driver
        self.base = base
        self.content_handle = driver.current_window_handle
        self.ext_handle = None

    def ext_async(self, script: str, *args):
        """Run an async script (last arg is the callback) in the extension tab."""
        if self.ext_handle not in self.driver.window_handles:
            self.ext_handle = open_privileged_tab(self.driver, f"{EXT_ORIGIN}/src/popup/popup.html")
            self.driver.switch_to.window(self.ext_handle)
            self.wait_for(lambda: self.js("return document.readyState") == "complete", message="ext page")
        self.driver.switch_to.window(self.ext_handle)
        try:
            return self.driver.execute_async_script(script, *args)
        finally:
            self.driver.switch_to.window(self.content_handle)

    # -- navigation -----------------------------------------------------------------
    def open(self, path: str, settle: float = 0.6):
        self.driver.get(self.base + path)
        self.wait_ready()
        time.sleep(settle)

    def wait_ready(self, timeout: float = 5):
        """Wait until the content script has booted (it marks <html data-rfy-page>)."""
        end = time.time() + timeout
        while time.time() < end:
            if self.js("return document.documentElement.hasAttribute('data-rfy-page')"):
                return
            time.sleep(0.05)
        raise AssertionError("content script never booted on " + self.driver.current_url)

    def js(self, script: str, *args):
        return self.driver.execute_script(script, *args)

    # -- settings -------------------------------------------------------------------
    def set_settings(self, **patch):
        """Merge a patch into stored settings via the real storage API (applies live)."""
        result = self.ext_async(
            """
            const [patch, done] = arguments;
            const key = 'settings';
            browser.storage.local.get(key).then(r => {
              const next = Object.assign({}, r[key] || {}, patch);
              return browser.storage.local.set({[key]: next});
            }).then(() => done(true), e => done(String(e)));
            """,
            patch,
        )
        assert result is True, result

    def get_settings(self) -> dict:
        return self.ext_async(
            "const done = arguments[0]; browser.storage.local.get('settings').then(r => done(r.settings || {}));"
        )

    def reset_settings(self):
        self.ext_async("const done = arguments[0]; browser.storage.local.clear().then(() => done(true));")

    # -- assertions -----------------------------------------------------------------
    def visible(self, selector: str) -> list[bool]:
        """checkVisibility() for every match (empty list if none)."""
        return self.js(
            "return [...document.querySelectorAll(arguments[0])].map(e => e.checkVisibility());",
            selector,
        )

    def any_visible(self, selector: str) -> bool:
        return any(self.visible(selector))

    def all_visible(self, selector: str) -> bool:
        v = self.visible(selector)
        return bool(v) and all(v)

    def wait_for(self, predicate, timeout: float = 5, message: str = "condition"):
        end = time.time() + timeout
        last = None
        while time.time() < end:
            last = predicate()
            if last:
                return last
            time.sleep(0.1)
        raise AssertionError(f"timed out waiting for {message} (last={last!r})")


@pytest.fixture(scope="session")
def fixture_base():
    srv, base = fixture_server.start()
    yield base
    srv.shutdown()


@pytest.fixture(scope="session")
def _fixture_browser(tmp_path_factory, fixture_base):
    addon = build_addon(tmp_path_factory.mktemp("addon-test") / "addon", allow_localhost=True)
    driver = make_driver(addon)
    yield Browser(driver, fixture_base)
    driver.quit()


@pytest.fixture()
def browser(_fixture_browser):
    """A Firefox with the add-on, reset to default settings before each test."""
    b = _fixture_browser
    # Close stray tabs a test may have opened; keep the content and extension tabs.
    for handle in b.driver.window_handles:
        if handle not in (b.content_handle, b.ext_handle):
            b.driver.switch_to.window(handle)
            b.driver.close()
    b.driver.switch_to.window(b.content_handle)
    b.driver.get("about:blank")
    b.reset_settings()
    return b


@pytest.fixture(scope="session")
def live_browser(tmp_path_factory):
    """The shipped add-on (no localhost access) against the real www.youtube.com."""
    addon = build_addon(tmp_path_factory.mktemp("addon-live") / "addon", allow_localhost=False)
    driver = make_driver(addon)
    b = Browser(driver, "https://www.youtube.com")
    yield b
    driver.quit()


def pytest_configure(config):
    config.addinivalue_line("markers", "live: runs against the real www.youtube.com (network, may be flaky)")
    config.addinivalue_line("markers", "signedin: needs RFY_FIREFOX_PROFILE pointing at a signed-in Firefox profile")

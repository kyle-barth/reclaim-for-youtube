"""E2E tests for the settings UI (toolbar popup, opened as an extension page)."""
from __future__ import annotations

import time

import pytest
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from conftest import EXT_ORIGIN, MANIFEST, open_privileged_tab


@pytest.fixture()
def popup(browser):
    """The popup page in its own tab; yields (browser, handle)."""
    handle = open_privileged_tab(browser.driver, f"{EXT_ORIGIN}/src/popup/popup.html")
    browser.driver.switch_to.window(handle)
    browser.wait_for(lambda: browser.js("return document.readyState") == "complete", message="popup loaded")
    time.sleep(0.3)
    yield browser, handle
    browser.driver.switch_to.window(handle)
    browser.driver.close()
    browser.driver.switch_to.window(browser.content_handle)


def schema(b) -> dict:
    return b.js("return JSON.parse(JSON.stringify(ReclaimSettings.SCHEMA))")


def stored(b) -> dict:
    return b.driver.execute_async_script(
        "const d = arguments[0]; browser.storage.local.get('settings').then(r => d(r.settings || {}));"
    )


def click(b, selector: str):
    """Click like a user: the control itself, or its label when the label covers it (radio cards)."""
    el = b.driver.find_element(By.CSS_SELECTOR, selector)
    b.js("arguments[0].scrollIntoView({block: 'center'})", el)
    try:
        if not el.is_displayed():
            raise ElementClickInterceptedException("hidden native input")
        el.click()
    except ElementClickInterceptedException:
        b.driver.find_element(By.CSS_SELECTOR, f'label[for="{el.get_attribute("id")}"]').click()


def test_every_setting_has_a_control(popup):
    b, _ = popup
    for key, spec in schema(b).items():
        n = b.js("return document.querySelectorAll(`[data-setting=\"${arguments[0]}\"]`).length", key)
        assert n >= 1, f"no control for {key}"
        if spec["type"] == "enum":
            values = b.js(
                "return [...document.querySelectorAll(`[data-setting=\"${arguments[0]}\"]`)].flatMap(e =>"
                " e.tagName === 'SELECT' ? [...e.options].map(o => o.value) : [e.value])",
                key,
            )
            assert sorted(set(values)) == sorted(spec["values"]), f"{key} options {values}"


def test_controls_reflect_defaults(popup):
    b, _ = popup
    for key, spec in schema(b).items():
        if spec["type"] == "boolean":
            checked = b.js("return document.querySelector(`input[data-setting=\"${arguments[0]}\"]`).checked", key)
            assert checked == spec["default"], key
        else:
            value = b.js(
                "const els = [...document.querySelectorAll(`[data-setting=\"${arguments[0]}\"]`)];"
                "const sel = els.find(e => e.tagName === 'SELECT'); if (sel) return sel.value;"
                "const r = els.find(e => e.checked); return r ? r.value : null;",
                key,
            )
            assert value == spec["default"], key


def test_toggle_saves_immediately(popup):
    b, _ = popup
    click(b, 'input[data-setting="autoplayOff"]')
    b.wait_for(lambda: stored(b).get("autoplayOff") is False, message="saved without a Save button")


def test_enum_saves(popup):
    b, _ = popup
    radio = b.js("return !!document.querySelector('input[type=radio][data-setting=\"shorts\"]')")
    if radio:
        click(b, 'input[data-setting="shorts"][value="remove"]')
    else:
        b.js("const s = document.querySelector('select[data-setting=\"shorts\"]'); s.value = 'remove';"
             "s.dispatchEvent(new Event('change', {bubbles: true}))")
    b.wait_for(lambda: stored(b).get("shorts") == "remove", message="shorts saved")


def test_master_switch_pauses_ui(popup):
    b, _ = popup
    click(b, 'input[data-setting="enabled"]')
    b.wait_for(lambda: stored(b).get("enabled") is False, message="master off saved")
    assert b.js("return document.documentElement.hasAttribute('data-paused')")
    click(b, 'input[data-setting="enabled"]')
    b.wait_for(lambda: stored(b).get("enabled") is True, message="master on saved")
    assert not b.js("return document.documentElement.hasAttribute('data-paused')")


def test_reset_needs_confirmation(popup):
    b, _ = popup
    click(b, 'input[data-setting="autoplayOff"]')
    b.wait_for(lambda: stored(b).get("autoplayOff") is False, message="changed")
    click(b, '#reset-start')
    assert stored(b).get("autoplayOff") is False, "one click must not reset"
    click(b, '#reset-yes')
    b.wait_for(lambda: stored(b).get("autoplayOff") is True, message="reset to defaults")


def test_every_control_has_an_accessible_name(popup):
    b, _ = popup
    unnamed = b.js("""
      return [...document.querySelectorAll('input, select, button, a[href]')].filter(el => {
        if (el.type === 'hidden') return false;
        const labelled = el.labels && [...el.labels].some(l => l.textContent.trim());
        const aria = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby');
        const text = (el.textContent || '').trim();
        return !(labelled || aria || text);
      }).map(el => el.outerHTML.slice(0, 120));
    """)
    assert unnamed == []


def test_keyboard_operable(popup):
    b, _ = popup
    # Tab to the master switch and toggle it with the keyboard.
    body = b.driver.find_element(By.TAG_NAME, "body")
    body.send_keys(Keys.TAB)
    for _ in range(40):
        if b.js("return document.activeElement && document.activeElement.getAttribute('data-setting')") == "enabled":
            break
        b.driver.switch_to.active_element.send_keys(Keys.TAB)
    else:
        pytest.fail("master switch not reachable by keyboard")
    b.driver.switch_to.active_element.send_keys(Keys.SPACE)
    b.wait_for(lambda: stored(b).get("enabled") is False, message="space toggles the focused switch")


def test_no_remote_resources(popup):
    b, _ = popup
    remote = b.js("""
      return [...document.querySelectorAll('[src], link[href]')]
        .map(e => e.getAttribute('src') || e.getAttribute('href'))
        .filter(u => /^(https?:)?\\/\\//i.test(u));
    """)
    assert remote == []


def test_popup_change_applies_to_open_youtube_tab(browser):
    """End to end: flip Shorts to 'show' in the real popup; an open YouTube tab updates live."""
    browser.open("/results?search_query=guitar")
    assert not browser.any_visible('[data-test="search-shorts-shelf"]')
    handle = open_privileged_tab(browser.driver, f"{EXT_ORIGIN}/src/popup/popup.html")
    browser.driver.switch_to.window(handle)
    browser.wait_for(lambda: browser.js("return document.readyState") == "complete", message="popup")
    time.sleep(0.3)
    if browser.js("return !!document.querySelector('input[type=radio][data-setting=\"shorts\"]')"):
        click(browser, 'input[data-setting="shorts"][value="show"]')
    else:
        browser.js("const s = document.querySelector('select[data-setting=\"shorts\"]'); s.value = 'show';"
                   "s.dispatchEvent(new Event('change', {bubbles: true}))")
    time.sleep(0.5)
    browser.driver.close()
    browser.driver.switch_to.window(browser.content_handle)
    browser.wait_for(lambda: browser.all_visible('[data-test="search-shorts-shelf"]'), message="tab updated live")


def test_reset_undo(popup):
    b, _ = popup
    click(b, 'input[data-setting="cleanLinks"]')
    b.wait_for(lambda: stored(b).get("cleanLinks") is False, message="changed")
    click(b, '#reset-start')
    click(b, '#reset-yes')
    b.wait_for(lambda: stored(b).get("cleanLinks") is True, message="reset")
    b.wait_for(lambda: b.js("return document.getElementById('reset-status').textContent") == "Defaults restored.", message='status')
    click(b, '#reset-undo')
    b.wait_for(lambda: stored(b).get("cleanLinks") is False, message="undo restores the user's settings")


def test_reset_leaves_master_switch_alone(popup):
    b, _ = popup
    click(b, 'input[data-setting="enabled"]')
    b.wait_for(lambda: stored(b).get("enabled") is False, message="off")
    click(b, '#reset-start')
    click(b, '#reset-yes')
    time.sleep(0.5)
    assert stored(b).get("enabled") is False


def test_version_shown(popup):
    b, _ = popup
    assert b.js("return document.querySelector('[data-version]').textContent") == MANIFEST["version"]

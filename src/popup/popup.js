/*
 * Toolbar popup. Markup-agnostic binder: every control carries data-setting="<key>".
 *   checkbox             -> boolean setting
 *   radio group / select -> enum setting (value attributes are the enum values)
 * Changes save immediately through ReclaimSettings, which validates every value.
 * <html data-paused> mirrors the master switch; popup.css drives the whole off state from it.
 * Nothing here builds HTML from strings: all text is static markup or textContent.
 */
(function () {
  'use strict';
  const Settings = globalThis.ReclaimSettings;
  const root = document.documentElement;

  // ---- Binder -----------------------------------------------------------------------------

  function render(settings) {
    for (const [key, spec] of Object.entries(Settings.SCHEMA)) {
      for (const el of document.querySelectorAll(`[data-setting="${key}"]`)) {
        if (spec.type === 'boolean' && el.type === 'checkbox') el.checked = settings[key] === true;
        else if (spec.type === 'enum' && el.type === 'radio') el.checked = el.value === settings[key];
        else if (spec.type === 'enum' && el.tagName === 'SELECT') el.value = settings[key];
      }
    }
    root.toggleAttribute('data-paused', !settings.enabled);
    root.setAttribute('data-ready', '');
  }

  function valueFrom(el, spec) {
    return spec.type === 'boolean' ? el.checked : el.value;
  }

  async function onChange(event) {
    const el = event.target;
    const key = el && typeof el.getAttribute === 'function' ? el.getAttribute('data-setting') : null;
    if (!key || !Object.prototype.hasOwnProperty.call(Settings.SCHEMA, key)) return;
    if (el.type === 'radio' && !el.checked) return;
    render(await Settings.save({ [key]: valueFrom(el, Settings.SCHEMA[key]) }));
    if (key !== 'enabled') forgetUndo(); // a new change ends the chance to undo a reset
  }

  // ---- Reset to defaults, with a confirmation step and Undo --------------------------------

  const $ = (id) => document.getElementById(id);
  const resetIdle = $('reset-idle');
  const resetConfirm = $('reset-confirm');
  const resetStart = $('reset-start');
  const resetYes = $('reset-yes');
  const resetNo = $('reset-no');
  const resetUndo = $('reset-undo');
  const resetStatus = $('reset-status');
  const version = $('version');

  let snapshot = null; // settings just before the last reset; lives until the popup closes

  function showStatus(text, withUndo) {
    resetStatus.textContent = text;
    version.hidden = Boolean(text);
    resetUndo.hidden = !withUndo;
  }

  function forgetUndo() {
    if (!resetStatus.textContent) return;
    snapshot = null;
    showStatus('', false);
  }

  function showConfirm(show) {
    resetIdle.hidden = show;
    resetConfirm.hidden = !show;
    (show ? resetYes : resetStart).focus();
  }

  resetStart.addEventListener('click', () => {
    showStatus('', false);
    showConfirm(true);
  });
  resetNo.addEventListener('click', () => showConfirm(false));
  resetConfirm.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      showConfirm(false);
    }
  });

  resetYes.addEventListener('click', async () => {
    const current = await Settings.load();
    snapshot = current;
    // The master switch is left alone.
    const next = Object.assign(Settings.defaults(), { enabled: current.enabled });
    render(await Settings.save(next));
    showConfirm(false);
    // The status row was hidden during the question; filling it on a later task makes the
    // live region announce the change instead of appearing with its text already in place.
    version.hidden = true;
    resetUndo.hidden = false;
    setTimeout(() => showStatus('Defaults restored.', true), 150);
  });

  resetUndo.addEventListener('click', async () => {
    if (!snapshot) return;
    const current = await Settings.load();
    render(await Settings.save(Object.assign({}, snapshot, { enabled: current.enabled })));
    snapshot = null;
    resetStart.focus(); // Undo is about to disappear; keep focus nearby
    showStatus('Your settings are back.', false);
  });

  // ---- Boot ----------------------------------------------------------------------------------

  for (const el of document.querySelectorAll('[data-version]')) {
    el.textContent = browser.runtime.getManifest().version;
  }
  document.addEventListener('change', onChange);
  Settings.load().then(render);
  Settings.onChange(render); // stay in sync with changes made elsewhere
})();

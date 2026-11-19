/*
 * Content-script core: settings, page detection, the <html> attributes the stylesheet keys
 * off, and one shared, throttled DOM scan that every feature hooks into.
 *
 * Design rules:
 *  - CSS does the hiding wherever a selector can express it (no flash, no JS cost).
 *  - JS only marks elements CSS cannot identify, via the data-rfy-hide token list, so a
 *    feature can always undo exactly what it did.
 *  - If anything throws, the feature is skipped and YouTube behaves normally.
 */
(function () {
  'use strict';

  const Settings = globalThis.ReclaimSettings;
  const ROOT = document.documentElement;
  const HIDE_ATTR = 'data-rfy-hide';
  const features = [];

  const state = {
    settings: Settings.defaults(),
    page: 'other',
    href: location.href,
    ready: false,
  };

  const CHANNEL_PREFIX = /^\/(?:@[^/]+|channel\/[^/]+|c\/[^/]+|user\/[^/]+)/;

  function pageTypeFor(pathname) {
    if (pathname === '/' || pathname === '') return 'home';
    if (pathname.startsWith('/feed/subscriptions')) return 'subscriptions';
    if (pathname.startsWith('/results')) return 'search';
    if (pathname.startsWith('/watch')) return 'watch';
    if (pathname === '/shorts' || pathname.startsWith('/shorts/')) return 'shorts';
    if (CHANNEL_PREFIX.test(pathname)) {
      return /^\/(?:@[^/]+|channel\/[^/]+|c\/[^/]+|user\/[^/]+)\/shorts\/?$/.test(pathname)
        ? 'channel-shorts'
        : 'channel';
    }
    if (pathname.startsWith('/feed/history')) return 'history';
    if (pathname.startsWith('/playlist')) return 'playlist';
    if (pathname.startsWith('/feed/')) return 'feed';
    return 'other';
  }

  /** Mark an element hidden on behalf of a feature (token list, so features don't collide). */
  function hide(el, token) {
    const current = (el.getAttribute(HIDE_ATTR) || '').split(' ').filter(Boolean);
    if (!current.includes(token)) {
      current.push(token);
      el.setAttribute(HIDE_ATTR, current.join(' '));
    }
  }

  function unhide(el, token) {
    const rest = (el.getAttribute(HIDE_ATTR) || '').split(' ').filter((t) => t && t !== token);
    if (rest.length) el.setAttribute(HIDE_ATTR, rest.join(' '));
    else el.removeAttribute(HIDE_ATTR);
  }

  function unhideAll(token) {
    for (const el of document.querySelectorAll(`[${HIDE_ATTR}~="${token}"]`)) unhide(el, token);
  }

  function safely(feature, method, ...args) {
    const fn = feature[method];
    if (typeof fn !== 'function') return undefined;
    try {
      return fn.apply(feature, args);
    } catch (err) {
      console.debug(`[Reclaim] ${feature.id}.${method} failed; leaving YouTube as-is.`, err);
      return undefined;
    }
  }

  function kebab(key) {
    return key.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());
  }

  /**
   * Mirror settings onto <html> so the stylesheet can key off them:
   *   boolean true  -> data-rfy-<key>
   *   enum value    -> data-rfy-<key>="<value>"
   * Lists and numbers are JS-only and not mirrored.
   */
  function applyAttributes() {
    const s = state.settings;
    const on = s.enabled;
    if (on) ROOT.setAttribute('data-rfy', '');
    else ROOT.removeAttribute('data-rfy');
    ROOT.setAttribute('data-rfy-page', state.page);
    for (const [key, spec] of Object.entries(Settings.SCHEMA)) {
      if (key === 'enabled') continue;
      const name = 'data-rfy-' + kebab(key);
      const value = s[key];
      if (spec.type === 'boolean') {
        if (on && value) ROOT.setAttribute(name, '');
        else ROOT.removeAttribute(name);
      } else if (spec.type === 'enum') {
        if (on) ROOT.setAttribute(name, value);
        else ROOT.removeAttribute(name);
      }
    }
  }

  // ---- Scan scheduling -------------------------------------------------------------

  let scanTimer = 0;
  let lastScan = 0;
  const SCAN_DELAY = 80; // coalesce bursts of mutations
  const SCAN_MAX_WAIT = 400;

  function scheduleScan() {
    if (scanTimer) return;
    const wait = Math.min(SCAN_DELAY, Math.max(0, SCAN_MAX_WAIT - (Date.now() - lastScan)));
    scanTimer = setTimeout(runScan, wait);
  }

  function runScan() {
    scanTimer = 0;
    lastScan = Date.now();
    // JS marking waits for the real settings; until then only the default CSS applies, so a
    // feature the user switched off can never be acted on by a pre-load scan.
    if (!state.ready) return;
    if (location.href !== state.href) onNavigate();
    if (!state.settings.enabled) return;
    for (const f of features) safely(f, 'scan', state);
  }

  function onNavigate() {
    state.href = location.href;
    state.page = pageTypeFor(location.pathname);
    ROOT.setAttribute('data-rfy-page', state.page);
    if (!state.settings.enabled) return;
    for (const f of features) safely(f, 'navigate', state);
  }

  function applySettings(next) {
    const prev = state.settings;
    state.settings = next;
    applyAttributes();
    for (const f of features) safely(f, 'update', state, prev);
    scheduleScan();
  }

  // ---- Public API for feature modules -------------------------------------------------

  const Reclaim = {
    state,
    hide,
    unhide,
    unhideAll,
    pageTypeFor,
    scheduleScan,
    /** register({ id, init?(state), update?(state, prev), navigate?(state), scan?(state), mutations?(records, state) }) */
    register(feature) {
      features.push(feature);
      if (state.ready) {
        safely(feature, 'init', state);
        if (state.settings.enabled) safely(feature, 'navigate', state);
      }
    },
    /** True when the master switch and the given boolean setting are both on. */
    on(key) {
      return state.settings.enabled && state.settings[key] === true;
    },
  };
  globalThis.Reclaim = Reclaim;

  // ---- Boot --------------------------------------------------------------------------

  state.page = pageTypeFor(location.pathname);
  applyAttributes(); // defaults first, so CSS applies before storage answers

  Settings.load().then((loaded) => {
    state.settings = loaded;
    state.ready = true;
    applyAttributes();
    for (const f of features) safely(f, 'init', state);
    onNavigate();
    scheduleScan();
  });

  Settings.onChange(applySettings);

  // YouTube is an SPA: listen for its navigation events, and also notice URL changes in the
  // mutation-driven scan in case those events are renamed.
  for (const type of ['yt-navigate-finish', 'yt-page-data-updated', 'popstate']) {
    window.addEventListener(type, () => { if (location.href !== state.href) onNavigate(); scheduleScan(); }, true);
  }

  // One observer for the whole add-on. Features that must act before the next paint get the
  // records synchronously (mutations hook); everything else runs in the throttled scan.
  // aria-hidden is watched because YouTube reuses popups and only flips that attribute.
  const observer = new MutationObserver((records) => {
    if (state.ready && state.settings.enabled) {
      for (const f of features) if (typeof f.mutations === 'function') safely(f, 'mutations', records, state);
    }
    if (records.some((r) => r.type === 'childList')) scheduleScan();
  });
  observer.observe(ROOT, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-hidden'] });
})();

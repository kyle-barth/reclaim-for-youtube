/*
 * Clean links: links you copy or share carry only the video, not YouTube's si= / pp= tracking.
 *
 * Removed: si, pp, feature, source_ve_path, embeds_referring_euri, embeds_referring_origin,
 * embeds_widget_referrer, utm_*, gclid, fbclid. Everything else (v, t, list, index, start, end,
 * lc, …) is kept, and non-YouTube URLs are never touched.
 *
 * Everything runs here, in the isolated content script (no page script, no main world):
 *   1. Clipboard: navigator.clipboard.writeText is wrapped at document_start with
 *      exportFunction on the page's own clipboard object (Xray waiving). The original is always
 *      called with the page clipboard as `this`, and the page's own promise is returned.
 *   2. Copying from the page (Ctrl+C, or YouTube's Share → Copy, which uses
 *      execCommand("copy")): a capture-phase `copy` listener.
 *   3. The address bar: history.replaceState through wrappedJSObject, once at load and once per
 *      navigation (core's single yt-navigate-finish listener calls navigate()).
 *   4. Links handed to Firefox: `contextmenu` (Copy Link, Open in New Tab) cleans the link's
 *      href; `dragstart` overwrites the drag data.
 *
 * The gate (master switch && cleanLinks) is read at the moment each path runs. Off, the
 * clipboard wrapper stays installed and passes text through untouched. Every path falls back to
 * "copied as YouTube produced it": cleaning errors pass the original text through.
 * Everything read from the page is untrusted and treated as plain strings: no innerHTML, no eval.
 *
 * The test suite builds a copy of this file with the two "test-fault" comments replaced by code
 * that throws on demand. In the shipped add-on they are only comments.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;

  const TRACKING = new Set([
    'si',
    'pp',
    'feature',
    'source_ve_path',
    'embeds_referring_euri',
    'embeds_referring_origin',
    'embeds_widget_referrer',
    'gclid',
    'fbclid',
  ]);
  const URL_IN_TEXT = /https?:\/\/[^\s"'<>`]+/gi;
  const TRAILING_PUNCTUATION = /[.,;:!?)\]}]+$/;

  function enabled() {
    return R.state.ready && R.on('cleanLinks');
  }

  function isTrackingKey(key) {
    return TRACKING.has(key) || key.startsWith('utm_');
  }

  function isYouTubeHost(host) {
    const h = host.toLowerCase();
    return (
      h === 'youtu.be' ||
      h === 'youtube.com' ||
      h.endsWith('.youtube.com') ||
      h === 'youtube-nocookie.com' ||
      h.endsWith('.youtube-nocookie.com')
    );
  }

  function paramKey(pair) {
    const eq = pair.indexOf('=');
    const raw = eq < 0 ? pair : pair.slice(0, eq);
    try {
      return decodeURIComponent(raw.replace(/\+/g, ' '));
    } catch (_) {
      return raw;
    }
  }

  /** Drops tracking pairs from the query of one URL string; everything else stays byte-for-byte. */
  function stripQuery(raw) {
    const hash = raw.indexOf('#');
    const end = hash < 0 ? raw.length : hash;
    const q = raw.indexOf('?');
    if (q < 0 || q > end) return raw;
    const pairs = raw.slice(q + 1, end).split('&').filter(Boolean);
    const kept = pairs.filter((pair) => !isTrackingKey(paramKey(pair)));
    if (kept.length === pairs.length) return raw;
    return raw.slice(0, q) + (kept.length ? '?' + kept.join('&') : '') + raw.slice(end);
  }

  /**
   * One link (absolute, or relative to this page). It counts as YouTube's if its host is a
   * YouTube host, or it is same-origin with the page this script runs on (only YouTube).
   * Returns the input unchanged if it isn't YouTube's or can't be parsed.
   */
  function cleanLink(raw) {
    if (typeof raw !== 'string' || raw.indexOf('?') < 0) return raw;
    let url;
    try {
      url = new URL(raw, location.href);
    } catch (_) {
      return raw;
    }
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return raw;
    if (!isYouTubeHost(url.hostname) && url.origin !== location.origin) return raw;
    return stripQuery(raw);
  }

  /**
   * Text that is, or contains, YouTube URLs (a share link, an embed snippet, a sentence): each
   * URL in it is cleaned and the rest of the text is left exactly as it was. Pure; returns its
   * input unchanged on any parse error.
   */
  function cleanYouTubeUrl(text) {
    /* test-fault: clean */
    if (typeof text !== 'string' || text.indexOf('://') < 0) return text;
    return text.replace(URL_IN_TEXT, (match) => {
      try {
        const tail = (TRAILING_PUNCTUATION.exec(match) || [''])[0];
        const link = tail ? match.slice(0, -tail.length) : match;
        // Embed snippets are HTML: their query separators are written as &amp;.
        const escaped = link.indexOf('&amp;') >= 0;
        const plain = escaped ? link.replace(/&amp;/g, '&') : link;
        let cleaned = cleanLink(plain);
        if (cleaned === plain) return match;
        if (escaped) cleaned = cleaned.replace(/&/g, '&amp;');
        return cleaned + tail;
      } catch (_) {
        return match;
      }
    });
  }

  // ---- 1. Clipboard: wrap the page's navigator.clipboard.writeText ---------------------------

  function installClipboardWrapper() {
    try {
      /* test-fault: install */
      const page = window.wrappedJSObject;
      const pageClipboard = page.navigator.clipboard;
      // Wrap the browser's writeText from Clipboard.prototype, never whatever is on the instance.
      // On an add-on update or re-enable Firefox nukes the old content script and injects this
      // one into open tabs; the instance property is then the old copy's wrapper, a dead object,
      // and wrapping it broke writeText ("can't access dead object") in every open YouTube tab
      // until a reload. At document_start the two are the same function. (Disabling or removing
      // the add-on still leaves the dead wrapper until the tab reloads: no add-on code runs then.)
      const original = page.Clipboard.prototype.writeText;
      if (typeof original !== 'function') return;
      // The page calls this wrapper, but `original` then runs with the content script's
      // principal. Never add the clipboardWrite permission while this wrapper exists: YouTube
      // could write the clipboard through it without a user gesture. scripts/build.py refuses it.
      exportFunction(
        function (text) {
          let out = text;
          try {
            if (typeof text === 'string' && enabled()) out = cleanYouTubeUrl(text);
          } catch (_) {
            out = text;
          }
          // `this` is ignored on purpose: the original always gets the page clipboard, so a
          // detached call writes instead of throwing "Illegal invocation".
          return arguments.length ? original.call(pageClipboard, out) : original.call(pageClipboard);
        },
        pageClipboard,
        { defineAs: 'writeText' }
      );
    } catch (err) {
      // Install failed: YouTube's own writeText stays in place; links just aren't cleaned.
      console.debug('[Reclaim] cleanLinks: clipboard wrapper not installed.', err);
    }
  }

  // ---- 2. Copying from the page ----------------------------------------------------------------

  function isTextField(el) {
    return !!el && (el.localName === 'textarea' || el.localName === 'input');
  }

  /** The selected part of a text field, or '' if none (some input types have no selection). */
  function fieldSelection(el) {
    try {
      const start = el.selectionStart;
      const end = el.selectionEnd;
      if (typeof start !== 'number' || typeof end !== 'number' || end <= start) return '';
      return String(el.value).slice(start, end);
    } catch (_) {
      return '';
    }
  }

  function selectedText(event) {
    const path = typeof event.composedPath === 'function' ? event.composedPath() : [];
    for (const el of [path[0], event.target, document.activeElement]) {
      if (!isTextField(el)) continue;
      const text = fieldSelection(el);
      if (text) return { text, plain: true };
    }
    const selection = window.getSelection();
    return { text: selection ? selection.toString() : '', plain: false };
  }

  function onCopy(event) {
    if (!enabled()) return;
    try {
      const data = event.clipboardData;
      if (!data) return;
      const { text, plain } = selectedText(event);
      if (!text) return;
      let cleaned;
      if (plain) {
        // A text field only ever copies plain text, so cleaning inside it loses nothing.
        cleaned = cleanYouTubeUrl(text);
      } else {
        // A page selection may carry rich text; only take over when it is just a link.
        const trimmed = text.trim();
        if (!trimmed || /\s/.test(trimmed)) return;
        cleaned = cleanYouTubeUrl(trimmed);
        if (cleaned === trimmed) return;
      }
      if (cleaned === text) return;
      data.setData('text/plain', cleaned);
      event.preventDefault();
    } catch (err) {
      // Leave the copy exactly as the page produced it.
      console.debug('[Reclaim] cleanLinks: copy left as is.', err);
    }
  }

  // ---- 3. The address bar --------------------------------------------------------------------

  function cleanAddressBar() {
    if (!enabled()) return;
    const current = location.href;
    const cleaned = cleanLink(current);
    if (cleaned === current) return;
    const h = window.wrappedJSObject.history;
    // The page's own state object, handed straight back: it never leaves the page world.
    h.replaceState(h.state, '', cleaned);
    // We just changed the URL ourselves; tell core so it doesn't report a second navigation.
    if (R.state.href === current) R.state.href = location.href;
  }

  // ---- 4. Links handed to Firefox ---------------------------------------------------------------

  function linkOf(target) {
    return target && typeof target.closest === 'function' ? target.closest('a[href]') : null;
  }

  function onContextMenu(event) {
    if (!enabled()) return;
    try {
      const link = linkOf(event.target);
      if (!link) return;
      const href = link.getAttribute('href');
      const cleaned = cleanLink(href);
      if (cleaned !== href) link.setAttribute('href', cleaned);
    } catch (_) {
      /* the link stays as YouTube made it */
    }
  }

  function onDragStart(event) {
    if (!enabled()) return;
    try {
      const link = linkOf(event.target);
      const dt = event.dataTransfer;
      if (!link || !dt) return;
      const href = String(link.href);
      const cleaned = cleanLink(href);
      if (cleaned === href) return;
      // A drag of selected text inside a link carries that text, not the link: leave it.
      const types = Array.prototype.slice.call(dt.types || []);
      if (types.length && !types.includes('text/uri-list') && !types.includes('text/x-moz-url')) return;
      const mozUrl = types.includes('text/x-moz-url') ? String(dt.getData('text/x-moz-url')) : '';
      const newline = mozUrl.indexOf('\n');
      const title = newline >= 0 ? mozUrl.slice(newline + 1) : '';
      // Written through the page's own DataTransfer, so the items carry the page's principal,
      // like the ones Firefox filled in (data set through the Xray would be owned by the add-on
      // and hidden from the page's own reads). Only cleaned strings cross over.
      const page = dt.wrappedJSObject;
      page.setData('text/uri-list', cleaned);
      page.setData('text/plain', cleaned);
      page.setData('text/x-moz-url', cleaned + '\n' + (title || cleaned));
    } catch (_) {
      /* the drag carries the link as YouTube made it */
    }
  }

  // ---- Wiring ----------------------------------------------------------------------------------

  installClipboardWrapper(); // now, at document_start, before any page script runs

  R.register({
    id: 'cleanLinks',

    init() {
      window.addEventListener('copy', onCopy, true);
      window.addEventListener('contextmenu', onContextMenu, true);
      window.addEventListener('dragstart', onDragStart, true);
    },

    navigate() {
      cleanAddressBar(); // once at load (core's first navigate), then once per navigation
    },
  });
})();

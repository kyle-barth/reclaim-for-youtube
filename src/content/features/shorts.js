/*
 * Core 2: Shorts containment.
 *
 *   show     – YouTube as normal.
 *   contain  – Shorts appear only in the Shorts tab (/shorts and a channel's own Shorts tab).
 *              Hidden everywhere else (CSS in content.css), plus the search "Shorts" chip.
 *   remove   – Shorts are gone: nav entries and channel tabs hidden, /shorts/<id> opens in
 *              the normal player, /shorts and channel Shorts tabs redirect away.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const TOKEN = 'shorts';
  const SHORT_ID = /^\/shorts\/([A-Za-z0-9_-]{6,20})\/?$/;
  const CHANNEL_SHORTS = /^(\/(?:@[^/]+|channel\/[^/]+|c\/[^/]+|user\/[^/]+))\/shorts\/?$/;

  function mode() {
    return R.state.settings.enabled ? R.state.settings.shorts : 'show';
  }

  /** Where a Shorts URL should go when Shorts are removed, or null to stay. */
  function redirectFor(url) {
    const id = url.pathname.match(SHORT_ID);
    if (id) {
      const target = new URL('/watch', url.origin);
      target.searchParams.set('v', id[1]);
      return target.href;
    }
    if (url.pathname === '/shorts' || url.pathname === '/shorts/') return new URL('/', url.origin).href;
    const channel = url.pathname.match(CHANNEL_SHORTS);
    if (channel) return new URL(channel[1] + '/videos', url.origin).href;
    return null;
  }

  function redirectIfNeeded() {
    if (mode() !== 'remove') return;
    const target = redirectFor(new URL(location.href));
    if (target && target !== location.href) location.replace(target);
  }

  // In "remove" mode, a click on any Shorts link (descriptions, comments, notifications)
  // opens the video in the normal player instead of the Shorts player.
  function onClick(event) {
    if (mode() !== 'remove' || event.button !== 0 || event.defaultPrevented) return;
    const target0 = event.target;
    const link = target0 && typeof target0.closest === 'function' ? target0.closest('a[href]') : null;
    if (!link) return;
    let url;
    try { url = new URL(link.href, location.href); } catch (_) { return; }
    if (url.origin !== location.origin) return;
    const target = redirectFor(url);
    if (!target) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (event.ctrlKey || event.metaKey || event.shiftKey) window.open(target, '_blank', 'noopener');
    else location.assign(target);
  }

  function chipLabel(el) {
    return (el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  R.register({
    id: TOKEN,

    init() {
      window.addEventListener('click', onClick, true);
    },

    update(state, prev) {
      if (mode() === 'show') R.unhideAll(TOKEN);
      if (prev.shorts !== state.settings.shorts || prev.enabled !== state.settings.enabled) redirectIfNeeded();
    },

    navigate() {
      redirectIfNeeded();
    },

    scan(state) {
      if (mode() === 'show') return;
      // The search page's "Shorts" filter chip is a way into Shorts outside the Shorts tab.
      if (state.page === 'search') {
        for (const chip of document.querySelectorAll('yt-chip-cloud-chip-renderer')) {
          if (chipLabel(chip) === 'Shorts') R.hide(chip, TOKEN);
        }
      }
    },
  });

})();

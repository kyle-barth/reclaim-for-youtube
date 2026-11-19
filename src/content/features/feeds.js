/*
 * Home & Up next feeds: recommendations that run out, and a home page you choose.
 *
 *   homePage: default | finite (first batch only) | search (no feed) | subscriptions (redirect)
 *   upNext:   default | finite (first batch only) | hidden
 *
 * "finite", "search" and "hidden" are pure CSS (content.css): a continuation element with
 * display:none never intersects the viewport, so YouTube never asks for more.
 *
 * "subscriptions" also needs JS to redirect "/" to /feed/subscriptions:
 *   1. direct loads (typed URL, bookmark, new tab, middle-click)  -> location.replace
 *   2. in-app clicks on any link to "/" (logo, guide Home)         -> YouTube's own router
 *   3. backstop after an in-app navigation that still lands on "/" -> location.replace
 * Loop guard: only the automatic paths (1 and 3) are guarded, and only against a bounce, i.e.
 * arriving back at "/" within ~2s of our own redirect with no user input in between. User clicks
 * are never throttled. While a redirect is pending the home grid is hidden by CSS, so the feed
 * never flashes.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const TARGET = '/feed/subscriptions';
  const GUARD_KEY = 'reclaim-home-redirect-at';
  const BOUNCE_MS = 2000;

  let lastTrustedInput = 0;
  let navSeq = 0; // bumped on every navigation signal

  for (const type of ['yt-navigate-start', 'yt-navigate-finish', 'popstate']) {
    window.addEventListener(type, () => { navSeq++; }, true);
  }

  function subscriptionsMode() {
    return R.state.settings.enabled && R.state.settings.homePage === 'subscriptions';
  }

  function lastRedirect() {
    try { return Number(sessionStorage.getItem(GUARD_KEY)) || 0; } catch (_) { return 0; }
  }

  function noteRedirect() {
    try { sessionStorage.setItem(GUARD_KEY, String(Date.now())); } catch (_) { /* storage blocked */ }
  }

  /** True if arriving at "/" now looks like YouTube bouncing our redirect back. */
  function isBounce() {
    const at = lastRedirect();
    return at > 0 && Date.now() - at < BOUNCE_MS && lastTrustedInput < at;
  }

  function autoRedirect() {
    if (!subscriptionsMode() || location.pathname !== '/') return;
    if (isBounce()) return; // settle on the quiet (grid-hidden) home instead of looping
    noteRedirect();
    location.replace(TARGET);
  }

  function onTrustedInput(event) {
    if (event.isTrusted) lastTrustedInput = Date.now();
  }

  function onClick(event) {
    if (!subscriptionsMode() || event.defaultPrevented) return;
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const target = event.target;
    const link = target && typeof target.closest === 'function' ? target.closest('a[href]') : null;
    if (!link) return;
    let url;
    try { url = new URL(link.href, location.href); } catch (_) { return; }
    if (url.origin !== location.origin || url.pathname !== '/') return;

    event.preventDefault();
    event.stopImmediatePropagation();
    // Prefer YouTube's own router (no reload) via the guide's Subscriptions link.
    const guideLink = document.querySelector(
      'ytd-guide-entry-renderer a[href="/feed/subscriptions"], ytd-mini-guide-entry-renderer a[href="/feed/subscriptions"]'
    );
    if (guideLink) {
      const before = location.href;
      const seq = navSeq;
      guideLink.click();
      if (location.href !== before) return; // the router navigated synchronously
      // If the router ignored the synthetic click, fall back to a normal navigation. Any
      // navigation in the meantime (including the user pressing Back) cancels the fallback.
      setTimeout(() => {
        if (navSeq === seq && location.href === before) location.assign(TARGET);
      }, 1500);
    } else {
      location.assign(TARGET);
    }
  }

  R.register({
    id: 'feeds',

    init() {
      document.addEventListener('click', onClick, true);
      document.addEventListener('pointerdown', onTrustedInput, true);
      document.addEventListener('keydown', onTrustedInput, true);
    },

    update(state, prev) {
      if (prev.homePage !== state.settings.homePage || prev.enabled !== state.settings.enabled) autoRedirect();
    },

    navigate() {
      autoRedirect(); // paths 1 (first navigate after load) and 3 (SPA backstop)
    },
  });
})();

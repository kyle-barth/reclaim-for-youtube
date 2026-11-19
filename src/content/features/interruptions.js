/*
 * Core 1: hide the "Experiencing interruptions?" popup shown to ad-block users.
 *
 * YouTube has shipped it in two forms:
 *  - a reused tp-yt-paper-toast whose action links to the ad-blocker help article. CSS in
 *    content.css hides it by that link; :has() un-hides it once the toast shows something else.
 *  - (current, seen 2026-11) the reused yt-ephemeral-actions host under ytd-app, holding only
 *    the text "Experiencing interruptions?" and no link. Only the text identifies it, so JS
 *    marks it while that text is showing and unmarks it when the host shows anything else.
 *
 * Reused hosts change their text in place, which the shared observer (childList only) can
 * miss, so each host gets its own tiny observer that re-checks synchronously, before paint.
 * display:none (not visibility) so no invisible box is left swallowing clicks.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const TOKEN = 'interruptions';
  const HOSTS = 'yt-ephemeral-actions, tp-yt-paper-toast, yt-notification-action-renderer, ytd-popup-container tp-yt-paper-dialog';
  const TEXT = /experiencing interruptions/i;
  const watched = new WeakSet();

  function check(el) {
    const matches = R.on('hideInterruptions') && TEXT.test(el.textContent || '');
    const marked = (el.getAttribute('data-rfy-hide') || '').split(' ').includes(TOKEN);
    if (matches && !marked) R.hide(el, TOKEN);
    else if (!matches && marked) R.unhide(el, TOKEN); // the reused host now shows something else
  }

  function watch(el) {
    if (watched.has(el)) return;
    watched.add(el);
    new MutationObserver(() => {
      try { check(el); } catch (_) { /* leave YouTube as-is */ }
    }).observe(el, { childList: true, characterData: true, subtree: true });
  }

  R.register({
    id: TOKEN,

    update(state, prev) {
      if (prev.hideInterruptions && !R.on('hideInterruptions')) R.unhideAll(TOKEN);
    },

    scan() {
      for (const el of document.querySelectorAll(HOSTS)) {
        watch(el);
        check(el);
      }
    },
  });
})();

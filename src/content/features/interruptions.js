/*
 * Core 1: hide the "Experiencing interruptions? Find out why" popup shown to ad-block users.
 *
 * Primary hook (CSS, content.css): a toast whose action link points at YouTube's
 * ad-blocker help article (href contains "blocker"). The toast element is reused for
 * other messages, so CSS :has() un-hides it automatically once its content changes.
 *
 * Fallback (here): if the link hook ever disappears, match the toast by its English text.
 * display:none (not visibility) is used so no invisible box is left swallowing clicks.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const TOKEN = 'interruptions';
  const POPUPS = 'tp-yt-paper-toast, yt-notification-action-renderer, ytd-popup-container tp-yt-paper-dialog';
  const TEXT = /experiencing interruptions/i;

  R.register({
    id: TOKEN,

    update(state, prev) {
      if (prev.hideInterruptions && !R.on('hideInterruptions')) R.unhideAll(TOKEN);
    },

    scan() {
      if (!R.on('hideInterruptions')) return;
      for (const el of document.querySelectorAll(POPUPS)) {
        const matches = TEXT.test(el.textContent || '');
        const marked = (el.getAttribute('data-rfy-hide') || '').includes(TOKEN);
        if (matches && !marked) R.hide(el, TOKEN);
        else if (!matches && marked) R.unhide(el, TOKEN); // reused toast now shows something else
      }
    },
  });
})();

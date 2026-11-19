/*
 * Nag scrubber: no "Try Premium free" pop-ups and no "turn your history back on" nudges.
 *
 * Hiding is CSS (nags.css): a listed promo container that holds a listed promo link, inline or
 * in a mealbar dialog while no overlay backdrop is attached, plus the home-page feed nudge.
 * This script never hides anything. It does two things:
 *
 * 1. Solicited marks. A promo the user asked for stays: if a trusted pointerdown/keydown came
 *    within 1.5 s before a listed container is *shown*, the container gets data-rfy-solicited,
 *    which the CSS rules exclude. A show is an insertion, or the tp-yt-paper-dialog holding it
 *    flipping open (iron-overlay toggles aria-hidden on every open and close). Every show is
 *    judged afresh, because YouTube reuses popup elements; a close clears the mark. Marks are
 *    set in the MutationObserver callback, so they land before the next paint (no flicker).
 *
 * 2. Modal promos (a listed container with a promo link, shown in a ytd-popup-container dialog
 *    while a tp-yt-iron-overlay-backdrop is attached). CSS never hides these. If the promo is
 *    unsolicited and its dialog is the only open dialog, close it once through the dialog's own
 *    cancel()/close() (page world, via wrappedJSObject), so iron-overlay releases the backdrop
 *    and scroll lock itself, exactly as if the user had dismissed it. About 1 s later: if it is
 *    still open, stop (no retry, no CSS, no node removal): it stays visible and closable, as on
 *    normal YouTube. If it closed and the dialog had paused the video, resume the video.
 *
 * Never touched: core 1's toast (tp-yt-paper-toast is not a listed container), the ad-blocker
 * enforcement dialog, any dialog the user opened, consent pages, age gates, tooltips.
 *
 * Everything read from the page is untrusted: only attributes, tag names and typeof checks are
 * used, and every page call is inside try/catch.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;

  // Keep in sync with nags.css.
  const CONTAINERS = [
    'ytd-banner-promo-renderer',
    'ytd-statement-banner-renderer',
    'ytd-mealbar-promo-renderer',
    'yt-mealbar-promo-renderer',
  ].join(', ');
  const PROMO_LINKS = [
    'a[href="/premium"]',
    'a[href^="/premium?"]',
    'a[href^="https://www.youtube.com/premium"]',
    'a[href^="/paid_memberships"]',
    'a[href^="https://music.youtube.com"]',
    'a[href^="/musicpremium"]',
    'a[href^="https://tv.youtube.com"]',
    'a[href^="/account_notifications"]',
    'a[href^="https://apps.apple.com/"]',
    'a[href^="https://play.google.com/store/apps/"]',
  ].join(', ');
  const PROMO = `:is(${CONTAINERS}):has(${PROMO_LINKS})`;

  const DIALOG = 'tp-yt-paper-dialog';
  const POPUP = 'ytd-popup-container';
  const POPUP_DIALOGS = `${POPUP} ${DIALOG}`;
  const BACKDROP = 'body > tp-yt-iron-overlay-backdrop';
  const ENFORCEMENT = 'ytd-enforcement-message-view-model';
  const MAIN_VIDEO = '#movie_player video, video.html5-main-video';
  const MARK = 'data-rfy-solicited';

  const SOLICITED_MS = 1500; // trusted input this recent before a show = the user asked for it
  const BACKDROP_WAIT_MS = 1000; // iron-overlay attaches the backdrop a frame after opening
  const VERIFY_MS = 1000; // check the dismissal once, this long after it
  const PAUSE_SLACK_MS = 1000; // a pause this close before the show counts as the dialog's

  let lastInput = -Infinity;
  let lastPause = -Infinity;
  const marked = new Set(); // containers currently carrying the solicited mark
  const pending = new Map(); // dialog -> when its promo was shown, until we know if it is modal
  const attempted = new WeakSet(); // dialogs we dismissed during their current opening

  const now = () => performance.now();

  function isOpen(dialog) {
    return dialog.isConnected && dialog.getAttribute('aria-hidden') !== 'true';
  }

  function popupDialogOf(el) {
    const dialog = el.closest(DIALOG);
    return dialog && dialog.closest(POPUP) ? dialog : null;
  }

  function mark(container) {
    container.setAttribute(MARK, '');
    marked.add(container);
  }

  function unmark(container) {
    if (container.hasAttribute(MARK)) container.removeAttribute(MARK);
    marked.delete(container);
  }

  function clearMarks() {
    for (const el of document.querySelectorAll(`[${MARK}]`)) el.removeAttribute(MARK);
    marked.clear();
    pending.clear();
  }

  /** A listed container was shown (inserted, or its dialog flipped open). */
  function onShow(container, at) {
    if (at - lastInput <= SOLICITED_MS) mark(container);
    else unmark(container);
    const dialog = popupDialogOf(container);
    if (dialog) pending.set(dialog, at);
  }

  function onDialogClosed(dialog) {
    for (const c of dialog.querySelectorAll(CONTAINERS)) unmark(c);
    pending.delete(dialog);
    attempted.delete(dialog);
  }

  function showsIn(node, at) {
    if (node.matches(CONTAINERS)) onShow(node, at);
    for (const c of node.querySelectorAll(CONTAINERS)) onShow(c, at);
  }

  function onMutations(records) {
    if (!R.on('nagScrubber')) return;
    const at = now();
    const recent = at - lastInput <= SOLICITED_MS;
    let removals = false;
    for (const rec of records) {
      const target = rec.target;
      if (rec.type === 'attributes') {
        if (target.localName !== DIALOG || !target.closest(POPUP)) continue;
        if (isOpen(target)) {
          for (const c of target.querySelectorAll(CONTAINERS)) onShow(c, at);
        } else {
          onDialogClosed(target);
        }
        continue;
      }
      if (rec.removedNodes.length) removals = true;
      if (!rec.addedNodes.length) continue;
      // Every insertion is judged right after trusted input, and always in the popup container
      // (modal path). Otherwise a show can only clear a mark, so only marked containers matter:
      // this keeps the callback cheap on YouTube's busy DOM.
      const judgeAll = recent || (target.nodeType === 1 && target.closest(POPUP));
      if (!judgeAll && !marked.size) continue;
      for (const node of rec.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (judgeAll) showsIn(node, at);
        else for (const c of [...marked]) if (node.contains(c)) unmark(c);
      }
    }
    if (removals && marked.size) {
      for (const c of [...marked]) if (!c.isConnected) unmark(c);
    }
    if (pending.size) checkModals(at);
  }

  /** Runs right after the observer callback: act on promos shown in a modal dialog. */
  function checkModals(at) {
    const backdrop = document.querySelector(BACKDROP);
    for (const [dialog, shownAt] of [...pending]) {
      if (!isOpen(dialog) || at - shownAt > BACKDROP_WAIT_MS) {
        pending.delete(dialog); // closed, or never became modal: CSS (or nothing) handles it
        continue;
      }
      if (!backdrop) continue; // not modal (yet): wait for the backdrop a little
      const promo = dialog.querySelector(PROMO);
      if (!promo) continue; // its promo link may still be rendering
      pending.delete(dialog);
      dismiss(dialog, shownAt);
    }
  }

  function dismiss(dialog, shownAt) {
    if (attempted.has(dialog)) return; // once per opening: never retried
    if (dialog.querySelector(`:is(${CONTAINERS})[${MARK}]`)) return; // the user asked for it
    if (dialog.querySelector(ENFORCEMENT)) return; // never touch the enforcement dialog
    // Only when the promo's dialog is the sole open dialog: never disturb one the user opened.
    const open = [...document.querySelectorAll(POPUP_DIALOGS)].filter(isOpen);
    if (open.length !== 1 || open[0] !== dialog) return;

    attempted.add(dialog);
    const video = document.querySelector(MAIN_VIDEO);
    try {
      const page = dialog.wrappedJSObject;
      // The overlay's own dismissal: cancel() (which the page may veto) or close().
      if (page && typeof page.cancel === 'function') page.cancel();
      else if (page && typeof page.close === 'function') page.close();
    } catch (err) {
      console.debug('[Reclaim] nags: dismissal failed; leaving the dialog to the user.', err);
    }
    setTimeout(() => verify(dialog, video, shownAt), VERIFY_MS);
  }

  function verify(dialog, video, shownAt) {
    if (isOpen(dialog)) return; // dismissal didn't take: visible and closable, as on YouTube
    // Resume the video only if the dialog paused it: it paused around the show, and the user
    // hasn't touched anything since.
    try {
      if (!R.on('nagScrubber') || !video || !video.isConnected) return;
      if (!video.paused || video.ended) return;
      if (lastPause < shownAt - PAUSE_SLACK_MS || lastInput > shownAt) return;
      const played = video.play();
      if (played && typeof played.catch === 'function') played.catch(() => {});
    } catch (_) {
      /* the video stays paused, as YouTube left it */
    }
  }

  function onInput(event) {
    if (event.isTrusted) lastInput = now();
  }

  function onPause(event) {
    const t = event.target;
    if (t && typeof t.matches === 'function' && t.matches(MAIN_VIDEO)) lastPause = now();
  }

  R.register({
    id: 'nags',

    init() {
      window.addEventListener('pointerdown', onInput, true);
      window.addEventListener('keydown', onInput, true);
      document.addEventListener('pause', onPause, true); // media events don't bubble; capture does
    },

    // Called synchronously from core's shared observer (childList + aria-hidden), so solicited
    // marks land before the next paint. Errors are contained by core's safely().
    mutations(records) {
      if (R.on('nagScrubber')) onMutations(records);
    },

    update() {
      if (!R.on('nagScrubber')) clearMarks();
    },
  });
})();

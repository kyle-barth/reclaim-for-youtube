/*
 * Core 1: hide the "Experiencing interruptions?" popup shown to ad-block users.
 *
 * Forms YouTube has shipped (all reused for other messages, so we hide only while this
 * message is showing and un-hide as soon as they show anything else):
 *  - current (captured from an affected account, 2026-11): a snackbar,
 *      ytd-app > snackbar-container > div > snackbar-view-model > … > span "Experiencing interruptions?"
 *    plus a screen-reader copy in ytd-app > yt-ephemeral-actions (aria-live). Text only, no link.
 *  - older: a tp-yt-paper-toast whose action links to the ad-blocker help article (CSS in
 *    content.css hides it by that link).
 *
 * Snackbars are inserted on demand, so new ones are caught synchronously from the shared
 * observer (before paint, no flash), and every host gets a tiny observer of its own for text
 * that changes in place. While a hidden snackbar is present its whole snackbar-container is
 * hidden too (content.css), so no empty box is left over the page swallowing clicks.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const TOKEN = 'interruptions';
  const HOSTS = [
    'snackbar-view-model',
    'yt-ephemeral-actions',
    'tp-yt-paper-toast',
    'yt-notification-action-renderer',
    'ytd-popup-container tp-yt-paper-dialog',
  ].join(', ');
  // Only mutations inside these containers can carry the popup.
  const CONTAINERS = 'snackbar-container, yt-ephemeral-actions, ytd-popup-container';
  const TEXT = /experiencing\s+interruptions/i; // \s also matches the no-break spaces YouTube uses
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

  function handle(el) {
    watch(el);
    check(el);
  }

  /** Hosts at or inside a node (cheap: only called for nodes inside the popup containers). */
  function hostsIn(node) {
    const out = [];
    if (node.nodeType !== 1) return out;
    if (node.matches(HOSTS)) out.push(node);
    for (const el of node.querySelectorAll(HOSTS)) out.push(el);
    return out;
  }

  R.register({
    id: TOKEN,

    update(state, prev) {
      if (prev.hideInterruptions && !R.on('hideInterruptions')) R.unhideAll(TOKEN);
    },

    // Synchronous, from the shared observer: catch a new snackbar before it is painted.
    mutations(records) {
      if (!R.on('hideInterruptions')) return;
      for (const record of records) {
        if (record.type !== 'childList' || !record.addedNodes.length) continue;
        const target = record.target;
        if (!target || target.nodeType !== 1 || !(target.matches(CONTAINERS) || target.closest(CONTAINERS))) continue;
        for (const node of record.addedNodes) for (const el of hostsIn(node)) handle(el);
        // Text added straight into an existing host (e.g. the aria-live copy).
        const host = target.closest(HOSTS);
        if (host) handle(host);
      }
    },

    // Backstop for anything already on the page, and after settings change.
    scan() {
      for (const el of document.querySelectorAll(HOSTS)) handle(el);
    },
  });
})();

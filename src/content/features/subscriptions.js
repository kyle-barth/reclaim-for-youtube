/*
 * Core 3: chronological subscriptions.
 *
 * The subscriptions grid itself is already newest-first; what breaks it is the injected
 * sections (Most relevant, Shorts shelves, Playables, Recommended, Breaking news, posts).
 * Every one of those is a ytd-rich-section-renderer, so CSS removes them all (content.css).
 *
 * JS here only catches stray non-video tiles inside the grid itself (posts, games) whose
 * markup CSS can't pin down reliably: a tile without a /watch link is not a video.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const TOKEN = 'subs';

  R.register({
    id: TOKEN,

    update(state, prev) {
      if (prev.subscriptionsChronological && !R.on('subscriptionsChronological')) R.unhideAll(TOKEN);
    },

    scan(state) {
      if (!R.on('subscriptionsChronological') || state.page !== 'subscriptions') return;
      const grid = document.querySelector('ytd-browse[page-subtype="subscriptions"] ytd-rich-grid-renderer');
      if (!grid) return;
      // Re-judged every scan: Polymer recycles tile elements when the grid re-renders.
      for (const item of grid.querySelectorAll('ytd-rich-item-renderer')) {
        // Tiles render their link lazily; only judge a tile once it has any link at all.
        if (!item.querySelector('a[href]')) continue;
        const isVideo = item.querySelector('a[href^="/watch"], a[href^="/shorts/"], a[href^="/live/"]');
        const marked = (item.getAttribute('data-rfy-hide') || '').includes(TOKEN);
        if (!isVideo && !marked) R.hide(item, TOKEN);
        else if (isVideo && marked) R.unhide(item, TOKEN);
      }
    },
  });
})();

/*
 * Watched videos: show | dim | hide videos you've watched 90%+ on Home, Subscriptions and
 * Up next (never Search, channels, History or playlists).
 *
 * "Watched" is read from the thumbnail's own progress bar (an inline width: N%). The outermost
 * tile container gets data-rfy-watched so a grid cell disappears whole; content.css does the
 * dimming/hiding. Signed out or with history off there are no progress bars, so nothing happens.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const ATTR = 'data-rfy-watched';
  const THRESHOLD = 90;
  const SCOPE = ':is(ytd-browse[page-subtype="home"], ytd-browse[page-subtype="subscriptions"], ytd-watch-next-secondary-results-renderer)';
  const OVERLAYS = `${SCOPE} :is(yt-thumbnail-overlay-progress-bar-view-model, ytd-thumbnail-overlay-resume-playback-renderer)`;
  const TILES = 'ytd-rich-item-renderer, ytd-compact-video-renderer, yt-lockup-view-model';

  function mode() {
    return R.state.settings.enabled ? R.state.settings.watchedVideos : 'show';
  }

  /** Percentage watched from an overlay, or -1 if it can't be read. */
  function percent(overlay) {
    const bar = overlay.querySelector('[style*="width"]');
    if (!bar) return -1;
    const match = /^([\d.]+)%$/.exec(bar.style.width || '');
    return match ? parseFloat(match[1]) : -1;
  }

  function tileOf(overlay) {
    // Outermost recognised tile, so a grid cell goes as a whole.
    let tile = null;
    for (let el = overlay.closest(TILES); el; el = el.parentElement && el.parentElement.closest(TILES)) tile = el;
    return tile;
  }

  function clearAll() {
    for (const el of document.querySelectorAll(`[${ATTR}]`)) el.removeAttribute(ATTR);
  }

  R.register({
    id: 'watched',

    update() {
      if (mode() === 'show') clearAll();
    },

    scan(state) {
      if (mode() === 'show') return;
      if (!['home', 'subscriptions', 'watch'].includes(state.page)) return;
      const stale = new Set(document.querySelectorAll(`[${ATTR}]`));
      for (const overlay of document.querySelectorAll(OVERLAYS)) {
        const tile = tileOf(overlay);
        if (!tile) continue;
        if (percent(overlay) >= THRESHOLD) {
          tile.setAttribute(ATTR, '');
          stale.delete(tile);
        }
      }
      // Tiles that were recycled for another video, or lost their overlay.
      for (const tile of stale) tile.removeAttribute(ATTR);
    },
  });
})();

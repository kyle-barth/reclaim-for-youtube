/*
 * No hover previews: thumbnails stay still until you click.
 *
 * CSS hides YouTube's floating inline-preview player and animated thumbnails. This script
 * makes sure a hidden preview can't keep playing or streaming sound: any <video> that starts
 * inside the preview element is paused and muted. Positively scoped: the watch-page player and
 * the miniplayer are never touched. If YouTube keeps re-starting a preview, stop fighting after
 * a few tries and leave it muted (no play/pause tug-of-war).
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const PREVIEW = 'ytd-video-preview, ytd-moving-thumbnail-renderer';
  const MAX_PAUSES = 3;
  const pauses = new WeakMap();

  function onPlay(event) {
    if (!R.on('noHoverPreviews')) return;
    const video = event.target;
    if (!video || typeof video.closest !== 'function' || video.tagName !== 'VIDEO') return;
    if (!video.closest(PREVIEW) || video.closest('#movie_player, ytd-miniplayer')) return;
    video.muted = true;
    const count = pauses.get(video) || 0;
    if (count >= MAX_PAUSES) return;
    pauses.set(video, count + 1);
    video.pause();
  }

  R.register({
    id: 'hover',
    init() {
      document.addEventListener('play', onPlay, true);
    },
  });
})();

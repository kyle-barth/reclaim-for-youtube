/*
 * Autoplay off, enforced: your video ends when it ends.
 *
 * On each /watch video, if YouTube's own Autoplay switch is on, flip it off. Once per video,
 * never in a loop. If the user turns it back on with a real (trusted) click, leave it alone
 * for the rest of this tab's life. Playlists and Mixes (list=) are the user's choice and are
 * never touched. Fallback: if the "Up next" countdown appears anyway, press its Cancel.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const TOGGLE = '#movie_player .ytp-autonav-toggle-button';
  const CANCEL = '#movie_player .ytp-autonav-endscreen-upnext-cancel-button';

  const GRACE_MS = 6000;
  const COOLDOWN_MS = 1200;

  let userWantsAutoplay = false; // set by a trusted click on the switch
  let handledVideo = null;
  let firstSeen = 0;
  let lastClick = 0;

  function active() {
    if (!R.on('autoplayOff') || userWantsAutoplay || R.state.page !== 'watch') return false;
    return !new URLSearchParams(location.search).has('list');
  }

  function videoId() {
    return new URLSearchParams(location.search).get('v');
  }

  function onClick(event) {
    if (!event.isTrusted) return; // our own programmatic click is untrusted
    const t = event.target;
    if (t && typeof t.closest === 'function' && t.closest('.ytp-autonav-toggle, .ytp-autonav-toggle-button')) {
      userWantsAutoplay = true;
    }
  }

  function onEnded(event) {
    const video = event.target;
    if (!active() || !video || typeof video.closest !== 'function' || !video.closest('#movie_player')) return;
    // Give the countdown up to ~1s to appear, then cancel it.
    let tries = 0;
    const timer = setInterval(() => {
      const cancel = document.querySelector(CANCEL);
      if (cancel && cancel.checkVisibility()) {
        cancel.click();
        clearInterval(timer);
      } else if (++tries >= 10) {
        clearInterval(timer);
      }
    }, 100);
  }

  R.register({
    id: 'autoplay',

    init() {
      document.addEventListener('click', onClick, true);
      document.addEventListener('ended', onEnded, true); // media events don't bubble; capture does
    },

    scan() {
      if (!active()) return;
      const id = videoId();
      if (!id) return;
      if (handledVideo !== id) {
        handledVideo = id;
        firstSeen = 0;
      }
      const toggle = document.querySelector(TOGGLE);
      if (!toggle) return; // player not built yet; try again on the next scan
      const now = Date.now();
      if (!firstSeen) firstSeen = now;
      // Act only in a short window after the switch appears for this video (YouTube may apply
      // its stored preference a moment after rendering), then leave it alone.
      if (now - firstSeen > GRACE_MS) return;
      // Cool down after a click so we never click twice before YouTube updates the switch.
      if (now - lastClick < COOLDOWN_MS) return;
      if (toggle.getAttribute('aria-checked') === 'true') {
        lastClick = now;
        (toggle.closest('button') || toggle).click();
      }
    },
  });
})();

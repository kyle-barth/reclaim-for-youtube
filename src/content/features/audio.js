/*
 * Original audio: hear the creator's own voice instead of YouTube's AI auto-dub.
 *
 * One rule, once per video: if the selected audio track is an AI auto-dub (acont=dubbed-auto)
 * and exactly one original track exists, switch to it. Creator-made dubs (acont=dubbed),
 * descriptive audio and anything ambiguous are left alone. A track the user picks afterwards
 * is never changed back for that video.
 *
 * The player's audio-track methods live in the page; Firefox lets the isolated content script
 * call them through wrappedJSObject (Xray waiving). Everything read back from the page is
 * treated as untrusted: only string ids are read, inside try/catch.
 * Track ids look like "<lang>.<n>;<base64 metadata>"; the metadata carries the acont tag.
 */
(function () {
  'use strict';
  const R = globalThis.Reclaim;
  const KINDS = /acont[^a-z]{0,4}(dubbed-auto|dubbed|original|descriptive|secondary)/;
  const POLL_MS = 250;
  const WINDOW_MS = 3000;

  let handled = null; // video id already decided
  let pollTimer = 0;
  let pollDeadline = 0;
  let deciding = false; // attempt() is running (see the re-entrancy note there)

  function videoId() {
    return R.state.page === 'watch' ? new URLSearchParams(location.search).get('v') : null;
  }

  /** 'original' | 'dubbed-auto' | 'dubbed' | 'descriptive' | 'secondary' | 'unknown' */
  function classify(id) {
    if (typeof id !== 'string') return 'unknown';
    const semi = id.indexOf(';');
    if (semi < 0) return 'unknown';
    let b64 = id.slice(semi + 1).replace(/-/g, '+').replace(/_/g, '/');
    b64 += '='.repeat((4 - (b64.length % 4)) % 4);
    let raw;
    try { raw = atob(b64); } catch (_) { return 'unknown'; }
    const m = KINDS.exec(raw);
    return m ? m[1] : 'unknown';
  }

  function trackId(track) {
    try {
      const id = track && track.id;
      return typeof id === 'string' ? id : null;
    } catch (_) {
      return null;
    }
  }

  /**
   * Returns true when this video is decided (switched, or nothing to do), false to retry.
   *
   * Re-entrancy: every player and track property read below can run page code (a getter or a
   * Proxy), and page code can fire loadedmetadata synchronously, which calls start() and so
   * attempt() again from inside this one. Unguarded, each nesting level switched the track once
   * more and the recursion only stopped at a stack overflow. A nested call now just says "not
   * yet" and the outermost call decides, once.
   */
  function attempt(id) {
    if (deciding) return false;
    deciding = true;
    try {
      return decide(id);
    } finally {
      deciding = false;
    }
  }

  function decide(id) {
    const host = document.querySelector('ytd-watch-flexy #movie_player');
    const player = host && host.wrappedJSObject;
    if (!player) return false;
    let getTracks, getTrack, setTrack;
    try {
      getTracks = player.getAvailableAudioTracks;
      getTrack = player.getAudioTrack;
      setTrack = player.setAudioTrack;
    } catch (_) {
      return true;
    }
    if (typeof getTracks !== 'function' || typeof getTrack !== 'function' || typeof setTrack !== 'function') {
      return false; // not attached yet; after the retry window we give up (YouTube as normal)
    }

    let tracks = [];
    let current;
    try {
      // Make sure the player is showing this video, not the previous one.
      const response = typeof player.getPlayerResponse === 'function' ? player.getPlayerResponse() : null;
      const playing = response && response.videoDetails && response.videoDetails.videoId;
      if (typeof playing === 'string' && playing !== id) return false;
      const list = player.getAvailableAudioTracks();
      const n = list && typeof list.length === 'number' ? Math.min(list.length, 200) : 0;
      for (let i = 0; i < n; i++) tracks.push(list[i]);
      current = player.getAudioTrack();
    } catch (_) {
      return true;
    }
    if (!tracks.length) return false; // not populated yet

    if (classify(trackId(current)) !== 'dubbed-auto') return true;
    const originals = tracks.filter((t) => classify(trackId(t)) === 'original');
    if (originals.length !== 1) return true;
    try {
      player.setAudioTrack(originals[0]);
    } catch (_) {
      /* never retried */
    }
    return true;
  }

  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = 0;
  }

  function start() {
    if (!R.on('originalAudio')) return;
    const id = videoId();
    if (!id || handled === id) return;
    if (attempt(id)) {
      handled = id;
      stopPolling();
      return;
    }
    if (pollTimer) return;
    pollDeadline = Date.now() + WINDOW_MS;
    pollTimer = setInterval(() => {
      const current = videoId();
      if (!current || current !== id || !R.on('originalAudio')) return stopPolling();
      if (attempt(id) || Date.now() > pollDeadline) {
        handled = id; // decided, or gave up: never act again for this video
        stopPolling();
      }
    }, POLL_MS);
  }

  function onLoadedMetadata(event) {
    const video = event.target;
    if (video && typeof video.closest === 'function' && video.closest('ytd-watch-flexy #movie_player')) start();
  }

  R.register({
    id: 'audio',
    init() {
      document.addEventListener('loadedmetadata', onLoadedMetadata, true);
    },
    navigate() {
      stopPolling();
      if (videoId() !== handled) handled = null; // a video watched again is a new start
      start();
    },
  });

})();

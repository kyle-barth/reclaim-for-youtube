// Page-side helpers for fixtures (runs in the page, not the add-on).
(function () {
  'use strict';

  function html(markup) {
    const t = document.createElement('template');
    t.innerHTML = markup.trim();
    return t.content;
  }

  window.__fx = {
    /** Simulate a YouTube SPA navigation: change the URL, swap page content, fire the event. */
    navigate(path, pageMarkup) {
      history.pushState({}, '', path);
      if (pageMarkup !== undefined) {
        const pm = document.querySelector('ytd-page-manager');
        pm.replaceChildren(html(pageMarkup));
      }
      document.querySelector('ytd-app').dispatchEvent(new CustomEvent('yt-navigate-finish', { bubbles: true }));
    },

    /** Append markup to a container after a delay (lazy-loaded continuation). */
    append(selector, markup, delay) {
      setTimeout(() => document.querySelector(selector).append(html(markup)), delay || 0);
    },

    /** Put a message into the (reused) toast, like YouTube does. */
    toast(markup) {
      const toast = document.querySelector('tp-yt-paper-toast#toast');
      toast.replaceChildren(html(markup));
      toast.setAttribute('opened', '');
      toast.style.display = 'block';
    },
  };
})();

# Changelog

## 1.0.2 (2026-11-19)

- **Fixed: the "Experiencing interruptions?" popup is hidden again.** YouTube now shows it as a
  snackbar (`snackbar-container > snackbar-view-model`), with only the text and no help link, so the
  previous hooks never matched. The snackbar is hidden while it shows this message, along with its
  container so nothing invisible is left blocking clicks. New snackbars are caught before they are
  painted, so the popup never flashes. Other snackbars, such as "Saved to Watch later", still appear.
  Confirmed on a real affected account.
- The text match now accepts any whitespace between the words, including the no-break spaces YouTube
  sometimes uses.
- New fixture tests reproduce the captured markup, and a live canary checks that the snackbar host
  still exists.

## 1.0.1 (2026-11-19)

- Hide the screen-reader copy of the "Experiencing interruptions?" message (`yt-ephemeral-actions`).
  This turned out not to be the visible popup; 1.0.2 has the real fix.

## 1.0.0 (2026-11-19)

First release:
- Hide the "Experiencing interruptions?" popup.
- Shorts only in the Shorts tab, or removed entirely.
- Chronological Subscriptions.
- Plus ten further features: home and Up next feeds that end after the first page, dimmed watched
  videos, search results only, a quiet left menu, a nag scrubber, autoplay off, a clear player, no
  hover previews, original audio, and clean links.

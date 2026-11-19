# Live YouTube DOM notes (probed 2026-11-19, signed out, Firefox 160 headless)

## Search (/results)
- Videos are `yt-lockup-view-model` (new lockup) inside `ytd-item-section-renderer > #contents`. `ytd-video-renderer` no longer seen.
- Shorts shelf: `grid-shelf-view-model` (child `yt-section-header-view-model`, title "Shorts") containing
  `ytm-shorts-lockup-view-model-v2 > ytm-shorts-lockup-view-model > a[href^="/shorts/"]`.
- Ads: `ytd-ad-slot-renderer` (leave alone; uBO's job).
- Filter chips: `yt-chip-cloud-chip-renderer` > `chip-shape`.

## Watch (/watch)
- Sidebar: `ytd-watch-next-secondary-results-renderer` > `ytd-item-section-renderer` > `yt-lockup-view-model` (x20) + `ytd-continuation-item-renderer`.
- Autoplay toggle: `button.ytp-autonav-toggle[data-tooltip-target-id="ytp-autonav-toggle-button"]` with `aria-label="Autoplay is on"`, inner `.ytp-autonav-toggle-button[aria-checked="true|false"]`.
- Player overlays present: `.ytp-endscreen-content`, `.ytp-cards-teaser`, `.ytp-autonav-endscreen-countdown-overlay`, `.ytp-fullscreen-grid`, `.iv-branding`.
- Engagement panels: `ytd-engagement-panel-section-list-renderer[target-id]` e.g. `engagement-panel-comments-section`, `engagement-panel-structured-description`, `engagement-panel-searchable-transcript`, `PAmodern_transcript_view`, `PAsearch_preview`, `engagement-panel-macro-markers-description-chapters`.

## Channel (/@handle)
- Tabs: `yt-tab-shape[tab-title="Home|Videos|Shorts|Playables|Playlists|Posts|Store"]` (no href on the tab).

## Guide (left nav)
- `ytd-guide-section-renderer` with `#guide-section-title` ("" / "Explore" / "More from YouTube").
- `ytd-guide-entry-renderer > a#endpoint[title]`; Shorts entry has `title="Shorts"` and **no href**; others have hrefs
  (`/`, `/feed/subscriptions`, `/feed/you`, `/feed/history`, `/premium`, `https://music.youtube.com/`, `/labs`, `/reporthistory`).
- Mini guide: `ytd-mini-guide-entry-renderer`.

## Home (/)
- Signed-out with history off: `ytd-rich-grid-renderer #contents > ytd-rich-section-renderer > ytd-feed-nudge-renderer` ("Your YouTube history is off").

## "Experiencing interruptions?" popup (from community filter lists)
- Toast: `tp-yt-paper-toast#toast` containing `yt-button-renderer#action-button a[href*="blocker"]`. Bottom-left. Reused toast element.
- `visibility:hidden` leaves an invisible box that still blocks clicks → use `display:none`.
- Related page flag: `yt.config_.EXPERIENCE_INTERRUPTIONS_MODE` (not used; out of scope).

## Update 2026-11-19 (captured from a real affected account)
- The "Experiencing interruptions?" popup now renders in the reused host `ytd-app > yt-ephemeral-actions.ytEphemeralActionsHost`
  (`aria-live="polite" aria-atomic="true"`) containing only the text "Experiencing interruptions?", no link. Hidden by text
  match while that message is showing; the host is reused for other notices, which stay visible.

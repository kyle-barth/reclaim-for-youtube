/*
 * Settings schema, defaults and validation. Shared by the content script and the popup.
 * Every value read from storage goes through sanitize(), so a corrupted or hostile
 * storage entry can never put the content script into an unexpected state.
 */
(function (root) {
  'use strict';

  // type: 'boolean' | 'enum' | 'number' | 'list'
  const SCHEMA = Object.freeze({
    enabled: { type: 'boolean', default: true },

    // Core
    hideInterruptions: { type: 'boolean', default: true },
    shorts: { type: 'enum', values: ['show', 'contain', 'remove'], default: 'contain' },
    subscriptionsChronological: { type: 'boolean', default: true },

    // Feeds & navigation
    homePage: { type: 'enum', values: ['default', 'finite', 'search', 'subscriptions'], default: 'finite' },
    upNext: { type: 'enum', values: ['default', 'finite', 'hidden'], default: 'finite' },
    watchedVideos: { type: 'enum', values: ['show', 'dim', 'hide'], default: 'dim' },
    searchResultsOnly: { type: 'boolean', default: true },
    quietGuide: { type: 'boolean', default: true },
    nagScrubber: { type: 'boolean', default: true },

    // Watching
    autoplayOff: { type: 'boolean', default: true },
    hideSuggestions: { type: 'boolean', default: true },
    hideCreatorOverlays: { type: 'boolean', default: true },
    noHoverPreviews: { type: 'boolean', default: true },
    originalAudio: { type: 'boolean', default: true },

    // Privacy
    cleanLinks: { type: 'boolean', default: true },
  });

  const STORAGE_KEY = 'settings';

  function defaults() {
    const out = {};
    for (const [key, spec] of Object.entries(SCHEMA)) {
      out[key] = Array.isArray(spec.default) ? spec.default.slice() : spec.default;
    }
    return out;
  }

  function sanitizeValue(spec, value) {
    switch (spec.type) {
      case 'boolean':
        return typeof value === 'boolean' ? value : spec.default;
      case 'enum':
        return spec.values.includes(value) ? value : spec.default;
      case 'number':
        return typeof value === 'number' && Number.isFinite(value)
          ? Math.min(spec.max, Math.max(spec.min, value))
          : spec.default;
      case 'list': {
        if (!Array.isArray(value)) return spec.default.slice();
        const seen = new Set();
        const out = [];
        for (const item of value) {
          if (typeof item !== 'string') continue;
          const clean = item.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, spec.maxItemLength);
          const key = clean.toLowerCase();
          if (!clean || seen.has(key)) continue;
          seen.add(key);
          out.push(clean);
          if (out.length >= spec.maxItems) break;
        }
        return out;
      }
      default:
        return spec.default;
    }
  }

  /** Returns a complete, valid settings object; unknown keys are dropped. */
  function sanitize(raw) {
    const input = raw && typeof raw === 'object' ? raw : {};
    const base = defaults();
    const out = {};
    for (const [key, spec] of Object.entries(SCHEMA)) {
      out[key] = Object.prototype.hasOwnProperty.call(input, key) ? sanitizeValue(spec, input[key]) : base[key];
    }
    return out;
  }

  async function load() {
    try {
      const stored = await browser.storage.local.get(STORAGE_KEY);
      return sanitize(stored[STORAGE_KEY]);
    } catch (_) {
      return defaults();
    }
  }

  /** Merge a partial update into stored settings. Returns the saved settings. */
  async function save(patch) {
    const current = await load();
    const next = sanitize(Object.assign({}, current, patch));
    await browser.storage.local.set({ [STORAGE_KEY]: next });
    return next;
  }

  async function reset() {
    const next = defaults();
    await browser.storage.local.set({ [STORAGE_KEY]: next });
    return next;
  }

  /** Calls fn(settings) whenever stored settings change. */
  function onChange(fn) {
    browser.storage.onChanged.addListener((changes, area) => {
      if (area === 'local' && changes[STORAGE_KEY]) fn(sanitize(changes[STORAGE_KEY].newValue));
    });
  }

  root.ReclaimSettings = Object.freeze({ SCHEMA, STORAGE_KEY, defaults, sanitize, load, save, reset, onChange });
})(globalThis);

/*
 * Background (event page). Its only job: show at a glance in the toolbar whether Reclaim is on.
 * Grey icon and an "(off)" title while the master switch is off.
 */
(function () {
  'use strict';
  const Settings = globalThis.ReclaimSettings;

  function show(settings) {
    const on = settings.enabled;
    browser.action.setIcon({ path: on ? '/icons/icon.svg' : '/icons/icon-off.svg' });
    browser.action.setTitle({ title: on ? 'Reclaim for YouTube: on' : 'Reclaim for YouTube: off' });
  }

  Settings.load().then(show);
  Settings.onChange(show);
  browser.runtime.onStartup.addListener(() => Settings.load().then(show));
  browser.runtime.onInstalled.addListener(() => Settings.load().then(show));
})();

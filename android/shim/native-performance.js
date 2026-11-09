/* APK only. Frame sampling runs during interaction, never an always-on FPS polling loop. */
(function () {
  'use strict';
  var cap = window.Capacitor;
  if (!cap || !cap.isNativePlatform || !cap.isNativePlatform()) return;
  var root = document.documentElement, policy = window.ItcPerfPolicy;
  var state = { deviceMemory: navigator.deviceMemory, cores: navigator.hardwareConcurrency };
  var reduced = matchMedia('(prefers-reduced-transparency: reduce)');
  var tier, ceiling, frame = 0, until = 0, previous = 0, samples = [], moving = false, motionStart = 0;
  var stats = { probes: 0, samples: 0, slowRatio: 0, refreshRate: 60 };
  root.dataset.nativePerf = 'true';
  function announce() {
    root.dataset.glassTier = tier;
    api.tier = tier; api.powerSave = !!state.powerSave;
    window.dispatchEvent(new CustomEvent('itc:performancechange', { detail: { tier: tier, powerSave: api.powerSave } }));
  }
  function configure(update) {
    Object.assign(state, update || {}, { reducedTransparency: reduced.matches, solidGlass: root.dataset.solidGlass === 'true' });
    var next = policy.select(state);
    // Capability changes can lift the ceiling; noisy runtime probes only lower a session tier.
    if (ceiling !== next) { ceiling = next; tier = next; samples = []; }
    var rate = state.refreshRate || 60;
    if (stats.refreshRate !== rate) samples = [];
    stats.refreshRate = rate;
    announce();
  }
  function tick(now) {
    frame = 0;
    if (document.hidden) { previous = 0; until = 0; }
    // A queued GPU frame can delay the FIRST RAF beyond the whole gesture. Still deliver a no-blur frame.
    if (!previous && moving && now >= until && !document.hidden) until = now + 100;
    var active = now < until && !document.hidden;
    if (moving !== active) { moving = active; root.toggleAttribute('data-perf-motion', moving); }
    if (active) {
      var dt = previous ? now - previous : now - motionStart;
      previous = now;
      if (dt > 0 && dt < 10000) { samples.push(dt); stats.samples++; }
      if (policy.shouldProbe(samples)) {
        var next = policy.degrade(tier, samples, stats.refreshRate);
        stats.slowRatio = samples.filter(function (n) { return n > 1650 / stats.refreshRate; }).length / samples.length;
        stats.probes++; samples = [];
        if (next !== tier) { tier = next; announce(); }
      }
      frame = requestAnimationFrame(tick);
    } else { previous = 0; } // accumulate valid samples across short interactions, never sample the idle gap
  }
  function beginMotion(ms) {
    var now = performance.now();
    until = Math.max(until, now + (typeof ms === 'number' ? ms : 180));
    // One write at the interaction boundary, not per touchmove: do not wait behind the slow blur to pause that blur.
    if (!moving) { motionStart = now; moving = true; root.toggleAttribute('data-perf-motion', true); }
    if (!frame) frame = requestAnimationFrame(tick);
  }
  var api = window.ItcPerformance = { enabled: true, tier: 'light', beginMotion: beginMotion, stats: stats };
  configure();
  ['touchstart', 'touchmove', 'pointerdown', 'scroll', 'wheel'].forEach(function (event) {
    window.addEventListener(event, function () { beginMotion(220); }, { passive: true, capture: true });
  });
  window.addEventListener('itc:performance', function (e) { configure(e.detail); });
  window.addEventListener('clubs:themechange', function () { configure(); });
  reduced.addEventListener('change', function () { configure(); });
  function nativeState() {
    var p = cap.Plugins && cap.Plugins.ItcPerformance;
    if (p && p.getState) p.getState().then(configure).catch(function () {});
  }
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { until = 0; if (frame) cancelAnimationFrame(frame); frame = 0; previous = 0; samples = []; moving = false; root.removeAttribute('data-perf-motion'); }
    else nativeState();
  });
  nativeState();
})();

/* Pure policy, also exercised by Node without a native runtime. */
(function (root) {
  'use strict';
  var tiers = ['none', 'light', 'full'];
  function select(c) {
    if (c.powerSave || c.nativeGpuOverloaded || c.reducedTransparency || c.solidGlass || c.lowRam) return 'none';
    var memory = c.memoryGB || c.deviceMemory || 0, cores = c.cores || 0;
    if ((memory && memory <= 3.25) || (cores && cores <= 2)) return 'none';
    return memory >= 4 && cores >= 6 ? 'full' : 'light';
  }
  function severe(samples) { return samples.length >= 8 && samples.filter(n => n >= 250).length >= 2; }
  function shouldProbe(samples) { return samples.length >= 60 || severe(samples); }
  function degrade(tier, samples, hz) {
    if (samples.length < 45 && !severe(samples)) return tier;
    var budget = 1000 / Math.max(30, Math.min(hz || 60, 240));
    var slow = samples.filter(function (dt) { return dt > budget * 1.65; }).length / samples.length;
    return slow > .22 || severe(samples) ? tiers[Math.max(0, tiers.indexOf(tier) - 1)] : tier;
  }
  root.ItcPerfPolicy = { select: select, degrade: degrade, shouldProbe: shouldProbe, tiers: tiers };
})(globalThis);

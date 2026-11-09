// ../core/src/quality/a11y.ts
function parseColor(color) {
  const value = color.trim();
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(value);
  if (hex && hex[1]) {
    const raw = hex[1];
    const size = raw.length === 3 ? 1 : 2;
    const channel = (index) => {
      const part = raw.slice(index * size, index * size + size);
      return parseInt(size === 1 ? part + part : part, 16);
    };
    return [channel(0), channel(1), channel(2), 1];
  }
  const rgb = /^rgba?\(([^)]+)\)$/i.exec(value);
  if (rgb && rgb[1]) {
    const parts = rgb[1].split(/[\s,/]+/).filter(Boolean).map((part) => parseFloat(part));
    if (parts.length >= 3 && parts.slice(0, 3).every(Number.isFinite)) {
      const alpha = parts.length > 3 && Number.isFinite(parts[3]) ? parts[3] : 1;
      return [parts[0], parts[1], parts[2], alpha];
    }
  }
  return null;
}
var TONE_CROSSOVER = 0.179;
function relativeLuminance(r, g, b) {
  const channel = (v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}
function sampleTone(element, backdrop) {
  const observed = observeTone(element, backdrop);
  return observed === "unpainted" ? "light" : observed;
}
function averageGradient(image) {
  if (!image.includes("-gradient(") || image.includes("url(")) return null;
  const stops = image.match(/#[0-9a-f]{3,6}\b|rgba?\([^)]*\)/gi);
  if (!stops) return null;
  const sum = [0, 0, 0, 0];
  let count = 0;
  for (const stop of stops) {
    const parsed = parseColor(stop);
    if (!parsed) continue;
    sum[0] += parsed[0];
    sum[1] += parsed[1];
    sum[2] += parsed[2];
    sum[3] += parsed[3];
    count++;
  }
  if (count === 0) return null;
  return [sum[0] / count, sum[1] / count, sum[2] / count, sum[3] / count];
}
function observeTone(element, backdrop) {
  if (typeof getComputedStyle !== "function") return null;
  const layers = [];
  let sawImage = false;
  let node = backdrop ?? element.parentElement;
  while (node) {
    const computed = getComputedStyle(node);
    const image = computed.backgroundImage;
    let settled = false;
    if (image && image !== "none") {
      const averaged = averageGradient(image);
      if (averaged) {
        if (averaged[3] > 0.01) {
          layers.push(averaged);
          settled = averaged[3] >= 0.99;
        }
      } else {
        sawImage = true;
      }
    }
    if (!settled) {
      const parsed = parseColor(computed.backgroundColor);
      if (parsed && parsed[3] > 0.01) {
        layers.push(parsed);
        settled = parsed[3] >= 0.99;
      }
    }
    if (settled) break;
    node = node.parentElement;
  }
  if (layers.length === 0) {
    return sawImage ? null : "unpainted";
  }
  const opaque = layers[layers.length - 1];
  if (sawImage && (!opaque || opaque[3] < 0.99)) return null;
  let r = 255;
  let g = 255;
  let b = 255;
  for (let i = layers.length - 1; i >= 0; i--) {
    const layer = layers[i];
    if (!layer) continue;
    const [lr, lg, lb, la] = layer;
    r = lr * la + r * (1 - la);
    g = lg * la + g * (1 - la);
    b = lb * la + b * (1 - la);
  }
  return relativeLuminance(r, g, b) > TONE_CROSSOVER ? "light" : "dark";
}
function readAppearance(element) {
  if (typeof getComputedStyle !== "function") return null;
  const tokens = (getComputedStyle(element).getPropertyValue("color-scheme") || "").split(/\s+/);
  const light = tokens.includes("light");
  const dark = tokens.includes("dark");
  if (light && dark) {
    return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  if (dark) return "dark";
  if (light) return "light";
  return null;
}
var appearanceListeners = /* @__PURE__ */ new Set();
var appearanceObserver = null;
var appearanceMedia = null;
function notifyAppearance() {
  for (const listener of [...appearanceListeners]) listener();
}
function watchAppearance(listener) {
  appearanceListeners.add(listener);
  if (!appearanceObserver && typeof MutationObserver === "function" && typeof document !== "undefined") {
    appearanceObserver = new MutationObserver(notifyAppearance);
    appearanceObserver.observe(document.documentElement, { attributes: true });
    if (document.body) appearanceObserver.observe(document.body, { attributes: true });
    appearanceMedia = watchMedia("(prefers-color-scheme: dark)", notifyAppearance);
  }
  return () => {
    appearanceListeners.delete(listener);
    if (appearanceListeners.size > 0) return;
    appearanceObserver?.disconnect();
    appearanceObserver = null;
    appearanceMedia?.();
    appearanceMedia = null;
  };
}
function readReducedTransparency() {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-transparency: reduce)").matches;
}
function readReducedMotion() {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}
function readForcedColors() {
  return typeof matchMedia === "function" && matchMedia("(forced-colors: active)").matches;
}
function applyReducedTransparency(material) {
  return {
    ...material,
    tintOpacity: Math.max(material.tintOpacity, 0.85),
    blur: Math.min(material.blur, 4),
    refraction: 0,
    dispersion: 0,
    specular: 0
  };
}
function adaptTintToTone(material, tone, defaultTint) {
  if (!tone || material.tint !== defaultTint) return material;
  if (tone === "dark") {
    return {
      ...material,
      tint: "#14171e",
      tintOpacity: Math.max(material.tintOpacity, 0.24)
    };
  }
  return {
    ...material,
    tintOpacity: Math.max(material.tintOpacity, 0.36)
  };
}
function watchMedia(query, onChange) {
  if (typeof matchMedia !== "function") return () => {
  };
  const mql = matchMedia(query);
  if (typeof mql.addEventListener !== "function") return () => {
  };
  const listener = (event) => onChange(event.matches);
  mql.addEventListener("change", listener);
  return () => mql.removeEventListener("change", listener);
}

// ../core/src/quality/adapt.ts
var FROSTED_DARK = {
  tint: "#1e1e1e",
  tintOpacity: 0.6,
  brightness: 0.65,
  saturation: 2.8,
  specular: 0.55
};
var FROST_FLIP_LUMINANCE = 0.1;
var FROST_HYSTERESIS = 0.02;
function frostTone(appearance, luminance, previous) {
  if (appearance === "dark") return "dark";
  if (luminance === null) return previous ?? "light";
  const band = previous === "dark" ? FROST_HYSTERESIS : previous === "light" ? -FROST_HYSTERESIS : 0;
  return luminance < FROST_FLIP_LUMINANCE + band ? "dark" : "light";
}
function adaptMaterial(material, preset, tone, explicit) {
  if (preset !== "frosted" || tone !== "dark") return material;
  const adapted = { ...material };
  for (const key of Object.keys(FROSTED_DARK)) {
    if (explicit[key] === void 0) Object.assign(adapted, { [key]: FROSTED_DARK[key] });
  }
  return adapted;
}

// ../core/src/runtime/scheduler.ts
var frameCbs = /* @__PURE__ */ new Set();
var observerCbs = /* @__PURE__ */ new Set();
var viewportCbs = /* @__PURE__ */ new Set();
var frame = 0;
var last = 0;
var now = 0;
var viewportBound = false;
var viewportDirty = false;
var continuous = false;
var viewportBuffer = [];
var frameBuffer = [];
var observerBuffer = [];
function drain(source, buffer) {
  let count = 0;
  for (const item of source) {
    buffer[count] = item;
    count += 1;
  }
  return count;
}
function tick(time) {
  frame = 0;
  now = time;
  const gap = last && continuous ? (time - last) / 1e3 : 0;
  const dt = last ? Math.min(gap || 1 / 60, 1 / 20) : 1 / 60;
  last = time;
  if (viewportDirty) {
    viewportDirty = false;
    const count2 = drain(viewportCbs, viewportBuffer);
    for (let i = 0; i < count2; i++) viewportBuffer[i]();
    viewportBuffer.length = 0;
  }
  const count = drain(frameCbs, frameBuffer);
  for (let i = 0; i < count; i++) frameBuffer[i](dt);
  frameBuffer.length = 0;
  if (observerCbs.size > 0) {
    const observed = drain(observerCbs, observerBuffer);
    for (let i = 0; i < observed; i++) observerBuffer[i](gap);
    observerBuffer.length = 0;
  }
  continuous = frameCbs.size > 0 || viewportDirty;
  if (continuous) schedule();
}
function schedule() {
  if (frame || typeof requestAnimationFrame !== "function") return;
  frame = requestAnimationFrame(tick);
}
var onViewportEvent = () => {
  viewportDirty = true;
  schedule();
};
function bindViewport() {
  if (viewportBound || typeof window === "undefined") return;
  window.addEventListener("scroll", onViewportEvent, { passive: true, capture: true });
  window.addEventListener("resize", onViewportEvent, { passive: true });
  viewportBound = true;
}
function unbindViewport() {
  if (!viewportBound || viewportCbs.size > 0 || typeof window === "undefined") return;
  window.removeEventListener("scroll", onViewportEvent, true);
  window.removeEventListener("resize", onViewportEvent);
  viewportBound = false;
}
function frameNow() {
  return now;
}
function onFrame(cb) {
  frameCbs.add(cb);
  schedule();
  return () => {
    frameCbs.delete(cb);
  };
}
function observeFrames(cb) {
  observerCbs.add(cb);
  return () => {
    observerCbs.delete(cb);
  };
}
function onViewport(cb) {
  viewportCbs.add(cb);
  bindViewport();
  return () => {
    viewportCbs.delete(cb);
    unbindViewport();
  };
}

// ../core/src/backends/inert.ts
var inertBackend = {
  id: "inert",
  priority: -1,
  autoSelect: false,
  isSupported() {
    return true;
  },
  mount() {
    return {
      update() {
      },
      sync() {
      },
      destroy() {
      }
    };
  }
};

// ../core/src/style-restore.ts
function captureInlineStyles(element, props) {
  if (typeof HTMLElement === "undefined" || !(element instanceof HTMLElement)) return () => {
  };
  const style = element.style;
  const saved = props.map(
    (prop) => [prop, style.getPropertyValue(prop), style.getPropertyPriority(prop)]
  );
  return () => {
    for (const [prop, value, priority] of saved) {
      if (value) style.setProperty(prop, value, priority);
      else style.removeProperty(prop);
    }
  };
}

// ../core/src/fx/bezel.ts
function mountBezel(host, specular) {
  const doc = host.ownerDocument;
  const el2 = doc.createElement("div");
  el2.className = "lg-bezel";
  el2.setAttribute("aria-hidden", "true");
  el2.setAttribute("data-liquid-glass-layer", "bezel");
  const style = el2.style;
  style.position = "absolute";
  style.inset = "0";
  style.borderRadius = "inherit";
  style.pointerEvents = "none";
  style.padding = "1.5px";
  style.setProperty("--lg-bezel-hi", (0.85 * specular).toFixed(3));
  style.setProperty("--lg-bezel-lo", (0.32 * specular).toFixed(3));
  style.setProperty("--lg-bezel-dark", (0.3 * specular).toFixed(3));
  style.setProperty("--lg-bezel-half", (0.15 * specular).toFixed(3));
  style.setProperty(
    "background",
    "conic-gradient(from var(--lg-light-angle, 45deg), rgba(255,255,255,var(--lg-bezel-hi)) 0deg, rgba(255,255,255,var(--lg-bezel-lo)) 70deg, rgba(0,0,0,var(--lg-bezel-half)) 150deg, rgba(0,0,0,var(--lg-bezel-dark)) 180deg, rgba(0,0,0,var(--lg-bezel-half)) 210deg, rgba(255,255,255,var(--lg-bezel-lo)) 290deg, rgba(255,255,255,var(--lg-bezel-hi)) 360deg)"
  );
  style.setProperty("mask", "linear-gradient(#000 0 0) content-box exclude, linear-gradient(#000 0 0)");
  style.setProperty("-webkit-mask", "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)");
  style.setProperty("-webkit-mask-composite", "xor");
  style.setProperty("mask-composite", "exclude");
  style.setProperty("clip-path", "inherit");
  style.setProperty("-webkit-clip-path", "inherit");
  const restore = captureInlineStyles(host, ["position", "--lg-light-angle"]);
  if (typeof getComputedStyle === "function") {
    const position = getComputedStyle(host).position;
    if (position === "static" || position === "") {
      host.style.setProperty("position", "relative");
    }
  }
  host.appendChild(el2);
  let lastAngle = Number.NaN;
  return {
    update(angleDeg) {
      const rounded = Math.round(angleDeg * 2) / 2;
      if (Math.abs(rounded - lastAngle) < 0.5) return;
      lastAngle = rounded;
      host.style.setProperty("--lg-light-angle", `${rounded}deg`);
    },
    destroy() {
      el2.remove();
      host.style.removeProperty("--lg-light-angle");
      restore();
    }
  };
}

// ../core/src/quality/contrast.ts
var grid = null;
var gridListeners = /* @__PURE__ */ new Set();
function setLuminanceGrid(next) {
  grid = next;
  for (const listener of [...gridListeners]) {
    try {
      listener();
    } catch {
      continue;
    }
  }
}
function onLuminanceGrid(cb) {
  gridListeners.add(cb);
  return () => {
    gridListeners.delete(cb);
  };
}
function getLuminanceGrid() {
  return grid;
}
function backdropLuminance(rect) {
  if (!grid || rect.width < 1 || rect.height < 1) return null;
  const { data, cols, rows, docWidth, docHeight } = grid;
  if (docWidth < 1 || docHeight < 1) return null;
  const top = rect.top - (grid.docTop ?? 0);
  if (top + rect.height < 0 || top > docHeight) return null;
  const x0 = Math.max(0, Math.floor(rect.left / docWidth * cols));
  const x1 = Math.min(cols - 1, Math.ceil((rect.left + rect.width) / docWidth * cols) - 1);
  const y0 = Math.max(0, Math.floor(top / docHeight * rows));
  const y1 = Math.min(rows - 1, Math.ceil((top + rect.height) / docHeight * rows) - 1);
  if (x1 < x0 || y1 < y0) return null;
  let sum = 0;
  let count = 0;
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      sum += data[y * cols + x];
      count++;
    }
  }
  return count > 0 ? sum / count : null;
}
function buildLuminanceGrid(source, docWidth, docHeight, cols = 48, docTop = 0) {
  if (typeof document === "undefined" || docWidth < 1 || docHeight < 1) return null;
  const rows = Math.max(1, Math.round(cols * docHeight / docWidth));
  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context || typeof context.drawImage !== "function") return null;
  try {
    context.drawImage(source, 0, 0, cols, rows);
    const image = context.getImageData(0, 0, cols, rows);
    const data = new Float32Array(cols * rows);
    for (let i = 0; i < data.length; i++) {
      const p = i * 4;
      data[i] = relativeLuminance(image.data[p], image.data[p + 1], image.data[p + 2]);
    }
    return { data, cols, rows, docWidth, docHeight, docTop };
  } catch {
    return null;
  }
}

// ../core/src/fx/glow.ts
function mountGlow(host) {
  const el2 = host.ownerDocument.createElement("div");
  el2.className = "lg-glow";
  el2.setAttribute("aria-hidden", "true");
  el2.setAttribute("data-liquid-glass-layer", "glow");
  const style = el2.style;
  style.position = "absolute";
  style.inset = "0";
  style.borderRadius = "inherit";
  style.pointerEvents = "none";
  style.opacity = "0";
  style.transition = "opacity 140ms ease-out";
  style.setProperty("clip-path", "inherit");
  style.setProperty("-webkit-clip-path", "inherit");
  style.setProperty(
    "background",
    "radial-gradient(140px circle at var(--lg-glow-x, 50%) var(--lg-glow-y, 50%), rgba(255, 255, 255, 0.24), rgba(255, 255, 255, 0.05) 55%, transparent 75%)"
  );
  const restore = captureInlineStyles(host, ["position"]);
  if (typeof getComputedStyle === "function") {
    const position = getComputedStyle(host).position;
    if (position === "static" || position === "") {
      host.style.setProperty("position", "relative");
    }
  }
  host.appendChild(el2);
  return {
    press(x, y) {
      el2.style.setProperty("--lg-glow-x", `${Math.round(x)}px`);
      el2.style.setProperty("--lg-glow-y", `${Math.round(y)}px`);
      el2.style.transition = "opacity 140ms ease-out";
      el2.style.opacity = "1";
    },
    release() {
      el2.style.transition = "opacity 460ms ease-out";
      el2.style.opacity = "0";
    },
    destroy() {
      el2.remove();
      restore();
    }
  };
}

// ../core/src/fx/light.ts
function pointerAngle(cx, cy, px, py) {
  return Math.atan2(px - cx, cy - py) * 180 / Math.PI;
}
var clients = /* @__PURE__ */ new Set();
var pointerBound = false;
var motionBound = false;
var flushPending = false;
var lastX = 0;
var lastY = 0;
var onscreen = [];
var angles = [];
function flush() {
  const vh = typeof window === "undefined" ? 0 : window.innerHeight;
  const vw = typeof window === "undefined" ? 0 : window.innerWidth;
  let count = 0;
  for (const client of clients) {
    const rect = client.host.getBoundingClientRect();
    if (rect.bottom < -80 || rect.top > vh + 80 || rect.right < -80 || rect.left > vw + 80) {
      continue;
    }
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    onscreen[count] = client;
    angles[count] = pointerAngle(cx, cy, lastX, lastY);
    count += 1;
  }
  for (let i = 0; i < count; i++) onscreen[i].update(angles[i]);
  onscreen.length = 0;
  angles.length = 0;
}
function onPointerMove(event) {
  lastX = event.clientX;
  lastY = event.clientY;
  if (flushPending) return;
  if (typeof requestAnimationFrame !== "function") {
    flush();
    return;
  }
  flushPending = true;
  const off = onFrame(() => {
    off();
    flushPending = false;
    flush();
  });
}
function onOrientation(event) {
  const gamma = event.gamma ?? 0;
  const beta = event.beta ?? 0;
  const angle = Math.atan2(gamma, Math.max(beta, 1)) * 180 / Math.PI;
  for (const client of clients) {
    if (client.motion) client.update(angle);
  }
}
function ensureListeners() {
  if (typeof window === "undefined") return;
  if (!pointerBound) {
    window.addEventListener("pointermove", onPointerMove, { passive: true });
    pointerBound = true;
  }
  if (!motionBound && [...clients].some((client) => client.motion) && "DeviceOrientationEvent" in window) {
    window.addEventListener("deviceorientation", onOrientation);
    motionBound = true;
  }
}
function releaseListeners() {
  if (typeof window === "undefined" || clients.size > 0) return;
  if (pointerBound) {
    window.removeEventListener("pointermove", onPointerMove);
    pointerBound = false;
  }
  if (motionBound) {
    window.removeEventListener("deviceorientation", onOrientation);
    motionBound = false;
  }
}
function registerLight(client) {
  clients.add(client);
  ensureListeners();
  return () => {
    clients.delete(client);
    releaseListeners();
  };
}
function globalLightDir() {
  if (typeof window === "undefined" || lastX === 0 && lastY === 0) return [-Math.SQRT1_2, -Math.SQRT1_2];
  const cx = window.innerWidth / 2;
  const cy = window.innerHeight / 2;
  const dx = lastX - cx;
  const dy = lastY - cy;
  const len = Math.hypot(dx, dy);
  if (len < 1) return [-Math.SQRT1_2, -Math.SQRT1_2];
  return [dx / len, dy / len];
}

// ../core/src/optics.ts
var DEFAULT_BEVEL_DEPTH = 0.6;
var BAND_LIMIT = 20;
var BAND_RATIO = 0.7;
var EDGE_REACH = 2.39;
var EDGE_DECAY = 0.31;
var REFERENCE_IOR = 1.5;
function domeExponent(bevelDepth) {
  return 2 + 4 * bevelDepth;
}
function appleBand(halfMin) {
  return Math.min(BAND_LIMIT, BAND_RATIO * Math.max(halfMin, 0));
}
function edgeDecay(bevelDepth) {
  return EDGE_DECAY * (1.6 - bevelDepth) / (1.6 - DEFAULT_BEVEL_DEPTH);
}
function lensProfile(depth, { band, ior, bevelDepth }) {
  if (depth < 0 || depth >= band || band <= 0 || ior <= 1) return 0;
  const decay = edgeDecay(bevelDepth ?? DEFAULT_BEVEL_DEPTH);
  const floor = Math.exp(-1 / decay);
  const shape = (Math.exp(-depth / band / decay) - floor) / (1 - floor);
  return EDGE_REACH * band * shape * (ior - 1) / (REFERENCE_IOR - 1);
}
function interiorZoomOffsetX(px, cx, magnify) {
  if (magnify === 0) return 0;
  return (px - cx) * -magnify || 0;
}
function interiorZoomOffsetY(py, cy, magnify) {
  if (magnify === 0) return 0;
  return (py - cy) * -magnify || 0;
}
function interiorZoomOffset(px, py, cx, cy, magnify) {
  return [interiorZoomOffsetX(px, cx, magnify), interiorZoomOffsetY(py, cy, magnify)];
}

// ../core/src/quality/profile.ts
var OVERLAY_Z_INDEX = 2147483e3;
var TIERS = {
  high: { mapSide: 600, caPasses: 3, maxDpr: 2, snapshotThrottleMs: 250, overlayZIndex: OVERLAY_Z_INDEX },
  mid: { mapSide: 480, caPasses: 3, maxDpr: 2, snapshotThrottleMs: 350, overlayZIndex: OVERLAY_Z_INDEX },
  low: { mapSide: 320, caPasses: 1, maxDpr: 1.5, snapshotThrottleMs: 500, overlayZIndex: OVERLAY_Z_INDEX }
};
function deviceTier() {
  if (typeof navigator === "undefined") return "mid";
  const nav = navigator;
  const cores = nav.hardwareConcurrency ?? 0;
  const memory = nav.deviceMemory ?? Infinity;
  const dpr2 = typeof devicePixelRatio === "number" ? devicePixelRatio : 1;
  if (cores > 0 && cores <= 4 || memory <= 4) return "low";
  if (cores >= 8 && dpr2 >= 2) return "high";
  return "mid";
}
var overrides = {};
var tier = null;
var base = null;
var cachedDpr = 0;
function getQuality(local) {
  const dpr2 = typeof devicePixelRatio === "number" ? devicePixelRatio : 1;
  if (!base || dpr2 !== cachedDpr) {
    cachedDpr = dpr2;
    tier = deviceTier();
    base = { ...TIERS[tier], ...overrides };
  }
  return local ? { ...base, ...local } : base;
}
function configure(next) {
  overrides = { ...overrides, ...next };
  base = null;
}
function resetQuality() {
  overrides = {};
  tier = null;
  base = null;
  cachedDpr = 0;
  windowSamples.length = 0;
  windowSeconds = 0;
  slowWindows = 0;
  fired = false;
}
var WINDOW_SIZE = 90;
var WINDOW_SECONDS = 1.5;
var MIN_WINDOW_SAMPLES = 8;
var SLOW_FPS = 45;
var SLOW_WINDOWS_NEEDED = 3;
var windowSamples = [];
var windowSeconds = 0;
var slowWindows = 0;
var fired = false;
var degradeCbs = [];
var offWatch = null;
var ABSURD_GAP_S = 4;
function _pushFrameSample(dt) {
  if (fired || dt <= 0 || dt > ABSURD_GAP_S) return;
  windowSamples.push(1 / dt);
  windowSeconds += dt;
  const full = windowSamples.length >= WINDOW_SIZE;
  const timedOut = windowSeconds >= WINDOW_SECONDS && windowSamples.length >= MIN_WINDOW_SAMPLES;
  if (!full && !timedOut) return;
  const sorted = [...windowSamples].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)] ?? 60;
  windowSamples.length = 0;
  windowSeconds = 0;
  if (median < SLOW_FPS) {
    slowWindows += 1;
    if (slowWindows >= SLOW_WINDOWS_NEEDED) {
      fired = true;
      const cbs = [...degradeCbs];
      degradeCbs = [];
      offWatch?.();
      offWatch = null;
      offBurst?.();
      offBurst = null;
      for (const cb of cbs) cb();
    }
  } else {
    slowWindows = 0;
  }
}
var offBurst = null;
var burstSeconds = 0;
var burstLast = 0;
function stopBurst() {
  offBurst?.();
  offBurst = null;
  burstSeconds = 0;
  burstLast = 0;
  windowSamples.length = 0;
  windowSeconds = 0;
}
function startBurst() {
  if (fired || offBurst || typeof requestAnimationFrame !== "function") return;
  burstSeconds = 0;
  burstLast = 0;
  offBurst = onFrame(() => {
    const time = frameNow();
    const real = burstLast ? (time - burstLast) / 1e3 : 0;
    burstLast = time;
    if (real > 0) {
      burstSeconds += real;
      _pushFrameSample(real);
    }
    if (fired || burstSeconds >= WINDOW_SECONDS * 1.5) stopBurst();
  });
}
function watchFps(onDegrade) {
  if (fired) return () => {
  };
  degradeCbs.push(onDegrade);
  if (!offWatch) {
    offWatch = onViewport(() => startBurst());
  }
  return () => {
    degradeCbs = degradeCbs.filter((cb) => cb !== onDegrade);
    if (degradeCbs.length === 0) {
      stopBurst();
      offWatch?.();
      offWatch = null;
    }
  };
}

// ../core/src/displacement.ts
function sdfRoundedRect(x, y, width, height, radius) {
  const hx = width / 2;
  const hy = height / 2;
  const r = Math.min(radius, hx, hy);
  const px = Math.abs(x - hx) - (hx - r);
  const py = Math.abs(y - hy) - (hy - r);
  const ax = Math.max(px, 0);
  const ay = Math.max(py, 0);
  const outside = Math.hypot(ax, ay);
  const inside = Math.min(Math.max(px, py), 0);
  return outside + inside - r;
}
function sdfSuperellipse(x, y, width, height, exponent = 4) {
  const hx = Math.max(width / 2, 1e-3);
  const hy = Math.max(height / 2, 1e-3);
  const px = Math.abs(x - hx) / hx;
  const py = Math.abs(y - hy) / hy;
  const value = Math.pow(Math.pow(px, exponent) + Math.pow(py, exponent), 1 / exponent);
  return (value - 1) * Math.min(hx, hy);
}
function surfaceSdf(x, y, spec) {
  if (spec.shape === "squircle") {
    return sdfSuperellipse(x, y, spec.width, spec.height);
  }
  return sdfRoundedRect(x, y, spec.width, spec.height, spec.radius);
}
function squircleClipPath(exponent = 4, segments = 64) {
  const points = [];
  const power = 2 / exponent;
  for (let i = 0; i < segments; i++) {
    const angle = i / segments * Math.PI * 2;
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    const x = Math.sign(c) * Math.pow(Math.abs(c), power);
    const y = Math.sign(s) * Math.pow(Math.abs(s), power);
    points.push(`${(50 + x * 50).toFixed(2)}% ${(50 + y * 50).toFixed(2)}%`);
  }
  return `polygon(${points.join(", ")})`;
}
var MAP_PAD = 0.2;
var MIN_BAND_TEXELS = 8;
var MAX_MAP_SIDE = 2048;
var MAX_BUDGET_OVERRUN = 3;
function domeHeight(depth, band, bevelDepth = DEFAULT_BEVEL_DEPTH) {
  if (depth < 0) return 0;
  if (band <= 0 || depth >= band) return 1;
  const n = domeExponent(bevelDepth);
  const u = 1 - depth / band;
  return Math.pow(Math.max(1 - Math.pow(u, n), 0), 1 / n);
}
function computeOffsets(opts) {
  const side = opts.mapSide ?? getQuality().mapSide;
  const budget = side * side;
  let scale = Math.min(1, Math.sqrt(budget / Math.max(opts.width * opts.height, 1)));
  if (opts.band > 0) {
    scale = Math.min(1, Math.max(scale, MIN_BAND_TEXELS / opts.band));
  }
  const longest = Math.max(opts.width, opts.height) * (1 + MAP_PAD * 2);
  scale = Math.min(scale, MAX_MAP_SIDE / Math.max(longest, 1));
  const spread = (1 + MAP_PAD * 2) ** 2;
  const texels = opts.width * opts.height * scale * scale * spread;
  const ceiling = budget * MAX_BUDGET_OVERRUN;
  if (texels > ceiling) scale *= Math.sqrt(ceiling / texels);
  const ew = opts.width * scale;
  const eh = opts.height * scale;
  const padX = Math.round(ew * MAP_PAD);
  const padY = Math.round(eh * MAP_PAD);
  const w = Math.max(2, Math.round(ew) + padX * 2);
  const h = Math.max(2, Math.round(eh) + padY * 2);
  const bevelDepth = opts.bevelDepth ?? DEFAULT_BEVEL_DEPTH;
  const sdfSpec = {
    width: Math.round(ew),
    height: Math.round(eh),
    radius: opts.radius * scale,
    shape: opts.shape
  };
  const band = opts.band * scale;
  const lens = { band, ior: opts.ior, thickness: opts.thickness * scale, bevelDepth };
  const cx = sdfSpec.width / 2;
  const cy = sdfSpec.height / 2;
  const data = new Float32Array(w * h * 2);
  const dome = new Uint8ClampedArray(w * h);
  let maxOffset = 0;
  const halfW = Math.ceil(w / 2);
  const halfH = Math.ceil(h / 2);
  for (let y = 0; y < halfH; y++) {
    for (let x = 0; x < halfW; x++) {
      const sx = x + 0.5 - padX;
      const sy = y + 0.5 - padY;
      const d = surfaceSdf(sx, sy, sdfSpec);
      const depth = -d;
      let dx = 0;
      let dy = 0;
      if (depth >= 0 && depth < band) {
        const mag = lensProfile(depth, lens);
        if (mag > 0) {
          const gx = surfaceSdf(sx + 1, sy, sdfSpec) - surfaceSdf(sx - 1, sy, sdfSpec);
          const gy = surfaceSdf(sx, sy + 1, sdfSpec) - surfaceSdf(sx, sy - 1, sdfSpec);
          const len = Math.hypot(gx, gy);
          if (len > 0) {
            dx = -gx / len * mag;
            dy = -gy / len * mag;
          }
        }
      }
      if (depth >= 0) {
        dx += interiorZoomOffsetX(sx, cx, opts.magnify);
        dy += interiorZoomOffsetY(sy, cy, opts.magnify);
      }
      const m = Math.max(Math.abs(dx), Math.abs(dy));
      if (m > maxOffset) maxOffset = m;
      writeOffset(data, w, x, y, dx, dy);
      writeOffset(data, w, w - 1 - x, y, -dx, dy);
      writeOffset(data, w, x, h - 1 - y, dx, -dy);
      writeOffset(data, w, w - 1 - x, h - 1 - y, -dx, -dy);
      const lit = depth < 0 ? 0 : 1 + Math.round(254 * domeHeight(depth, band, bevelDepth));
      dome[y * w + x] = lit;
      dome[y * w + (w - 1 - x)] = lit;
      dome[(h - 1 - y) * w + x] = lit;
      dome[(h - 1 - y) * w + (w - 1 - x)] = lit;
    }
  }
  return { data, dome, width: w, height: h, padX, padY, scale, maxOffset: maxOffset / (scale || 1) };
}
function writeOffset(data, w, x, y, dx, dy) {
  const i = (y * w + x) * 2;
  data[i] = dx || 0;
  data[i + 1] = dy || 0;
}
function resolveRadiusPx(radius, element, width, height) {
  const half = Math.min(width, height) / 2;
  if (typeof radius === "number") return Math.max(0, Math.min(radius, half));
  if (typeof HTMLElement !== "undefined" && element instanceof HTMLElement && typeof getComputedStyle === "function") {
    const raw = getComputedStyle(element).borderRadius.split(" ")[0] ?? "";
    const parsed = parseFloat(raw);
    if (Number.isFinite(parsed)) {
      const px = raw.endsWith("%") ? parsed / 100 * Math.min(width, height) : parsed;
      return Math.max(0, Math.min(px, half));
    }
  }
  return 0;
}
function resolveThicknessPx(thickness, width, height) {
  if (typeof thickness === "number") return Math.max(0, Math.min(thickness, 100));
  const factor = Math.min(1.6, Math.max(0.85, Math.sqrt(width * height) / 260));
  return 12 * factor;
}
function resolveBandPx(bevelWidth, radiusPx, width, height) {
  if (typeof bevelWidth === "number") return bevelWidth;
  return appleBand(Math.min(width, height) / 2);
}
var lensMapCache = /* @__PURE__ */ new Map();
var LENS_MAP_CACHE_MAX = 32;
var SIZE_BUCKET = 8;
var DETAIL_BUCKET = 0.5;
var DEPTH_BUCKET = 0.05;
function bucket(value, step) {
  return Math.round(value / step) * step;
}
function lensMapKey(opts) {
  const w = bucket(opts.width, SIZE_BUCKET);
  const h = bucket(opts.height, SIZE_BUCKET);
  const radius = bucket(opts.radius, DETAIL_BUCKET);
  const band = bucket(opts.band, DETAIL_BUCKET);
  const thickness = bucket(opts.thickness, DETAIL_BUCKET);
  const bevelDepth = bucket(opts.bevelDepth ?? DEFAULT_BEVEL_DEPTH, DEPTH_BUCKET);
  return `${w}|${h}|${radius}|${opts.shape}|${band}|${opts.ior}|${thickness}|${bevelDepth}|${opts.magnify}`;
}
function renderLensPixels(opts) {
  const { data, dome, width, height, scale, maxOffset } = computeOffsets(opts);
  const pixels = new Uint8ClampedArray(width * height * 4);
  const norm = maxOffset * scale || 1;
  for (let p = 0, i = 0; p < data.length; p += 2, i += 4) {
    pixels[i] = 128 + Math.round(data[p] / norm * 127);
    pixels[i + 1] = 128 + Math.round(data[p + 1] / norm * 127);
    pixels[i + 2] = dome[p >> 1] ?? 128;
    pixels[i + 3] = 255;
  }
  return { pixels, width, height, maxOffset };
}
function encodeLensMap(rendered) {
  const entry = { url: null, maxOffset: rendered.maxOffset };
  if (typeof document !== "undefined") {
    const canvas = document.createElement("canvas");
    canvas.width = rendered.width;
    canvas.height = rendered.height;
    const context = context2d(canvas);
    if (context && typeof context.createImageData === "function") {
      const image = context.createImageData(rendered.width, rendered.height);
      image.data.set(rendered.pixels);
      context.putImageData(image, 0, 0);
      entry.url = canvas.toDataURL("image/png");
    }
  }
  return entry;
}
function cacheLensMap(key, entry) {
  lensMapCache.delete(key);
  if (lensMapCache.size >= LENS_MAP_CACHE_MAX) {
    const oldest = lensMapCache.keys().next().value;
    if (oldest !== void 0) lensMapCache.delete(oldest);
  }
  lensMapCache.set(key, entry);
}
function cachedLensMap(key) {
  const hit = lensMapCache.get(key);
  if (hit === void 0) return void 0;
  lensMapCache.delete(key);
  lensMapCache.set(key, hit);
  return hit;
}
function generateLensMap(opts) {
  if (opts.width < 1 || opts.height < 1) return null;
  const key = lensMapKey(opts);
  const hit = cachedLensMap(key);
  if (hit) return hit;
  const entry = encodeLensMap(renderLensPixels(opts));
  cacheLensMap(key, entry);
  return entry;
}
function context2d(canvas) {
  try {
    return canvas.getContext("2d");
  } catch {
    return null;
  }
}

// ../core/src/color.ts
var HEX_PATTERN = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
function colorWithOpacity(color, opacity) {
  const normalized = color.trim();
  if (HEX_PATTERN.test(normalized)) {
    const hex = normalized.slice(1);
    const size = hex.length === 3 ? 1 : 2;
    const channel = (index) => {
      const part = hex.slice(index * size, index * size + size);
      return parseInt(size === 1 ? part + part : part, 16);
    };
    return `rgba(${channel(0)}, ${channel(1)}, ${channel(2)}, ${opacity})`;
  }
  return `color-mix(in srgb, ${normalized} ${Math.round(opacity * 100)}%, transparent)`;
}

// ../core/src/material.ts
var MATERIAL_DEFAULTS = {
  blur: 8,
  saturation: 1.4,
  brightness: 1,
  tint: "#ffffff",
  tintOpacity: 0.12,
  refraction: 0.5,
  ior: 1.5,
  magnify: 0,
  thickness: "auto",
  bevelWidth: "auto",
  bevelDepth: 0.6,
  dispersion: 0.15,
  specular: 0.6,
  shadow: 0.55,
  lighting: false,
  frost: 0,
  radius: "auto",
  shape: "rounded"
};
var FROST_SPREAD = 45;
function frostSpread(width, height) {
  return Math.min(FROST_SPREAD, Math.min(width, height) / 4);
}
var MATERIAL_PRESETS = {
  clear: {
    blur: 1.2,
    tintOpacity: 0.0765,
    brightness: 1.121,
    saturation: 1,
    frost: 0,
    refraction: 0.5,
    ior: 1.5,
    magnify: 0,
    dispersion: 0,
    specular: 0.8,
    shadow: 0
  },
  frosted: {
    blur: 1.5,
    tintOpacity: 0.86,
    brightness: 0.936,
    saturation: 5.5,
    frost: 0.09,
    refraction: 0.5,
    dispersion: 0,
    specular: 0.8,
    shadow: 0.35
  },
  tinted: {
    blur: 8,
    tint: "#7c5cff",
    tintOpacity: 0.96,
    saturation: 1,
    refraction: 0.5,
    dispersion: 0,
    specular: 0.1,
    shadow: 0.35
  }
};
var MATERIAL_KEYS = Object.keys(MATERIAL_DEFAULTS);
var NUMERIC_RANGES = {
  blur: [0, 100],
  saturation: [0, 8],
  brightness: [0, 3],
  tintOpacity: [0, 1],
  refraction: [0, 1],
  ior: [1, 2.5],
  magnify: [0, 0.1],
  thickness: [0, 100],
  bevelWidth: [0, 200],
  bevelDepth: [0, 1],
  dispersion: [0, 1],
  specular: [0, 1],
  shadow: [0, 1],
  frost: [0, 1]
};
function clampMaterial(material) {
  const result = { ...material };
  for (const key of MATERIAL_KEYS) {
    const range = NUMERIC_RANGES[key];
    if (!range) continue;
    const value = result[key];
    const numeric = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(numeric)) {
      Object.assign(result, { [key]: MATERIAL_DEFAULTS[key] });
      continue;
    }
    Object.assign(result, { [key]: Math.min(range[1], Math.max(range[0], numeric)) });
  }
  if (typeof result.tint !== "string") result.tint = MATERIAL_DEFAULTS.tint;
  if (result.shape !== "squircle") result.shape = "rounded";
  if (result.radius !== "auto") {
    const radius = Number(result.radius);
    result.radius = Number.isFinite(radius) ? Math.max(0, radius) : MATERIAL_DEFAULTS.radius;
  }
  return result;
}
function glassShadowCss(shadow, height) {
  if (shadow <= 0) return "";
  const h = Math.max(height, 1);
  const lift = (h * 0.11).toFixed(1);
  const spread = (h * 0.3).toFixed(1);
  const ambient = (0.22 * shadow).toFixed(3);
  const contact = (0.1 * shadow).toFixed(3);
  return `0 ${lift}px ${spread}px rgba(0, 0, 0, ${ambient}), 0 1px 2px rgba(0, 0, 0, ${contact})`;
}
function glassSheenCss(material) {
  return colorWithOpacity(material.tint, material.tintOpacity);
}
function glassInnerShadowCss(specular) {
  const lit = Math.min(1, specular * 0.9).toFixed(3);
  return `inset 1px 1px 0 rgba(255, 255, 255, ${lit}), inset -1px -1px 0 rgba(255, 255, 255, ${lit})`;
}
function resolveMaterial(options) {
  const preset = options.preset ?? "clear";
  const merged = { ...MATERIAL_DEFAULTS, ...MATERIAL_PRESETS[preset] };
  for (const key of MATERIAL_KEYS) {
    const value = options[key];
    if (value !== void 0) {
      Object.assign(merged, { [key]: value });
    }
  }
  return clampMaterial(merged);
}

// ../core/src/backends/css-fallback.ts
var TOUCHED = ["background", "backdrop-filter", "-webkit-backdrop-filter", "border-radius", "clip-path", "box-shadow"];
function isStyleable(element) {
  return typeof HTMLElement !== "undefined" && element instanceof HTMLElement;
}
function apply(surface) {
  if (!isStyleable(surface.element)) return;
  const { material } = surface;
  const style = surface.element.style;
  const filter = `blur(${material.blur}px) saturate(${material.saturation}) brightness(${material.brightness})`;
  style.setProperty("background", glassSheenCss(material));
  style.setProperty("backdrop-filter", filter);
  style.setProperty("-webkit-backdrop-filter", filter);
  if (typeof material.radius === "number") {
    style.setProperty("border-radius", `${material.radius}px`);
  }
  if (material.shape === "squircle") {
    style.setProperty("clip-path", squircleClipPath());
  } else {
    style.removeProperty("clip-path");
  }
  const cast = glassShadowCss(material.shadow, surface.element.getBoundingClientRect().height);
  if (cast) style.setProperty("box-shadow", cast);
  else style.removeProperty("box-shadow");
}
var cssFallbackBackend = {
  id: "css-fallback",
  priority: 0,
  isSupported() {
    return true;
  },
  mount(surface) {
    const restore = captureInlineStyles(surface.element, TOUCHED);
    apply(surface);
    const instance = {
      update(next) {
        apply(next);
      },
      sync() {
      },
      destroy() {
        restore();
      }
    };
    return instance;
  }
};

// lens-worker:virtual:lens-worker

// ../core/src/worker/host.ts
var worker = null;
var workerBroken = false;
var nextId = 0;
var pending = /* @__PURE__ */ new Map();
function ensureWorker() {
  if (workerBroken || typeof Worker === "undefined" || typeof URL === "undefined") return null;
  if (worker) return worker;
  try {
    worker = new Worker(new URL("./lens-worker.js", import.meta.url));
    worker.onmessage = (event) => {
      const { id, pixels, width, height, maxOffset } = event.data;
      const request = pending.get(id);
      if (!request) return;
      pending.delete(id);
      const entry = encodeLensMap({ pixels, width, height, maxOffset });
      cacheLensMap(request.key, entry);
      request.onReady(entry);
    };
    worker.onerror = () => {
      failPending();
    };
    return worker;
  } catch {
    workerBroken = true;
    return null;
  }
}
function failPending() {
  workerBroken = true;
  worker?.terminate();
  worker = null;
  const requests = [...pending.values()];
  pending.clear();
  for (const request of requests) {
    const map = cachedLensMap(request.key) ?? generateLensMap(request.opts);
    if (map) request.onReady(map);
  }
}
function requestLensMap(opts, onReady) {
  if (opts.width < 1 || opts.height < 1) return;
  const key = lensMapKey(opts);
  const hit = cachedLensMap(key);
  if (hit) {
    onReady(hit);
    return;
  }
  const active = ensureWorker();
  if (!active) {
    const map = generateLensMap(opts);
    if (map) onReady(map);
    return;
  }
  const id = ++nextId;
  pending.set(id, { key, opts, onReady });
  try {
    active.postMessage({ id, opts, mapSide: opts.mapSide ?? getQuality().mapSide });
  } catch {
    pending.delete(id);
    failPending();
    const map = generateLensMap(opts);
    if (map) onReady(map);
  }
}

// ../core/src/backends/filter-chain.ts
var SVG_NS = "http://www.w3.org/2000/svg";
var DEFAULT_AZIMUTH = 225;
function azimuthFromBearing(deg) {
  return ((90 - deg) % 360 + 360) % 360;
}
function resolveSurfaceScale(material) {
  const thickness = typeof material.thickness === "number" ? material.thickness : 12;
  return Math.max(2, Math.min(thickness, 40));
}
function el(name) {
  return document.createElementNS(SVG_NS, name);
}
function mkDisplace(role, scale, result, source) {
  const node = el("feDisplacementMap");
  node.setAttribute("in", source);
  node.setAttribute("in2", "lgMap");
  node.setAttribute("xChannelSelector", "R");
  node.setAttribute("yChannelSelector", "G");
  node.setAttribute("scale", String(scale));
  node.setAttribute("result", result);
  node.setAttribute("data-lg-role", role);
  return node;
}
function mkChannel(input, out, rgb) {
  const m = el("feColorMatrix");
  m.setAttribute("in", input);
  m.setAttribute("type", "matrix");
  const [r, g, b] = rgb;
  m.setAttribute("values", `${r} 0 0 0 0 0 ${g} 0 0 0 0 0 ${b} 0 0 0 0 0 1 0`);
  m.setAttribute("result", out);
  return m;
}
function mkComposite(a, b, out) {
  const c = el("feComposite");
  c.setAttribute("in", a);
  c.setAttribute("in2", b);
  c.setAttribute("operator", "arithmetic");
  c.setAttribute("k1", "0");
  c.setAttribute("k2", "1");
  c.setAttribute("k3", "1");
  c.setAttribute("k4", "0");
  c.setAttribute("result", out);
  return c;
}
function placeLensMap(image, width, height) {
  image.setAttribute("x", String(-0.2 * width));
  image.setAttribute("y", String(-0.2 * height));
  image.setAttribute("width", String(1.4 * width));
  image.setAttribute("height", String(1.4 * height));
}
function buildLensChain(spec) {
  const { filter, material, scale, passes } = spec;
  filter.replaceChildren();
  const feImage = el("feImage");
  feImage.setAttribute("result", "lgMap");
  feImage.setAttribute("preserveAspectRatio", "none");
  feImage.setAttribute("x", "-20%");
  feImage.setAttribute("y", "-20%");
  feImage.setAttribute("width", "140%");
  feImage.setAttribute("height", "140%");
  filter.appendChild(feImage);
  const blur = el("feGaussianBlur");
  blur.setAttribute("in", "SourceGraphic");
  blur.setAttribute("stdDeviation", String(material.blur));
  blur.setAttribute("result", material.frost > 0 ? "lgSharp" : "lgSoft");
  blur.setAttribute("data-lg-role", "blur");
  filter.appendChild(blur);
  if (material.frost > 0) {
    const spread = el("feGaussianBlur");
    spread.setAttribute("in", "SourceGraphic");
    spread.setAttribute("stdDeviation", String(spec.spread ?? FROST_SPREAD));
    spread.setAttribute("edgeMode", "duplicate");
    spread.setAttribute("result", "lgScatter");
    spread.setAttribute("data-lg-role", "frost");
    const blend = el("feComposite");
    blend.setAttribute("in", "lgSharp");
    blend.setAttribute("in2", "lgScatter");
    blend.setAttribute("operator", "arithmetic");
    blend.setAttribute("k1", "0");
    blend.setAttribute("k2", String(Number((1 - material.frost).toFixed(4))));
    blend.setAttribute("k3", String(material.frost));
    blend.setAttribute("k4", "0");
    blend.setAttribute("result", "lgSoft");
    blend.setAttribute("data-lg-role", "frost-mix");
    filter.append(spread, blend);
  }
  const caShift = material.dispersion * 0.25;
  let displace;
  let lensResult;
  const displaceNodes = [];
  if (passes === 3) {
    const dispR = mkDisplace("displace-r", scale * (1 - caShift), "lgDispR", "lgSoft");
    displace = mkDisplace("displace", scale, "lgDispG", "lgSoft");
    const dispB = mkDisplace("displace-b", scale * (1 + caShift), "lgDispB", "lgSoft");
    displaceNodes.push(dispR, displace, dispB);
    filter.append(
      dispR,
      mkChannel("lgDispR", "lgR", [1, 0, 0]),
      displace,
      mkChannel("lgDispG", "lgG", [0, 1, 0]),
      dispB,
      mkChannel("lgDispB", "lgB", [0, 0, 1]),
      mkComposite("lgR", "lgG", "lgRG"),
      mkComposite("lgRG", "lgB", "lgLens")
    );
    lensResult = "lgLens";
  } else {
    displace = mkDisplace("displace", scale, "lgLens", "lgSoft");
    displaceNodes.push(displace);
    filter.appendChild(displace);
    lensResult = "lgLens";
  }
  let lightNodes = null;
  if (material.lighting && material.specular > 1e-3) {
    const height = el("feColorMatrix");
    height.setAttribute("in", "lgMap");
    height.setAttribute("type", "matrix");
    height.setAttribute("values", "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0 0");
    height.setAttribute("result", "lgHeight");
    const distant = el("feDistantLight");
    distant.setAttribute("azimuth", String(DEFAULT_AZIMUTH));
    distant.setAttribute("elevation", "58");
    const specular = el("feSpecularLighting");
    specular.setAttribute("in", "lgHeight");
    specular.setAttribute("surfaceScale", String(resolveSurfaceScale(material)));
    specular.setAttribute("specularConstant", (material.specular * 1.1).toFixed(3));
    specular.setAttribute("specularExponent", "22");
    specular.setAttribute("lighting-color", "#ffffff");
    specular.setAttribute("result", "lgSpec");
    specular.setAttribute("data-lg-role", "specular");
    specular.appendChild(distant);
    const inside = el("feComponentTransfer");
    inside.setAttribute("in", "lgHeight");
    inside.setAttribute("result", "lgInside");
    const insideFn = el("feFuncA");
    insideFn.setAttribute("type", "linear");
    insideFn.setAttribute("slope", "255");
    insideFn.setAttribute("intercept", "0");
    inside.appendChild(insideFn);
    const rim = el("feComposite");
    rim.setAttribute("in", "lgInside");
    rim.setAttribute("in2", "lgHeight");
    rim.setAttribute("operator", "arithmetic");
    rim.setAttribute("k1", "0");
    rim.setAttribute("k2", "1");
    rim.setAttribute("k3", "-1");
    rim.setAttribute("k4", "0");
    rim.setAttribute("result", "lgRim");
    const clip = el("feComposite");
    clip.setAttribute("in", "lgSpec");
    clip.setAttribute("in2", "lgRim");
    clip.setAttribute("operator", "in");
    clip.setAttribute("result", "lgSpecClipped");
    const add = el("feComposite");
    add.setAttribute("in", lensResult);
    add.setAttribute("in2", "lgSpecClipped");
    add.setAttribute("operator", "arithmetic");
    add.setAttribute("k1", "0");
    add.setAttribute("k2", "1");
    add.setAttribute("k3", "1");
    add.setAttribute("k4", "0");
    add.setAttribute("result", "lgLit");
    filter.append(height, inside, rim, specular, clip, add);
    lensResult = "lgLit";
    lightNodes = { distant };
  }
  const saturate = el("feColorMatrix");
  saturate.setAttribute("in", lensResult);
  saturate.setAttribute("type", "saturate");
  saturate.setAttribute("values", String(material.saturation));
  saturate.setAttribute("result", "lgSat");
  const brightnessNode = el("feComponentTransfer");
  brightnessNode.setAttribute("in", "lgSat");
  for (const name of ["feFuncR", "feFuncG", "feFuncB"]) {
    const fn = el(name);
    fn.setAttribute("type", "linear");
    fn.setAttribute("slope", String(material.brightness));
    brightnessNode.appendChild(fn);
  }
  filter.append(saturate, brightnessNode);
  return {
    feImage,
    displace,
    blur,
    setLightAngle(deg) {
      if (!lightNodes) return;
      lightNodes.distant.setAttribute("azimuth", azimuthFromBearing(deg).toFixed(0));
    },
    setScale(next) {
      const shift = material.dispersion * 0.25;
      for (const node of displaceNodes) {
        const role = node.getAttribute("data-lg-role");
        const factor = role === "displace-r" ? 1 - shift : role === "displace-b" ? 1 + shift : 1;
        node.setAttribute("scale", String(next * factor));
      }
    }
  };
}

// ../core/src/backends/css-svg.ts
var SVG_NS2 = "http://www.w3.org/2000/svg";
var uid = 0;
var defsRoot = null;
function ensureDefs() {
  if (typeof document === "undefined" || !document.body) return null;
  if (defsRoot && defsRoot.isConnected) return defsRoot;
  const svg = document.createElementNS(SVG_NS2, "svg");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.setAttribute("aria-hidden", "true");
  svg.style.position = "absolute";
  svg.style.left = "-9999px";
  svg.setAttribute("data-liquid-glass-ignore", "");
  const defs = document.createElementNS(SVG_NS2, "defs");
  svg.appendChild(defs);
  document.body.appendChild(svg);
  defsRoot = defs;
  return defs;
}
function releaseDefs() {
  if (!defsRoot || defsRoot.childElementCount > 0) return;
  defsRoot.ownerSVGElement?.remove();
  defsRoot = null;
}
function isStyleable2(element) {
  return typeof HTMLElement !== "undefined" && element instanceof HTMLElement;
}
function surfaceSize(surface) {
  const { rect } = surface.state;
  if (rect.width > 0 && rect.height > 0) return { width: rect.width, height: rect.height };
  const box = surface.element.getBoundingClientRect();
  return { width: box.width, height: box.height };
}
var TOUCHED2 = [
  "backdrop-filter",
  "-webkit-backdrop-filter",
  "background",
  "border-radius",
  "box-shadow",
  "clip-path"
];
var CssSvgInstance = class {
  #id;
  #filter;
  #restore;
  #chain = null;
  #chainKey = "";
  #band = 0;
  #lastWidth = 0;
  #lastHeight = 0;
  #lastMapKey = " ";
  #mapToken = 0;
  constructor(surface, defs) {
    this.#id = `lg-${++uid}`;
    this.#filter = document.createElementNS(SVG_NS2, "filter");
    this.#filter.setAttribute("id", this.#id);
    this.#filter.setAttribute("x", "-20%");
    this.#filter.setAttribute("y", "-20%");
    this.#filter.setAttribute("width", "140%");
    this.#filter.setAttribute("height", "140%");
    this.#filter.setAttribute("color-interpolation-filters", "sRGB");
    defs.appendChild(this.#filter);
    this.#restore = captureInlineStyles(surface.element, TOUCHED2);
    this.#applyStyles(surface);
    this.#refresh(surface, true);
  }
  update(surface) {
    this.#applyStyles(surface);
    this.#refresh(surface, true);
  }
  sync(surface) {
    this.#refresh(surface, false);
  }
  destroy() {
    this.#mapToken++;
    this.#filter.remove();
    this.#restore();
    releaseDefs();
  }
  debug() {
    return { band: this.#band };
  }
  #applyStyles(surface) {
    if (!isStyleable2(surface.element)) return;
    const { material } = surface;
    const style = surface.element.style;
    style.setProperty("backdrop-filter", `url("#${this.#id}")`);
    style.setProperty("-webkit-backdrop-filter", `url("#${this.#id}")`);
    style.setProperty("background", glassSheenCss(material));
    if (typeof material.radius === "number") {
      style.setProperty("border-radius", `${material.radius}px`);
    }
    if (material.shape === "squircle") {
      style.setProperty("clip-path", squircleClipPath());
    } else {
      style.removeProperty("clip-path");
    }
    const inner = glassInnerShadowCss(material.specular);
    const cast = glassShadowCss(material.shadow, surfaceSize(surface).height);
    style.setProperty("box-shadow", cast ? `${cast}, ${inner}` : inner);
  }
  #refresh(surface, force) {
    const { width, height } = surfaceSize(surface);
    if (width < 1 || height < 1) return;
    if (!force && Math.abs(width - this.#lastWidth) < 1 && Math.abs(height - this.#lastHeight) < 1) {
      return;
    }
    this.#lastWidth = width;
    this.#lastHeight = height;
    const { material } = surface;
    if (material.shape === "squircle" && material.radius === "auto" && isStyleable2(surface.element)) {
      surface.element.style.setProperty(
        "border-radius",
        `${Math.round(Math.min(width, height) * 0.36)}px`
      );
    }
    const radius = resolveRadiusPx(material.radius, surface.element, width, height);
    this.#band = resolveBandPx(material.bevelWidth, radius, width, height);
    const token = ++this.#mapToken;
    requestLensMap(
      {
        width,
        height,
        radius,
        shape: material.shape,
        band: this.#band,
        ior: material.ior,
        thickness: resolveThicknessPx(material.thickness, width, height),
        bevelDepth: material.bevelDepth,
        magnify: material.magnify,
        mapSide: getQuality(surface.quality).mapSide
      },
      (map) => {
        if (token !== this.#mapToken) return;
        const { material: latest } = surface;
        const passes = latest.dispersion > 1e-3 && getQuality(surface.quality).caPasses === 3 ? 3 : 1;
        const scale = 2 * map.maxOffset * latest.refraction * 2;
        const spread = Math.round(frostSpread(width, height) * 10) / 10;
        const chainKey = `${passes}|${latest.frost}|${spread}|${latest.blur}|${latest.saturation}|${latest.brightness}|${latest.dispersion}`;
        if (!this.#chain || chainKey !== this.#chainKey) {
          this.#chain = buildLensChain({
            filter: this.#filter,
            material: latest,
            scale,
            passes,
            spread
          });
          this.#chainKey = chainKey;
          this.#lastMapKey = "";
        } else {
          this.#chain.setScale(scale);
        }
        const image = this.#chain.feImage;
        placeLensMap(image, width, height);
        const mapKey = map.url ?? "";
        if (map.url && mapKey !== this.#lastMapKey) {
          image.setAttribute("href", map.url);
          this.#lastMapKey = mapKey;
        }
      }
    );
  }
};
var cssSvgBackend = {
  id: "css-svg",
  priority: 30,
  isSupported(capabilities) {
    return capabilities.backdropFilterUrl;
  },
  mount(surface) {
    const defs = ensureDefs();
    if (!defs) {
      return { update() {
      }, sync() {
      }, destroy() {
      } };
    }
    const instance = new CssSvgInstance(surface, defs);
    return {
      update(next) {
        instance.update(next);
      },
      sync(next) {
        instance.sync(next);
      },
      destroy() {
        instance.destroy();
      },
      debug() {
        return instance.debug();
      }
    };
  }
};

// ../core/src/backends/svg-content.ts
var SVG_NS3 = "http://www.w3.org/2000/svg";
function paints(node) {
  const computed = getComputedStyle(node);
  const color = parseColor(computed.backgroundColor);
  if (color && color[3] > 0.01) return true;
  return computed.backgroundImage !== "" && computed.backgroundImage !== "none";
}
var warnedMissingSource = false;
function warnMissingSource() {
  if (warnedMissingSource) return;
  warnedMissingSource = true;
  console.warn(
    "liquidglass: no painted ancestor to refract on this engine, so the surface falls back to blur and tint. Pass backdrop: <element|selector> to name the layer it should bend."
  );
}
function resolveContentSource(element) {
  if (typeof getComputedStyle !== "function") return null;
  const doc = element.ownerDocument;
  let node = element.parentElement;
  while (node && node !== doc?.body && node !== doc?.documentElement) {
    if (paints(node)) return node;
    node = node.parentElement;
  }
  return null;
}
var TOUCHED3 = [
  "backdrop-filter",
  "-webkit-backdrop-filter",
  "background",
  "border-radius",
  "box-shadow",
  "isolation",
  "clip-path",
  "position"
];
var uid2 = 0;
var defsRoot2 = null;
function ensureDefs2() {
  if (typeof document === "undefined" || !document.body) return null;
  if (defsRoot2 && defsRoot2.isConnected) return defsRoot2;
  const svg = document.createElementNS(SVG_NS3, "svg");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.setAttribute("aria-hidden", "true");
  svg.style.position = "absolute";
  svg.style.left = "-9999px";
  svg.setAttribute("data-liquid-glass-ignore", "");
  const defs = document.createElementNS(SVG_NS3, "defs");
  svg.appendChild(defs);
  document.body.appendChild(svg);
  defsRoot2 = defs;
  return defs;
}
function releaseDefs2() {
  if (!defsRoot2 || defsRoot2.childElementCount > 0) return;
  defsRoot2.ownerSVGElement?.remove();
  defsRoot2 = null;
}
function isStyleable3(element) {
  return typeof HTMLElement !== "undefined" && element instanceof HTMLElement;
}
function surfaceSize2(surface) {
  const { rect } = surface.state;
  if (rect.width > 0 && rect.height > 0) return { width: rect.width, height: rect.height };
  const box = surface.element.getBoundingClientRect();
  return { width: box.width, height: box.height };
}
var SvgContentInstance = class {
  #defs;
  #filter = null;
  #chain = null;
  #chainKey = "";
  #band = 0;
  #lastMapKey = "";
  #layer = null;
  #clone = null;
  #source = null;
  #mutationObserver = null;
  #cloneFrame = 0;
  #restore = null;
  #lastWidth = 0;
  #lastHeight = 0;
  #mapToken = 0;
  constructor(surface, defs) {
    this.#defs = defs;
    this.#restore = captureInlineStyles(surface.element, TOUCHED3);
    this.#applyBaseStyles(surface);
    this.#syncLayer(surface);
  }
  update(surface) {
    this.#applyBaseStyles(surface);
    this.#syncLayer(surface);
    this.#refreshMap(surface, true);
  }
  sync(surface) {
    this.#lastSurface = surface;
    if (this.#recloneDeferred && surface.state.visible) {
      this.#recloneDeferred = false;
      this.#scheduleReclone();
    }
    this.#position(surface);
    this.#refreshMap(surface, false);
  }
  destroy() {
    this.#mapToken++;
    this.#teardownLayer();
    this.#restore?.();
    releaseDefs2();
  }
  #applyBaseStyles(surface) {
    if (!isStyleable3(surface.element)) return;
    const { material } = surface;
    const style = surface.element.style;
    const filter = `blur(${material.blur}px) saturate(${material.saturation}) brightness(${material.brightness})`;
    style.setProperty("backdrop-filter", filter);
    style.setProperty("-webkit-backdrop-filter", filter);
    style.setProperty("background", glassSheenCss(material));
    if (typeof material.radius === "number") {
      style.setProperty("border-radius", `${material.radius}px`);
    }
    if (material.shape === "squircle") {
      style.setProperty("clip-path", squircleClipPath());
    } else {
      style.removeProperty("clip-path");
    }
    const height = surface.element.getBoundingClientRect().height;
    const inner = glassInnerShadowCss(material.specular);
    const cast = glassShadowCss(material.shadow, height);
    style.setProperty("box-shadow", cast ? `${cast}, ${inner}` : inner);
    style.setProperty("isolation", "isolate");
    if (typeof getComputedStyle === "function" && getComputedStyle(surface.element).position === "static") {
      style.setProperty("position", "relative");
    }
  }
  #syncLayer(surface) {
    const wanted = surface.backdrop ?? resolveContentSource(surface.element);
    if (wanted === this.#source) {
      this.#position(surface);
      return;
    }
    this.#teardownLayer();
    this.#source = wanted;
    if (!this.#source) {
      warnMissingSource();
      return;
    }
    if (!isStyleable3(surface.element)) return;
    const id = `lgc-${++uid2}`;
    const filter = document.createElementNS(SVG_NS3, "filter");
    filter.setAttribute("id", id);
    filter.setAttribute("x", "-20%");
    filter.setAttribute("y", "-20%");
    filter.setAttribute("width", "140%");
    filter.setAttribute("height", "140%");
    filter.setAttribute("color-interpolation-filters", "sRGB");
    this.#defs.appendChild(filter);
    this.#filter = filter;
    this.#chain = null;
    this.#chainKey = "";
    this.#lastMapKey = "";
    const layer = document.createElement("div");
    layer.setAttribute("data-liquid-glass-layer", "refract");
    layer.setAttribute("aria-hidden", "true");
    const layerStyle = layer.style;
    layerStyle.position = "absolute";
    layerStyle.inset = "0";
    layerStyle.overflow = "hidden";
    layerStyle.borderRadius = "inherit";
    layerStyle.zIndex = "-1";
    layerStyle.pointerEvents = "none";
    layerStyle.filter = `url("#${id}")`;
    surface.element.insertBefore(layer, surface.element.firstChild);
    this.#layer = layer;
    this.#recloneNow(surface);
    this.#observeSource();
    this.#refreshMap(surface, true);
  }
  #reachesLens(target) {
    const surface = this.#lastSurface;
    if (!surface || !(target instanceof Element)) return true;
    if (typeof target.getBoundingClientRect !== "function") return true;
    const box = target.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) return true;
    const lens = surface.element.getBoundingClientRect();
    if (lens.width === 0 && lens.height === 0) return true;
    const reach = this.#band + 24;
    return box.left < lens.right + reach && box.right > lens.left - reach && box.top < lens.bottom + reach && box.bottom > lens.top - reach;
  }
  #observeSource() {
    if (!this.#source || typeof MutationObserver === "undefined") return;
    this.#mutationObserver = new MutationObserver((records) => {
      for (const record of records) {
        const target = record.target;
        if (target instanceof Element && target.closest("[data-liquid-glass], [data-liquid-glass-layer], [data-liquid-glass-overlay]")) {
          continue;
        }
        if (!this.#reachesLens(target)) continue;
        this.#scheduleReclone();
        return;
      }
    });
    this.#mutationObserver.observe(this.#source, {
      childList: true,
      attributes: true,
      characterData: true,
      subtree: true
    });
  }
  #recloneDeferred = false;
  #scheduleReclone() {
    if (this.#cloneFrame || typeof requestAnimationFrame !== "function") return;
    if (typeof document !== "undefined" && document.hidden) {
      this.#recloneDeferred = true;
      return;
    }
    if (this.#lastSurface && !this.#lastSurface.state.visible) {
      this.#recloneDeferred = true;
      return;
    }
    this.#cloneFrame = requestAnimationFrame(() => {
      this.#cloneFrame = 0;
      this.#recloneDeferred = false;
      if (this.#lastSurface) this.#recloneNow(this.#lastSurface);
    });
  }
  #lastSurface = null;
  #recloneNow(surface) {
    this.#lastSurface = surface;
    if (!this.#layer || !this.#source) return;
    this.#clone?.remove();
    const clone = this.#source.cloneNode(true);
    for (const glass of clone.querySelectorAll(
      "liquid-glass, [data-liquid-glass], [data-liquid-glass-layer], [data-liquid-glass-overlay], [data-liquid-glass-ignore]"
    )) {
      glass.remove();
    }
    for (const node of clone.querySelectorAll("[id], [name]")) {
      node.removeAttribute("id");
      node.removeAttribute("name");
    }
    if (isStyleable3(clone)) {
      clone.style.margin = "0";
      clone.style.pointerEvents = "none";
      clone.style.userSelect = "none";
      clone.inert = true;
    }
    clone.setAttribute("aria-hidden", "true");
    clone.removeAttribute("id");
    clone.removeAttribute("name");
    this.#layer.appendChild(clone);
    this.#clone = clone;
    this.#position(surface);
  }
  #position(surface) {
    const clone = this.#clone;
    if (!clone || !this.#source || !isStyleable3(clone)) return;
    const sourceBox = this.#source.getBoundingClientRect();
    const glassBox = surface.element.getBoundingClientRect();
    const x = sourceBox.left - glassBox.left - surface.element.clientLeft;
    const y = sourceBox.top - glassBox.top - surface.element.clientTop;
    const style = clone.style;
    if (style.position !== "absolute") {
      style.inset = "";
      style.position = "absolute";
      style.left = "0";
      style.top = "0";
      style.willChange = "transform";
    }
    const next = `translate(${x}px, ${y}px)`;
    if (style.transform !== next) style.transform = next;
    const w = `${sourceBox.width}px`;
    const h = `${sourceBox.height}px`;
    if (style.width !== w) style.width = w;
    if (style.height !== h) style.height = h;
    const host = surface.element;
    const covered = sourceBox.left <= glassBox.left + 1 && sourceBox.top <= glassBox.top + 1 && sourceBox.right >= glassBox.right - 1 && sourceBox.bottom >= glassBox.bottom - 1;
    if (covered !== this.#hostFilterOff) {
      this.#hostFilterOff = covered;
      if (covered) {
        host.style.setProperty("backdrop-filter", "none");
        host.style.setProperty("-webkit-backdrop-filter", "none");
      } else {
        this.#applyBaseStyles(surface);
      }
    }
  }
  #hostFilterOff = false;
  #refreshMap(surface, force) {
    if (!this.#filter) return;
    const { width, height } = surfaceSize2(surface);
    if (width < 1 || height < 1) return;
    if (!force && Math.abs(width - this.#lastWidth) < 1 && Math.abs(height - this.#lastHeight) < 1) {
      return;
    }
    this.#lastWidth = width;
    this.#lastHeight = height;
    const { material } = surface;
    if (material.shape === "squircle" && material.radius === "auto" && isStyleable3(surface.element)) {
      surface.element.style.setProperty(
        "border-radius",
        `${Math.round(Math.min(width, height) * 0.36)}px`
      );
    }
    const radius = resolveRadiusPx(material.radius, surface.element, width, height);
    this.#band = resolveBandPx(material.bevelWidth, radius, width, height);
    const token = ++this.#mapToken;
    requestLensMap(
      {
        width,
        height,
        radius,
        shape: material.shape,
        band: this.#band,
        ior: material.ior,
        thickness: resolveThicknessPx(material.thickness, width, height),
        bevelDepth: material.bevelDepth,
        magnify: material.magnify,
        mapSide: getQuality(surface.quality).mapSide
      },
      (map) => {
        if (token !== this.#mapToken || !this.#filter) return;
        const { material: latest } = surface;
        const scale = 2 * map.maxOffset * latest.refraction * 2;
        const spread = Math.round(frostSpread(width, height) * 10) / 10;
        const chainKey = `1|${latest.frost}|${spread}|${latest.blur}|${latest.saturation}|${latest.brightness}`;
        if (!this.#chain || chainKey !== this.#chainKey) {
          this.#chain = buildLensChain({ filter: this.#filter, material: latest, scale, passes: 1, spread });
          this.#chainKey = chainKey;
          this.#lastMapKey = "";
        } else {
          this.#chain.setScale(scale);
        }
        const image = this.#chain.feImage;
        placeLensMap(image, width, height);
        if (map.url && map.url !== this.#lastMapKey) {
          image.setAttribute("href", map.url);
          this.#lastMapKey = map.url;
        }
      }
    );
  }
  debug() {
    return { band: this.#band };
  }
  #teardownLayer() {
    this.#mutationObserver?.disconnect();
    this.#mutationObserver = null;
    if (this.#cloneFrame && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this.#cloneFrame);
      this.#cloneFrame = 0;
    }
    this.#clone?.remove();
    this.#clone = null;
    this.#layer?.remove();
    this.#layer = null;
    this.#filter?.remove();
    this.#filter = null;
    this.#chain = null;
    this.#chainKey = "";
    this.#lastMapKey = "";
    this.#source = null;
  }
};
var svgContentBackend = {
  id: "svg-content",
  priority: 20,
  isSupported(capabilities) {
    return capabilities.svgFilterOnContent;
  },
  mount(surface) {
    const defs = ensureDefs2();
    if (!defs) {
      return { update() {
      }, sync() {
      }, destroy() {
      } };
    }
    const instance = new SvgContentInstance(surface, defs);
    return {
      update(next) {
        instance.update(next);
      },
      sync(next) {
        instance.sync(next);
      },
      destroy() {
        instance.destroy();
      },
      debug() {
        return instance.debug();
      }
    };
  }
};

// ../core/src/gl/renderer.ts
var MAX_SHAPES = 8;
function scaleMaterialToDevice(material, scale) {
  return {
    ...material,
    blur: material.blur * scale.ratio,
    bevelWidth: resolveBandPx(material.bevelWidth, scale.radius, scale.width, scale.height) * scale.ratio,
    thickness: resolveThicknessPx(material.thickness, scale.width, scale.height) * scale.ratio
  };
}
var VERT = `#version 300 es
layout(location=0) in vec2 a_pos;
uniform vec4 u_lensRect;
uniform vec2 u_canvasSize;
out vec2 v_local;
void main() {
  v_local = a_pos;
  vec2 px = u_lensRect.xy + a_pos * u_lensRect.zw;
  vec2 clip = (px / u_canvasSize) * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
}`;
var FRAG = `#version 300 es
precision highp float;
uniform sampler2D u_tex;
uniform vec4 u_lensRect;
uniform vec4 u_texRect;
uniform vec2 u_texSize;
uniform vec4 u_shapes[8];
uniform float u_shapeRadii[8];
uniform int u_shapeCount;
uniform int u_shapeMode;
uniform float u_mergeK;
uniform float u_bevelWidth;
uniform float u_ior;
uniform float u_magnify;
uniform vec2 u_center;
uniform vec2 u_lightDir;
uniform float u_displace;
uniform float u_blur;
uniform float u_dispersion;
uniform float u_saturation;
uniform float u_brightness;
uniform vec4 u_tint;
uniform float u_specular;
uniform float u_frost;
uniform float u_bevelDepth;
uniform float u_pxRatio;
uniform float u_rimTone;
in vec2 v_local;
out vec4 outColor;

float sdBox(vec2 p, vec2 halfSize, float r) {
  float rr = min(r, min(halfSize.x, halfSize.y));
  vec2 q = abs(p) - halfSize + rr;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - rr;
}

float smin(float a, float b, float k) {
  float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
  return mix(b, a, h) - k * h * (1.0 - h);
}

float sdSquircle(vec2 p, vec2 halfSize) {
  vec2 h = max(halfSize, vec2(0.001));
  vec2 q = abs(p) / h;
  float v = pow(pow(q.x, 4.0) + pow(q.y, 4.0), 0.25);
  return (v - 1.0) * min(h.x, h.y);
}

float shapeSdf(int i, vec2 px) {
  vec4 s = u_shapes[i];
  vec2 p = px - s.xy - s.zw * 0.5;
  if (u_shapeMode == 1) return sdSquircle(p, s.zw * 0.5);
  return sdBox(p, s.zw * 0.5, u_shapeRadii[i]);
}

float sceneSdf(vec2 px) {
  float d = shapeSdf(0, px);
  for (int i = 1; i < 8; i++) {
    if (i >= u_shapeCount) break;
    d = smin(d, shapeSdf(i, px), max(u_mergeK, 0.001));
  }
  return d;
}

vec3 sampleBg(vec2 px) {
  vec2 uv = (px - u_texRect.xy) / u_texRect.zw;
  return texture(u_tex, clamp(uv, 0.001, 0.999)).rgb;
}

vec3 blurredBg(vec2 px, float sigma) {
  float radius = sigma * 1.4;
  if (radius < 0.5) return sampleBg(px);
  float tpp = u_texSize.x / max(u_texRect.z, 1.0);
  float lod = log2(max(radius * tpp, 1.0));
  vec2 uv = clamp((px - u_texRect.xy) / u_texRect.zw, 0.001, 0.999);
  vec2 o = vec2(radius * 0.6) / u_texRect.zw;
  vec3 acc = textureLod(u_tex, uv, lod).rgb;
  acc += textureLod(u_tex, clamp(uv + o, vec2(0.001), vec2(0.999)), lod).rgb;
  acc += textureLod(u_tex, clamp(uv - o, vec2(0.001), vec2(0.999)), lod).rgb;
  acc += textureLod(u_tex, clamp(uv + vec2(o.x, -o.y), vec2(0.001), vec2(0.999)), lod).rgb;
  acc += textureLod(u_tex, clamp(uv + vec2(-o.x, o.y), vec2(0.001), vec2(0.999)), lod).rgb;
  return acc / 5.0;
}

float lensMag(float depth, float band, float ior) {
  if (depth < 0.0 || depth >= band || ior <= 1.0) return 0.0;
  float decay = ${EDGE_DECAY} * (1.6 - u_bevelDepth) / (1.6 - ${DEFAULT_BEVEL_DEPTH});
  float floorLevel = exp(-1.0 / decay);
  float shape = (exp(-depth / band / decay) - floorLevel) / (1.0 - floorLevel);
  return ${EDGE_REACH} * band * shape * (ior - 1.0) / (${REFERENCE_IOR} - 1.0);
}

void main() {
  vec2 basePx = u_lensRect.xy + v_local * u_lensRect.zw;
  float d = sceneSdf(basePx);
  float coverage = clamp(0.5 - d / 1.5, 0.0, 1.0);
  if (coverage <= 0.0) { outColor = vec4(0.0); discard; }

  float depth = -d;
  float eps = 1.0;
  vec2 grad = vec2(
    sceneSdf(basePx + vec2(eps, 0.0)) - sceneSdf(basePx - vec2(eps, 0.0)),
    sceneSdf(basePx + vec2(0.0, eps)) - sceneSdf(basePx - vec2(0.0, eps))
  );
  float gradLen = max(length(grad), 1e-5);
  grad /= gradLen;

  float mag = lensMag(depth, max(u_bevelWidth, 1e-3), u_ior) * u_displace;
  vec2 bend = -grad * mag;
  vec2 zoom = (basePx - u_center) * -u_magnify;
  float px = max(u_pxRatio, 1.0);

  vec3 col;
  if (u_dispersion > 0.001) {
    col = vec3(
      blurredBg(basePx + bend * (1.0 - u_dispersion * 0.6) + zoom, u_blur).r,
      blurredBg(basePx + bend + zoom, u_blur).g,
      blurredBg(basePx + bend * (1.0 + u_dispersion * 0.6) + zoom, u_blur).b
    );
  } else {
    col = blurredBg(basePx + bend + zoom, u_blur);
  }
  if (u_frost > 0.001) {
    vec2 lo = u_shapes[0].xy;
    vec2 hi = u_shapes[0].xy + u_shapes[0].zw;
    for (int i = 1; i < 8; i++) {
      if (i >= u_shapeCount) break;
      lo = min(lo, u_shapes[i].xy);
      hi = max(hi, u_shapes[i].xy + u_shapes[i].zw);
    }
    vec2 halfSize = (hi - lo) * 0.5;
    float spread = min(${FROST_SPREAD}.0 * px, 0.5 * min(halfSize.x, halfSize.y));
    vec2 at = clamp(basePx + bend + zoom, lo + vec2(spread), max(lo + vec2(spread), hi - vec2(spread)));
    vec3 scattered = blurredBg(at, spread);
    col = mix(col, scattered, u_frost);
  }

  float grey = dot(col, vec3(0.299, 0.587, 0.114));
  col = mix(vec3(grey), col, u_saturation) * u_brightness;
  col = mix(col, u_tint.rgb, u_tint.a);

  vec2 light = normalize(u_lightDir);
  float rim = clamp(1.0 - depth / (1.2 * px), 0.0, 1.0);
  float facing = 0.15 + 0.85 * abs(dot(grad, light));
  float k = rim * facing * u_specular;
  float rimGrey = dot(col, vec3(0.2126, 0.7152, 0.0722));
  vec3 lifted = vec3(rimGrey) + (col - vec3(rimGrey)) * (1.0 + k) + vec3((1.0 - rimGrey) * k);
  vec3 vivid = (vec3(rimGrey) + (col - vec3(rimGrey)) * (1.0 + k)) * (1.0 + k);
  col = clamp(mix(lifted, vivid, u_rimTone), 0.0, 1.0);

  outColor = vec4(col, coverage);
}`;
function compile(gl, type, source) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}
var UNIFORMS = [
  "u_tex",
  "u_lensRect",
  "u_texRect",
  "u_texSize",
  "u_canvasSize",
  "u_shapes",
  "u_shapeRadii",
  "u_shapeCount",
  "u_shapeMode",
  "u_mergeK",
  "u_bevelWidth",
  "u_ior",
  "u_magnify",
  "u_center",
  "u_lightDir",
  "u_displace",
  "u_blur",
  "u_dispersion",
  "u_saturation",
  "u_brightness",
  "u_tint",
  "u_specular",
  "u_frost",
  "u_bevelDepth",
  "u_pxRatio",
  "u_rimTone"
];
function unionRect(rects, margin = 0) {
  let left = Infinity;
  let top = Infinity;
  let right = -Infinity;
  let bottom = -Infinity;
  for (const rect of rects) {
    left = Math.min(left, rect.x);
    top = Math.min(top, rect.y);
    right = Math.max(right, rect.x + rect.width);
    bottom = Math.max(bottom, rect.y + rect.height);
  }
  if (!Number.isFinite(left)) return { x: 0, y: 0, width: 0, height: 0 };
  return {
    x: left - margin,
    y: top - margin,
    width: right - left + margin * 2,
    height: bottom - top + margin * 2
  };
}
var GlRenderer = class _GlRenderer {
  #gl;
  #program;
  #locations;
  #texture = null;
  #width = 0;
  #height = 0;
  #shapeData = new Float32Array(MAX_SHAPES * 4);
  #radiusData = new Float32Array(MAX_SHAPES);
  #contextLost = false;
  #onRestored = null;
  #onLost = null;
  #onContextLost = (event) => {
    event.preventDefault();
    this.#contextLost = true;
    this.#texture = null;
    this.#onLost?.();
  };
  #onContextRestored = () => {
    this.#contextLost = false;
    this.#onRestored?.();
  };
  #buffer = null;
  constructor(gl, program, locations, buffer) {
    this.#gl = gl;
    this.#program = program;
    this.#locations = locations;
    this.#buffer = buffer;
    const canvas = gl.canvas;
    if (canvas instanceof HTMLCanvasElement) {
      canvas.addEventListener("webglcontextlost", this.#onContextLost);
      canvas.addEventListener("webglcontextrestored", this.#onContextRestored);
    }
  }
  get contextLost() {
    return this.#contextLost;
  }
  onContextRestored(cb) {
    this.#onRestored = cb;
  }
  onContextLost(cb) {
    this.#onLost = cb;
  }
  static create(canvas) {
    let gl;
    try {
      gl = canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: false });
    } catch {
      return null;
    }
    if (!gl) return null;
    const vert = compile(gl, gl.VERTEX_SHADER, VERT);
    const frag = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vert || !frag) {
      if (vert) gl.deleteShader(vert);
      if (frag) gl.deleteShader(frag);
      return null;
    }
    const program = gl.createProgram();
    if (!program) {
      gl.deleteShader(vert);
      gl.deleteShader(frag);
      return null;
    }
    gl.attachShader(program, vert);
    gl.attachShader(program, frag);
    gl.linkProgram(program);
    gl.deleteShader(vert);
    gl.deleteShader(frag);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.deleteProgram(program);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
      return null;
    }
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    const locations = /* @__PURE__ */ new Map();
    gl.useProgram(program);
    for (const name of UNIFORMS) {
      locations.set(name, gl.getUniformLocation(program, name));
    }
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    return new _GlRenderer(gl, program, locations, buffer);
  }
  #texW = 1;
  #texH = 1;
  setTexture(source) {
    const gl = this.#gl;
    const sized = source;
    this.#texW = sized.width ?? sized.videoWidth ?? 1;
    this.#texH = sized.height ?? sized.videoHeight ?? 1;
    if (!this.#texture) this.#texture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.#texture);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.generateMipmap(gl.TEXTURE_2D);
  }
  get hasTexture() {
    return this.#texture !== null;
  }
  resize(width, height) {
    if (width === this.#width && height === this.#height) return;
    this.#width = width;
    this.#height = height;
    this.#gl.canvas.width = width;
    this.#gl.canvas.height = height;
    this.#gl.viewport(0, 0, width, height);
  }
  render(draws, texRect) {
    const gl = this.#gl;
    if (this.#contextLost || !this.#texture || this.#width === 0) return;
    gl.useProgram(this.#program);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform1i(this.#locations.get("u_tex") ?? null, 0);
    gl.uniform2f(this.#locations.get("u_canvasSize") ?? null, this.#width, this.#height);
    gl.uniform4f(
      this.#locations.get("u_texRect") ?? null,
      texRect.x,
      texRect.y,
      texRect.width,
      texRect.height
    );
    gl.uniform2f(this.#locations.get("u_texSize") ?? null, this.#texW, this.#texH);
    for (const draw of draws) {
      const { material, quad } = draw;
      const shapes = draw.shapes.slice(0, MAX_SHAPES);
      if (shapes.length === 0) continue;
      this.#shapeData.fill(0);
      this.#radiusData.fill(0);
      shapes.forEach((shape, i) => {
        this.#shapeData[i * 4] = shape.rect.x;
        this.#shapeData[i * 4 + 1] = shape.rect.y;
        this.#shapeData[i * 4 + 2] = shape.rect.width;
        this.#shapeData[i * 4 + 3] = shape.rect.height;
        this.#radiusData[i] = shape.radius;
      });
      const tint = parseTint(material.tint);
      gl.uniform4f(this.#locations.get("u_lensRect") ?? null, quad.x, quad.y, quad.width, quad.height);
      gl.uniform4fv(this.#locations.get("u_shapes") ?? null, this.#shapeData);
      gl.uniform1fv(this.#locations.get("u_shapeRadii") ?? null, this.#radiusData);
      gl.uniform1i(this.#locations.get("u_shapeCount") ?? null, shapes.length);
      gl.uniform1i(this.#locations.get("u_shapeMode") ?? null, material.shape === "squircle" ? 1 : 0);
      gl.uniform1f(this.#locations.get("u_mergeK") ?? null, draw.mergeK);
      gl.uniform1f(
        this.#locations.get("u_bevelWidth") ?? null,
        resolveBandPx(material.bevelWidth, shapes[0]?.radius ?? 0, quad.width, quad.height)
      );
      gl.uniform1f(this.#locations.get("u_ior") ?? null, material.ior);
      gl.uniform1f(this.#locations.get("u_magnify") ?? null, material.magnify);
      gl.uniform2f(
        this.#locations.get("u_center") ?? null,
        quad.x + quad.width / 2,
        quad.y + quad.height / 2
      );
      const light = globalLightDir();
      gl.uniform2f(this.#locations.get("u_lightDir") ?? null, light[0], light[1]);
      gl.uniform1f(this.#locations.get("u_displace") ?? null, material.refraction * 2);
      gl.uniform1f(this.#locations.get("u_blur") ?? null, material.blur);
      gl.uniform1f(this.#locations.get("u_dispersion") ?? null, material.dispersion);
      gl.uniform1f(this.#locations.get("u_saturation") ?? null, material.saturation);
      gl.uniform1f(this.#locations.get("u_brightness") ?? null, material.brightness);
      gl.uniform4f(this.#locations.get("u_tint") ?? null, tint[0], tint[1], tint[2], material.tintOpacity);
      gl.uniform1f(this.#locations.get("u_specular") ?? null, material.specular);
      gl.uniform1f(this.#locations.get("u_frost") ?? null, material.frost);
      gl.uniform1f(this.#locations.get("u_bevelDepth") ?? null, material.bevelDepth);
      gl.uniform1f(this.#locations.get("u_pxRatio") ?? null, draw.pxRatio ?? 1);
      gl.uniform1f(this.#locations.get("u_rimTone") ?? null, draw.rimTone ?? 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
  }
  destroy() {
    const gl = this.#gl;
    const canvas = gl.canvas;
    if (canvas instanceof HTMLCanvasElement) {
      canvas.removeEventListener("webglcontextlost", this.#onContextLost);
      canvas.removeEventListener("webglcontextrestored", this.#onContextRestored);
    }
    this.#onRestored = null;
    this.#onLost = null;
    if (this.#buffer) gl.deleteBuffer(this.#buffer);
    if (this.#texture) gl.deleteTexture(this.#texture);
    gl.deleteProgram(this.#program);
    gl.getExtension("WEBGL_lose_context")?.loseContext();
  }
};
var TINT_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;
var tintCache = /* @__PURE__ */ new Map();
var TINT_CACHE_MAX = 32;
function parseTint(color) {
  const hit = tintCache.get(color);
  if (hit) return hit;
  const parsed = parseTintUncached(color);
  if (tintCache.size >= TINT_CACHE_MAX) {
    const oldest = tintCache.keys().next().value;
    if (oldest !== void 0) tintCache.delete(oldest);
  }
  tintCache.set(color, parsed);
  return parsed;
}
function parseTintUncached(color) {
  const match = TINT_RE.exec(color.trim());
  if (!match || !match[1]) return [1, 1, 1];
  const hex = match[1];
  const size = hex.length === 3 ? 1 : 2;
  const channel = (index) => {
    const part = hex.slice(index * size, index * size + size);
    return parseInt(size === 1 ? part + part : part, 16) / 255;
  };
  return [channel(0), channel(1), channel(2)];
}

// ../core/src/runtime/layout.ts
function collectAncestors(elements, stop) {
  const seen = /* @__PURE__ */ new Set();
  const chain = [];
  for (const element of elements) {
    let node = element.parentElement;
    while (node && node !== stop && node.parentElement) {
      if (!seen.has(node)) {
        seen.add(node);
        chain.push(node);
      }
      node = node.parentElement;
    }
  }
  return chain;
}
var FLOW_CONTAINERS = /* @__PURE__ */ new Set(["block", "flow-root"]);
var BLOCK_LEVEL = /* @__PURE__ */ new Set(["block", "flow-root", "table", "list-item"]);
function usedMarginLeft(node) {
  const parent = node.parentElement;
  if (!parent || typeof getComputedStyle !== "function") return null;
  const computed = getComputedStyle(node);
  if (computed.marginLeft !== "0px") return null;
  if (computed.position === "absolute" || computed.position === "fixed") return null;
  if (computed.float !== "none" && computed.float !== "") return null;
  if (!BLOCK_LEVEL.has(computed.display)) return null;
  const parentStyle = getComputedStyle(parent);
  if (!FLOW_CONTAINERS.has(parentStyle.display)) return null;
  if (parentStyle.direction === "rtl") return null;
  const contentLeft = parent.getBoundingClientRect().left + (parseFloat(parentStyle.borderLeftWidth || "0") || 0) + (parseFloat(parentStyle.paddingLeft || "0") || 0);
  const used = node.getBoundingClientRect().left - contentLeft;
  return used > 0.5 ? used : null;
}
function pinUsedMargins(elements, stop) {
  const pending2 = [];
  for (const node of collectAncestors(elements, stop)) {
    const used = usedMarginLeft(node);
    if (used !== null) pending2.push({ node, left: used, previous: node.style.marginLeft });
  }
  return pending2.map(({ node, left, previous }) => {
    node.style.marginLeft = `${left}px`;
    return () => {
      node.style.marginLeft = previous;
    };
  });
}

// ../core/src/backends/webgl-overlay.ts
var DEFAULT_MERGE_K = 30;
var MAX_SNAPSHOT_SIDE = 4096;
var SNAPSHOT_DENSITY_CAP = 2;
var SCROLL_QUIET_MS = 180;
function isStyleable4(element) {
  return typeof HTMLElement !== "undefined" && element instanceof HTMLElement;
}
function dpr() {
  return Math.min(typeof devicePixelRatio === "number" ? devicePixelRatio : 1, getQuality().maxDpr);
}
var ANCHOR_MARGIN = 72;
var MAX_CANVAS_SIDE = 8192;
function requiredOverlayBox(rects, margin = ANCHOR_MARGIN) {
  const union = unionRect(rects, margin);
  return {
    x: Math.floor(union.x),
    y: Math.floor(union.y),
    width: Math.ceil(union.width),
    height: Math.ceil(union.height)
  };
}
function needsReanchor(current, required) {
  if (!current) return true;
  if (required.x < current.x || required.y < current.y || required.x + required.width > current.x + current.width || required.y + required.height > current.y + current.height) {
    return true;
  }
  const currentArea = current.width * current.height;
  const requiredArea = Math.max(required.width * required.height, 1);
  return currentArea > requiredArea * 2.5;
}
var OverlayManager = class _OverlayManager {
  static #instance = null;
  static acquire() {
    if (_OverlayManager.#instance) return _OverlayManager.#instance;
    if (typeof document === "undefined" || !document.body) return null;
    const canvas = document.createElement("canvas");
    canvas.setAttribute("data-liquid-glass-overlay", "true");
    canvas.setAttribute("aria-hidden", "true");
    const style = canvas.style;
    style.position = "absolute";
    style.left = "0";
    style.top = "0";
    style.pointerEvents = "none";
    style.zIndex = String(getQuality().overlayZIndex);
    style.willChange = "transform";
    document.body.appendChild(canvas);
    const renderer = GlRenderer.create(canvas);
    if (!renderer) {
      canvas.remove();
      return null;
    }
    const manager = new _OverlayManager(canvas, renderer);
    renderer.onContextRestored(() => manager.scheduleSnapshot());
    renderer.onContextLost(() => manager.releaseMaterial());
    _OverlayManager.#instance = manager;
    return manager;
  }
  #canvas;
  #renderer;
  #surfaces = /* @__PURE__ */ new Set();
  #owned = /* @__PURE__ */ new Set();
  #renderFrame = 0;
  #snapshotTimer = null;
  #snapshotting = false;
  #snapshotDirty = false;
  #mutationObserver = null;
  #anchor = null;
  #quietUntil = 0;
  #unwatchViewport = null;
  #onResize = () => {
    this.scheduleRender();
  };
  #onMotionSettled = (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest("[data-liquid-glass], [data-liquid-glass-overlay]")) return;
    if (!this.#touchesSurfaces(target)) return;
    this.scheduleSnapshot();
  };
  constructor(canvas, renderer) {
    this.#canvas = canvas;
    this.#renderer = renderer;
    window.addEventListener("resize", this.#onResize, { passive: true });
    document.addEventListener("transitionend", this.#onMotionSettled, { capture: true, passive: true });
    document.addEventListener("animationend", this.#onMotionSettled, { capture: true, passive: true });
    this.#unwatchViewport = onViewport(() => {
      this.#quietUntil = Date.now() + SCROLL_QUIET_MS;
    });
    if (typeof MutationObserver !== "undefined") {
      this.#mutationObserver = new MutationObserver((records) => {
        for (const record of records) {
          const target = record.target;
          if (target instanceof Element && target.closest("[data-liquid-glass], [data-liquid-glass-overlay]")) {
            continue;
          }
          if (!this.#touchesSurfaces(target)) continue;
          this.scheduleSnapshot();
          return;
        }
      });
      this.#mutationObserver.observe(document.body, {
        childList: true,
        attributes: true,
        characterData: true,
        subtree: true
      });
    }
    const idle = typeof requestIdleCallback === "function" ? requestIdleCallback : (fn) => setTimeout(fn, 180);
    idle(() => {
      if (!this.#destroyed) this.scheduleSnapshot();
    });
  }
  #touchesSurfaces(target) {
    if (!(target instanceof Element)) return true;
    const el2 = target;
    if (typeof el2.getBoundingClientRect !== "function") return true;
    const box = el2.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) return true;
    const reach = 240;
    for (const surface of this.#surfaces) {
      const glass = surface.element.getBoundingClientRect();
      if (box.left < glass.right + reach && box.right > glass.left - reach && box.top < glass.bottom + reach && box.bottom > glass.top - reach) {
        return true;
      }
    }
    return false;
  }
  add(surface) {
    this.#surfaces.add(surface);
    this.scheduleRender();
    this.#syncPoll();
  }
  remove(surface) {
    this.#surfaces.delete(surface);
    this.#owned.delete(surface.element);
    if (this.#surfaces.size === 0) {
      this.#teardown();
      return;
    }
    this.scheduleRender();
    this.#syncPoll();
  }
  #pollFrame = 0;
  #pollSignature = "";
  #needsPoll(surface) {
    if (surface.merge) return true;
    if (typeof getComputedStyle !== "function") return false;
    const computed = getComputedStyle(surface.element);
    if (computed.position === "fixed" || computed.position === "sticky") return true;
    return computed.transform !== "" && computed.transform !== "none";
  }
  #syncPoll() {
    const needsPoll = [...this.#surfaces].some((surface) => this.#needsPoll(surface));
    if (!needsPoll && this.#pollFrame && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this.#pollFrame);
      this.#pollFrame = 0;
      return;
    }
    if (needsPoll && !this.#pollFrame && typeof requestAnimationFrame === "function") {
      const loop = () => {
        this.#pollFrame = 0;
        const polled = [...this.#surfaces].filter((surface) => this.#needsPoll(surface));
        if (polled.length === 0) return;
        let signature = "";
        for (const surface of polled) {
          const box = surface.element.getBoundingClientRect();
          signature += `${box.left.toFixed(1)},${box.top.toFixed(1)},${box.width.toFixed(1)},${box.height.toFixed(1)};`;
        }
        if (signature !== this.#pollSignature) {
          this.#pollSignature = signature;
          this.#render();
        }
        this.#pollFrame = requestAnimationFrame(loop);
      };
      this.#pollFrame = requestAnimationFrame(loop);
    }
  }
  #snapshotDeadline = 0;
  scheduleSnapshot() {
    const throttle = getQuality().snapshotThrottleMs;
    const now2 = Date.now();
    if (now2 < this.#quietUntil) {
      if (this.#snapshotTimer) clearTimeout(this.#snapshotTimer);
      this.#snapshotTimer = setTimeout(() => {
        this.#snapshotTimer = null;
        this.scheduleSnapshot();
      }, this.#quietUntil - now2);
      return;
    }
    if (this.#snapshotDeadline === 0) this.#snapshotDeadline = now2 + throttle * 4;
    if (now2 >= this.#snapshotDeadline) {
      if (this.#snapshotTimer) clearTimeout(this.#snapshotTimer);
      this.#snapshotTimer = null;
      this.#snapshotDeadline = 0;
      void this.#snapshot();
      return;
    }
    if (this.#snapshotTimer) clearTimeout(this.#snapshotTimer);
    this.#snapshotTimer = setTimeout(() => {
      this.#snapshotTimer = null;
      this.#snapshotDeadline = 0;
      void this.#snapshot();
    }, throttle);
  }
  scheduleRender() {
    if (this.#renderFrame || typeof requestAnimationFrame !== "function") return;
    this.#renderFrame = requestAnimationFrame(() => {
      this.#renderFrame = 0;
      this.#render();
    });
  }
  #texBand = null;
  #snapshotBand(pageH) {
    if (typeof window === "undefined") return { y: 0, height: pageH };
    const bodyTop = document.body.getBoundingClientRect().top + window.scrollY;
    let top = Infinity;
    let bottom = -Infinity;
    for (const surface of this.#surfaces) {
      const box = surface.element.getBoundingClientRect();
      if (box.width < 1 || box.height < 1) continue;
      top = Math.min(top, box.top + window.scrollY - bodyTop);
      bottom = Math.max(bottom, box.bottom + window.scrollY - bodyTop);
    }
    if (!Number.isFinite(top)) return { y: 0, height: pageH };
    const margin = Math.max(window.innerHeight, 600);
    const y = Math.max(0, Math.floor(top - margin));
    const height = Math.min(pageH, Math.ceil(bottom + margin)) - y;
    if (height >= pageH * 0.8) return { y: 0, height: pageH };
    return { y, height: Math.max(1, height) };
  }
  async #snapshot() {
    if (this.#snapshotting || this.#destroyed) {
      this.#snapshotDirty = !this.#destroyed;
      return;
    }
    this.#snapshotting = true;
    let restorePins = [];
    try {
      const { toSvg } = await import('./es-HHUKSKAF.js');
      if (this.#destroyed) return;
      const body = document.body;
      const pageW = Math.max(body.scrollWidth, 1);
      const pageH = Math.max(body.scrollHeight, 1);
      const band = this.#snapshotBand(pageH);
      const bandBottom = band.y + band.height;
      const partial = band.height < pageH;
      const scrollYAtStart = window.scrollY;
      const bodyTop = body.getBoundingClientRect().top + scrollYAtStart;
      const scale = Math.min(
        Math.min(dpr(), SNAPSHOT_DENSITY_CAP),
        MAX_SNAPSHOT_SIDE / Math.max(pageW, band.height, 1)
      );
      restorePins = pinUsedMargins(
        [...this.#surfaces].map((surface) => surface.element),
        body
      );
      const svgUrl = await toSvg(body, {
        width: pageW,
        height: pageH,
        filter: (node) => {
          if (!(node instanceof Element)) return true;
          if (node.hasAttribute("data-liquid-glass") || node.hasAttribute("data-liquid-glass-overlay") || node.hasAttribute("data-liquid-glass-ignore")) {
            return false;
          }
          if (!partial || node === body || typeof node.getBoundingClientRect !== "function") {
            return true;
          }
          const box = node.getBoundingClientRect();
          if (box.height === 0 && box.width === 0) return true;
          return box.top + scrollYAtStart - bodyTop < bandBottom;
        }
      });
      if (this.#destroyed) return;
      const image = new Image();
      image.decoding = "async";
      image.src = svgUrl;
      if (typeof image.decode === "function") {
        await image.decode();
      } else {
        await new Promise((resolve, reject) => {
          image.onload = () => resolve();
          image.onerror = () => reject(new Error("snapshot image failed"));
        });
      }
      if (this.#destroyed) return;
      const snapshot = document.createElement("canvas");
      snapshot.width = Math.max(1, Math.round(pageW * scale));
      snapshot.height = Math.max(1, Math.round(band.height * scale));
      const context = snapshot.getContext("2d");
      if (!context) throw new Error("snapshot 2d context unavailable");
      context.scale(scale, scale);
      context.drawImage(image, 0, -band.y);
      this.#texBand = { y: band.y, height: band.height, fullHeight: pageH };
      this.#renderer.setTexture(snapshot);
      const gridIdle = typeof requestIdleCallback === "function" ? requestIdleCallback : (fn) => setTimeout(fn, 120);
      gridIdle(() => {
        if (this.#destroyed) return;
        setLuminanceGrid(buildLuminanceGrid(snapshot, pageW, band.height, 48, bodyTop + band.y));
      });
      this.scheduleRender();
    } catch {
      this.#snapshotDirty = false;
      return;
    } finally {
      for (const restore of restorePins) restore();
      this.#snapshotting = false;
    }
    if (this.#snapshotDirty) {
      this.#snapshotDirty = false;
      this.scheduleSnapshot();
    }
  }
  #render() {
    if (typeof document !== "undefined" && document.hidden) return;
    const scrollX = window.scrollX;
    const scrollY = window.scrollY;
    const draws = [];
    const drawn = [];
    const groups = /* @__PURE__ */ new Map();
    for (const surface of this.#surfaces) {
      const box = surface.element.getBoundingClientRect();
      if (box.width < 1 || box.height < 1) continue;
      drawn.push(surface);
      const shape = {
        rect: {
          x: box.left + scrollX,
          y: box.top + scrollY,
          width: box.width,
          height: box.height
        },
        radius: resolveRadiusPx(surface.material.radius, surface.element, box.width, box.height)
      };
      if (surface.merge) {
        const key = surface.merge;
        const group = groups.get(key);
        const mergeK = surface.mergeStrength ?? DEFAULT_MERGE_K;
        if (group) {
          if (group.shapes.length < MAX_SHAPES) group.shapes.push(shape);
          group.mergeK = Math.max(group.mergeK, mergeK);
        } else {
          groups.set(key, { shapes: [shape], surface, mergeK });
        }
        continue;
      }
      draws.push({
        quad: shape.rect,
        shapes: [shape],
        material: surface.material,
        mergeK: 1,
        rimTone: surface.appearance === "dark" ? 1 : 0
      });
    }
    for (const group of groups.values()) {
      const quad = unionRect(
        group.shapes.map((shape) => shape.rect),
        group.mergeK
      );
      if (quad.width < 1 || quad.height < 1) continue;
      draws.push({
        quad,
        shapes: group.shapes,
        material: group.surface.material,
        mergeK: group.mergeK,
        rimTone: group.surface.appearance === "dark" ? 1 : 0
      });
    }
    if (draws.length === 0) return;
    const required = requiredOverlayBox(draws.map((draw) => draw.quad));
    if (needsReanchor(this.#anchor, required)) {
      this.#anchor = required;
      const style = this.#canvas.style;
      style.width = `${required.width}px`;
      style.height = `${required.height}px`;
      style.transform = `translate(${required.x}px, ${required.y}px)`;
    }
    const anchor = this.#anchor;
    if (!anchor) return;
    const ratio = Math.min(
      dpr(),
      MAX_CANVAS_SIDE / Math.max(anchor.width, anchor.height, 1)
    );
    this.#renderer.resize(Math.round(anchor.width * ratio), Math.round(anchor.height * ratio));
    const toCanvas = (rect) => ({
      x: (rect.x - anchor.x) * ratio,
      y: (rect.y - anchor.y) * ratio,
      width: rect.width * ratio,
      height: rect.height * ratio
    });
    const canvasDraws = draws.map((draw) => ({
      quad: toCanvas(draw.quad),
      shapes: draw.shapes.map((shape) => ({
        rect: toCanvas(shape.rect),
        radius: shape.radius * ratio
      })),
      material: scaleMaterialToDevice(draw.material, {
        radius: draw.shapes[0]?.radius ?? 0,
        width: draw.quad.width,
        height: draw.quad.height,
        ratio
      }),
      pxRatio: ratio,
      mergeK: draw.mergeK * ratio,
      rimTone: draw.rimTone
    }));
    const bodyBox = document.body.getBoundingClientRect();
    const band = this.#texBand;
    if (band && band.height < band.fullHeight) {
      const bodyTop = bodyBox.top + scrollY;
      for (const draw of draws) {
        const top = draw.quad.y - bodyTop;
        if (band.y > 0 && top < band.y + 160 || band.y + band.height < band.fullHeight && top + draw.quad.height > band.y + band.height - 160) {
          this.scheduleSnapshot();
          break;
        }
      }
    }
    const bandScale = band ? bodyBox.height / Math.max(band.fullHeight, 1) : 1;
    const painting = this.#renderer.hasTexture && !this.#renderer.contextLost;
    this.#renderer.render(canvasDraws, {
      x: (bodyBox.left + scrollX - anchor.x) * ratio,
      y: (bodyBox.top + scrollY + (band ? band.y * bandScale : 0) - anchor.y) * ratio,
      width: bodyBox.width * ratio,
      height: (band ? band.height * bandScale : bodyBox.height) * ratio
    });
    if (!painting) return;
    for (const surface of drawn) {
      if (this.#owned.has(surface.element)) continue;
      this.#owned.add(surface.element);
      applyBaseStyles(surface, true);
    }
  }
  owns(surface) {
    return this.#owned.has(surface.element);
  }
  releaseMaterial() {
    for (const surface of this.#surfaces) {
      if (this.#owned.delete(surface.element)) applyBaseStyles(surface, false);
    }
  }
  #destroyed = false;
  #teardown() {
    this.#destroyed = true;
    setLuminanceGrid(null);
    window.removeEventListener("resize", this.#onResize);
    document.removeEventListener("transitionend", this.#onMotionSettled, { capture: true });
    document.removeEventListener("animationend", this.#onMotionSettled, { capture: true });
    this.#unwatchViewport?.();
    this.#unwatchViewport = null;
    this.#mutationObserver?.disconnect();
    this.#mutationObserver = null;
    if (this.#snapshotTimer) clearTimeout(this.#snapshotTimer);
    if (this.#renderFrame && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this.#renderFrame);
    }
    if (this.#pollFrame && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this.#pollFrame);
      this.#pollFrame = 0;
    }
    this.#renderer.destroy();
    this.#canvas.remove();
    if (_OverlayManager.#instance === this) _OverlayManager.#instance = null;
  }
};
function applyBaseStyles(surface, owned) {
  if (!isStyleable4(surface.element)) return;
  const { material } = surface;
  const style = surface.element.style;
  const filter = owned ? "none" : `blur(${material.blur}px) saturate(${material.saturation}) brightness(${material.brightness})`;
  style.setProperty("backdrop-filter", filter);
  style.setProperty("-webkit-backdrop-filter", filter);
  style.setProperty("background", owned ? "transparent" : colorWithOpacity(material.tint, material.tintOpacity));
  if (typeof material.radius === "number") {
    style.setProperty("border-radius", `${material.radius}px`);
  }
  const cast = surface.merge ? "" : glassShadowCss(material.shadow, surface.element.getBoundingClientRect().height);
  if (cast) style.setProperty("box-shadow", cast);
  else style.removeProperty("box-shadow");
  if (typeof getComputedStyle === "function") {
    const computed = getComputedStyle(surface.element);
    if (computed.position === "static") style.setProperty("position", "relative");
    if (computed.zIndex === "auto" || computed.zIndex === "0") {
      style.setProperty("z-index", String(getQuality().overlayZIndex + 1));
    }
  }
}
var TOUCHED4 = [
  "backdrop-filter",
  "-webkit-backdrop-filter",
  "background",
  "border-radius",
  "box-shadow",
  "position",
  "z-index"
];
var webglOverlayBackend = {
  id: "webgl-overlay",
  priority: 10,
  isSupported(capabilities) {
    return capabilities.webgl2;
  },
  mount(surface) {
    const restore = captureInlineStyles(surface.element, TOUCHED4);
    applyBaseStyles(surface, false);
    const manager = OverlayManager.acquire();
    if (!manager) {
      const fallback = {
        update(next) {
          applyBaseStyles(next, false);
        },
        sync() {
        },
        destroy() {
          restore();
        }
      };
      return fallback;
    }
    manager.add(surface);
    let wasVisible = surface.state.visible;
    return {
      update(next) {
        applyBaseStyles(next, manager.owns(next));
        manager.add(next);
      },
      sync(next) {
        if (next.state.visible && !wasVisible) manager.scheduleSnapshot();
        wasVisible = next.state.visible;
        manager.scheduleRender();
      },
      destroy() {
        manager.remove(surface);
        restore();
      }
    };
  }
};

// ../core/src/backends/webgl-scene.ts
var TOUCHED5 = ["background", "border-radius", "box-shadow", "isolation", "position"];
function isStyleable5(element) {
  return typeof HTMLElement !== "undefined" && element instanceof HTMLElement;
}
var SceneGl = class _SceneGl {
  static #shared = null;
  static #clients = 0;
  #canvas;
  #renderer;
  #bound = null;
  constructor(canvas, renderer) {
    this.#canvas = canvas;
    this.#renderer = renderer;
  }
  static acquire() {
    if (!_SceneGl.#shared) {
      if (typeof document === "undefined") return null;
      const canvas = document.createElement("canvas");
      const renderer = GlRenderer.create(canvas);
      if (!renderer) return null;
      _SceneGl.#shared = new _SceneGl(canvas, renderer);
    }
    _SceneGl.#clients += 1;
    return _SceneGl.#shared;
  }
  static release() {
    _SceneGl.#clients = Math.max(0, _SceneGl.#clients - 1);
    if (_SceneGl.#clients > 0 || !_SceneGl.#shared) return;
    _SceneGl.#shared.#renderer.destroy();
    _SceneGl.#shared = null;
  }
  bind(source) {
    if (this.#bound === source) return;
    this.#renderer.setTexture(source);
    this.#bound = source;
  }
  onContextRestored(cb) {
    const previous = this.#restored;
    this.#restored = () => {
      previous?.();
      cb();
    };
    this.#renderer.onContextRestored(() => {
      this.#bound = null;
      this.#restored?.();
    });
  }
  #restored = null;
  paint(width, height, draws, texRect) {
    if (!this.#renderer.hasTexture || this.#renderer.contextLost) return null;
    this.#renderer.resize(width, height);
    this.#renderer.render(draws, texRect);
    return this.#canvas;
  }
};
var WebglSceneInstance = class {
  #canvas;
  #context;
  #gl;
  #image = null;
  #restore;
  #host;
  constructor(surface, host, canvas, gl) {
    this.#host = host;
    this.#canvas = canvas;
    this.#context = canvas.getContext("2d");
    this.#gl = gl;
    this.#restore = captureInlineStyles(host, TOUCHED5);
    this.#applyHostStyles(surface);
    this.#loadImage(surface);
    this.#draw(surface);
  }
  update(surface) {
    this.#applyHostStyles(surface);
    this.#loadImage(surface);
    this.#draw(surface);
  }
  sync(surface) {
    this.#draw(surface);
  }
  destroy() {
    SceneGl.release();
    this.#canvas.remove();
    this.#restore();
  }
  #applyHostStyles(surface) {
    const { material } = surface;
    const style = this.#host.style;
    style.setProperty("background", colorWithOpacity(material.tint, 0));
    if (typeof material.radius === "number") {
      style.setProperty("border-radius", `${material.radius}px`);
    }
    const cast = glassShadowCss(material.shadow, this.#host.getBoundingClientRect().height);
    if (cast) style.setProperty("box-shadow", cast);
    else style.removeProperty("box-shadow");
    style.setProperty("isolation", "isolate");
    if (typeof getComputedStyle === "function" && getComputedStyle(this.#host).position === "static") {
      style.setProperty("position", "relative");
    }
  }
  #loadImage(surface) {
    const src = surface.sceneImage;
    if (!src || this.#image?.src === src) return;
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => {
      this.#draw(surface);
    };
    image.src = src;
    this.#image = image;
  }
  #draw(surface) {
    const dpr2 = Math.min(
      typeof devicePixelRatio === "number" ? devicePixelRatio : 1,
      getQuality(surface.quality).maxDpr
    );
    const hostBox = this.#host.getBoundingClientRect();
    if (hostBox.width < 1 || hostBox.height < 1) return;
    const image = this.#image;
    if (!image || !image.complete || image.naturalWidth === 0) return;
    this.#gl.bind(image);
    const width = Math.round(hostBox.width * dpr2);
    const height = Math.round(hostBox.height * dpr2);
    const reference = surface.backdrop ?? this.#host;
    const refBox = reference.getBoundingClientRect();
    const quad = { x: 0, y: 0, width: hostBox.width * dpr2, height: hostBox.height * dpr2 };
    const radius = resolveRadiusPx(
      surface.material.radius,
      surface.element,
      hostBox.width,
      hostBox.height
    );
    const painted = this.#gl.paint(
      width,
      height,
      [
        {
          quad,
          shapes: [{ rect: quad, radius: radius * dpr2 }],
          material: scaleMaterialToDevice(surface.material, {
            radius,
            width: hostBox.width,
            height: hostBox.height,
            ratio: dpr2
          }),
          pxRatio: dpr2,
          mergeK: 1,
          rimTone: surface.appearance === "dark" ? 1 : 0
        }
      ],
      {
        x: (refBox.left - hostBox.left) * dpr2,
        y: (refBox.top - hostBox.top) * dpr2,
        width: refBox.width * dpr2,
        height: refBox.height * dpr2
      }
    );
    if (!painted || !this.#context) return;
    this.#canvas.width = width;
    this.#canvas.height = height;
    this.#context.clearRect(0, 0, width, height);
    this.#context.drawImage(painted, 0, 0);
  }
};
var webglSceneBackend = {
  id: "webgl-scene",
  priority: 5,
  autoSelect: false,
  isSupported(capabilities) {
    return capabilities.webgl2;
  },
  mount(surface) {
    if (!isStyleable5(surface.element)) {
      return { update() {
      }, sync() {
      }, destroy() {
      } };
    }
    const canvas = document.createElement("canvas");
    canvas.setAttribute("data-liquid-glass-layer", "scene");
    canvas.setAttribute("aria-hidden", "true");
    const style = canvas.style;
    style.position = "absolute";
    style.inset = "0";
    style.width = "100%";
    style.height = "100%";
    style.zIndex = "-1";
    style.pointerEvents = "none";
    style.borderRadius = "inherit";
    const gl = SceneGl.acquire();
    if (!gl) {
      return { update() {
      }, sync() {
      }, destroy() {
      } };
    }
    surface.element.insertBefore(canvas, surface.element.firstChild);
    const instance = new WebglSceneInstance(surface, surface.element, canvas, gl);
    gl.onContextRestored(() => instance.update(surface));
    return {
      update(next) {
        instance.update(next);
      },
      sync(next) {
        instance.sync(next);
      },
      destroy() {
        instance.destroy();
      }
    };
  }
};

// ../core/src/backends/registry.ts
var backends = /* @__PURE__ */ new Map();
var builtinsReady = false;
function ensureBuiltinBackends() {
  if (builtinsReady) return;
  builtinsReady = true;
  const builtins = [
    cssFallbackBackend,
    cssSvgBackend,
    svgContentBackend,
    webglSceneBackend,
    webglOverlayBackend
  ];
  for (const backend of builtins) {
    if (!backends.has(backend.id)) backends.set(backend.id, backend);
  }
}
function registerBackend(backend) {
  ensureBuiltinBackends();
  backends.set(backend.id, backend);
}
function getBackend(id) {
  ensureBuiltinBackends();
  return backends.get(id);
}
function listBackends() {
  ensureBuiltinBackends();
  return [...backends.values()].sort((a, b) => b.priority - a.priority);
}
function selectBackend(capabilities, preferred) {
  ensureBuiltinBackends();
  if (preferred !== "auto") {
    const exact = backends.get(preferred);
    if (exact && exact.isSupported(capabilities)) return exact;
  }
  for (const backend of listBackends()) {
    if (backend.autoSelect === false) continue;
    if (backend.isSupported(capabilities)) return backend;
  }
  throw new Error("liquidglass: no supported backend registered");
}

// ../core/src/runtime/events.ts
function createEmitter() {
  const listeners = /* @__PURE__ */ new Map();
  return {
    on(event, cb) {
      const bucket2 = listeners.get(event) ?? /* @__PURE__ */ new Set();
      listeners.set(event, bucket2);
      bucket2.add(cb);
      return () => {
        bucket2.delete(cb);
      };
    },
    emit(event, detail) {
      const bucket2 = listeners.get(event);
      if (!bucket2) return;
      for (const cb of [...bucket2]) {
        try {
          ;
          cb(detail);
        } catch {
          continue;
        }
      }
    },
    clear() {
      listeners.clear();
    }
  };
}

// ../core/src/runtime/dom-sync.ts
var OFFSCREEN_MARGIN = "200px";
var SurfaceTracker = class {
  #element;
  #listener;
  #resizeObserver = null;
  #intersectionObserver = null;
  #offViewport = null;
  #running = false;
  #state = { rect: { x: 0, y: 0, width: 0, height: 0 }, visible: true };
  constructor(element, listener) {
    this.#element = element;
    this.#listener = listener;
  }
  get state() {
    return this.#state;
  }
  start() {
    if (this.#running || typeof window === "undefined") return;
    this.#running = true;
    if (typeof ResizeObserver !== "undefined") {
      this.#resizeObserver = new ResizeObserver(() => this.#measure());
      this.#resizeObserver.observe(this.#element);
    }
    if (typeof IntersectionObserver !== "undefined") {
      this.#intersectionObserver = new IntersectionObserver(
        (entries) => {
          const entry = entries[entries.length - 1];
          if (!entry) return;
          const visible = entry.isIntersecting;
          const appeared = visible && !this.#state.visible;
          this.#state = { ...this.#state, visible };
          if (appeared) this.#readRect();
          this.#listener(this.#state);
        },
        { rootMargin: OFFSCREEN_MARGIN }
      );
      this.#intersectionObserver.observe(this.#element);
    }
    this.#offViewport = onViewport(() => {
      if (this.#state.visible) this.#measure();
    });
    this.#measure();
  }
  stop() {
    if (!this.#running) return;
    this.#running = false;
    this.#resizeObserver?.disconnect();
    this.#resizeObserver = null;
    this.#intersectionObserver?.disconnect();
    this.#intersectionObserver = null;
    this.#offViewport?.();
    this.#offViewport = null;
  }
  #measure() {
    if (this.#readRect()) this.#listener(this.#state);
  }
  #readRect() {
    const box = this.#element.getBoundingClientRect();
    const previous = this.#state.rect;
    if (box.x === previous.x && box.y === previous.y && box.width === previous.width && box.height === previous.height) {
      return false;
    }
    this.#state = {
      ...this.#state,
      rect: { x: box.x, y: box.y, width: box.width, height: box.height }
    };
    return true;
  }
};

// ../core/src/physics/spring.ts
var Spring = class {
  value;
  velocity = 0;
  target;
  stiffness;
  damping;
  mass;
  constructor(value, config) {
    this.value = value;
    this.target = value;
    this.stiffness = config.stiffness;
    this.damping = config.damping;
    this.mass = config.mass;
  }
  configure(config) {
    if (config.stiffness !== void 0) this.stiffness = config.stiffness;
    if (config.damping !== void 0) this.damping = config.damping;
    if (config.mass !== void 0) this.mass = config.mass;
  }
  get settled() {
    return Math.abs(this.value - this.target) < 5e-4 && Math.abs(this.velocity) < 5e-3;
  }
  step(dt) {
    const displacement = this.value - this.target;
    const force = -this.stiffness * displacement - this.damping * this.velocity;
    this.velocity += force / this.mass * dt;
    this.value += this.velocity * dt;
    if (this.settled) {
      this.value = this.target;
      this.velocity = 0;
      return false;
    }
    return true;
  }
};

// ../core/src/physics/controller.ts
var PHYSICS_DEFAULTS = {
  press: true,
  hover: true,
  wobble: 0.6,
  stretch: 0.6
};
function resolvePhysics(option) {
  if (option === false) return null;
  if (option === true || option === void 0) return { ...PHYSICS_DEFAULTS };
  return { ...PHYSICS_DEFAULTS, ...option };
}
var PRESS_SPRING = { stiffness: 550, damping: 30, mass: 1 };
var STRETCH_SPRING = { stiffness: 260, damping: 22, mass: 1 };
var STRETCH_REFERENCE_SPEED = 1600;
var STRETCH_LIMIT = 0.18;
var STRETCH_DECAY = 9;
var HOVER_SPRING = { stiffness: 220, damping: 18, mass: 1 };
var MAGNET_RATIO = 0.05;
var PhysicsController = class {
  #element;
  #config;
  #base;
  #hadInlineTransform;
  #restore;
  #scaleX;
  #scaleY;
  #tx;
  #ty;
  #stretchX;
  #stretchY;
  #lastX = 0;
  #lastY = 0;
  #lastViewX = 0;
  #lastViewY = 0;
  #seen = false;
  #speed = 0;
  #alongX = true;
  #offFrame = null;
  #onDown = (event) => {
    if (!this.#config.press) return;
    this.#configureScale(PRESS_SPRING.stiffness, PRESS_SPRING.damping);
    this.#scaleX.target = 1.045;
    this.#scaleY.target = 1.045;
    const box = this.#element.getBoundingClientRect();
    this.#hooks?.onPress?.(event.clientX - box.left, event.clientY - box.top);
    this.#pressed = true;
    this.#wake();
  };
  #onUp = () => {
    if (!this.#config.press) return;
    if (this.#pressed) {
      this.#pressed = false;
      this.#hooks?.onRelease?.();
    }
    const damping = 8 + (1 - this.#config.wobble) * 20;
    this.#configureScale(300, damping);
    this.#scaleX.target = 1;
    this.#scaleY.target = 1;
    this.#wake();
  };
  #pointerX = 0;
  #pointerY = 0;
  #magnetFrame = 0;
  #onMove = (event) => {
    if (!this.#config.hover) return;
    this.#pointerX = event.clientX;
    this.#pointerY = event.clientY;
    if (this.#magnetFrame) return;
    this.#aimMagnet();
    if (typeof requestAnimationFrame !== "function") return;
    this.#magnetFrame = requestAnimationFrame(() => {
      this.#magnetFrame = 0;
      this.#aimMagnet();
    });
  };
  #aimMagnet() {
    const box = this.#element.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) return;
    const dx = this.#pointerX - (box.left + box.width / 2);
    const dy = this.#pointerY - (box.top + box.height / 2);
    this.#tx.target = dx * MAGNET_RATIO;
    this.#ty.target = dy * MAGNET_RATIO;
    this.#wake();
  }
  #onLeave = () => {
    this.#tx.target = 0;
    this.#ty.target = 0;
    this.#onUp();
    this.#wake();
  };
  #hooks;
  #pressed = false;
  constructor(element, config, hooks) {
    this.#element = element;
    this.#config = config;
    this.#hooks = hooks;
    this.#hadInlineTransform = element.style.transform !== "";
    this.#restore = captureInlineStyles(element, ["transform", "display"]);
    const computed = typeof getComputedStyle === "function" ? getComputedStyle(element) : null;
    this.#base = computed && computed.transform !== "none" ? computed.transform : "";
    if (computed && computed.display === "inline") {
      element.style.display = "inline-block";
    }
    this.#scaleX = new Spring(1, PRESS_SPRING);
    this.#scaleY = new Spring(1, PRESS_SPRING);
    this.#tx = new Spring(0, HOVER_SPRING);
    this.#ty = new Spring(0, HOVER_SPRING);
    this.#stretchX = new Spring(1, STRETCH_SPRING);
    this.#stretchY = new Spring(1, STRETCH_SPRING);
    element.addEventListener("pointerdown", this.#onDown);
    element.addEventListener("pointerup", this.#onUp);
    element.addEventListener("pointercancel", this.#onUp);
    element.addEventListener("pointermove", this.#onMove);
    element.addEventListener("pointerleave", this.#onLeave);
  }
  /**
   * Feeds the surface's own position so travel can elongate it. Pass both the page-space
   * and viewport-space coordinates: travel is the smaller of the two motions per axis, so
   * a scroll — which moves an element in exactly one of those spaces — never reads as travel.
   */
  travelled(x, y, dt, viewX = x, viewY = y) {
    if (this.#config.stretch <= 0) return;
    if (!this.#seen) {
      this.#seen = true;
      this.#lastX = x;
      this.#lastY = y;
      this.#lastViewX = viewX;
      this.#lastViewY = viewY;
      return;
    }
    const pageDx = x - this.#lastX;
    const pageDy = y - this.#lastY;
    const viewDx = viewX - this.#lastViewX;
    const viewDy = viewY - this.#lastViewY;
    const dx = Math.abs(pageDx) <= Math.abs(viewDx) ? pageDx : viewDx;
    const dy = Math.abs(pageDy) <= Math.abs(viewDy) ? pageDy : viewDy;
    this.#lastX = x;
    this.#lastY = y;
    this.#lastViewX = viewX;
    this.#lastViewY = viewY;
    const step = Math.max(dt, 1 / 240);
    const speed = Math.hypot(dx, dy) / step;
    this.#speed = (this.#speed + speed) / 2;
    if (speed >= 1) this.#alongX = Math.abs(dx) >= Math.abs(dy);
    this.#wake();
  }
  tick(dt) {
    const clamped = Math.min(dt, 1 / 30);
    if (this.#config.stretch > 0) {
      this.#speed *= Math.exp(-clamped * STRETCH_DECAY);
      if (this.#speed < 1) this.#speed = 0;
      const amount = Math.min(this.#speed / STRETCH_REFERENCE_SPEED, 1) * STRETCH_LIMIT * this.#config.stretch;
      this.#stretchX.target = this.#alongX ? 1 + amount : 1 - amount * 0.6;
      this.#stretchY.target = this.#alongX ? 1 - amount * 0.6 : 1 + amount;
    }
    let active = false;
    active = this.#scaleX.step(clamped) || active;
    active = this.#scaleY.step(clamped) || active;
    active = this.#tx.step(clamped) || active;
    active = this.#ty.step(clamped) || active;
    active = this.#stretchX.step(clamped) || active;
    active = this.#stretchY.step(clamped) || active;
    this.#apply(active);
    return active || this.#speed > 0;
  }
  destroy() {
    const element = this.#element;
    element.removeEventListener("pointerdown", this.#onDown);
    element.removeEventListener("pointerup", this.#onUp);
    element.removeEventListener("pointercancel", this.#onUp);
    element.removeEventListener("pointermove", this.#onMove);
    element.removeEventListener("pointerleave", this.#onLeave);
    if (this.#magnetFrame && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(this.#magnetFrame);
      this.#magnetFrame = 0;
    }
    this.#offFrame?.();
    this.#offFrame = null;
    this.#restore();
  }
  #configureScale(stiffness, damping) {
    this.#scaleX.configure({ stiffness, damping });
    this.#scaleY.configure({ stiffness, damping });
  }
  #apply(active) {
    if (!active && !this.#hadInlineTransform && this.#isIdentity()) {
      this.#element.style.removeProperty("transform");
      return;
    }
    const sx = this.#scaleX.value * this.#stretchX.value;
    const sy = this.#scaleY.value * this.#stretchY.value;
    const transform = `${this.#base} translate3d(${this.#tx.value.toFixed(3)}px, ${this.#ty.value.toFixed(3)}px, 0) scale(${sx.toFixed(4)}, ${sy.toFixed(4)})`;
    this.#element.style.transform = transform.trim();
  }
  #isIdentity() {
    return Math.abs(this.#scaleX.value - 1) < 1e-3 && Math.abs(this.#scaleY.value - 1) < 1e-3 && Math.abs(this.#stretchX.value - 1) < 1e-3 && Math.abs(this.#stretchY.value - 1) < 1e-3 && Math.abs(this.#tx.value) < 0.05 && Math.abs(this.#ty.value) < 0.05;
  }
  #wake() {
    if (this.#offFrame) return;
    this.#offFrame = onFrame((dt) => {
      if (!this.tick(dt)) {
        this.#offFrame?.();
        this.#offFrame = null;
      }
    });
  }
};

// ../core/src/quality/probe.ts
var NO_CAPABILITIES = {
  backdropFilter: false,
  backdropFilterUrl: false,
  svgFilterOnContent: false,
  webgl2: false,
  webgpu: false,
  htmlInCanvas: false,
  reducedMotion: false,
  reducedTransparency: false
};
var cached = null;
function supports(property, value) {
  return typeof CSS !== "undefined" && typeof CSS.supports === "function" && CSS.supports(property, value);
}
function media(query) {
  return typeof matchMedia === "function" && matchMedia(query).matches;
}
function detectWebgl2() {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 1;
    canvas.height = 1;
    const gl = canvas.getContext("webgl2");
    if (!gl) return false;
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    return true;
  } catch {
    return false;
  }
}
function probeCapabilities(force = false) {
  if (cached && !force) return cached;
  if (typeof window === "undefined" || typeof document === "undefined") {
    return NO_CAPABILITIES;
  }
  const backdropFilter = supports("backdrop-filter", "blur(1px)") || supports("-webkit-backdrop-filter", "blur(1px)");
  const isBlink = typeof navigator !== "undefined" && ("userAgentData" in navigator || /chrom(e|ium)/i.test(navigator.userAgent));
  cached = {
    backdropFilter,
    backdropFilterUrl: backdropFilter && isBlink && supports("backdrop-filter", "url(#lg)"),
    svgFilterOnContent: supports("filter", "url(#lg)"),
    webgl2: detectWebgl2(),
    webgpu: typeof navigator !== "undefined" && "gpu" in navigator,
    htmlInCanvas: false,
    reducedMotion: media("(prefers-reduced-motion: reduce)"),
    reducedTransparency: media("(prefers-reduced-transparency: reduce)")
  };
  return cached;
}
function resetCapabilitiesCache() {
  cached = null;
}

// ../core/src/engine.ts
var instances = /* @__PURE__ */ new WeakMap();
var TONE_SAMPLE_INTERVAL_MS = 250;
function samePhysicsOption(a, b) {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) return false;
  return bKeys.every(
    (key) => a[key] === b[key]
  );
}
function resolveBackdrop(backdrop) {
  if (!backdrop) return null;
  if (typeof backdrop === "string") {
    return typeof document === "undefined" ? null : document.querySelector(backdrop);
  }
  return backdrop;
}
function createPhysics(element, options, reducedMotion2, hooks) {
  if (reducedMotion2 || options.effects === false) return null;
  if (typeof HTMLElement === "undefined" || !(element instanceof HTMLElement)) return null;
  const config = resolvePhysics(options.physics);
  if (!config) return null;
  const explicitHover = typeof options.physics === "object" && options.physics !== null && "hover" in options.physics;
  if (config.hover && !explicitHover && typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches) {
    config.hover = false;
  }
  return new PhysicsController(element, config, hooks);
}
function degradeTarget(capabilities) {
  const cssSvg = getBackend("css-svg");
  if (cssSvg?.isSupported(capabilities)) return cssSvg;
  return cssFallbackBackend;
}
var degradeTargets = /* @__PURE__ */ new Set();
var cheapenTargets = /* @__PURE__ */ new Set();
var warnedAboutMerge = false;
var watchdogArmed = false;
var globallyDegraded = false;
var stopWatchdog = null;
function releaseWatchdog() {
  stopWatchdog?.();
  stopWatchdog = null;
  watchdogArmed = false;
}
function attach(element, options = {}) {
  const existing = instances.get(element);
  if (existing) {
    existing.set(options);
    return existing;
  }
  let destroyed = false;
  let current = { ...options };
  let pressed = false;
  const capabilities = probeCapabilities();
  let reducedMotion2 = readReducedMotion();
  const pickBackend = () => {
    if (current.effects === false) return inertBackend;
    const preference = current.backend ?? "auto";
    if (preference === "auto" && current.merge && !globallyDegraded) {
      const overlay = getBackend("webgl-overlay");
      if (overlay?.isSupported(capabilities)) return overlay;
    }
    const selected = selectBackend(capabilities, preference);
    if (globallyDegraded && preference === "auto" && selected.id === "webgl-overlay") {
      return degradeTarget(capabilities);
    }
    return selected;
  };
  let backend = pickBackend();
  const emitter = createEmitter();
  let tone = null;
  let frost = null;
  let shownTone = null;
  let toneWritten = false;
  let lastToneSample = 0;
  const surface = {
    element,
    preset: current.preset ?? "clear",
    material: resolveMaterial(current),
    state: { rect: { x: 0, y: 0, width: 0, height: 0 }, visible: true },
    backdrop: resolveBackdrop(current.backdrop),
    sceneImage: current.sceneImage ?? null,
    merge: current.merge ?? null,
    mergeStrength: current.mergeStrength ?? null,
    quality: current.quality ?? null
  };
  const applyMaterial = () => {
    const previousShown = shownTone;
    let material = resolveMaterial(current);
    if (readReducedTransparency() || readForcedColors()) {
      material = applyReducedTransparency(material);
    }
    if (pressed) {
      material = {
        ...material,
        refraction: material.refraction * 0.82,
        specular: Math.min(1, material.specular * 1.3)
      };
    }
    if (current.adaptive !== false) {
      let surroundLuminance = null;
      const painted = observeTone(element, surface.backdrop);
      if (painted === "light" || painted === "dark") {
        tone = painted;
      } else {
        const box = element.getBoundingClientRect();
        const luminance = backdropLuminance({
          left: box.left + (typeof window === "undefined" ? 0 : window.scrollX),
          top: box.top + (typeof window === "undefined" ? 0 : window.scrollY),
          width: box.width,
          height: box.height
        });
        if (luminance !== null) {
          if (tone === null || Math.abs(luminance - TONE_CROSSOVER) >= 0.04) {
            tone = luminance > TONE_CROSSOVER ? "light" : "dark";
          }
          const margin = Math.min(box.width, box.height);
          surroundLuminance = backdropLuminance({
            left: box.left - margin + (typeof window === "undefined" ? 0 : window.scrollX),
            top: box.top - margin + (typeof window === "undefined" ? 0 : window.scrollY),
            width: box.width + margin * 2,
            height: box.height + margin * 2
          }) ?? luminance;
        } else {
          tone = painted === "unpainted" ? "light" : null;
        }
      }
      if (painted === "light" || painted === "dark") surroundLuminance = painted === "dark" ? 0 : 1;
      frost = frostTone(readAppearance(element), surroundLuminance, frost);
      if (current.tint === void 0) {
        material = adaptMaterial(material, current.preset ?? "clear", frost, current);
      }
    } else {
      tone = null;
    }
    surface.material = material;
    surface.appearance = readAppearance(element);
    const materialTone = current.adaptive !== false && current.preset === "frosted" && current.tint === void 0;
    shownTone = materialTone ? frost : tone;
    if (shownTone !== previousShown) emitter.emit("tonechange", shownTone);
    if (shownTone !== previousShown || !toneWritten) {
      toneWritten = true;
      const styled = element instanceof HTMLElement ? element : null;
      if (shownTone) {
        element.setAttribute("data-liquid-glass-tone", shownTone);
        styled?.style.setProperty("--lg-on-glass", shownTone === "light" ? "#1d1d1f" : "#f5f5f7");
      } else {
        element.removeAttribute("data-liquid-glass-tone");
        styled?.style.removeProperty("--lg-on-glass");
      }
    }
  };
  applyMaterial();
  const markElement = () => {
    element.setAttribute("data-liquid-glass", surface.preset);
    element.setAttribute("data-liquid-glass-backend", backend.id);
  };
  markElement();
  let instance = backend.mount(surface);
  let glow = null;
  const pressHooks = {
    onPress(x, y) {
      pressed = true;
      emitter.emit("press", { x, y });
      element.setAttribute("data-liquid-glass-pressed", "true");
      applyMaterial();
      instance.update(surface);
      if (!glow && typeof HTMLElement !== "undefined" && element instanceof HTMLElement) {
        glow = mountGlow(element);
      }
      glow?.press(x, y);
    },
    onRelease() {
      pressed = false;
      emitter.emit("release", null);
      element.removeAttribute("data-liquid-glass-pressed");
      applyMaterial();
      instance.update(surface);
      glow?.release();
    }
  };
  let physics = createPhysics(element, current, reducedMotion2, pressHooks);
  let bezel = null;
  let bezelSpecular = -1;
  let bezelMotion = null;
  let bezelGl = null;
  let releaseLight = null;
  const syncBezel = () => {
    const styleable = typeof HTMLElement !== "undefined" && element instanceof HTMLElement;
    const wanted = styleable && current.effects !== false && surface.material.specular > 0;
    if (!wanted) {
      releaseLight?.();
      releaseLight = null;
      bezel?.destroy();
      bezel = null;
      bezelSpecular = -1;
      bezelMotion = null;
      return;
    }
    const motion = !reducedMotion2 && current.motionLight === true;
    const glBackend = backend.id === "webgl-overlay" || backend.id === "webgl-scene";
    if (surface.material.specular === bezelSpecular && motion === bezelMotion && glBackend === bezelGl) return;
    releaseLight?.();
    releaseLight = null;
    bezel?.destroy();
    const host = element;
    bezel = glBackend ? null : mountBezel(host, surface.material.specular);
    bezelSpecular = surface.material.specular;
    bezelMotion = motion;
    bezelGl = glBackend;
    if (!reducedMotion2) {
      releaseLight = registerLight({
        host,
        motion,
        update: (angle) => bezel?.update(angle)
      });
    }
  };
  syncBezel();
  let wasVisible = false;
  let lastTravel = 0;
  const tracker = new SurfaceTracker(element, (state) => {
    const appeared = state.visible && !wasVisible;
    wasVisible = state.visible;
    surface.state = state;
    if (physics && state.visible) {
      const stamp = frameNow();
      const pageX = state.rect.x + (typeof window === "undefined" ? 0 : window.scrollX);
      const pageY = state.rect.y + (typeof window === "undefined" ? 0 : window.scrollY);
      physics.travelled(
        pageX,
        pageY,
        lastTravel ? (stamp - lastTravel) / 1e3 : 0,
        state.rect.x,
        state.rect.y
      );
      lastTravel = stamp;
    }
    if (current.adaptive !== false) {
      const now2 = Date.now();
      if (appeared || now2 - lastToneSample > TONE_SAMPLE_INTERVAL_MS) {
        lastToneSample = now2;
        const previousTone = tone;
        applyMaterial();
        if (tone !== previousTone) {
          instance.update(surface);
        }
      }
    }
    instance.sync(surface);
  });
  tracker.start();
  const applyDegrade = () => {
    if ((current.backend ?? "auto") !== "auto") return;
    if (backend.id !== "webgl-overlay") return;
    const replacement = degradeTarget(capabilities);
    if (replacement.id === backend.id) return;
    instance.destroy();
    backend = replacement;
    instance = backend.mount(surface);
    element.setAttribute("data-liquid-glass-degraded", "true");
    markElement();
    emitter.emit("degrade", backend.id);
    emitter.emit("backendchange", backend.id);
  };
  const applyCheaperQuality = () => {
    instance.update(surface);
    emitter.emit("degrade", backend.id);
  };
  degradeTargets.add(applyDegrade);
  cheapenTargets.add(applyCheaperQuality);
  const armWatchdog = () => {
    if (watchdogArmed || typeof window === "undefined") return;
    if ((current.backend ?? "auto") !== "auto") return;
    watchdogArmed = true;
    stopWatchdog = watchFps(() => {
      globallyDegraded = true;
      stopWatchdog = null;
      watchdogArmed = false;
      configure({ caPasses: 1 });
      for (const fn of [...cheapenTargets]) fn();
      for (const fn of [...degradeTargets]) fn();
    });
  };
  armWatchdog();
  const warnUnmergeable = () => {
    if (!current.merge || backend.id === "webgl-overlay" || warnedAboutMerge) return;
    warnedAboutMerge = true;
    console.warn(
      `liquidglass: the "${backend.id}" backend cannot merge lenses; the merge group is ignored. Use backend: 'webgl-overlay' or wrap the lenses in <liquid-glass-group>.`
    );
  };
  warnUnmergeable();
  const retoneFromBackdrop = () => {
    if (current.adaptive === false) return;
    const previousTone = tone;
    const previousFrost = frost;
    lastToneSample = Date.now();
    applyMaterial();
    if (tone !== previousTone || frost !== previousFrost) instance.update(surface);
  };
  let appearance = readAppearance(element);
  const unsubscribers = [
    onLuminanceGrid(retoneFromBackdrop),
    watchAppearance(() => {
      const next = readAppearance(element);
      if (next === appearance) return;
      appearance = next;
      retoneFromBackdrop();
    }),
    watchMedia("(prefers-reduced-motion: reduce)", (matches) => {
      reducedMotion2 = matches;
      physics?.destroy();
      physics = createPhysics(element, current, reducedMotion2, pressHooks);
      syncBezel();
    }),
    watchMedia("(prefers-reduced-transparency: reduce)", () => {
      applyMaterial();
      instance.update(surface);
    }),
    watchMedia("(forced-colors: active)", () => {
      applyMaterial();
      instance.update(surface);
    })
  ];
  const handle = {
    element,
    get backend() {
      return backend.id;
    },
    get options() {
      return { ...current };
    },
    on(event, cb) {
      return emitter.on(event, cb);
    },
    set(next) {
      const previousPhysics = current.physics;
      current = { ...current, ...next };
      const merged = current;
      for (const key of Object.keys(merged)) {
        if (merged[key] === void 0) delete merged[key];
      }
      surface.preset = current.preset ?? "clear";
      surface.backdrop = resolveBackdrop(current.backdrop);
      surface.sceneImage = current.sceneImage ?? null;
      surface.merge = current.merge ?? null;
      surface.mergeStrength = current.mergeStrength ?? null;
      surface.quality = current.quality ?? null;
      applyMaterial();
      const replacement = pickBackend();
      if (replacement.id !== backend.id) {
        instance.destroy();
        backend = replacement;
        instance = backend.mount(surface);
        emitter.emit("backendchange", backend.id);
      }
      if ("physics" in next && !samePhysicsOption(previousPhysics, current.physics)) {
        physics?.destroy();
        physics = createPhysics(element, current, reducedMotion2, pressHooks);
      }
      instance.update(surface);
      syncBezel();
      markElement();
      armWatchdog();
      warnUnmergeable();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      if (pressed) {
        pressed = false;
        emitter.emit("release", null);
      }
      tracker.stop();
      degradeTargets.delete(applyDegrade);
      cheapenTargets.delete(applyCheaperQuality);
      if (degradeTargets.size === 0) releaseWatchdog();
      for (const unsubscribe of unsubscribers) unsubscribe();
      physics?.destroy();
      physics = null;
      releaseLight?.();
      releaseLight = null;
      glow?.destroy();
      glow = null;
      bezel?.destroy();
      bezel = null;
      instance.destroy();
      instances.delete(element);
      emitter.clear();
      element.removeAttribute("data-liquid-glass-pressed");
      element.removeAttribute("data-liquid-glass");
      element.removeAttribute("data-liquid-glass-backend");
      element.removeAttribute("data-liquid-glass-tone");
      element.removeAttribute("data-liquid-glass-degraded");
    }
  };
  instances.set(element, handle);
  return handle;
}
function getInstance(element) {
  return instances.get(element);
}
function detach(element) {
  instances.get(element)?.destroy();
}

// ../core/src/auto.ts
var AUTO_ATTR = "data-liquid-glass-auto";
function parseOptions(value) {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed;
    }
    return {};
  } catch {
    return {};
  }
}
function collect(root) {
  const found = [];
  if (root instanceof Element && root.hasAttribute(AUTO_ATTR)) found.push(root);
  found.push(...root.querySelectorAll(`[${AUTO_ATTR}]`));
  return found;
}
function autoAttach(root) {
  if (typeof document === "undefined") return () => {
  };
  const scope = root ?? document;
  const attached = /* @__PURE__ */ new Set();
  const mount = (el2) => {
    if (attached.has(el2)) return;
    try {
      attach(el2, parseOptions(el2.getAttribute(AUTO_ATTR)));
      attached.add(el2);
    } catch (error) {
      console.warn("liquidglass: autoAttach skipped an element", el2, error);
    }
  };
  const unmount = (el2) => {
    if (!attached.has(el2)) return;
    getInstance(el2)?.destroy();
    attached.delete(el2);
  };
  for (const el2 of collect(scope)) mount(el2);
  let observer = null;
  if (typeof MutationObserver !== "undefined") {
    observer = new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node instanceof Element) {
            for (const el2 of collect(node)) mount(el2);
          }
        }
        for (const node of record.removedNodes) {
          if (!(node instanceof Element)) continue;
          if (attached.has(node)) unmount(node);
          if (attached.size === 0) continue;
          const stale = [];
          for (const el2 of attached) {
            if (!el2.isConnected) stale.push(el2);
          }
          for (const el2 of stale) unmount(el2);
        }
      }
    });
    observer.observe(scope instanceof Document ? scope.documentElement : scope, {
      childList: true,
      subtree: true
    });
  }
  return () => {
    observer?.disconnect();
    observer = null;
    for (const el2 of [...attached]) unmount(el2);
  };
}

// ../core/src/options.ts
var OPTION_KEY_MAP = {
  blur: true,
  saturation: true,
  brightness: true,
  tint: true,
  tintOpacity: true,
  refraction: true,
  ior: true,
  magnify: true,
  thickness: true,
  bevelWidth: true,
  bevelDepth: true,
  dispersion: true,
  specular: true,
  shadow: true,
  lighting: true,
  frost: true,
  radius: true,
  shape: true,
  preset: true,
  backend: true,
  effects: true,
  backdrop: true,
  sceneImage: true,
  physics: true,
  merge: true,
  mergeStrength: true,
  adaptive: true,
  motionLight: true,
  quality: true
};
var OPTION_KEYS = new Set(Object.keys(OPTION_KEY_MAP));
function isOptionKey(key) {
  return OPTION_KEYS.has(key);
}
function resetMissingOptions(previous, next) {
  if (!previous) return next;
  const reset = {};
  for (const key of Object.keys(previous)) {
    if (!(key in next)) reset[key] = void 0;
  }
  return { ...reset, ...next };
}

// ../core/src/fx/scroll-edge.ts
function mountScrollEdge(host, options = {}) {
  const position = options.position ?? "top";
  const size = options.size ?? 96;
  const strength = options.strength ?? 12;
  const doc = host.ownerDocument;
  const el2 = doc.createElement("div");
  el2.className = "lg-scroll-edge";
  el2.setAttribute("aria-hidden", "true");
  el2.setAttribute("data-liquid-glass-layer", "scroll-edge");
  el2.setAttribute("data-liquid-glass-ignore", "");
  const isBody = host === doc.body;
  const toEdge = position === "top" ? "to top" : "to bottom";
  const style = el2.style;
  style.position = isBody ? "fixed" : "absolute";
  style.left = "0";
  style.right = "0";
  style[position] = "0";
  style.height = `${size}px`;
  style.pointerEvents = "none";
  style.zIndex = "2147483003";
  const filter = `blur(${strength}px)`;
  style.setProperty("backdrop-filter", filter);
  style.setProperty("-webkit-backdrop-filter", filter);
  const mask = `linear-gradient(${toEdge}, transparent, rgba(0, 0, 0, 0.5) 40%, black)`;
  style.setProperty("mask-image", mask);
  style.setProperty("-webkit-mask-image", mask);
  style.setProperty(
    "background",
    `linear-gradient(${toEdge}, transparent, rgba(4, 6, 12, 0.28))`
  );
  if (!isBody && typeof getComputedStyle === "function") {
    const hostPosition = getComputedStyle(host).position;
    if (hostPosition === "static" || hostPosition === "") {
      host.style.setProperty("position", "relative");
    }
  }
  host.appendChild(el2);
  return {
    destroy() {
      el2.remove();
    }
  };
}

// ../core/src/fx/morph.ts
var MORPH_SPRING = { stiffness: 320, damping: 26};
function reducedMotion() {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}
function morphGlass(from, to, options = {}) {
  const a = from.getBoundingClientRect();
  const b = to.getBoundingClientRect();
  from.style.visibility = "hidden";
  if (reducedMotion() || typeof requestAnimationFrame !== "function") {
    return Promise.resolve();
  }
  const config = {
    stiffness: options.stiffness ?? MORPH_SPRING.stiffness,
    damping: options.damping ?? MORPH_SPRING.damping,
    mass: 1
  };
  const springs = {
    x: new Spring(a.left, config),
    y: new Spring(a.top, config),
    w: new Spring(Math.max(a.width, 1), config),
    h: new Spring(Math.max(a.height, 1), config)
  };
  springs.x.target = b.left;
  springs.y.target = b.top;
  springs.w.target = Math.max(b.width, 1);
  springs.h.target = Math.max(b.height, 1);
  const style = to.style;
  const saved = {
    position: style.position,
    left: style.left,
    top: style.top,
    width: style.width,
    height: style.height,
    margin: style.margin,
    zIndex: style.zIndex
  };
  to.setAttribute("data-liquid-glass-morphing", "true");
  style.position = "fixed";
  style.margin = "0";
  style.zIndex = "2147483002";
  const startScrollX = typeof window === "undefined" ? 0 : window.scrollX;
  const startScrollY = typeof window === "undefined" ? 0 : window.scrollY;
  return new Promise((resolve) => {
    let last2 = 0;
    const step = (time) => {
      const dt = last2 ? Math.min((time - last2) / 1e3, 1 / 20) : 1 / 60;
      last2 = time;
      let moving = false;
      for (const spring of Object.values(springs)) {
        moving = spring.step(dt) || moving;
      }
      const dx = (typeof window === "undefined" ? 0 : window.scrollX) - startScrollX;
      const dy = (typeof window === "undefined" ? 0 : window.scrollY) - startScrollY;
      style.left = `${(springs.x.value - dx).toFixed(2)}px`;
      style.top = `${(springs.y.value - dy).toFixed(2)}px`;
      style.width = `${springs.w.value.toFixed(2)}px`;
      style.height = `${springs.h.value.toFixed(2)}px`;
      if (moving) {
        requestAnimationFrame(step);
        return;
      }
      style.position = saved.position;
      style.left = saved.left;
      style.top = saved.top;
      style.width = saved.width;
      style.height = saved.height;
      style.margin = saved.margin;
      style.zIndex = saved.zIndex;
      to.removeAttribute("data-liquid-glass-morphing");
      resolve();
    };
    requestAnimationFrame(step);
  });
}

// ../core/src/index.ts
var VERSION = "0.12.0" ;

export { GlRenderer, MATERIAL_DEFAULTS, MATERIAL_PRESETS, MAX_SHAPES, NO_CAPABILITIES, OPTION_KEYS, PHYSICS_DEFAULTS, PhysicsController, Spring, SurfaceTracker, TONE_CROSSOVER, VERSION, adaptTintToTone, applyReducedTransparency, attach, autoAttach, backdropLuminance, buildLuminanceGrid, clampMaterial, colorWithOpacity, computeOffsets, configure, createEmitter, cssFallbackBackend, cssSvgBackend, detach, deviceTier, frameNow, generateLensMap, getBackend, getInstance, getLuminanceGrid, getQuality, interiorZoomOffset, isOptionKey, lensProfile, listBackends, morphGlass, mountScrollEdge, observeFrames, observeTone, onFrame, onViewport, parseColor, parseTint, probeCapabilities, readForcedColors, readReducedMotion, readReducedTransparency, registerBackend, relativeLuminance, resetCapabilitiesCache, resetMissingOptions, resetQuality, resolveBandPx, resolveMaterial, resolvePhysics, sampleTone, sdfRoundedRect, sdfSuperellipse, selectBackend, setLuminanceGrid, squircleClipPath, svgContentBackend, unionRect, watchFps, watchMedia, webglOverlayBackend, webglSceneBackend };

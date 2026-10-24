"""Время до первого контента (TTFC) экрана «Расписание» в симулированной нативной оболочке (мок Capacitor),
демо-сборка www. CPU x4 (как средний телефон), задержка API LATENCY мс (сеть). Без эмулятора.
Использование: WWW=/tmp/www python perf_ttfc.py [label]"""
import os, sys, json, threading, http.server, functools, socketserver, statistics
from playwright.sync_api import sync_playwright
WWW = os.environ.get("WWW", "/tmp/www"); PORT = int(os.environ.get("PERF_PORT", "9177"))
LAT = int(os.environ.get("LATENCY", "300")); RUNS = int(os.environ.get("RUNS", "5"))
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
socketserver.ThreadingTCPServer.allow_reuse_address = True
srv = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), functools.partial(Q, directory=WWW)); srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{PORT}"
INIT = """
window.Capacitor = { isNativePlatform: () => true, getPlatform: () => 'android', Plugins: {
  ItcNative: new Proxy({}, { get: () => () => Promise.resolve({}) }),
  App: { addListener: () => ({ remove() {} }), getLaunchUrl: () => Promise.resolve({}) } } };
(function(){ let f; Object.defineProperty(window, 'fetch', { configurable: true, get(){ return f; }, set(v){
  if (v && v.__lat) { f = v; return; }
  const inner = v; const w = function(i, o){ const u = typeof i === 'string' ? i : (i && i.url) || '';
    const api = /\\/api\\//.test(u); return api ? new Promise(r => setTimeout(r, %LAT%)).then(() => inner(i, o)) : inner(i, o); };
  if (!f) { w.__lat = 1; f = w; } else f = v; } }); })();
window.__perf = { first: null, flashes: 0, cls: 0, had: false };
new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__perf.cls += e.value; }).observe({ type: 'layout-shift', buffered: true });
const mo = new MutationObserver(() => { const c = document.getElementById('content'); if (!c) return;
  const real = c.querySelector('.calendar-event, .schedule-state:not(.is-loading):not(.app-skeleton)');
  if (real && window.__perf.first == null) window.__perf.first = performance.now();
  if (real) window.__perf.had = true;
  else if (window.__perf.had && c.querySelector('.is-loading')) { window.__perf.flashes++; window.__perf.had = false; } });
document.addEventListener('DOMContentLoaded', () => mo.observe(document.body, { childList: true, subtree: true }));
""".replace("%LAT%", str(LAT))
def med(a): return round(statistics.median(a)) if a else None
res = {"cold": [], "warm": [], "day": [], "week": [], "cls": [], "flashes": []}
with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for i in range(RUNS):
        c = br.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        c.add_init_script(INIT); pg = c.new_page()
        cdp = c.new_cdp_session(pg); cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
        for kind in ("cold", "warm"):
            pg.goto(B + "/index.html"); pg.wait_for_function("window.__perf && window.__perf.first != null", timeout=20000)
            res[kind].append(pg.evaluate("window.__perf.first"))
            if kind == "warm":
                pg.wait_for_timeout(1500)
                res["cls"].append(pg.evaluate("window.__perf.cls"))
                # смена дня и недели: время до появления контента нового дня
                for key, sel in (("day", "#day-buttons > button:nth-child(3)"), ("week", "#app-next-week, #next-week")):
                    pg.evaluate("window.__perf.first=null; window.__perf.had=false")
                    t0 = pg.evaluate("performance.now()")
                    if key == "week" and pg.locator("#next-week:visible").count() == 0:
                        pg.evaluate("window.ItcSchedule && window.ItcSchedule.shiftWeek(1)")
                    else: pg.click(sel)
                    pg.wait_for_function("window.__perf.first != null", timeout=20000)
                    res[key].append(pg.evaluate("window.__perf.first") - t0)
                    pg.wait_for_timeout(800)
                res["flashes"].append(pg.evaluate("window.__perf.flashes"))
        c.close()
    br.close()
out = {k: (med(v) if k not in ("cls",) else round(statistics.median(v), 4)) for k, v in res.items()}
out["label"] = sys.argv[1] if len(sys.argv) > 1 else WWW; out["latency_ms"] = LAT; out["cpu"] = "x4"; out["runs"] = RUNS
print(json.dumps(out, ensure_ascii=False))

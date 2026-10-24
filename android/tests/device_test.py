"""On-device smoke test for the installed APK. Drives the app WebView over raw CDP (adb forward) --
Playwright's connect_over_cdp does NOT work with Android WebView (Browser context management unsupported).
Env: SERVER (default http://10.0.2.2:48990), SHOTS_DIR, ADMIN_USER/ADMIN_PASS. Needs adb in PATH, `pip install websocket-client requests`."""
import os, subprocess, sys, time, re, json, base64, urllib.request
import websocket
SERVER = os.environ.get("SERVER", "http://10.0.2.2:48990")
SHOTS = os.environ.get("SHOTS_DIR", "/workspace/itc/shots")
PKG = "ru.kipfin.clubs"
ADMIN = (os.environ.get("ADMIN_USER", "admin"), os.environ.get("ADMIN_PASS", "DemoPass123!"))
res = []
def ok(name, cond, extra=""):
    res.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name, str(extra)[:300], flush=True)
def sh(*a): return subprocess.run(a, capture_output=True, text=True).stdout.strip()

class Cdp:
    def __init__(s, url): s.ws = websocket.create_connection(url, timeout=60, suppress_origin=True); s.i = 0
    def call(s, method, **params):
        s.i += 1; s.ws.send(json.dumps({"id": s.i, "method": method, "params": params}))
        while True:
            m = json.loads(s.ws.recv())
            if m.get("id") == s.i: return m
    def ev(s, expr, wait=True):
        r = s.call("Runtime.evaluate", expression=expr, awaitPromise=wait, returnByValue=True)
        return r.get("result", {}).get("result", {}).get("value")
    def shot(s, name):
        d = s.call("Page.captureScreenshot", format="png")["result"]["data"]
        open(f"{SHOTS}/{name}.png", "wb").write(base64.b64decode(d))

def connect():
    sock = None
    for _ in range(60):
        m = re.findall(r"webview_devtools_remote_(\d+)", sh("adb", "shell", "cat", "/proc/net/unix"))
        if m: sock = m[-1]; break
        time.sleep(3)
    ok("webview devtools socket found", sock, sock)
    if not sock: sys.exit(1)
    sh("adb", "forward", "tcp:9333", f"localabstract:webview_devtools_remote_{sock}")
    for _ in range(40):
        try:
            t = [x for x in json.load(urllib.request.urlopen("http://127.0.0.1:9333/json")) if x.get("type") == "page"]
            if t: return Cdp(t[0]["webSocketDebuggerUrl"]), t[0]["url"]
        except Exception: pass
        time.sleep(3)
    sys.exit("no page target")

def wait_for(c, expr, tries=40, delay=2):
    for _ in range(tries):
        try:
            v = c.ev(expr)
            if v: return v
        except Exception: pass
        time.sleep(delay)
    return None

sh("adb", "shell", "pm", "clear", PKG)
sh("adb", "shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1")
c, url = connect()
c.call("Page.enable"); c.call("Runtime.enable")
ok("first launch -> settings.html", wait_for(c, "location.pathname.includes('settings.html')"), c.ev("location.href"))
time.sleep(2); c.shot("apk-dev-01-first-launch")
ok("Capacitor native platform detected", c.ev("window.Capacitor && Capacitor.getPlatform && Capacitor.getPlatform()") == "android", c.ev("window.Capacitor && Capacitor.getPlatform && Capacitor.getPlatform()"))
inp = c.ev("(document.querySelector('input')||{}).id||''")
c.ev(f"(()=>{{const i=document.querySelector('input'); i.value={json.dumps(SERVER)}; i.dispatchEvent(new Event('input',{{bubbles:true}}));}})()", wait=False)
c.ev("document.querySelector('#test').click()", wait=False)
body = ""
for _ in range(20):
    time.sleep(2); body = c.ev("document.body.innerText") or ""
    if re.search(r"(Соединение|успеш|работает|✓|✅|Ошибка|не удалось|недоступ)", body, re.I): break
c.shot("apk-dev-02-test-connection")
ok("test connection OK on device", re.search(r"(успеш|работает|✓|✅|Соединение установлено|OK)", body, re.I) and not re.search(r"Не удалось|Ошибка", body), body.replace("\n", " | "))
c.ev("document.querySelector('#save').click()", wait=False)
ok("after save -> schedule page (not settings)", wait_for(c, "!location.pathname.includes('settings.html')", 30), c.ev("location.href"))
time.sleep(8); c.shot("apk-dev-03-schedule")
body = c.ev("document.body.innerText") or ""
ok("schedule shows data from the server", re.search(r"Шахмат|Робот|Хор|Футбол|Англий|Рисован|Театр|Программ|Спорт", body), body[:200].replace("\n", " | "))
# --- админка в приложении: вход через форму (Bearer + refresh), проверка ротации и настроек ---
c.call("Page.navigate", url=c.ev("location.origin") + "/admin/login.html")
ok("admin login page opened", wait_for(c, "!!document.querySelector('#login-form')"), c.ev("location.href"))
c.ev(f"""(()=>{{const l=document.querySelector('#login'),p=document.querySelector('#password');
  l.value={json.dumps(ADMIN[0])}; p.value={json.dumps(ADMIN[1])};
  document.querySelector('#login-form button[type=submit]').click();}})()""", wait=False)
ok("admin login via form -> dashboard", wait_for(c, "!!document.querySelector('.stat-card')", 30), c.ev("location.href"))
time.sleep(1); c.shot("apk-dev-04-admin-dashboard")
ok("Bearer token + refresh token stored by the app", c.ev("!!localStorage.getItem('clubs.adminToken') && !!localStorage.getItem('clubs.adminRefresh')"))
ok("no stray 'false' text on dashboard", "false" not in (c.ev("document.querySelector('#admin-main').innerText") or ""))
old = c.ev("localStorage.getItem('clubs.adminRefresh')")
r = c.ev("""(async()=>{const rt=localStorage.getItem('clubs.adminRefresh');
  const a=await fetch('/api/admin/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token:rt})});
  const j=a.status===200?await a.json():{};
  const b=await fetch('/api/admin/refresh',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token:rt})});
  return JSON.stringify({first:a.status,rotated:!!j.refresh_token&&j.refresh_token!==rt,replay_within_grace:b.status});})()""")
print(r, flush=True); r = json.loads(r)
ok("refresh rotates the refresh token on device", r["first"] == 200 and r["rotated"], r)
ok("replay of the old refresh inside grace window -> 409", r["replay_within_grace"] == 409, r)
# приложение само переживает протухший access: портим access-токен и перезагружаем админку
c.ev("localStorage.setItem('clubs.adminToken','x.y.z')")
c.call("Page.reload")
ok("broken access token is refreshed silently (stays in admin)", wait_for(c, "!!document.querySelector('.stat-card')", 30) and "/admin/" in (c.ev("location.pathname") or ""), c.ev("location.href"))
# настройки (шестерёнка) на устройстве: тёмная тема + блок «Сервер»
c.ev("document.querySelector('[data-settings-button]').click()", wait=False)
ok("settings dialog opens with server section", wait_for(c, "!!document.querySelector('#settings-dialog[open]') && /Сервер/.test(document.querySelector('#settings-dialog').innerText)"))
c.ev("document.querySelector('input[name=theme][value=dark]').click()", wait=False); time.sleep(1)
ok("dark theme applied on device", c.ev("document.documentElement.dataset.theme") == "dark")
c.shot("apk-dev-05-settings-dark")
bad = [n for n, k in res if not k]
print(f"{len(res)-len(bad)}/{len(res)} passed"); sys.exit(1 if bad else 0)

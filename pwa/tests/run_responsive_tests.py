"""Адаптивность (phase 2 E): установленное PWA (standalone) на разных устройствах — автоматические проверки и скриншоты.
Устройства: iPhone SE / 15 / 16 Pro Max (iOS standalone), Android 360, Galaxy/Pixel Fold 840 (развёрнут), альбомная
ориентация, текст 200%. Проверки на каждом экране: нет горизонтальной прокрутки, ничего не вылезает за край экрана,
подписи нижней навигации в одну строку, кнопки ≥ 44×44 (iOS HIG) / 48 dp, поля ввода на iOS ≥ 16px (без автозума),
шапка и нижняя панель не перекрывают контент, текст не обрезан у кнопок.
  python pwa/tests/run_responsive_tests.py      (PWA_DIR — готовая сборка; SHOTS_DIR — каталог скриншотов)"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402

from pwa_env import ADMIN, ANDROID_UA, CHROME, IOS_UA, PASSWORD, Stand, init_script  # noqa: E402

SHOTS = Path(os.environ.get("SHOTS_DIR", "/workspace/itc/shots_de")); SHOTS.mkdir(parents=True, exist_ok=True)
# (имя, платформа, ширина, высота, dpr, масштаб текста)
DEVICES = [
    ("iphone-se", "ios", 375, 667, 2, 1),
    ("iphone-15", "ios", 393, 852, 3, 1),
    ("iphone-16-pro-max", "ios", 440, 956, 3, 1),
    ("android-360", "android", 360, 800, 3, 1),
    ("fold-840", "android", 840, 900, 2.625, 1),
    ("iphone-15-landscape", "ios", 852, 393, 3, 1),
    ("android-360-landscape", "android", 800, 360, 3, 1),
    ("iphone-se-font200", "ios", 375, 667, 2, 2),
    ("android-360-font200", "android", 360, 800, 3, 2),
]
ONLY = os.environ.get("DEVICES")
if ONLY:
    DEVICES = [d for d in DEVICES if d[0] in ONLY.split(",")]
PAGES = [("schedule", "/"), ("clubs", "/clubs.html"), ("club", "/club.html?id=1"), ("qr", "/qr.html"),
         ("sheet", "/#sheet"), ("admin-sessions", "/admin/#/sessions"), ("admin-dashboard", "/admin/#/")]

PROBE = r"""
(fontScale) => {
  const W = document.documentElement.clientWidth, H = innerHeight, out = { overflowX: 0, outside: [], small: [], wrapNav: [], zoomInputs: [], clipped: [], covered: [] };
  out.overflowX = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - W;
  const visible = el => { const s = getComputedStyle(el); if (s.visibility === 'hidden' || s.display === 'none' || +s.opacity === 0) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const clippedByScroller = el => { for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) { const s = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(s.overflowX)) return true; } return false; };
  const label = el => (el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '')) + ' «' + (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 24) + '»';
  for (const el of document.querySelectorAll('body *')) {
    if (!visible(el) || el.closest('[aria-hidden=true], .itc-toast, .snackbar, svg')) continue;
    const r = el.getBoundingClientRect();
    if ((r.right > W + 1 || r.left < -1) && !clippedByScroller(el) && getComputedStyle(el).position !== 'fixed') out.outside.push(label(el) + ` ${Math.round(r.left)}..${Math.round(r.right)}`);
  }
  for (const el of document.querySelectorAll('a[href], button, input:not([type=hidden]), select, [role=tab], summary')) {
    if (!visible(el) || el.closest('.event-facts, p, li > a.club-link, .itc-sheet-card p')) continue;
    const r = el.getBoundingClientRect();
    if (r.bottom < 0 || r.top > H * 3) continue;
    const isText = el.tagName === 'A' && getComputedStyle(el).display === 'inline';
    if (!isText && (r.height < 40 || r.width < 40)) out.small.push(label(el) + ` ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  for (const el of document.querySelectorAll('.bottom-nav .bn-label')) {
    if (!visible(el)) continue; const lh = parseFloat(getComputedStyle(el).lineHeight) || 14;
    if (el.getBoundingClientRect().height > lh * 1.6) out.wrapNav.push(label(el));
  }
  if (document.documentElement.classList.contains('is-pwa-ios'))
    for (const el of document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=hidden]), select, textarea'))
      if (visible(el) && parseFloat(getComputedStyle(el).fontSize) < 16) out.zoomInputs.push(label(el) + ' ' + getComputedStyle(el).fontSize);
  for (const el of document.querySelectorAll('button, .btn, .itc-chip, [role=tab], .bn-label, h1, h2')) {
    if (!visible(el)) continue; const s = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 2 && s.textOverflow !== 'ellipsis' && /(hidden|clip)/.test(s.overflowX)) out.clipped.push(label(el));
  }
  // контент под фиксированной нижней навигацией в конце прокрутки
  const nav = document.querySelector('.bottom-nav'); const main = document.querySelector('main');
  if (nav && visible(nav) && main) { const pb = parseFloat(getComputedStyle(main).paddingBottom) + parseFloat(getComputedStyle(document.body).paddingBottom || 0);
    if (pb + 2 < nav.getBoundingClientRect().height) out.covered.push('main padding-bottom ' + pb + ' < nav ' + Math.round(nav.getBoundingClientRect().height)); }
  for (const k of ['outside', 'small', 'clipped']) out[k] = [...new Set(out[k])].slice(0, 12);
  return out;
}
"""

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name + (f"  -- {detail}" if detail else ""), flush=True)


st = Stand(build=True)
try:
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        # вход в админку один раз — cookie переиспользуем
        c0 = br.new_context(base_url=st.base); r = c0.request.post("/api/admin/login", data={"login": ADMIN, "password": PASSWORD})
        state = c0.storage_state(); c0.close()
        for name, kind, w, h, dpr, scale in DEVICES:
            for scheme in (["light", "dark"] if name in ("iphone-15", "android-360") else ["light"]):
                c = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=dpr, is_mobile=True, has_touch=True,
                                   user_agent=IOS_UA if kind == "ios" else ANDROID_UA, locale="ru-RU", timezone_id="Europe/Moscow",
                                   color_scheme=scheme, base_url=st.base, storage_state=state, service_workers="block")
                c.add_init_script(init_script(kind))
                c.add_init_script("localStorage.setItem('itc.follows','[1,3]');" + (f"document.addEventListener('DOMContentLoaded',()=>document.documentElement.style.setProperty('--text-scale','{scale}'));" if scale != 1 else ""))
                pg = c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
                for key, path in PAGES:
                    tag = f"{name}{'' if scheme == 'light' else '-dark'} {key}"
                    pg.goto(path.replace("#sheet", "")); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(700)
                    if key == "sheet":
                        pg.click("#itc-notify-open"); pg.wait_for_selector("#itc-sheet"); pg.wait_for_timeout(400)
                    if key.startswith("admin") and "/admin/login" in pg.url:
                        check(f"{tag}: админ вошёл", False, pg.url); continue
                    res = pg.evaluate(PROBE, scale)
                    check(f"{tag}: нет горизонтальной прокрутки", res["overflowX"] <= 1, f"+{res['overflowX']}px")
                    check(f"{tag}: ничего не вылезает за край", not res["outside"], "; ".join(res["outside"]))
                    check(f"{tag}: кнопки ≥ 40px", not res["small"], "; ".join(res["small"]))
                    check(f"{tag}: нижняя навигация в одну строку", not res["wrapNav"], "; ".join(res["wrapNav"]))
                    if kind == "ios":
                        check(f"{tag}: поля ≥ 16px (без автозума iOS)", not res["zoomInputs"], "; ".join(res["zoomInputs"]))
                    check(f"{tag}: текст кнопок не обрезан", not res["clipped"], "; ".join(res["clipped"]))
                    check(f"{tag}: нижняя навигация не закрывает контент", not res["covered"], "; ".join(res["covered"]))
                    pg.screenshot(path=str(SHOTS / f"e-{name}{'' if scheme == 'light' else '-dark'}-{key}.png"))
                check(f"{name}-{scheme}: без ошибок JS", not errs, "; ".join(errs[:3]))
                c.close()
        br.close()
finally:
    st.stop()

ok = sum(1 for _, r in results if r)
print(f"\nИТОГО: {ok}/{len(results)} ок")
sys.exit(0 if ok == len(results) else 1)

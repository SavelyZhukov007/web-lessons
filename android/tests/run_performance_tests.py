"""Current Android shim regression suite. Builds an isolated offline/demo www; no phone or external services.
Run: python android/tests/run_performance_tests.py. Optional WWW, SHOTS_DIR, CHROME_PATH.
"""
from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pwa/tests'))
from pwa_env import ANDROID_UA, Stand  # noqa: E402

shots = Path(os.environ.get('SHOTS_DIR', tempfile.mkdtemp(prefix='android-shots-')))
shots.mkdir(parents=True, exist_ok=True)
if not os.getenv('WWW'):
    www = Path(tempfile.mkdtemp(prefix='android-www-'))
    subprocess.run(['node', 'scripts/prepare-web.mjs'], cwd=ROOT / 'android', check=True,
                   env={**os.environ, 'APP_DEMO': '1', 'WWW_OUT': str(www)})
else:
    www = Path(os.environ['WWW'])
os.environ['PWA_DIR'] = str(www)
release = json.loads((ROOT / 'frontend/release-info.json').read_text(encoding='utf-8'))['version']
stand = Stand(build=False)
checks = 0
try:
    with sync_playwright() as p:
        chrome = os.environ.get('CHROME_PATH') or shutil.which('google-chrome') or shutil.which('chromium')
        if not chrome and sys.platform == 'win32':
            chrome = next((str(candidate) for base in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')
                           if os.environ.get(base) and (candidate := Path(os.environ[base]) / 'Google/Chrome/Application/chrome.exe').exists()), None)
        kwargs = {'executable_path': chrome} if chrome else {}
        browser = p.chromium.launch(args=[] if sys.platform == 'win32' else ['--no-sandbox'], **kwargs)
        for width in (390, 320):
            for scheme in ('light', 'dark'):
                ctx = browser.new_context(viewport={'width': width, 'height': 844}, is_mobile=True, has_touch=True,
                                          color_scheme=scheme, user_agent=ANDROID_UA, locale='ru-RU', timezone_id='Europe/Moscow')
                ctx.add_init_script("""window.Capacitor={isNativePlatform:()=>true,getPlatform:()=> 'android',Plugins:{
                  ItcPerformance:{getState:async()=>({powerSave:false,memoryGB:8,cores:8,refreshRate:60})}}};
                  localStorage.setItem('kipclub.release.seen.__CURRENT_RELEASE__','1');
                  localStorage.setItem('kipclub.storage-notice.v1','1');
                  localStorage.setItem('kc.pingAt',String(Date.now()));""".replace('__CURRENT_RELEASE__', release))
                pg = ctx.new_page()
                pg.clock.set_fixed_time('2026-11-09T12:00:00+03:00')
                errors = []
                pg.on('pageerror', lambda e: errors.append(str(e)))
                pg.goto(stand.base + '/?week=2026-11-09&day=2026-11-10', wait_until='networkidle')
                pg.locator('#itc-splash').wait_for(state='hidden')
                pg.get_by_role('button', name='Смотреть расписание', exact=True).click()
                pg.locator('.itc-ob-role').wait_for(state='detached')
                expect(pg.locator('#content')).to_have_attribute('aria-busy', 'false')
                expect(pg.locator('#day-buttons .ribbon-track')).to_have_count(1)
                checks += 1
                # The compositor/accessibility bounding box must cover ALL slots, not a one-viewport box translated offscreen.
                track = pg.locator('.ribbon-track').bounding_box()
                rail = pg.locator('#day-buttons').bounding_box()
                assert track['x'] <= rail['x'] + rail['width'] and track['x'] + track['width'] >= rail['x']
                assert track['width'] >= rail['width'] * 4
                checks += 2
                assert pg.evaluate('document.documentElement.scrollWidth <= innerWidth')
                checks += 1
                rail_height=pg.locator('#day-buttons').bounding_box()['height']
                pg.locator('#day-buttons .ribbon-hit[data-day-date="2026-11-11"]').tap()
                expect(pg.locator('#day-buttons [aria-pressed="true"]')).to_have_attribute('data-day-date','2026-11-11')
                assert pg.locator('#day-buttons').bounding_box()['height']==rail_height
                checks+=2
                top = pg.locator('#content').bounding_box()['y']
                for day in ('2026-11-11', '2026-11-12', '2026-11-10'):
                    pg.evaluate('(day)=>ItcSchedule.goto(day)', day)
                    expect(pg.locator('#day-buttons [aria-pressed="true"]')).to_have_attribute('data-day-date', day)
                    assert pg.locator('.ribbon-track').evaluate('el=>el.getAnimations().length') <= 1
                    expect(pg.locator('#content > .app-pane')).to_have_count(1)
                    assert pg.locator('#content').bounding_box()['y'] == top
                    checks += 4
                pg.locator('.ribbon-track').evaluate('el=>Promise.allSettled(el.getAnimations().map(a=>a.finished))')
                assert pg.locator('#day-buttons').evaluate('el=>el.scrollLeft') == 0
                checks += 1
                pg.evaluate("ClubsTheme.set({dayNavigation:'week'})")
                expect(pg.locator('#day-buttons [data-day-date]')).to_have_count(6)
                pg.evaluate("ItcSchedule.goto('2026-11-11')")
                assert pg.locator('.ribbon-track > .glass-indicator').evaluate('el=>el.getAnimations().length') <= 1
                assert pg.locator('.ribbon-track').evaluate('el=>el.getAnimations().length') == 0
                checks += 3
                pg.locator('#today').click()
                expect(pg.locator('#today')).to_have_attribute('aria-pressed', 'true')
                checks += 1
                pg.evaluate("window.dispatchEvent(new CustomEvent('itc:performance',{detail:{powerSave:true}}))")
                expect(pg.locator('html')).to_have_attribute('data-glass-tier', 'none')
                expect(pg.locator('#prev-week')).to_have_css('backdrop-filter', 'none')
                checks += 2
                pg.evaluate("window.dispatchEvent(new CustomEvent('itc:performance',{detail:{powerSave:false,memoryGB:4,cores:4}}))")
                expect(pg.locator('html')).to_have_attribute('data-glass-tier', 'light')
                checks += 1
                pg.evaluate('ItcPerformance.beginMotion(1000)')
                expect(pg.locator('html')).to_have_attribute('data-perf-motion', '')
                expect(pg.locator('#prev-week')).to_have_css('backdrop-filter', 'none')
                checks += 2
                pg.screenshot(path=str(shots / f'android-perf-{width}-{scheme}.png'), animations='disabled')
                pg.evaluate("Capacitor.Plugins.ItcNative={pinWidget:async({kind})=>{window.__pinned=kind;return {requested:true}}}")
                pg.locator('.app-gear').click()
                expect(pg.get_by_role('heading',name='Виджеты на рабочий стол',exact=True)).to_be_visible()
                expect(pg.get_by_role('link',name='3D-тур КИПФИН',exact=False)).to_have_attribute('rel','noopener noreferrer')
                privacy=pg.get_by_role('switch',name='Анонимная статистика и технические ошибки',exact=True)
                expect(privacy).to_have_attribute('aria-checked','false')
                privacy.click();assert pg.evaluate('KipUsage.consent()')
                privacy.click();assert not pg.evaluate('KipUsage.consent()')
                pg.locator('[data-widget-settings]').scroll_into_view_if_needed()
                pg.screenshot(path=str(shots / f'final-19021-{width}-{scheme}-android-settings-actual.png'),animations='disabled')
                pg.get_by_role('button',name='Следующее занятие',exact=True).click()
                assert pg.evaluate('window.__pinned')=='next'
                expect(pg.locator('[data-widget-settings] [role=status]')).to_contain_text('Подтвердите')
                pg.locator('.itc-set-back').click()
                checks+=8
                assert not errors, errors
                checks += 1
                print(f'PASS Android shim {width} {scheme}', flush=True)
                ctx.close()
        browser.close()
finally:
    stand.stop()
print(f'ИТОГО: {checks}/{checks} ок')

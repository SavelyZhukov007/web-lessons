// WCAG 2.x AA для пар токенов tokens.css: светлая/тёмная тема × все акценты. Парсим сам CSS — расхождение «в тексте» невозможно.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const css = readFileSync(fileURLToPath(new URL('../css/tokens.css', import.meta.url)), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');

function blocks() {
  const out = new Map();
  for (const [, selector, body] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const sel = selector.trim();
    if (!sel.startsWith(':root')) continue; // @media / @font-face
    const vars = {};
    for (const [, name, value] of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[name] = value.trim();
    out.set(sel, { ...(out.get(sel) ?? {}), ...vars });
  }
  return out;
}
const B = blocks();

function tokens(theme, accent) {
  const base = { ...B.get(':root') };
  if (theme === 'dark') Object.assign(base, B.get(':root[data-theme="dark"]'));
  if (accent !== 'brick') Object.assign(base, B.get(`:root[data-accent="${accent}"]`), theme === 'dark' ? B.get(`:root[data-theme="dark"][data-accent="${accent}"]`) : {});
  return base;
}

const hex = value => {
  assert.match(value, /^#([0-9a-f]{3}|[0-9a-f]{6})$/i, `ожидался #rgb или #rrggbb, получено ${value}`);
  const full = value.length === 4 ? `#${[...value.slice(1)].map(c => c + c).join('')}` : value;
  return [1, 3, 5].map(i => parseInt(full.slice(i, i + 2), 16));
};
const lin = c => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
const luminance = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
export function ratio(a, b) {
  const [l1, l2] = [luminance(hex(a)), luminance(hex(b))].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
}

test('ratio(): эталонные значения WCAG', () => {
  assert.equal(Math.round(ratio('#000000', '#ffffff')), 21);
  assert.ok(Math.abs(ratio('#767676', '#ffffff') - 4.54) < 0.02); // известная граница AA
});

const TEXT_PAIRS = [ // [передний, фон]
  ['--on-surface', '--bg'], ['--on-surface', '--surface-1'], ['--on-surface', '--surface-2'], ['--on-surface', '--surface-3'],
  ['--on-surface-muted', '--bg'], ['--on-surface-muted', '--surface-1'], ['--on-surface-muted', '--surface-2'],
  ['--primary', '--bg'], ['--primary', '--surface-1'], ['--on-primary', '--primary'],
  ['--on-primary-container', '--primary-container'],
  ['--status-moved-fg', '--status-moved-bg'], ['--status-cancelled-fg', '--status-cancelled-bg'], ['--status-ok-fg', '--status-ok-bg'],
  ['--danger', '--bg'], ['--danger', '--surface-1'], ['--on-danger', '--danger'],
];
const UI_PAIRS = [['--outline', '--bg'], ['--outline', '--surface-1'], ['--status-moved-line', '--bg'], ['--status-cancelled-line', '--bg']]; // нетекстовые элементы ≥ 3:1

for (const theme of ['light', 'dark']) {
  for (const accent of ['brick', 'blue', 'green', 'violet']) {
    test(`AA текст — ${theme} / ${accent}`, () => {
      const t = tokens(theme, accent);
      for (const [fg, bg] of TEXT_PAIRS) {
        assert.ok(t[fg] && t[bg], `нет токена ${fg} или ${bg}`);
        const r = ratio(t[fg], t[bg]);
        assert.ok(r >= 4.5, `${theme}/${accent}: ${fg} ${t[fg]} на ${bg} ${t[bg]} = ${r.toFixed(2)} (< 4.5)`);
      }
    });
    test(`AA нетекстовые элементы — ${theme} / ${accent}`, () => {
      const t = tokens(theme, accent);
      for (const [fg, bg] of UI_PAIRS) {
        const r = ratio(t[fg], t[bg]);
        assert.ok(r >= 3, `${theme}/${accent}: ${fg} ${t[fg]} на ${bg} ${t[bg]} = ${r.toFixed(2)} (< 3)`);
      }
    });
  }
}

test('блок «без JS» (prefers-color-scheme: dark) совпадает с data-theme=dark для базовых токенов', () => {
  const m = css.match(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root:not\(\[data-theme\]\)\s*\{([^}]*)\}/);
  assert.ok(m, 'нет блока prefers-color-scheme');
  const vars = Object.fromEntries([...m[1].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)].map(x => [x[1], x[2].trim()]));
  const dark = tokens('dark', 'brick');
  for (const [k, v] of Object.entries(vars)) assert.equal(dark[k], v, `${k} расходится с тёмной темой`);
});

import { h, icon } from './ui.js';
import { hasUnsavedWork } from './update-controller.js';

let releaseRequest;
let dialog;
const pending = { auto: false };

function releaseInfo() {
  releaseRequest ||= fetch('/release-info.json')
    .then(async response => {
      const data = response.ok ? await response.json() : null;
      return /^v\d+\.\d+\.\d+$/.test(data?.version) && Array.isArray(data.changelog) ? data : null;
    })
    .catch(() => null)
    .then(data => {
      if (!data) releaseRequest = undefined;
      return data;
    });
  return releaseRequest;
}

function remember(version) {
  try { localStorage.setItem(`kipclub.release.seen.${version}`, '1'); } catch { /* storage disabled */ }
}

function seen(version) {
  try { return localStorage.getItem(`kipclub.release.seen.${version}`) === '1'; } catch { return false; }
}

export async function showRelease({ requested, auto = false, opener } = {}) {
  const release = await releaseInfo();
  if (!release || (requested && release.version !== requested)) return false;
  if (dialog?.open) return true;
  if (auto && !requested && seen(release.version)) return false;
  if (auto && hasUnsavedWork()) return false;

  const close = () => dialog.close();
  dialog = h('dialog', { class: 'sheet sheet--bottom release-sheet', 'aria-labelledby': 'release-title' },
    h('div', { class: 'sheet-head' },
      h('h2', { id: 'release-title' }, `Что нового в ${release.version}`),
      h('button', { type: 'button', class: 'btn btn--text btn--small', 'aria-label': 'Закрыть список изменений', onclick: close }, icon('close'))),
    h('div', { class: 'sheet-body' },
      h('ul', { class: 'release-changes' }, release.changelog.map(change => h('li', {}, change)))),
    h('div', { class: 'sheet-foot' },
      h('button', { type: 'button', class: 'btn btn--filled', onclick: close }, 'Понятно')));
  dialog.addEventListener('click', event => { if (event.target === dialog) close(); });
  dialog.addEventListener('close', () => {
    remember(release.version);
    dialog.remove();
    dialog = undefined;
    opener?.focus();
  }, { once: true });
  document.body.append(dialog);
  dialog.showModal();
  if (requested) {
    const url = new URL(location.href);
    url.searchParams.delete('release');
    url.searchParams.delete('update');
    history.replaceState(history.state, '', url);
  }
  return true;
}

export function startReleaseNotes() {
  if (location.pathname !== '/' && location.pathname !== '/index.html') return;
  async function open() {
    if (pending.auto || document.hidden || hasUnsavedWork()) return;
    pending.auto = true;
    try {
      const requested = new URLSearchParams(location.search).get('release');
      const shown = await showRelease({ requested, auto: true });
      if (!shown && requested) await showRelease({ auto: true });
    } finally { pending.auto = false; }
  }
  window.addEventListener('pageshow', open);
  document.addEventListener('visibilitychange', open);
  document.addEventListener('close', open, true);
  if (document.readyState === 'complete') open();
}

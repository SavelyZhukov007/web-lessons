// Версия сборки (схема — README «Версии», ../../version.json → _scheme):
//   v<X.Y.Z><канал><стадия><платформа>, канал l|i|p, стадия a|d|r — задаёт пользователь (--version v0.4.312pd),
//   платформа A|W|M — дописывает скрипт сборки сам. Номер X.Y.Z — общий для всех платформ (../../version.json).
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
export const androidVersionPath = join(root, 'version.json');
export const sharedVersionPath = join(root, '..', 'version.json');
export const ID_RE = /^v(\d+\.\d+\.\d+)([lip])([abdr])$/;
export const PLATFORM = { android: 'A', web: 'W', pwa: 'M' };
export function parseId(id) {
  const m = ID_RE.exec(String(id || '').trim());
  if (!m) throw new Error(`Версия «${id}» не по схеме: нужно v<X.Y.Z><l|i|p><a|b|d|r>, например v1.0.012pb (буква платформы добавляется автоматически)`);
  return { id: m[0], version: m[1], channel: m[2], stage: m[3] };
}
// ITC_VERSION (ставит build.mjs) → иначе последняя собранная (android/version.json → lastId)
export function readVersion(platform = 'android') {
  const a = JSON.parse(readFileSync(androidVersionPath, 'utf8'));
  const shared = JSON.parse(readFileSync(sharedVersionPath, 'utf8'));
  const p = parseId(process.env.ITC_VERSION || a.lastId || `v${shared.version}la`);
  if (p.version !== shared.version) throw new Error(`Номер ${p.version} не совпадает с общим version.json (${shared.version}); build.mjs обновляет его сам`);
  // Явное пользовательское название применяется только к совпадающему номеру.
  // Последующая сборка другого номера не наследует устаревшую подпись.
  const versionName = a.versionName === `v${p.version}` ? a.versionName : p.id + PLATFORM[platform];
  return { ...p, platform: PLATFORM[platform], versionName, versionCode: a.versionCode, raw: a };
}
export function setShared(version) {
  const s = JSON.parse(readFileSync(sharedVersionPath, 'utf8'));
  if (s.version !== version) { s.version = version; writeFileSync(sharedVersionPath, JSON.stringify(s, null, 2) + '\n'); }
}

#!/usr/bin/env node
// Единая точка сборки: node scripts/build.mjs --version v0.4.312pd [--platform android|web|pwa|all] [--no-bump] [--release] [--no-demo]
//  - --version: v<X.Y.Z><канал l|i|p><стадия a|d|r>; буква платформы (A/W/M) дописывается автоматически.
//  - канал задаёт конфиг: p — без демо-инструментов, тестового сервера и отладки; l/i — с ними.
//  - результат: builds/<platform>/<полный id>/ (например builds/android/v0.4.312pdA/kipclub-v0.4.312pdA.apk).
//    Разные id лежат рядом; пересборка того же id заменяет только его папку.
import { spawnSync } from 'node:child_process';
import { existsSync, rmSync, mkdirSync, copyFileSync, cpSync, writeFileSync, readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseId, setShared, readVersion, androidVersionPath, PLATFORM } from './version.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repo = resolve(root, '..');
const arg = (n) => { const i = process.argv.indexOf(n); return i >= 0 ? process.argv[i + 1] : undefined; };
const has = (n) => process.argv.includes(n);
let id;
try { id = parseId(arg('--version')); } catch (e) { console.error(e.message); process.exit(2); }
const plat = arg('--platform') || 'android';
const targets = plat === 'all' ? ['android', 'web', 'pwa'] : [plat];
if (targets.some((t) => !PLATFORM[t])) { console.error('--platform: android | web | pwa | all'); process.exit(2); }

setShared(id.version); // номер X.Y.Z — общий для всех платформ
const env = { ...process.env, ITC_VERSION: id.id, ITC_CHANNEL: id.channel };
const run = (cmd, cwd) => { console.log(`\n> ${cmd}`); const r = spawnSync(cmd, { cwd, stdio: 'inherit', shell: true, env }); if (r.status !== 0) process.exit(r.status || 1); };
const outDir = (t) => { const full = id.id + PLATFORM[t]; const d = join(repo, 'builds', t, full); rmSync(d, { recursive: true, force: true }); mkdirSync(d, { recursive: true }); return { d, full }; };

for (const t of targets) {
  if (t === 'android') {
    const a = JSON.parse(readFileSync(androidVersionPath, 'utf8'));
    a.lastId = id.id; if (!has('--no-bump')) a.versionCode += 1;
    writeFileSync(androidVersionPath, JSON.stringify(a, null, 2) + '\n');
    run(`node scripts/build-apk.mjs --no-bump ${has('--no-demo') ? '' : '--demo'} ${has('--release') ? '--release' : ''}`, root);
    const v = readVersion('android'); const { d, full } = outDir(t);
    const apk = join(root, 'dist', `kipclub-${v.versionName}.apk`);
    copyFileSync(apk, join(d, `kipclub-${v.versionName}.apk`));
    writeFileSync(join(d, 'version.json'), JSON.stringify({ versionName: v.versionName, buildId: full, versionCode: v.versionCode, channel: id.channel, stage: id.stage }, null, 2) + '\n');
    console.log(`✔ ${join(d, `kipclub-${v.versionName}.apk`)} (versionCode ${v.versionCode})`);
  } else {
    const py = process.env.PYTHON || (existsSync(join(repo, '..', 'venv310', 'bin', 'python')) ? join(repo, '..', 'venv310', 'bin', 'python') : 'python3');
    const { d, full } = outDir(t);
    const fn = t === 'web' ? 'tools.build.web import build_web as b' : 'tools.build.pwa import build_pwa as b';
    run(`"${py}" -c "from pathlib import Path; from ${fn}; b(Path(r'${d}'))"`, repo);
    writeFileSync(join(d, 'version.json'), JSON.stringify({ versionName: full, version: id.version, channel: id.channel, stage: id.stage, platform: PLATFORM[t] }) + '\n');
    console.log(`✔ ${d}`);
  }
}

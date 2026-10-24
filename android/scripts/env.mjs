// Автоопределение окружения для сборки APK: JDK 21+ и Android SDK. Работает на Windows/Linux/macOS.
import { existsSync, readdirSync } from 'node:fs';
import { join, delimiter } from 'node:path';
import { homedir } from 'node:os';
import { spawnSync } from 'node:child_process';

const isWin = process.platform === 'win32';
const javaExe = isWin ? 'java.exe' : 'java';

export function javaMajor(home) {
  const bin = home ? join(home, 'bin', javaExe) : 'java';
  if (home && !existsSync(bin)) return 0;
  const r = spawnSync(bin, ['-version'], { encoding: 'utf8', shell: !home });
  const m = ((r.stderr || '') + (r.stdout || '')).match(/version "(\d+)(?:\.(\d+))?/);
  if (!m) return 0;
  return m[1] === '1' ? Number(m[2]) : Number(m[1]); // "1.8.0" -> 8
}

function listDirs(base, re) {
  try { return readdirSync(base, { withFileTypes: true }).filter(d => d.isDirectory() && re.test(d.name)).map(d => join(base, d.name)); }
  catch { return []; }
}

function jdkCandidates() {
  const list = [];
  const add = (p) => { if (p && !list.includes(p)) list.push(p); };
  add(process.env.JAVA_HOME);
  add(process.env.JDK_21_HOME); add(process.env.JAVA_HOME_21_X64);
  if (isWin) {
    const pf = [process.env.ProgramFiles, process.env['ProgramFiles(x86)'], process.env.ProgramW6432, 'C:\\Program Files'].filter(Boolean);
    const vendors = ['Eclipse Adoptium', 'Microsoft', 'Java', 'Zulu', 'Amazon Corretto', 'BellSoft', 'Semeru', 'JetBrains', 'OpenJDK', 'AdoptOpenJDK'];
    for (const p of new Set(pf)) {
      for (const v of vendors) for (const d of listDirs(join(p, v), /^(jdk|jbr|java|zulu|openjdk|microsoft)/i)) add(d);
      add(join(p, 'Android', 'Android Studio', 'jbr'));
      add(join(p, 'Android', 'Android Studio', 'jre'));
    }
    const local = process.env.LOCALAPPDATA;
    if (local) for (const d of listDirs(join(local, 'Programs'), /^(eclipse adoptium|microsoft|jdk|java)/i)) { add(d); for (const s of listDirs(d, /^(jdk|jbr)/i)) add(s); }
    add(join(homedir(), '.jdks')); for (const d of listDirs(join(homedir(), '.jdks'), /./)) add(d);
  } else {
    for (const base of ['/usr/lib/jvm', '/Library/Java/JavaVirtualMachines', join(homedir(), '.sdkman/candidates/java'), join(homedir(), '.jdks')]) {
      for (const d of listDirs(base, /./)) { add(d); add(join(d, 'Contents', 'Home')); }
    }
  }
  return list;
}

/** Ищет JDK >= minMajor. Возвращает { home, major } (home=null — если подходит java из PATH). */
export function findJdk(minMajor = 21, maxMajor = 24) {
  const found = [];
  for (const home of jdkCandidates()) { const major = javaMajor(home); if (major >= minMajor && major <= maxMajor) found.push({ home, major }); }
  // Gradle 8.14 не запускается на Java 25+, поэтому предпочитаем 21, иначе берём ближайший подходящий
  if (found.length) return found.sort((a, b) => Math.abs(a.major - 21) - Math.abs(b.major - 21))[0];
  const pm = javaMajor(null);
  if (pm >= minMajor && pm <= maxMajor) return { home: null, major: pm };
  return null;
}

/** Ищет Android SDK: ANDROID_HOME, ANDROID_SDK_ROOT, %LOCALAPPDATA%\Android\Sdk, ~/Android/Sdk, ~/Library/Android/sdk. */
export function findSdk() {
  const c = [process.env.ANDROID_HOME, process.env.ANDROID_SDK_ROOT];
  if (isWin && process.env.LOCALAPPDATA) c.push(join(process.env.LOCALAPPDATA, 'Android', 'Sdk'));
  c.push(join(homedir(), 'Android', 'Sdk'), join(homedir(), 'Library', 'Android', 'sdk'), '/opt/android-sdk', '/usr/lib/android-sdk');
  return c.filter(Boolean).find(p => existsSync(join(p, 'platforms')) || existsSync(join(p, 'platform-tools'))) || null;
}

/** Применяет найденное к process.env (только для этого процесса и его детей). */
export function applyEnv({ minJava = 21 } = {}) {
  const problems = [], notes = [];
  const jdk = findJdk(minJava);
  if (!jdk) problems.push(`Не найден JDK ${minJava}+ (Capacitor 8 / AGP 8.13 требуют JDK 21). Поставь Temurin 21 (https://adoptium.net) — он ставится рядом с JDK 17, ничего не ломает. Можно задать JAVA_HOME вручную.`);
  else {
    if (jdk.home) {
      if (process.env.JAVA_HOME !== jdk.home) notes.push(`JAVA_HOME (только для этой сборки) = ${jdk.home}` + (process.env.JAVA_HOME ? ` (был: ${process.env.JAVA_HOME})` : ''));
      process.env.JAVA_HOME = jdk.home;
      process.env.PATH = join(jdk.home, 'bin') + delimiter + process.env.PATH;
    }
    notes.push(`JDK ${jdk.major}`);
  }
  const sdk = findSdk();
  if (!sdk) problems.push('Не найден Android SDK. Задай ANDROID_HOME (напр. C:\\Users\\<you>\\AppData\\Local\\Android\\Sdk) или поставь через Android Studio.');
  else {
    process.env.ANDROID_HOME = sdk; process.env.ANDROID_SDK_ROOT = sdk;
    process.env.PATH = join(sdk, 'platform-tools') + delimiter + process.env.PATH;
    notes.push(`SDK ${sdk}`);
  }
  const nodeMajor = Number(process.versions.node.split('.')[0]);
  if (nodeMajor < 22) problems.push(`Нужен Node.js >= 22 (сейчас ${process.versions.node}).`);
  return { jdk, sdk, problems, notes };
}

import { readVersion, androidVersionPath } from './version.mjs';
// `npm run apk` — собирает debug APK (`--release` — подписанный release, `--demo` — офлайн-демо). Работает на Windows/macOS/Linux.
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, statSync, readdirSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { applyEnv } from './env.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const checkOnly = process.argv.includes('--check-only');
const argValue = (name) => { const i = process.argv.indexOf(name); return i >= 0 ? process.argv[i + 1] : undefined; };
const serverUrl = argValue('--server-url');            // предзаданный адрес сервера (иначе при первом запуске приложение спросит)
if (serverUrl) process.env.APP_DEFAULT_SERVER = serverUrl;
const install = process.argv.includes('--install');
const demo = process.argv.includes('--demo');        // офлайн-демо: локальный бэкенд + случайные данные + админ без входа
if (demo) process.env.APP_DEMO = '1';
const release = process.argv.includes('--release');   // release: подпись ключом из ANDROID_KEYSTORE*
const noBump = process.argv.includes('--no-bump');    // не поднимать versionCode/versionName
const sh = (cmd, opts = {}) => {
  console.log(`\n> ${cmd}`);
  const r = spawnSync(cmd, { cwd: root, stdio: 'inherit', shell: true, env: process.env, ...opts });
  if (r.status !== 0) { console.error(`\nКоманда упала (код ${r.status}): ${cmd}`); process.exit(r.status || 1); }
};
const out = (cmd) => spawnSync(cmd, { shell: true, encoding: 'utf8' });

// ---- проверки окружения (JDK 21+, Android SDK ищутся автоматически, JAVA_HOME ставится только для этого процесса)
const { sdk, problems, notes } = applyEnv({ minJava: 21 });
if (problems.length) { console.error('\nПроблемы окружения:\n - ' + problems.join('\n - ')); process.exit(2); }
if (!existsSync(join(sdk, 'platforms', 'android-36'))) console.warn('! В SDK нет platforms;android-36 — Gradle попробует докачать его сам (нужны принятые лицензии: sdkmanager --licenses).');
if (!existsSync(join(sdk, 'build-tools', '36.0.0'))) console.warn('! В SDK нет build-tools;36.0.0 — Gradle попробует докачать сам.');
console.log(`Окружение OK: node ${process.versions.node}; ${notes.join('; ')}`);
if (checkOnly) process.exit(0);

// ---- release: ключ подписи (не храним в репозитории)
const signing = release ? {
  file: process.env.ANDROID_KEYSTORE, storePass: process.env.ANDROID_KEYSTORE_PASSWORD,
  alias: process.env.ANDROID_KEY_ALIAS, keyPass: process.env.ANDROID_KEY_PASSWORD || process.env.ANDROID_KEYSTORE_PASSWORD,
} : null;
if (signing && (!signing.file || !existsSync(signing.file) || !signing.storePass || !signing.alias)) {
  console.error('\nДля --release нужен ключ: ANDROID_KEYSTORE (путь к .jks), ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS[, ANDROID_KEY_PASSWORD].\n' +
    'Создать: keytool -genkeypair -v -keystore kruzhki-release.jks -alias kruzhki -keyalg RSA -keysize 4096 -validity 10000\n' +
    'Храните .jks и пароли вне репозитория: обновления в RuStore/поверх APK подписываются только тем же ключом.');
  process.exit(5);
}

// ---- версия: каждая сборка поднимает versionCode (+1), чтобы APK ставились поверх. versionName (v0.4.312pd) задаётся
// вручную в version.json по смыслу изменений (схема — в его _comment); старый формат «1.1» по-прежнему авто-поднимается.
if (!noBump) { // только versionCode +1; id версии задаётся через build.mjs --version
  const a = JSON.parse(readFileSync(androidVersionPath, 'utf8')); a.versionCode += 1; writeFileSync(androidVersionPath, JSON.stringify(a, null, 2) + '\n');
}
const ver = readVersion('android');
process.env.ITC_VERSION = ver.id; process.env.ITC_CHANNEL = ver.channel; // для prepare-web / patch-android
console.log(`Версия сборки: ${ver.versionName} (versionCode ${ver.versionCode})`);

// ---- сборка
if (!existsSync(join(root, 'node_modules', '@capacitor', 'cli'))) sh(existsSync(join(root, 'package-lock.json')) ? 'npm ci' : 'npm install');
sh('node scripts/prepare-web.mjs');
if (!existsSync(join(root, 'android', 'gradlew'))) sh('npx cap add android');
sh('node scripts/patch-android.mjs');
sh('npx cap sync android');
// local.properties (Gradle иначе берёт ANDROID_HOME; пишем явно для надёжности)
writeFileSync(join(root, 'android', 'local.properties'), `sdk.dir=${sdk.replace(/\\/g, '\\\\')}\n`);
const gradlew = isWin ? 'gradlew.bat' : './gradlew';
const variant = release ? 'release' : 'debug';
// подпись release: android/app/build.gradle (patch-android.mjs) читает ANDROID_KEYSTORE* из окружения — пароли не попадают в командную строку
sh(`${gradlew} ${release ? 'assembleRelease' : 'assembleDebug'}`, { cwd: join(root, 'android') });

const apkDir = join(root, 'android', 'app', 'build', 'outputs', 'apk', variant);
const apk = join(apkDir, `app-${variant}.apk`);
if (!existsSync(apk)) { console.error('APK не найден в ' + apkDir + ': ' + (existsSync(apkDir) ? readdirSync(apkDir).join(', ') : 'нет папки')); process.exit(3); }
mkdirSync(join(root, 'dist'), { recursive: true });
const dest = join(root, 'dist', `kipclub-${ver.versionName}.apk`);
copyFileSync(apk, dest);
console.log(`\n✔ APK готов: ${dest} (${(statSync(dest).size / 1048576).toFixed(1)} MB)\nУстановка: adb install -r "${dest}"`);
if (install) {
  const adb = join(sdk, 'platform-tools', isWin ? 'adb.exe' : 'adb');
  if (!existsSync(adb)) { console.error('Нет adb: ' + adb + ' (поставь platform-tools в SDK Manager).'); process.exit(4); }
  sh(`"${adb}" devices`);
  sh(`"${adb}" install -r "${dest}"`);
  sh(`"${adb}" shell monkey -p ru.kipfin.clubs${demo ? '.demo' : ''} -c android.intent.category.LAUNCHER 1`);
}

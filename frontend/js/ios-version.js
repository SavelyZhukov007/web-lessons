// Версия iOS из userAgent (чистые функции — покрыты node-тестами). На iPadOS 13+ Safari притворяется Mac — версии нет.
export const MIN_IOS = [16, 4];

/** 'iPhone OS 16_3_1' / 'CPU OS 16_3' / запасной 'Version/16.3' → {major, minor, patch, text} или null. */
export function parseIosVersion(ua) {
    const s = String(ua || '');
    const m = s.match(/(?:iPhone|CPU)(?: iPhone)? OS (\d+)(?:[_.](\d+))?(?:[_.](\d+))?/)
        || (/iPhone|iPad|iPod/.test(s) ? s.match(/Version\/(\d+)(?:\.(\d+))?(?:\.(\d+))?/) : null);
    if (!m) return null;
    const [major, minor, patch] = [m[1], m[2], m[3]].map((x) => (x === undefined ? 0 : Number(x)));
    if (!major) return null;
    const text = [major, minor, ...(patch ? [patch] : [])].join('.');
    return { major, minor, patch, text };
}

/** true — версия известна и ниже 16.4 (установка на экран «Домой» не поддерживается). */
export function isTooOld(v, min = MIN_IOS) {
    if (!v) return false;
    return v.major < min[0] || (v.major === min[0] && v.minor < min[1]);
}

export function tooOldMessage(v) {
    return `На этом iPhone стоит iOS ${v.text} — она слишком старая, поэтому KipClub нельзя добавить на экран «Домой». Обновите iOS до 16.4 или новее: Настройки → Основные → Обновление ПО.`;
}

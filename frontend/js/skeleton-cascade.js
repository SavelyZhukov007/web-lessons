// Каскадный переход «скелетон → расписание» (вариант c). Чистая логика таймингов вынесена отдельно — её проверяют тесты.
export const CASCADE = Object.freeze({
  cap: 450,          // весь переход не дольше, мс
  step: 45,          // шаг между карточками, мс
  cardDuration: 280, // появление одной карточки
  cardLead: 60,      // карточки стартуют чуть позже, чем начинают гаснуть заглушки
  skeletonDuration: 160,
  reduced: 120,      // prefers-reduced-motion: один короткий fade без сдвига и каскада
});

/** Тайминги каскада: задержки/длительности для заглушек и карточек, общий итог ≤ cap. */
export function cascadeTiming(cardCount, skeletonCount, { reduced = false } = {}) {
  const cards = Math.max(0, cardCount | 0), skels = Math.max(0, skeletonCount | 0);
  if (reduced) {
    const d = CASCADE.reduced;
    return { cards: Array.from({ length: cards }, () => ({ delay: 0, duration: d })), skeletons: Array.from({ length: skels }, () => ({ delay: 0, duration: d })), total: cards || skels ? d : 0, shift: 0 };
  }
  const room = CASCADE.cap - CASCADE.cardLead - CASCADE.cardDuration; // время на «лесенку»
  const step = cards > 1 ? Math.min(CASCADE.step, room / (cards - 1)) : 0;
  const skelStep = skels > 1 ? Math.min(step / 2 || CASCADE.step / 2, (CASCADE.cap - CASCADE.skeletonDuration) / (skels - 1)) : 0;
  const cardList = Array.from({ length: cards }, (_, i) => ({ delay: Math.round(CASCADE.cardLead + i * step), duration: CASCADE.cardDuration }));
  const skelList = Array.from({ length: skels }, (_, i) => ({ delay: Math.round(i * skelStep), duration: CASCADE.skeletonDuration }));
  const ends = [...cardList, ...skelList].map(x => x.delay + x.duration);
  return { cards: cardList, skeletons: skelList, total: ends.length ? Math.max(...ends) : 0, shift: 8 };
}

/** Порядок появления: сверху вниз, при равной высоте — слева направо. Принимает [{top,left}], возвращает индексы. */
export function cascadeOrder(rects) {
  return rects.map((r, i) => [r, i]).sort(([a], [b]) => (a.top - b.top) || (a.left - b.left)).map(([, i]) => i);
}

/**
 * Запускает каскад: skeletons — уже снятые с потока заглушки (поверх), items — новые элементы.
 * Возвращает { cancel() } — мгновенно завершает анимации и убирает заглушки (повторная смена недели).
 */
export function runCascade(skeletons, items, { reduced = false } = {}) {
  const timing = cascadeTiming(items.length, skeletons.length, { reduced });
  const anims = [];
  if (typeof Element === 'undefined' || !Element.prototype.animate) {
    skeletons.forEach(s => s.remove());
    return { cancel() {}, finished: Promise.resolve() };
  }
  skeletons.forEach((s, i) => {
    const { delay, duration } = timing.skeletons[i];
    const a = s.animate([{ opacity: 1 }, { opacity: 0 }], { duration, delay, easing: 'ease-out', fill: 'both' });
    a.finished.then(() => s.remove(), () => {});
    anims.push(a);
  });
  const order = cascadeOrder(items.map(el => el.getBoundingClientRect()));
  order.forEach((index, rank) => {
    const { delay, duration } = timing.cards[rank];
    const frames = timing.shift ? [{ opacity: 0, transform: `translateY(${timing.shift}px)` }, { opacity: 1, transform: 'none' }] : [{ opacity: 0 }, { opacity: 1 }];
    anims.push(items[index].animate(frames, { duration, delay, easing: 'cubic-bezier(.2,0,0,1)', fill: 'backwards' }));
  });
  return {
    finished: Promise.allSettled(anims.map(a => a.finished)).then(() => {}),
    cancel() { for (const a of anims) { try { a.finish(); } catch { a.cancel(); } } skeletons.forEach(s => s.remove()); },
  };
}

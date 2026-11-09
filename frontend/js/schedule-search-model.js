import MiniSearch from '../vendor/minisearch/index.js';
import * as translitBundle from '../vendor/translit/bundle.js';
import { DAY_NAMES, dateKey, formatDate, parseDate } from './schedule-dates.js';

const translit = (translitBundle.default || globalThis.cyrillicToTranslit)();
const latinKeys = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./";
const russianKeys = 'ёйцукенгшщзхъфывапролджэячсмитьбю.';
const words = value => String(value).toLowerCase().normalize('NFKC').replace(/ё/g, 'е')
  .match(/[\p{L}\p{N}]+/gu) || [];
const plain = value => words(value).join(' ');
const latin = value => plain(translit.transform(value));
const swap = (value, from, to) => [...value].map(char => {
  const index = from.indexOf(char);
  return index === -1 ? char : to[index];
}).join('');

function queries(value) {
  const input = value.toLowerCase().normalize('NFKC');
  return [...new Set([
    plain(input), latin(input),
    plain(swap(input, latinKeys, russianKeys)),
    plain(swap(input, russianKeys, latinKeys)),
  ].filter(Boolean))];
}

export function indexSchedule(events) {
  const items = new Map();
  const documents = [];
  for (const event of events) {
    const date = parseDate(event.date);
    const raw = {
      name: event.club_name,
      teacher: (event.leader_names || [event.leader_name]).join(' '),
      room: (event.room_names || [event.room_name]).join(' '),
      context: [event.category_name, DAY_NAMES[date.getDay() - 1], formatDate(date), event.start_time].join(' '),
    };
    items.set(event.event_id, { event, raw });
    documents.push({
      id: event.event_id, date: dateKey(date),
      ...Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, [...new Set([plain(value), latin(value)])].join(' ')])),
    });
  }
  const index = new MiniSearch({
    fields: ['name', 'teacher', 'room', 'context'],
    storeFields: ['date'],
    tokenize: words,
    searchOptions: { combineWith: 'AND', boost: { name: 5, room: 4, teacher: 3, context: 1 } },
  });
  index.addAll(documents);

  return (value, day) => {
    const hits = new Map();
    queries(value).forEach((query, indexOfQuery) => {
      const results = index.search(query, {
        prefix: token => !/^\d+$/.test(token),
        fuzzy: token => token.length >= 4 && !/\d/.test(token) ? 0.22 : false,
        filter: result => !day || result.date === day,
      });
      for (const result of results) {
        const { event, raw } = items.get(result.id);
        const exact = Object.values(raw).map(text => [plain(text), latin(text)]);
        const exactRoom = /^\d+$/.test(query) && words(raw.room).includes(query);
        const exactName = exact[0].includes(query);
        const exactPhrase = exact.some(values => values.some(text => ` ${text} `.includes(` ${query} `)));
        const rank = exactRoom ? 4 : exactName ? 3 : exactPhrase ? 2 : query.split(' ').every(token => result.terms.some(term => term.startsWith(token))) ? 1 : 0;
        const candidate = { event, rank, score: result.score / (1 + indexOfQuery * 0.18), terms: result.terms };
        const old = hits.get(result.id);
        if (!old || rank > old.rank || (rank === old.rank && candidate.score > old.score)) hits.set(result.id, candidate);
      }
    });
    return [...hits.values()].sort((a, b) => b.rank - a.rank || b.score - a.score
      || a.event.date.localeCompare(b.event.date) || a.event.start_time.localeCompare(b.event.start_time));
  };
}

export function markedText(text, terms) {
  const fragment = document.createDocumentFragment();
  const used = new Set(terms);
  for (const part of String(text).split(/([\p{L}\p{N}]+)/u)) {
    if (!part) continue;
    if (used.has(plain(part)) || used.has(latin(part))) {
      const mark = document.createElement('mark');
      mark.textContent = part;
      fragment.append(mark);
    } else fragment.append(part);
  }
  return fragment;
}

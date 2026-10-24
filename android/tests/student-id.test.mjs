// node22: crypto global
const store = {}; globalThis.localStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => store[k] = String(v), removeItem: k => delete store[k] };
globalThis.window = globalThis; globalThis.document = { readyState: 'complete', documentElement: {}, addEventListener() {} };
globalThis.MutationObserver = class { observe() {} }; globalThis.location = { pathname: '/admin/x', search: '' };
globalThis.atob = s => Buffer.from(s, 'base64').toString('binary'); globalThis.btoa = s => Buffer.from(s, 'binary').toString('base64');
await import('../shim/app-student.js');
const sec = new Uint8Array(32).map((_, i) => i);
const id = await ItcStudent.computeId(sec, { last: 'Ёлкин', first: 'Пётр', middle: 'Иванович', group: '1исип-126' }); if (id !== 'S-5VAF-E45T-VUBA-2NQP-Q2RF-CVMF-PI') throw new Error('ID ≠ эталону Python: ' + id);
const c = ItcStudent.backupCode(sec); if (!Buffer.from(ItcStudent.parseBackup(c)).equals(Buffer.from(sec))) throw new Error('backup'); const id2 = await ItcStudent.computeId(sec, { last: 'Елкин', first: 'Петр', noMiddle: true, group: '1ИСИП-126' }); if (id2 === id) throw new Error('uniq'); if (Object.keys(ItcStudent.validate({ last: 'А', first: 'Б', noMiddle: true, group: '1ab-126' })).length !== 1) throw new Error('group re'); console.log('student-id: ok (совпадает с Python, уникален, резервный код)');

import {request} from '../api.js';
export function login() {
  throw new Error('Вход ещё не реализован. Доступ к API закрыт.');
}
export function getAdminStatus() { return request('/api/admin/status'); }

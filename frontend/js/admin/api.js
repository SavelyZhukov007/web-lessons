import { request } from '../api.js';

// request is async
export function login(login, password) {
  return request('/api/admin/login', {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      "login": login,
      "password": password
    })
  });
}

// POST /api/admin/logout
export function logout() {
  return request('/api/admin/logout', { method: "POST"});
}

export function getAdminStatus() { return request('/api/admin/status'); }
import { request } from '../api.js';
export async function login(body) {
  try {
    const response = await fetch("/api/admin/login", {
      method: "POST",
      headers: {
          "Content-Type": "application/json"
      },
      credentials: "same-origin",
      body: body
    })

    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(data?.detail || "Ошибка сервера: HTTP ${response.status}");
    }
    return data;

  } catch (error) {

  }
}
export function getAdminStatus() { return request('/api/admin/status'); }

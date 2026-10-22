import { login } from './api.js';

const form = document.querySelector("#login-form");
const message = document.querySelector("#message");
const submitButton = form.querySelector("button");

const ADMIN_PAGE_URL = "/admin/"; // хз что тут должно быть

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";

  const login = form.elements.login.value.trim() ?? "";
  const password = form.elements.password.value ?? "";

  submitButton.disabled = true;
  message.textContent = "Выполняется вход...";

  await login(JSON.stringify({
    login: login,
    password: password
  }));

  window.location.assign(ADMIN_PAGE_URL)
});

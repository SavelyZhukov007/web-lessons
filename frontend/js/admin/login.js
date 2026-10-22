import { login } from './api.js';

const form = document.querySelector("#login-form");
const message = document.querySelector("#message");
const submitButton = form.querySelector("button")

const ADMIN_PAGE_URL = "/admin/"; // valid url goes here

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  message.textContent = "";

  const lgn = form.elements.login.value.trim() ?? "";
  const password = form.elements.password.value ?? "";

  submitButton.disabled = true;
  message.textContent = "Выполняется вход...";

  try {
    await login(lgn, password);
    window.location.assign(ADMIN_PAGE_URL);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  };
});

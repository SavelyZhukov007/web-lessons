// Optional UI, loaded only when the notification sheet is open. Never asks permission.
export function mountScheduleNotificationForm(container, { load, save }) {
  const form = document.createElement("form");
  form.className = "personal-notification-form";
  const title = document.createElement("h3");
  title.textContent = "Расписание уведомлений";
  form.append(title);
  const fields = {};
  for (const [key, label, type, value] of [
    ["reminder_minutes", "Напомнить за N минут (0 — выключено)", "number", 0],
    ["quiet_enabled", "Тихие часы", "checkbox", false],
    ["quiet_start", "Начало тихих часов (МСК)", "time", "22:00"],
    ["quiet_end", "Конец тихих часов (МСК)", "time", "08:00"],
    ["digest_enabled", "Утренний дайджест «Моих кружков»", "checkbox", false],
    ["digest_time", "Время дайджеста (МСК)", "time", "08:00"],
  ]) {
    const row = document.createElement("label");
    row.className = "preference-toggle";
    const text = document.createElement("span");
    text.textContent = label;
    const input = document.createElement("input");
    input.type = type;
    input.name = key;
    if (type === "checkbox") input.checked = value;
    else input.value = value;
    if (type === "number") {
      input.min = "0";
      input.max = "120";
      input.step = "1";
      input.required = true;
    }
    if (type === "time") input.required = true;
    row.append(text, input);
    form.append(row);
    fields[key] = input;
  }
  const hint = document.createElement("p");
  hint.className = "field-hint";
  hint.textContent =
    "Время — московское. Во время тихих часов изменения дождутся окончания; просроченные напоминания не отправляются. На iPhone доставка зависит от установленного PWA и системных настроек.";
  const button = document.createElement("button");
  button.type = "submit";
  button.className = "btn btn--tonal";
  button.textContent = "Сохранить расписание уведомлений";
  const status = document.createElement("p");
  status.className = "field-hint";
  status.setAttribute("role", "status");
  form.append(hint, button, status);
  container.append(form);
  const busy = (v) => {
    button.disabled = v;
    Object.values(fields).forEach((f) => (f.disabled = v));
  };
  async function refresh() {
    busy(true);
    try {
      const s = await load();
      if (!s) {
        status.textContent = "Сначала включите push-уведомления.";
        return;
      }
      for (const [k, f] of Object.entries(fields))
        if (k in s) {
          if (f.type === "checkbox") f.checked = s[k];
          else f.value = s[k];
        }
      status.textContent = "";
      busy(false);
    } catch {
      status.textContent =
        "Не удалось загрузить настройки. Проверьте соединение.";
    }
  }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!form.reportValidity()) return;
    const v = Object.fromEntries(
      Object.entries(fields).map(([k, f]) => [
        k,
        f.type === "checkbox"
          ? f.checked
          : f.type === "number"
            ? Number(f.value)
            : f.value,
      ]),
    );
    if (v.quiet_enabled && v.quiet_start === v.quiet_end) {
      status.textContent = "Начало и конец тихих часов должны отличаться";
      return;
    }
    busy(true);
    try {
      await save(v);
      status.textContent = "Настройки уведомлений сохранены";
    } catch {
      status.textContent =
        "Не удалось сохранить настройки. Повторите при подключении.";
    } finally {
      busy(false);
    }
  });
  refresh();
  return { refresh };
}

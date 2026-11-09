import {
  favorites,
  toggleFavorite,
  liveState,
} from "./personal-schedule-model.js";
export function favoriteControls(event) {
  const root = document.createElement("div");
  const error = document.createElement("p");
  error.className = "field-hint"; error.setAttribute("role", "status"); error.hidden = true;
  root.className = "schedule-event-actions favorite-actions";
  for (const [kind, ids, names, label] of [
    [
      "leaders",
      event.leader_ids || [event.leader_id],
      event.leader_names || [event.leader_name],
      "Руководитель",
    ],
    [
      "rooms",
      event.room_ids || [event.room_id],
      event.room_names || [event.room_name],
      "Аудитория",
    ],
  ]) {
    ids.forEach((id, i) => {
      if (!Number.isInteger(id) || id <= 0) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "glass-action";
      button.dataset.favorite = kind + ":" + id;
      const paint = () => {
        const on = favorites(kind).some((x) => x.id === id);
        button.setAttribute("aria-pressed", String(on));
        button.textContent = (on ? "★ " : "☆ ") + label + ": " + names[i];
      };
      paint();
      button.addEventListener("click", () => {
        try {
          toggleFavorite(kind, id, names[i]);
          error.hidden = true; error.textContent = "";
          paint();
          window.dispatchEvent(new CustomEvent("kc:favorites"));
        } catch (e) {
          error.textContent = e.message; error.hidden = false;
          window.ItcFeatures?.toast?.(e.message);
        }
      });
      root.append(button);
    });
  }
  root.append(error);
  return root;
}
let mounted = false;
export function markLiveCard(card, event) {
  card.dataset.liveEvent = JSON.stringify({
    date: event.date,
    start_time: event.start_time,
    end_time: event.end_time,
    status: event.status,
    ghost: event.ghost,
  });
  card.dataset.liveBaseLabel = card.getAttribute("aria-label") || "";
  card.classList.add("has-live-status");
  const label = document.createElement("span");
  label.className = "event-live";
  label.setAttribute("aria-live", "off");
  const bar = document.createElement("span");
  bar.className = "event-live-progress";
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-label", "Ход занятия или ожидания начала");
  bar.setAttribute("aria-valuemin", "0");
  bar.setAttribute("aria-valuemax", "100");
  card.append(label, bar);
  paint(card);
  if (!mounted) {
    mounted = true;
    setInterval(() => {
      if (!document.hidden) refresh();
    }, 30000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) refresh();
    });
  }
}
function paint(card) {
  const s = liveState(JSON.parse(card.dataset.liveEvent));
  const l = card.querySelector(".event-live"),
    b = card.querySelector(".event-live-progress");
  l.textContent = s?.label || "";
  l.hidden = !s;
  b.hidden = !s;
  card.dataset.liveKind = s?.kind || "";
  // No live-region announcements on the 30s timer; the focused card still has a complete name.
  if (card.dataset.liveBaseLabel) {
    const status = s?.kind === "soon" ? "Начнётся в ближайшие 15 минут" : s?.label;
    const name = card.dataset.liveBaseLabel + (status ? ". " + status : "");
    if (card.getAttribute("aria-label") !== name) card.setAttribute("aria-label", name);
  }
  if (s) {
    b.style.transform = `scaleX(${s.progress})`;
    b.setAttribute("aria-valuenow", String(Math.round(s.progress * 100)));
  }
}
function refresh() {
  document.querySelectorAll("[data-live-event]").forEach(paint);
}
export function favoritesSection(h) {
  const section = h(
    "section",
    { class: "sheet-section", dataset: { favoritesSection: "" } },
    h("h3", {}, "Избранные руководители и аудитории"),
  );
  for (const kind of ["leaders", "rooms"]) {
    const list = favorites(kind);
    for (const item of list) {
      const remove = h(
        "button",
        {
          type: "button",
          class: "btn btn--text",
          "aria-label": "Убрать из избранного: " + item.name,
        },
        "Убрать",
      );
      const row = h(
        "div",
        { class: "favorite-setting-row" },
        h(
          "a",
          {
            href:
              "/?" +
              (kind === "leaders" ? "leader_id" : "room_id") +
              "=" +
              item.id,
          },
          item.name,
        ),
        remove,
      );
      remove.addEventListener("click", () => {
        try {
          toggleFavorite(kind, item.id, item.name);
          row.remove();
          window.dispatchEvent(new CustomEvent("kc:favorites"));
        } catch {}
      });
      section.append(row);
    }
  }
  if (section.children.length === 1)
    section.append(
      h(
        "p",
        { class: "field-hint" },
        "Добавляйте звёздочкой в подробностях занятия. Избранное хранится на этом устройстве.",
      ),
    );
  return section;
}
let lastWeekInfo;
window.addEventListener("offline", () =>
  publishWeekStatus(
    lastWeekInfo
      ? { ...lastWeekInfo, source: "cache", failed: true }
      : { source: "cache", failed: true },
  ),
);
export function publishWeekStatus(info) {
  if (!document.body.classList.contains("schedule-page")) return;
  lastWeekInfo = info;
  let el = document.getElementById("schedule-cache-status");
  if (!el) {
    el = document.createElement("p");
    el.id = "schedule-cache-status";
    el.className = "field-hint offline-data-badge";
    el.setAttribute("role", "status");
    document.getElementById("content")?.before(el);
  }
  const cached = info?.source === "cache";
  el.hidden = !cached;
  const savedAt = info?.savedAt ?? info?.time;
  const stamp = Number.isFinite(savedAt) && savedAt > 0
    ? new Date(savedAt).toLocaleString("ru-RU", {
        timeZone: "Europe/Moscow",
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
  el.textContent = cached
    ? (stamp ? "Данные от " + stamp + " (МСК)" : "Сохранённой недели нет") +
      (info.failed || info.offline || navigator.onLine === false
        ? " · нет сети"
        : " · обновляем…")
    : "";
  if (info?.failed || info?.offline) document.documentElement.classList.add("itc-offline");
  else if (!cached && navigator.onLine !== false)
    document.documentElement.classList.remove("itc-offline");
  document.getElementById("itc-offline-banner")?.remove();
}

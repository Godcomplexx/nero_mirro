// neuro_mirror/web/static/js/components/check-list.js
//
// Equipment status rows (camera, face + light, microphone, voice probe) for
// the session-condition check. State is shown by icon shape + text, never by
// color alone (deck slide 2). Styles: css/components/check-list.css.

const LABELS = {
  camera: "Камера",
  face: "Лицо в кадре и освещение",
  mic: "Микрофон",
  voice: "Проба голоса",
};

const ICONS = { ok: "✓", warn: "!", fail: "✕", wait: "…", idle: "•" };

const STATE_TEXT = {
  ok: "в порядке",
  warn: "есть замечание",
  fail: "не пройдено",
  wait: "проверяется",
  idle: "ещё не проверено",
};

// requirements: { camera, face, mic, voice } booleans; items: name → { state, note }
export function renderCheckList(list, requirements, items) {
  list.innerHTML = "";
  for (const name of Object.keys(LABELS)) {
    if (!requirements[name]) continue;
    const item = items[name] || { state: "idle", note: "" };
    const row = document.createElement("li");
    row.className = "nm-check";
    row.dataset.state = item.state;

    const icon = document.createElement("span");
    icon.className = "nm-check-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = ICONS[item.state] || "•";

    const copy = document.createElement("div");
    copy.className = "nm-check-copy";
    const title = document.createElement("strong");
    title.className = "nm-check-title";
    title.textContent = LABELS[name];
    const sr = document.createElement("span");
    sr.className = "nm-visually-hidden";
    sr.textContent = ` — ${STATE_TEXT[item.state]}`;
    title.appendChild(sr);
    const note = document.createElement("span");
    note.className = "nm-check-note";
    note.textContent = item.note || STATE_TEXT[item.state];
    copy.append(title, note);

    row.append(icon, copy);
    list.appendChild(row);
  }
}

// neuro_mirror/web/static/js/components/notify.js
//
// App-wide notice shown under the header: what went wrong and what to do
// next (deck slide 2: errors are worded neutrally and say how to fix them).
// It stays until the person closes it — no auto-hiding toasts, which are easy
// to miss for users 58+. Styles: css/components/notice.css.
//
// app.js (a classic script) reaches it through window.nmNotify.

const HOST_ID = "nm-notices";
const MAX_VISIBLE = 3;

function host() {
  let node = document.getElementById(HOST_ID);
  if (!node) {
    node = document.createElement("div");
    node.id = HOST_ID;
    node.className = "nm-notices";
    document.body.appendChild(node);
  }
  return node;
}

// kind: "error" | "info"
export function notify(message, { kind = "error" } = {}) {
  const text = String(message || "").trim();
  if (!text) return;
  const container = host();
  // The same message is not stacked twice
  for (const existing of container.children) {
    if (existing.dataset.message === text) return;
  }
  while (container.children.length >= MAX_VISIBLE) container.firstChild.remove();

  const notice = document.createElement("div");
  notice.className = "nm-notice";
  notice.dataset.kind = kind;
  notice.dataset.message = text;
  notice.setAttribute("role", kind === "error" ? "alert" : "status");

  const icon = document.createElement("span");
  icon.className = "nm-notice-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = kind === "error" ? "!" : "i";

  const body = document.createElement("p");
  body.className = "nm-notice-text";
  body.textContent = text;

  const close = document.createElement("button");
  close.type = "button";
  close.className = "nm-btn nm-btn-secondary nm-notice-close";
  close.textContent = "Понятно";
  close.addEventListener("click", () => notice.remove());

  notice.append(icon, body, close);
  container.appendChild(notice);
}

export function clearNotices() {
  const node = document.getElementById(HOST_ID);
  if (node) node.innerHTML = "";
}

window.nmNotify = notify;

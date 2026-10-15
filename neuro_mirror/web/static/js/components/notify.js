// neuro_mirror/web/static/js/components/notify.js
//
// App-wide notice shown under the header: what went wrong and what to do
// next (deck slide 2: errors are worded neutrally and say how to fix them).
// An error stays until the person closes it — an auto-hiding toast is easy to
// miss for users 58+. A confirmation (kind "info", e.g. «Согласие дано») only
// confirms what the person has just done and goes away by itself after
// INFO_HIDE_MS, or earlier with «Понятно»; it waits while it is pointed at or
// focused. Styles: css/components/notice.css.
//
// app.js (a classic script) reaches it through window.nmNotify.

const HOST_ID = "nm-notices";
const MAX_VISIBLE = 3;
const INFO_HIDE_MS = 3000;
const LEAVE_MS = 250; // css/components/notice.css: .nm-notice.is-leaving

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
    if (existing.dataset.message === text && !existing.classList.contains("is-leaving")) return;
  }
  const shown = () => [...container.children].filter((node) => !node.classList.contains("is-leaving"));
  while (shown().length >= MAX_VISIBLE) dismiss(shown()[0]);

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
  close.addEventListener("click", () => dismiss(notice));

  notice.append(icon, body, close);
  container.appendChild(notice);
  if (kind === "info") hideLater(notice);
}

function hideLater(notice) {
  let timer = null;
  const start = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (notice.matches(":hover, :focus-within")) start();
      else dismiss(notice);
    }, INFO_HIDE_MS);
  };
  start();
}

// Fades the notice out, then the ones below close up (their height shrinks
// together with the fade, so nothing jumps)
export function dismiss(notice) {
  if (!notice || !notice.isConnected || notice.classList.contains("is-leaving")) return;
  notice.style.height = `${notice.offsetHeight}px`;
  void notice.offsetHeight; // start the transition from the current height
  notice.classList.add("is-leaving");
  setTimeout(() => notice.remove(), LEAVE_MS);
}

export function clearNotices() {
  const node = document.getElementById(HOST_ID);
  if (node) node.innerHTML = "";
}

window.nmNotify = notify;

// neuro_mirror/web/static/js/shell.js
//
// Persistent app shell: sidebar navigation + header + work-area section
// switcher for the new sidebar-app UI. Loaded as a native ES module (no
// bundler in this project). Every section is either a migrated screen
// (js/screens/*) or a stub for functionality the backend doesn't have yet.

import { confirmDialog } from "./components/confirm-dialog.js";
import { screeningScreen } from "./screens/screening.js";
import { hadsScreen } from "./screens/hads.js";
import { mocaScreen } from "./screens/moca.js";
import { reportsScreen } from "./screens/reports.js";
import { serviceScreen } from "./screens/service.js";
import { tasksScreen } from "./screens/tasks.js";
import { trainingScreen } from "./screens/training.js";
// Registers window.nmNotify for app.js (a classic script cannot import)
import "./components/notify.js";
import { loadTrainingPlan } from "./core/training.js";
import { hadsController } from "./core/hads-controller.js";
import { mocaController } from "./core/moca-controller.js";

// A section either shows a stub or hosts a migrated screen (`screen`:
// { mount(container), unmount(), isBusy(), leaveWarning() } from
// js/screens/*). `hidden` sections are reachable by link, not the sidebar.
const SECTIONS = [
  {
    id: "home",
    label: "Главное меню",
    icon: "home",
  },
  {
    id: "screening",
    label: "Базовый скрининг",
    icon: "clipboard",
    description: "Проверка оборудования, видеоанализ и оценка самочувствия.",
    screen: screeningScreen,
  },
  {
    id: "hads",
    label: "Проверка самочувствия",
    icon: "heart",
    description: "Тест на тревожность (шкала HADS) и оценка самочувствия.",
    screen: hadsScreen,
  },
  {
    id: "moca",
    label: "Когнитивный тест",
    icon: "brain",
    description: "Голосовой тест MoCA — 11 заданий с голосовыми инструкциями.",
    screen: mocaScreen,
  },
  {
    id: "tasks",
    label: "Задачи",
    icon: "list",
    description: "Библиотека социально-бытовых задач.",
    screen: tasksScreen,
  },
  {
    id: "training",
    label: "Тренировка",
    icon: "activity",
    description: "Тренируйте когнитивные функции с учётом ваших результатов.",
    // The home card starts locked and unlocks once the server has a MoCA
    // report (renderHomeSection); the screen shows the same state itself.
    locked: true,
    lockedReason: "Сначала пройдите когнитивный тест",
    screen: trainingScreen,
  },
  {
    id: "reports",
    label: "Отчёты",
    icon: "chart",
    description: "Последние результаты и история сессий.",
    screen: reportsScreen,
  },
  {
    id: "service",
    label: "Устройства и сведения",
    icon: "list",
    hidden: true,
    screen: serviceScreen,
  },
];

// Card order on Главное меню follows the deck's grid (row by row), which
// differs from the sidebar order.
const HOME_CARD_ORDER = ["screening", "moca", "tasks", "training", "reports", "hads"];

const ICONS = {
  home: '<path d="M12 3l9 8h-3v9h-5v-6H11v6H6v-9H3z"/>',
  clipboard: '<path d="M9 2h6a1 1 0 011 1v1h2a1 1 0 011 1v15a1 1 0 01-1 1H6a1 1 0 01-1-1V5a1 1 0 011-1h2V3a1 1 0 011-1zm1 2v1h4V4h-4zM8 11h8v2H8v-2zm0 4h8v2H8v-2z"/>',
  heart: '<path d="M12 21s-7.5-5-10-9.5C.5 8 2 4 6 4c2.2 0 3.7 1.2 4.5 2.3C11.3 5.2 12.8 4 15 4c4 0 5.5 4 4 7.5C19.5 16 12 21 12 21z"/>',
  brain: '<path d="M12 2C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7zM9 21h6v-1H9v1z"/>',
  list: '<path d="M4 5h2v2H4V5zm4 0h12v2H8V5zM4 11h2v2H4v-2zm4 0h12v2H8v-2zm-4 6h2v2H4v-2zm4 0h12v2H8v-2z"/>',
  activity: '<path d="M3 12h4l2.5-7 5 14 2.5-7h4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  chart: '<path d="M4 20V10h3v10H4zm6.5 0V4h3v16h-3zM17 20v-7h3v7h-3z"/>',
  lock: '<path d="M17 9h-1V7a4 4 0 00-8 0v2H7a2 2 0 00-2 2v9a2 2 0 002 2h10a2 2 0 002-2v-9a2 2 0 00-2-2zm-7-2a2 2 0 014 0v2h-4V7zm2 10a2 2 0 110-4 2 2 0 010 4z"/>',
};

function renderStaticPlaceholder(message) {
  const wrap = document.createElement("div");
  wrap.className = "nm-placeholder";
  wrap.textContent = message;
  return wrap;
}

function buildHomeCard(section, locked = Boolean(section.locked)) {
  const card = document.createElement("article");
  card.className = locked ? "nm-card nm-card-locked" : "nm-card";

  const head = document.createElement("div");
  head.className = "nm-card-head";

  const iconWrap = document.createElement("div");
  iconWrap.className = "nm-card-icon";
  const icon = locked ? ICONS.lock : ICONS[section.icon];
  iconWrap.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${icon}</svg>`;
  head.appendChild(iconWrap);

  const text = document.createElement("div");
  const title = document.createElement("h2");
  title.className = "nm-card-title";
  title.textContent = section.label;
  text.appendChild(title);

  // Deck: a locked card states the reason as its description text, so the
  // status is never conveyed by the grey color alone.
  const desc = document.createElement("p");
  desc.className = "nm-card-desc";
  desc.textContent = locked ? section.lockedReason : section.description || "";
  text.appendChild(desc);
  head.appendChild(text);
  card.appendChild(head);

  const button = document.createElement("button");
  button.type = "button";
  button.className = "nm-card-action";
  button.textContent = "Открыть →";
  if (locked) {
    button.disabled = true;
  } else {
    button.addEventListener("click", () => {
      selectSection(section.id);
    });
  }
  card.appendChild(button);

  return card;
}

function buildResumeBanner(session) {
  const banner = document.createElement("div");
  banner.className = "nm-resume-banner";
  const text = document.createElement("span");
  text.textContent = "У вас есть незавершённая сессия.";
  banner.appendChild(text);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nm-card-action";
  button.textContent = "Продолжить сессию";
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Продолжаю...";
    try {
      // Same as the old menu's "resume" item: unlock audio first so the
      // resumed test's voiced instructions are allowed to play.
      if (window.unlockAudioPlayback) await window.unlockAudioPlayback().catch(() => {});
      const resp = await fetch(`/api/sessions/${encodeURIComponent(session.session_id)}/resume`, {
        method: "POST",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      banner.remove();
    } catch (_) {
      button.disabled = false;
      button.textContent = "Продолжить сессию";
      text.textContent = "Не удалось продолжить сессию. Попробуйте ещё раз.";
    }
  });
  banner.appendChild(button);
  return banner;
}

async function loadResumeBanner(slot) {
  try {
    const resp = await fetch("/api/sessions/incomplete");
    if (!resp.ok) return;
    const data = await resp.json();
    const items = (data.items || []).filter((item) => item.status === "interrupted");
    if (!items.length) return;
    // The user may have navigated to a different section while this fetch
    // was in flight — only render if the slot is still on screen.
    if (!document.body.contains(slot)) return;
    slot.appendChild(buildResumeBanner(items[0]));
  } catch (_) {
    // Soft, non-blocking convenience banner — silent on failure.
  }
}

// A profile must be chosen before anything else. app.js owns that state
// (its `state.activeUser` is not reachable from a module), but it reliably
// toggles #user-chip's `hidden` attribute via updateUserChip() whenever a
// profile becomes active — so the chip is the single signal the shell reads.
function hasActiveUser() {
  const chip = document.getElementById("user-chip");
  return Boolean(chip && !chip.hidden);
}

function renderHomeSection() {
  const wrap = document.createElement("div");
  if (!hasActiveUser()) {
    // The #user-gate form sits on top of the work area at this point; this
    // text is only what shows through if the gate is still loading.
    wrap.appendChild(renderStaticPlaceholder("Выберите профиль или создайте новый, чтобы продолжить."));
    return wrap;
  }

  const subtitle = document.createElement("p");
  subtitle.className = "nm-workarea-subtitle";
  subtitle.textContent = "Выберите сценарий работы";
  wrap.appendChild(subtitle);

  const bannerSlot = document.createElement("div");
  wrap.appendChild(bannerSlot);
  loadResumeBanner(bannerSlot);

  const grid = document.createElement("div");
  grid.className = "nm-card-grid";
  for (const id of HOME_CARD_ORDER) {
    grid.appendChild(buildHomeCard(SECTIONS.find((section) => section.id === id)));
  }
  wrap.appendChild(grid);
  unlockTrainingCard(grid);

  // Camera/microphone selection and the app version: a service page that is
  // not part of the deck's navigation, so it is linked from here.
  const service = document.createElement("button");
  service.type = "button";
  service.className = "nm-link-button";
  service.textContent = "Устройства и сведения о программе";
  service.addEventListener("click", () => selectSection("service"));
  wrap.appendChild(service);

  return wrap;
}

async function unlockTrainingCard(grid) {
  const info = await loadTrainingPlan();
  if (!info.unlocked || !grid.isConnected) return;
  const training = SECTIONS.find((section) => section.id === "training");
  const index = HOME_CARD_ORDER.indexOf("training");
  const old = grid.children[index];
  if (old) grid.replaceChild(buildHomeCard(training, false), old);
}

function renderSectionBody(section) {
  if (section.id === "home") return renderHomeSection();
  if (section.screen) {
    const container = document.createElement("div");
    container.className = "nm-screen";
    section.screen.mount(container);
    return container;
  }
  return renderStaticPlaceholder(section.description || "");
}

function buildNavItem(section) {
  const li = document.createElement("li");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "nm-nav-item";
  button.dataset.section = section.id;
  button.innerHTML =
    `<svg class="nm-nav-item-icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[section.icon]}</svg>` +
    `<span class="nm-nav-item-label">${section.label}</span>`;
  button.addEventListener("click", () => {
    // No profile yet: sections are unavailable — say so instead of silently
    // doing nothing
    if (profileRequired()) {
      showProfileRequiredNotice();
      return;
    }
    // Leaving the "switch profile" form open under a newly opened section
    // would hide it; the current profile stays active until another is picked.
    if (window.closeUserGate) window.closeUserGate();
    selectSection(section.id);
  });
  li.appendChild(button);
  return li;
}

function renderSidebar() {
  const nav = document.getElementById("nm-sidebar-nav");
  if (!nav) return;
  nav.innerHTML = "";
  for (const section of SECTIONS) {
    if (!section.hidden) nav.appendChild(buildNavItem(section));
  }
}

// ---- Where the user is, kept in the address (#section[/profile|/profile-new])
// so a page reload returns to the same place instead of Главное меню. ----

const GATE_STATES = ["profile", "profile-new"];

function readLocation() {
  const [section = "", gate = ""] = window.location.hash.replace(/^#/, "").split("/");
  return {
    section: SECTIONS.some((item) => item.id === section) ? section : "home",
    gate: GATE_STATES.includes(gate) ? gate : "",
  };
}

function writeLocation(section, gate) {
  const hash = gate ? `#${section}/${gate}` : section === "home" ? "" : `#${section}`;
  if (window.location.hash === hash || (!hash && !window.location.hash)) return;
  const url = `${window.location.pathname}${window.location.search}${hash}`;
  window.history.replaceState(null, "", url);
}

const initialLocation = readLocation();
let currentSectionId = "home";

function markCurrentNav(sectionId) {
  for (const button of document.querySelectorAll(".nm-nav-item")) {
    if (button.dataset.section === sectionId) {
      button.setAttribute("aria-current", "page");
    } else {
      button.removeAttribute("aria-current");
    }
  }
}

function renderPendingSection(sectionId) {
  const section = SECTIONS.find((item) => item.id === sectionId);
  const title = document.getElementById("nm-workarea-title");
  const content = document.getElementById("nm-workarea-content");
  if (title) title.textContent = section ? section.label : "";
  if (content) content.innerHTML = "";
  markCurrentNav(sectionId);
}
// The section the user asked for; kept while no profile is active yet (e.g.
// right after a reload) so it opens as soon as the profile is picked up.
let requestedSectionId = initialLocation.section;
let gateState = "";
// Profile form that was open before a reload; kept in the address until it
// has been reopened, so nothing overwrites it in the meantime.
let pendingGate = initialLocation.gate;
let restoringGate = false;

async function selectSection(sectionId, { focus = true, force = false } = {}) {
  if (!SECTIONS.some((item) => item.id === sectionId)) return;
  requestedSectionId = sectionId;
  // Nothing but the profile gate is reachable until a profile is active.
  // Until then (e.g. the first moment after a reload) show the requested
  // section's name over an empty work area — not Главное меню, which would
  // flash before the real section opens.
  if (!hasActiveUser()) {
    renderPendingSection(sectionId);
    return;
  }
  const section = SECTIONS.find((item) => item.id === sectionId);

  const current = SECTIONS.find((item) => item.id === currentSectionId);
  const leaving = current && current.screen && sectionId !== currentSectionId;
  // Deck: leaving an unfinished test asks for confirmation first
  if (leaving && !force && current.screen.isBusy()) {
    const warning = current.screen.leaveWarning();
    const confirmed = await confirmDialog({
      title: warning.title,
      message: warning.message,
      confirmLabel: "Перейти",
      cancelLabel: "Остаться",
    });
    if (!confirmed) return;
  }
  if (current && current.screen) current.screen.unmount();
  currentSectionId = sectionId;
  if (hasActiveUser()) writeLocation(sectionId, pendingGate || gateState);

  markCurrentNav(sectionId);

  const title = document.getElementById("nm-workarea-title");
  const content = document.getElementById("nm-workarea-content");
  if (title) title.textContent = section.label;
  if (content) {
    content.innerHTML = "";
    content.appendChild(renderSectionBody(section));
  }
  // Deck requirement: moving between sections moves focus to the work-area
  // heading so screen-reader / keyboard users always know where they are.
  if (title && focus) title.focus();
}

// The menu starts collapsed (index.html); a menu opened by the person stays
// open after a reload — the choice is kept in this browser
const SIDEBAR_KEY = "nm-sidebar-collapsed";

function initSidebarToggle() {
  const sidebar = document.getElementById("nm-sidebar");
  const toggle = document.getElementById("nm-sidebar-toggle");
  const label = toggle ? toggle.querySelector(".nm-sidebar-toggle-label") : null;
  if (!sidebar || !toggle) return;

  const apply = (collapsed) => {
    sidebar.dataset.collapsed = collapsed ? "true" : "false";
    // Mirrored on <body> so the profile form (#user-gate, css/screens/welcome.css)
    // lines up with the sidebar's current width.
    document.body.dataset.nmSidebarCollapsed = sidebar.dataset.collapsed;
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    if (label) label.textContent = collapsed ? "Развернуть меню" : "Свернуть меню";
  };

  let saved = null;
  try {
    saved = window.localStorage.getItem(SIDEBAR_KEY);
  } catch (_) {
    // storage unavailable — the menu simply starts collapsed
  }
  apply(saved !== "false");

  toggle.addEventListener("click", () => {
    const collapsed = sidebar.dataset.collapsed !== "true";
    apply(collapsed);
    try {
      window.localStorage.setItem(SIDEBAR_KEY, collapsed ? "true" : "false");
    } catch (_) {
      // not remembered — fine
    }
  });
}

// Shown above the profile picker when a section is clicked before a profile
// is chosen. Plain text in a status region: no blinking, read by screen readers.
function showProfileRequiredNotice() {
  const panel = document.querySelector("#user-gate .user-gate-panel");
  if (!panel) return;
  let notice = document.getElementById("nm-profile-required");
  if (!notice) {
    notice = document.createElement("p");
    notice.id = "nm-profile-required";
    notice.className = "nm-gate-notice";
    notice.setAttribute("role", "status");
    panel.prepend(notice);
  }
  notice.textContent = "Сначала выберите профиль или создайте новый — после этого откроются все разделы.";
}

// A profile must be picked: no active profile and the picker is on screen.
// (Right after a reload neither is known yet — the menu is not greyed out
// for that moment, so nothing flickers.)
function profileRequired() {
  const gate = document.getElementById("user-gate");
  return !hasActiveUser() && Boolean(gate) && !gate.hidden;
}

function syncNavAvailability() {
  const available = !profileRequired();
  for (const button of document.querySelectorAll(".nm-nav-item")) {
    if (available) {
      button.removeAttribute("aria-disabled");
      button.removeAttribute("title");
    } else {
      button.setAttribute("aria-disabled", "true");
      button.title = "Сначала выберите профиль";
    }
  }
  if (available) {
    const notice = document.getElementById("nm-profile-required");
    if (notice) notice.remove();
  }
}

function syncShellToActiveUser() {
  syncNavAvailability();
  selectSection(requestedSectionId, { focus: false, force: true });
  if (hasActiveUser()) restorePendingGate();
}

// A test the server starts without the user opening its screen (resumed
// session, chained HADS after the user left the screening) must still be
// visible: open its screen when the test begins.
function followServerTests() {
  let hadsStatus = hadsController.state.status;
  hadsController.subscribe((state) => {
    const started = state.status === "running" && hadsStatus !== "running";
    hadsStatus = state.status;
    if (!started) return;
    if (currentSectionId === "hads") return;
    if (currentSectionId === "screening" && screeningScreen.ownsHads()) return;
    selectSection(screeningScreen.ownsHads() ? "screening" : "hads", { force: true });
  });
  let mocaStatus = mocaController.state.status;
  mocaController.subscribe((state) => {
    const started = state.status === "running" && mocaStatus !== "running";
    mocaStatus = state.status;
    if (started && currentSectionId !== "moca") selectSection("moca", { force: true });
  });
}

function watchActiveUser() {
  const chip = document.getElementById("user-chip");
  if (!chip) return;
  // Fires on first pick, on creation of a new profile, on the silent pickup
  // of an already-active profile after a page reload (chip unhidden), and on
  // switching to another profile (chip name text replaced) — so per-user
  // content such as the resume banner is always for the current profile.
  new MutationObserver(syncShellToActiveUser).observe(chip, {
    attributes: true,
    attributeFilter: ["hidden"],
    subtree: true,
    childList: true,
    characterData: true,
  });
}

async function initMicIndicator() {
  const dot = document.getElementById("nm-mic-status-dot");
  const text = document.getElementById("nm-mic-status-text");
  if (!dot || !text) return;

  const applyState = (state) => {
    if (state === "granted") {
      dot.dataset.state = "on";
      text.textContent = "Микрофон включён";
    } else if (state === "denied") {
      dot.dataset.state = "off";
      text.textContent = "Микрофон выключен";
    } else {
      dot.dataset.state = "unknown";
      text.textContent = "Микрофон: неизвестно";
    }
  };

  if (!navigator.permissions || !navigator.permissions.query) {
    applyState("unknown");
    return;
  }
  try {
    const status = await navigator.permissions.query({ name: "microphone" });
    applyState(status.state);
    status.addEventListener("change", () => applyState(status.state));
  } catch (_) {
    // Some browsers (e.g. Firefox) don't support the "microphone" permission
    // name — this is a soft-fail, not an error the user needs to see.
    applyState("unknown");
  }
}

// ---- Profile form (#user-gate, driven by app.js): survive a reload ----------

const DRAFT_KEY = "nm-new-user-draft";

function readDraft() {
  try {
    return JSON.parse(window.sessionStorage.getItem(DRAFT_KEY) || "{}");
  } catch (_) {
    return {};
  }
}

function saveDraft(patch) {
  try {
    window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ ...readDraft(), ...patch }));
  } catch (_) {
    // Storage unavailable (private mode) — the form simply starts empty
  }
}

function clearDraft() {
  try {
    window.sessionStorage.removeItem(DRAFT_KEY);
  } catch (_) {
    // nothing to clear
  }
}

// Name and avatar only. Consents are never restored: the person has to tick
// them again themselves.
function restoreDraft() {
  const draft = readDraft();
  const input = document.getElementById("user-name-input");
  if (input && draft.name && !input.value) {
    input.value = draft.name;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  if (draft.avatar) {
    const option = document.querySelector(`#avatar-picker .avatar-option[data-preset-id="${draft.avatar}"]`);
    if (option) option.click();
  }
}

function currentGateState() {
  const gate = document.getElementById("user-gate");
  if (!gate || gate.hidden) return "";
  const createView = document.getElementById("user-create-view");
  return createView && !createView.hidden ? "profile-new" : "profile";
}

// Reopens the profile form that was open before a reload (once).
async function restorePendingGate() {
  if (!pendingGate || restoringGate || !window.openUserGate) return;
  restoringGate = true;
  const wanted = pendingGate;
  try {
    const gate = document.getElementById("user-gate");
    if (gate && gate.hidden) await window.openUserGate();
    if (wanted === "profile-new") window.showUserGateView("create");
  } finally {
    pendingGate = "";
    restoringGate = false;
    syncProfileGate();
  }
}

function syncProfileGate() {
  syncNavAvailability();
  const state = currentGateState();
  if (state === "profile-new") restoreDraft();
  // Closed by the user (or after the profile was created): forget the draft
  if (!state && gateState && !restoringGate && !pendingGate) clearDraft();
  gateState = state;
  if (restoringGate) return;
  writeLocation(hasActiveUser() ? currentSectionId : requestedSectionId, pendingGate || state);
}

function watchProfileGate() {
  const gate = document.getElementById("user-gate");
  const createView = document.getElementById("user-create-view");
  if (!gate || !createView) return;

  const input = document.getElementById("user-name-input");
  if (input) input.addEventListener("input", () => saveDraft({ name: input.value }));
  const picker = document.getElementById("avatar-picker");
  if (picker) {
    picker.addEventListener("click", (event) => {
      const option = event.target.closest(".avatar-option");
      if (option) saveDraft({ avatar: option.dataset.presetId });
    });
  }

  const observer = new MutationObserver(() => {
    // No profile yet: app.js opens the gate by itself — switch it to the
    // form that was open before the reload
    if (pendingGate && !hasActiveUser() && !gate.hidden) {
      const wanted = pendingGate;
      pendingGate = "";
      if (wanted === "profile-new") window.showUserGateView("create");
    }
    syncProfileGate();
  });
  observer.observe(gate, { attributes: true, attributeFilter: ["hidden"] });
  observer.observe(createView, { attributes: true, attributeFilter: ["hidden"] });
}

export function initShell() {
  renderSidebar();
  initSidebarToggle();
  initMicIndicator();
  watchActiveUser();
  watchProfileGate();
  followServerTests();
  syncShellToActiveUser();
  // Legacy code (old main menu, deep links) opens migrated screens through this
  window.nmOpenSection = (sectionId) => selectSection(sectionId);
}

initShell();

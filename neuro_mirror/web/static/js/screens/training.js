// neuro_mirror/web/static/js/screens/training.js
//
// «Тренировка» (deck slide 10). The core composes the session from the last
// cognitive test (js/core/training.js) and owns every game (js/core/games.js);
// this screen shows the composition, then plays the games one after another
// in the order given, inside the work area. «Выбрать игру самому» opens the
// core's catalog by domain and plays a single game outside the session.
//
// Progress is kept in module state, so leaving the section and coming back
// returns to the same task of the session; it is also kept for the browser
// session (sessionStorage), so a page reload returns to the same place: the
// game list, the same game and the same step of it (instruction, practice or
// the game itself — a game interrupted by the reload starts over).

import { loadTrainingPlan, loadTrainingSession } from "../core/training.js";
import { loadCatalog, mountGame } from "../core/games.js";
import { activeUser } from "../core/legacy.js";
import { createDomainTag } from "../components/domain-tag.js";
import { confirmDialog } from "../components/confirm-dialog.js";
import { notify } from "../components/notify.js";

// loading → locked | overview | legacy | failed;  overview → playing → done
const model = {
  phase: "loading",
  userId: "",
  session: null,
  index: 0,
  completed: 0,
  currentFinished: false,
  message: "",
  legacy: null,
  // Free choice of one game
  catalog: [],
  freeDomain: "",
  freeGame: null,
  // Step of the game on screen: intro | practice | done | game
  stage: "intro",
};

const PLACE_KEY = "nm-training-place";
const RESTORABLE = new Set(["overview", "catalog", "free", "playing", "done"]);

function savePlace() {
  try {
    if (!RESTORABLE.has(model.phase)) return;
    const { phase, userId, session, index, completed, stopped, freeDomain, freeGame, stage } = model;
    window.sessionStorage.setItem(
      PLACE_KEY,
      JSON.stringify({ phase, userId, session, index, completed, stopped, freeDomain, freeGame, stage }),
    );
  } catch (_) {
    // storage unavailable — a reload simply starts from the overview
  }
}

function readPlace(userId) {
  try {
    const place = JSON.parse(window.sessionStorage.getItem(PLACE_KEY) || "null");
    if (!place || place.userId !== userId || !RESTORABLE.has(place.phase) || !place.session) return null;
    return place;
  } catch (_) {
    return null;
  }
}

function setStage(stage) {
  model.stage = stage;
  savePlace();
}

let host = null;
let body = null;
let removeGame = null;
let nextButton = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function button(label, variant, onClick) {
  const node = el("button", `nm-btn nm-btn-${variant}`, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

function formatDate(isoText) {
  const date = new Date(isoText);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

function tasksWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "задание";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "задания";
  return "заданий";
}

const games = () => (model.session && model.session.games) || [];

// ---- Loading the session ---------------------------------------------------

async function load() {
  model.phase = "loading";
  render();
  const result = await loadTrainingSession();
  if (result.status === "ready") {
    model.session = result.session;
    model.index = 0;
    model.completed = 0;
    model.phase = "overview";
  } else if (result.status === "locked") {
    model.message = result.message;
    model.phase = "locked";
  } else if (result.status === "unsupported") {
    // A core without ready-made sessions: show what it does have — the
    // composition stored with the last cognitive test
    model.legacy = await loadTrainingPlan();
    model.phase = "legacy";
  } else {
    model.message = result.message;
    model.phase = "failed";
  }
  render();
}

// ---- Playing ------------------------------------------------------------------

function dropGame() {
  if (removeGame) removeGame();
  removeGame = null;
  nextButton = null;
}

function startSession() {
  model.stopped = false;
  model.index = 0;
  model.completed = 0;
  model.stage = "intro";
  model.phase = "playing";
  render();
}

function advance() {
  if (model.currentFinished) model.completed += 1;
  dropGame();
  if (model.index + 1 >= games().length) {
    model.phase = "done";
  } else {
    model.index += 1;
    model.stage = "intro";
  }
  render();
}

async function nextOrSkip() {
  if (!model.currentFinished) {
    const confirmed = await confirmDialog({
      title: "Задание ещё не завершено",
      message: "Перейти к следующему заданию? Текущее останется невыполненным.",
      confirmLabel: "Перейти",
      cancelLabel: "Остаться",
    });
    if (!confirmed) return;
  }
  advance();
}

async function stopSession() {
  const confirmed = await confirmDialog({
    title: "Прервать занятие?",
    message: "Оставшиеся задания не будут выполнены.",
    confirmLabel: "Прервать",
    cancelLabel: "Продолжить занятие",
  });
  if (!confirmed) return;
  if (model.currentFinished) model.completed += 1;
  dropGame();
  model.stopped = true;
  model.phase = "done";
  render();
}

function syncNextButton() {
  if (!nextButton) return;
  const last = model.index + 1 >= games().length;
  if (model.currentFinished) {
    nextButton.textContent = last ? "Завершить занятие" : "Следующее задание";
    nextButton.className = "nm-btn nm-btn-primary";
  } else {
    nextButton.textContent = "Пропустить задание";
    nextButton.className = "nm-btn nm-btn-secondary";
  }
}

// ---- Views --------------------------------------------------------------------

function buildLocked(text) {
  const panel = el("section", "nm-panel nm-training-locked");
  const icon = el("div", "nm-card-icon");
  icon.innerHTML =
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17 9h-1V7a4 4 0 00-8 0v2H7a2 2 0 00-2 2v9a2 2 0 002 2h10a2 2 0 002-2v-9a2 2 0 00-2-2zm-7-2a2 2 0 014 0v2h-4V7zm2 10a2 2 0 110-4 2 2 0 010 4z"/></svg>';
  panel.append(
    icon,
    el("h2", "nm-panel-title", "Сначала пройдите когнитивный тест"),
    // The core's own wording of the state, shown as is
    el("p", "nm-panel-text", text || "Курс тренировок составляется по результатам когнитивного теста. После теста здесь появится ваш курс."),
  );
  panel.appendChild(button("Перейти к когнитивному тесту", "primary", () => window.nmOpenSection && window.nmOpenSection("moca")));
  return panel;
}

function buildFailed() {
  const panel = el("section", "nm-panel nm-training-locked");
  panel.append(el("h2", "nm-panel-title", "Занятие не подобрано"), el("p", "nm-panel-text", model.message));
  panel.appendChild(button("Попробовать ещё раз", "primary", load));
  return panel;
}

function planList(rows) {
  const list = el("ul", "nm-training-plan");
  for (const [domain, count] of rows) {
    const item = el("li");
    item.append(createDomainTag(domain), el("strong", "nm-training-count", String(count)));
    list.appendChild(item);
  }
  return list;
}

function buildOverview() {
  const session = model.session;
  const grid = el("div", "nm-training-grid");

  const course = el("section", "nm-panel");
  course.append(
    el("h2", "nm-panel-title", "Начать тренировку"),
    el("p", "nm-panel-text nm-optional-text", "Занятие подобрано по результатам вашего когнитивного теста."),
    el("p", "nm-training-total", `${games().length} ${tasksWord(games().length)} в занятии`),
    el("h3", "nm-training-subtitle", "Состав занятия"),
    planList(Object.entries(session.plan || {}).filter(([, count]) => Number(count) > 0)),
  );
  // Reasons come from the core and are shown as is
  for (const skipped of session.skipped || []) {
    course.appendChild(el("p", "nm-help-bar nm-training-skipped", `${skipped.domain}: ${skipped.reason}`));
  }
  course.append(
    button("Начать тренировку", "primary nm-btn-block", startSession),
    button("Выбрать игру самому", "secondary nm-btn-block nm-training-free", openCatalog),
  );

  const order = el("section", "nm-panel");
  order.appendChild(el("h2", "nm-panel-title", "Порядок заданий"));
  const list = el("ol", "nm-training-order");
  for (const game of games()) {
    const item = el("li");
    item.append(el("span", "nm-training-order-title", game.title), createDomainTag(game.domain));
    list.appendChild(item);
  }
  order.appendChild(list);

  grid.append(course, order);
  return grid;
}

// A core without ready-made sessions (before the games were added)
function buildLegacy() {
  const info = model.legacy;
  if (!info.unlocked) return buildLocked("");
  const course = el("section", "nm-panel nm-training-locked");
  course.append(
    el("h2", "nm-panel-title", "Начать тренировку"),
    el("p", "nm-panel-text", info.testedAt
      ? `Курс составлен по результатам когнитивного теста от ${formatDate(info.testedAt)}.`
      : "Курс составлен по результатам когнитивного теста."),
  );
  if (info.plan.length > 0) {
    course.append(
      el("p", "nm-training-total", `${info.total} ${tasksWord(info.total)} в занятии`),
      planList(info.plan.map((row) => [row.domain, row.tasks])),
    );
  }
  const start = button("Начать тренировку", "primary nm-btn-block", () => {});
  start.disabled = true;
  course.append(start, el("p", "nm-status-line", "Игры тренировки ещё не подключены в этой версии ядра."));
  return course;
}

// ---- End of a game: one clear screen for every game -------------------------

// Where the games put their final words (their wording, shown as is)
const RESULT_SOURCES = ["[data-result-text]", ".game-result-new p", "[data-result]", "[data-status]"];

// The game is already hidden under the end screen, so "shown" means: not
// inside anything the game itself hides
function gameResultText(stage) {
  for (const selector of RESULT_SOURCES) {
    for (const node of stage.querySelectorAll(selector)) {
      const text = node.textContent.trim();
      if (text && !node.closest("[hidden]") && !node.closest(".nm-game-finish")) return text;
    }
  }
  return "";
}

// Right when the core says the game is over, the end screen replaces the
// field. The game writes its result line a moment later (after it receives
// the same answer), so the line is filled in when it appears.
// actions: [{ label, primary, onClick }]
function showFinish(stage, isCurrent, actions) {
  if (!isCurrent() || stage.querySelector(".nm-game-finish")) return;
  const panel = el("div", "nm-game-finish");
  panel.setAttribute("role", "status");
  const icon = el("div", "nm-game-finish-icon");
  icon.innerHTML =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const heading = el("h3", null, "Задание выполнено");
  heading.tabIndex = -1;
  const result = el("p", "nm-game-finish-result");
  result.hidden = true;
  const row = el("div", "nm-btn-row nm-game-finish-actions");
  for (const action of actions) row.append(button(action.label, action.primary ? "primary" : "secondary", action.onClick));
  panel.append(icon, heading, result, row);
  stage.append(panel);
  stage.classList.add("is-finished");
  heading.focus();
  for (const delay of [60, 400, 1200]) {
    setTimeout(() => {
      if (!panel.isConnected || !result.hidden) return;
      const text = gameResultText(stage);
      if (text) {
        result.textContent = text;
        result.hidden = false;
      }
    }, delay);
  }
}

// Puts a game on `stage`; `isCurrent()` tells whether that stage is still the
// one on screen when an answer from the core arrives.
function playOn(stage, game, isCurrent, { onFinished, onClose }) {
  mountGame(game.game_code, stage, {
    fallbackTitle: game.title,
    introStage: model.stage,
    onIntroStage(step) {
      if (isCurrent()) setStage(step);
    },
    onFinished() {
      if (isCurrent()) onFinished();
    },
    onClose() {
      if (isCurrent()) onClose();
    },
    onError(text) {
      if (isCurrent()) notify(`Задание «${game.title}»: ${text}`);
    },
  })
    .then((remove) => {
      if (isCurrent()) removeGame = remove;
      else remove();
    })
    .catch((error) => {
      if (!isCurrent()) return;
      notify(`Задание «${game.title}» не открылось. ${error.message || error}`);
      stage.replaceChildren(el("p", "nm-panel-text", "Это задание сейчас недоступно."));
    });
}

// ---- Free choice of one game ---------------------------------------------------

// Domain names as the core words them (taken from the session it composed)
function domainLabel(code) {
  const known = games().find((game) => game.domain_code === code);
  return known ? known.domain : code;
}

async function openCatalog() {
  try {
    model.catalog = (await loadCatalog()).filter((item) => item.implemented);
  } catch (error) {
    notify(`Список игр не загрузился. ${error.message || error}`);
    return;
  }
  model.phase = "catalog";
  render();
}

function openFreeGame(definition) {
  model.freeGame = {
    game_code: definition.code,
    title: definition.title,
    domain: domainLabel(definition.primary_domain),
  };
  model.stage = "intro";
  model.phase = "free";
  render();
}

function buildCatalog() {
  const wrap = el("div", "nm-training-catalog");
  const domains = [...new Set(model.catalog.map((item) => item.primary_domain))];
  if (!domains.includes(model.freeDomain)) model.freeDomain = domains[0];

  const tablist = el("div", "nm-tabs");
  tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-label", "Область тренировки");
  const panel = el("div", "nm-training-games");
  panel.setAttribute("role", "tabpanel");

  const tabs = domains.map((code) => {
    const tab = el("button", "nm-tab", domainLabel(code));
    tab.type = "button";
    tab.setAttribute("role", "tab");
    tab.addEventListener("click", () => select(code, true));
    tablist.appendChild(tab);
    return tab;
  });

  function select(code, focus) {
    model.freeDomain = code;
    savePlace();
    domains.forEach((item, i) => {
      const selected = item === code;
      tabs[i].setAttribute("aria-selected", String(selected));
      tabs[i].tabIndex = selected ? 0 : -1;
      if (selected && focus) tabs[i].focus();
    });
    panel.replaceChildren();
    for (const definition of model.catalog.filter((item) => item.primary_domain === code)) {
      const card = el("button", "nm-training-game");
      card.type = "button";
      card.appendChild(el("strong", null, definition.title));
      // How the answer is given matters before starting: voice needs a microphone
      if (definition.response_type === "spoken") card.appendChild(el("span", null, "Ответ голосом"));
      card.addEventListener("click", () => openFreeGame(definition));
      panel.appendChild(card);
    }
  }
  // Arrow keys move between tabs, as in any tab list
  tablist.addEventListener("keydown", (event) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    const index = (domains.indexOf(model.freeDomain) + step + domains.length) % domains.length;
    select(domains[index], true);
  });
  select(model.freeDomain, false);

  const row = el("div", "nm-btn-row");
  row.appendChild(button("Назад к занятию", "secondary", () => {
    model.phase = "overview";
    render();
  }));
  const title = el("h2", "nm-panel-title", "Выберите игру");
  title.tabIndex = -1;
  wrap.append(title, tablist, panel, row);
  setTimeout(() => title.isConnected && title.focus(), 0);
  return wrap;
}

function buildFree() {
  const game = model.freeGame;
  const wrap = el("div", "nm-training-play");

  const head = el("div", "nm-training-play-head");
  const title = el("h2", "nm-panel-title", "Свободная игра");
  title.tabIndex = -1;
  head.append(title, createDomainTag(game.domain));

  const stage = el("div", "nm-game-host");
  const actions = el("div", "nm-btn-row nm-training-play-actions");
  const back = button("К выбору игр", "secondary", () => {
    dropGame();
    model.phase = "catalog";
    render();
  });
  // Plays the game again from its start (the instruction was already seen)
  const again = button("Сыграть ещё раз", "secondary", () => {
    model.stage = "game";
    render();
  });
  actions.append(back, again);
  wrap.append(head, stage, actions);

  const current = () => model.phase === "free" && model.freeGame === game && stage.isConnected;
  playOn(stage, game, current, {
    onFinished() {
      back.className = "nm-btn nm-btn-primary";
      showFinish(stage, current, [
        { label: "Сыграть ещё раз", onClick: () => again.click() },
        { label: "Выбрать другую игру", primary: true, onClick: () => back.click() },
      ]);
    },
    onClose: () => back.click(),
  });
  setTimeout(() => title.isConnected && title.focus(), 0);
  return wrap;
}

function buildPlaying() {
  const game = games()[model.index];
  const total = games().length;
  const wrap = el("div", "nm-training-play");

  const head = el("div", "nm-training-play-head");
  const title = el("h2", "nm-panel-title", `Задание ${model.index + 1} из ${total}`);
  title.tabIndex = -1;
  const bar = el("div", "nm-progress");
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-label", "Ход занятия");
  bar.setAttribute("aria-valuemin", "0");
  bar.setAttribute("aria-valuemax", String(total));
  bar.setAttribute("aria-valuenow", String(model.index));
  const fill = el("div", "nm-progress-fill");
  fill.style.width = `${Math.round((model.index / total) * 100)}%`;
  bar.appendChild(fill);
  head.append(title, createDomainTag(game.domain), bar);

  // The game draws itself here; its look comes from css/screens/game.css
  const stage = el("div", "nm-game-host");

  const actions = el("div", "nm-btn-row nm-training-play-actions");
  nextButton = button("", "secondary", nextOrSkip);
  actions.append(button("Прервать занятие", "secondary", stopSession), nextButton);

  wrap.append(head, stage, actions);

  model.currentFinished = false;
  syncNextButton();
  const index = model.index;
  const current = () => model.phase === "playing" && model.index === index && stage.isConnected;
  playOn(stage, game, current, {
    onFinished() {
      model.currentFinished = true;
      syncNextButton();
      const last = model.index + 1 >= games().length;
      showFinish(stage, current, [
        { label: last ? "Завершить занятие" : "Следующее задание", primary: true, onClick: advance },
      ]);
    },
    // The game's own «close» button is hidden in a session; if a game still
    // calls it, that means "done with this one"
    onClose: nextOrSkip,
  });

  setTimeout(() => title.isConnected && title.focus(), 0);
  return wrap;
}

function buildDone() {
  const total = games().length;
  const card = el("section", "nm-panel nm-result");
  const title = el("h2", "nm-panel-title", model.stopped ? "Занятие остановлено" : "Занятие завершено");
  title.tabIndex = -1;
  card.append(title, el("p", "nm-panel-text", `Выполнено ${model.completed} из ${total} ${tasksWord(total)}.`));
  const row = el("div", "nm-btn-row");
  row.append(
    button("В меню", "primary", () => window.nmOpenSection && window.nmOpenSection("home")),
    button("Новое занятие", "secondary", load),
  );
  card.appendChild(row);
  setTimeout(() => title.isConnected && title.focus(), 0);
  return card;
}

function render() {
  if (!host || !body) return;
  dropGame();
  body.replaceChildren();
  host.classList.toggle("nm-training-in-game", model.phase === "playing" || model.phase === "free");
  const views = {
    loading: () => el("p", "nm-panel-text", "Подбираю занятие…"),
    locked: () => buildLocked(model.message),
    failed: buildFailed,
    legacy: buildLegacy,
    overview: buildOverview,
    catalog: buildCatalog,
    free: buildFree,
    playing: buildPlaying,
    done: buildDone,
  };
  body.appendChild(views[model.phase]());
  savePlace();
}

// After a page reload: back to the place saved for this profile
async function restore(place) {
  Object.assign(model, place, { currentFinished: false });
  if (place.phase === "catalog" || place.phase === "free") {
    try {
      model.catalog = (await loadCatalog()).filter((item) => item.implemented);
    } catch (_) {
      model.phase = "overview";
    }
  }
  render();
}

// ---- Screen contract used by js/shell.js ------------------------------------

export const trainingScreen = {
  mount(container) {
    host = container;
    container.appendChild(el("p", "nm-workarea-subtitle", "Тренируйте когнитивные функции с учётом ваших результатов"));
    body = el("div");
    container.appendChild(body);
    // A session in progress continues from its current task; anything else is
    // asked from the core again (the profile or the test result may have changed)
    const userId = (activeUser() || {}).id || "";
    // Back from another section: the game list or a game stays where it was
    if (["playing", "catalog", "free"].includes(model.phase) && model.userId === userId) {
      render();
      return;
    }
    model.userId = userId;
    // First opening after a page reload: the place saved before it
    const place = model.phase === "loading" ? readPlace(userId) : null;
    if (place) restore(place);
    else load();
  },
  unmount() {
    dropGame();
    host.classList.remove("nm-training-in-game");
    host = null;
    body = null;
  },
  isBusy() {
    return model.phase === "playing";
  },
  leaveWarning() {
    return {
      title: "Занятие ещё не завершено",
      message: "Если перейти в другой раздел, текущее задание начнётся заново, когда вы вернётесь в «Тренировку».",
    };
  },
};

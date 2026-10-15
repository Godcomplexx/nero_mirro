// neuro_mirror/web/static/js/screens/training.js
//
// «Тренировка» (deck slide 10). The core forms the course of twelve sessions
// at once (js/core/training.js): the same split by domain in every session,
// the games rotate between sessions, and the difficulty of each game follows
// how correctly it was done. The core owns every game (js/core/games.js). This screen shows the session, then plays
// the games one after another in the order given, inside the work area.
//
// The person does not choose games: the course does. «Выбрать игру самому»
// is an extra tool for checking the games and for the doctor; such a game is
// outside the course and does not change its levels.
//
// A task ends only by itself (done, time or attempts are over): there is no
// skipping. «Пауза» hides the task; from the pause the user continues — the
// interrupted trial is presented again and is not scored, the trials done
// before it are kept (methodology 4.5, п. 5) — interrupts the task or ends the
// session. Interrupting asks for the reason (6.3): with fatigue or feeling
// unwell the screen first offers to end the session, otherwise a lighter
// alternative of the task; new or unusual symptoms are a red flag (9) — the
// session stops and the course waits for the specialist.
//
// Before the session, once, the core's question about new symptoms (9).
//
// Progress is kept in module state, so leaving the section and coming back
// returns to the same task of the session; it is also kept for the browser
// session (sessionStorage), so a page reload returns to the same place: the
// game list, the same game and the same step of it (instruction, practice or
// the game itself — a game interrupted by the reload starts over). The core
// keeps the plan itself, so even without that place the session continues
// from its first unfinished task.
//
// The session is framed by the SAN questionnaire: once before the first game
// and once after the session ends (normally or from the pause). Both answers
// carry the id of the course session, so the core can compare "before" and
// "after". Either survey may be skipped. If the server has no questionnaire,
// the step shows a notice and a button to continue — the screen does not
// invent questions.

import {
  addAlternative,
  finishTrainingSession,
  interruptTask,
  loadTrainingPlan,
  loadTrainingSession,
  noteResume,
  notePause,
  sendPreCheck,
} from "../core/training.js";
import { loadCatalog, mountGame } from "../core/games.js";
import { activeUser } from "../core/legacy.js";
import { loadSanQuestionnaire, saveSanAnswers } from "../core/questionnaires.js";
import { createDomainTag } from "../components/domain-tag.js";
import { createSanSurvey } from "../components/san-survey.js";
import { notify } from "../components/notify.js";

// loading → locked | overview | legacy | failed;
// overview → pre-check → san-before → playing → san-after → done;
// playing → interrupt → playing | san-after | stopped
const model = {
  phase: "loading",
  userId: "",
  session: null,
  index: 0,
  completed: 0,
  currentFinished: false,
  // The task on screen could not be opened: the session may go past it
  currentUnavailable: false,
  paused: false,
  message: "",
  legacy: null,
  // Free choice of one game
  catalog: [],
  freeDomain: "",
  freeGame: null,
  // Step of the game on screen: intro | practice | done | game
  stage: "intro",
  // The game session of the task on screen: after a pause the task goes on
  // from its interrupted trial
  gameSessionId: "",
  // Interrupting: { mode: "task" | "session", step: "reason" | "suggest", ... }
  interrupt: null,
  // The course waits for the specialist (red flag)
  hold: false,
};

const PLACE_KEY = "nm-training-place";
const RESTORABLE = new Set(["overview", "catalog", "free", "san-before", "playing", "san-after", "done"]);

function savePlace() {
  try {
    if (!RESTORABLE.has(model.phase)) return;
    const { phase, userId, session, index, completed, stopped, paused, currentFinished, freeDomain, freeGame, stage, gameSessionId } = model;
    window.sessionStorage.setItem(
      PLACE_KEY,
      JSON.stringify({
        phase, userId, session, index, completed, stopped, paused, currentFinished, freeDomain, freeGame, stage, gameSessionId,
      }),
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
const courseInfo = () => (model.session && model.session.course) || null;

// Where the saved session continues: the first task without an outcome
function firstOpenTask() {
  const index = games().findIndex((game) => !["done", "abandoned", "not_presented"].includes(game.status));
  return index < 0 ? games().length : index;
}

const doneCount = () => games().filter((game) => game.status === "done").length;

// Ties the "before" and "after" questionnaires to the session of the course
function sessionKey() {
  const info = courseInfo();
  return info ? `${info.course_id}-${info.session_number}` : "";
}

function sessionTitle() {
  const info = courseInfo();
  if (!info) return "";
  return `Занятие ${info.session_number} из ${info.sessions_total} · ${info.stage.title}`;
}

// ---- Loading the session ---------------------------------------------------

async function load() {
  model.phase = "loading";
  render();
  const result = await loadTrainingSession();
  if (result.status === "ready") {
    model.session = result.session;
    model.index = firstOpenTask();
    model.completed = doneCount();
    model.paused = false;
    model.currentFinished = false;
    model.phase = "overview";
  } else if (result.status === "locked") {
    model.message = result.message;
    model.hold = Boolean(result.hold);
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
}

function startSession() {
  model.stopped = false;
  model.paused = false;
  model.index = firstOpenTask();
  model.completed = doneCount();
  model.currentFinished = false;
  model.currentUnavailable = false;
  model.stage = "intro";
  if (model.index >= games().length) {
    finishSession(false);
    return;
  }
  // The question about new symptoms comes once per session, before anything
  model.phase = model.session.pre_check ? afterPreCheck() : "pre-check";
  render();
}

// A session continued after a break has already had its "before" survey
function afterPreCheck() {
  return doneCount() === 0 && !games().some((game) => game.status === "abandoned") ? "san-before" : "playing";
}

function startGames() {
  model.phase = "playing";
  render();
}

// The session is over: the core closes it, then the "after" survey.
// `reasonCode` — why the person ended it early (methodology 6.3)
function finishSession(stopped, reasonCode = "") {
  model.phase = "san-after";
  render();
  endSession(stopped, reasonCode);
}

// The core closes the session; its count of finished tasks is the one shown
async function endSession(stopped, reasonCode = "") {
  model.stopped = stopped;
  const reply = await finishTrainingSession("", stopped ? reasonCode : "");
  if (reply && reply.finished) model.completed = reply.done;
  if (model.phase === "done") render();
}

// «Следующее задание» exists only once the task has ended (or could not open)
function advance() {
  if (model.currentFinished) model.completed += 1;
  dropGame();
  model.currentFinished = false;
  model.currentUnavailable = false;
  model.gameSessionId = "";
  if (model.index + 1 >= games().length) {
    finishSession(false);
    return;
  }
  model.index += 1;
  model.stage = "intro";
  render();
}

const taskInProgress = () => !model.currentFinished && !model.currentUnavailable && Boolean(games()[model.index]);

// The pause hides the task: the field is removed, its timers stop with it.
// The core notes which trial was interrupted.
function pauseSession() {
  if (model.paused) return;
  dropGame();
  model.paused = true;
  const game = games()[model.index] || {};
  if (taskInProgress()) notePause(game.position ?? null, game.game_code || "", model.gameSessionId);
  else notePause(null);
  render();
}

function resumeSession() {
  model.paused = false;
  noteResume();
  render();
}

// «Завершить занятие» from the pause: the reason is asked first (6.3)
function endFromPause() {
  model.interrupt = { mode: "session", step: "reason" };
  model.phase = "interrupt";
  render();
}

// «Прервать задание»: the reason, then what the methodology offers for it
function interruptFromPause() {
  model.interrupt = { mode: "task", step: "reason" };
  model.phase = "interrupt";
  render();
}

function backToPause() {
  model.interrupt = null;
  model.phase = "playing";
  render();
}

function closeSession(reasonCode) {
  if (model.currentFinished) model.completed += 1;
  model.currentFinished = false;
  model.paused = false;
  model.interrupt = null;
  model.gameSessionId = "";
  dropGame();
  finishSession(true, reasonCode);
}

function showStopped(message) {
  model.interrupt = null;
  model.paused = false;
  model.gameSessionId = "";
  model.message = message;
  model.phase = "stopped";
  render();
}

async function chooseReason(reason) {
  const interrupt = model.interrupt;
  if (!interrupt) return;
  if (interrupt.mode === "session") {
    if (reason.red_flag) {
      dropGame();
      const reply = await finishTrainingSession("", reason.code);
      showStopped((reply && reply.message) || "");
      return;
    }
    closeSession(reason.code);
    return;
  }
  const game = games()[model.index];
  let reply;
  try {
    reply = await interruptTask(game.position, reason.code);
  } catch (error) {
    notify(error.message || String(error));
    return;
  }
  dropGame();
  model.gameSessionId = "";
  game.status = "abandoned";
  if (reply.stopped) {
    showStopped(reply.message);
    return;
  }
  model.interrupt = { mode: "task", step: "suggest", reason, suggest: reply.suggest, alternative: reply.alternative };
  render();
}

async function takeAlternative() {
  const game = games()[model.index];
  try {
    model.session = await addAlternative(game.position);
  } catch (error) {
    notify(error.message || String(error));
    return;
  }
  model.interrupt = null;
  model.paused = false;
  model.currentFinished = false;
  model.currentUnavailable = false;
  model.gameSessionId = "";
  model.index += 1;
  // The same form one level lower needs no instruction again
  const next = games()[model.index];
  model.stage = next && next.game_code === game.game_code ? "game" : "intro";
  model.phase = "playing";
  render();
}

// No alternative and the person wants to go on: the next task
function skipToNext() {
  model.interrupt = null;
  model.paused = false;
  model.phase = "playing";
  advance();
}

// ---- Views --------------------------------------------------------------------

function buildLocked(text) {
  const panel = el("section", "nm-panel nm-training-locked");
  const icon = el("div", "nm-card-icon");
  icon.innerHTML =
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M17 9h-1V7a4 4 0 00-8 0v2H7a2 2 0 00-2 2v9a2 2 0 002 2h10a2 2 0 002-2v-9a2 2 0 00-2-2zm-7-2a2 2 0 014 0v2h-4V7zm2 10a2 2 0 110-4 2 2 0 010 4z"/></svg>';
  // A red flag paused the course: the core's own words, no test to go to
  if (model.hold) {
    panel.append(icon, el("h2", "nm-panel-title", "Тренировки приостановлены"), el("p", "nm-panel-text", text));
    panel.appendChild(button("В меню", "primary", () => window.nmOpenSection && window.nmOpenSection("home")));
    return panel;
  }
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

  const started = doneCount() > 0 || model.index > 0;
  const course = el("section", "nm-panel");
  course.append(
    el("h2", "nm-panel-title", started ? "Продолжить тренировку" : "Начать тренировку"),
    el("p", "nm-training-total", sessionTitle()),
    el("p", "nm-panel-text nm-optional-text", "Курс из 12 занятий составлен по результатам вашего когнитивного теста. Игры меняются от занятия к занятию, сложность подстраивается под ваши результаты."),
    el("p", "nm-training-total", started
      ? `Выполнено ${doneCount()} из ${games().length} ${tasksWord(games().length)}`
      : `${games().length} ${tasksWord(games().length)} в занятии`),
    el("h3", "nm-training-subtitle", "Состав занятия"),
    planList(Object.entries(session.plan || {}).filter(([, count]) => Number(count) > 0)),
  );
  // Reasons come from the core and are shown as is
  for (const skipped of session.skipped || []) {
    course.appendChild(el("p", "nm-help-bar nm-training-skipped", `${skipped.domain}: ${skipped.reason}`));
  }
  course.append(
    button(started ? "Продолжить занятие" : "Начать тренировку", "primary nm-btn-block", startSession),
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
function showFinish(stage, isCurrent, actions, headingText = "Задание выполнено") {
  if (!isCurrent() || stage.querySelector(".nm-game-finish")) return;
  const panel = el("div", "nm-game-finish");
  panel.setAttribute("role", "status");
  const icon = el("div", "nm-game-finish-icon");
  icon.innerHTML =
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const heading = el("h3", null, headingText);
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
function playOn(
  stage,
  game,
  isCurrent,
  { onFinished, onClose, onUnavailable, startOptions = null, resumeSessionId = "", onSessionStarted = () => {} },
) {
  mountGame(game.game_code, stage, {
    fallbackTitle: game.title,
    // Задание курса называет себя номером занятия и задания; уровень и
    // стимульный набор ядро берёт из сохранённого плана.
    startOptions,
    stimulusSet: game.stimulus_set ?? null,
    introStage: model.stage,
    resumeSessionId,
    onSessionStarted(id) {
      if (isCurrent()) onSessionStarted(id);
    },
    onIntroStage(step) {
      if (isCurrent()) setStage(step);
    },
    onFinished(reply) {
      if (isCurrent()) onFinished(reply);
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
      if (onUnavailable) onUnavailable();
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
    onFinished(reply) {
      back.className = "nm-btn nm-btn-primary";
      showFinish(stage, current, [
        { label: "Сыграть ещё раз", onClick: () => again.click() },
        { label: "Выбрать другую игру", primary: true, onClick: () => back.click() },
      ], reply && reply.end_reason === "timeout" ? "Время задания закончилось" : "Задание выполнено");
    },
    onClose: () => back.click(),
  });
  setTimeout(() => title.isConnected && title.focus(), 0);
  return wrap;
}

function buildPause() {
  const panel = el("section", "nm-panel nm-training-locked");
  const title = el("h2", "nm-panel-title", "Пауза");
  title.tabIndex = -1;
  const inTask = taskInProgress();
  panel.append(
    title,
    el("p", "nm-panel-text", inTask
      ? "Задание остановлено. Если продолжить, прерванный шаг задания начнётся заново, а уже выполненные шаги сохранятся."
      : "Отдохните, сколько нужно. Выполненные задания сохранены."),
  );
  const row = el("div", "nm-btn-row");
  row.append(button("Продолжить", "primary", resumeSession));
  if (inTask) row.append(button("Прервать задание", "secondary", interruptFromPause));
  row.append(button("Завершить занятие", "secondary", endFromPause));
  panel.appendChild(row);
  setTimeout(() => title.isConnected && title.focus(), 0);
  return panel;
}

// Why the task or the session is interrupted; the reasons are the core's
function buildInterrupt() {
  const interrupt = model.interrupt;
  const panel = el("section", "nm-panel nm-training-locked");
  if (interrupt.step === "reason") {
    const title = el("h2", "nm-panel-title", interrupt.mode === "task" ? "Почему вы прерываете задание?" : "Почему вы завершаете занятие?");
    title.tabIndex = -1;
    panel.append(title, el("p", "nm-panel-text", "Это поможет подобрать следующие занятия. Выполненные задания сохранены."));
    const list = el("div", "nm-training-reasons");
    for (const reason of model.session.interruption_reasons || []) {
      list.append(button(reason.label, "secondary nm-btn-block", () => chooseReason(reason)));
    }
    panel.append(list);
    const row = el("div", "nm-btn-row");
    row.append(button("Назад", "secondary", backToPause));
    panel.append(row);
    setTimeout(() => title.isConnected && title.focus(), 0);
    return panel;
  }
  // What to do next: methodology 6.3 — fatigue or feeling unwell: ending the
  // session comes first; otherwise the lighter alternative
  const alternative = interrupt.alternative;
  const finishFirst = interrupt.suggest === "finish";
  const title = el("h2", "nm-panel-title", finishFirst ? "Лучше завершить занятие" : "Можно продолжить с более лёгким заданием");
  title.tabIndex = -1;
  panel.append(title);
  panel.append(el("p", "nm-panel-text", finishFirst
    ? "Если вы устали или плохо себя чувствуете, лучше завершить занятие. Выполненные задания сохранены, следующее занятие продолжит курс."
    : alternative
      ? `Вместо прерванного задания можно выполнить более лёгкое: «${alternative.title}».`
      : "Более лёгкого варианта для этого задания нет. Можно перейти к следующему заданию или завершить занятие."));
  const row = el("div", "nm-btn-row");
  const finish = () => closeSession(interrupt.reason.code);
  const lighter = alternative ? button("Выполнить более лёгкое задание", finishFirst ? "secondary" : "primary", takeAlternative) : null;
  const next = !alternative && model.index + 1 < games().length
    ? button("Перейти к следующему заданию", finishFirst ? "secondary" : "primary", skipToNext)
    : null;
  if (finishFirst) row.append(button("Завершить занятие", "primary", finish));
  if (lighter) row.append(lighter);
  if (next) row.append(next);
  if (!finishFirst) row.append(button("Завершить занятие", "secondary", finish));
  panel.append(row);
  setTimeout(() => title.isConnected && title.focus(), 0);
  return panel;
}

// Red flag (methodology 9): the session stops, the course waits for the specialist
function buildStopped() {
  const panel = el("section", "nm-panel nm-training-locked");
  const title = el("h2", "nm-panel-title", "Тренировка остановлена");
  title.tabIndex = -1;
  panel.append(title, el("p", "nm-panel-text", model.message || "Обратитесь, пожалуйста, к врачу."));
  const row = el("div", "nm-btn-row");
  row.append(button("В меню", "primary", () => window.nmOpenSection && window.nmOpenSection("home")));
  panel.append(row);
  setTimeout(() => title.isConnected && title.focus(), 0);
  return panel;
}

// The question about new symptoms before the session (methodology 9). Its
// wording is the core's (a draft until approved by the methodologists).
function buildPreCheck() {
  const question = model.session.pre_check_question || {};
  const panel = el("section", "nm-panel nm-training-locked");
  const title = el("h2", "nm-panel-title", "Перед занятием");
  title.tabIndex = -1;
  panel.append(title, el("p", "nm-panel-text", question.text || ""));
  const row = el("div", "nm-btn-row");
  const answer = async (value, node) => {
    for (const item of row.querySelectorAll("button")) item.disabled = true;
    try {
      const reply = await sendPreCheck(value);
      if (reply.stop) {
        showStopped(reply.message);
        return;
      }
      model.session.pre_check = { new_symptoms: false };
      model.phase = afterPreCheck();
      render();
    } catch (error) {
      notify(error.message || String(error));
      for (const item of row.querySelectorAll("button")) item.disabled = false;
      node.focus();
    }
  };
  for (const option of question.options || []) {
    const node = button(option.label, "secondary", () => answer(option.value, node));
    row.append(node);
  }
  panel.append(row);
  setTimeout(() => title.isConnected && title.focus(), 0);
  return panel;
}

function buildPlaying() {
  if (model.paused) return buildPause();
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
  actions.append(button("Пауза", "secondary", pauseSession));

  wrap.append(head, stage, actions);

  const index = model.index;
  const current = () => model.phase === "playing" && !model.paused && model.index === index && stage.isConnected;
  const last = model.index + 1 >= games().length;
  const nextAction = [{ label: last ? "Завершить занятие" : "Следующее задание", primary: true, onClick: advance }];
  if (model.currentFinished || model.currentUnavailable) {
    // Back from the pause after the task had ended: its end screen again
    setTimeout(() => showFinish(stage, current, nextAction, model.currentFinished ? "Задание выполнено" : "Задание недоступно"), 0);
  } else {
    playOn(stage, game, current, {
      startOptions: courseInfo() ? { course_session: courseInfo().session_number, course_position: game.position } : null,
      // Back from a pause, another section or a reload: the interrupted trial again
      resumeSessionId: model.gameSessionId,
      onSessionStarted(id) {
        model.gameSessionId = id;
        savePlace();
      },
      onFinished(reply) {
        model.currentFinished = true;
        model.gameSessionId = "";
        savePlace();
        showFinish(stage, current, nextAction, reply && reply.end_reason === "timeout" ? "Время задания закончилось" : "Задание выполнено");
      },
      // A task that does not open is a technical problem, not the user's
      // choice: the session goes on, the core marks it as not presented
      onUnavailable() {
        model.currentUnavailable = true;
        showFinish(stage, current, nextAction, "Задание недоступно");
      },
      // The game's own «close» button is hidden in a session; if a game still
      // calls it, the session pauses
      onClose: pauseSession,
    });
  }

  setTimeout(() => title.isConnected && title.focus(), 0);
  return wrap;
}

// ---- Questionnaire before and after the session --------------------------------

// Only a loaded questionnaire is kept: after a failed load the next survey asks again
let sanQuestionnaire = null;
async function questionnaire() {
  if (!sanQuestionnaire) sanQuestionnaire = await loadSanQuestionnaire();
  return sanQuestionnaire;
}

const SAN_TEXTS = {
  before: {
    title: "Как вы себя чувствуете перед занятием?",
    intro: "Ответьте на несколько вопросов перед началом — так будет видно, как меняется ваше состояние за занятие.",
    finishLabel: "Начать занятие",
  },
  after: {
    title: "Как вы себя чувствуете после занятия?",
    intro: "Ответьте на те же вопросы ещё раз — их сравнят с ответами перед занятием.",
    finishLabel: "Завершить",
  },
};

function buildSan(moment) {
  const phase = model.phase;
  const wrap = el("div", "nm-training-san");
  wrap.appendChild(el("p", "nm-panel-text", "Загружаю вопросы…"));
  const isCurrent = () => model.phase === phase && wrap.isConnected;
  const proceed = () => {
    if (!isCurrent()) return;
    if (moment === "before") {
      startGames();
    } else {
      model.phase = "done";
      render();
    }
  };
  questionnaire().then((data) => {
    if (!isCurrent()) return;
    if (!data) {
      const box = el("section", "nm-panel nm-stub");
      const title = el("h2", "nm-panel-title", "Оценка самочувствия");
      title.tabIndex = -1;
      const skipLabel = moment === "before" ? "Начать занятие" : "Завершить";
      box.append(
        title,
        el(
          "p",
          "nm-panel-text",
          moment === "before"
            ? "Вопросы о самочувствии ещё не подключены. Этот шаг можно пропустить и начать занятие."
            : "Вопросы о самочувствии ещё не подключены. Этот шаг можно пропустить и завершить занятие.",
        ),
      );
      const skipRow = el("div", "nm-btn-row");
      skipRow.appendChild(button(skipLabel, "primary", proceed));
      box.appendChild(skipRow);
      wrap.replaceChildren(box);
      title.focus();
      return;
    }
    const texts = SAN_TEXTS[moment];
    const survey = createSanSurvey({
      questionnaire: data,
      title: texts.title,
      intro: texts.intro,
      finishLabel: texts.finishLabel,
      async onDone(answers) {
        try {
          await saveSanAnswers(answers, { moment, sessionId: sessionKey() });
        } catch (error) {
          notify(`Ответы не сохранились: ${error.message || error}. Нажмите «${texts.finishLabel}» ещё раз или пропустите опрос.`);
          throw error;
        }
        proceed();
      },
    });
    const row = el("div", "nm-btn-row");
    row.appendChild(button("Пропустить опрос", "secondary", proceed));
    wrap.replaceChildren(survey, row);
    const heading = survey.querySelector("h2");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  });
  return wrap;
}

function buildDone() {
  const total = games().length;
  const card = el("section", "nm-panel nm-result");
  const title = el("h2", "nm-panel-title", model.stopped ? "Занятие остановлено" : "Занятие завершено");
  title.tabIndex = -1;
  card.append(title);
  if (sessionTitle()) card.appendChild(el("p", "nm-training-total", sessionTitle()));
  card.appendChild(el("p", "nm-panel-text", `Выполнено ${model.completed} из ${total} ${tasksWord(total)}.`));
  const info = courseInfo();
  const lastOfCourse = info && info.session_number >= info.sessions_total;
  const row = el("div", "nm-btn-row");
  row.append(
    button("В меню", "primary", () => window.nmOpenSection && window.nmOpenSection("home")),
    button(lastOfCourse ? "Что дальше" : "Следующее занятие", "secondary", load),
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
    "pre-check": buildPreCheck,
    "san-before": () => buildSan("before"),
    playing: buildPlaying,
    interrupt: buildInterrupt,
    stopped: buildStopped,
    "san-after": () => buildSan("after"),
    done: buildDone,
  };
  body.appendChild(views[model.phase]());
  savePlace();
}

// After a page reload: back to the place saved for this profile
async function restore(place) {
  Object.assign(model, place, { currentUnavailable: false });
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
    if (["pre-check", "san-before", "playing", "interrupt", "san-after", "catalog", "free"].includes(model.phase) && model.userId === userId) {
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
      message: "Если перейти в другой раздел, прерванный шаг задания начнётся заново, когда вы вернётесь в «Тренировку». Выполненные шаги сохранятся.",
    };
  },
};

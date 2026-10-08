// neuro_mirror/web/static/js/screens/screening.js
//
// Базовый скрининг (deck slide 4): «Проверка оборудования → Видеоанализ →
// Самочувствие». Step 3 is the HADS test the backend chains after the video
// analysis on its own (shown in place, js/components/hads-test.js), then
// the SAN questionnaire. Its questions come from the server; the step falls
// back to a stub only if the server returns nothing usable. The answers are
// not sent back to the server yet.
//
// The screen keeps its progress in module state, so leaving the section and
// coming back (deck: navigation must not reset progress) shows where the
// scenario is; server snapshots are followed even while it is not mounted.

import { api, cameraStream, cameraVideo, isCameraActive, log, unlockAudio } from "../core/legacy.js";
import { createSessionCheck } from "../core/session-check.js";
import { createSanSurvey } from "../components/san-survey.js";
import { loadSanQuestionnaire } from "../core/questionnaires.js";
import { renderCheckList } from "../components/check-list.js";
import { createHadsView } from "../components/hads-test.js";

const STEPS = ["Проверка оборудования", "Видеоанализ", "Самочувствие"];

const RPPG_SECONDS = 20;
const RPPG_FPS = 15;
const RESULT_TIMEOUT_MS = 90000;

// idle → checking → ready → running → processing → analyzed → hads → san → done
// any running phase → error
const BUSY_PHASES = new Set(["checking", "running", "processing", "analyzed", "hads", "san"]);

const model = {
  phase: "idle",
  check: null,
  items: {},
  status: "",
  verdict: null,
  progress: 0,
  message: "",
  sawScreening: false,
  resultTimer: null,
  sanElement: null,
};

let host = null;
let refs = null;

// ---- Server snapshots ----------------------------------------------------

function onSnapshot(event) {
  const snapshot = event.detail || {};
  const screen = snapshot.screen;
  const phase = model.phase;

  if ((phase === "running" || phase === "processing") && screen === "screening") {
    model.sawScreening = true;
    if (/завершён/i.test(String(snapshot.message || ""))) setPhase("analyzed");
    return;
  }
  if (["running", "processing", "analyzed"].includes(phase) && screen === "hads") {
    setPhase("hads");
    return;
  }
  if (phase === "hads" && screen === "summary" && snapshot.report && snapshot.report.report_type === "screening") {
    // The finish message carries the HADS scores — never shown to the patient
    setPhase("san");
    return;
  }
  // An interruption (test stopped, session failed) lands on "idle". Before the
  // server has acknowledged this run with a "screening" snapshot, an "idle"
  // snapshot is stale state from earlier and is ignored.
  if (["running", "processing", "analyzed", "hads"].includes(phase) && screen === "idle") {
    if (phase !== "hads" && !model.sawScreening) return;
    model.message = String(snapshot.message || "").trim() || "Скрининг был прерван.";
    setPhase("error");
  }
}

window.addEventListener("nm:snapshot", onSnapshot);

// ---- Phase changes -------------------------------------------------------

function setPhase(phase) {
  model.phase = phase;
  if (model.resultTimer) {
    clearTimeout(model.resultTimer);
    model.resultTimer = null;
  }
  if (phase === "processing") {
    model.resultTimer = setTimeout(() => {
      if (model.phase !== "processing") return;
      model.message = "Не удалось получить результат видеоанализа. Попробуйте ещё раз.";
      setPhase("error");
    }, RESULT_TIMEOUT_MS);
  }
  if (phase === "san" && !model.sanElement) {
    model.sanElement = buildSanLoading();
    loadSan();
  }
  render();
}

// ---- Step 3b: SAN questionnaire (content from the server) ----------------

function sanHeading(text) {
  const heading = el("h2", "nm-panel-title", text);
  heading.tabIndex = -1;
  return heading;
}

function buildSanLoading() {
  const box = el("section", "nm-panel");
  box.append(sanHeading("Оценка самочувствия"), el("p", "nm-panel-text", "Загружаю вопросы…"));
  return box;
}

// Shown while the server has no SAN questionnaire: nothing is invented on
// the frontend, the step is explained and can be skipped.
function buildSanStub() {
  const box = el("section", "nm-panel nm-stub");
  box.append(
    sanHeading("Оценка самочувствия"),
    el("p", "nm-panel-text", "Этот шаг пока недоступен: вопросы анкеты самочувствия ещё не подключены на сервере. Его можно пропустить — результаты видеоанализа и теста уже сохранены."),
  );
  const row = el("div", "nm-btn-row");
  row.appendChild(button("Продолжить", "primary", () => setPhase("done")));
  box.appendChild(row);
  return box;
}

async function loadSan() {
  const questionnaire = await loadSanQuestionnaire();
  if (model.phase !== "san") return;
  model.sanElement = questionnaire
    ? createSanSurvey({
        questionnaire,
        title: "Давайте оценим ваше самочувствие",
        intro: "Эти вопросы помогут лучше понять ваше состояние после видеоанализа. Выберите ответ, который подходит больше всего.",
        finishLabel: "Завершить скрининг",
        onDone: () => setPhase("done"),
      })
    : buildSanStub();
  // Rebuild the SAN area with the loaded content and move focus to it
  if (refs) refs.mode = "san-loading";
  render();
}

function resetToStart() {
  if (model.check) model.check.stop();
  model.check = null;
  model.items = {};
  model.status = "";
  model.verdict = null;
  model.progress = 0;
  model.message = "";
  model.sanElement = null;
  setPhase("idle");
}

async function runEquipmentCheck() {
  if (model.check) model.check.stop();
  model.items = {};
  model.verdict = null;
  model.status = "";
  model.check = createSessionCheck("screening", {
    onItem(name, state, note) {
      model.items[name] = { state, note };
      renderChecks();
      attachCamera();
    },
    onStatus(text) {
      model.status = text;
      renderSide();
    },
  });
  setPhase("checking");
  try {
    const verdict = await model.check.run();
    model.verdict = verdict;
    const allOk = Object.values(model.items).every((item) => item.state !== "fail");
    model.status = verdict.canStart && allOk
      ? "Всё готово — нажмите «Начать видеоанализ»."
      : verdict.message;
  } catch (error) {
    model.verdict = { canStart: false };
    model.status = `Ошибка проверки: ${error.message || error}`;
  }
  setPhase("ready");
}

async function startAnalysis() {
  if (!model.check || !(model.verdict && model.verdict.canStart)) return;
  const conditions = model.check.conditions();
  await unlockAudio();
  if (!isCameraActive()) {
    model.message = "Камера выключилась. Проверьте оборудование ещё раз.";
    setPhase("error");
    return;
  }
  model.progress = 0;
  model.sawScreening = false;
  setPhase("running");
  try {
    await api("/api/actions/start_screening", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_conditions: conditions }),
    });
  } catch (error) {
    model.message = `Не удалось запустить видеоанализ: ${error.message || error}`;
    log(`[screening] start error: ${error.message || error}`);
    setPhase("error");
    return;
  }
  await streamRppgFrames((fraction) => {
    model.progress = fraction;
    renderProgress();
  });
  if (model.phase === "running") setPhase("processing");
}

// Moved from app.js (_streamRppgFrames): browser-side frame capture sent to
// /ws/rppg for the pulse estimate; the camera stays on in the browser.
async function streamRppgFrames(onProgress) {
  const intervalMs = Math.round(1000 / RPPG_FPS);
  const maxFrames = Math.ceil(RPPG_SECONDS * RPPG_FPS);
  const videoEl = cameraVideo();
  if (!videoEl || !isCameraActive()) {
    log("[screening] no camera stream, skipping rPPG frame capture");
    return;
  }

  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 240;
  const ctx2d = canvas.getContext("2d");

  const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
  let ws;
  try {
    ws = new WebSocket(`${wsProto}//${location.host}/ws/rppg`);
  } catch (err) {
    log(`[screening] WebSocket open failed: ${err.message || err}`);
    return;
  }
  await new Promise((resolve) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", resolve, { once: true });
  });
  if (ws.readyState !== WebSocket.OPEN) {
    log("[screening] WebSocket not open, skipping frame stream");
    return;
  }

  log(`[screening] streaming ${maxFrames} frames to server (~${RPPG_SECONDS}s)`);
  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.done) log(`[screening] rPPG done: bpm=${msg.heart_rate_bpm} status=${msg.heart_rate_status}`);
    } catch (_) {
      // progress acks are not JSON-relevant
    }
  });

  let sent = 0;
  const startedAt = Date.now();
  while (sent < maxFrames && ws.readyState === WebSocket.OPEN) {
    try {
      ctx2d.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.75));
      if (blob && ws.readyState === WebSocket.OPEN) {
        ws.send(await blob.arrayBuffer());
        sent += 1;
        onProgress(sent / maxFrames);
      }
    } catch (err) {
      log(`[screening] frame capture error: ${err.message || err}`);
      break;
    }
    const delay = Math.max(0, sent * intervalMs - (Date.now() - startedAt));
    if (delay > 0) await new Promise((r) => setTimeout(r, delay));
  }

  log(`[screening] sent ${sent} frames, waiting for rPPG result…`);
  // Give the server time to finish processing and close; wait up to 60s
  if (ws.readyState === WebSocket.OPEN) {
    await new Promise((resolve) => {
      const timer = setTimeout(() => { ws.close(); resolve(); }, 60000);
      ws.addEventListener("close", () => { clearTimeout(timer); resolve(); }, { once: true });
    });
  }
}

// ---- Rendering -----------------------------------------------------------

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

function currentStepIndex() {
  switch (model.phase) {
    case "running":
    case "processing":
      return 1;
    case "analyzed":
    case "hads":
    case "san":
      return 2;
    case "done":
      return 3;
    case "error":
      return model.progress > 0 ? 1 : 0;
    default:
      return 0;
  }
}

function renderStepper() {
  if (!refs) return;
  const current = currentStepIndex();
  refs.stepper.innerHTML = "";
  STEPS.forEach((label, i) => {
    const step = el("li", "nm-step");
    const state = i < current ? "done" : i === current ? "current" : "todo";
    step.dataset.state = state;
    if (state === "current") step.setAttribute("aria-current", "step");
    const num = el("span", "nm-step-num", state === "done" ? "✓" : String(i + 1));
    num.setAttribute("aria-hidden", "true");
    const text = el("span", "nm-step-label", label);
    const sr = el("span", "nm-visually-hidden",
      state === "done" ? " — выполнено" : state === "current" ? " — текущий шаг" : " — впереди");
    step.append(num, text, sr);
    refs.stepper.appendChild(step);
  });
}

function renderChecks() {
  if (!refs || !refs.checkList) return;
  const requirements = model.check ? model.check.requirements : { camera: true, face: true, mic: true, voice: true };
  renderCheckList(refs.checkList, requirements, model.items);
}

function instructionList() {
  const items = [
    ["user", "Расположитесь удобно на расстоянии 50–70 см от камеры"],
    ["eye", "Смотрите прямо в камеру"],
    ["smile", "Постарайтесь сохранять спокойное выражение лица"],
  ];
  const icons = {
    user: '<path d="M12 12a4 4 0 100-8 4 4 0 000 8zm0 2c-4 0-8 2-8 5v1h16v-1c0-3-4-5-8-5z"/>',
    eye: '<path d="M12 5C6 5 2 12 2 12s4 7 10 7 10-7 10-7-4-7-10-7zm0 11a4 4 0 110-8 4 4 0 010 8z"/>',
    smile: '<path d="M12 2a10 10 0 100 20 10 10 0 000-20zM8.5 8a1.5 1.5 0 110 3 1.5 1.5 0 010-3zm7 0a1.5 1.5 0 110 3 1.5 1.5 0 010-3zM12 18c-2.5 0-4.5-1.5-5.3-3.5h10.6C16.5 16.5 14.5 18 12 18z"/>',
  };
  const list = el("ul", "nm-instructions");
  for (const [icon, text] of items) {
    const li = el("li");
    li.innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${icons[icon]}</svg>`;
    li.appendChild(el("span", null, text));
    list.appendChild(li);
  }
  return list;
}

function renderSide() {
  if (!refs || !refs.side) return;
  const side = refs.side;
  side.innerHTML = "";
  const phase = model.phase;

  if (phase === "running" || phase === "processing") {
    side.append(el("h2", "nm-panel-title", "Идёт видеоанализ"));
    side.append(el("p", "nm-panel-text", phase === "running"
      ? "Смотрите в камеру и не отворачивайтесь. Это займёт около 20 секунд."
      : "Запись сделана. Обрабатываю результат — это может занять до минуты."));
    const bar = el("div", "nm-progress");
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-label", "Ход видеоанализа");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    const fill = el("div", "nm-progress-fill");
    bar.appendChild(fill);
    const label = el("p", "nm-progress-label");
    refs.progressBar = bar;
    refs.progressFill = fill;
    refs.progressLabel = label;
    side.append(bar, label);
    renderProgress();
    return;
  }
  if (phase === "analyzed" || phase === "hads") {
    side.append(el("h2", "nm-panel-title", "Видеоанализ завершён"));
    side.append(el("p", "nm-panel-text", phase === "analyzed"
      ? "Через несколько секунд откроется тест на тревожность: 14 вопросов, ответ выбирается нажатием на подходящий вариант."
      : "Сейчас начнётся тест на тревожность."));
    return;
  }
  if (phase === "error") {
    side.append(el("h2", "nm-panel-title", "Скрининг не завершён"));
    side.append(el("p", "nm-panel-text", model.message));
    side.append(button("Начать заново", "primary nm-btn-block", resetToStart));
    return;
  }

  // idle / checking / ready
  side.append(el("h2", "nm-panel-title", "Видеоанализ"));
  side.append(el("p", "nm-panel-text nm-optional-text", "Смотрите в камеру и сохраняйте спокойное выражение лица."));
  // Actions before the instruction list: at the large interface scale the
  // main action must stay visible without scrolling
  const actions = el("div", "nm-side-actions");
  if (phase === "ready") {
    const start = button("Начать видеоанализ", "primary nm-btn-block", startAnalysis);
    start.insertAdjacentHTML("afterbegin", '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>');
    start.disabled = !(model.verdict && model.verdict.canStart);
    actions.append(start, button("Проверить оборудование ещё раз", "secondary nm-btn-block", runEquipmentCheck));
  } else {
    const check = button(phase === "checking" ? "Идёт проверка…" : "Проверить оборудование", "primary nm-btn-block", runEquipmentCheck);
    check.disabled = phase === "checking";
    actions.append(check);
  }
  side.append(actions);
  const status = el("p", "nm-status-line", model.status);
  status.setAttribute("role", "status");
  side.append(status, instructionList());
}

function renderProgress() {
  if (!refs || !refs.progressFill) return;
  const percent = model.phase === "processing" ? 100 : Math.round(model.progress * 100);
  refs.progressFill.style.width = `${percent}%`;
  refs.progressBar.setAttribute("aria-valuenow", String(percent));
  const left = Math.max(0, Math.ceil(RPPG_SECONDS * (1 - model.progress)));
  refs.progressLabel.textContent = model.phase === "processing"
    ? "Обработка записи…"
    : `Осталось примерно ${left} с`;
}

function attachCamera() {
  if (!refs || !refs.video) return;
  const stream = cameraStream();
  if (refs.video.srcObject !== stream) refs.video.srcObject = stream;
  const on = Boolean(stream && isCameraActive());
  refs.videoOverlay.hidden = on;
  refs.videoCaption.textContent = on ? "Камера активна" : "Камера выключена";
}

function buildEquipmentView() {
  const grid = el("div", "nm-screening-grid");

  const checks = el("section", "nm-panel");
  checks.setAttribute("aria-labelledby", "nm-screening-checks-title");
  const checksTitle = el("h2", "nm-panel-title", "Проверка оборудования");
  checksTitle.id = "nm-screening-checks-title";
  const checkList = el("ul", "nm-check-list");
  checkList.setAttribute("aria-live", "polite");
  checks.append(checksTitle, el("p", "nm-panel-text nm-optional-text", "Убедитесь, что все устройства работают корректно."), checkList);

  const frame = el("div", "nm-video-frame");
  const video = document.createElement("video");
  video.autoplay = true;
  video.muted = true;
  video.playsInline = true;
  video.setAttribute("aria-label", "Изображение с камеры");
  const overlay = el("div", "nm-video-overlay", "Камера выключена. Нажмите «Проверить оборудование».");
  const caption = el("div", "nm-video-caption");
  frame.append(video, overlay, caption);

  const side = el("section", "nm-panel nm-screening-side");
  side.setAttribute("aria-live", "polite");

  grid.append(checks, frame, side);
  refs.checkList = checkList;
  refs.video = video;
  refs.videoOverlay = overlay;
  refs.videoCaption = caption;
  refs.side = side;
  return grid;
}

function buildDoneView() {
  const card = el("section", "nm-panel nm-result");
  const title = el("h2", "nm-panel-title", "Скрининг завершён");
  title.tabIndex = -1;
  card.append(
    title,
    el("p", "nm-panel-text", "Спасибо! Результаты видеоанализа и теста сохранены в вашем профиле. Их можно посмотреть в разделе «Отчёты»."),
  );
  const row = el("div", "nm-btn-row");
  row.append(
    button("В меню", "primary", () => window.nmOpenSection && window.nmOpenSection("home")),
    button("Открыть отчёты", "secondary", () => {
      if (window.nmOpenSection) window.nmOpenSection("reports");
    }),
    button("Пройти скрининг ещё раз", "secondary", resetToStart),
  );
  card.appendChild(row);
  refs.focusTarget = title;
  return card;
}

function render() {
  if (!host) return;
  const previousMode = refs && refs.mode;
  const modes = { san: "san", done: "done", hads: "hads" };
  const mode = modes[model.phase] || "equipment";

  if (!refs || refs.mode !== mode || (mode === "san" && refs.sanElement !== model.sanElement)) {
    if (refs && refs.video) refs.video.srcObject = null;
    if (refs && refs.hadsView) refs.hadsView.destroy();
    host.innerHTML = "";
    refs = { mode };
    host.appendChild(el("p", "nm-workarea-subtitle", "Проверьте оборудование и выполните короткую видеофиксацию"));
    const stepper = el("ol", "nm-stepper");
    stepper.setAttribute("aria-label", "Шаги скрининга");
    refs.stepper = stepper;
    host.appendChild(stepper);
    if (mode === "equipment") {
      host.appendChild(buildEquipmentView());
      const help = el("p", "nm-help-bar", "Если у вас возникли трудности, попросите помощи у близких или у специалиста.");
      host.appendChild(help);
    } else if (mode === "hads") {
      refs.hadsView = createHadsView();
      host.appendChild(refs.hadsView.element);
    } else if (mode === "san") {
      host.appendChild(model.sanElement);
      refs.sanElement = model.sanElement;
    } else {
      host.appendChild(buildDoneView());
    }
  }

  renderStepper();
  if (mode === "equipment") {
    renderChecks();
    renderSide();
    attachCamera();
  }
  // Moving into a new part of the scenario moves focus to its heading
  if (previousMode && previousMode !== mode) {
    const target = mode === "san"
      ? model.sanElement.querySelector("h2")
      : mode === "hads"
        ? refs.hadsView.element.querySelector("legend")
        : refs.focusTarget;
    if (target) {
      target.tabIndex = -1;
      target.focus();
    }
  }
}

// ---- Screen contract used by js/shell.js ----------------------------------

export const screeningScreen = {
  mount(container) {
    host = container;
    refs = null;
    render();
  },
  unmount() {
    if (refs && refs.video) refs.video.srcObject = null;
    if (refs && refs.hadsView) refs.hadsView.destroy();
    host = null;
    refs = null;
  },
  isBusy() {
    return BUSY_PHASES.has(model.phase);
  },
  // True while the server-chained HADS belongs to this scenario (step 3)
  ownsHads() {
    return ["running", "processing", "analyzed", "hads"].includes(model.phase);
  },
  leaveWarning() {
    return {
      title: "Скрининг ещё не завершён",
      message: "Если перейти в другой раздел, скрининг продолжится. Вернуться к нему можно через «Базовый скрининг» в меню.",
    };
  },
};

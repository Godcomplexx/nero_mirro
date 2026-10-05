// neuro_mirror/web/static/js/screens/test-screen.js
//
// Shared shape of the «Проверка самочувствия» (HADS) and «Когнитивный
// тест» (MoCA) screens, embedded in the work area instead of the old dark
// overlays: equipment check (ТЗ 6.3.2: tests start only after it) → the test
// view → a neutral result card. The running test is driven by the server;
// the screen follows it through the test's controller, so a test started
// elsewhere (e.g. «Продолжить сессию») is shown here as well.

import { api, unlockAudio, userConsents } from "../core/legacy.js";
import { createSessionCheck, getCheckRequirements } from "../core/session-check.js";
import { renderCheckList } from "../components/check-list.js";

const START_TIMEOUT_MS = 15000;

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

// config: { scenario, subtitle, introTitle, introText, startUrl, controller,
//           createView, doneTitle, doneText, stoppedTitle, leaveWarning }
export function createTestScreen(config) {
  // intro → checking → ready → starting → running → done | stopped
  const model = { phase: "intro", check: null, items: {}, verdict: null, status: "", stoppedText: "" };
  let host = null;
  let view = null;
  let startTimer = null;

  config.controller.subscribe((state) => {
    let next = null;
    if (state.status === "running" && model.phase !== "running") next = "running";
    else if (state.status === "finished" && model.phase === "running") next = "done";
    else if (state.status === "stopped" && model.phase === "running") {
      next = "stopped";
      model.stoppedText = state.message || "";
    }
    if (!next) return;
    if (startTimer) {
      clearTimeout(startTimer);
      startTimer = null;
    }
    model.phase = next;
    render();
  });

  async function runCheck() {
    if (model.check) model.check.stop();
    model.items = {};
    model.verdict = null;
    model.status = "";
    model.check = createSessionCheck(config.scenario, {
      onItem(name, state, note) {
        model.items[name] = { state, note };
        render();
      },
      onStatus(text) {
        model.status = text;
        render();
      },
    });
    model.phase = "checking";
    render();
    try {
      model.verdict = await model.check.run();
      model.status = model.verdict.message;
    } catch (error) {
      model.verdict = { canStart: false };
      model.status = `Ошибка проверки: ${error.message || error}`;
    }
    model.phase = "ready";
    render();
  }

  async function start() {
    if (!model.check || !(model.verdict && model.verdict.canStart)) return;
    const conditions = model.check.conditions();
    await unlockAudio();
    config.controller.reset();
    model.phase = "starting";
    model.status = "";
    render();
    try {
      await api(config.startUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_conditions: conditions }),
      });
    } catch (error) {
      model.phase = "ready";
      model.status = `Не удалось запустить тест: ${error.message || error}`;
      render();
      return;
    }
    startTimer = setTimeout(() => {
      if (model.phase !== "starting") return;
      model.phase = "ready";
      model.status = "Тест не запустился: сервер не ответил. Попробуйте ещё раз.";
      render();
    }, START_TIMEOUT_MS);
  }

  function startOver() {
    config.controller.reset();
    model.phase = "intro";
    model.items = {};
    model.verdict = null;
    model.status = "";
    render();
  }

  function buildIntro() {
    const panel = el("section", "nm-panel nm-test-intro");
    panel.append(el("h2", "nm-panel-title", config.introTitle), el("p", "nm-panel-text", config.introText));
    const list = el("ul", "nm-check-list");
    list.setAttribute("aria-live", "polite");
    const requirements = model.check ? model.check.requirements : getCheckRequirements(config.scenario);
    renderCheckList(list, requirements, model.items);
    panel.appendChild(list);

    // Without the audio consent the microphone is not used at all — say so
    // instead of leaving an empty check list
    if (userConsents().audio === false) {
      panel.appendChild(el("p", "nm-help-bar", config.scenario === "moca"
        ? "В профиле нет согласия на обработку аудиоданных. Этот тест проходится голосом, поэтому запустить его не получится. Выберите или создайте профиль с таким согласием."
        : "В профиле нет согласия на обработку аудиоданных, поэтому микрофон не используется. Отвечать нужно нажатием на варианты."));
    }

    const row = el("div", "nm-btn-row nm-test-actions");
    const phase = model.phase;
    if (phase === "ready" || phase === "starting") {
      const go = button(phase === "starting" ? "Запускаю тест…" : "Начать тест", "primary", start);
      go.disabled = phase === "starting" || !(model.verdict && model.verdict.canStart);
      row.append(go, button("Проверить оборудование ещё раз", "secondary", runCheck));
      row.lastChild.disabled = phase === "starting";
    } else {
      const check = button(phase === "checking" ? "Идёт проверка…" : "Проверить оборудование", "primary", runCheck);
      check.disabled = phase === "checking";
      row.appendChild(check);
    }
    panel.appendChild(row);
    const status = el("p", "nm-status-line", model.status);
    status.setAttribute("role", "status");
    panel.appendChild(status);
    return panel;
  }

  function buildResult(title, text, restartLabel) {
    const card = el("section", "nm-panel nm-result");
    const heading = el("h2", "nm-panel-title", title);
    heading.tabIndex = -1;
    card.append(heading, el("p", "nm-panel-text", text));
    const row = el("div", "nm-btn-row");
    row.append(
      button("В меню", "primary", () => window.nmOpenSection && window.nmOpenSection("home")),
      button("Открыть отчёты", "secondary", () => {
        if (window.nmOpenSection) window.nmOpenSection("reports");
        }),
    );
    row.appendChild(button(restartLabel, "secondary", startOver));
    card.appendChild(row);
    return card;
  }

  let renderedMode = null;

  function render() {
    if (!host) return;
    const mode = ["running", "done", "stopped"].includes(model.phase) ? model.phase : "intro";
    if (mode === "running" && renderedMode === "running") return; // the view updates itself
    if (view) {
      view.destroy();
      view = null;
    }
    host.innerHTML = "";
    host.appendChild(el("p", "nm-workarea-subtitle", config.subtitle));
    let focusTarget = null;
    if (mode === "running") {
      view = config.createView();
      host.appendChild(view.element);
    } else if (mode === "done") {
      const card = buildResult(config.doneTitle, config.doneText, "Пройти ещё раз");
      focusTarget = card.querySelector("h2");
      host.appendChild(card);
    } else if (mode === "stopped") {
      const text = [model.stoppedText, "Уже данные ответы сохранены — продолжить тест можно из главного меню («Продолжить сессию») или начать заново."]
        .filter(Boolean)
        .join(" ");
      const card = buildResult(config.stoppedTitle, text, "Начать заново");
      focusTarget = card.querySelector("h2");
      host.appendChild(card);
    } else {
      host.appendChild(buildIntro());
    }
    if (renderedMode && renderedMode !== mode && focusTarget) focusTarget.focus();
    renderedMode = mode;
  }

  return {
    mount(container) {
      host = container;
      renderedMode = null;
      render();
    },
    unmount() {
      if (view) {
        view.destroy();
        view = null;
      }
      host = null;
      renderedMode = null;
    },
    isBusy() {
      return ["checking", "starting", "running"].includes(model.phase);
    },
    leaveWarning() {
      return config.leaveWarning;
    },
  };
}

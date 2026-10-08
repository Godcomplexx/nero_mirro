// neuro_mirror/web/static/js/components/moca-test.js
//
// Voice MoCA task view embedded in the work area (deck slide 7): «Задание N
// из 11» with the 11 steps, the task text, whether the instruction is being
// spoken or the answer is being recorded. Task texts and their order come
// from the server via mocaController. Styles: css/components/moca.css.
//
// «Повторить инструкцию» replays the current task's instruction and
// «Приступить к выполнению» starts the task; both are commands to the MoCA
// plugin (moca_repeat_prompt, moca_begin_task). The task time limit comes
// from the server with the task.

import { mocaController } from "../core/moca-controller.js";
import { confirmDialog } from "./confirm-dialog.js";

const SPEAKER_ICON =
  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 10v4h4l5 5V5L7 10H3zm13.5 2A4.5 4.5 0 0014 8v8a4.5 4.5 0 002.5-4zM14 3.2v2.1a7 7 0 010 13.4v2.1a9 9 0 000-17.6z"/></svg>';
const MIC_ICON =
  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 14a3 3 0 003-3V5a3 3 0 00-6 0v6a3 3 0 003 3zm5-3a5 5 0 01-10 0H5a7 7 0 006 6.9V21h2v-3.1A7 7 0 0019 11h-2z"/></svg>';

export function createMocaView() {
  const root = document.createElement("section");
  root.className = "nm-moca";
  root.setAttribute("aria-label", "Когнитивный тест MoCA");

  const counter = document.createElement("p");
  counter.className = "nm-moca-counter";
  const steps = document.createElement("ol");
  steps.className = "nm-moca-steps";
  steps.setAttribute("aria-hidden", "true"); // the counter above says the same in words

  const card = document.createElement("div");
  card.className = "nm-panel nm-moca-card";
  const kicker = document.createElement("p");
  kicker.className = "nm-moca-kicker";
  const task = document.createElement("h2");
  task.className = "nm-moca-task";
  task.tabIndex = -1;

  const voice = document.createElement("div");
  voice.className = "nm-moca-voice";
  voice.setAttribute("role", "status");
  const voiceIcon = document.createElement("span");
  voiceIcon.className = "nm-moca-voice-icon";
  const voiceText = document.createElement("span");
  voiceText.className = "nm-moca-voice-text";
  voice.append(voiceIcon, voiceText);

  const actions = document.createElement("div");
  actions.className = "nm-btn-row nm-moca-actions";
  const repeat = document.createElement("button");
  repeat.type = "button";
  repeat.className = "nm-btn nm-btn-secondary";
  repeat.innerHTML = `${SPEAKER_ICON}<span>Повторить инструкцию</span>`;
  repeat.onclick = () => mocaController.repeatPrompt();
  const begin = document.createElement("button");
  begin.type = "button";
  begin.className = "nm-btn nm-btn-primary";
  begin.textContent = "Приступить к выполнению";
  begin.hidden = true;
  begin.onclick = () => mocaController.beginTask();
  actions.append(repeat, begin);

  const tip = document.createElement("p");
  tip.className = "nm-help-bar";
  tip.textContent = "Отвечайте вслух, когда увидите «Говорите». Говорите чётко и спокойно.";

  card.append(kicker, task, voice, actions);

  const footer = document.createElement("div");
  footer.className = "nm-btn-row nm-moca-footer";
  const stopButton = document.createElement("button");
  stopButton.type = "button";
  stopButton.className = "nm-btn nm-btn-secondary";
  stopButton.textContent = "Прервать тест";
  footer.appendChild(stopButton);

  root.append(counter, steps, card, tip, footer);

  let lastTaskIndex = null;

  function renderSteps(state) {
    steps.innerHTML = "";
    for (let i = 0; i < state.taskTotal; i += 1) {
      const step = document.createElement("li");
      step.className = "nm-moca-step";
      step.dataset.state = i < state.taskIndex ? "done" : i === state.taskIndex ? "current" : "todo";
      step.textContent = i < state.taskIndex ? "✓" : String(i + 1);
      steps.appendChild(step);
    }
  }

  function render(state) {
    const total = state.taskTotal || 11;
    const finished = state.taskIndex >= total;
    counter.textContent = finished ? "Все задания выполнены" : `Задание ${state.taskIndex + 1} из ${total}`;
    renderSteps(state);

    kicker.textContent = state.domain ? `Задание · ${state.domain}` : "Задание";
    // While the answer is recorded the task text is hidden: memory tasks must
    // be answered from memory (same rule as before the redesign)
    if (state.recording) {
      task.textContent = "Отвечайте сейчас";
    } else if (finished) {
      task.textContent = "Тест завершён. Сохраняю результат…";
    } else {
      task.textContent = state.hint || "Слушайте инструкцию";
    }

    // «Приступить» показывается, пока ядро ждёт готовности; повтор инструкции
    // доступен всё задание, кроме времени записи ответа — иначе озвучка
    // наложится на речь человека.
    begin.hidden = !state.awaitingStart || finished;
    repeat.disabled = state.recording || state.speaking || finished;

    voice.dataset.mode = state.recording ? "recording" : state.speaking ? "speaking" : "idle";
    if (state.recording) {
      voiceIcon.innerHTML = MIC_ICON;
      voiceText.textContent = "Говорите — идёт запись ответа";
    } else if (state.speaking) {
      voiceIcon.innerHTML = SPEAKER_ICON;
      voiceText.textContent = "Инструкция воспроизводится голосом";
    } else {
      voiceIcon.innerHTML = SPEAKER_ICON;
      voiceText.textContent = state.message && state.message !== "Говорите..." ? state.message : "Подождите…";
    }

    stopButton.disabled = finished;
    if (lastTaskIndex !== null && lastTaskIndex !== state.taskIndex && root.contains(document.activeElement)) {
      task.focus();
    }
    lastTaskIndex = state.taskIndex;
  }

  stopButton.addEventListener("click", async () => {
    const confirmed = await confirmDialog({
      title: "Прервать тест?",
      message: "Выполненные задания сохранятся. Продолжить тест можно будет позже из главного меню.",
      confirmLabel: "Прервать",
      cancelLabel: "Продолжить тест",
    });
    if (confirmed) mocaController.stop();
  });

  const unsubscribe = mocaController.subscribe(render);
  render(mocaController.state);
  return { element: root, destroy: unsubscribe };
}

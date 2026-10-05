// neuro_mirror/web/static/js/components/hads-test.js
//
// HADS question view embedded in the work area (deck slide 6): progress,
// one question, four answer options as large radio rows, «Следующий
// вопрос». Everything shown comes from the server via hadsController; the
// score is never shown. Used by «Проверка самочувствия» and by step 3 of
// «Базовый скрининг». Styles: css/components/hads.css.
//
// Deck differences forced by the backend: the server accepts only an answer
// to the current question, so there is no «Назад»; if the profile allows
// audio the server also listens for a spoken answer, which is mentioned.

import { hadsController } from "../core/hads-controller.js";
import { confirmDialog } from "./confirm-dialog.js";

let viewCounter = 0;

export function createHadsView() {
  viewCounter += 1;
  const uid = `nm-hads-${viewCounter}`;
  let questionKey = null;
  let choice = null;
  let sending = false;

  const root = document.createElement("section");
  root.className = "nm-hads";
  root.setAttribute("aria-label", "Тест HADS");

  const head = document.createElement("div");
  head.className = "nm-hads-head";
  const counter = document.createElement("p");
  counter.className = "nm-hads-counter";
  const percent = document.createElement("span");
  percent.className = "nm-hads-percent";
  head.append(counter, percent);

  const bar = document.createElement("div");
  bar.className = "nm-progress nm-hads-progress";
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-label", "Пройдено вопросов");
  bar.setAttribute("aria-valuemin", "0");
  const fill = document.createElement("div");
  fill.className = "nm-progress-fill";
  bar.appendChild(fill);

  const info = document.createElement("p");
  info.className = "nm-help-bar nm-hads-info";
  info.textContent = "Выберите один вариант, который лучше всего описывает ваше состояние за последнюю неделю.";

  const card = document.createElement("div");
  card.className = "nm-panel nm-hads-card";
  const part = document.createElement("p");
  part.className = "nm-hads-part";
  const fieldset = document.createElement("fieldset");
  fieldset.className = "nm-hads-question";
  const legend = document.createElement("legend");
  legend.className = "nm-hads-question-text";
  legend.id = `${uid}-question`;
  const options = document.createElement("div");
  options.className = "nm-hads-options";
  fieldset.append(legend, options);
  const voiceNote = document.createElement("p");
  voiceNote.className = "nm-hads-voice";
  const status = document.createElement("p");
  status.className = "nm-status-line";
  status.setAttribute("role", "status");
  card.append(part, fieldset, voiceNote, status);

  const actions = document.createElement("div");
  actions.className = "nm-btn-row nm-hads-actions";
  const stopButton = document.createElement("button");
  stopButton.type = "button";
  stopButton.className = "nm-btn nm-btn-secondary";
  stopButton.textContent = "Прервать тест";
  const nextButton = document.createElement("button");
  nextButton.type = "button";
  nextButton.className = "nm-btn nm-btn-primary";
  nextButton.textContent = "Следующий вопрос";
  actions.append(stopButton, nextButton);

  const saved = document.createElement("p");
  saved.className = "nm-hads-saved";
  saved.textContent = "Ответы сохраняются автоматически.";

  root.append(head, bar, info, card, actions, saved);

  function renderOptions(state) {
    options.innerHTML = "";
    state.options.forEach((text, index) => {
      const id = `${uid}-${state.questionIndex}-${index}`;
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `${uid}-q${state.questionIndex}`;
      input.id = id;
      input.className = "nm-hads-radio";
      input.value = String(index);
      input.addEventListener("change", () => {
        choice = index;
        render(hadsController.state);
      });
      const label = document.createElement("label");
      label.className = "nm-hads-option";
      label.htmlFor = id;
      label.textContent = text;
      options.append(input, label);
    });
  }

  function render(state) {
    const total = state.questionTotal || 14;
    const hasQuestion = state.questionIndex >= 0 && state.questionIndex < total && Boolean(state.text);
    const answered = Math.max(0, Math.min(total, state.questionIndex + (state.selected != null ? 1 : 0)));
    const pct = Math.round((answered / total) * 100);
    counter.textContent = hasQuestion ? `Вопрос ${state.questionIndex + 1} из ${total}` : "Тест HADS";
    percent.textContent = `${pct}%`;
    fill.style.width = `${pct}%`;
    bar.setAttribute("aria-valuemax", String(total));
    bar.setAttribute("aria-valuenow", String(answered));

    const key = `${state.questionId}:${state.questionIndex}`;
    if (key !== questionKey) {
      questionKey = key;
      choice = null;
      sending = false;
      renderOptions(state);
    }

    part.textContent = hasQuestion && state.part ? `Раздел: ${state.part}` : "";
    legend.textContent = hasQuestion
      ? state.text
      : state.questionIndex >= total
        ? "Все вопросы пройдены. Сохраняю ответы…"
        : "Приготовьтесь — сейчас начнётся тест.";
    fieldset.hidden = false;

    const accepted = state.selected != null;
    for (const input of options.querySelectorAll("input")) {
      const index = Number(input.value);
      input.checked = accepted ? index === state.selected : index === choice;
      input.disabled = accepted || sending;
    }
    nextButton.disabled = !hasQuestion || accepted || sending || choice == null;
    nextButton.textContent = state.questionIndex === total - 1 ? "Завершить тест" : "Следующий вопрос";
    stopButton.disabled = !hasQuestion && state.questionIndex >= total;

    voiceNote.textContent = state.recording
      ? "Можно также ответить голосом — назовите номер варианта."
      : "";
    status.textContent = accepted ? "Ответ принят." : "";
  }

  nextButton.addEventListener("click", async () => {
    if (choice == null) return;
    sending = true;
    render(hadsController.state);
    try {
      await hadsController.answer(choice);
    } catch (_) {
      sending = false;
      status.textContent = "Не удалось отправить ответ. Попробуйте ещё раз.";
      render(hadsController.state);
    }
  });

  stopButton.addEventListener("click", async () => {
    const confirmed = await confirmDialog({
      title: "Прервать тест?",
      message: "Ответы, которые вы уже дали, сохранятся. Продолжить тест можно будет позже из главного меню.",
      confirmLabel: "Прервать",
      cancelLabel: "Продолжить тест",
    });
    if (confirmed) hadsController.stop();
  });

  const unsubscribe = hadsController.subscribe(render);
  render(hadsController.state);

  return {
    element: root,
    destroy: unsubscribe,
  };
}

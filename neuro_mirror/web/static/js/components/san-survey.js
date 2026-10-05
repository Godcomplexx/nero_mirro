// neuro_mirror/web/static/js/components/san-survey.js
//
// Оценка самочувствия (shortened SAN block, deck slide 5): questions answered
// on a face scale with text labels. A shared component — the deck uses it
// after screening and before/after training. Renders whatever questionnaire
// the server provides ({ questions, scale }); answers are handed to onDone.

// Faces are presentation only; questions and scale labels come from the
// server (js/core/questionnaires.js). Face i is picked by the option's
// position on the negative → positive scale, so any scale length works.
const FACES = [
  { color: "#f87171", mouth: "M9 17c1.6-2 4.4-2 6 0" },
  { color: "#fb923c", mouth: "M9 16.5c1.8-1.2 4.2-1.2 6 0" },
  { color: "#facc15", mouth: "M9 15.5h6" },
  { color: "#a3e635", mouth: "M9 14.5c1.8 1.4 4.2 1.4 6 0" },
  { color: "#4ade80", mouth: "M8.5 14c2 2.8 5 2.8 7 0" },
];

function faceFor(position, count) {
  const index = count <= 1 ? 2 : Math.round((position / (count - 1)) * (FACES.length - 1));
  return FACES[index];
}

function faceSvg(face) {
  return (
    `<svg viewBox="0 0 24 24" aria-hidden="true">` +
    `<circle cx="12" cy="12" r="11" fill="${face.color}"/>` +
    `<circle cx="8.5" cy="9.5" r="1.3" fill="#1f2937"/>` +
    `<circle cx="15.5" cy="9.5" r="1.3" fill="#1f2937"/>` +
    `<path d="${face.mouth}" fill="none" stroke="#1f2937" stroke-width="1.6" stroke-linecap="round"/>` +
    `</svg>`
  );
}

let surveyCounter = 0;

export function createSanSurvey({ questionnaire, title, intro, finishLabel = "Завершить", onDone }) {
  const QUESTIONS = questionnaire.questions;
  const SCALE = questionnaire.scale;
  surveyCounter += 1;
  const uid = `nm-san-${surveyCounter}`;
  const answers = new Array(QUESTIONS.length).fill(null);
  let index = 0;

  const root = document.createElement("section");
  root.className = "nm-san";
  root.setAttribute("aria-labelledby", `${uid}-title`);

  const heading = document.createElement("h2");
  heading.className = "nm-san-title";
  heading.id = `${uid}-title`;
  heading.textContent = title;
  const introEl = document.createElement("p");
  introEl.className = "nm-san-intro";
  introEl.textContent = intro;

  const layout = document.createElement("div");
  layout.className = "nm-san-layout";

  // Left: all questions with their state, so the whole task is visible
  const list = document.createElement("ol");
  list.className = "nm-san-list";

  // Right: the current question
  const panel = document.createElement("div");
  panel.className = "nm-san-panel";
  const progressText = document.createElement("p");
  progressText.className = "nm-san-progress-text";
  const progress = document.createElement("div");
  progress.className = "nm-san-progress";
  progress.setAttribute("role", "progressbar");
  progress.setAttribute("aria-valuemin", "0");
  progress.setAttribute("aria-valuemax", String(QUESTIONS.length));
  const progressFill = document.createElement("div");
  progressFill.className = "nm-san-progress-fill";
  progress.appendChild(progressFill);

  const fieldset = document.createElement("fieldset");
  fieldset.className = "nm-san-question";
  const legend = document.createElement("legend");
  legend.className = "nm-san-question-text";
  const scale = document.createElement("div");
  scale.className = "nm-san-scale";
  fieldset.append(legend, scale);

  const actions = document.createElement("div");
  actions.className = "nm-btn-row nm-san-actions";
  const back = document.createElement("button");
  back.type = "button";
  back.className = "nm-btn nm-btn-secondary";
  back.textContent = "Назад";
  const next = document.createElement("button");
  next.type = "button";
  next.className = "nm-btn nm-btn-primary";
  actions.append(back, next);

  // No "answers are saved" hint here: SAN answers are not stored yet.
  panel.append(progressText, progress, fieldset, actions);
  layout.append(list, panel);
  root.append(heading, introEl, layout);

  function renderList() {
    list.innerHTML = "";
    QUESTIONS.forEach((question, i) => {
      const item = document.createElement("li");
      item.className = "nm-san-list-item";
      const answered = answers[i] !== null;
      item.dataset.state = i === index ? "current" : answered ? "done" : "todo";
      if (i === index) item.setAttribute("aria-current", "step");
      const mark = document.createElement("span");
      mark.className = "nm-san-list-mark";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = answered ? "✓" : String(i + 1);
      const text = document.createElement("span");
      text.textContent = question.text;
      const status = document.createElement("span");
      status.className = "nm-visually-hidden";
      status.textContent = answered ? " — отвечено" : " — без ответа";
      item.append(mark, text, status);
      list.appendChild(item);
    });
  }

  function renderProgress() {
    const question = QUESTIONS[index];
    const answeredCount = answers.filter((value) => value !== null).length;
    progressText.textContent = question.group
      ? `Вопрос ${index + 1} из ${QUESTIONS.length} · ${question.group}`
      : `Вопрос ${index + 1} из ${QUESTIONS.length}`;
    progress.setAttribute("aria-valuenow", String(answeredCount));
    progressFill.style.width = `${(answeredCount / QUESTIONS.length) * 100}%`;
    next.disabled = answers[index] === null;
  }

  function renderQuestion() {
    const question = QUESTIONS[index];
    legend.textContent = question.text;

    scale.innerHTML = "";
    scale.style.gridTemplateColumns = `repeat(${SCALE.length}, minmax(0, 1fr))`;
    SCALE.forEach((option, position) => {
      const id = `${uid}-q${index}-${option.value}`;
      const input = document.createElement("input");
      input.type = "radio";
      input.name = `${uid}-q${index}`;
      input.id = id;
      input.value = String(option.value);
      input.className = "nm-san-radio";
      input.checked = answers[index] === option.value;
      // Only state + progress update here: re-rendering the radios would
      // break arrow-key movement between faces.
      input.addEventListener("change", () => {
        answers[index] = option.value;
        renderList();
        renderProgress();
      });
      const label = document.createElement("label");
      label.className = "nm-san-option";
      label.htmlFor = id;
      label.innerHTML = `<span class="nm-san-face">${faceSvg(faceFor(position, SCALE.length))}</span>`;
      const caption = document.createElement("span");
      caption.className = "nm-san-caption";
      caption.textContent = option.label;
      label.appendChild(caption);
      scale.append(input, label);
    });

    back.disabled = index === 0;
    const last = index === QUESTIONS.length - 1;
    next.textContent = last ? finishLabel : "Следующий вопрос";
    renderProgress();
  }

  back.addEventListener("click", () => {
    if (index === 0) return;
    index -= 1;
    renderList();
    renderQuestion();
  });
  next.addEventListener("click", () => {
    if (answers[index] === null) return;
    if (index === QUESTIONS.length - 1) {
      if (onDone) {
        onDone(
          QUESTIONS.map((question, i) => ({ id: question.id, value: answers[i] }))
        );
      }
      return;
    }
    index += 1;
    renderList();
    renderQuestion();
    const firstRadio = scale.querySelector("input");
    if (firstRadio) firstRadio.focus();
  });

  renderList();
  renderQuestion();
  return root;
}

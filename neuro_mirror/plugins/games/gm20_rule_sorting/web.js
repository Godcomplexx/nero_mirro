const SVG_NS = "http://www.w3.org/2000/svg";
const TRIAL_SLOT_MS = 1000;

const TRAINING_REFERENCES = [
  { id: "reference-0", color: "red", shape: "triangle", count: 1 },
  { id: "reference-1", color: "green", shape: "circle", count: 2 },
  { id: "reference-2", color: "blue", shape: "square", count: 3 },
  { id: "reference-3", color: "yellow", shape: "star", count: 4 },
];
const TRAINING_TRIALS = [
  { stimulus: { color: "green", shape: "star", count: 3 }, answer: "reference-1" },
  { stimulus: { color: "blue", shape: "circle", count: 4 }, answer: "reference-2" },
];

export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new"><div><p class="game-kicker-new mono">АБСТРАКЦИЯ</p><h2>${definition.title}</h2><p data-instruction>Определите скрытое правило и выберите подходящую карточку.</p></div><div class="game-progress-new" data-progress>Инструкция</div></header>
    <main class="game-stage-new gm20-module is-instruction-stage">
      <section class="gm20-tutorial" data-tutorial>
        <h3>Как выполнять задание</h3>
        <ol><li>Сравните нижнюю карточку с четырьмя верхними.</li><li>Предположите, по какому скрытому правилу распределяются карточки.</li><li>Нажмите на подходящую верхнюю карточку. Правило во время игры может измениться.</li></ol>
        <div class="gm20-demo-placeholder"><span class="mono">ПРИМЕР ВЫПОЛНЕНИЯ</span><strong>Видеоинструкция появится здесь</strong></div>
        <button type="button" class="icon-btn primary-btn" data-start-training><span>Перейти к тренировке</span></button>
      </section>
      <section class="gm20-training" data-training hidden>
        <h3>Тренировочный пример</h3><p>Определите правило и распределите две карточки.</p>
        <div class="gm20-module-play"><section class="gm20-module-reference-wrap"><p class="mono">ВЫБЕРИТЕ ПОДХОДЯЩУЮ КАРТОЧКУ</p><div class="gm20-module-references" data-training-references></div></section><section class="gm20-module-stimulus-wrap"><p class="mono">СОРТИРУЕМАЯ КАРТОЧКА</p><div class="gm20-module-stimulus" data-training-stimulus></div></section></div>
        <p class="gm20-training-feedback" data-training-feedback aria-live="polite"></p>
      </section>
      <section class="gm20-complete" data-complete hidden><h3>Обучение завершено</h3><p>Вы правильно распределили обе карточки. Закончить обучение и начать игру?</p><div class="gm20-complete-actions"><button type="button" class="icon-btn gm20-secondary-btn" data-repeat><span>Повторить обучение</span></button><button type="button" class="icon-btn primary-btn" data-start><span>Да, начать игру</span></button></div></section>
      <div class="gm20-module-play" data-play hidden><section class="gm20-module-reference-wrap"><p class="mono">ВЫБЕРИТЕ ПОДХОДЯЩУЮ КАРТОЧКУ</p><div class="gm20-module-references" data-references></div></section><section class="gm20-module-stimulus-wrap"><p class="mono">СОРТИРУЕМАЯ КАРТОЧКА</p><div class="gm20-module-stimulus" data-stimulus></div></section></div>
      <div class="gm20-module-feedback" data-feedback hidden></div>
      <div class="game-result-new" data-result hidden><h3>Игра завершена</h3><p data-result-text></p><button type="button" class="icon-btn primary-btn" data-restart><span>Ещё раз</span></button></div>
    </main>
    <footer class="game-actions-new"><button type="button" class="icon-btn" data-close><span>К выбору игр</span></button></footer>`;

  const q = (selector) => container.querySelector(selector);
  const stage = q(".gm20-module");
  const instruction = q("[data-instruction]");
  const progress = q("[data-progress]");
  const tutorial = q("[data-tutorial]");
  const training = q("[data-training]");
  const complete = q("[data-complete]");
  const trainingReferences = q("[data-training-references]");
  const trainingStimulus = q("[data-training-stimulus]");
  const trainingFeedback = q("[data-training-feedback]");
  const play = q("[data-play]");
  const references = q("[data-references]");
  const stimulus = q("[data-stimulus]");
  const feedback = q("[data-feedback]");
  const result = q("[data-result]");
  const start = q("[data-start]");
  const restart = q("[data-restart]");
  const sections = [tutorial, training, complete, play, result];
  let state = null;
  let trainingIndex = 0;
  let accepting = false;
  let shownAt = 0;
  let token = 0;
  let active = true;
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function showOnly(section) {
    sections.forEach((item) => { item.hidden = item !== section; });
    stage.classList.toggle("is-instruction-stage", section === tutorial);
  }

  function createShape(shape, color) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("aria-hidden", "true");
    let node;
    if (shape === "circle") {
      node = document.createElementNS(SVG_NS, "circle");
      node.setAttribute("cx", "50"); node.setAttribute("cy", "50"); node.setAttribute("r", "34");
    } else if (shape === "triangle") {
      node = document.createElementNS(SVG_NS, "polygon"); node.setAttribute("points", "50,12 90,84 10,84");
    } else if (shape === "star") {
      node = document.createElementNS(SVG_NS, "polygon"); node.setAttribute("points", "50,7 61,36 93,37 68,56 77,88 50,69 23,88 32,56 7,37 39,36");
    } else {
      node = document.createElementNS(SVG_NS, "rect");
      node.setAttribute("x", "16"); node.setAttribute("y", "16"); node.setAttribute("width", "68"); node.setAttribute("height", "68"); node.setAttribute("rx", "5");
    }
    node.classList.add(`is-${color}`);
    svg.append(node);
    return svg;
  }

  function createCard(card, interactive = false) {
    const root = document.createElement(interactive ? "button" : "div");
    if (interactive) root.type = "button";
    root.className = `gm20-module-card ${interactive ? "gm20-module-reference" : ""} count-${card.count}`;
    const symbols = document.createElement("div");
    symbols.className = `gm20-module-symbols count-${card.count}`;
    for (let index = 0; index < card.count; index += 1) symbols.append(createShape(card.shape, card.color));
    root.append(symbols);
    return root;
  }

  function appendReferences(target, items, onSelect) {
    target.replaceChildren();
    const order = { 1: 0, 4: 1, 2: 2, 3: 3 };
    [...items].sort((a, b) => order[a.count] - order[b.count]).forEach((reference) => {
      const card = createCard(reference, true);
      card.setAttribute("aria-label", `Эталонная карточка: фигур ${reference.count}`);
      card.onclick = () => onSelect(reference.id, card);
      target.append(card);
    });
  }

  function renderTraining() {
    const trial = TRAINING_TRIALS[trainingIndex];
    trainingFeedback.textContent = "";
    trainingFeedback.className = "gm20-training-feedback";
    appendReferences(trainingReferences, TRAINING_REFERENCES, submitTraining);
    trainingStimulus.replaceChildren(createCard(trial.stimulus));
    progress.textContent = `Тренировка · ${trainingIndex + 1} из ${TRAINING_TRIALS.length}`;
  }

  async function submitTraining(selected, card) {
    if (!active || training.hidden) return;
    if (selected !== TRAINING_TRIALS[trainingIndex].answer) {
      card.classList.add("is-incorrect");
      trainingFeedback.className = "gm20-training-feedback is-incorrect";
      trainingFeedback.textContent = "Неверно. Попробуйте определить правило ещё раз.";
      await delay(450);
      card.classList.remove("is-incorrect");
      return;
    }
    trainingReferences.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    card.classList.add("is-correct");
    trainingFeedback.className = "gm20-training-feedback is-correct";
    trainingFeedback.textContent = "Верно";
    await delay(650);
    if (!active) return;
    trainingIndex += 1;
    if (trainingIndex < TRAINING_TRIALS.length) return renderTraining();
    showOnly(complete);
    progress.textContent = "Обучение завершено";
    instruction.textContent = "Тренировочные карточки распределены правильно.";
  }

  function beginTraining() {
    trainingIndex = 0;
    showOnly(training);
    instruction.textContent = "Определите скрытое правило по результатам своих ответов.";
    renderTraining();
  }

  function renderTrial(payload) {
    state = payload;
    accepting = true;
    shownAt = performance.now();
    appendReferences(references, payload.references, submitAnswer);
    stimulus.replaceChildren(createCard(payload.stimulus));
    progress.textContent = `Карточка ${payload.trial} из ${payload.trial_count}`;
    instruction.textContent = "Выберите эталонную карточку по предполагаемому правилу.";
    feedback.hidden = true;
    feedback.className = "gm20-module-feedback";
    showOnly(play);
  }

  async function submitAnswer(selectedReference, card) {
    if (!accepting || !state) return;
    accepting = false;
    const currentToken = token;
    card.classList.add("is-selected");
    references.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    try {
      const payload = await api.answer({ session_id: state.session_id, selected_reference: selectedReference, timestamp_ms: Date.now() });
      if (!active || currentToken !== token) return;
      const correct = payload.feedback === "correct";
      feedback.className = `gm20-module-feedback ${correct ? "is-correct" : "is-incorrect"}`;
      feedback.textContent = correct ? "Верно" : "Неверно";
      feedback.hidden = false;
      await delay(Math.max(650, TRIAL_SLOT_MS - (performance.now() - shownAt)));
      if (!active || currentToken !== token) return;
      if (!payload.finished) return renderTrial(payload);
      feedback.hidden = true;
      showOnly(result);
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Все карточки распределены.";
      const accuracy = Math.round(Number(payload.metrics?.u01_correct_action_rate || 0) * 100);
      q("[data-result-text]").textContent = `Правильных ответов: ${accuracy}%.`;
    } catch (error) {
      feedback.hidden = true;
      card.classList.remove("is-selected");
      references.querySelectorAll("button").forEach((button) => { button.disabled = false; });
      accepting = true;
      instruction.textContent = `Не удалось сохранить ответ: ${error.message}`;
    }
  }

  async function begin() {
    token += 1;
    accepting = false;
    start.disabled = true;
    restart.disabled = true;
    feedback.hidden = true;
    showOnly(play);
    play.hidden = true;
    progress.textContent = "Подготовка";
    instruction.textContent = "Подготавливаю карточки…";
    try {
      renderTrial(await api.start());
    } catch (error) {
      showOnly(complete);
      instruction.textContent = `Не удалось начать игру: ${error.message}`;
      start.disabled = false;
      restart.disabled = false;
    }
  }

  q("[data-start-training]").onclick = beginTraining;
  q("[data-repeat]").onclick = beginTraining;
  start.onclick = begin;
  restart.onclick = begin;
  q("[data-close]").onclick = () => { active = false; accepting = false; token += 1; close(); };

  const style = document.createElement("style");
  style.textContent = `
    .gm20-module{position:relative;display:grid;place-items:center;overflow:hidden;padding:clamp(9px,1.5vh,18px)}
    .gm20-module.is-instruction-stage{align-items:start;overflow-y:auto}.gm20-tutorial,.gm20-training,.gm20-complete{width:min(760px,94%);text-align:center}.gm20-tutorial[hidden],.gm20-training[hidden],.gm20-complete[hidden]{display:none}
    .gm20-tutorial h3,.gm20-training h3,.gm20-complete h3{margin:0 0 14px;color:#17212b}.gm20-tutorial ol{width:min(650px,92%);margin:0 auto 18px;padding-left:24px;text-align:left;color:#617180;line-height:1.55}
    .gm20-demo-placeholder{min-height:clamp(120px,22vh,210px);margin:0 auto 18px;display:grid;place-content:center;gap:8px;border:2px dashed #bdd2dc;border-radius:18px;background:#edf4f6;color:#607482}.gm20-demo-placeholder span{font-size:11px;letter-spacing:.14em;color:#168ba8}
    .gm20-secondary-btn{border-color:#75838d!important;background:#e7edf0!important;color:#17212b!important}.gm20-complete-actions{display:flex;flex-wrap:wrap;justify-content:center;gap:14px;margin-top:22px}.gm20-training>p{margin:0 0 10px;color:#617180}.gm20-training-feedback{min-height:25px;margin:8px 0 0!important;font-weight:700}.gm20-training-feedback.is-correct{color:#16875c}.gm20-training-feedback.is-incorrect{color:#c63d4b}
    .gm20-module-play{width:min(650px,58vh,96%);display:grid;justify-items:center;gap:clamp(12px,2vh,20px)}.gm20-module-play[hidden]{display:none}.gm20-module-reference-wrap,.gm20-module-stimulus-wrap{width:100%;text-align:center}.gm20-module-reference-wrap>p,.gm20-module-stimulus-wrap>p{margin:0 0 9px;color:#667784;font-size:11px;letter-spacing:.13em}
    .gm20-module-references{width:min(590px,100%);margin:auto;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:clamp(10px,1.6vh,16px)}.gm20-module-card{width:100%;min-width:0;aspect-ratio:1.7;display:grid;place-items:center;border:2px solid #d2dee4;border-radius:clamp(12px,1.5vw,19px);background:#fff;padding:clamp(8px,1.5vh,16px);overflow:hidden;color:#17212b}.gm20-module-references .gm20-module-card.count-1,.gm20-module-references .gm20-module-card.count-4{aspect-ratio:1}
    .gm20-module-reference{cursor:pointer;transition:border-color 120ms ease,box-shadow 120ms ease,background 120ms ease}.gm20-module-reference:hover:not(:disabled),.gm20-module-reference:focus-visible{border-color:#36b7d7;box-shadow:0 0 0 4px rgba(54,183,215,.14)}.gm20-module-reference.is-selected{border-color:#168ba8;background:#e8f8fc}.gm20-module-reference.is-correct{border-color:#16875c;background:#e6f6ef}.gm20-module-reference.is-incorrect{border-color:#c63d4b;background:#fbeaec}.gm20-module-reference:disabled{cursor:default}
    .gm20-module-stimulus{width:clamp(145px,18vh,190px);margin:auto}.gm20-module-symbols{width:100%;height:100%;min-width:0;min-height:0;display:grid;place-items:center;gap:4px;overflow:hidden}.gm20-module-symbols.count-1{grid-template:1fr/1fr}.gm20-module-symbols.count-2{grid-template:1fr/repeat(2,1fr)}.gm20-module-symbols.count-3{grid-template:1fr/repeat(3,1fr)}.gm20-module-symbols.count-4{grid-template:repeat(2,1fr)/repeat(2,1fr)}.gm20-module-symbols svg{width:78%;height:78%;min-width:0;min-height:0;max-width:100%;max-height:100%}.gm20-module-symbols .is-red{fill:#d83a48}.gm20-module-symbols .is-green{fill:#29a46f}.gm20-module-symbols .is-blue{fill:#327bd6}.gm20-module-symbols .is-yellow{fill:#e3ac24}
    .gm20-module-feedback{position:absolute;inset:0;z-index:2;display:grid;place-items:center;border-radius:inherit;background:rgba(244,247,248,.94);font-size:clamp(36px,6vw,68px);font-weight:800}.gm20-module-feedback[hidden]{display:none}.gm20-module-feedback.is-correct{color:#16875c}.gm20-module-feedback.is-incorrect{color:#c63d4b}
    @media(max-height:700px){.gm20-demo-placeholder{min-height:90px}.gm20-module-play{width:min(520px,55vh,96%);gap:7px}.gm20-module-references{width:min(470px,100%);gap:7px}.gm20-module-card{padding:5px}.gm20-module-stimulus{width:min(115px,15vh)}.gm20-module-reference-wrap>p,.gm20-module-stimulus-wrap>p{margin-bottom:4px}}
  `;
  container.append(style);
  return () => { active = false; accepting = false; token += 1; };
}

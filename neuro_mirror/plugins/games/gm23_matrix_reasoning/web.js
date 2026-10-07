const TRIAL_SLOT_MS = 6000;
const SYMBOLS = { star: "★", triangle: "▲", heart: "♥" };
const TRAINING_MATRIX = [
  { symbol: "star", style: "filled" }, { symbol: "triangle", style: "filled" }, { symbol: "heart", style: "filled" },
  { symbol: "triangle", style: "filled" }, { symbol: "heart", style: "filled" }, { symbol: "star", style: "filled" },
  { symbol: "heart", style: "filled" }, { symbol: "star", style: "filled" }, null,
];
const TRAINING_OPTIONS = [
  { id: "triangle", symbol: "triangle", style: "filled", correct: true },
  { id: "star", symbol: "star", style: "filled" },
  { id: "heart", symbol: "heart", style: "filled" },
  { id: "outline", symbol: "triangle", style: "outline" },
];

export function mount({ container, definition, api, close }) {
  const symbolBySet = { "звезда": "star", "треугольник": "triangle", "сердце": "heart" };
  const trainingTarget = symbolBySet[String(definition.selected_stimulus_set || "").toLowerCase()] || "triangle";
  const remapTrainingSymbol = (symbol) => symbol === "triangle" ? trainingTarget : symbol === trainingTarget ? "triangle" : symbol;
  const trainingMatrixData = TRAINING_MATRIX.map((item) => item ? { ...item, symbol: remapTrainingSymbol(item.symbol) } : null);
  const trainingOptionsData = TRAINING_OPTIONS.map((item) => ({ ...item, symbol: remapTrainingSymbol(item.symbol) }));
  container.innerHTML = `
    <header class="game-header-new"><div><p class="game-kicker-new mono">АБСТРАКЦИЯ</p><h2>${definition.title}</h2><p data-instruction>Определите закономерность и выберите недостающий элемент.</p></div><div class="game-progress-new" data-progress>Инструкция</div></header>
    <main class="game-stage-new gm23-module is-instruction-stage">
      <section class="gm23-tutorial" data-tutorial><h3>Как выполнять задание</h3><ol><li>Рассмотрите фигуры во всех строках и столбцах.</li><li>Определите, в каком порядке меняются фигуры и их вид.</li><li>Найдите элемент, который должен стоять вместо знака вопроса.</li><li>Нажмите на подходящий вариант ответа.</li></ol><div class="gm23-demo-placeholder"><span class="mono">ПРИМЕР ВЫПОЛНЕНИЯ</span><strong>Видеоинструкция появится здесь</strong></div><button type="button" class="icon-btn primary-btn" data-start-training><span>Перейти к тренировке</span></button></section>
      <section class="gm23-training" data-training hidden><h3>Тренировочный пример</h3><p>Продолжите закономерность и выберите недостающую фигуру.</p><div class="gm23-module-play"><section class="gm23-module-section"><p class="mono">ЗАКОНОМЕРНОСТЬ</p><div class="gm23-module-matrix" data-training-matrix></div></section><section class="gm23-module-section"><p class="mono">ВЫБЕРИТЕ ОТВЕТ</p><div class="gm23-module-options" data-training-options></div></section></div><p class="gm23-training-status" data-training-status aria-live="polite"></p></section>
      <section class="gm23-complete" data-complete hidden><h3>Обучение завершено</h3><p>Вы правильно продолжили закономерность. Закончить обучение и начать игру?</p><div class="gm23-complete-actions"><button type="button" class="icon-btn gm23-secondary-btn" data-repeat><span>Повторить обучение</span></button><button type="button" class="icon-btn primary-btn" data-start><span>Да, начать игру</span></button></div></section>
      <div class="gm23-module-play" data-play hidden><section class="gm23-module-section"><p class="mono">ЗАКОНОМЕРНОСТЬ</p><div class="gm23-module-matrix" data-matrix></div></section><section class="gm23-module-section"><p class="mono">ВЫБЕРИТЕ ОТВЕТ</p><div class="gm23-module-options" data-options></div></section></div>
      <div class="game-result-new" data-result hidden><h3>Игра завершена</h3><p data-result-text></p><button type="button" class="icon-btn primary-btn" data-restart><span>Ещё раз</span></button></div>
    </main><footer class="game-actions-new"><button type="button" class="icon-btn" data-close><span>К выбору игр</span></button></footer>`;

  const q = (selector) => container.querySelector(selector);
  const stage = q(".gm23-module");
  const instruction = q("[data-instruction]");
  const progress = q("[data-progress]");
  const tutorial = q("[data-tutorial]");
  const training = q("[data-training]");
  const complete = q("[data-complete]");
  const play = q("[data-play]");
  const result = q("[data-result]");
  const trainingMatrix = q("[data-training-matrix]");
  const trainingOptions = q("[data-training-options]");
  const trainingStatus = q("[data-training-status]");
  const matrix = q("[data-matrix]");
  const options = q("[data-options]");
  const start = q("[data-start]");
  const restart = q("[data-restart]");
  const sections = [tutorial, training, complete, play, result];
  let state = null;
  let accepting = false;
  let shownAt = 0;
  let active = true;
  let token = 0;
  let trainingBusy = false;
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function showOnly(section) {
    sections.forEach((item) => { item.hidden = item !== section; });
    stage.classList.toggle("is-instruction-stage", section === tutorial);
  }

  function createElement(item) {
    const element = document.createElement("span");
    if (!item) {
      element.textContent = "?";
      element.className = "gm23-module-symbol is-missing";
    } else {
      element.textContent = SYMBOLS[item.symbol] || "?";
      element.className = `gm23-module-symbol is-${item.style}`;
    }
    return element;
  }

  function createOption(item, index, onSelect) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gm23-module-option";
    button.setAttribute("aria-label", `Вариант ${index + 1}`);
    button.append(createElement(item));
    button.onclick = () => onSelect(item, button);
    return button;
  }

  function beginTraining() {
    trainingBusy = false;
    trainingStatus.textContent = "";
    trainingStatus.className = "gm23-training-status";
    trainingMatrix.replaceChildren(...trainingMatrixData.map(createElement));
    trainingOptions.replaceChildren(...trainingOptionsData.map((item, index) => createOption(item, index, answerTraining)));
    progress.textContent = "2. Тренировочный пример";
    instruction.textContent = "Выберите фигуру, которая должна стоять вместо знака вопроса.";
    showOnly(training);
  }

  function answerTraining(item, button) {
    if (trainingBusy) return;
    if (!item.correct) {
      button.classList.add("is-wrong");
      trainingStatus.textContent = "Неверно. Ещё раз проверьте порядок фигур в строках.";
      trainingStatus.className = "gm23-training-status is-wrong";
      window.setTimeout(() => button.classList.remove("is-wrong"), 450);
      return;
    }
    trainingBusy = true;
    trainingOptions.querySelectorAll("button").forEach((option) => { option.disabled = true; });
    button.classList.add("is-correct");
    trainingStatus.textContent = "Верно";
    trainingStatus.className = "gm23-training-status is-correct";
    window.setTimeout(() => {
      if (!active) return;
      progress.textContent = "Обучение завершено";
      instruction.textContent = "Тренировочная закономерность продолжена правильно.";
      showOnly(complete);
    }, 650);
  }

  function renderTrial(payload) {
    state = payload;
    accepting = true;
    shownAt = performance.now();
    matrix.replaceChildren(...payload.matrix.map(createElement));
    options.replaceChildren(...payload.options.map((item, index) => createOption(item, index, (_choice, button) => answer(item.id, button))));
    progress.textContent = `Матрица ${payload.trial} из ${payload.trial_count}`;
    instruction.textContent = "Определите закономерность и выберите недостающий элемент.";
    showOnly(play);
  }

  async function answer(selectedId, button) {
    if (!accepting || !state) return;
    accepting = false;
    const currentToken = token;
    button.classList.add("is-selected");
    options.querySelectorAll("button").forEach((item) => { item.disabled = true; });
    const elapsed = performance.now() - shownAt;
    if (elapsed < TRIAL_SLOT_MS) await delay(TRIAL_SLOT_MS - elapsed);
    if (!active || currentToken !== token) return;
    try {
      const payload = await api.answer({ session_id: state.session_id, selected_id: selectedId, timestamp_ms: Date.now() });
      if (!active || currentToken !== token) return;
      if (!payload.finished) return renderTrial(payload);
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Все матрицы завершены.";
      const accuracy = Math.round(Number(payload.metrics?.u01_correct_action_rate || 0) * 100);
      q("[data-result-text]").textContent = `Правильных ответов: ${accuracy}%.`;
      showOnly(result);
    } catch (error) {
      button.classList.remove("is-selected");
      options.querySelectorAll("button").forEach((item) => { item.disabled = false; });
      accepting = true;
      instruction.textContent = `Не удалось сохранить ответ: ${error.message}`;
    }
  }

  async function beginGame() {
    token += 1;
    accepting = false;
    start.disabled = true;
    restart.disabled = true;
    progress.textContent = "Подготовка";
    instruction.textContent = "Подготавливаю матрицы…";
    showOnly(play);
    play.hidden = true;
    try { renderTrial(await api.start()); }
    catch (error) { instruction.textContent = `Не удалось начать игру: ${error.message}`; start.disabled = false; restart.disabled = false; showOnly(complete); }
  }

  q("[data-start-training]").onclick = beginTraining;
  q("[data-repeat]").onclick = beginTraining;
  start.onclick = beginGame;
  restart.onclick = beginGame;
  q("[data-close]").onclick = () => { active = false; accepting = false; token += 1; close(); };

  const style = document.createElement("style");
  style.textContent = `
    .gm23-module{display:grid;place-items:center;overflow:hidden;text-align:center;padding:clamp(10px,2vh,22px)}.gm23-module.is-instruction-stage{align-items:start;overflow-y:auto}.gm23-tutorial,.gm23-training,.gm23-complete{width:min(820px,96%)}.gm23-tutorial[hidden],.gm23-training[hidden],.gm23-complete[hidden]{display:none}.gm23-tutorial h3,.gm23-training h3,.gm23-complete h3{margin:0 0 14px;color:#17212b}.gm23-tutorial ol{width:min(680px,92%);margin:0 auto 18px;padding-left:24px;text-align:left;color:#617180;line-height:1.55}.gm23-demo-placeholder{min-height:clamp(120px,20vh,190px);margin:0 auto 18px;display:grid;place-content:center;gap:8px;border:2px dashed #bdd2dc;border-radius:18px;background:#edf4f6;color:#607482}.gm23-demo-placeholder span{font-size:11px;letter-spacing:.14em;color:#168ba8}.gm23-complete-actions{display:flex;flex-wrap:wrap;justify-content:center;gap:14px;margin-top:22px}.gm23-secondary-btn{border-color:#75838d!important;background:#e7edf0!important;color:#17212b!important}.gm23-training-status{min-height:1.5em;margin:10px 0 0;font-weight:700}.gm23-training-status.is-correct{color:#16835c}.gm23-training-status.is-wrong{color:#b34c54}
    .gm23-module-play{width:min(790px,96%);display:grid;grid-template-columns:minmax(290px,1.55fr) minmax(190px,1fr);gap:clamp(20px,5vw,55px);align-items:center}.gm23-module-play[hidden]{display:none}.gm23-module-section>p{margin:0 0 12px;color:#667784;font-size:11px;letter-spacing:.14em}.gm23-module-matrix{width:min(430px,48vh,100%);aspect-ratio:1;display:grid;grid-template-columns:repeat(3,1fr);gap:clamp(6px,1vh,10px)}.gm23-module-matrix>span,.gm23-module-option{aspect-ratio:1;display:grid;place-items:center;border:2px solid #d4dfe4;border-radius:clamp(11px,1.5vw,16px);background:#fff}.gm23-module-symbol{color:#327bd6;font-size:clamp(31px,6vh,64px);line-height:1}.gm23-module-symbol.is-outline{color:transparent;-webkit-text-stroke:2px #327bd6}.gm23-module-symbol.is-missing{color:#82939e;-webkit-text-stroke:0}.gm23-module-options{display:grid;grid-template-columns:repeat(2,1fr);gap:clamp(8px,1.4vh,13px)}.gm23-module-option{color:#17212b;cursor:pointer}.gm23-module-option:hover:not(:disabled),.gm23-module-option:focus-visible{border-color:#36b7d7;box-shadow:0 0 0 4px rgba(54,183,215,.14)}.gm23-module-option.is-selected{border-color:#168ba8;background:#e8f8fc}.gm23-module-option.is-correct{border-color:#16835c;background:#e6f6ef}.gm23-module-option.is-wrong{border-color:#b34c54;background:#fbeaec}.gm23-module-option:disabled{cursor:default}
    @media(max-height:700px){.gm23-demo-placeholder{min-height:80px}.gm23-module-play{width:min(680px,94%);gap:20px}.gm23-module-matrix{width:min(350px,43vh)}.gm23-module-symbol{font-size:clamp(28px,5vh,52px)}}@media(max-width:650px){.gm23-module-play{grid-template-columns:1.45fr 1fr;gap:10px}.gm23-module-matrix{width:min(330px,42vh,100%)}.gm23-module-options{gap:6px}}
  `;
  container.append(style);
  return () => { active = false; accepting = false; token += 1; };
}

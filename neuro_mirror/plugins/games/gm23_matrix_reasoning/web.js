const TRIAL_SLOT_MS = 6000;
const SYMBOLS = { star: "★", triangle: "▲", heart: "♥" };

export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">АБСТРАКЦИЯ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Определите закономерность и выберите недостающий элемент.</p>
      </div>
      <div class="game-progress-new" data-progress>Матрица 1 из 10</div>
    </header>
    <main class="game-stage-new gm23-module">
      <div class="game-intro-new" data-intro>
        <p>Рассмотрите расположение фигур в матрице 3×3. Выберите один из четырёх элементов, который должен находиться вместо знака вопроса.</p>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <div class="gm23-module-play" data-play hidden>
        <section class="gm23-module-section">
          <p class="mono">ЗАКОНОМЕРНОСТЬ</p>
          <div class="gm23-module-matrix" data-matrix></div>
        </section>
        <section class="gm23-module-section">
          <p class="mono">ВЫБЕРИТЕ ОТВЕТ</p>
          <div class="gm23-module-options" data-options></div>
        </section>
      </div>
      <div class="game-result-new" data-result hidden>
        <h3>Игра завершена</h3>
        <p data-result-text></p>
        <button type="button" class="icon-btn primary-btn" data-restart><span>Ещё раз</span></button>
      </div>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const instruction = container.querySelector("[data-instruction]");
  const progress = container.querySelector("[data-progress]");
  const intro = container.querySelector("[data-intro]");
  const play = container.querySelector("[data-play]");
  const matrix = container.querySelector("[data-matrix]");
  const options = container.querySelector("[data-options]");
  const result = container.querySelector("[data-result]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const restart = container.querySelector("[data-restart]");
  let state = null;
  let accepting = false;
  let shownAt = 0;
  let active = true;
  let token = 0;

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

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

  function renderTrial(payload) {
    state = payload;
    accepting = true;
    shownAt = performance.now();
    matrix.replaceChildren(...payload.matrix.map(createElement));
    options.replaceChildren();
    payload.options.forEach((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "gm23-module-option";
      button.setAttribute("aria-label", `Вариант ${index + 1}`);
      button.append(createElement(item));
      button.onclick = () => answer(item.id, button);
      options.append(button);
    });
    progress.textContent = `Матрица ${payload.trial} из ${payload.trial_count}`;
    instruction.textContent = "Определите закономерность и выберите недостающий элемент.";
    intro.hidden = true;
    result.hidden = true;
    play.hidden = false;
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
      const payload = await api.answer({
        session_id: state.session_id,
        selected_id: selectedId,
        timestamp_ms: Date.now(),
      });
      if (!active || currentToken !== token) return;
      if (!payload.finished) {
        renderTrial(payload);
        return;
      }
      play.hidden = true;
      result.hidden = false;
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Все матрицы завершены.";
      const accuracy = Math.round(Number(payload.metrics?.u01_correct_action_rate || 0) * 100);
      resultText.textContent = `Правильных ответов: ${accuracy}%.`;
    } catch (error) {
      button.classList.remove("is-selected");
      options.querySelectorAll("button").forEach((item) => { item.disabled = false; });
      accepting = true;
      instruction.textContent = `Не удалось сохранить ответ: ${error.message}`;
    }
  }

  async function begin() {
    token += 1;
    accepting = false;
    start.disabled = true;
    restart.disabled = true;
    play.hidden = true;
    result.hidden = true;
    instruction.textContent = "Подготавливаю матрицы…";
    try {
      renderTrial(await api.start());
    } catch (error) {
      instruction.textContent = `Не удалось начать игру: ${error.message}`;
      start.disabled = false;
      restart.disabled = false;
    }
  }

  start.onclick = begin;
  restart.onclick = begin;
  container.querySelector("[data-close]").onclick = () => {
    active = false;
    accepting = false;
    token += 1;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm23-module { display: grid; place-items: center; overflow: hidden; text-align: center; }
    .gm23-module-play { width: min(790px, 96%); display: grid; grid-template-columns: minmax(290px, 1.55fr) minmax(190px, 1fr); gap: clamp(20px, 5vw, 55px); align-items: center; }
    .gm23-module-play[hidden] { display: none; }
    .gm23-module-section > p { margin: 0 0 12px; color: #667784; font-size: 11px; letter-spacing: .14em; }
    .gm23-module-matrix { width: min(430px, 48vh, 100%); aspect-ratio: 1; display: grid; grid-template-columns: repeat(3, 1fr); gap: clamp(6px, 1vh, 10px); }
    .gm23-module-matrix > span, .gm23-module-option { aspect-ratio: 1; display: grid; place-items: center; border: 2px solid #d4dfe4; border-radius: clamp(11px, 1.5vw, 16px); background: #fff; }
    .gm23-module-symbol { color: #327bd6; font-size: clamp(31px, 6vh, 64px); line-height: 1; }
    .gm23-module-symbol.is-outline { color: transparent; -webkit-text-stroke: 2px #327bd6; }
    .gm23-module-symbol.is-missing { color: #82939e; -webkit-text-stroke: 0; }
    .gm23-module-options { display: grid; grid-template-columns: repeat(2, 1fr); gap: clamp(8px, 1.4vh, 13px); }
    .gm23-module-option { color: #17212b; cursor: pointer; }
    .gm23-module-option:hover:not(:disabled), .gm23-module-option:focus-visible { border-color: #36b7d7; box-shadow: 0 0 0 4px rgba(54,183,215,.14); }
    .gm23-module-option.is-selected { border-color: #168ba8; background: #e8f8fc; }
    .gm23-module-option:disabled { cursor: default; }
    @media (max-height: 700px) {
      .gm23-module-play { width: min(680px, 94%); gap: 20px; }
      .gm23-module-matrix { width: min(350px, 43vh); }
      .gm23-module-symbol { font-size: clamp(28px, 5vh, 52px); }
    }
    @media (max-width: 650px) {
      .gm23-module-play { grid-template-columns: 1.45fr 1fr; gap: 10px; }
      .gm23-module-matrix { width: min(330px, 42vh, 100%); }
      .gm23-module-options { gap: 6px; }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    accepting = false;
    token += 1;
  };
}

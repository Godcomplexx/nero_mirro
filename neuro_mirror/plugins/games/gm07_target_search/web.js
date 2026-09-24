export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">ВНИМАНИЕ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Запомните цель, которую нужно будет найти.</p>
      </div>
      <div class="game-progress-new" data-progress>Проба 1 из 10</div>
    </header>
    <main class="game-stage-new gm07-module">
      <div class="game-intro-new" data-intro>
        <p>Ищите красную букву «Т» без поворота.</p>
        <div class="gm07-module-target" aria-label="Образец цели">Т</div>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <div class="gm07-module-play" data-play hidden>
        <div class="gm07-module-grid" data-grid></div>
        <button type="button" class="icon-btn gm07-module-absent" data-absent><span>Цели нет</span></button>
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
  const grid = container.querySelector("[data-grid]");
  const absent = container.querySelector("[data-absent]");
  const result = container.querySelector("[data-result]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const restart = container.querySelector("[data-restart]");
  let state = null;
  let acceptingInput = false;
  let renderToken = 0;
  let active = true;

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function renderStimuli(stimuli) {
    grid.replaceChildren();
    stimuli.forEach((stimulus) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `gm07-module-stimulus is-${stimulus.color}`;
      button.setAttribute(
        "aria-label",
        `${stimulus.color === "red" ? "Красная" : "Чёрная"} буква Т`,
      );
      const symbol = document.createElement("span");
      symbol.textContent = stimulus.symbol;
      symbol.style.transform = `rotate(${Number(stimulus.rotation) || 0}deg)`;
      button.append(symbol);
      button.onclick = () => answer(stimulus.id);
      grid.append(button);
    });
  }

  async function renderTrial(payload) {
    const token = ++renderToken;
    state = payload;
    acceptingInput = false;
    progress.textContent = `Проба ${payload.trial} из ${payload.trial_count}`;
    instruction.textContent = "Приготовьтесь…";
    intro.hidden = true;
    result.hidden = true;
    play.hidden = true;
    await delay(400);
    if (!active || token !== renderToken) return;
    renderStimuli(payload.stimuli || []);
    play.hidden = false;
    instruction.textContent = "Нажмите на цель или выберите «Цели нет».";
    acceptingInput = true;
  }

  async function begin() {
    renderToken += 1;
    acceptingInput = false;
    start.disabled = true;
    restart.disabled = true;
    instruction.textContent = "Подготавливаю задание…";
    try {
      await renderTrial(await api.start());
    } catch (error) {
      instruction.textContent = `Не удалось начать игру: ${error.message}`;
      start.disabled = false;
      restart.disabled = false;
    }
  }

  async function answer(selectedId) {
    if (!acceptingInput || !state) return;
    acceptingInput = false;
    [...grid.children].forEach((item) => { item.disabled = true; });
    absent.disabled = true;
    try {
      const payload = await api.answer({
        session_id: state.session_id,
        selected_id: selectedId,
        timestamp_ms: Date.now(),
      });
      absent.disabled = false;
      if (!active) return;
      if (!payload.finished) {
        await renderTrial(payload);
        return;
      }
      play.hidden = true;
      result.hidden = false;
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Все 10 проб завершены.";
      const accuracy = Math.round(Number(payload.metrics?.u01_correct_action_rate || 0) * 100);
      resultText.textContent = `Правильных ответов: ${accuracy}%.`;
    } catch (error) {
      instruction.textContent = `Не удалось сохранить ответ: ${error.message}`;
      [...grid.children].forEach((item) => { item.disabled = false; });
      absent.disabled = false;
      acceptingInput = true;
    }
  }

  absent.onclick = () => answer(null);
  start.onclick = begin;
  restart.onclick = begin;
  container.querySelector("[data-close]").onclick = () => {
    active = false;
    renderToken += 1;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm07-module { text-align: center; }
    .gm07-module-target {
      display: grid;
      place-items: center;
      width: 120px;
      aspect-ratio: 1;
      margin: 18px auto 24px;
      border: 2px solid #d4dfe4;
      border-radius: 20px;
      background: #fff;
      color: #d92f42;
      font-size: 76px;
      font-weight: 800;
    }
    .gm07-module-play { width: min(900px, 94%); }
    .gm07-module-play[hidden] { display: none; }
    .gm07-module-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: clamp(8px, 1.5vw, 16px);
      margin-bottom: clamp(14px, 2vh, 24px);
    }
    .gm07-module-stimulus {
      display: grid;
      place-items: center;
      aspect-ratio: 1;
      min-width: 0;
      border: 2px solid #cfdae0;
      border-radius: 18px;
      background: #fff;
      transition: border-color .12s, box-shadow .12s;
    }
    .gm07-module-stimulus:hover { border-color: #69b8c9; box-shadow: 0 5px 15px rgba(20, 35, 45, .1); }
    .gm07-module-stimulus span {
      display: block;
      font-size: clamp(38px, 8vh, 72px);
      font-weight: 800;
      line-height: 1;
      pointer-events: none;
    }
    .gm07-module-stimulus.is-red { color: #d92f42; }
    .gm07-module-stimulus.is-black { color: #17212b; }
    .gm07-module-absent { margin: auto; }
    @media (max-width: 700px) {
      .gm07-module-grid { gap: 6px; }
      .gm07-module-stimulus { border-radius: 10px; }
      .gm07-module-stimulus span { font-size: clamp(26px, 9vw, 48px); }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    renderToken += 1;
    acceptingInput = false;
  };
}

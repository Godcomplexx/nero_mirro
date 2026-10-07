export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">ПАМЯТЬ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Запомните порядок подсвечивания клеток и повторите его.</p>
      </div>
      <div class="game-progress-new" data-round>Обучение</div>
    </header>
    <main class="game-stage-new gm02-module is-instruction-stage" data-stage>
      <div class="game-intro-new" data-intro>
        <h3>Как выполнять задание</h3>
        <ol class="gm02-training-steps">
          <li>Несколько клеток по очереди подсветятся.</li>
          <li>Запомните клетки и порядок их подсвечивания.</li>
          <li>Когда появится надпись «Повторите последовательность», нажмите эти клетки в том же порядке.</li>
        </ol>
        <p class="gm02-training-note">Сначала выполним тренировочный пример. Он не учитывается в результате игры.</p>
        <p class="gm02-example-title">Посмотрите пример</p>
        <img
          class="gm02-training-gif"
          src="/game-assets/tutorials/gm02_sequence.gif"
          alt="Пример выполнения задания: клетки подсвечиваются, затем их нажимают в том же порядке"
        >
        <button type="button" class="icon-btn primary-btn" data-start><span>Перейти к тренировке</span></button>
      </div>
      <div class="gm02-module-grid" data-grid hidden aria-label="Игровое поле"></div>
      <div class="game-intro-new gm02-training-complete" data-training-complete hidden>
        <h3>Обучение завершено</h3>
        <p>Вы правильно повторили последовательность. Закончить обучение и начать игру?</p>
        <div class="gm02-training-actions">
          <button type="button" class="icon-btn gm02-training-repeat" data-repeat-training><span>Повторить обучение</span></button>
          <button type="button" class="icon-btn primary-btn" data-confirm-start><span>Да, начать игру</span></button>
        </div>
      </div>
      <div class="game-result-new" data-result hidden>
        <h3 data-result-title>Игра завершена</h3>
        <p data-result-text></p>
        <button type="button" class="icon-btn primary-btn" data-restart><span>Попробовать ещё раз</span></button>
      </div>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const instruction = container.querySelector("[data-instruction]");
  const round = container.querySelector("[data-round]");
  const stage = container.querySelector("[data-stage]");
  const intro = container.querySelector("[data-intro]");
  const grid = container.querySelector("[data-grid]");
  const trainingComplete = container.querySelector("[data-training-complete]");
  const result = container.querySelector("[data-result]");
  const resultTitle = container.querySelector("[data-result-title]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const repeatTraining = container.querySelector("[data-repeat-training]");
  const confirmStart = container.querySelector("[data-confirm-start]");
  const restart = container.querySelector("[data-restart]");
  let state = null;
  let clicks = [];
  let acceptingInput = false;
  let playbackToken = 0;
  let active = true;
  let training = false;
  const trainingSequence = [0, 4, 8];

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function buildGrid(size) {
    grid.style.gridTemplateColumns = `repeat(${size}, 1fr)`;
    grid.replaceChildren();
    for (let cell = 0; cell < size * size; cell += 1) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "gm02-module-cell";
      button.setAttribute("aria-label", `Клетка ${cell + 1}`);
      button.onclick = () => handleCell(cell, button);
      grid.append(button);
    }
  }

  async function playSequence(sequence) {
    const token = ++playbackToken;
    acceptingInput = false;
    clicks = [];
    instruction.textContent = "Смотрите и запоминайте…";
    await delay(500);
    for (const cell of sequence) {
      if (!active || token !== playbackToken) return;
      const node = grid.children[cell];
      node.classList.add("is-active");
      await delay(430);
      node.classList.remove("is-active");
      await delay(180);
    }
    if (!active || token !== playbackToken) return;
    acceptingInput = true;
    instruction.textContent = "Теперь повторите последовательность.";
  }

  function renderRound(payload) {
    stage.classList.remove("is-instruction-stage");
    training = false;
    state = payload;
    clicks = [];
    round.textContent = `Раунд ${payload.round} из ${payload.max_rounds}`;
    buildGrid(payload.grid_size);
    intro.hidden = true;
    trainingComplete.hidden = true;
    result.hidden = true;
    grid.hidden = false;
    playSequence(payload.sequence);
  }

  async function beginTraining() {
    playbackToken += 1;
    stage.classList.remove("is-instruction-stage");
    training = true;
    state = null;
    clicks = [];
    acceptingInput = false;
    intro.hidden = true;
    trainingComplete.hidden = true;
    result.hidden = true;
    grid.hidden = false;
    round.textContent = "Тренировочный пример";
    buildGrid(3);
    await playSequence(trainingSequence);
  }

  async function begin() {
    playbackToken += 1;
    acceptingInput = false;
    confirmStart.disabled = true;
    restart.disabled = true;
    instruction.textContent = "Подготавливаю задание…";
    try {
      renderRound(await api.start());
    } catch (error) {
      instruction.textContent = `Не удалось начать игру: ${error.message}`;
      confirmStart.disabled = false;
      restart.disabled = false;
    }
  }

  async function submitAnswer() {
    acceptingInput = false;
    const payload = await api.answer({ session_id: state.session_id, clicks });
    if (!active) return;
    if (!payload.finished) {
      await delay(450);
      renderRound(payload);
      return;
    }
    grid.hidden = true;
    result.hidden = false;
    restart.disabled = false;
    const completed = payload.reason === "level_complete";
    const length = Number(payload.metrics?.m01_max_sequence_length || 0);
    resultTitle.textContent = completed ? "Уровень пройден" : "Последовательность прервана";
    resultText.textContent = completed
      ? "Вы успешно прошли все 10 раундов."
      : `Максимальная длина последовательности: ${length}.`;
    instruction.textContent = completed
      ? "Задание выполнено."
      : "Первый неверный выбор завершает попытку.";
  }

  async function handleCell(cell, node) {
    if (!acceptingInput) return;
    const position = clicks.length;
    clicks.push({ cell, timestamp_ms: Date.now() });
    node.classList.add("is-pressed");
    setTimeout(() => node.classList.remove("is-pressed"), 160);

    if (training) {
      if (cell !== trainingSequence[position]) {
        acceptingInput = false;
        instruction.textContent = "Порядок неверный. Посмотрите пример ещё раз.";
        await delay(700);
        if (active) await playSequence(trainingSequence);
        return;
      }
      if (clicks.length === trainingSequence.length) {
        acceptingInput = false;
        grid.hidden = true;
        trainingComplete.hidden = false;
        instruction.textContent = "Тренировочный пример выполнен правильно.";
      }
      return;
    }

    if (cell !== state.sequence[position] || clicks.length === state.sequence.length) {
      try {
        await submitAnswer();
      } catch (error) {
        instruction.textContent = `Не удалось проверить ответ: ${error.message}`;
        acceptingInput = true;
      }
    }
  }

  start.onclick = beginTraining;
  repeatTraining.onclick = beginTraining;
  confirmStart.onclick = begin;
  restart.onclick = begin;
  container.querySelector("[data-close]").onclick = () => {
    active = false;
    playbackToken += 1;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm02-module { text-align: center; }
    .gm02-module.is-instruction-stage { align-items: start; padding-top: clamp(18px, 3vh, 38px); }
    .gm02-module .game-intro-new { width: min(760px, 100%); }
    .gm02-training-steps {
      max-width: 650px;
      margin: 0 auto 20px;
      padding-left: 28px;
      color: #52606d;
      text-align: left;
      font-size: clamp(16px, 2vw, 19px);
      line-height: 1.5;
    }
    .gm02-training-steps li + li { margin-top: 8px; }
    .gm02-training-note { margin-bottom: 12px !important; font-size: 15px !important; }
    .gm02-example-title {
      margin: 0 0 8px !important;
      color: #17212b !important;
      font-size: 16px !important;
      font-weight: 700;
    }
    .gm02-training-gif {
      display: block;
      width: auto;
      max-width: 100%;
      height: min(34vh, 330px);
      margin: 0 auto 14px;
      border: 1px solid #cbd8de;
      border-radius: 14px;
      object-fit: contain;
      background: #f4f7f8;
    }
    .gm02-training-actions { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }
    .gm02-training-repeat {
      border-color: #60727d;
      background: #ffffff;
      color: #17212b;
    }
    .gm02-training-repeat:hover {
      border-color: #168ba8;
      background: #e8f8fc;
      color: #17212b;
    }
    .gm02-training-complete[hidden] { display: none; }
    .gm02-module-grid {
      display: grid;
      width: min(58vh, 560px, 76vw);
      aspect-ratio: 1;
      gap: clamp(8px, 1.5vh, 16px);
    }
    .gm02-module-grid[hidden] { display: none; }
    .gm02-module-cell {
      min-width: 0;
      min-height: 0;
      border: 2px solid #b9ccd5;
      border-radius: clamp(12px, 2vh, 22px);
      background: #e5edf1;
      transition: background 100ms ease, border-color 100ms ease, box-shadow 100ms ease;
    }
    .gm02-module-cell:hover { border-color: #69b9ca; }
    .gm02-module-cell.is-active,
    .gm02-module-cell.is-pressed {
      border-color: transparent;
      background: linear-gradient(135deg, #70d5ed, #9d83ff);
      box-shadow: 0 0 28px rgba(70, 181, 214, .45);
    }
    @media (max-height: 650px) {
      .gm02-module.is-instruction-stage { padding-top: 10px; }
      .gm02-training-steps { margin-bottom: 10px; font-size: 14px; line-height: 1.3; }
      .gm02-training-note { margin-bottom: 7px !important; }
      .gm02-training-gif { height: 24vh; margin-bottom: 8px; }
      .gm02-module-grid { width: min(50vh, 430px, 70vw); }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    playbackToken += 1;
    acceptingInput = false;
  };
}

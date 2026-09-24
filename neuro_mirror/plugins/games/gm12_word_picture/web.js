export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">РЕЧЬ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Посмотрите на картинку и выберите подходящее слово.</p>
      </div>
      <div class="game-progress-new" data-progress>Время: 1:00</div>
    </header>
    <main class="game-stage-new gm12-module">
      <div class="game-intro-new" data-intro>
        <p>В каждом задании будет показана одна картинка и четыре слова. Выберите слово, которое соответствует картинке.</p>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <div class="gm12-module-task" data-task hidden>
        <div class="gm12-module-picture"><img data-picture alt="Изображение для выбора слова"></div>
        <div class="gm12-module-options" data-options></div>
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
  const task = container.querySelector("[data-task]");
  const picture = container.querySelector("[data-picture]");
  const options = container.querySelector("[data-options]");
  const result = container.querySelector("[data-result]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const restart = container.querySelector("[data-restart]");
  let state = null;
  let accepting = false;
  let active = true;
  let token = 0;
  let deadline = 0;
  let timeoutId = null;
  let clockId = null;
  let requestInFlight = false;
  let timeExpired = false;

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function clearClock() {
    clearTimeout(timeoutId);
    clearInterval(clockId);
    timeoutId = null;
    clockId = null;
  }

  function updateProgress() {
    const remaining = Math.max(0, deadline - performance.now());
    const seconds = Math.ceil(remaining / 1000);
    const minutes = Math.floor(seconds / 60);
    const rest = seconds % 60;
    progress.textContent = `Задание ${state?.trial || 1} · время ${minutes}:${String(rest).padStart(2, "0")}`;
  }

  function startClock(durationMs) {
    clearClock();
    timeExpired = false;
    deadline = performance.now() + durationMs;
    updateProgress();
    clockId = setInterval(updateProgress, 250);
    timeoutId = setTimeout(() => {
      timeExpired = true;
      updateProgress();
      if (!requestInFlight) finishByTime();
    }, durationMs);
  }

  function renderTrial(payload) {
    state = payload;
    accepting = true;
    updateProgress();
    instruction.textContent = "Выберите слово, которое соответствует картинке.";
    picture.src = `/game-assets/objects/${encodeURIComponent(payload.picture)}`;
    picture.alt = `Картинка из категории «${payload.category}»`;
    options.replaceChildren();
    payload.choices.forEach((word) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "gm12-module-option";
      button.textContent = word;
      button.onclick = () => answer(word, button);
      options.append(button);
    });
    intro.hidden = true;
    result.hidden = true;
    task.hidden = false;
  }

  async function answer(selectedWord, button) {
    if (!accepting || !state) return;
    accepting = false;
    const currentToken = token;
    options.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
      button.classList.toggle("is-selected", button.textContent === selectedWord);
    });
    if (!active || currentToken !== token) return;
    requestInFlight = true;
    try {
      const payload = await api.answer({
        session_id: state.session_id,
        selected_word: selectedWord,
        timestamp_ms: Date.now(),
      });
      if (!active || currentToken !== token) return;
      const correct = payload.finished ? payload.correct : payload.previous_correct;
      button.classList.remove("is-selected");
      button.classList.add(correct ? "is-correct" : "is-incorrect");
      await delay(400);
      if (!active || currentToken !== token) return;
      requestInFlight = false;
      if (!payload.finished) {
        if (timeExpired) {
          state = payload;
          await finishByTime();
          return;
        }
        renderTrial(payload);
        return;
      }
      showResult(payload);
    } catch (error) {
      requestInFlight = false;
      instruction.textContent = `Не удалось сохранить ответ: ${error.message}`;
      accepting = true;
      options.querySelectorAll("button").forEach((button) => { button.disabled = false; });
    }
  }

  function showResult(payload) {
    clearClock();
    accepting = false;
    task.hidden = true;
    result.hidden = false;
    restart.disabled = false;
    progress.textContent = "Время завершено";
    instruction.textContent = "Минута закончилась.";
    const correctCount = payload.events.filter((event) => event.correct).length;
    resultText.textContent = `Выполнено: ${payload.events.length}. Правильных ответов: ${correctCount}.`;
  }

  async function finishByTime() {
    if (!active || !state || requestInFlight) return;
    accepting = false;
    requestInFlight = true;
    options.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    try {
      const payload = await api.answer({ session_id: state.session_id, time_up: true });
      if (active) showResult(payload);
    } catch (error) {
      requestInFlight = false;
      instruction.textContent = `Не удалось завершить игру: ${error.message}`;
    }
  }

  async function begin() {
    token += 1;
    accepting = false;
    requestInFlight = false;
    clearClock();
    start.disabled = true;
    restart.disabled = true;
    task.hidden = true;
    result.hidden = true;
    instruction.textContent = "Подготавливаю задание…";
    try {
      const payload = await api.start();
      renderTrial(payload);
      startClock(payload.duration_ms);
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
    clearClock();
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm12-module { display: grid; place-items: center; text-align: center; overflow: hidden; }
    .gm12-module-task { width: min(720px, 94%); }
    .gm12-module-task[hidden] { display: none; }
    .gm12-module-picture {
      display: grid; place-items: center; width: min(270px, 35vh, 60vw); aspect-ratio: 1;
      margin: 0 auto clamp(14px, 2.5vh, 24px); padding: clamp(18px, 3vh, 30px);
      border: 2px solid #cbd8de; border-radius: 24px; background: #fff;
    }
    .gm12-module-picture img { width: 100%; height: 100%; object-fit: contain; }
    .gm12-module-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    .gm12-module-option {
      min-height: 62px; padding: 12px 18px; border: 2px solid #cbd8de; border-radius: 16px;
      background: #fff; color: #17212b; font: inherit; font-size: clamp(17px, 2.2vh, 22px);
      font-weight: 700; cursor: pointer;
    }
    .gm12-module-option:hover:not(:disabled), .gm12-module-option:focus-visible { border-color: #33a9ca; background: #edfaff; }
    .gm12-module-option.is-selected { border-color: #79919d; background: #edf2f4; }
    .gm12-module-option.is-correct { border-color: #16875c; background: #dff5e9; color: #126b4a; }
    .gm12-module-option.is-incorrect { border-color: #c63d4b; background: #fde5e8; color: #9d2f3b; }
    .gm12-module-option:disabled { cursor: default; opacity: .78; }
    @media (max-height: 720px) {
      .gm12-module-picture { width: min(210px, 29vh); margin-bottom: 12px; padding: 16px; }
      .gm12-module-option { min-height: 50px; padding: 8px 14px; }
    }
    @media (max-width: 520px) {
      .gm12-module-options { grid-template-columns: 1fr; gap: 8px; }
      .gm12-module-picture { width: min(200px, 28vh, 58vw); }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    accepting = false;
    token += 1;
    clearClock();
  };
}

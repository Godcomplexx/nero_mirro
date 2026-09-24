const TRIAL_SLOT_MS = 1500;

export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">ВНИМАНИЕ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Нажимайте на обычную «В» и не нажимайте на зеркальную.</p>
      </div>
      <div class="game-progress-new" data-progress>Стимул 1 из 40</div>
    </header>
    <main class="game-stage-new gm08-module">
      <div class="game-intro-new" data-intro>
        <p>Нажмите пробел или кнопку при обычной букве. При зеркальной букве удержитесь от ответа.</p>
        <div class="gm08-module-examples">
          <span><b>В</b><small>нажимать</small></span>
          <span><b class="is-mirrored">В</b><small>не нажимать</small></span>
        </div>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <button type="button" class="gm08-module-stimulus" data-stimulus hidden aria-label="Ответить">В</button>
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
  const stimulus = container.querySelector("[data-stimulus]");
  const result = container.querySelector("[data-result]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const restart = container.querySelector("[data-restart]");
  let state = null;
  let accepting = false;
  let responseTimer = null;
  let shownAt = 0;
  let token = 0;
  let active = true;

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  async function renderTrial(payload) {
    const currentToken = ++token;
    state = payload;
    accepting = false;
    clearTimeout(responseTimer);
    progress.textContent = `Стимул ${payload.trial} из ${payload.trial_count}`;
    instruction.textContent = "Приготовьтесь…";
    intro.hidden = true;
    result.hidden = true;
    stimulus.hidden = true;
    await delay(220);
    if (!active || currentToken !== token) return;
    stimulus.classList.toggle("is-mirrored", payload.mirrored);
    stimulus.hidden = false;
    shownAt = performance.now();
    accepting = true;
    instruction.textContent = "Нажимайте только на обычную букву.";
    responseTimer = setTimeout(() => respond(false), payload.display_ms);
  }

  async function respond(responded) {
    if (!accepting || !state) return;
    accepting = false;
    clearTimeout(responseTimer);
    const reaction = responded ? performance.now() - shownAt : null;
    stimulus.hidden = true;
    const elapsed = performance.now() - shownAt;
    if (elapsed < TRIAL_SLOT_MS) await delay(TRIAL_SLOT_MS - elapsed);
    if (!active) return;
    try {
      const payload = await api.answer({
        session_id: state.session_id,
        responded,
        reaction_ms: reaction,
        timestamp_ms: Date.now(),
      });
      if (!active) return;
      if (!payload.finished) {
        await renderTrial(payload);
        return;
      }
      result.hidden = false;
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Все 40 стимулов завершены.";
      resultText.textContent = `Ошибок: ${payload.metrics.u07_error_count}.`;
    } catch (error) {
      instruction.textContent = `Не удалось сохранить ответ: ${error.message}`;
      accepting = true;
      stimulus.hidden = false;
    }
  }

  async function begin() {
    token += 1;
    accepting = false;
    clearTimeout(responseTimer);
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

  function onKeyDown(event) {
    if (event.code !== "Space" || !accepting) return;
    event.preventDefault();
    respond(true);
  }

  stimulus.onclick = () => respond(true);
  start.onclick = begin;
  restart.onclick = begin;
  window.addEventListener("keydown", onKeyDown);
  container.querySelector("[data-close]").onclick = () => {
    active = false;
    token += 1;
    accepting = false;
    clearTimeout(responseTimer);
    window.removeEventListener("keydown", onKeyDown);
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm08-module { text-align: center; }
    .gm08-module-examples { display: flex; justify-content: center; gap: 28px; margin: 20px 0 26px; }
    .gm08-module-examples span { display: grid; gap: 5px; color: #526875; }
    .gm08-module-examples b {
      display: grid;
      place-items: center;
      width: 92px;
      aspect-ratio: 1;
      border: 2px solid #cbd8de;
      border-radius: 18px;
      background: #fff;
      color: #17212b;
      font-size: 62px;
    }
    .gm08-module-examples .is-mirrored { transform: scaleX(-1); }
    .gm08-module-stimulus {
      width: min(300px, 45vh, 60vw);
      aspect-ratio: 1;
      border: 2px solid #c8d7de;
      border-radius: 28px;
      background: #fff;
      color: #17212b;
      font-size: clamp(100px, 24vh, 210px);
      font-weight: 800;
      box-shadow: 0 14px 28px rgba(20, 35, 45, .12);
    }
    .gm08-module-stimulus[hidden] { display: none; }
    .gm08-module-stimulus.is-mirrored { transform: scaleX(-1); }
    @media (max-height: 700px) {
      .gm08-module-stimulus { width: min(250px, 38vh); }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    token += 1;
    accepting = false;
    clearTimeout(responseTimer);
    window.removeEventListener("keydown", onKeyDown);
  };
}

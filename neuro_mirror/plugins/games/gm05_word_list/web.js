export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">ПАМЯТЬ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Запомните слова, затем найдите их среди предложенных.</p>
      </div>
      <div class="game-progress-new" data-progress>Раунд 1 из 3</div>
    </header>
    <main class="game-stage-new gm05-module">
      <div class="game-intro-new" data-intro>
        <p>В каждом раунде пять слов показываются на несколько секунд.</p>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <div class="gm05-module-study" data-study hidden></div>
      <div class="gm05-module-choice" data-choice hidden>
        <div class="gm05-module-words" data-words></div>
        <button type="button" class="icon-btn primary-btn" data-submit><span>Готово</span></button>
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
  const study = container.querySelector("[data-study]");
  const choice = container.querySelector("[data-choice]");
  const words = container.querySelector("[data-words]");
  const result = container.querySelector("[data-result]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const restart = container.querySelector("[data-restart]");
  const submit = container.querySelector("[data-submit]");
  let state = null;
  let selected = new Set();
  let renderToken = 0;
  let active = true;
  let busy = false;

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  async function renderRound(payload) {
    const token = ++renderToken;
    state = payload;
    selected = new Set();
    busy = false;
    progress.textContent = `Раунд ${payload.round} из ${payload.round_count}`;
    instruction.textContent = `${payload.category}: запомните слова.`;
    intro.hidden = true;
    choice.hidden = true;
    result.hidden = true;
    study.hidden = false;
    study.replaceChildren(...payload.study_words.map((word) => {
      const card = document.createElement("div");
      card.className = "gm05-module-study-word";
      card.textContent = word;
      return card;
    }));
    await delay(payload.study_ms);
    if (!active || token !== renderToken) return;

    words.replaceChildren(...payload.choices.map((word) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "gm05-module-word";
      button.textContent = word;
      button.onclick = () => {
        button.classList.toggle("is-selected");
        if (button.classList.contains("is-selected")) selected.add(word);
        else selected.delete(word);
      };
      return button;
    }));
    instruction.textContent = "Выберите все слова, которые были показаны.";
    study.hidden = true;
    choice.hidden = false;
  }

  async function begin() {
    renderToken += 1;
    start.disabled = true;
    restart.disabled = true;
    instruction.textContent = "Подготавливаю слова…";
    try {
      await renderRound(await api.start());
    } catch (error) {
      instruction.textContent = `Не удалось начать игру: ${error.message}`;
      start.disabled = false;
      restart.disabled = false;
    }
  }

  submit.onclick = async () => {
    if (busy || !state) return;
    busy = true;
    submit.disabled = true;
    instruction.textContent = "Проверяю ответ…";
    try {
      const payload = await api.answer({
        session_id: state.session_id,
        selected: [...selected],
        timestamp_ms: Date.now(),
      });
      submit.disabled = false;
      if (!active) return;
      if (!payload.finished) {
        await renderRound(payload);
        return;
      }
      choice.hidden = true;
      result.hidden = false;
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Задание выполнено.";
      resultText.textContent = `Узнано целей: ${Math.round((payload.metrics.m07_target_recognition_rate || 0) * 100)}%.`;
    } catch (error) {
      instruction.textContent = `Не удалось проверить ответ: ${error.message}`;
      submit.disabled = false;
      busy = false;
    }
  };

  start.onclick = begin;
  restart.onclick = begin;
  container.querySelector("[data-close]").onclick = () => {
    active = false;
    renderToken += 1;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm05-module { text-align: center; }
    .gm05-module-study {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: clamp(10px, 2vw, 18px);
      width: min(820px, 90%);
    }
    .gm05-module-study[hidden], .gm05-module-choice[hidden] { display: none; }
    .gm05-module-study-word {
      padding: clamp(18px, 3vh, 30px) clamp(24px, 4vw, 44px);
      border: 2px solid #c6d5dc;
      border-radius: 18px;
      background: #fff;
      font-size: clamp(22px, 3vw, 32px);
      font-weight: 650;
    }
    .gm05-module-choice { width: min(780px, 92%); }
    .gm05-module-words {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: clamp(8px, 1.5vh, 14px);
      margin-bottom: clamp(12px, 2vh, 24px);
    }
    .gm05-module-word {
      padding: clamp(11px, 1.8vh, 18px);
      border: 2px solid #cbd8de;
      border-radius: 15px;
      background: #fff;
      color: #17212b;
      font-size: clamp(17px, 2.2vw, 22px);
    }
    .gm05-module-word:hover { border-color: #72b9c8; }
    .gm05-module-word.is-selected { border-color: #168ba8; background: #dff5fa; }
    @media (max-height: 700px) {
      .gm05-module-word { padding: 8px; }
      .gm05-module-study-word { padding: 14px 22px; }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    renderToken += 1;
  };
}

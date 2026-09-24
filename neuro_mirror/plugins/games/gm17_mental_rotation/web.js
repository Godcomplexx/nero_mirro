const TRIAL_SLOT_MS = 6000;
const SVG_NS = "http://www.w3.org/2000/svg";

export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">АБСТРАКЦИЯ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Выберите фигуру, которая совпадает с образцом после поворота.</p>
      </div>
      <div class="game-progress-new" data-progress>Проба 1 из 10</div>
    </header>
    <main class="game-stage-new gm17-module">
      <div class="game-intro-new" data-intro>
        <p>Фигура может быть повёрнута, но её форма не меняется. Сравните образец с двумя вариантами и выберите совпадающий.</p>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <div class="gm17-module-play" data-play hidden>
        <section class="gm17-module-section">
          <p class="mono">ОБРАЗЕЦ</p>
          <div class="gm17-module-sample" data-sample></div>
        </section>
        <div class="gm17-module-divider" aria-hidden="true"></div>
        <section class="gm17-module-section">
          <p class="mono">ВЫБЕРИТЕ СОВПАДАЮЩУЮ ФИГУРУ</p>
          <div class="gm17-module-choices" data-choices></div>
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
  const sample = container.querySelector("[data-sample]");
  const choices = container.querySelector("[data-choices]");
  const result = container.querySelector("[data-result]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const restart = container.querySelector("[data-restart]");
  let state = null;
  let accepting = false;
  let shownAt = 0;
  let token = 0;
  let active = true;

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function createShape(shape) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("aria-hidden", "true");
    const group = document.createElementNS(SVG_NS, "g");
    group.setAttribute("transform", `rotate(${Number(shape.rotation) || 0} 50 50)`);
    const polygon = document.createElementNS(SVG_NS, "polygon");
    polygon.setAttribute("points", (shape.points || []).map((point) => point.join(",")).join(" "));
    group.append(polygon);
    svg.append(group);
    return svg;
  }

  function renderTrial(payload) {
    state = payload;
    accepting = true;
    shownAt = performance.now();
    sample.replaceChildren(createShape(payload.sample));
    choices.replaceChildren();
    payload.choices.forEach((choice, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "gm17-module-choice";
      button.setAttribute("aria-label", `Вариант ${index + 1}`);
      button.append(createShape(choice));
      button.onclick = () => submitAnswer(choice.id, button);
      choices.append(button);
    });
    progress.textContent = `Проба ${payload.trial} из ${payload.trial_count}`;
    instruction.textContent = "Выберите фигуру, которая совпадает с образцом после поворота.";
    intro.hidden = true;
    result.hidden = true;
    play.hidden = false;
  }

  async function submitAnswer(selectedId, button) {
    if (!accepting || !state) return;
    accepting = false;
    const currentToken = token;
    button.classList.add("is-selected");
    choices.querySelectorAll("button").forEach((item) => { item.disabled = true; });
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
      instruction.textContent = "Все пробы завершены.";
      const accuracy = Math.round(Number(payload.metrics?.u01_correct_action_rate || 0) * 100);
      resultText.textContent = `Правильных ответов: ${accuracy}%.`;
    } catch (error) {
      button.classList.remove("is-selected");
      choices.querySelectorAll("button").forEach((item) => { item.disabled = false; });
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
    instruction.textContent = "Подготавливаю задание…";
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
    .gm17-module { display: grid; place-items: center; text-align: center; overflow: hidden; }
    .gm17-module-play { width: min(980px, 100%); display: grid; grid-template-columns: minmax(180px, 1fr) 1px minmax(380px, 2fr); align-items: center; gap: clamp(20px, 4vw, 56px); }
    .gm17-module-play[hidden] { display: none; }
    .gm17-module-section > p { margin: 0 0 16px; color: #667784; font-size: 12px; letter-spacing: .14em; }
    .gm17-module-sample, .gm17-module-choice { border: 2px solid #d1dde3; border-radius: clamp(16px, 2vw, 24px); background: #fff; }
    .gm17-module-sample { width: min(250px, 29vh, 100%); aspect-ratio: 1; margin: auto; padding: clamp(20px, 3vh, 30px); }
    .gm17-module-divider { align-self: stretch; background: #d8e0e5; }
    .gm17-module-choices { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: clamp(14px, 2vw, 26px); }
    .gm17-module-choice { aspect-ratio: 1; padding: clamp(18px, 3vh, 30px); color: #17212b; cursor: pointer; transition: border-color 120ms ease, box-shadow 120ms ease; }
    .gm17-module-choice:hover:not(:disabled), .gm17-module-choice:focus-visible { border-color: #36b7d7; box-shadow: 0 0 0 4px rgba(54,183,215,.14); }
    .gm17-module-choice.is-selected { border-color: #168ba8; background: #e8f8fc; }
    .gm17-module-choice:disabled { cursor: default; }
    .gm17-module-sample svg, .gm17-module-choice svg { width: 100%; height: 100%; display: block; }
    .gm17-module-sample polygon, .gm17-module-choice polygon { fill: #17212b; }
    @media (max-height: 700px) {
      .gm17-module-sample { width: min(205px, 27vh); padding: 18px; }
      .gm17-module-play { grid-template-columns: minmax(160px, 1fr) 1px minmax(320px, 2fr); gap: 22px; }
      .gm17-module-choice { padding: 16px; }
    }
    @media (max-width: 680px) {
      .gm17-module-play { grid-template-columns: 1fr 1.5fr; gap: 14px; }
      .gm17-module-divider { display: none; }
      .gm17-module-choices { gap: 8px; }
      .gm17-module-sample { width: min(180px, 25vh); }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    accepting = false;
    token += 1;
  };
}

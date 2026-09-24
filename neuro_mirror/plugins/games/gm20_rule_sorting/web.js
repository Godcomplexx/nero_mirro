const SVG_NS = "http://www.w3.org/2000/svg";
const TRIAL_SLOT_MS = 1000;

export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">АБСТРАКЦИЯ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Определите скрытое правило по обратной связи и выберите подходящую карточку.</p>
      </div>
      <div class="game-progress-new" data-progress>Карточка 1 из 60</div>
    </header>
    <main class="game-stage-new gm20-module">
      <div class="game-intro-new" data-intro>
        <p>Сопоставляйте нижнюю карточку с одной из четырёх верхних. Правило не показывается и может измениться во время игры.</p>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <div class="gm20-module-play" data-play hidden>
        <section class="gm20-module-reference-wrap">
          <p class="mono">ВЫБЕРИТЕ ПОДХОДЯЩУЮ КАРТОЧКУ</p>
          <div class="gm20-module-references" data-references></div>
        </section>
        <section class="gm20-module-stimulus-wrap">
          <p class="mono">СОРТИРУЕМАЯ КАРТОЧКА</p>
          <div class="gm20-module-stimulus" data-stimulus></div>
        </section>
      </div>
      <div class="gm20-module-feedback" data-feedback hidden></div>
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
  const references = container.querySelector("[data-references]");
  const stimulus = container.querySelector("[data-stimulus]");
  const feedback = container.querySelector("[data-feedback]");
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

  function createShape(shape, color) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("aria-hidden", "true");
    let node;
    if (shape === "circle") {
      node = document.createElementNS(SVG_NS, "circle");
      node.setAttribute("cx", "50"); node.setAttribute("cy", "50"); node.setAttribute("r", "34");
    } else if (shape === "triangle") {
      node = document.createElementNS(SVG_NS, "polygon");
      node.setAttribute("points", "50,12 90,84 10,84");
    } else if (shape === "star") {
      node = document.createElementNS(SVG_NS, "polygon");
      node.setAttribute("points", "50,7 61,36 93,37 68,56 77,88 50,69 23,88 32,56 7,37 39,36");
    } else {
      node = document.createElementNS(SVG_NS, "rect");
      node.setAttribute("x", "16"); node.setAttribute("y", "16");
      node.setAttribute("width", "68"); node.setAttribute("height", "68"); node.setAttribute("rx", "5");
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

  function renderTrial(payload) {
    state = payload;
    accepting = true;
    shownAt = performance.now();
    references.replaceChildren();
    const displayOrder = { 1: 0, 4: 1, 2: 2, 3: 3 };
    [...payload.references].sort((left, right) => displayOrder[left.count] - displayOrder[right.count]).forEach((reference) => {
      const card = createCard(reference, true);
      card.setAttribute("aria-label", `Эталонная карточка: фигур ${reference.count}`);
      card.onclick = () => submitAnswer(reference.id, card);
      references.append(card);
    });
    stimulus.replaceChildren(createCard(payload.stimulus));
    progress.textContent = `Карточка ${payload.trial} из ${payload.trial_count}`;
    instruction.textContent = "Выберите эталонную карточку по предполагаемому правилу.";
    feedback.hidden = true;
    feedback.className = "gm20-module-feedback";
    intro.hidden = true;
    result.hidden = true;
    play.hidden = false;
  }

  async function submitAnswer(selectedReference, card) {
    if (!accepting || !state) return;
    accepting = false;
    const currentToken = token;
    card.classList.add("is-selected");
    references.querySelectorAll("button").forEach((button) => { button.disabled = true; });
    try {
      const payload = await api.answer({
        session_id: state.session_id,
        selected_reference: selectedReference,
        timestamp_ms: Date.now(),
      });
      if (!active || currentToken !== token) return;
      const correct = payload.feedback === "correct";
      feedback.className = `gm20-module-feedback ${correct ? "is-correct" : "is-incorrect"}`;
      feedback.textContent = correct ? "Верно" : "Неверно";
      feedback.hidden = false;
      const remaining = Math.max(650, TRIAL_SLOT_MS - (performance.now() - shownAt));
      await delay(remaining);
      if (!active || currentToken !== token) return;
      if (!payload.finished) {
        renderTrial(payload);
        return;
      }
      feedback.hidden = true;
      play.hidden = true;
      result.hidden = false;
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Все карточки распределены.";
      const accuracy = Math.round(Number(payload.metrics?.u01_correct_action_rate || 0) * 100);
      resultText.textContent = `Правильных ответов: ${accuracy}%.`;
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
    play.hidden = true;
    result.hidden = true;
    feedback.hidden = true;
    instruction.textContent = "Подготавливаю карточки…";
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
    .gm20-module { position: relative; display: grid; place-items: center; overflow: hidden; padding: clamp(9px, 1.5vh, 18px); }
    .gm20-module-play { width: min(650px, 58vh, 96%); display: grid; justify-items: center; gap: clamp(12px, 2vh, 20px); }
    .gm20-module-play[hidden] { display: none; }
    .gm20-module-reference-wrap, .gm20-module-stimulus-wrap { width: 100%; text-align: center; }
    .gm20-module-reference-wrap > p, .gm20-module-stimulus-wrap > p { margin: 0 0 9px; color: #667784; font-size: 11px; letter-spacing: .13em; }
    .gm20-module-references { width: min(590px, 100%); margin: auto; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: clamp(10px, 1.6vh, 16px); }
    .gm20-module-card { width: 100%; min-width: 0; aspect-ratio: 1.7; display: grid; place-items: center; border: 2px solid #d2dee4; border-radius: clamp(12px, 1.5vw, 19px); background: #fff; padding: clamp(8px, 1.5vh, 16px); overflow: hidden; color: #17212b; }
    .gm20-module-references .gm20-module-card.count-1, .gm20-module-references .gm20-module-card.count-4 { aspect-ratio: 1; }
    .gm20-module-reference { cursor: pointer; transition: border-color 120ms ease, box-shadow 120ms ease; }
    .gm20-module-reference:hover:not(:disabled), .gm20-module-reference:focus-visible { border-color: #36b7d7; box-shadow: 0 0 0 4px rgba(54,183,215,.14); }
    .gm20-module-reference.is-selected { border-color: #168ba8; background: #e8f8fc; }
    .gm20-module-reference:disabled { cursor: default; }
    .gm20-module-stimulus { width: clamp(145px, 18vh, 190px); margin: auto; }
    .gm20-module-symbols { width: 100%; height: 100%; min-width: 0; min-height: 0; display: grid; place-items: center; gap: 4px; overflow: hidden; }
    .gm20-module-symbols.count-1 { grid-template: 1fr / 1fr; }
    .gm20-module-symbols.count-2 { grid-template: 1fr / repeat(2, 1fr); }
    .gm20-module-symbols.count-3 { grid-template: 1fr / repeat(3, 1fr); }
    .gm20-module-symbols.count-4 { grid-template: repeat(2, 1fr) / repeat(2, 1fr); }
    .gm20-module-symbols svg { width: 78%; height: 78%; min-width: 0; min-height: 0; max-width: 100%; max-height: 100%; }
    .gm20-module-symbols .is-red { fill: #d83a48; } .gm20-module-symbols .is-green { fill: #29a46f; }
    .gm20-module-symbols .is-blue { fill: #327bd6; } .gm20-module-symbols .is-yellow { fill: #e3ac24; }
    .gm20-module-feedback { position: absolute; inset: 0; z-index: 2; display: grid; place-items: center; border-radius: inherit; background: rgba(244,247,248,.94); font-size: clamp(36px, 6vw, 68px); font-weight: 800; }
    .gm20-module-feedback[hidden] { display: none; }
    .gm20-module-feedback.is-correct { color: #16875c; } .gm20-module-feedback.is-incorrect { color: #c63d4b; }
    @media (max-height: 700px) {
      .gm20-module-play { width: min(520px, 55vh, 96%); gap: 7px; }
      .gm20-module-references { width: min(470px, 100%); gap: 7px; }
      .gm20-module-card { padding: 5px; }
      .gm20-module-stimulus { width: min(115px, 15vh); }
      .gm20-module-reference-wrap > p, .gm20-module-stimulus-wrap > p { margin-bottom: 4px; }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    accepting = false;
    token += 1;
  };
}

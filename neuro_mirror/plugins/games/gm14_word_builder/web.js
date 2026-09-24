const FIRST_ATTEMPT_SLOT_MS = 6000;

export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">РЕЧЬ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Расположите буквы в правильном порядке.</p>
      </div>
      <div class="game-progress-new" data-progress>Слово 1 из 10</div>
    </header>
    <main class="game-stage-new gm14-module">
      <div class="game-intro-new" data-intro>
        <p>Соберите слово из перемешанных букв. Буквы можно перетаскивать или последовательно выбирать кликами.</p>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <div class="gm14-module-play" data-play hidden>
        <div class="gm14-module-slots" data-slots aria-label="Ячейки для слова"></div>
        <div class="gm14-module-bank" data-bank aria-label="Перемешанные буквы"></div>
        <p class="gm14-module-hint" data-status>Выберите букву, затем свободную ячейку.</p>
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
  const slots = container.querySelector("[data-slots]");
  const bank = container.querySelector("[data-bank]");
  const status = container.querySelector("[data-status]");
  const result = container.querySelector("[data-result]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const restart = container.querySelector("[data-restart]");
  let state = null;
  let selectedTile = null;
  let placements = [];
  let submitting = false;
  let firstAttempt = true;
  let shownAt = 0;
  let active = true;
  let token = 0;

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function locationOf(tile) {
    const parent = tile?.parentElement;
    return parent?.classList.contains("gm14-module-slot") ? `slot-${parent.dataset.slotIndex}` : "bank";
  }

  function selectTile(tile) {
    selectedTile?.classList.remove("is-selected");
    selectedTile = tile;
    selectedTile?.classList.add("is-selected");
  }

  function recordPlacement(tile, from) {
    placements.push({
      tile_id: tile.dataset.tileId,
      letter: tile.dataset.letter,
      from,
      to: locationOf(tile),
      timestamp_ms: Date.now(),
    });
  }

  function moveTile(tile, destination) {
    if (!tile || !destination || submitting || tile.parentElement === destination) return;
    const source = tile.parentElement;
    const from = locationOf(tile);
    const occupant = destination.classList.contains("gm14-module-slot")
      ? destination.querySelector(".gm14-module-tile") : null;
    if (occupant && occupant !== tile) {
      if (source?.classList.contains("gm14-module-slot")) source.append(occupant);
      else bank.append(occupant);
    }
    destination.append(tile);
    recordPlacement(tile, from);
    selectTile(null);
    maybeSubmit();
  }

  function bindDropZone(zone) {
    zone.ondragover = (event) => {
      event.preventDefault();
      zone.classList.add("is-drop-target");
    };
    zone.ondragleave = () => zone.classList.remove("is-drop-target");
    zone.ondrop = (event) => {
      event.preventDefault();
      zone.classList.remove("is-drop-target");
      const id = event.dataTransfer.getData("text/plain");
      moveTile(container.querySelector(`[data-tile-id="${CSS.escape(id)}"]`), zone);
    };
    zone.onclick = (event) => {
      if (event.target === zone && selectedTile) moveTile(selectedTile, zone);
    };
  }

  function makeTile(item) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "gm14-module-tile";
    tile.draggable = true;
    tile.dataset.tileId = item.id;
    tile.dataset.letter = item.letter;
    tile.textContent = item.letter.toUpperCase();
    tile.ondragstart = (event) => {
      event.dataTransfer.setData("text/plain", item.id);
      event.dataTransfer.effectAllowed = "move";
      selectTile(tile);
    };
    tile.onclick = (event) => {
      event.stopPropagation();
      if (tile.parentElement?.classList.contains("gm14-module-slot")) {
        moveTile(tile, bank);
      } else {
        selectTile(selectedTile === tile ? null : tile);
      }
    };
    return tile;
  }

  function renderWord(payload) {
    state = payload;
    placements = [];
    submitting = false;
    firstAttempt = true;
    shownAt = performance.now();
    selectTile(null);
    slots.replaceChildren();
    bank.replaceChildren();
    payload.letters.forEach((_, index) => {
      const slot = document.createElement("div");
      slot.className = "gm14-module-slot";
      slot.dataset.slotIndex = String(index);
      slot.setAttribute("aria-label", `Позиция ${index + 1}`);
      bindDropZone(slot);
      slots.append(slot);
    });
    bindDropZone(bank);
    payload.letters.forEach((item) => bank.append(makeTile(item)));
    progress.textContent = `Слово ${payload.word_number} из ${payload.word_count}`;
    instruction.textContent = payload.correct
      ? "Верно! Соберите следующее слово."
      : "Расположите буквы в правильном порядке.";
    status.textContent = "Выберите букву, затем свободную ячейку.";
    intro.hidden = true;
    result.hidden = true;
    play.hidden = false;
  }

  async function maybeSubmit() {
    if (submitting || !state) return;
    const slotList = [...slots.querySelectorAll(".gm14-module-slot")];
    const tiles = slotList.map((slot) => slot.querySelector(".gm14-module-tile"));
    if (tiles.some((tile) => !tile)) return;
    submitting = true;
    const currentToken = token;
    const assembled = tiles.map((tile) => tile.dataset.letter).join("");
    if (firstAttempt) {
      status.textContent = "Слово составлено, проверяю…";
      const elapsed = performance.now() - shownAt;
      if (elapsed < FIRST_ATTEMPT_SLOT_MS) await delay(FIRST_ATTEMPT_SLOT_MS - elapsed);
    }
    if (!active || currentToken !== token) return;
    try {
      const payload = await api.answer({
        session_id: state.session_id,
        assembled,
        placements,
        timestamp_ms: Date.now(),
      });
      if (!active || currentToken !== token) return;
      if (payload.finished) {
        play.hidden = true;
        result.hidden = false;
        restart.disabled = false;
        progress.textContent = "Завершено";
        instruction.textContent = "Все слова собраны.";
        const accuracy = Math.round(Number(payload.metrics?.u01_first_attempt_word_accuracy || 0) * 100);
        resultText.textContent = `С первой попытки собрано правильно: ${accuracy}%.`;
        return;
      }
      if (payload.correct === false) {
        firstAttempt = false;
        submitting = false;
        instruction.textContent = "Пока неверно. Переставьте буквы и попробуйте ещё раз.";
        status.textContent = "Нажмите букву в ячейке, чтобы вернуть её вниз.";
        slots.classList.add("is-error");
        setTimeout(() => slots.classList.remove("is-error"), 350);
        return;
      }
      await delay(350);
      if (active && currentToken === token) renderWord(payload);
    } catch (error) {
      instruction.textContent = `Не удалось проверить слово: ${error.message}`;
      status.textContent = "Попробуйте ещё раз.";
      submitting = false;
    }
  }

  async function begin() {
    token += 1;
    submitting = true;
    start.disabled = true;
    restart.disabled = true;
    play.hidden = true;
    result.hidden = true;
    instruction.textContent = "Подготавливаю слова…";
    try {
      renderWord(await api.start());
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
    submitting = true;
    token += 1;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm14-module { display: grid; place-items: center; text-align: center; overflow: hidden; }
    .gm14-module-play { display: grid; gap: clamp(22px, 5vh, 48px); width: min(760px, 96%); }
    .gm14-module-play[hidden] { display: none; }
    .gm14-module-slots, .gm14-module-bank { display: flex; flex-wrap: wrap; justify-content: center; gap: clamp(10px, 1.8vw, 18px); }
    .gm14-module-bank { min-height: 106px; padding: 17px; border: 2px dashed #b9cbd3; border-radius: 22px; background: #edf3f5; }
    .gm14-module-slot, .gm14-module-tile { width: clamp(68px, 10vh, 92px); aspect-ratio: 1; border-radius: 18px; }
    .gm14-module-slot { display: grid; place-items: center; border: 2px dashed #a8bdc7; background: #fff; }
    .gm14-module-slot.is-drop-target, .gm14-module-bank.is-drop-target { border-color: #33a9ca; background: #e9f9fd; }
    .gm14-module-tile { border: 2px solid #c4d4da; background: #fff; color: #17212b; font: inherit; font-size: clamp(30px, 5vh, 46px); font-weight: 800; cursor: grab; box-shadow: 0 7px 16px rgba(20, 35, 45, .1); }
    .gm14-module-tile.is-selected { outline: 3px solid #29a9cc; outline-offset: 3px; }
    .gm14-module-slots.is-error { animation: gm14-module-error 300ms ease; }
    .gm14-module-hint { min-height: 22px; margin: -25px 0 0; color: #526875; }
    @keyframes gm14-module-error { 25% { transform: translateX(-7px); } 75% { transform: translateX(7px); } }
    @media (max-height: 700px) {
      .gm14-module-play { gap: 25px; }
      .gm14-module-bank { min-height: 82px; padding: 10px; }
      .gm14-module-slot, .gm14-module-tile { width: clamp(58px, 9vh, 76px); border-radius: 14px; }
      .gm14-module-hint { margin-top: -14px; }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    submitting = true;
    token += 1;
  };
}

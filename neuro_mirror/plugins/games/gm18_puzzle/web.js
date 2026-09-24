export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">АБСТРАКЦИЯ</p>
        <h2>${definition.title}</h2>
        <p>Выберите два фрагмента, чтобы поменять их местами и собрать изображение.</p>
      </div>
    </header>
    <main class="game-stage-new gm18">
      <div class="gm18-info"><span data-round></span><span data-moves></span></div>
      <div class="gm18-layout">
        <div class="gm18-board" data-board></div>
        <aside class="gm18-reference">
          <span class="mono">ОБРАЗЕЦ</span>
          <img data-reference alt="Образец собираемого изображения">
        </aside>
      </div>
      <p data-status aria-live="polite"></p>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const board = container.querySelector("[data-board]");
  const round = container.querySelector("[data-round]");
  const moves = container.querySelector("[data-moves]");
  const reference = container.querySelector("[data-reference]");
  const status = container.querySelector("[data-status]");
  let state = null;
  let selected = null;
  let active = true;
  let busy = false;

  function piecePosition(piece, columns, rows) {
    const column = piece % columns;
    const row = Math.floor(piece / columns);
    return {
      x: columns === 1 ? 0 : (column / (columns - 1)) * 100,
      y: rows === 1 ? 0 : (row / (rows - 1)) * 100,
    };
  }

  function render(payload) {
    if (!active) return;
    state = payload;
    selected = null;
    busy = false;
    round.textContent = payload.bonus
      ? "Дополнительный пазл"
      : `Пазл ${payload.round_number} из ${payload.required_rounds} · ${payload.name}`;
    moves.textContent = `Ходов: ${payload.move_count}`;
    status.textContent = "";
    reference.src = `/game-assets/differences/${payload.image}`;
    board.style.gridTemplateColumns = `repeat(${payload.columns}, 1fr)`;
    board.style.gridTemplateRows = `repeat(${payload.rows}, 1fr)`;
    board.replaceChildren();

    payload.board.forEach((piece, index) => {
      const position = piecePosition(piece, payload.columns, payload.rows);
      const tile = document.createElement("button");
      tile.type = "button";
      tile.className = "gm18-piece";
      tile.dataset.index = index;
      tile.setAttribute("aria-label", `Фрагмент ${index + 1}`);
      tile.style.backgroundImage = `url('/game-assets/differences/${payload.image}')`;
      tile.style.backgroundSize = `${payload.columns * 100}% ${payload.rows * 100}%`;
      tile.style.backgroundPosition = `${position.x}% ${position.y}%`;
      tile.onclick = () => choose(index, tile);
      board.append(tile);
    });
  }

  async function choose(index, tile) {
    if (busy) return;
    if (selected === null) {
      selected = index;
      tile.classList.add("is-selected");
      status.textContent = "Теперь выберите второй фрагмент";
      return;
    }
    if (selected === index) {
      selected = null;
      tile.classList.remove("is-selected");
      status.textContent = "";
      return;
    }
    busy = true;
    [...board.children].forEach((item) => { item.disabled = true; });
    status.textContent = "Переставляю…";
    try {
      const next = await api.answer({
        session_id: state.session_id,
        first_index: selected,
        second_index: index,
      });
      if (!active) return;
      if (next.finished) {
        board.replaceChildren();
        reference.hidden = true;
        round.textContent = "Готово";
        moves.textContent = "";
        status.textContent = "Все пазлы собраны. Результат сохранён.";
        return;
      }
      render(next);
    } catch (error) {
      status.textContent = error.message;
      busy = false;
      selected = null;
      [...board.children].forEach((item) => {
        item.disabled = false;
        item.classList.remove("is-selected");
      });
    }
  }

  container.querySelector("[data-close]").onclick = () => {
    active = false;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm18 { text-align: center; }
    .gm18-info {
      display: flex;
      justify-content: space-between;
      width: min(980px, 90vw);
      margin: 0 auto 10px;
      color: #455b68;
    }
    .gm18-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) clamp(110px, 14vw, 180px);
      align-items: start;
      gap: clamp(12px, 2vw, 24px);
      width: min(1040px, 92vw);
      margin: auto;
    }
    .gm18-board {
      display: grid;
      width: min(780px, 70vw, calc(58vh * 1.429));
      aspect-ratio: 1499 / 1049;
      gap: 2px;
      overflow: hidden;
      border: 3px solid #b8cbd4;
      border-radius: 16px;
      background: #dce6eb;
    }
    .gm18-piece {
      min-width: 0;
      min-height: 0;
      padding: 0;
      border: 0;
      border-radius: 0;
      background-repeat: no-repeat;
      transition: box-shadow .12s, filter .12s;
    }
    .gm18-piece:hover { filter: brightness(1.06); }
    .gm18-piece.is-selected {
      position: relative;
      z-index: 1;
      box-shadow: inset 0 0 0 6px #2fa6bd;
      filter: brightness(1.08);
    }
    .gm18-reference {
      color: #587180;
      font-size: 12px;
      letter-spacing: .12em;
    }
    .gm18-reference img {
      display: block;
      width: 100%;
      margin-top: 8px;
      border: 2px solid #c6d5dc;
      border-radius: 12px;
    }
    .gm18 [data-status] { min-height: 1.5em; margin: 10px 0 0; }
    @media (max-width: 720px) {
      .gm18-layout { grid-template-columns: 1fr; width: min(94vw, 620px); }
      .gm18-board { width: 100%; }
      .gm18-reference { display: none; }
    }
  `;
  container.append(style);
  api.start().then(render);

  return () => { active = false; };
}

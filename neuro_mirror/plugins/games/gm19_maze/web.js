const MAZE_SLOT_MS = 20000;

export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">АБСТРАКЦИЯ</p>
        <h2>${definition.title}</h2>
        <p data-instruction>Проведите линию от зелёного старта до красного финиша.</p>
      </div>
      <div class="game-progress-new" data-progress>Лабиринт 1 из 3</div>
    </header>
    <main class="game-stage-new gm19-module">
      <div class="game-intro-new" data-intro>
        <p>Нажмите на зелёную точку и ведите линию по проходам до красной точки, не отпуская кнопку мыши или палец.</p>
        <button type="button" class="icon-btn primary-btn" data-start><span>Начать</span></button>
      </div>
      <canvas class="gm19-module-canvas" data-canvas width="720" height="720" hidden></canvas>
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
  const canvas = container.querySelector("[data-canvas]");
  const result = container.querySelector("[data-result]");
  const resultText = container.querySelector("[data-result-text]");
  const start = container.querySelector("[data-start]");
  const restart = container.querySelector("[data-restart]");
  const context = canvas.getContext("2d");
  let state = null;
  let path = [];
  let drawing = false;
  let finishing = false;
  let errors = 0;
  let shownAt = 0;
  let startedAt = 0;
  let lastRejected = "";
  let active = true;
  let token = 0;

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  function draw() {
    if (!state) return;
    const size = state.size;
    const cell = canvas.width / size;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#f7fafb";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.strokeStyle = "#17212b";
    context.lineWidth = 4;
    context.beginPath();
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        const walls = state.walls[y][x];
        const x0 = x * cell;
        const y0 = y * cell;
        if (walls.n) { context.moveTo(x0, y0); context.lineTo(x0 + cell, y0); }
        if (walls.w) { context.moveTo(x0, y0); context.lineTo(x0, y0 + cell); }
        if (y === size - 1 && walls.s) { context.moveTo(x0, y0 + cell); context.lineTo(x0 + cell, y0 + cell); }
        if (x === size - 1 && walls.e) { context.moveTo(x0 + cell, y0); context.lineTo(x0 + cell, y0 + cell); }
      }
    }
    context.stroke();
    if (path.length) {
      context.strokeStyle = "#38a9c7";
      context.lineWidth = 8;
      context.lineCap = "round";
      context.beginPath();
      path.forEach(([x, y], index) => {
        const px = (x + 0.5) * cell;
        const py = (y + 0.5) * cell;
        if (index) context.lineTo(px, py); else context.moveTo(px, py);
      });
      context.stroke();
    }
    [[state.start, "#24a66f"], [state.finish, "#d83a48"]].forEach(([position, color]) => {
      context.fillStyle = color;
      context.beginPath();
      context.arc((position[0] + 0.5) * cell, (position[1] + 0.5) * cell, cell * 0.22, 0, Math.PI * 2);
      context.fill();
    });
  }

  function renderMaze(payload) {
    state = payload;
    path = [];
    drawing = false;
    finishing = false;
    errors = 0;
    lastRejected = "";
    shownAt = performance.now();
    progress.textContent = `Лабиринт ${payload.maze} из ${payload.maze_count}`;
    instruction.textContent = "Начните с зелёной точки и не отпускайте кнопку до финиша.";
    intro.hidden = true;
    result.hidden = true;
    canvas.hidden = false;
    draw();
  }

  function cellFromEvent(event) {
    const rect = canvas.getBoundingClientRect();
    return [
      Math.max(0, Math.min(state.size - 1, Math.floor((event.clientX - rect.left) / rect.width * state.size))),
      Math.max(0, Math.min(state.size - 1, Math.floor((event.clientY - rect.top) / rect.height * state.size))),
    ];
  }

  function canMove(from, to) {
    const [x, y] = from;
    const [nextX, nextY] = to;
    const dx = nextX - x;
    const dy = nextY - y;
    const direction = dx === 1 && dy === 0 ? "e"
      : dx === -1 && dy === 0 ? "w"
        : dx === 0 && dy === 1 ? "s"
          : dx === 0 && dy === -1 ? "n" : null;
    return Boolean(direction && !state.walls[y][x][direction]);
  }

  async function finishMaze() {
    if (finishing) return;
    drawing = false;
    finishing = true;
    const currentToken = token;
    const executionMs = performance.now() - startedAt;
    instruction.textContent = "Маршрут завершён…";
    const elapsed = performance.now() - shownAt;
    if (elapsed < MAZE_SLOT_MS) await delay(MAZE_SLOT_MS - elapsed);
    if (!active || currentToken !== token) return;
    try {
      const payload = await api.answer({
        session_id: state.session_id,
        path,
        boundary_errors: errors,
        planning_ms: startedAt - shownAt,
        execution_ms: executionMs,
        timestamp_ms: Date.now(),
      });
      if (!active || currentToken !== token) return;
      if (!payload.finished) {
        renderMaze(payload);
        return;
      }
      canvas.hidden = true;
      result.hidden = false;
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Все лабиринты пройдены.";
      resultText.textContent = `Выходов за границы: ${payload.metrics.v03_boundary_exits}.`;
    } catch (error) {
      finishing = false;
      path = [];
      instruction.textContent = `Не удалось сохранить маршрут: ${error.message}. Начните снова.`;
      draw();
    }
  }

  function onPointerDown(event) {
    if (!state || finishing) return;
    const cell = cellFromEvent(event);
    if (cell[0] !== state.start[0] || cell[1] !== state.start[1]) return;
    event.preventDefault();
    drawing = true;
    path = [[...state.start]];
    errors = 0;
    lastRejected = "";
    startedAt = performance.now();
    canvas.setPointerCapture(event.pointerId);
    draw();
  }

  function onPointerMove(event) {
    if (!drawing || finishing) return;
    event.preventDefault();
    const cell = cellFromEvent(event);
    const last = path[path.length - 1];
    if (cell[0] === last[0] && cell[1] === last[1]) {
      lastRejected = "";
      return;
    }
    if (canMove(last, cell)) {
      lastRejected = "";
      path.push(cell);
      draw();
      if (cell[0] === state.finish[0] && cell[1] === state.finish[1]) finishMaze();
      return;
    }
    const key = cell.join(",");
    if (key !== lastRejected) {
      errors += 1;
      lastRejected = key;
    }
  }

  function onPointerEnd() {
    if (!drawing || finishing) return;
    drawing = false;
    path = [];
    errors += 1;
    instruction.textContent = "Кнопка отпущена до финиша. Начните снова с зелёной точки.";
    draw();
  }

  async function begin() {
    token += 1;
    drawing = false;
    finishing = true;
    start.disabled = true;
    restart.disabled = true;
    canvas.hidden = true;
    result.hidden = true;
    instruction.textContent = "Создаю лабиринты…";
    try {
      renderMaze(await api.start());
    } catch (error) {
      finishing = false;
      instruction.textContent = `Не удалось начать игру: ${error.message}`;
      start.disabled = false;
      restart.disabled = false;
    }
  }

  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerEnd);
  canvas.addEventListener("pointercancel", onPointerEnd);
  start.onclick = begin;
  restart.onclick = begin;
  container.querySelector("[data-close]").onclick = () => {
    active = false;
    drawing = false;
    finishing = true;
    token += 1;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm19-module { display: grid; place-items: center; padding: clamp(7px, 1.2vh, 14px); overflow: hidden; }
    .gm19-module-canvas { display: block; width: min(68vh, 720px, 88vw); height: min(68vh, 720px, 88vw); max-width: 100%; touch-action: none; background: #fff; border-radius: 12px; }
    .gm19-module-canvas[hidden] { display: none; }
    @media (max-height: 720px) {
      .gm19-module-canvas { width: min(60vh, 560px, 86vw); height: min(60vh, 560px, 86vw); }
    }
  `;
  container.append(style);

  return () => {
    active = false;
    drawing = false;
    finishing = true;
    token += 1;
    canvas.removeEventListener("pointerdown", onPointerDown);
    canvas.removeEventListener("pointermove", onPointerMove);
    canvas.removeEventListener("pointerup", onPointerEnd);
    canvas.removeEventListener("pointercancel", onPointerEnd);
  };
}

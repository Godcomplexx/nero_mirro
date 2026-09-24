export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">АБСТРАКЦИЯ</p>
        <h2>${definition.title}</h2>
        <p>Перенесите башню на правый стержень. Больший диск нельзя класть на меньший.</p>
      </div>
    </header>
    <main class="game-stage-new gm22">
      <div class="gm22-info"><span data-level></span><span data-moves></span></div>
      <div class="gm22-board" data-board></div>
      <p class="gm22-hint">Сначала выберите стержень с диском, затем стержень назначения.</p>
      <p class="gm22-status" data-status aria-live="polite"></p>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const level = container.querySelector("[data-level]");
  const moves = container.querySelector("[data-moves]");
  const board = container.querySelector("[data-board]");
  const status = container.querySelector("[data-status]");
  const colors = ["#55b7d2", "#71c58a", "#f2c14e", "#ec8c66", "#c184d7", "#e65d72", "#6d8fe8"];
  let state = null;
  let selectedRod = null;
  let busy = false;
  let active = true;

  function setDisabled(disabled) {
    [...board.children].forEach((rod) => { rod.disabled = disabled; });
  }

  function render(payload) {
    if (!active) return;
    state = payload;
    selectedRod = null;
    busy = false;
    level.textContent = payload.bonus
      ? `Дополнительная башня · ${payload.disk_count} диска`
      : `Уровень ${payload.level_number} из ${payload.required_levels} · ${payload.disk_count} диска`;
    moves.textContent = `Ходов: ${payload.move_count}`;
    status.textContent = "";
    status.className = "gm22-status";
    board.replaceChildren();
    payload.rods.forEach((disks, rodIndex) => {
      const rod = document.createElement("button");
      rod.type = "button";
      rod.className = "gm22-rod";
      rod.setAttribute("aria-label", `Стержень ${rodIndex + 1}`);
      const pole = document.createElement("span");
      pole.className = "gm22-pole";
      const stack = document.createElement("span");
      stack.className = "gm22-stack";
      disks.forEach((diskSize) => {
        const disk = document.createElement("span");
        disk.className = "gm22-disk";
        disk.style.width = `${34 + (diskSize / payload.disk_count) * 60}%`;
        disk.style.background = colors[(diskSize - 1) % colors.length];
        stack.append(disk);
      });
      rod.append(pole, stack);
      rod.onclick = () => chooseRod(rodIndex, rod);
      board.append(rod);
    });

    if (payload.level_complete) {
      busy = true;
      setDisabled(true);
      status.textContent = "Уровень завершён";
      status.classList.add("is-correct");
      setTimeout(() => {
        if (!active) return;
        status.textContent = "";
        status.className = "gm22-status";
        setDisabled(false);
        busy = false;
      }, 700);
    } else if (payload.move_valid === false) {
      status.textContent = "Такой ход запрещён: больший диск нельзя положить на меньший";
      status.classList.add("is-wrong");
    }
  }

  async function chooseRod(rodIndex, rod) {
    if (busy) return;
    if (selectedRod === null) {
      selectedRod = rodIndex;
      rod.classList.add("is-selected");
      status.textContent = "Выберите стержень назначения";
      status.className = "gm22-status";
      return;
    }
    if (selectedRod === rodIndex) {
      selectedRod = null;
      rod.classList.remove("is-selected");
      status.textContent = "";
      return;
    }
    busy = true;
    setDisabled(true);
    try {
      const next = await api.answer({
        session_id: state.session_id,
        source_rod: selectedRod,
        target_rod: rodIndex,
      });
      if (!active) return;
      if (next.finished) {
        board.replaceChildren();
        level.textContent = "Готово";
        moves.textContent = "";
        status.textContent = "Все башни собраны. Результат сохранён.";
        status.className = "gm22-status is-correct";
        return;
      }
      render(next);
    } catch (error) {
      status.textContent = error.message;
      status.className = "gm22-status is-wrong";
      selectedRod = null;
      setDisabled(false);
      busy = false;
    }
  }

  container.querySelector("[data-close]").onclick = () => {
    active = false;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm22 { text-align: center; }
    .gm22-info {
      display: flex;
      justify-content: space-between;
      width: min(900px, 88vw);
      margin: 0 auto;
      color: #526b78;
    }
    .gm22-board {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: clamp(10px, 2vw, 24px);
      width: min(900px, 88vw);
      height: min(430px, 52vh);
      margin: clamp(12px, 2vh, 24px) auto 10px;
    }
    .gm22-rod {
      position: relative;
      min-width: 0;
      padding: 16px 8px 22px;
      overflow: hidden;
      border: 2px solid #cad7dd;
      border-radius: 22px;
      background: #f9fbfc;
      transition: border-color .12s, box-shadow .12s;
    }
    .gm22-rod:hover { border-color: #75b7c5; }
    .gm22-rod.is-selected { border-color: #2fa6bd; box-shadow: 0 0 0 5px rgba(47, 166, 189, .17); }
    .gm22-pole {
      position: absolute;
      left: 50%;
      bottom: 20px;
      width: 10px;
      height: 82%;
      transform: translateX(-50%);
      border-radius: 8px 8px 0 0;
      background: #6c7c84;
    }
    .gm22-rod::after {
      content: "";
      position: absolute;
      left: 7%;
      right: 7%;
      bottom: 14px;
      height: 12px;
      border-radius: 8px;
      background: #53646d;
    }
    .gm22-stack {
      position: absolute;
      z-index: 1;
      left: 5%;
      right: 5%;
      bottom: 26px;
      display: flex;
      flex-direction: column-reverse;
      align-items: center;
    }
    .gm22-disk {
      display: block;
      height: clamp(24px, 4.2vh, 42px);
      margin-top: 3px;
      border: 2px solid rgba(23, 33, 43, .18);
      border-radius: 12px;
      box-shadow: 0 4px 8px rgba(20, 35, 45, .12);
    }
    .gm22-hint { margin: 6px 0; color: #587180; }
    .gm22-status { min-height: 1.5em; margin: 5px 0; }
    .gm22-status.is-correct { color: #16835c; }
    .gm22-status.is-wrong { color: #b34c54; }
  `;
  container.append(style);
  api.start().then(render);

  return () => { active = false; };
}

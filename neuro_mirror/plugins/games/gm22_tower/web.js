const COLORS = ["#55b7d2", "#71c58a", "#f2c14e", "#ec8c66", "#c184d7", "#e65d72", "#6d8fe8"];

export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new"><div><p class="game-kicker-new mono">АБСТРАКЦИЯ</p><h2>${definition.title}</h2><p data-instruction>Перенесите башню на правый стержень, соблюдая правила.</p></div><div class="game-progress-new" data-progress>1. Инструкция</div></header>
    <main class="game-stage-new gm22 is-instruction-stage">
      <section class="gm22-tutorial" data-tutorial><h3>Как выполнять задание</h3><ol><li>Сначала нажмите на стержень, с которого хотите взять верхний диск.</li><li>Затем нажмите на стержень, куда хотите его перенести.</li><li>Перемещайте только по одному диску. Большой диск нельзя класть на маленький.</li><li>Соберите всю башню на правом стержне.</li></ol><div class="gm22-demo-placeholder"><span class="mono">ПРИМЕР ВЫПОЛНЕНИЯ</span><strong>Видеоинструкция появится здесь</strong></div><button type="button" class="icon-btn primary-btn" data-start-training><span>Перейти к тренировке</span></button></section>
      <section class="gm22-training" data-training hidden><h3>Тренировочный пример</h3><p>Перенесите башню из двух дисков на правый стержень.</p><div class="gm22-info"><span>2 диска</span><span data-training-moves>Ходов: 0</span></div><div class="gm22-board" data-training-board></div><p class="gm22-hint">Выберите стержень с диском, затем стержень назначения.</p><p class="gm22-status" data-training-status aria-live="polite"></p></section>
      <section class="gm22-complete" data-complete hidden><h3>Обучение завершено</h3><p>Вы правильно перенесли башню. Закончить обучение и начать игру?</p><div class="gm22-complete-actions"><button type="button" class="icon-btn gm22-secondary-btn" data-repeat><span>Повторить обучение</span></button><button type="button" class="icon-btn primary-btn" data-start><span>Да, начать игру</span></button></div></section>
      <section class="gm22-game" data-game hidden><div class="gm22-info"><span data-level></span><span data-moves></span></div><div class="gm22-board" data-board></div><p class="gm22-hint">Выберите стержень с диском, затем стержень назначения.</p><p class="gm22-status" data-status aria-live="polite"></p></section>
      <section class="game-result-new" data-result hidden><h3>Игра завершена</h3><p>Все башни собраны. Результат сохранён.</p><button type="button" class="icon-btn primary-btn" data-restart><span>Ещё раз</span></button></section>
    </main><footer class="game-actions-new"><button type="button" class="icon-btn" data-close><span>К выбору игр</span></button></footer>`;

  const q = (selector) => container.querySelector(selector);
  const stage = q(".gm22");
  const instruction = q("[data-instruction]");
  const progress = q("[data-progress]");
  const tutorial = q("[data-tutorial]");
  const training = q("[data-training]");
  const complete = q("[data-complete]");
  const game = q("[data-game]");
  const result = q("[data-result]");
  const trainingBoard = q("[data-training-board]");
  const trainingMoves = q("[data-training-moves]");
  const trainingStatus = q("[data-training-status]");
  const board = q("[data-board]");
  const status = q("[data-status]");
  const level = q("[data-level]");
  const moves = q("[data-moves]");
  const start = q("[data-start]");
  const restart = q("[data-restart]");
  const sections = [tutorial, training, complete, game, result];
  let state = null;
  let selectedRod = null;
  let busy = false;
  let active = true;
  let trainingRods = [[2, 1], [], []];
  let trainingSelected = null;
  let trainingMoveCount = 0;

  function showOnly(section) {
    sections.forEach((item) => { item.hidden = item !== section; });
    stage.classList.toggle("is-instruction-stage", section === tutorial);
  }

  function drawBoard(target, rods, diskCount, onChoose, selected = null) {
    target.replaceChildren();
    rods.forEach((disks, rodIndex) => {
      const rod = document.createElement("button");
      rod.type = "button";
      rod.className = `gm22-rod${selected === rodIndex ? " is-selected" : ""}`;
      rod.setAttribute("aria-label", `Стержень ${rodIndex + 1}`);
      const pole = document.createElement("span");
      pole.className = "gm22-pole";
      const stack = document.createElement("span");
      stack.className = "gm22-stack";
      disks.forEach((size) => {
        const disk = document.createElement("span");
        disk.className = "gm22-disk";
        disk.style.width = `${34 + (size / diskCount) * 60}%`;
        disk.style.background = COLORS[(size - 1) % COLORS.length];
        stack.append(disk);
      });
      rod.append(pole, stack);
      rod.onclick = () => onChoose(rodIndex);
      target.append(rod);
    });
  }

  function setDisabled(target, disabled) {
    target.querySelectorAll("button").forEach((rod) => { rod.disabled = disabled; });
  }

  function beginTraining() {
    trainingRods = [[2, 1], [], []];
    trainingSelected = null;
    trainingMoveCount = 0;
    trainingMoves.textContent = "Ходов: 0";
    trainingStatus.textContent = "";
    trainingStatus.className = "gm22-status";
    instruction.textContent = "Перенесите тренировочную башню на правый стержень.";
    progress.textContent = "2. Тренировочный пример";
    drawBoard(trainingBoard, trainingRods, 2, chooseTrainingRod);
    showOnly(training);
  }

  function chooseTrainingRod(index) {
    if (trainingSelected === null) {
      if (!trainingRods[index].length) {
        trainingStatus.textContent = "На этом стержне нет диска. Выберите другой.";
        trainingStatus.className = "gm22-status is-wrong";
        return;
      }
      trainingSelected = index;
      trainingStatus.textContent = "Теперь выберите стержень назначения";
      trainingStatus.className = "gm22-status";
      drawBoard(trainingBoard, trainingRods, 2, chooseTrainingRod, trainingSelected);
      return;
    }
    if (trainingSelected === index) {
      trainingSelected = null;
      trainingStatus.textContent = "";
      drawBoard(trainingBoard, trainingRods, 2, chooseTrainingRod);
      return;
    }
    const source = trainingRods[trainingSelected];
    const target = trainingRods[index];
    const disk = source[source.length - 1];
    if (target.length && disk > target[target.length - 1]) {
      trainingStatus.textContent = "Большой диск нельзя положить на маленький. Попробуйте другой ход.";
      trainingStatus.className = "gm22-status is-wrong";
      trainingSelected = null;
      drawBoard(trainingBoard, trainingRods, 2, chooseTrainingRod);
      return;
    }
    target.push(source.pop());
    trainingMoveCount += 1;
    trainingMoves.textContent = `Ходов: ${trainingMoveCount}`;
    trainingSelected = null;
    drawBoard(trainingBoard, trainingRods, 2, chooseTrainingRod);
    if (trainingRods[2].join(",") === "2,1") {
      setDisabled(trainingBoard, true);
      trainingStatus.textContent = "Верно. Башня собрана.";
      trainingStatus.className = "gm22-status is-correct";
      window.setTimeout(() => {
        if (!active) return;
        progress.textContent = "Обучение завершено";
        instruction.textContent = "Тренировочная башня собрана правильно.";
        showOnly(complete);
      }, 700);
    }
  }

  function render(payload) {
    if (!active) return;
    state = payload;
    selectedRod = null;
    busy = false;
    level.textContent = payload.bonus ? `Дополнительная башня · ${payload.disk_count} диска` : `Уровень ${payload.level_number} из ${payload.required_levels} · ${payload.disk_count} диска`;
    moves.textContent = `Ходов: ${payload.move_count}`;
    progress.textContent = payload.bonus ? "Дополнительный уровень" : `Уровень ${payload.level_number} из ${payload.required_levels}`;
    instruction.textContent = "Перенесите башню на правый стержень.";
    status.textContent = "";
    status.className = "gm22-status";
    drawBoard(board, payload.rods, payload.disk_count, chooseRod);
    showOnly(game);
    if (payload.level_complete) {
      busy = true;
      setDisabled(board, true);
      status.textContent = "Уровень завершён";
      status.className = "gm22-status is-correct";
      window.setTimeout(() => { if (active) { setDisabled(board, false); busy = false; } }, 700);
    } else if (payload.move_valid === false) {
      status.textContent = "Большой диск нельзя положить на маленький";
      status.className = "gm22-status is-wrong";
    }
  }

  async function chooseRod(index) {
    if (busy || !state) return;
    if (selectedRod === null) {
      selectedRod = index;
      status.textContent = "Выберите стержень назначения";
      drawBoard(board, state.rods, state.disk_count, chooseRod, selectedRod);
      return;
    }
    if (selectedRod === index) {
      selectedRod = null;
      status.textContent = "";
      drawBoard(board, state.rods, state.disk_count, chooseRod);
      return;
    }
    busy = true;
    setDisabled(board, true);
    try {
      const next = await api.answer({ session_id: state.session_id, source_rod: selectedRod, target_rod: index });
      if (!active) return;
      if (!next.finished) return render(next);
      progress.textContent = "Завершено";
      instruction.textContent = "Все башни собраны.";
      restart.disabled = false;
      showOnly(result);
    } catch (error) {
      status.textContent = error.message;
      status.className = "gm22-status is-wrong";
      selectedRod = null;
      setDisabled(board, false);
      busy = false;
    }
  }

  async function beginGame() {
    busy = true;
    start.disabled = true;
    restart.disabled = true;
    progress.textContent = "Подготовка";
    instruction.textContent = "Подготавливаю башню…";
    showOnly(game);
    board.replaceChildren();
    try { render(await api.start()); }
    catch (error) { instruction.textContent = `Не удалось начать игру: ${error.message}`; start.disabled = false; restart.disabled = false; showOnly(complete); }
  }

  q("[data-start-training]").onclick = beginTraining;
  q("[data-repeat]").onclick = beginTraining;
  start.onclick = beginGame;
  restart.onclick = beginGame;
  q("[data-close]").onclick = () => { active = false; close(); };

  const style = document.createElement("style");
  style.textContent = `
    .gm22{display:grid;place-items:center;text-align:center;overflow:hidden;padding:clamp(10px,2vh,22px)}.gm22.is-instruction-stage{align-items:start;overflow-y:auto}.gm22-tutorial,.gm22-training,.gm22-complete,.gm22-game{width:min(960px,96%)}.gm22-tutorial[hidden],.gm22-training[hidden],.gm22-complete[hidden],.gm22-game[hidden]{display:none}.gm22-tutorial h3,.gm22-training h3,.gm22-complete h3{margin:0 0 14px;color:#17212b}.gm22-tutorial ol{width:min(680px,92%);margin:0 auto 18px;padding-left:24px;text-align:left;color:#617180;line-height:1.55}.gm22-demo-placeholder{min-height:clamp(120px,20vh,190px);margin:0 auto 18px;display:grid;place-content:center;gap:8px;border:2px dashed #bdd2dc;border-radius:18px;background:#edf4f6;color:#607482}.gm22-demo-placeholder span{font-size:11px;letter-spacing:.14em;color:#168ba8}.gm22-complete-actions{display:flex;flex-wrap:wrap;justify-content:center;gap:14px;margin-top:22px}.gm22-secondary-btn{border-color:#75838d!important;background:#e7edf0!important;color:#17212b!important}
    .gm22-info{display:flex;justify-content:space-between;width:min(900px,88vw);margin:0 auto;color:#526b78}.gm22-board{display:grid;grid-template-columns:repeat(3,1fr);gap:clamp(10px,2vw,24px);width:min(900px,88vw);height:min(430px,48vh);margin:clamp(12px,2vh,24px) auto 10px}.gm22-rod{position:relative;min-width:0;padding:16px 8px 22px;overflow:hidden;border:2px solid #cad7dd;border-radius:22px;background:#f9fbfc;transition:border-color .12s,box-shadow .12s}.gm22-rod:hover:not(:disabled){border-color:#75b7c5}.gm22-rod.is-selected{border-color:#2fa6bd;box-shadow:0 0 0 5px rgba(47,166,189,.17)}.gm22-pole{position:absolute;left:50%;bottom:20px;width:10px;height:82%;transform:translateX(-50%);border-radius:8px 8px 0 0;background:#6c7c84}.gm22-rod:after{content:"";position:absolute;left:7%;right:7%;bottom:14px;height:12px;border-radius:8px;background:#53646d}.gm22-stack{position:absolute;z-index:1;left:5%;right:5%;bottom:26px;display:flex;flex-direction:column-reverse;align-items:center}.gm22-disk{display:block;height:clamp(24px,4.2vh,42px);margin-top:3px;border:2px solid rgba(23,33,43,.18);border-radius:12px;box-shadow:0 4px 8px rgba(20,35,45,.12)}.gm22-hint{margin:6px 0;color:#587180}.gm22-status{min-height:1.5em;margin:5px 0}.gm22-status.is-correct{color:#16835c;font-weight:700}.gm22-status.is-wrong{color:#b34c54;font-weight:700}
    @media(max-height:700px){.gm22-demo-placeholder{min-height:80px}.gm22-board{height:min(300px,43vh)}.gm22-disk{height:clamp(18px,3.6vh,30px)}}
  `;
  container.append(style);
  return () => { active = false; };
}

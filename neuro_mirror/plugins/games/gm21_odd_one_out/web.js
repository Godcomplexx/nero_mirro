const TRAINING_CHOICES = [
  { id: "cat", image: "cat.png" },
  { id: "dog", image: "dog.png" },
  { id: "apple", image: "apple.png", odd: true },
  { id: "bear", image: "bear.png" },
];

export function mount({ container, definition, api, close }) {
  const trainingSets = {
    "животные": [{ id: "cat", image: "cat.png" }, { id: "dog", image: "dog.png" }, { id: "apple", image: "apple.png", odd: true }, { id: "bear", image: "bear.png" }],
    "продукты": [{ id: "apple", image: "apple.png" }, { id: "bread", image: "bread.png" }, { id: "cat", image: "cat.png", odd: true }, { id: "carrot", image: "carrot.png" }],
    "инструменты": [{ id: "scissors", image: "scissors.png" }, { id: "key", image: "key.png" }, { id: "apple", image: "apple.png", odd: true }, { id: "pencil", image: "pencil.png" }],
  };
  const trainingChoices = trainingSets[String(definition.selected_stimulus_set || "").toLowerCase()] || TRAINING_CHOICES;
  container.innerHTML = `
    <header class="game-header-new"><div><p class="game-kicker-new mono">АБСТРАКЦИЯ</p><h2>${definition.title}</h2><p data-instruction>Найдите предмет, который не относится к общей группе.</p></div><div class="game-progress-new" data-progress>Инструкция</div></header>
    <main class="game-stage-new gm21 is-instruction-stage">
      <section class="gm21-tutorial" data-tutorial>
        <h3>Как выполнять задание</h3>
        <ol><li>Внимательно рассмотрите все четыре изображения.</li><li>Определите, что объединяет большинство предметов.</li><li>Нажмите на изображение, которое не подходит к остальным.</li></ol>
        <div class="gm21-demo-placeholder"><span class="mono">ПРИМЕР ВЫПОЛНЕНИЯ</span><strong>Видеоинструкция появится здесь</strong></div>
        <button type="button" class="icon-btn primary-btn" data-start-training><span>Перейти к тренировке</span></button>
      </section>
      <section class="gm21-training" data-training hidden><h3>Тренировочный пример</h3><p>Найдите одно лишнее изображение.</p><div class="gm21-grid" data-training-grid></div><p class="gm21-status" data-training-status aria-live="polite"></p></section>
      <section class="gm21-complete" data-complete hidden><h3>Обучение завершено</h3><p>Вы правильно нашли лишний предмет. Закончить обучение и начать игру?</p><div class="gm21-complete-actions"><button type="button" class="icon-btn gm21-secondary-btn" data-repeat><span>Повторить обучение</span></button><button type="button" class="icon-btn primary-btn" data-start><span>Да, начать игру</span></button></div></section>
      <section class="gm21-game" data-game hidden><div class="gm21-grid" data-grid></div><p class="gm21-status" data-status aria-live="polite"></p></section>
      <section class="game-result-new" data-result hidden><h3>Игра завершена</h3><p>Задание завершено. Результат сохранён.</p><button type="button" class="icon-btn primary-btn" data-restart><span>Ещё раз</span></button></section>
    </main>
    <footer class="game-actions-new"><button type="button" class="icon-btn" data-close><span>К выбору игр</span></button></footer>`;

  const q = (selector) => container.querySelector(selector);
  const stage = q(".gm21");
  const instruction = q("[data-instruction]");
  const progress = q("[data-progress]");
  const tutorial = q("[data-tutorial]");
  const training = q("[data-training]");
  const complete = q("[data-complete]");
  const game = q("[data-game]");
  const result = q("[data-result]");
  const trainingGrid = q("[data-training-grid]");
  const trainingStatus = q("[data-training-status]");
  const grid = q("[data-grid]");
  const status = q("[data-status]");
  const start = q("[data-start]");
  const restart = q("[data-restart]");
  const sections = [tutorial, training, complete, game, result];
  let state = null;
  let active = true;
  let busy = false;
  let trainingBusy = false;

  function showOnly(section) {
    sections.forEach((item) => { item.hidden = item !== section; });
    stage.classList.toggle("is-instruction-stage", section === tutorial);
  }

  function createCard(choice, onClick) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "gm21-card";
    card.setAttribute("aria-label", "Выбрать изображение");
    const image = document.createElement("img");
    image.src = `/game-assets/objects/${choice.image}`;
    image.alt = "";
    card.append(image);
    card.onclick = () => onClick(choice, card);
    return card;
  }

  function setDisabled(target, disabled) {
    target.querySelectorAll("button").forEach((card) => { card.disabled = disabled; });
  }

  function beginTraining() {
    trainingBusy = false;
    trainingStatus.textContent = "";
    trainingStatus.className = "gm21-status";
    trainingGrid.replaceChildren(...trainingChoices.map((choice) => createCard(choice, answerTraining)));
    instruction.textContent = "Найдите изображение, которое не подходит к остальным.";
    progress.textContent = "2. Тренировочный пример";
    showOnly(training);
  }

  function answerTraining(choice, card) {
    if (trainingBusy) return;
    if (!choice.odd) {
      card.classList.add("is-wrong");
      trainingStatus.textContent = "Этот предмет подходит к общей группе. Попробуйте ещё раз.";
      trainingStatus.className = "gm21-status is-wrong";
      window.setTimeout(() => card.classList.remove("is-wrong"), 450);
      return;
    }
    trainingBusy = true;
    setDisabled(trainingGrid, true);
    card.classList.add("is-correct");
    trainingStatus.textContent = "Верно";
    trainingStatus.className = "gm21-status is-correct";
    window.setTimeout(() => {
      if (!active) return;
      progress.textContent = "Обучение завершено";
      instruction.textContent = "Пробное задание выполнено правильно.";
      showOnly(complete);
    }, 650);
  }

  function render(payload) {
    if (!active) return;
    state = payload;
    busy = false;
    progress.textContent = payload.bonus ? "Дополнительное задание" : `Задание ${payload.trial_number} из ${payload.required_trials}`;
    instruction.textContent = "Выберите изображение, которое не относится к общей категории.";
    status.textContent = "";
    status.className = "gm21-status";
    grid.replaceChildren(...payload.choices.map((choice) => createCard(choice, (_item, card) => answer(choice.id, card))));
    showOnly(game);
    if (typeof payload.previous_correct === "boolean") {
      busy = true;
      setDisabled(grid, true);
      status.textContent = payload.previous_correct ? "Верно" : "Это изображение подходит к группе";
      status.className = `gm21-status ${payload.previous_correct ? "is-correct" : "is-wrong"}`;
      window.setTimeout(() => {
        if (!active) return;
        status.textContent = "";
        status.className = "gm21-status";
        setDisabled(grid, false);
        busy = false;
      }, 550);
    }
  }

  async function answer(selectedId, card) {
    if (busy || !state) return;
    busy = true;
    setDisabled(grid, true);
    card.classList.add("is-selected");
    try {
      const next = await api.answer({ session_id: state.session_id, selected_id: selectedId });
      if (!active) return;
      if (!next.finished) return render(next);
      progress.textContent = "Завершено";
      instruction.textContent = "Все задания выполнены.";
      restart.disabled = false;
      showOnly(result);
    } catch (error) {
      status.textContent = error.message;
      status.className = "gm21-status is-wrong";
      card.classList.remove("is-selected");
      setDisabled(grid, false);
      busy = false;
    }
  }

  async function beginGame() {
    busy = true;
    start.disabled = true;
    restart.disabled = true;
    showOnly(game);
    grid.replaceChildren();
    status.textContent = "Подготавливаю задание…";
    progress.textContent = "Подготовка";
    try {
      render(await api.start());
    } catch (error) {
      instruction.textContent = `Не удалось начать игру: ${error.message}`;
      start.disabled = false;
      restart.disabled = false;
      showOnly(complete);
    }
  }

  q("[data-start-training]").onclick = beginTraining;
  q("[data-repeat]").onclick = beginTraining;
  start.onclick = beginGame;
  restart.onclick = beginGame;
  q("[data-close]").onclick = () => { active = false; close(); };

  const style = document.createElement("style");
  style.textContent = `
    .gm21{display:grid;place-items:center;text-align:center;overflow:hidden;padding:clamp(10px,2vh,22px)}.gm21.is-instruction-stage{align-items:start;overflow-y:auto}.gm21-tutorial,.gm21-training,.gm21-complete,.gm21-game{width:min(780px,96%)}.gm21-tutorial[hidden],.gm21-training[hidden],.gm21-complete[hidden],.gm21-game[hidden]{display:none}
    .gm21-tutorial h3,.gm21-training h3,.gm21-complete h3{margin:0 0 14px;color:#17212b}.gm21-tutorial ol{width:min(650px,92%);margin:0 auto 18px;padding-left:24px;text-align:left;color:#617180;line-height:1.55}.gm21-demo-placeholder{min-height:clamp(120px,22vh,210px);margin:0 auto 18px;display:grid;place-content:center;gap:8px;border:2px dashed #bdd2dc;border-radius:18px;background:#edf4f6;color:#607482}.gm21-demo-placeholder span{font-size:11px;letter-spacing:.14em;color:#168ba8}
    .gm21-training>p,.gm21-complete>p{color:#617180}.gm21-complete-actions{display:flex;flex-wrap:wrap;justify-content:center;gap:14px;margin-top:22px}.gm21-secondary-btn{border-color:#75838d!important;background:#e7edf0!important;color:#17212b!important}
    .gm21-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:clamp(12px,2vh,22px);width:min(660px,65vh,82vw);margin:clamp(10px,2vh,22px) auto}.gm21-card{display:grid;place-items:center;aspect-ratio:1;padding:8%;border:2px solid #c5d4dc;border-radius:24px;background:#fff;box-shadow:0 8px 18px rgba(20,35,45,.08);transition:border-color .12s,box-shadow .12s,background .12s}.gm21-card:hover:not(:disabled){border-color:#73b9c8;box-shadow:0 10px 22px rgba(20,35,45,.12)}.gm21-card.is-selected{border-color:#2fa6bd;box-shadow:0 0 0 5px rgba(47,166,189,.18)}.gm21-card.is-correct{border-color:#16835c;background:#e6f6ef}.gm21-card.is-wrong{border-color:#b34c54;background:#fbeaec}.gm21-card img{width:84%;height:84%;object-fit:contain;pointer-events:none}.gm21-status{min-height:1.5em}.gm21-status.is-correct{color:#16835c;font-weight:700}.gm21-status.is-wrong{color:#b34c54;font-weight:700}
    @media(max-height:700px){.gm21-demo-placeholder{min-height:90px}.gm21-grid{width:min(480px,58vh,82vw);gap:8px}.gm21-card{border-radius:16px}}
  `;
  container.append(style);
  return () => { active = false; };
}

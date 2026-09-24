export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">АБСТРАКЦИЯ</p>
        <h2>${definition.title}</h2>
        <p>Выберите изображение, которое не относится к общей категории остальных.</p>
      </div>
    </header>
    <main class="game-stage-new gm21">
      <p class="gm21-progress" data-progress></p>
      <div class="gm21-grid" data-grid></div>
      <p class="gm21-status" data-status aria-live="polite"></p>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const progress = container.querySelector("[data-progress]");
  const grid = container.querySelector("[data-grid]");
  const status = container.querySelector("[data-status]");
  let state = null;
  let active = true;
  let busy = false;

  function setCardsDisabled(disabled) {
    [...grid.children].forEach((card) => { card.disabled = disabled; });
  }

  function render(payload) {
    if (!active) return;
    state = payload;
    busy = false;
    progress.textContent = payload.bonus
      ? "Дополнительное задание"
      : `Задание ${payload.trial_number} из ${payload.required_trials}`;
    status.textContent = "";
    grid.replaceChildren();
    payload.choices.forEach((choice) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "gm21-card";
      card.setAttribute("aria-label", "Выбрать изображение");
      const image = document.createElement("img");
      image.src = `/game-assets/objects/${choice.image}`;
      image.alt = "";
      card.append(image);
      card.onclick = () => answer(choice.id, card);
      grid.append(card);
    });

    if (typeof payload.previous_correct === "boolean") {
      busy = true;
      setCardsDisabled(true);
      status.textContent = payload.previous_correct ? "Верно" : "Это изображение подходит к группе";
      status.className = `gm21-status ${payload.previous_correct ? "is-correct" : "is-wrong"}`;
      setTimeout(() => {
        if (!active) return;
        status.textContent = "";
        status.className = "gm21-status";
        setCardsDisabled(false);
        busy = false;
      }, 550);
    }
  }

  async function answer(selectedId, card) {
    if (busy) return;
    busy = true;
    setCardsDisabled(true);
    card.classList.add("is-selected");
    try {
      const next = await api.answer({
        session_id: state.session_id,
        selected_id: selectedId,
      });
      if (!active) return;
      if (next.finished) {
        grid.replaceChildren();
        progress.textContent = "Готово";
        status.textContent = "Задание завершено. Результат сохранён.";
        status.className = "gm21-status is-correct";
        return;
      }
      render(next);
    } catch (error) {
      status.textContent = error.message;
      card.classList.remove("is-selected");
      setCardsDisabled(false);
      busy = false;
    }
  }

  container.querySelector("[data-close]").onclick = () => {
    active = false;
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm21 { text-align: center; }
    .gm21-progress { color: #587180; }
    .gm21-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: clamp(12px, 2vh, 22px);
      width: min(660px, 72vh, 82vw);
      margin: clamp(10px, 2vh, 22px) auto;
    }
    .gm21-card {
      display: grid;
      place-items: center;
      aspect-ratio: 1;
      padding: 8%;
      border: 2px solid #c5d4dc;
      border-radius: 24px;
      background: #fff;
      box-shadow: 0 8px 18px rgba(20, 35, 45, .08);
      transition: border-color .12s, box-shadow .12s;
    }
    .gm21-card:hover { border-color: #73b9c8; box-shadow: 0 10px 22px rgba(20, 35, 45, .12); }
    .gm21-card.is-selected { border-color: #2fa6bd; box-shadow: 0 0 0 5px rgba(47, 166, 189, .18); }
    .gm21-card img { width: 84%; height: 84%; object-fit: contain; pointer-events: none; }
    .gm21-status { min-height: 1.5em; }
    .gm21-status.is-correct { color: #16835c; }
    .gm21-status.is-wrong { color: #b34c54; }
  `;
  container.append(style);
  api.start().then(render);

  return () => { active = false; };
}

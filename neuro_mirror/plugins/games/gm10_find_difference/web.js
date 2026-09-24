export function mount({ container, definition, api, close }) {
  container.innerHTML = `<header class="game-header-new"><div><p class="game-kicker-new mono">ВНИМАНИЕ</p><h2>${definition.title}</h2><p>Сравните картинки. Все ответы отмечайте только на нижней картинке.</p></div></header><main class="game-stage-new gm10"><p data-progress></p><div class="gm10-pair"><div class="gm10-reference"><span class="gm10-label">ОБРАЗЕЦ · НЕ НАЖИМАТЬ</span><img data-left alt="Исходное изображение"></div><div class="gm10-target"><span class="gm10-label gm10-label-active">ИЩИТЕ И НАЖИМАЙТЕ ЗДЕСЬ</span><img data-right alt="Изменённое изображение"><div data-marks></div></div></div><p data-status></p></main><footer class="game-actions-new"><button data-close class="icon-btn"><span>К выбору игр</span></button></footer>`;
  const left = container.querySelector("[data-left]");
  const right = container.querySelector("[data-right]");
  const marks = container.querySelector("[data-marks]");
  const progress = container.querySelector("[data-progress]");
  const status = container.querySelector("[data-status]");
  let state = null;
  let locked = false;

  function render(payload) {
    state = payload;
    locked = false;
    left.src = `/game-assets/differences/${payload.left}`;
    right.src = `/game-assets/differences/${payload.right}`;
    marks.replaceChildren();
    progress.textContent = `${payload.scene} · уровень ${payload.scene_number} из ${payload.scene_count}`;
    status.textContent = `Найдено ${payload.found.length} из ${payload.difference_count}`;
  }

  right.onclick = async event => {
    if (locked) return;
    const rect = right.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    const payload = await api.answer({ session_id: state.session_id, x, y });
    if (payload.finished) {
      locked = true;
      container.querySelector(".gm10-pair").remove();
      progress.textContent = "Завершено";
      status.textContent = `Найдено отличий: ${Math.round(payload.metrics.a07_found_difference_rate * 100)}%`;
      return;
    }
    if (payload.scene_complete) {
      locked = true;
      status.textContent = "Уровень завершён";
      setTimeout(() => render(payload), 650);
      return;
    }
    if (payload.correct) {
      const mark = document.createElement("span");
      mark.className = "gm10-mark";
      mark.style.left = `${x * 100}%`;
      mark.style.top = `${y * 100}%`;
      marks.append(mark);
    } else {
      status.textContent = "Здесь отличия нет";
    }
    setTimeout(() => {
      if (!locked) status.textContent = `Найдено ${payload.found.length} из ${payload.difference_count}`;
    }, 500);
  };

  container.querySelector("[data-close]").onclick = close;
  const style = document.createElement("style");
  style.textContent = `.gm10{display:flex!important;flex-direction:column;align-items:center;justify-content:flex-start;gap:6px;text-align:center;padding:8px!important;overflow:hidden!important}.gm10>p{flex:0 0 auto;margin:2px 0}.gm10-pair{flex:1 1 auto;min-height:0;width:100%;display:grid;grid-template-rows:minmax(0,1fr) minmax(0,1fr);justify-items:center;align-items:stretch;gap:8px}.gm10-reference,.gm10-target{position:relative;height:100%;min-height:0;width:fit-content;max-width:100%;padding-top:20px}.gm10-reference img,.gm10-target img{display:block;height:calc(100% - 20px);min-height:0;width:auto;max-width:100%;object-fit:contain;border-radius:12px;border:1px solid #b8c8d1}.gm10-target img{border:3px solid #38a9c7;box-shadow:0 0 0 4px rgba(56,169,199,.14)}.gm10-label{position:absolute;top:0;left:50%;transform:translateX(-50%);white-space:nowrap;font:700 11px/16px var(--font-mono,monospace);letter-spacing:.12em;color:#687783}.gm10-label-active{color:#167d9b}.gm10-target>[data-marks]{position:absolute;left:0;right:0;top:20px;bottom:0;pointer-events:none}.gm10-mark{position:absolute;width:clamp(28px,3vw,44px);height:clamp(28px,3vw,44px);transform:translate(-50%,-50%);border:4px solid #e84252;border-radius:50%;box-shadow:0 0 0 3px #fff8}`;
  container.append(style);
  api.start().then(render);
}

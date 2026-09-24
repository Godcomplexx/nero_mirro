export function mount({ container, definition, api, close }) {
  container.innerHTML = `<header class="game-header-new"><div><p class="game-kicker-new mono">ПАМЯТЬ</p><h2>${definition.title}</h2><p>Открывайте по две карточки и находите одинаковые пары.</p></div></header><main class="game-stage-new dynamic-memory-game"><p data-progress></p><div data-board class="gm01-board"></div><p data-result></p></main><footer class="game-actions-new"><button type="button" data-close class="icon-btn"><span>К выбору игр</span></button></footer>`;
  const board = container.querySelector("[data-board]");
  const progress = container.querySelector("[data-progress]");
  const result = container.querySelector("[data-result]");
  let state = null, locked = false, shownAt = performance.now();
  const files={"Часы":"clock.png","Телефон":"phone.png","Ножницы":"scissors.png","Карандаш":"pencil.png","Зонт":"umbrella.png","Ключ":"key.png","Конверт":"convert.png","Лампа":"lamp.png","Весы":"scales.png","Чашка":"cup.png","Собака":"dog.png","Кошка":"cat.png","Мышь":"mouse.png","Кролик":"rabbit.png","Лиса":"fox.png","Медведь":"bear.png","Панда":"panda.png","Лягушка":"frog.png","Обезьяна":"monkey.png","Лев":"lion.png","Яблоко":"apple.png","Груша":"pear.png","Апельсин":"orange.png","Лимон":"lemon.png","Арбуз":"watermelon.png","Виноград":"grapes.png","Клубника":"strawberry.png","Морковь":"carrot.png","Кукуруза":"corn.png","Помидор":"tomato.png"};
  const visual = name => `<img class="gm-object-image" src="/game-assets/objects/${files[name]}" alt=""><small>${name}</small>`;
  const render = payload => {
    state = payload; locked = false; shownAt = performance.now();
    progress.textContent = `Поле ${payload.board} из ${payload.board_count}`;
    board.replaceChildren(...payload.cards.map((symbol, index) => {
      const button = document.createElement("button"); button.type="button"; button.className="gm01-card";
      button.innerHTML = payload.matched.includes(index) ? visual(symbol) : "?";
      button.disabled = payload.matched.includes(index);
      button.onclick = () => choose(index, button, symbol);
      return button;
    }));
  };
  const choose = async (index, button, symbol) => {
    if (locked || button.disabled) return;
    button.innerHTML = visual(symbol); button.disabled = true;
    const payload = await api.answer({session_id: state.session_id, selected_index: index, reaction_ms: performance.now()-shownAt});
    if (payload.first_pick) { state = payload; return; }
    locked = true;
    if (payload.finished) { board.replaceChildren(); progress.textContent = "Завершено"; result.textContent = `Ошибок: ${payload.metrics.u07_error_count}`; return; }
    setTimeout(() => render(payload), payload.correct ? 250 : 800);
  };
  container.querySelector("[data-close]").onclick = close;
  const style = document.createElement("style"); style.textContent = `.dynamic-memory-game{text-align:center}.gm01-board{display:grid;grid-template-columns:repeat(5,minmax(90px,1fr));gap:16px;margin:20px auto}.gm01-card{min-height:120px;border:1px solid #b8c8d1;border-radius:18px;background:#fff;font-size:38px;color:#17212b;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;box-shadow:0 8px 22px rgba(20,35,45,.08)}.gm01-card:hover:not(:disabled){border-color:#38a9c7;transform:translateY(-2px)}.gm01-card small{font-size:12px}.gm-object-image{width:72px;height:72px;object-fit:contain}`; container.append(style);
  api.start().then(render);
  return () => { locked = true; };
}

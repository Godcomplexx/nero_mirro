export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new"><div><p class="game-kicker-new mono">ПАМЯТЬ</p><h2>${definition.title}</h2><p data-instruction>Открывайте по две карточки и находите одинаковые пары.</p></div><div class="game-progress-new" data-progress>Инструкция</div></header>
    <main class="game-stage-new gm01-stage is-instruction-stage" data-stage>
      <section class="gm01-instruction" data-intro><h3>Как выполнять задание</h3><ol><li>Откройте две закрытые карточки.</li><li>Запоминайте изображения и их расположение.</li><li>Найдите две карточки с одинаковым изображением.</li></ol><p class="gm01-example-title">Посмотрите пример</p><div class="gm01-media-placeholder" role="img" aria-label="Здесь будет видео-пример"><span aria-hidden="true">▶</span><strong>Здесь будет GIF с примером</strong><small>Визуальная инструкция будет добавлена позже</small></div><button type="button" class="icon-btn primary-btn" data-start-training><span>Перейти к тренировке</span></button></section>
      <section class="gm01-training" data-training hidden><h3>Тренировочный пример</h3><p>Откройте карточки и найдите одну одинаковую пару.</p><div class="gm01-board gm01-training-board" data-training-board></div><p class="gm01-feedback" data-training-feedback aria-live="polite"></p></section>
      <section class="game-intro-new gm01-training-complete" data-training-complete hidden><h3>Обучение завершено</h3><p>Вы нашли одинаковую пару. Повторить тренировку или начать игру?</p><div class="gm01-training-actions"><button type="button" class="icon-btn gm01-training-repeat" data-repeat-training><span>Повторить тренировку</span></button><button type="button" class="icon-btn primary-btn" data-confirm-start><span>Начать игру</span></button></div></section>
      <section class="gm01-game" data-game hidden><div data-board class="gm01-board"></div><p data-result></p></section>
    </main>
    <footer class="game-actions-new"><button type="button" data-close class="icon-btn"><span>К выбору игр</span></button></footer>`;

  const stage=container.querySelector("[data-stage]"), instruction=container.querySelector("[data-instruction]"), progress=container.querySelector("[data-progress]");
  const intro=container.querySelector("[data-intro]"), training=container.querySelector("[data-training]"), trainingBoard=container.querySelector("[data-training-board]");
  const trainingFeedback=container.querySelector("[data-training-feedback]"), trainingComplete=container.querySelector("[data-training-complete]");
  const game=container.querySelector("[data-game]"), board=container.querySelector("[data-board]"), result=container.querySelector("[data-result]");
  let state=null, locked=false, shownAt=performance.now(), trainingPicks=[], active=true;
  const timers=new Set();
  const later=(callback,delay)=>{const timer=setTimeout(()=>{timers.delete(timer);callback();},delay);timers.add(timer);};
  const files={"Часы":"clock.png","Телефон":"phone.png","Ножницы":"scissors.png","Карандаш":"pencil.png","Зонт":"umbrella.png","Ключ":"key.png","Конверт":"convert.png","Лампа":"lamp.png","Весы":"scales.png","Чашка":"cup.png","Книга":"book.png","Мыло":"soap.png","Собака":"dog.png","Кошка":"cat.png","Мышь":"mouse.png","Кролик":"rabbit.png","Лиса":"fox.png","Медведь":"bear.png","Панда":"panda.png","Лягушка":"frog.png","Обезьяна":"monkey.png","Лев":"lion.png","Лошадь":"horse.png","Слон":"elephant.png","Яблоко":"apple.png","Груша":"pear.png","Апельсин":"orange.png","Лимон":"lemon.png","Арбуз":"watermelon.png","Виноград":"grapes.png","Клубника":"strawberry.png","Морковь":"carrot.png","Кукуруза":"corn.png","Помидор":"tomato.png","Огурец":"cucumber.png","Капуста":"cabbage.png"};
  const visual=name=>`<img class="gm-object-image" src="/game-assets/objects/${files[name]}" alt=""><small>${name}</small>`;
  const showOnly=target=>[intro,training,trainingComplete,game].forEach(section=>{section.hidden=section!==target;});

  function beginTraining(){
    stage.classList.remove("is-instruction-stage");showOnly(training);progress.textContent="Тренировка";instruction.textContent="Найдите две одинаковые карточки.";
    trainingFeedback.textContent="";trainingFeedback.className="gm01-feedback";trainingPicks=[];locked=false;
    const cards=["Собака","Яблоко","Собака","Яблоко"];
    trainingBoard.replaceChildren(...cards.map((symbol,index)=>{const button=document.createElement("button");button.type="button";button.className="gm01-card";button.textContent="?";button.onclick=()=>chooseTraining(index,symbol,button);return button;}));
  }
  function chooseTraining(index,symbol,button){
    if(!active||locked||button.disabled)return;button.innerHTML=visual(symbol);button.disabled=true;trainingPicks.push({index,symbol,button});if(trainingPicks.length<2)return;
    locked=true;const [first,second]=trainingPicks;
    if(first.symbol===second.symbol){first.button.classList.add("is-matched");second.button.classList.add("is-matched");trainingFeedback.textContent="Верно, пара найдена.";trainingFeedback.classList.add("is-correct");later(()=>{if(!active)return;showOnly(trainingComplete);progress.textContent="Обучение завершено";instruction.textContent="Тренировочный пример выполнен правильно.";},450);return;}
    trainingFeedback.textContent="Карточки разные. Запомните их и попробуйте ещё раз.";trainingFeedback.classList.add("is-wrong");later(()=>{if(!active)return;first.button.textContent="?";second.button.textContent="?";first.button.disabled=false;second.button.disabled=false;trainingPicks=[];locked=false;trainingFeedback.textContent="";trainingFeedback.className="gm01-feedback";},800);
  }
  const render=payload=>{if(!active)return;state=payload;locked=false;shownAt=performance.now();progress.textContent=`Уровень ${payload.board} из ${payload.board_count} · ${payload.pair_count} пар`;board.style.setProperty("--gm01-columns",String(payload.grid_columns||5));board.replaceChildren(...payload.cards.map((symbol,index)=>{const button=document.createElement("button");button.type="button";button.className="gm01-card";button.innerHTML=payload.matched.includes(index)?visual(symbol):"?";button.disabled=payload.matched.includes(index);button.onclick=()=>choose(index,button,symbol);return button;}));};
  // Показанная пара, ожидающая закрытия. Пока она висит, прежний код
  // отбрасывал нажатия: человеку казалось, что игра подлагивает.
  let pendingReveal=null;
  const settlePending=()=>{if(!pendingReveal)return;clearTimeout(pendingReveal.timer);timers.delete(pendingReveal.timer);const payload=pendingReveal.payload;pendingReveal=null;render(payload);};
  const choose=async(index,button,symbol)=>{
    // Нажатие на следующую карточку закрывает показанную пару сразу и
    // засчитывается, а не теряется в ожидании паузы.
    if(pendingReveal){settlePending();const fresh=board.children[index];if(fresh&&!fresh.disabled)fresh.click();return;}
    if(locked||button.disabled)return;
    button.innerHTML=visual(symbol);button.disabled=true;
    // Замок ставится до обращения к ядру: иначе за время ответа принимается
    // ещё одно нажатие, и открытыми оказываются три карточки.
    locked=true;
    let payload;
    try{payload=await api.answer({session_id:state.session_id,selected_index:index,reaction_ms:performance.now()-shownAt});}
    catch(error){if(active){locked=false;button.disabled=false;button.innerHTML="?";result.textContent=`Не удалось проверить ход: ${error.message}`;}return;}
    if(!active)return;
    if(payload.first_pick){state=payload;locked=false;return;}
    if(payload.finished){board.replaceChildren();progress.textContent="Завершено";result.textContent=`Ошибок: ${payload.metrics.u07_error_count}`;return;}
    const timer=setTimeout(()=>{timers.delete(timer);pendingReveal=null;render(payload);},payload.correct?250:800);
    timers.add(timer);
    pendingReveal={timer,payload};
  };
  async function beginGame(){locked=true;showOnly(game);progress.textContent="Подготовка…";instruction.textContent="Открывайте по две карточки и находите одинаковые пары.";result.textContent="";try{render(await api.start());}catch(error){result.textContent=`Не удалось начать игру: ${error.message}`;}}

  container.querySelector("[data-start-training]").onclick=beginTraining;container.querySelector("[data-repeat-training]").onclick=beginTraining;container.querySelector("[data-confirm-start]").onclick=beginGame;
  container.querySelector("[data-close]").onclick=()=>{active=false;close();};
  const style=document.createElement("style");style.textContent=`
    .gm01-stage{text-align:center;overflow:hidden}.gm01-stage.is-instruction-stage{align-items:start;padding-top:clamp(14px,2.4vh,30px)}.gm01-instruction,.gm01-training{width:min(800px,100%)}.gm01-instruction h3,.gm01-training h3{margin:0 0 10px;font-size:clamp(19px,2.3vw,25px)}
    .gm01-instruction ol{width:min(700px,100%);margin:0 auto 16px;padding-left:28px;color:#52606d;text-align:left;font-size:clamp(14px,1.6vw,18px);line-height:1.4}.gm01-instruction li+li{margin-top:5px}.gm01-example-title{margin:0 0 7px;font-weight:700}
    .gm01-media-placeholder{box-sizing:border-box;display:flex;width:min(620px,100%);height:clamp(130px,22vh,230px);margin:0 auto 18px;flex-direction:column;align-items:center;justify-content:center;gap:7px;border:2px dashed #b8cbd5;border-radius:16px;background:#eaf1f4;color:#52606d}.gm01-media-placeholder>span{display:grid;width:46px;height:46px;place-items:center;padding-left:3px;border-radius:50%;background:#d3e2e9;color:#168ba8;font-size:20px}.gm01-media-placeholder strong{color:#263744}
    .gm01-training>p{margin:0 0 14px;color:#52606d}.gm01-game{width:100%}.gm01-board{display:grid;grid-template-columns:repeat(var(--gm01-columns,5),minmax(70px,1fr));gap:clamp(8px,1.3vh,14px);width:min(900px,100%);margin:clamp(8px,1.5vh,18px) auto}.gm01-training-board{--gm01-columns:2;width:min(400px,80vw)}
    .gm01-card{min-height:clamp(78px,11vh,116px);border:1px solid #b8c8d1;border-radius:18px;background:#fff;font-size:38px;color:#17212b;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;box-shadow:0 8px 22px rgba(20,35,45,.08)}.gm01-card:hover:not(:disabled){border-color:#38a9c7;transform:translateY(-2px)}.gm01-card.is-matched{border:3px solid #1d9b69;background:#e4f7ef}.gm01-card small{font-size:11px}.gm-object-image{width:clamp(46px,7vh,68px);height:clamp(46px,7vh,68px);object-fit:contain}
    .gm01-feedback{min-height:1.4em;margin:8px 0 0!important}.gm01-feedback.is-correct{color:#167950}.gm01-feedback.is-wrong{color:#b33443}.gm01-training-actions{display:flex;justify-content:center;gap:12px;flex-wrap:wrap}.gm01-training-repeat{border-color:#60727d;background:#fff;color:#17212b}.gm01-training-repeat span{color:#17212b}.gm01-instruction[hidden],.gm01-training[hidden],.gm01-training-complete[hidden],.gm01-game[hidden]{display:none}
    @media(max-width:700px){.gm01-board{grid-template-columns:repeat(4,minmax(58px,1fr))}.gm01-training-board{grid-template-columns:repeat(2,minmax(58px,1fr))}.gm01-card{min-height:78px}}@media(max-height:700px){.gm01-stage.is-instruction-stage{padding-top:8px}.gm01-instruction ol{margin-bottom:7px;font-size:13px;line-height:1.25}.gm01-media-placeholder{height:clamp(100px,18vh,140px);margin-bottom:8px}}
  `;container.append(style);
  return()=>{active=false;locked=true;timers.forEach(timer=>clearTimeout(timer));timers.clear();};
}

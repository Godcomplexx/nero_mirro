export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new"><div><p class="game-kicker-new mono">ПАМЯТЬ</p><h2>${definition.title}</h2><p data-instruction>Запомните предметы и их расположение.</p></div><div class="game-progress-new" data-progress>Инструкция</div></header>
    <main class="game-stage-new gm03-stage is-instruction-stage" data-stage>
      <section class="gm03-intro" data-intro><h3>Как выполнять задание</h3><ol><li>Запомните предметы и клетки, в которых они находятся.</li><li>После того как предметы исчезнут, прочитайте вопрос.</li><li>Нажмите клетку, в которой находился названный предмет.</li></ol><p class="gm03-example-title">Посмотрите пример</p><div class="gm03-media-placeholder"><span aria-hidden="true">▶</span><strong>Здесь будет GIF с примером</strong><small>Визуальная инструкция будет добавлена позже</small></div><button type="button" class="icon-btn primary-btn" data-start-training><span>Перейти к тренировке</span></button></section>
      <section class="gm03-training" data-training hidden><h3>Тренировочный пример</h3><p data-training-info></p><div class="gm03-grid" data-training-grid></div><p data-training-timer></p></section>
      <section class="game-intro-new gm03-training-complete" data-training-complete hidden><h3>Обучение завершено</h3><p>Вы правильно указали расположение предмета.</p><div class="gm03-training-actions"><button type="button" class="icon-btn gm03-training-repeat" data-repeat-training><span>Повторить тренировку</span></button><button type="button" class="icon-btn primary-btn" data-confirm-start><span>Начать игру</span></button></div></section>
      <section class="gm03-game" data-game hidden><p data-info></p><div data-grid class="gm03-grid"></div><p data-timer></p></section>
    </main>
    <footer class="game-actions-new"><button type="button" data-close class="icon-btn"><span>К выбору игр</span></button></footer>`;

  const stage=container.querySelector("[data-stage]"), instruction=container.querySelector("[data-instruction]"), progress=container.querySelector("[data-progress]");
  const intro=container.querySelector("[data-intro]"), training=container.querySelector("[data-training]"), trainingGrid=container.querySelector("[data-training-grid]");
  const trainingInfo=container.querySelector("[data-training-info]"), trainingTimer=container.querySelector("[data-training-timer]"), trainingComplete=container.querySelector("[data-training-complete]");
  const game=container.querySelector("[data-game]"), grid=container.querySelector("[data-grid]"), info=container.querySelector("[data-info]"), timer=container.querySelector("[data-timer]");
  let active=true, phaseToken=0;
  const timers=new Set(), intervals=new Set();
  const later=(callback,delay)=>{const id=setTimeout(()=>{timers.delete(id);callback();},delay);timers.add(id);};
  const files={"Чайник":"kettle.png","Чашка":"cup.png","Яблоко":"apple.png","Ложка":"spoon.png","Хлеб":"bread.png","Морковь":"carrot.png","Кукуруза":"corn.png","Лимон":"lemon.png","Апельсин":"orange.png","Виноград":"grapes.png","Мыло":"soap.png","Щётка":"toothbrush.png","Полотенце":"towel.png","Расчёска":"comb.png","Губка":"sponge.png","Шампунь":"shampoo.png","Зубная паста":"toothpaste.png","Зеркало":"mirror.png","Фен":"hairdryer.png","Бритва":"razor.png","Лампа":"lamp.png","Книга":"book.png","Часы":"clock.png","Цветок":"flower.png","Телефон":"phone.png","Диван":"sofa.png","Кресло":"armchair.png","Телевизор":"television.png","Ваза":"vase.png","Пульт":"remote.png"};
  const visual=name=>`<img class="gm03-image" src="/game-assets/objects/${files[name]}" alt=""><small>${name}</small>`;
  const cells=()=>Array.from({length:16},(_,i)=>{const button=document.createElement("button");button.type="button";button.className="gm03-cell";button.dataset.cell=i;return button;});
  const showOnly=target=>[intro,training,trainingComplete,game].forEach(section=>{section.hidden=section!==target;});

  function clearRunningTimers(){timers.forEach(id=>clearTimeout(id));timers.clear();intervals.forEach(id=>clearInterval(id));intervals.clear();}
  function beginTraining(){
    clearRunningTimers();const token=++phaseToken;stage.classList.remove("is-instruction-stage");showOnly(training);progress.textContent="Тренировка";instruction.textContent="Запомните предметы и их расположение.";
    trainingGrid.replaceChildren(...cells());const objects=[{name:"Чайник",cell:1},{name:"Яблоко",cell:6},{name:"Чашка",cell:11}];objects.forEach(object=>{trainingGrid.children[object.cell].innerHTML=visual(object.name);});
    trainingInfo.textContent="Запомните, где находятся три предмета.";let left=4;trainingTimer.textContent=`Запоминайте: ${left}`;
    const id=setInterval(()=>{if(!active||token!==phaseToken){clearInterval(id);intervals.delete(id);return;}left-=1;trainingTimer.textContent=`Запоминайте: ${left}`;if(left<=0){clearInterval(id);intervals.delete(id);beginTrainingRecall(token,objects);}},1000);intervals.add(id);
  }
  function beginTrainingRecall(token,objects){
    if(!active||token!==phaseToken)return;trainingGrid.replaceChildren(...cells());trainingInfo.textContent="Где находилось яблоко? Нажмите нужную клетку.";trainingTimer.textContent="";const expected=objects.find(object=>object.name==="Яблоко").cell;
    [...trainingGrid.children].forEach((button,index)=>{button.onclick=()=>{if(button.disabled)return;if(index===expected){[...trainingGrid.children].forEach(item=>item.disabled=true);button.innerHTML=visual("Яблоко");button.classList.add("is-correct");trainingTimer.textContent="Верно.";later(()=>{if(!active||token!==phaseToken)return;showOnly(trainingComplete);progress.textContent="Обучение завершено";instruction.textContent="Тренировочный пример выполнен правильно.";},450);return;}button.classList.add("is-wrong");button.disabled=true;trainingTimer.textContent="Неверная клетка. Попробуйте ещё раз.";later(()=>{if(!active||token!==phaseToken)return;button.classList.remove("is-wrong");button.disabled=false;},500);};});
  }

  async function render(payload){
    if(!active)return;grid.replaceChildren(...cells());info.textContent=`${payload.room} · сцена ${payload.room_number} из ${payload.room_count}`;timer.textContent="";
    if(payload.phase==="study"){
      payload.objects.forEach(object=>{grid.children[object.cell].innerHTML=visual(object.name);grid.children[object.cell].title=object.name;});let left=payload.study_seconds;timer.textContent=`Запоминайте: ${left}`;const token=phaseToken;
      const id=setInterval(async()=>{if(!active||token!==phaseToken){clearInterval(id);intervals.delete(id);return;}left-=1;timer.textContent=`Запоминайте: ${left}`;if(left<=0){clearInterval(id);intervals.delete(id);try{await render(await api.answer({session_id:payload.session_id,action:"begin_recall"}));}catch(error){info.textContent=`Не удалось продолжить: ${error.message}`;}}},1000);intervals.add(id);return;
    }
    info.textContent=`Где находился предмет «${payload.target.name}»?`;[...grid.children].forEach((button,index)=>button.onclick=async()=>{if(button.disabled)return;[...grid.children].forEach(item=>item.disabled=true);
      // Выбранная клетка отмечается сразу, а после ответа ядра показывается,
      // верна ли она: без отклика человек не понимал, принято ли нажатие, и
      // жал ещё раз.
      button.classList.add("is-selected");
      try{const next=await api.answer({session_id:payload.session_id,selected_cell:index});if(!active)return;button.classList.remove("is-selected");button.classList.add(next.correct?"is-correct":"is-wrong");info.textContent=next.correct?"Верно.":"Это другая клетка.";if(next.finished){later(()=>{if(!active)return;grid.replaceChildren();info.textContent=`Завершено. Правильных ответов: ${Math.round(next.metrics.u01_correct_action_rate*100)}%`;},600);return;}later(()=>render(next),600);}catch(error){button.classList.remove("is-selected");info.textContent=`Не удалось проверить ответ: ${error.message}`;}});
  }
  async function beginGame(){clearRunningTimers();phaseToken+=1;showOnly(game);progress.textContent="Подготовка…";instruction.textContent="Запомните предметы и их расположение.";try{await render(await api.start());}catch(error){info.textContent=`Не удалось начать игру: ${error.message}`;}}

  container.querySelector("[data-start-training]").onclick=beginTraining;container.querySelector("[data-repeat-training]").onclick=beginTraining;container.querySelector("[data-confirm-start]").onclick=beginGame;
  container.querySelector("[data-close]").onclick=()=>{active=false;phaseToken+=1;clearRunningTimers();close();};
  const style=document.createElement("style");style.textContent=`
    .gm03-stage{text-align:center;overflow:hidden}.gm03-stage.is-instruction-stage{align-items:start;padding-top:clamp(14px,2.4vh,30px)}.gm03-intro,.gm03-training,.gm03-game{width:min(800px,100%)}.gm03-intro h3,.gm03-training h3{margin:0 0 10px;font-size:clamp(19px,2.3vw,25px)}.gm03-intro ol{width:min(700px,100%);margin:0 auto 16px;padding-left:28px;color:#52606d;text-align:left;font-size:clamp(14px,1.6vw,18px);line-height:1.4}.gm03-intro li+li{margin-top:5px}.gm03-example-title{margin:0 0 7px;font-weight:700}
    .gm03-media-placeholder{box-sizing:border-box;display:flex;width:min(620px,100%);height:clamp(130px,22vh,230px);margin:0 auto 18px;flex-direction:column;align-items:center;justify-content:center;gap:7px;border:2px dashed #b8cbd5;border-radius:16px;background:#eaf1f4;color:#52606d}.gm03-media-placeholder>span{display:grid;width:46px;height:46px;place-items:center;border-radius:50%;background:#d3e2e9;color:#168ba8}.gm03-media-placeholder strong{color:#263744}
    .gm03-training>p,.gm03-game>p{margin:0 0 10px;color:#52606d}.gm03-grid{display:grid;grid-template-columns:repeat(4,minmax(70px,120px));gap:clamp(8px,1.3vh,14px);justify-content:center;margin:clamp(10px,2vh,24px) auto}.gm03-cell{height:clamp(76px,11vh,120px);border:1px solid #b8c8d1;border-radius:16px;background:#fff;color:#17212b;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px}.gm03-cell:hover:not(:disabled){border-color:#38a9c7}.gm03-cell.is-selected{border:3px solid #38a9c7;background:#eaf6fa}.gm03-cell.is-correct{border:3px solid #1d9b69;background:#e4f7ef}.gm03-cell.is-wrong{border:3px solid #d64b59;background:#fdebed}.gm03-cell small{font-size:12px}.gm03-image{width:clamp(48px,7vh,78px);height:clamp(48px,7vh,78px);object-fit:contain}
    .gm03-training-actions{display:flex;justify-content:center;gap:12px;flex-wrap:wrap}.gm03-training-repeat{border-color:#60727d;background:#fff;color:#17212b}.gm03-training-repeat span{color:#17212b}.gm03-intro[hidden],.gm03-training[hidden],.gm03-training-complete[hidden],.gm03-game[hidden]{display:none}@media(max-height:700px){.gm03-stage.is-instruction-stage{padding-top:8px}.gm03-intro ol{margin-bottom:7px;font-size:13px;line-height:1.25}.gm03-media-placeholder{height:clamp(100px,18vh,140px);margin-bottom:8px}.gm03-grid{gap:7px;margin:7px auto}.gm03-cell{height:70px}}
  `;container.append(style);
  return()=>{active=false;phaseToken+=1;clearRunningTimers();};
}

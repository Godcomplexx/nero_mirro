const TRAINING_RECORDING_MS = 4500;

export function mount({ container, definition, api, close }) {
  const trainingSets = {
    "животные": { words: ["Кошка", "Собака", "Лошадь"], answer: /(?:^|\s)(?:животн(?:ое|ые)|звер(?:ь|и))(?:$|\s)/i },
    "фрукты": { words: ["Яблоко", "Груша", "Слива"], answer: /(?:^|\s)фрукт(?:ы|ами|ов)?(?:$|\s)/i },
    "овощи": { words: ["Морковь", "Свёкла", "Капуста"], answer: /(?:^|\s)овощ(?:и|ами|ей)?(?:$|\s)/i },
    "транспорт": { words: ["Автобус", "Трамвай", "Поезд"], answer: /(?:^|\s)транспорт(?:ом|а|ные средства)?(?:$|\s)/i },
    "мебель": { words: ["Стол", "Стул", "Шкаф"], answer: /(?:^|\s)мебел(?:ь|и)(?:$|\s)/i },
    "инструменты": { words: ["Молоток", "Пила", "Отвёртка"], answer: /(?:^|\s)инструмент(?:ы|ами|ов)?(?:$|\s)/i },
    "одежда": { words: ["Рубашка", "Брюки", "Куртка"], answer: /(?:^|\s)одежд(?:а|ы|ой)(?:$|\s)/i },
  };
  const trainingSet = trainingSets[String(definition.selected_stimulus_set || "").toLowerCase()] || trainingSets["фрукты"];
  container.innerHTML = `
    <header class="game-header-new"><div><p class="game-kicker-new mono">АБСТРАКЦИЯ</p><h2>${definition.title}</h2><p data-instruction>Определите, что объединяет три слова, и назовите общую категорию.</p></div><div class="game-progress-new" data-progress>Инструкция</div></header>
    <main class="game-stage-new gm24 is-instruction-stage">
      <section class="gm24-tutorial" data-tutorial><h3>Как выполнять задание</h3><ol><li>Прочитайте три слова.</li><li>Определите общую категорию, к которой они относятся.</li><li>Нажмите «Назвать категорию».</li><li>После звукового сигнала чётко произнесите название категории.</li></ol><div class="gm24-demo-placeholder"><span class="mono">ПРИМЕР ВЫПОЛНЕНИЯ</span><strong>Видеоинструкция появится здесь</strong></div><button type="button" class="icon-btn primary-btn" data-start-training><span>Перейти к тренировке</span></button></section>
      <section class="gm24-training" data-training hidden><h3>Тренировочный пример</h3><p>Определите общую категорию этих слов и назовите её вслух.</p><div class="gm24-words" data-training-words></div><button type="button" class="icon-btn primary-btn" data-training-record><span>Назвать категорию</span></button><div class="gm24-recording" data-training-recording hidden aria-label="Идёт запись"><span></span><span></span><span></span><span></span><span></span></div><p class="gm24-status" data-training-status aria-live="polite"></p></section>
      <section class="gm24-complete" data-complete hidden><h3>Обучение завершено</h3><p>Категория названа правильно. Закончить обучение и начать игру?</p><div class="gm24-complete-actions"><button type="button" class="icon-btn gm24-secondary-btn" data-repeat><span>Повторить обучение</span></button><button type="button" class="icon-btn primary-btn" data-start><span>Да, начать игру</span></button></div></section>
      <section class="gm24-game" data-game hidden><div class="gm24-words" data-words></div><button type="button" class="icon-btn primary-btn" data-record><span>Назвать категорию</span></button><div class="gm24-recording" data-recording hidden aria-label="Идёт запись"><span></span><span></span><span></span><span></span><span></span></div><p class="gm24-status" data-status aria-live="polite"></p></section>
      <section class="game-result-new" data-result hidden><h3>Игра завершена</h3><p>Все ответы сохранены.</p><button type="button" class="icon-btn primary-btn" data-restart><span>Ещё раз</span></button></section>
    </main><footer class="game-actions-new"><button type="button" class="icon-btn" data-close><span>К выбору игр</span></button></footer>`;

  const q = (selector) => container.querySelector(selector);
  const stage = q(".gm24");
  const instruction = q("[data-instruction]");
  const progress = q("[data-progress]");
  const tutorial = q("[data-tutorial]");
  const training = q("[data-training]");
  const complete = q("[data-complete]");
  const game = q("[data-game]");
  const result = q("[data-result]");
  const trainingRecord = q("[data-training-record]");
  const trainingWords = q("[data-training-words]");
  const trainingRecording = q("[data-training-recording]");
  const trainingStatus = q("[data-training-status]");
  const words = q("[data-words]");
  const record = q("[data-record]");
  const recording = q("[data-recording]");
  const status = q("[data-status]");
  const start = q("[data-start]");
  const restart = q("[data-restart]");
  const sections = [tutorial, training, complete, game, result];
  let state = null;
  let stream = null;
  let recorder = null;
  let active = true;
  let busy = false;

  function showOnly(section) {
    sections.forEach((item) => { item.hidden = item !== section; });
    stage.classList.toggle("is-instruction-stage", section === tutorial);
  }

  function stopStream() {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }

  async function beep() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const context = new AudioContextClass();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 700;
    gain.gain.value = 0.15;
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.16);
    await new Promise((resolve) => window.setTimeout(resolve, 220));
    await context.close();
  }

  async function transcribe(chunks, mime) {
    const form = new FormData();
    form.append("audio", new Blob(chunks, { type: mime }), "category-name.webm");
    const response = await fetch("/api/speech/transcribe?assistant=false", { method: "POST", body: form });
    const speech = await response.json();
    return { transcript: String(speech.transcript || ""), recognized: Boolean(speech.accepted && speech.transcript) };
  }

  async function submitRecording(mode, chunks, mime) {
    stopStream();
    if (!active) return;
    const isTraining = mode === "training";
    const activeRecording = isTraining ? trainingRecording : recording;
    const activeStatus = isTraining ? trainingStatus : status;
    activeRecording.hidden = true;
    activeStatus.textContent = "Распознаю…";
    activeStatus.className = "gm24-status";
    let transcript = "";
    let recognized = false;
    try {
      ({ transcript, recognized } = await transcribe(chunks, mime));
    } catch (error) {
      activeStatus.textContent = `Не удалось распознать запись: ${error.message}`;
    }
    if (isTraining) {
      busy = false;
      trainingRecord.hidden = false;
      trainingRecord.disabled = false;
      const correct = trainingSet.answer.test(transcript.trim());
      if (!recognized || !correct) {
        activeStatus.textContent = recognized ? `Распознано: «${transcript}». Попробуйте назвать общую категорию ещё раз.` : "Ответ не распознан. Попробуйте ещё раз.";
        activeStatus.className = "gm24-status is-wrong";
        return;
      }
      activeStatus.textContent = `Верно: «${transcript}»`;
      activeStatus.className = "gm24-status is-correct";
      trainingRecord.hidden = true;
      window.setTimeout(() => {
        if (!active) return;
        progress.textContent = "Обучение завершено";
        instruction.textContent = "Пробная категория названа правильно.";
        showOnly(complete);
      }, 700);
      return;
    }
    try {
      const next = await api.answer({ session_id: state.session_id, transcript, recognized, duration_ms: state.recording_ms });
      if (!active) return;
      if (!next.finished) {
        render(next);
        if (!recognized) {
          status.textContent = "Ответ не распознан. Можно продолжать.";
          status.className = "gm24-status";
        }
        return;
      }
      busy = false;
      restart.disabled = false;
      progress.textContent = "Завершено";
      instruction.textContent = "Все категории названы.";
      showOnly(result);
    } catch (error) {
      status.textContent = error.message;
      status.className = "gm24-status is-wrong";
      record.disabled = false;
      record.hidden = false;
      busy = false;
    }
  }

  async function startRecording(mode) {
    if (busy || !active) return;
    busy = true;
    const isTraining = mode === "training";
    const button = isTraining ? trainingRecord : record;
    const activeRecording = isTraining ? trainingRecording : recording;
    const activeStatus = isTraining ? trainingStatus : status;
    const duration = isTraining ? TRAINING_RECORDING_MS : state.recording_ms;
    button.disabled = true;
    activeStatus.textContent = "Приготовьтесь…";
    activeStatus.className = "gm24-status";
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
      const chunks = [];
      recorder = new MediaRecorder(stream, { mimeType: mime });
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => submitRecording(mode, chunks, mime);
      recorder.start();
      button.hidden = true;
      await beep();
      if (!active || recorder.state !== "recording") return;
      activeRecording.hidden = false;
      activeStatus.textContent = "Говорите";
      window.setTimeout(() => { if (recorder && recorder.state === "recording") recorder.stop(); }, duration);
    } catch (error) {
      stopStream();
      activeStatus.textContent = `Не удалось включить микрофон: ${error.message}`;
      activeStatus.className = "gm24-status is-wrong";
      button.disabled = false;
      button.hidden = false;
      busy = false;
    }
  }

  function beginTraining() {
    busy = false;
    trainingRecord.hidden = false;
    trainingRecord.disabled = false;
    trainingRecording.hidden = true;
    trainingStatus.textContent = "";
    trainingStatus.className = "gm24-status";
    trainingWords.replaceChildren(...trainingSet.words.map((word) => {
      const card = document.createElement("div");
      card.className = "gm24-word";
      card.textContent = word;
      return card;
    }));
    progress.textContent = "2. Тренировочный пример";
    instruction.textContent = "Назовите общую категорию трёх слов.";
    showOnly(training);
  }

  function render(payload) {
    if (!active) return;
    state = payload;
    progress.textContent = `Задание ${payload.trial_number} из ${payload.trial_count}`;
    instruction.textContent = "Определите и назовите общую категорию слов.";
    words.replaceChildren(...payload.words.map((word) => {
      const card = document.createElement("div");
      card.className = "gm24-word";
      card.textContent = word;
      return card;
    }));
    record.disabled = false;
    record.hidden = false;
    recording.hidden = true;
    status.textContent = typeof payload.previous_correct === "boolean" ? (payload.previous_correct ? "Верно" : "Ответ записан") : "";
    status.className = `gm24-status ${payload.previous_correct ? "is-correct" : ""}`;
    busy = false;
    showOnly(game);
  }

  async function beginGame() {
    busy = true;
    start.disabled = true;
    restart.disabled = true;
    progress.textContent = "Подготовка";
    instruction.textContent = "Подготавливаю слова…";
    showOnly(game);
    words.replaceChildren();
    record.hidden = true;
    try { render(await api.start()); }
    catch (error) { instruction.textContent = `Не удалось начать игру: ${error.message}`; start.disabled = false; restart.disabled = false; busy = false; showOnly(complete); }
  }

  q("[data-start-training]").onclick = beginTraining;
  q("[data-repeat]").onclick = beginTraining;
  trainingRecord.onclick = () => startRecording("training");
  record.onclick = () => startRecording("game");
  start.onclick = beginGame;
  restart.onclick = beginGame;
  q("[data-close]").onclick = () => { active = false; if (recorder && recorder.state === "recording") recorder.stop(); stopStream(); close(); };

  const style = document.createElement("style");
  style.textContent = `
    .gm24{display:grid;place-items:center;text-align:center;overflow:hidden;padding:clamp(10px,2vh,22px)}.gm24.is-instruction-stage{align-items:start;overflow-y:auto}.gm24-tutorial,.gm24-training,.gm24-complete,.gm24-game{width:min(940px,96%)}.gm24-tutorial[hidden],.gm24-training[hidden],.gm24-complete[hidden],.gm24-game[hidden]{display:none}.gm24-tutorial h3,.gm24-training h3,.gm24-complete h3{margin:0 0 14px;color:#17212b}.gm24-tutorial ol{width:min(680px,92%);margin:0 auto 18px;padding-left:24px;text-align:left;color:#617180;line-height:1.55}.gm24-demo-placeholder{min-height:clamp(120px,20vh,190px);margin:0 auto 18px;display:grid;place-content:center;gap:8px;border:2px dashed #bdd2dc;border-radius:18px;background:#edf4f6;color:#607482}.gm24-demo-placeholder span{font-size:11px;letter-spacing:.14em;color:#168ba8}.gm24-complete-actions{display:flex;flex-wrap:wrap;justify-content:center;gap:14px;margin-top:22px}.gm24-secondary-btn{border-color:#75838d!important;background:#e7edf0!important;color:#17212b!important}
    .gm24-words{display:grid;grid-template-columns:repeat(3,1fr);gap:clamp(12px,2vw,24px);width:min(880px,88vw);margin:clamp(18px,4vh,48px) auto}.gm24-word{display:grid;place-items:center;min-height:clamp(120px,21vh,210px);padding:18px;border:2px solid #c4d4dc;border-radius:24px;background:#fff;color:#17212b;font-size:clamp(22px,3.2vw,38px);font-weight:650;box-shadow:0 10px 22px rgba(20,35,45,.08)}.gm24-status{min-height:1.5em}.gm24-status.is-correct{color:#16835c;font-weight:700}.gm24-status.is-wrong{color:#b34c54;font-weight:700}.gm24-recording{height:44px;color:#2fa6bd}.gm24-recording span{display:inline-block;width:8px;height:32px;margin:0 4px;border-radius:8px;background:currentColor;animation:gm24-wave .8s ease-in-out infinite alternate}.gm24-recording span:nth-child(2),.gm24-recording span:nth-child(4){animation-delay:-.3s}.gm24-recording span:nth-child(3){animation-delay:-.55s}@keyframes gm24-wave{to{transform:scaleY(.3);opacity:.5}}
    @media(max-height:700px){.gm24-demo-placeholder{min-height:80px}.gm24-words{margin:12px auto}.gm24-word{min-height:95px}}@media(max-width:700px){.gm24-words{gap:8px}.gm24-word{min-height:105px;padding:8px;font-size:clamp(17px,5vw,24px)}}
  `;
  container.append(style);
  return () => { active = false; if (recorder && recorder.state === "recording") recorder.stop(); stopStream(); };
}

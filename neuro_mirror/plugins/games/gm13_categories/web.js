export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">РЕЧЬ</p>
        <h2>${definition.title}</h2>
        <p>После сигнала называйте как можно больше слов указанной категории.</p>
      </div>
    </header>
    <main class="game-stage-new gm13">
      <p class="gm13-step mono" data-step></p>
      <h3 data-category></h3>
      <p class="gm13-prompt" data-prompt></p>
      <div class="gm13-recording" data-recording hidden>
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <button type="button" class="icon-btn primary-btn" data-start>
        <span>Начать блок</span>
      </button>
      <p class="gm13-status" data-status aria-live="polite"></p>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const step = container.querySelector("[data-step]");
  const category = container.querySelector("[data-category]");
  const prompt = container.querySelector("[data-prompt]");
  const start = container.querySelector("[data-start]");
  const status = container.querySelector("[data-status]");
  const recording = container.querySelector("[data-recording]");
  let state = null;
  let stream = null;
  let recorder = null;
  let active = true;
  let busy = false;

  function render(payload) {
    state = payload;
    step.textContent = `БЛОК ${payload.block_number} ИЗ ${payload.block_count}`;
    category.textContent = payload.category;
    prompt.textContent = payload.prompt;
    start.querySelector("span").textContent = payload.block_number === 1
      ? "Начать задание"
      : "Начать следующий блок";
    start.disabled = false;
    start.hidden = false;
    recording.hidden = true;
    status.textContent = "";
    busy = false;
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
    await new Promise((resolve) => setTimeout(resolve, 220));
    await context.close();
  }

  function stopStream() {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }

  async function submitRecording(chunks, mime, durationMs) {
    stopStream();
    if (!active) return;
    recording.hidden = true;
    status.textContent = "Распознаю ответы…";
    let transcript = "";
    let recognized = false;
    try {
      const form = new FormData();
      form.append("audio", new Blob(chunks, { type: mime }), "category.webm");
      const response = await fetch("/api/speech/transcribe?assistant=false", {
        method: "POST",
        body: form,
      });
      const speech = await response.json();
      transcript = String(speech.transcript || "");
      recognized = Boolean(speech.accepted && transcript);
    } catch (error) {
      status.textContent = `Не удалось распознать запись: ${error.message}`;
    }

    try {
      const next = await api.answer({
        session_id: state.session_id,
        transcript,
        recognized,
        duration_ms: durationMs,
      });
      if (!active) return;
      if (next.finished) {
        category.textContent = "Готово";
        prompt.textContent = "Задание завершено";
        step.textContent = "ВСЕ БЛОКИ ПРОЙДЕНЫ";
        status.textContent = recognized
          ? "Ответы сохранены"
          : "Последняя запись не распознана, остальные ответы сохранены";
        start.hidden = true;
        busy = false;
        return;
      }
      render(next);
      if (!recognized) status.textContent = "Запись не распознана. Переходим к следующей категории.";
    } catch (error) {
      status.textContent = error.message;
      start.disabled = false;
      start.hidden = false;
      busy = false;
    }
  }

  start.onclick = async () => {
    if (busy || !active) return;
    busy = true;
    start.disabled = true;
    status.textContent = "Подготавливаю микрофон…";
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const chunks = [];
      recorder = new MediaRecorder(stream, { mimeType: mime });
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = () => submitRecording(chunks, mime, state.duration_ms);
      recorder.start();
      start.hidden = true;
      await beep();
      if (!active || recorder.state !== "recording") return;
      status.textContent = "Говорите до окончания записи";
      recording.hidden = false;
      setTimeout(() => {
        if (recorder && recorder.state === "recording") recorder.stop();
      }, state.duration_ms);
    } catch (error) {
      stopStream();
      status.textContent = `Не удалось включить микрофон: ${error.message}`;
      start.disabled = false;
      start.hidden = false;
      busy = false;
    }
  };

  container.querySelector("[data-close]").onclick = () => {
    active = false;
    if (recorder && recorder.state === "recording") recorder.stop();
    stopStream();
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm13 { text-align: center; }
    .gm13-step { color: #587180; letter-spacing: .16em; }
    .gm13 h3 {
      margin: clamp(12px, 2vh, 24px) 0;
      color: #17212b;
      font-size: clamp(54px, 11vh, 112px);
      line-height: 1;
    }
    .gm13-prompt { font-size: clamp(18px, 2.4vw, 28px); }
    .gm13-status { min-height: 1.5em; }
    .gm13-recording {
      height: 54px;
      margin: 24px auto;
      color: #2fa6bd;
    }
    .gm13-recording span {
      display: inline-block;
      width: 8px;
      height: 32px;
      margin: 0 4px;
      border-radius: 8px;
      background: currentColor;
      animation: gm13-wave .8s ease-in-out infinite alternate;
    }
    .gm13-recording span:nth-child(2), .gm13-recording span:nth-child(4) { animation-delay: -.3s; }
    .gm13-recording span:nth-child(3) { animation-delay: -.55s; }
    @keyframes gm13-wave { to { transform: scaleY(.35); opacity: .55; } }
  `;
  container.append(style);
  api.start().then(render);

  return () => {
    active = false;
    if (recorder && recorder.state === "recording") recorder.stop();
    stopStream();
  };
}

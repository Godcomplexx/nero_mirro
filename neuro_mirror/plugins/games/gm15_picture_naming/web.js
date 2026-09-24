export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">РЕЧЬ</p>
        <h2>${definition.title}</h2>
        <p>После сигнала быстро назовите изображённый предмет.</p>
      </div>
    </header>
    <main class="game-stage-new gm15">
      <div class="gm15-meta">
        <span data-category></span><span data-progress></span>
      </div>
      <div class="gm15-card"><img data-image alt=""></div>
      <button type="button" class="icon-btn primary-btn" data-record>
        <span>Ответить голосом</span>
      </button>
      <div class="gm15-recording" data-recording hidden aria-label="Идёт запись">
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <p data-status class="gm15-status" aria-live="polite"></p>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const category = container.querySelector("[data-category]");
  const progress = container.querySelector("[data-progress]");
  const image = container.querySelector("[data-image]");
  const record = container.querySelector("[data-record]");
  const recording = container.querySelector("[data-recording]");
  const status = container.querySelector("[data-status]");
  let state = null;
  let stream = null;
  let recorder = null;
  let active = true;
  let busy = false;

  function render(payload) {
    state = payload;
    category.textContent = payload.category;
    progress.textContent = `${payload.item_number} из ${payload.item_count}`;
    image.src = `/game-assets/objects/${payload.image}`;
    record.disabled = false;
    record.hidden = false;
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

  async function submit(chunks, mime) {
    stopStream();
    if (!active) return;
    recording.hidden = true;
    status.textContent = "Распознаю…";
    let transcript = "";
    let recognized = false;
    try {
      const form = new FormData();
      form.append("audio", new Blob(chunks, { type: mime }), "picture-name.webm");
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
        duration_ms: state.recording_ms,
      });
      if (!active) return;
      if (next.finished) {
        category.textContent = "Готово";
        progress.textContent = "";
        image.hidden = true;
        record.hidden = true;
        status.textContent = "Задание завершено. Ответы сохранены.";
        busy = false;
        return;
      }
      render(next);
      if (!recognized) status.textContent = "Ответ не распознан. Можно продолжать.";
    } catch (error) {
      status.textContent = error.message;
      record.disabled = false;
      record.hidden = false;
      busy = false;
    }
  }

  record.onclick = async () => {
    if (busy || !active) return;
    busy = true;
    record.disabled = true;
    status.textContent = "Приготовьтесь…";
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
      recorder.onstop = () => submit(chunks, mime);
      recorder.start();
      record.hidden = true;
      await beep();
      if (!active || recorder.state !== "recording") return;
      recording.hidden = false;
      status.textContent = "Говорите";
      setTimeout(() => {
        if (recorder && recorder.state === "recording") recorder.stop();
      }, state.recording_ms);
    } catch (error) {
      stopStream();
      status.textContent = `Не удалось включить микрофон: ${error.message}`;
      record.disabled = false;
      record.hidden = false;
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
    .gm15 { text-align: center; }
    .gm15-meta {
      display: flex;
      justify-content: space-between;
      width: min(420px, 78vw);
      margin: 0 auto 12px;
      color: #587180;
    }
    .gm15-card {
      display: grid;
      place-items: center;
      width: min(420px, 55vh, 76vw);
      aspect-ratio: 1;
      margin: 0 auto 18px;
      border: 1px solid #c7d5dc;
      border-radius: 28px;
      background: #fff;
    }
    .gm15-card img { width: 76%; height: 76%; object-fit: contain; }
    .gm15-status { min-height: 1.5em; }
    .gm15-recording { height: 40px; color: #2fa6bd; }
    .gm15-recording span {
      display: inline-block;
      width: 7px;
      height: 28px;
      margin: 0 3px;
      border-radius: 7px;
      background: currentColor;
      animation: gm15-wave .75s ease-in-out infinite alternate;
    }
    .gm15-recording span:nth-child(2), .gm15-recording span:nth-child(4) { animation-delay: -.3s; }
    .gm15-recording span:nth-child(3) { animation-delay: -.5s; }
    @keyframes gm15-wave { to { transform: scaleY(.3); opacity: .5; } }
  `;
  container.append(style);
  api.start().then(render);

  return () => {
    active = false;
    if (recorder && recorder.state === "recording") recorder.stop();
    stopStream();
  };
}

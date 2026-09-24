export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">РЕЧЬ</p>
        <h2>${definition.title}</h2>
        <p>Назовите как можно больше разных слов, начинающихся с указанной буквы.</p>
      </div>
    </header>
    <main class="game-stage-new gm16">
      <p class="gm16-label mono">ВАША БУКВА</p>
      <strong data-letter></strong>
      <p>После сигнала говорите до автоматического завершения записи.</p>
      <button type="button" class="icon-btn primary-btn" data-start>
        <span>Начать задание</span>
      </button>
      <div class="gm16-recording" data-recording hidden aria-label="Идёт запись">
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <p class="gm16-status" data-status aria-live="polite"></p>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const letter = container.querySelector("[data-letter]");
  const start = container.querySelector("[data-start]");
  const recording = container.querySelector("[data-recording]");
  const status = container.querySelector("[data-status]");
  let state = null;
  let stream = null;
  let recorder = null;
  let active = true;
  let busy = false;

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
    status.textContent = "Распознаю ответы…";
    let transcript = "";
    let recognized = false;
    try {
      const form = new FormData();
      form.append("audio", new Blob(chunks, { type: mime }), "phonemic-fluency.webm");
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
      await api.answer({
        session_id: state.session_id,
        transcript,
        recognized,
        duration_ms: state.recording_ms,
      });
      if (!active) return;
      letter.textContent = "Готово";
      status.textContent = recognized
        ? "Задание завершено. Ответы сохранены."
        : "Задание завершено, но речь не была распознана.";
      busy = false;
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
      recorder.onstop = () => submit(chunks, mime);
      recorder.start();
      start.hidden = true;
      await beep();
      if (!active || recorder.state !== "recording") return;
      recording.hidden = false;
      status.textContent = "Говорите до окончания записи";
      setTimeout(() => {
        if (recorder && recorder.state === "recording") recorder.stop();
      }, state.recording_ms);
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
    .gm16 { text-align: center; }
    .gm16-label { color: #587180; letter-spacing: .16em; }
    .gm16 [data-letter] {
      display: grid;
      place-items: center;
      width: min(250px, 30vh, 58vw);
      aspect-ratio: 1;
      margin: clamp(10px, 2vh, 22px) auto;
      border: 2px solid #bfd0d8;
      border-radius: 30px;
      background: #fff;
      color: #17212b;
      font-size: clamp(90px, 18vh, 180px);
      line-height: 1;
    }
    .gm16-status { min-height: 1.5em; }
    .gm16-recording { height: 44px; margin: 12px auto; color: #2fa6bd; }
    .gm16-recording span {
      display: inline-block;
      width: 8px;
      height: 32px;
      margin: 0 4px;
      border-radius: 8px;
      background: currentColor;
      animation: gm16-wave .8s ease-in-out infinite alternate;
    }
    .gm16-recording span:nth-child(2), .gm16-recording span:nth-child(4) { animation-delay: -.3s; }
    .gm16-recording span:nth-child(3) { animation-delay: -.55s; }
    @keyframes gm16-wave { to { transform: scaleY(.3); opacity: .5; } }
  `;
  container.append(style);
  api.start().then((payload) => {
    state = payload;
    letter.textContent = payload.letter;
  });

  return () => {
    active = false;
    if (recorder && recorder.state === "recording") recorder.stop();
    stopStream();
  };
}

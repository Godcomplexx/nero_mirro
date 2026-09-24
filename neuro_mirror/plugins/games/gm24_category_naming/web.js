export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">АБСТРАКЦИЯ</p>
        <h2>${definition.title}</h2>
        <p>Определите, что объединяет три слова, и после сигнала назовите общую категорию.</p>
      </div>
    </header>
    <main class="game-stage-new gm24">
      <p class="gm24-progress" data-progress></p>
      <div class="gm24-words" data-words></div>
      <button type="button" class="icon-btn primary-btn" data-record>
        <span>Назвать категорию</span>
      </button>
      <div class="gm24-recording" data-recording hidden aria-label="Идёт запись">
        <span></span><span></span><span></span><span></span><span></span>
      </div>
      <p class="gm24-status" data-status aria-live="polite"></p>
    </main>
    <footer class="game-actions-new">
      <button type="button" class="icon-btn" data-close><span>К выбору игр</span></button>
    </footer>`;

  const progress = container.querySelector("[data-progress]");
  const words = container.querySelector("[data-words]");
  const record = container.querySelector("[data-record]");
  const recording = container.querySelector("[data-recording]");
  const status = container.querySelector("[data-status]");
  let state = null;
  let stream = null;
  let recorder = null;
  let active = true;
  let busy = false;

  function render(payload) {
    if (!active) return;
    state = payload;
    progress.textContent = `Задание ${payload.trial_number} из ${payload.trial_count}`;
    words.replaceChildren();
    payload.words.forEach((word) => {
      const card = document.createElement("div");
      card.className = "gm24-word";
      card.textContent = word;
      words.append(card);
    });
    record.disabled = false;
    record.hidden = false;
    recording.hidden = true;
    status.textContent = typeof payload.previous_correct === "boolean"
      ? (payload.previous_correct ? "Верно" : "Ответ записан")
      : "";
    status.className = `gm24-status ${payload.previous_correct ? "is-correct" : ""}`;
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
    status.className = "gm24-status";
    let transcript = "";
    let recognized = false;
    try {
      const form = new FormData();
      form.append("audio", new Blob(chunks, { type: mime }), "category-name.webm");
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
        words.replaceChildren();
        progress.textContent = "Готово";
        record.hidden = true;
        status.textContent = "Задание завершено. Ответы сохранены.";
        status.className = "gm24-status is-correct";
        busy = false;
        return;
      }
      render(next);
      if (!recognized) {
        status.textContent = "Ответ не распознан. Можно продолжать.";
        status.className = "gm24-status";
      }
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
    status.className = "gm24-status";
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
    .gm24 { text-align: center; }
    .gm24-progress { color: #587180; }
    .gm24-words {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: clamp(12px, 2vw, 24px);
      width: min(880px, 88vw);
      margin: clamp(24px, 5vh, 58px) auto;
    }
    .gm24-word {
      display: grid;
      place-items: center;
      min-height: clamp(120px, 21vh, 210px);
      padding: 18px;
      border: 2px solid #c4d4dc;
      border-radius: 24px;
      background: #fff;
      color: #17212b;
      font-size: clamp(22px, 3.2vw, 38px);
      font-weight: 650;
      box-shadow: 0 10px 22px rgba(20, 35, 45, .08);
    }
    .gm24-status { min-height: 1.5em; }
    .gm24-status.is-correct { color: #16835c; }
    .gm24-recording { height: 44px; color: #2fa6bd; }
    .gm24-recording span {
      display: inline-block;
      width: 8px;
      height: 32px;
      margin: 0 4px;
      border-radius: 8px;
      background: currentColor;
      animation: gm24-wave .8s ease-in-out infinite alternate;
    }
    .gm24-recording span:nth-child(2), .gm24-recording span:nth-child(4) { animation-delay: -.3s; }
    .gm24-recording span:nth-child(3) { animation-delay: -.55s; }
    @keyframes gm24-wave { to { transform: scaleY(.3); opacity: .5; } }
    @media (max-width: 700px) {
      .gm24-words { gap: 8px; }
      .gm24-word { min-height: 105px; padding: 8px; font-size: clamp(17px, 5vw, 24px); }
    }
  `;
  container.append(style);
  api.start().then(render);

  return () => {
    active = false;
    if (recorder && recorder.state === "recording") recorder.stop();
    stopStream();
  };
}

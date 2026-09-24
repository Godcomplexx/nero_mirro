export function mount({ container, definition, api, close }) {
  container.innerHTML = `
    <header class="game-header-new">
      <div>
        <p class="game-kicker-new mono">ВНИМАНИЕ</p>
        <h2>${definition.title}</h2>
        <p>После сигнала произнесите следующий результат вычисления.</p>
      </div>
    </header>
    <main class="game-stage-new gm11">
      <p data-rule></p>
      <strong data-number></strong>
      <p data-progress></p>
      <button type="button" data-record class="icon-btn primary-btn">
        <span>Ответить голосом</span>
      </button>
      <p data-status aria-live="polite"></p>
    </main>
    <footer class="game-actions-new">
      <button type="button" data-close class="icon-btn"><span>К выбору игр</span></button>
    </footer>`;

  const rule = container.querySelector("[data-rule]");
  const number = container.querySelector("[data-number]");
  const progress = container.querySelector("[data-progress]");
  const record = container.querySelector("[data-record]");
  const status = container.querySelector("[data-status]");
  let state = null;
  let busy = false;
  let active = true;
  let stream = null;

  function render(payload) {
    state = payload;
    rule.textContent = `${payload.instruction} · правило ${payload.rule_number} из ${payload.rule_count}`;
    number.textContent = payload.current;
    progress.textContent = `Правильных шагов: ${payload.correct_in_rule} из ${payload.required_correct}`;
    status.textContent = "";
    record.disabled = false;
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
      const recorder = new MediaRecorder(stream, { mimeType: mime });
      const chunks = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = async () => {
        stopStream();
        if (!active) return;
        status.textContent = "Распознаю…";
        const form = new FormData();
        form.append("audio", new Blob(chunks, { type: mime }), "answer.webm");
        try {
          const response = await fetch("/api/speech/transcribe?assistant=false", {
            method: "POST",
            body: form,
          });
          const speech = await response.json();
          if (!speech.accepted || !speech.transcript) {
            status.textContent = speech.message || "Речь не распознана. Повторите ответ.";
            record.disabled = false;
            busy = false;
            return;
          }
          const next = await api.answer({
            session_id: state.session_id,
            transcript: speech.transcript,
          });
          if (next.finished) {
            number.textContent = "Готово";
            progress.textContent = "Задание завершено";
            status.textContent = "Ответы сохранены";
            return;
          }
          status.textContent = next.correct
            ? `Верно: ${speech.transcript}`
            : `Распознано «${speech.transcript}». Попробуйте ещё раз.`;
          setTimeout(() => {
            if (!active) return;
            render(next);
            busy = false;
          }, 700);
        } catch (error) {
          status.textContent = error.message;
          record.disabled = false;
          busy = false;
        }
      };
      recorder.start();
      await beep();
      if (!active || recorder.state !== "recording") return;
      status.textContent = "Говорите";
      setTimeout(() => {
        if (recorder.state === "recording") recorder.stop();
      }, 3500);
    } catch (error) {
      stopStream();
      status.textContent = `Не удалось включить микрофон: ${error.message}`;
      record.disabled = false;
      busy = false;
    }
  };

  container.querySelector("[data-close]").onclick = () => {
    active = false;
    stopStream();
    close();
  };

  const style = document.createElement("style");
  style.textContent = `
    .gm11 { text-align: center; }
    .gm11 [data-number] {
      display: block;
      font-size: clamp(90px, 18vh, 190px);
      line-height: 1;
      color: #17212b;
    }
    .gm11 [data-rule] { font-size: clamp(20px, 3vw, 34px); }
    .gm11 [data-status] { min-height: 1.5em; }
  `;
  container.append(style);
  api.start().then(render);

  return () => {
    active = false;
    stopStream();
  };
}

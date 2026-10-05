// neuro_mirror/web/static/js/core/session-check.js
//
// Session-condition check before a test (ТЗ 6.3.2): camera, face + light,
// microphone + background noise, and a voice probe recorded by the server.
// Moved out of app.js unchanged in behaviour; it is UI-agnostic — callers
// get per-item updates through callbacks and render them however they like
// (the new screening screen, or the legacy #check-panel used by MoCA/HADS
// until their own stages).

import { api, cameraProblem, cameraVideo, ensureCamera, userConsents } from "./legacy.js";

export const CHECK_NAMES = ["camera", "face", "mic", "voice"];

const CHECK_REQUIREMENTS = {
  screening: { camera: true, face: true, mic: true, voice: true, required: ["camera", "face"] },
  moca: { camera: false, face: false, mic: true, voice: true, required: ["mic", "voice"] },
  // HADS можно пройти нажатием — микрофон желателен, но не обязателен
  hads: { camera: false, face: false, mic: true, voice: true, required: [] },
};

export function getCheckRequirements(scenario) {
  const base = CHECK_REQUIREMENTS[scenario] || CHECK_REQUIREMENTS.hads;
  if (userConsents().audio === false) {
    return {
      ...base,
      mic: false,
      voice: false,
      required: base.required.filter((item) => !["mic", "voice"].includes(item)),
    };
  }
  return base;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// onItem(name, state, note) — state is one of idle | wait | ok | warn | fail
// onStatus(text)            — one line of guidance under the list
export function createSessionCheck(scenario, { onItem = () => {}, onStatus = () => {} } = {}) {
  const requirements = getCheckRequirements(scenario);
  const results = {};
  let running = false;
  let audioStream = null;
  let audioCtx = null;
  let analyser = null;

  function setItem(name, checkState, note) {
    results[name] = { ...(results[name] || {}), state: checkState, note: note || "" };
    onItem(name, checkState, note || "");
  }

  const stateOf = (name, fallback = "idle") => (results[name] || {}).state || fallback;

  function stopAudio() {
    if (audioStream) {
      for (const track of audioStream.getTracks()) track.stop();
      audioStream = null;
    }
    if (audioCtx) {
      audioCtx.close().catch(() => {});
      audioCtx = null;
    }
    analyser = null;
  }

  function setupAnalyser(stream) {
    const AudioCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtor) return false;
    audioCtx = new AudioCtor();
    const source = audioCtx.createMediaStreamSource(stream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    return true;
  }

  async function measureRms(durationMs, mode) {
    if (!analyser) return 0;
    const buffer = new Uint8Array(analyser.fftSize);
    const samples = [];
    const deadline = Date.now() + durationMs;
    while (Date.now() < deadline) {
      analyser.getByteTimeDomainData(buffer);
      let sum = 0;
      for (const value of buffer) {
        const centered = (value - 128) / 128;
        sum += centered * centered;
      }
      samples.push(Math.sqrt(sum / buffer.length));
      await sleep(60);
    }
    if (samples.length === 0) return 0;
    if (mode === "peak") return Math.max(...samples);
    return samples.reduce((a, b) => a + b, 0) / samples.length;
  }

  function captureFrame() {
    const video = cameraVideo();
    if (!video || !video.videoWidth) return "";
    const width = Math.min(640, video.videoWidth);
    const height = Math.round(video.videoHeight * (width / video.videoWidth));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    canvas.getContext("2d").drawImage(video, 0, 0, width, height);
    return canvas.toDataURL("image/jpeg", 0.85);
  }

  async function checkCameraAndFace() {
    setItem("camera", "wait", "Включаю камеру...");
    let cameraOk = false;
    try {
      cameraOk = await ensureCamera();
    } catch (_) {
      // toggleCamera сам показывает ошибку
    }
    if (!cameraOk) {
      setItem("camera", "fail", cameraProblem() || "Камера недоступна. Проверьте подключение и повторите попытку.");
      setItem("face", "fail", "Без камеры проверить лицо и свет нельзя.");
      return;
    }
    setItem("camera", "ok", "Камера работает");

    setItem("face", "wait", "Смотрю на кадр...");
    // Пауза, чтобы автоэкспозиция камеры успела подстроиться
    await sleep(900);
    let data;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const frame = captureFrame();
      if (!frame) {
        setItem("face", "fail", "Не удалось получить кадр с камеры.");
        return;
      }
      try {
        const candidate = await api("/api/session/check-face", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ image_base64: frame }),
        });
        if (!data || candidate.face_detected || candidate.brightness > data.brightness) data = candidate;
        if (candidate.face_detected || candidate.detector_available === false) break;
        await sleep(250);
      } catch (error) {
        setItem(
          "face",
          "fail",
          "Проверка лица не запустилась. Перезапустите приложение, затем нажмите «Проверить снова»."
        );
        return;
      }
    }
    results.face = { ...(results.face || {}), data };

    const advice = (data.advice || []).join(" ");
    if (data.detector_available === false) {
      setItem(
        "face",
        "fail",
        advice || "Проверка лица не запустилась. Перезапустите приложение, затем нажмите «Проверить снова»."
      );
    } else if (data.face_detected && data.brightness_ok && data.face_close_enough) {
      setItem("face", "ok", advice || "Лицо видно, света достаточно");
    } else if (data.face_detected && data.brightness_ok) {
      // Только дистанция — предупреждение, не блокируем
      setItem("face", "warn", advice || "Приблизьтесь к экрану.");
    } else {
      setItem("face", "fail", advice || "Поправьте положение и освещение, затем проверьте снова.");
    }
  }

  async function checkMicAndNoise() {
    setItem("mic", "wait", "Проверяю микрофон...");
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      setItem("mic", "fail", "Микрофон недоступен. Проверьте подключение и разрешение в браузере.");
      setItem("voice", "fail", "Без микрофона проба голоса невозможна.");
      return;
    }
    audioStream = stream;
    if (!setupAnalyser(stream)) {
      setItem("mic", "warn", "Микрофон подключён, но замерить уровень звука не удалось.");
      return;
    }

    setItem("mic", "wait", "Побудьте в тишине — замеряю фоновый шум...");
    const noise = await measureRms(1800, "avg");
    results.mic = { ...(results.mic || {}), noise };

    if (noise < 0.025) {
      setItem("mic", "ok", "Микрофон работает, фон тихий");
    } else if (noise < 0.06) {
      setItem("mic", "warn", "Слышен фоновый шум — по возможности уберите его.");
    } else {
      setItem("mic", "warn", "Сильный фоновый шум — выключите телевизор или музыку.");
    }
  }

  async function checkVoiceSample() {
    if (!analyser) {
      if (stateOf("voice") !== "fail") {
        setItem("voice", "fail", "Проба голоса недоступна без микрофона.");
      }
      return;
    }
    for (let seconds = 3; seconds >= 1; seconds -= 1) {
      setItem("voice", "wait", `Приготовьтесь. Начинайте говорить через ${seconds}…`);
      onStatus("После сигнала произнесите: «раз, два, три».");
      await sleep(1000);
    }

    // A short cue clearly separates preparation from the actual measurement.
    // Measurement starts after the cue has finished, so it is not counted as voice.
    if (audioCtx) {
      try {
        if (audioCtx.state === "suspended") await audioCtx.resume();
        const oscillator = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        oscillator.frequency.value = 880;
        gain.gain.value = 0.08;
        oscillator.connect(gain);
        gain.connect(audioCtx.destination);
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + 0.16);
        await sleep(350);
      } catch (_) {
        // The large visual prompt remains sufficient if sound playback is blocked.
      }
    }

    // The browser meter only proves that getUserMedia works. Answers are
    // recorded by the server through its own device handle, so the probe must
    // go through that path — otherwise the check passes while the test cannot
    // record a thing. Release the browser stream first: two readers of the same
    // microphone is exactly the situation being tested for.
    stopAudio();
    await sleep(150);

    setItem("voice", "wait", "ГОВОРИТЕ СЕЙЧАС: «раз, два, три» — у вас 4 секунды");
    onStatus("Идёт запись пробы голоса…");

    let probe;
    try {
      probe = await api("/api/session/check-voice", { method: "POST" });
    } catch (error) {
      setItem("voice", "fail", `Проба голоса не выполнена: ${error.message || error}`);
      return;
    }

    onStatus("Проверяю запись…");
    results.voice = {
      ...(results.voice || {}),
      level: probe.peak_level,
      transcript: probe.transcript || "",
      reason: probe.reason || "",
    };
    setItem("voice", probe.state || (probe.ok ? "ok" : "fail"), probe.message || "");
  }

  // Readiness after a run: can the test start, and what to tell the user.
  function verdict() {
    const failedRequired = requirements.required.filter((name) => stateOf(name) === "fail");
    const anyFail = CHECK_NAMES.some((name) => requirements[name] && stateOf(name) === "fail");
    if (failedRequired.length > 0) {
      return {
        canStart: false,
        message: "Исправьте отмеченное красным и нажмите «Проверить снова».",
      };
    }
    if (anyFail && scenario === "hads") {
      return {
        canStart: true,
        message: "Голос недоступен — можно начинать, отвечать будете нажатием на варианты.",
      };
    }
    if (anyFail) {
      return { canStart: true, message: "Часть проверок не пройдена — результат может быть ограничен." };
    }
    return { canStart: true, message: "Всё готово — нажмите «Начать тест»." };
  }

  // Conditions stored with the session so reports can state limitations.
  function conditions() {
    const final = (name) => stateOf(name, "skipped");
    const faceData = (results.face || {}).data || {};
    const collected = { scenario, checked_at: new Date().toISOString() };
    if (requirements.camera) {
      collected.camera_ok = final("camera") === "ok";
      collected.face_detected = Boolean(faceData.face_detected);
      collected.face_close_enough = Boolean(faceData.face_close_enough);
      collected.brightness = faceData.brightness ?? null;
      collected.brightness_ok = Boolean(faceData.brightness_ok);
    }
    if (requirements.mic) {
      collected.mic_ok = final("mic") !== "fail";
      collected.noise_level = Number(((results.mic || {}).noise || 0).toFixed(4));
      collected.noise_ok = final("mic") === "ok";
    }
    if (requirements.voice) {
      collected.voice_ok = final("voice") === "ok";
      collected.voice_level = Number(((results.voice || {}).level || 0).toFixed(4));
    }
    return collected;
  }

  async function run() {
    if (running) return verdict();
    running = true;
    try {
      if (requirements.camera) await checkCameraAndFace();
      if (requirements.mic) await checkMicAndNoise();
      if (requirements.voice) await checkVoiceSample();
    } finally {
      stopAudio();
      running = false;
    }
    return verdict();
  }

  return {
    scenario,
    requirements,
    run,
    stop: stopAudio,
    verdict,
    conditions,
    isRunning: () => running,
  };
}

// The legacy #check-panel in app.js (MoCA/HADS) is a classic script and
// cannot import; it reaches the engine through this global.
window.nmSessionCheck = { create: createSessionCheck, getCheckRequirements, CHECK_NAMES };

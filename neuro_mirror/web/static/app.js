const WAKE_WORDS = ["зеркало", "привет зеркало", "hey mirror", "зеркала", "зеркалу", "зеркалом"];
const WAKE_WORD_DISPLAY = "«Зеркало»";

const state = {
  websocket: null,
  reconnectTimer: null,
  pingTimer: null,
  mediaStream: null,
  mediaRecorder: null,
  mediaChunks: [],
  audioContext: null,
  analyser: null,
  audioUnlocked: false,
  sharedAudioCtx: null,
  currentSpeechAudio: null,
  currentSpeechUrl: null,
  ttsRequestId: 0,
  ttsEnabled: true,
  lastSpokenText: "",
  currentSpeechText: "",
  config: null,
  deviceCatalog: { cameras: [], microphones: [] },
  selectedDevices: { camera_id: "", microphone_id: "" },
  cameraActive: false,
  recording: false,
  busy: false,
  live2dScriptsLoaded: false,
  live2dReady: false,
  live2dApp: null,
  live2dModel: null,
  live2dResizeHandler: null,
  // Wake-word activation
  wakeWordEnabled: false,
  wakeWordRecognition: null,
  wakeWordListening: false,
  wakeWordCooldown: false,
  // Heart rate monitoring
  hrMonitoring: false,
  hrMonitorAbort: null,
  lastHrBpm: null,
  lastHrAlgo: "",
  lastHrTs: null,
  // User profiles (личный кабинет)
  activeUser: null,
  userPresets: [],
  userSelectedPreset: "",
  userPhotoDataUrl: "",
  avatarCameraStream: null,
  userGateBound: false,
  lastScreen: "",
};

const $ = (id) => document.getElementById(id);

const el = {
  backendLabel: $("backend-label"),
  telemetryBackend: $("telemetry-backend"),
  connectionDot: $("connection-dot"),
  currentDate: $("current-date"),
  currentTime: $("current-time"),
  currentGreeting: $("current-greeting"),
  screenValue: $("screen-value"),
  sourceValue: $("source-value"),
  messageValue: $("message-value"),
  transcriptValue: $("transcript-value"),
  reportValue: $("report-value"),
  modulesValue: $("modules-value"),
  detailsDrawer: $("details-drawer"),
  logValue: $("log-value"),
  logClear: $("log-clear"),
  devicesForm: $("devices-form"),
  devicesRefresh: $("devices-refresh"),
  devicesSave: $("devices-save"),
  devicesStatus: $("devices-status"),
  devicesErrors: $("devices-errors"),
  cameraSelect: $("camera-select"),
  microphoneSelect: $("microphone-select"),
  assistantForm: $("assistant-form"),
  assistantInput: $("assistant-input"),
  composerShell: $("composer-shell"),
  composerHint: $("composer-hint"),
  askButton: $("ask-button"),
  cameraPreview: $("camera-preview"),
  cameraOverlay: $("camera-overlay"),
  cameraOverlayText: $("camera-overlay-text"),
  cameraToggle: $("camera-toggle"),
  appearanceButton: $("appearance-button"),
  voiceButton: $("voice-button"),
  voiceButtonLabel: $("voice-button-label"),
  voiceStatus: $("voice-status"),
  ttsEnabled: $("tts-enabled"),
  screeningButton: $("screening-button"),
  mascotFloat: $("mascot-float"),
  mascot: $("mascot"),
  mascotState: $("mascot-state"),
  mascotMouth: $("mascot-mouth"),
  mascotNote: $("mascot-note"),
  mascotSpeech: $("mascot-speech"),
  mascotSpeechText: $("mascot-speech-text"),
  mascotImage: $("mascot-image"),
  mascotLive2d: $("mascot-live2d"),
  wakeWordToggle: $("wake-word-toggle"),
  wakeWordIndicator: $("wake-word-indicator"),
  wakeWordHint: $("wake-word-hint"),
  hrWidget: $("hr-widget"),
  hrBpmValue: $("hr-bpm-value"),
  hrAlgoValue: $("hr-algo-value"),
  hrMonitorBtn: $("hr-monitor-btn"),
  hrProgressWrap: $("hr-progress-wrap"),
  hrProgressBar: $("hr-progress-bar"),
  hrProgressLabel: $("hr-progress-label"),
  userGate: $("user-gate"),
  userSelectView: $("user-select-view"),
  userCreateView: $("user-create-view"),
  userGrid: $("user-grid"),
  userCreateOpen: $("user-create-open"),
  userCreateForm: $("user-create-form"),
  userNameInput: $("user-name-input"),
  avatarPicker: $("avatar-picker"),
  avatarPhotoBtn: $("avatar-photo-btn"),
  avatarPhotoHint: $("avatar-photo-hint"),
  avatarCamera: $("avatar-camera"),
  avatarCameraVideo: $("avatar-camera-video"),
  avatarCaptureBtn: $("avatar-capture-btn"),
  avatarCameraCancel: $("avatar-camera-cancel"),
  userConsent: $("user-consent"),
  consentText: $("consent-text"),
  userCreateError: $("user-create-error"),
  userCreateSubmit: $("user-create-submit"),
  userCreateBack: $("user-create-back"),
  userChip: $("user-chip"),
  userChipAvatar: $("user-chip-avatar"),
  userChipName: $("user-chip-name"),
  menuButton: $("menu-button"),
  mainMenu: $("main-menu"),
  mainMenuClose: $("main-menu-close"),
  resultsPanel: $("results-panel"),
  resultsList: $("results-list"),
  resultsSub: $("results-sub"),
  resultsClose: $("results-close"),
  checkPanel: $("check-panel"),
  checkSub: $("check-sub"),
  checkStatus: $("check-status"),
  checkStart: $("check-start"),
  checkRetry: $("check-retry"),
  checkCancel: $("check-cancel"),
  hadsPanel: $("hads-panel"),
  hadsPart: $("hads-part"),
  hadsProgressFill: $("hads-progress-fill"),
  hadsQuestion: $("hads-question"),
  hadsOptions: $("hads-options"),
  hadsMic: $("hads-mic"),
  hadsStatus: $("hads-status"),
  hadsStop: $("hads-stop"),
};

const SCREEN_LABELS = {
  idle: "Idle",
  assistant: "Assistant",
  screening: "Screening",
  moca: "Тест MoCA",
  hads: "Тест HADS",
  summary: "Summary",
  device_setup: "Device Setup",
};

const MODULE_ORDER = ["vision_worker", "camera", "emotiefflib", "speech_worker", "microphone", "stt"];
const MODULE_LABELS = {
  vision_worker: "Vision Worker",
  camera: "Camera",
  emotiefflib: "EmotiEffLib",
  speech_worker: "Speech Worker",
  microphone: "Microphone",
  stt: "STT",
};

function setText(node, value) {
  if (node) node.textContent = value;
}

function setHidden(node, hidden) {
  if (node) node.hidden = hidden;
}

function setDisabled(node, disabled) {
  if (node) node.disabled = disabled;
}

function setButtonLabel(button, label) {
  if (!button) return;
  button.title = label;
  button.setAttribute("aria-label", label);
}

function setCameraOverlay(message) {
  if (!el.cameraOverlay) return;
  setHidden(el.cameraOverlay, false);
  if (el.cameraOverlayText) {
    setText(el.cameraOverlayText, message);
    return;
  }
  setText(el.cameraOverlay, message);
}

function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function stripTrailingSpeechMeta(text) {
  return String(text || "").replace(/\s*\[[^\]]+\]\s*$/u, "").trim();
}

function isAbsoluteHttpUrl(value) {
  return /^https?:\/\//i.test(String(value || ""));
}

function appendLogLine(line) {
  // Client log lives in the browser console; errors are relayed to the
  // server terminal via reportClientError → /api/client-log
  console.log(`[neuro-mirror] ${line}`);
}

function sendClientLog(level, message) {
  try {
    fetch("/api/client-log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level, message }),
      keepalive: true,
    }).catch(() => {});
  } catch (_) {
    // relay is best-effort only
  }
}

function reportClientError(error, prefix) {
  const message = error instanceof Error ? (error.stack || error.message) : String(error);
  console.error(prefix, error);
  setText(el.messageValue, `${prefix}: ${message}`);
  sendClientLog("error", `${prefix}: ${message}`);
}

function describeMediaError(error) {
  if (!error) return "unknown camera error";
  const name = typeof error.name === "string" && error.name ? error.name : "";
  const message = typeof error.message === "string" && error.message ? error.message : String(error);
  return name && message && !message.startsWith(`${name}:`) ? `${name}: ${message}` : (message || name || "unknown camera error");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error((await response.text()) || `${response.status}`);
  }
  return response.json();
}

function setButtonLoading(button, loading) {
  if (!button) return;
  button.disabled = loading;
  button.classList.toggle("loading", loading);
}

function describeSttRun(payload, elapsedMs) {
  const parts = [];
  if (typeof elapsedMs === "number" && Number.isFinite(elapsedMs)) {
    parts.push(`${elapsedMs} мс`);
  }
  if (payload && payload.stt_model) {
    const device = payload.stt_device ? `/${payload.stt_device}` : "";
    parts.push(`${payload.stt_model}${device}`);
  }
  return parts.length ? `Распознано за ${parts.join(" • ")}` : "Распознано";
}

function setMascotSpeech(text, options) {
  state.currentSpeechText = text || "";
  setHidden(el.mascotSpeech, true);
  if (el.mascotSpeech) {
    el.mascotSpeech.style.display = "none";
  }
  if (el.mascotSpeechText) {
    el.mascotSpeechText.textContent = "";
  }
}

function shouldShowMascotSpeech(snapshot) {
  return false;
}

function setMascotState(name) {
  if (el.mascot) el.mascot.dataset.state = name;
  if (el.mascotFloat) el.mascotFloat.dataset.state = name;
  document.body.dataset.uiState = name;
  setText(el.mascotState, name);

  if (!el.mascotMouth || state.analyser) return;

  const sizes = {
    idle: [46, 12, 0.45],
    listening: [58, 16, 0.85],
    thinking: [34, 8, 0.75],
    speaking: [72, 20, 0.9],
  };
  const values = sizes[name] || sizes.idle;
  el.mascotMouth.style.width = `${values[0]}px`;
  el.mascotMouth.style.height = `${values[1]}px`;
  el.mascotMouth.style.opacity = `${values[2]}`;
}

function setMascotLive2dStatus(status) {
  if (el.mascot) el.mascot.dataset.live2d = status;
}

function formatClockDate(value) {
  return value.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).replace(".", "");
}

function formatGreeting(hours) {
  if (hours < 6) return "Глубокая ночь";
  if (hours < 12) return "Доброе утро";
  if (hours < 18) return "Добрый день";
  return "Добрый вечер";
}

function updateClockDisplay() {
  const now = new Date();
  if (el.currentDate) setText(el.currentDate, formatClockDate(now));
  if (el.currentTime) {
    setText(
      el.currentTime,
      now.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
    );
  }
  if (el.currentGreeting) {
    const greeting = formatGreeting(now.getHours());
    setText(
      el.currentGreeting,
      state.activeUser ? `${greeting}, ${state.activeUser.name}` : greeting
    );
  }
}

async function loadExternalScript(url, test) {
  if (!url) throw new Error("script URL is empty");
  if (typeof test === "function" && test()) return;

  const existing = document.querySelector(`script[data-external-script="${url}"]`);
  if (existing) {
    await new Promise((resolve, reject) => {
      if (existing.dataset.loaded === "1") {
        resolve();
        return;
      }
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", () => reject(new Error(`failed to load ${url}`)), { once: true });
    });
    return;
  }

  await new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.async = true;
    script.dataset.externalScript = url;
    script.addEventListener("load", () => {
      script.dataset.loaded = "1";
      resolve();
    }, { once: true });
    script.addEventListener("error", () => reject(new Error(`failed to load ${url}`)), { once: true });
    document.head.appendChild(script);
  });
}

function fitLive2DModel() {
  if (!state.live2dModel || !state.live2dApp || !el.mascotLive2d) return;

  const width = Math.max(220, el.mascotLive2d.clientWidth || 280);
  const height = Math.max(280, el.mascotLive2d.clientHeight || 380);
  state.live2dApp.renderer.resize(width, height);

  const localBounds = state.live2dModel.getLocalBounds();
  const baseWidth = Math.max(1, localBounds.width);
  const baseHeight = Math.max(1, localBounds.height);
  const scale = Math.min(width / baseWidth, height / baseHeight) * 1.2;

  state.live2dModel.scale.set(scale);
  state.live2dModel.anchor.set(0.5, 0.0);
  state.live2dModel.x = width * 0.5;
  state.live2dModel.y = -height * 0.08;
}

async function setupLive2D() {
  const modelUrl = state.config && state.config.live2d_model_url;
  if (!modelUrl || !el.mascotLive2d || !el.mascot) {
    setMascotLive2dStatus("preview");
    return;
  }

  try {
    setMascotLive2dStatus("loading");
    setText(el.mascotNote, "Loading Live2D model...");

    const coreUrl = (state.config && state.config.live2d_cubism_core_url) || "";
    await loadExternalScript("https://cdn.jsdelivr.net/npm/pixi.js@6.5.10/dist/browser/pixi.min.js", () => Boolean(window.PIXI && window.PIXI.Application));
    if (coreUrl) {
      await loadExternalScript(coreUrl, () => Boolean(window.Live2DCubismCore));
    }
    await loadExternalScript("https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.4.0/dist/cubism4.min.js", () => Boolean(window.PIXI && window.PIXI.live2d && window.PIXI.live2d.Live2DModel));

    if (!window.PIXI || !window.PIXI.live2d || !window.PIXI.live2d.Live2DModel) {
      throw new Error("Live2D runtime is unavailable");
    }

    const app = new window.PIXI.Application({
      width: Math.max(220, el.mascotLive2d.clientWidth || 280),
      height: Math.max(280, el.mascotLive2d.clientHeight || 380),
      autoStart: true,
      transparent: true,
      antialias: true,
    });

    el.mascotLive2d.innerHTML = "";
    el.mascotLive2d.appendChild(app.view);

    const model = await window.PIXI.live2d.Live2DModel.from(modelUrl, {
      autoInteract: false,
    });

    app.stage.addChild(model);
    state.live2dApp = app;
    state.live2dModel = model;
    state.live2dReady = true;
    state.live2dScriptsLoaded = true;

    fitLive2DModel();
    if (!state.live2dResizeHandler) {
      state.live2dResizeHandler = () => fitLive2DModel();
      window.addEventListener("resize", state.live2dResizeHandler);
    }

    setHidden(el.mascotLive2d, false);
    setHidden(el.mascotImage, true);
    setMascotLive2dStatus("ready");
    setText(el.mascotNote, "AIRI Hiyori Live2D model is active.");
    appendLogLine(`[client] live2d ready: ${modelUrl}`);
  } catch (error) {
    state.live2dReady = false;
    setHidden(el.mascotLive2d, true);
    setHidden(el.mascotImage, false);
    setMascotLive2dStatus("fallback");
    setText(el.mascotNote, `Live2D fallback: ${error.message || error}`);
    appendLogLine(`[client] live2d error: ${error.message || error}`);
  }
}

async function unlockAudioPlayback() {
  if (state.audioUnlocked) return;

  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtor) {
    state.audioUnlocked = true;
    return;
  }

  if (!state.sharedAudioCtx) {
    state.sharedAudioCtx = new AudioCtor();
  }
  const context = state.sharedAudioCtx;

  try {
    if (context.state === "suspended") {
      await context.resume();
    }

    const source = context.createBufferSource();
    source.buffer = context.createBuffer(1, 1, 22050);
    const gain = context.createGain();
    gain.gain.value = 0;
    source.connect(gain);
    gain.connect(context.destination);
    source.start(0);

    await new Promise((resolve) => {
      source.onended = resolve;
      setTimeout(resolve, 60);
    });

    state.audioUnlocked = true;
    setText(el.mascotNote, "AIRI Hiyori voice output is unlocked.");
  } catch (_) {
    // ignore
  }
}

function installAudioUnlockHandlers() {
  const unlockOnce = async () => {
    try {
      await unlockAudioPlayback();
    } catch (_) {
      // keep trying on next user gesture
    }

    if (state.audioUnlocked) {
      window.removeEventListener("pointerdown", unlockOnce);
      window.removeEventListener("keydown", unlockOnce);
      window.removeEventListener("touchstart", unlockOnce);
    }
  };

  window.addEventListener("pointerdown", unlockOnce, { passive: true });
  window.addEventListener("keydown", unlockOnce, { passive: true });
  window.addEventListener("touchstart", unlockOnce, { passive: true });
}

function waitForVideoReady(video, timeoutMs) {
  return new Promise((resolve, reject) => {
    if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
      resolve();
      return;
    }

    let timer = null;

    const cleanup = () => {
      if (timer) clearTimeout(timer);
      video.removeEventListener("loadedmetadata", onReady);
      video.removeEventListener("canplay", onReady);
      video.removeEventListener("playing", onReady);
      video.removeEventListener("error", onError);
    };

    const onReady = () => {
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        cleanup();
        resolve();
      }
    };

    const onError = () => {
      cleanup();
      reject(new Error("video element failed to start"));
    };

    timer = setTimeout(() => {
      cleanup();
      reject(new Error("timeout waiting for first video frame"));
    }, timeoutMs || 6000);

    video.addEventListener("loadedmetadata", onReady);
    video.addEventListener("canplay", onReady);
    video.addEventListener("playing", onReady);
    video.addEventListener("error", onError);
  });
}

async function loadConfig() {
  appendLogLine("[client] requesting /api/config");
  state.config = await fetchJson("/api/config");
  setText(el.backendLabel, state.config.assistant_backend_label || "web");
  setText(el.telemetryBackend, state.config.assistant_backend_label || "web");

  if (state.config.live2d_model_url) {
    setText(el.mascotNote, "AIRI Hiyori Live2D URL is configured.");
  } else {
    setText(el.mascotNote, "AIRI Hiyori preview is loaded.");
  }
}

async function loadDevices() {
  appendLogLine("[client] requesting /api/devices");
  const payload = await fetchJson("/api/devices");
  renderDeviceWizard(payload);
}

async function submitDeviceSelection(event) {
  event.preventDefault();
  if (!el.cameraSelect || !el.microphoneSelect) return;

  setButtonLoading(el.devicesSave, true);
  try {
    await fetchJson("/api/devices/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        camera_id: el.cameraSelect.value || "",
        microphone_id: el.microphoneSelect.value || "",
      }),
    });
    await new Promise((resolve) => window.setTimeout(resolve, 150));
    await loadDevices();
    if (el.detailsDrawer) el.detailsDrawer.open = true;
  } catch (error) {
    renderDeviceErrors([error.message || String(error)]);
    appendLogLine(`[client] device selection error: ${error.message || error}`);
  } finally {
    setButtonLoading(el.devicesSave, false);
  }
}

function renderReport(report) {
  if (!el.reportValue) return;

  if (!report) {
    el.reportValue.innerHTML = '<p class="placeholder-text">No report yet.</p>';
    return;
  }

  if (report.report_type === "appearance") {
    const rows = [];
    rows.push(reportRow("State", report.state || "-"));
    if (report.compliment) rows.push(reportRow("Reply", report.compliment));
    if (report.observed) rows.push(reportRow("Observed", report.observed));
    if (report.suggestion) rows.push(reportRow("Suggestion", report.suggestion));
    if (report.face_detected !== undefined) rows.push(reportRow("Face detected", report.face_detected ? "Yes" : "No"));
    if (report.face_count != null) rows.push(reportRow("Faces", report.face_count));
    if (report.confidence != null) rows.push(reportRow("Confidence", typeof report.confidence === "number" ? report.confidence.toFixed(2) : report.confidence));
    if (report.emotion) rows.push(reportRow("Emotion", report.emotion));
    if (report.appearance_description) rows.push(reportRow("Description", report.appearance_description));
    if (report.emotiefflib_available !== undefined) rows.push(reportRow("EmotiEffLib", report.emotiefflib_available ? "Yes" : "No"));
    if (report.source_backend) rows.push(reportRow("Source", report.source_backend));
    if (report.notes) rows.push(reportRow("Notes", report.notes));
    el.reportValue.innerHTML = rows.join("");
    return;
  }

  if (report.report_type === "screening") {
    const rows = [];
    rows.push('<div class="report-section">Screening</div>');
    rows.push(reportRow("State", report.state || "-"));

    const domains = report.domains || {};
    if (domains.attention != null) rows.push(reportRow("Attention", formatNumber(domains.attention)));
    if (domains.heart_rate_bpm != null) rows.push(reportRow("Heart rate", `${formatNumber(domains.heart_rate_bpm)} bpm`));
    if (domains.heart_rate_status && domains.heart_rate_status !== "ok") rows.push(reportRow("Heart rate status", domains.heart_rate_status));
    if (domains.moca_score != null && domains.moca_max_score != null) {
      rows.push(reportRow("MoCA voice score", `${domains.moca_score} / ${domains.moca_max_score}`));
    }
    if (domains.moca_percent != null) rows.push(reportRow("MoCA voice percent", `${Math.round(Number(domains.moca_percent) * 100)}%`));
    if (domains.speech != null) rows.push(reportRow("Speech", formatNumber(domains.speech)));
    if (domains.reaction != null) rows.push(reportRow("Reaction", `${domains.reaction} ms`));

    const summary = report.summary || {};
    if (summary.moca_interpretation) rows.push(reportRow("Interpretation", summary.moca_interpretation));
    if (summary.moca_notes) rows.push(reportRow("Notes", summary.moca_notes));
    pushHadsRows(rows, domains, summary, report.sources || {});

    const sources = report.sources || {};
    const video = sources.video || {};
    const voice = sources.voice || {};

    if (Object.keys(video).length > 0) {
      rows.push('<div class="report-section">Video</div>');
      if (video.attention_score != null) rows.push(reportRow("Attention", formatNumber(video.attention_score)));
      if (video.face_detected !== undefined) rows.push(reportRow("Face", video.face_detected ? "Yes" : "No"));
      if (video.heart_rate_bpm != null) rows.push(reportRow("Heart rate", `${formatNumber(video.heart_rate_bpm)} bpm`));
      if (video.heart_rate_algorithm) rows.push(reportRow("Heart rate model", video.heart_rate_algorithm));
      if (video.heart_rate_status && video.heart_rate_status !== "ok") rows.push(reportRow("Heart rate status", video.heart_rate_status));
      if (video.heart_rate_error) rows.push(reportRow("Heart rate note", video.heart_rate_error));
      if (video.notes) rows.push(reportRow("Notes", video.notes));
    }

    if (Object.keys(voice).length > 0) {
      rows.push('<div class="report-section">Voice</div>');
      if (voice.speech_score != null) rows.push(reportRow("Speech", formatNumber(voice.speech_score)));
      if (voice.reaction_ms != null) rows.push(reportRow("Reaction", `${voice.reaction_ms} ms`));
      if (voice.notes) rows.push(reportRow("Notes", voice.notes));
    }

    const moca = sources.moca || {};
    const mocaTasks = Array.isArray(domains.moca_tasks) ? domains.moca_tasks : Array.isArray(moca.tasks) ? moca.tasks : [];
    if (mocaTasks.length > 0) {
      rows.push('<div class="report-section">MoCA answers</div>');
      for (const task of mocaTasks) {
        const maxScore = Number(task.max_score || 0);
        const scoreLabel = maxScore > 0 ? `${task.score || 0}/${maxScore}` : "not scored";
        const transcript = task.transcript || "-";
        const details = task.details ? ` · ${task.details}` : "";
        rows.push(reportRow(mocaTaskLabel(task.task_id), `${scoreLabel}: ${transcript}${details}`));
      }
    }

    el.reportValue.innerHTML = rows.join("");
    return;
  }

  if (report.report_type === "hads") {
    const rows = [];
    rows.push('<div class="report-section">Тест на тревожность (HADS)</div>');
    rows.push(reportRow("State", report.state || "-"));
    pushHadsRows(rows, report.domains || {}, report.summary || {}, report.sources || {});
    el.reportValue.innerHTML = rows.join("");
    return;
  }

  el.reportValue.innerHTML = `<pre>${escapeHtml(JSON.stringify(report, null, 2))}</pre>`;
}

function pushHadsRows(rows, domains, summary, sources) {
  const hasHads = domains.hads_anxiety_score != null || domains.hads_depression_score != null;
  if (!hasHads) return;

  rows.push('<div class="report-section">HADS</div>');
  if (domains.hads_anxiety_score != null) {
    rows.push(reportRow("Тревога", `${domains.hads_anxiety_score} / ${domains.hads_anxiety_max || 21}`));
  }
  if (summary.hads_anxiety_interpretation) {
    rows.push(reportRow("Оценка тревоги", summary.hads_anxiety_interpretation));
  }
  if (domains.hads_depression_score != null) {
    rows.push(reportRow("Депрессия", `${domains.hads_depression_score} / ${domains.hads_depression_max || 21}`));
  }
  if (summary.hads_depression_interpretation) {
    rows.push(reportRow("Оценка депрессии", summary.hads_depression_interpretation));
  }
  if (domains.hads_answered_count != null && domains.hads_question_count != null) {
    rows.push(reportRow("Отвечено", `${domains.hads_answered_count} из ${domains.hads_question_count}`));
  }
  if (summary.hads_notes) rows.push(reportRow("Notes", summary.hads_notes));

  const hads = sources.hads || {};
  const answers = Array.isArray(hads.answers) ? hads.answers : [];
  if (answers.length > 0) {
    rows.push('<div class="report-section">Ответы HADS</div>');
    for (const answer of answers) {
      rows.push(reportRow(answer.question || answer.question_id, `${answer.option_text} (${answer.score})`));
    }
  }
}

function formatNumber(value) {
  return typeof value === "number" ? value.toFixed(2) : value;
}

function reportRow(label, value) {
  return `<div class="report-row"><span class="report-label">${escapeHtml(label)}</span><span class="report-val">${escapeHtml(value)}</span></div>`;
}

function mocaTaskLabel(taskId) {
  const labels = {
    memory_1: "Memory 1",
    memory_2: "Memory 2",
    attention_digits_forward: "Digits forward",
    attention_digits_backward: "Digits backward",
    attention_serial: "Serial 100-7",
    language_sentence_1: "Sentence 1",
    language_sentence_2: "Sentence 2",
    language_fluency: "Fluency",
    abstraction_1: "Abstraction 1",
    abstraction_2: "Abstraction 2",
    delayed_recall: "Delayed recall",
  };
  return labels[taskId] || taskId || "MoCA task";
}

function renderModules(modules) {
  if (!el.modulesValue) return;

  if (!modules || Object.keys(modules).length === 0) {
    el.modulesValue.innerHTML = '<p class="placeholder-text">Module status is not available yet.</p>';
    return;
  }

  let html = "";
  for (const key of MODULE_ORDER) {
    const item = modules[key];
    if (!item) continue;
    const label = MODULE_LABELS[key] || key;
    const dotClass = item.available ? "ok" : "fail";
    html += `<div class="module-row" data-module="${escapeHtml(key)}"><span class="module-dot ${dotClass}"></span><span class="module-name">${escapeHtml(label)}</span><span class="module-detail">${escapeHtml(item.detail || "")}</span></div>`;
  }

  el.modulesValue.innerHTML = html || '<p class="placeholder-text">Module status is not available yet.</p>';
}

function renderLog(eventLog) {
  if (!el.logValue) return;
  if (!eventLog || eventLog.length === 0) {
    el.logValue.textContent = "Log is empty.";
    return;
  }
  el.logValue.textContent = eventLog.join("\n");
  el.logValue.scrollTop = el.logValue.scrollHeight;
}

function normalizeSelectedDevices(raw) {
  if (!raw || typeof raw !== "object") {
    return { camera_id: "", microphone_id: "" };
  }
  return {
    camera_id: String(raw.camera_id || raw.selected_camera_id || ""),
    microphone_id: String(raw.microphone_id || raw.selected_microphone_id || ""),
  };
}

function renderDeviceErrors(errors) {
  if (!el.devicesErrors) return;
  const items = Array.isArray(errors) ? errors.filter(Boolean) : [];
  if (!items.length) {
    el.devicesErrors.innerHTML = "";
    setHidden(el.devicesErrors, true);
    return;
  }
  el.devicesErrors.innerHTML = items.map((item) => `<div class="device-error">${escapeHtml(item)}</div>`).join("");
  setHidden(el.devicesErrors, false);
}

function renderDeviceSelect(select, devices, selectedId) {
  if (!select) return;
  const items = Array.isArray(devices) ? devices : [];
  const options = items.map((item) => {
    const id = String(item.device_id || "");
    const label = String(item.label || id || "Unknown device");
    const suffix = item.available === false ? " (недоступно)" : "";
    return `<option value="${escapeHtml(id)}">${escapeHtml(label + suffix)}</option>`;
  });
  select.innerHTML = options.join("") || '<option value="">Нет доступных устройств</option>';
  if (selectedId && items.some((item) => String(item.device_id || "") === selectedId)) {
    select.value = selectedId;
    return;
  }
  select.value = items[0] && items[0].device_id != null ? String(items[0].device_id) : "";
}

function renderDeviceWizard(snapshot) {
  const catalog = snapshot && snapshot.device_catalog ? snapshot.device_catalog : state.deviceCatalog;
  const selected = normalizeSelectedDevices(snapshot && snapshot.selected_devices ? snapshot.selected_devices : state.selectedDevices);
  const errors = snapshot && Array.isArray(snapshot.device_errors) ? snapshot.device_errors : [];

  state.deviceCatalog = {
    cameras: Array.isArray(catalog && catalog.cameras) ? catalog.cameras : [],
    microphones: Array.isArray(catalog && catalog.microphones) ? catalog.microphones : [],
  };
  state.selectedDevices = selected;

  renderDeviceSelect(el.cameraSelect, state.deviceCatalog.cameras, selected.camera_id);
  renderDeviceSelect(el.microphoneSelect, state.deviceCatalog.microphones, selected.microphone_id);
  renderDeviceErrors(errors);

  if (el.devicesStatus) {
    const selectedCamera = state.deviceCatalog.cameras.find((item) => String(item.device_id || "") === String(el.cameraSelect && el.cameraSelect.value || ""));
    const selectedMicrophone = state.deviceCatalog.microphones.find((item) => String(item.device_id || "") === String(el.microphoneSelect && el.microphoneSelect.value || ""));
    const hasCatalog = state.deviceCatalog.cameras.length > 0 || state.deviceCatalog.microphones.length > 0;
    setText(
      el.devicesStatus,
      hasCatalog
        ? `Камера: ${selectedCamera ? selectedCamera.label : "не выбрана"} • Микрофон: ${selectedMicrophone ? selectedMicrophone.label : "не выбран"}`
        : "Каталог устройств пока пуст."
    );
  }
}

function syncDeviceSelectionStatus() {
  renderDeviceWizard({
    device_catalog: state.deviceCatalog,
    selected_devices: {
      camera_id: el.cameraSelect ? el.cameraSelect.value : "",
      microphone_id: el.microphoneSelect ? el.microphoneSelect.value : "",
    },
    device_errors: [],
  });
}

function updateHrWidget(bpm, algo, status) {
  if (bpm == null || status === "disabled") return;
  state.lastHrBpm = bpm;
  state.lastHrAlgo = algo || "";
  state.lastHrTs = Date.now();

  if (!el.hrWidget) return;
  setHidden(el.hrWidget, false);

  const bpmText = `${Math.round(bpm)} уд/мин`;
  if (el.hrBpmValue) {
    el.hrBpmValue.textContent = bpmText;
    el.hrBpmValue.classList.remove("hr-active");
    void el.hrBpmValue.offsetWidth; // force reflow to restart animation
    el.hrBpmValue.classList.add("hr-active");
  }
  if (el.hrAlgoValue) {
    el.hrAlgoValue.textContent = algo ? algo.toUpperCase() : "";
  }
}

function renderSnapshot(snapshot) {
  // During MoCA test — only update the MoCA panel, suppress all other UI output
  if (snapshot.screen === "moca") {
    // Tests speak through their own TTS channel — cut any assistant speech
    if (state.currentSpeechAudio) cleanupSpeechAudio();
    renderHads(snapshot);
    renderMoca(snapshot);
    return;
  }

  // During HADS test — only update the HADS panel
  if (snapshot.screen === "hads") {
    if (state.currentSpeechAudio) cleanupSpeechAudio();
    renderMoca(snapshot);
    renderHads(snapshot);
    return;
  }

  // Hide test panels when their screens are no longer active
  renderMoca(snapshot);
  renderHads(snapshot);

  setText(el.screenValue, SCREEN_LABELS[snapshot.screen] || snapshot.screen || "-");
  setText(el.sourceValue, snapshot.assistant_source || "-");
  setText(el.messageValue, snapshot.message || "-");
  setText(el.transcriptValue, snapshot.transcript_text ? `Transcript: ${snapshot.transcript_text}` : "");
  setMascotSpeech(snapshot.message || "", { visible: shouldShowMascotSpeech(snapshot) });

  if (snapshot.heart_rate_bpm != null) {
    updateHrWidget(snapshot.heart_rate_bpm, snapshot.heart_rate_algorithm, snapshot.heart_rate_status);
  }

  if (snapshot.pulse_monitor_start && !state.hrMonitoring) {
    startPulseMonitor(snapshot.pulse_monitor_duration || 60);
  }

  renderReport(snapshot.report);
  renderModules(snapshot.worker_statuses || {});
  renderLog(snapshot.event_log || []);
  renderDeviceWizard(snapshot);

  // Override camera module status when browser camera is active
  if (state.cameraActive) {
    updateBrowserCameraModuleStatus(true);
  }

  let mascotState = "idle";
  if (state.recording || snapshot.recording_active) mascotState = "listening";
  else if (state.busy) mascotState = "thinking";
  else if (snapshot.assistant_source && snapshot.message && snapshot.screen === "summary") mascotState = "speaking";
  setMascotState(mascotState);

  setDisabled(el.appearanceButton, !state.cameraActive);
  if (snapshot.screen === "device_setup" && state.lastScreen !== "device_setup") {
    // The device wizard now lives inside the main menu overlay
    openMainMenu();
  }
  state.lastScreen = snapshot.screen;
}

// ---- MoCA test UI ----

let _mocaPanel = null;

function _getMocaPanel() {
  if (_mocaPanel) return _mocaPanel;
  _mocaPanel = document.getElementById("moca-panel");
  if (!_mocaPanel) {
    // Create panel dynamically if not in HTML
    _mocaPanel = document.createElement("div");
    _mocaPanel.id = "moca-panel";
    _mocaPanel.style.cssText = [
      "position:fixed", "top:0", "left:0", "width:100%", "height:100%",
      "background:rgba(0,0,0,0.85)", "color:#fff", "display:none",
      "flex-direction:column", "align-items:center", "justify-content:center",
      "z-index:9999", "font-family:sans-serif", "padding:32px", "box-sizing:border-box",
    ].join(";");
    _mocaPanel.innerHTML = `
      <div style="max-width:640px;width:100%;text-align:center">
        <div id="moca-domain" style="font-size:14px;opacity:.6;margin-bottom:8px"></div>
        <div id="moca-progress-bar" style="width:100%;height:6px;background:#333;border-radius:3px;margin-bottom:24px">
          <div id="moca-progress-fill" style="height:6px;background:#6ee7b7;border-radius:3px;width:0%;transition:width .4s"></div>
        </div>
        <div id="moca-hint" style="font-size:22px;font-weight:600;margin-bottom:20px;line-height:1.4"></div>
        <div id="moca-status" style="font-size:16px;opacity:.7;margin-bottom:16px"></div>
        <div id="moca-mic-indicator" style="display:none;margin-top:20px;align-items:center;justify-content:center;gap:12px">
          <span style="width:16px;height:16px;border-radius:50%;background:#ef4444;animation:moca-pulse 1s infinite;flex-shrink:0"></span>
          <span style="font-size:20px;font-weight:700;letter-spacing:.5px">Говорите...</span>
        </div>
        <button id="moca-stop-btn" onclick="stopMocaTest()" style="
          margin-top:32px;padding:10px 28px;background:transparent;
          border:1px solid rgba(255,255,255,0.3);color:#fff;border-radius:8px;
          font-size:14px;cursor:pointer;opacity:.6
        ">Прервать тест</button>
      </div>
      <style>
        @keyframes moca-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        #moca-stop-btn:hover { opacity:1; border-color:#fff; }
      </style>
    `;
    document.body.appendChild(_mocaPanel);
  }
  return _mocaPanel;
}

function renderMoca(snapshot) {
  if (snapshot.screen !== "moca") {
    const panel = document.getElementById("moca-panel");
    if (panel) panel.style.display = "none";
    stopMocaAudio();
    return;
  }

  const panel = _getMocaPanel();
  panel.style.display = "flex";

  const idx = typeof snapshot.moca_task_index === "number" ? snapshot.moca_task_index : 0;
  const total = typeof snapshot.moca_task_total === "number" ? snapshot.moca_task_total : 11;
  const pct = total > 0 ? Math.round((idx / total) * 100) : 0;

  const fill = document.getElementById("moca-progress-fill");
  if (fill) fill.style.width = pct + "%";

  const domain = document.getElementById("moca-domain");
  if (domain) domain.textContent = snapshot.moca_domain
    ? `${snapshot.moca_domain} — задание ${idx + 1} из ${total}`
    : `Задание ${idx + 1} из ${total}`;

  const taskId = snapshot.moca_task_id || "";
  const isRecording = !!snapshot.moca_recording;
  // Hide hint for ALL tasks while recording — patient must answer from memory
  const hideHint = isRecording;

  // hint = task description, visible only while NOT recording (for memory tasks)
  const hint = document.getElementById("moca-hint");
  if (hint) {
    if (snapshot.moca_hint) hint.textContent = snapshot.moca_hint;
    hint.style.display = hideHint ? "none" : "block";
  }

  // status line: show only neutral status, never "Говорите" (that's the mic indicator)
  const status = document.getElementById("moca-status");
  if (status) {
    const msg = snapshot.message || "";
    // Don't echo "Говорите..." in the status text — the mic indicator handles that
    status.textContent = (isRecording || msg === "Говорите...") ? "" : msg;
  }

  const mic = document.getElementById("moca-mic-indicator");
  if (mic) mic.style.display = isRecording ? "flex" : "none";

  // Auto-play TTS prompt when server sends moca_tts_text
  if (snapshot.moca_tts_text) {
    const ttsKey = snapshot.moca_tts_id || snapshot.moca_tts_text;
    if (ttsKey !== window._lastMocaTts) {
      window._lastMocaTts = ttsKey;
      _mocaPlayTts(snapshot.moca_tts_text, snapshot.moca_tts_id || "");
    }
  }
}

async function stopMocaTest() {
  try {
    await fetch("/api/actions/stop_moca", { method: "POST" });
  } catch (_) {}
}

async function _mocaNotifyTtsFinished(ttsId) {
  if (!ttsId) return;
  try {
    await fetch("/api/actions/moca_tts_finished", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ moca_tts_id: ttsId }),
    });
  } catch (_) {}
}

function stopMocaAudio() {
  // Invalidate any in-flight TTS fetch (see stopHadsAudio)
  window._mocaTtsSeq = (window._mocaTtsSeq || 0) + 1;
  if (!window._currentMocaAudio) return;
  window._currentMocaAudio.pause();
  window._currentMocaAudio.removeAttribute("src");
  window._currentMocaAudio.load();
  window._currentMocaAudio = null;
}

async function _mocaPlayTts(text, ttsId) {
  // Sequence guard against overlapping speech (see _hadsPlayTts)
  stopMocaAudio();
  const seq = window._mocaTtsSeq;

  try {
    const resp = await fetch("/api/tts/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    if (seq !== window._mocaTtsSeq) return; // superseded or stopped
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    window._currentMocaAudio = audio;
    const playbackDone = new Promise((resolve) => {
      audio.onended = resolve;
      audio.onerror = resolve;
      audio.onabort = resolve;
    });
    await audio.play();
    await playbackDone;
    URL.revokeObjectURL(url);
    if (window._currentMocaAudio === audio) window._currentMocaAudio = null;
  } catch (_) {
  } finally {
    await _mocaNotifyTtsFinished(ttsId);
  }
}

// ---- HADS anxiety test UI ----

function stopHadsAudio() {
  // Invalidate any in-flight TTS fetch: audio that is still being
  // synthesized must not start playing after the test was stopped
  window._hadsTtsSeq = (window._hadsTtsSeq || 0) + 1;
  if (!window._currentHadsAudio) return;
  // pause + clearing src fires "abort" which resolves the playback promise
  // inside _hadsPlayTts, so the server still gets its tts_finished notice
  window._currentHadsAudio.pause();
  window._currentHadsAudio.removeAttribute("src");
  window._currentHadsAudio.load();
  window._currentHadsAudio = null;
}

function renderHads(snapshot) {
  if (!el.hadsPanel) return;
  if (snapshot.screen !== "hads") {
    setHidden(el.hadsPanel, true);
    stopHadsAudio();
    return;
  }
  setHidden(el.hadsPanel, false);

  // Answer accepted while the question is still being spoken — cut the speech
  if (snapshot.hads_selected_option != null) {
    stopHadsAudio();
  }

  const idx = typeof snapshot.hads_question_index === "number" ? snapshot.hads_question_index : 0;
  const total = typeof snapshot.hads_question_total === "number" ? snapshot.hads_question_total : 14;
  const pct = total > 0 ? Math.round((idx / total) * 100) : 0;
  if (el.hadsProgressFill) el.hadsProgressFill.style.width = `${pct}%`;

  const hasQuestion = Boolean(snapshot.hads_question_text);
  if (el.hadsPart) {
    el.hadsPart.textContent = hasQuestion
      ? `${snapshot.hads_part || ""} — вопрос ${idx + 1} из ${total}`.replace(/^ — /, "")
      : "Тест на тревожность и депрессию (HADS)";
  }
  setText(el.hadsQuestion, snapshot.hads_question_text || "");

  renderHadsOptions(snapshot, idx);

  const isRecording = Boolean(snapshot.hads_recording);
  setHidden(el.hadsMic, !isRecording);
  if (el.hadsStatus) {
    const msg = snapshot.message || "";
    el.hadsStatus.textContent = isRecording ? "" : msg;
  }

  // Auto-play TTS prompt when server sends hads_tts_text
  if (snapshot.hads_tts_text) {
    const ttsKey = snapshot.hads_tts_id || snapshot.hads_tts_text;
    if (ttsKey !== window._lastHadsTts) {
      window._lastHadsTts = ttsKey;
      _hadsPlayTts(snapshot.hads_tts_text, snapshot.hads_tts_id || "");
    }
  }
}

function renderHadsOptions(snapshot, questionIndex) {
  if (!el.hadsOptions) return;

  const options = Array.isArray(snapshot.hads_options) ? snapshot.hads_options : [];
  const selected = snapshot.hads_selected_option;
  const questionKey = `${snapshot.hads_question_id || ""}:${questionIndex}`;

  // Rebuild buttons only when the question changes; otherwise just update state
  if (el.hadsOptions.dataset.questionKey !== questionKey) {
    el.hadsOptions.dataset.questionKey = questionKey;
    el.hadsOptions.innerHTML = "";
    options.forEach((text, optionIndex) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "hads-option";
      const num = document.createElement("span");
      num.className = "hads-option-num";
      num.textContent = String(optionIndex + 1);
      const label = document.createElement("span");
      label.textContent = text;
      button.append(num, label);
      button.addEventListener("click", () => {
        submitHadsAnswer(questionIndex, optionIndex);
      });
      el.hadsOptions.appendChild(button);
    });
  }

  const buttons = el.hadsOptions.querySelectorAll(".hads-option");
  buttons.forEach((button, optionIndex) => {
    button.classList.toggle("selected", selected === optionIndex);
    button.disabled = selected != null;
  });
}

async function submitHadsAnswer(questionIndex, optionIndex) {
  try {
    await fetch("/api/actions/hads_answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_index: questionIndex, option_index: optionIndex }),
    });
  } catch (error) {
    appendLogLine(`[hads] answer error: ${error.message || error}`);
  }
}

async function stopHadsTest() {
  try {
    await fetch("/api/actions/stop_hads", { method: "POST" });
  } catch (_) {}
}

async function _hadsNotifyTtsFinished(ttsId) {
  if (!ttsId) return;
  try {
    await fetch("/api/actions/hads_tts_finished", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hads_tts_id: ttsId }),
    });
  } catch (_) {}
}

async function _hadsPlayTts(text, ttsId) {
  // Sequence guard: stopHadsAudio() bumps the sequence, invalidating any
  // older in-flight synthesis; we adopt the fresh number for this prompt.
  // If the number moves on (newer prompt or test stopped), discard our audio.
  stopHadsAudio();
  const seq = window._hadsTtsSeq;

  try {
    const resp = await fetch("/api/tts/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) return;
    const blob = await resp.blob();
    if (seq !== window._hadsTtsSeq) return; // superseded or stopped
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    window._currentHadsAudio = audio;
    const playbackDone = new Promise((resolve) => {
      audio.onended = resolve;
      audio.onerror = resolve;
      audio.onabort = resolve;
    });
    await audio.play();
    await playbackDone;
    URL.revokeObjectURL(url);
    if (window._currentHadsAudio === audio) window._currentHadsAudio = null;
  } catch (_) {
  } finally {
    await _hadsNotifyTtsFinished(ttsId);
  }
}

// ---- «Мои результаты» ----

const REPORT_TYPE_LABELS = {
  screening: "Базовая проверка",
  hads: "Тест на тревожность",
  moca: "Тест MoCA",
  appearance: "Оценка внешности",
};

// betterWhen: "lower" — чем меньше, тем лучше; "higher" — наоборот; null — нейтрально
function extractResultMetrics(item) {
  const domains = (item && item.domains) || {};
  const metrics = [];
  if (domains.hads_anxiety_score != null) {
    metrics.push({
      key: "anxiety",
      label: "Тревога",
      value: Number(domains.hads_anxiety_score),
      max: Number(domains.hads_anxiety_max || 21),
      betterWhen: "lower",
    });
  }
  if (domains.hads_depression_score != null) {
    metrics.push({
      key: "depression",
      label: "Депрессия",
      value: Number(domains.hads_depression_score),
      max: Number(domains.hads_depression_max || 21),
      betterWhen: "lower",
    });
  }
  if (domains.moca_score != null) {
    metrics.push({
      key: "moca",
      label: "MoCA",
      value: Number(domains.moca_score),
      max: Number(domains.moca_max_score || 0) || null,
      betterWhen: "higher",
    });
  }
  if (domains.heart_rate_bpm != null) {
    metrics.push({
      key: "pulse",
      label: "Пульс",
      value: Math.round(Number(domains.heart_rate_bpm)),
      unit: "уд/мин",
      betterWhen: null,
    });
  }
  return metrics;
}

function findPreviousMetric(items, startIndex, reportType, metricKey) {
  for (let i = startIndex + 1; i < items.length; i += 1) {
    if (items[i].report_type !== reportType) continue;
    const previous = extractResultMetrics(items[i]).find((m) => m.key === metricKey);
    if (previous) return previous;
  }
  return null;
}

function trendBadge(metric, previous) {
  if (!previous || metric.betterWhen == null) return "";
  const delta = metric.value - previous.value;
  if (delta === 0) {
    return '<span class="result-trend same">— так же</span>';
  }
  const improved = metric.betterWhen === "lower" ? delta < 0 : delta > 0;
  const arrow = delta < 0 ? "▼" : "▲";
  const word = improved ? "лучше" : "хуже";
  const cls = improved ? "better" : "worse";
  return `<span class="result-trend ${cls}">${arrow} ${word}</span>`;
}

function formatResultDate(isoText) {
  const date = new Date(isoText);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}, ${date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

function resultInterpretations(item) {
  const summary = (item && item.summary) || {};
  return [
    summary.hads_anxiety_interpretation,
    summary.hads_depression_interpretation,
    summary.moca_interpretation,
    summary.hads_notes,
    summary.limitations,
  ].filter(Boolean).join(" · ");
}

function renderResults(items) {
  if (!el.resultsList) return;

  // Only medically meaningful records (tests with numbers)
  const testItems = items.filter((item) => extractResultMetrics(item).length > 0);

  if (testItems.length === 0) {
    el.resultsList.innerHTML =
      '<p class="placeholder-text">Результатов пока нет. Пройдите проверку — они появятся здесь.</p>';
    return;
  }

  const cards = testItems.map((item, index) => {
    const typeLabel = REPORT_TYPE_LABELS[item.report_type] || item.report_type || "Проверка";
    const dateLabel = formatResultDate(item.stored_at);
    const metricTiles = extractResultMetrics(item).map((metric) => {
      const previous = findPreviousMetric(testItems, index, item.report_type, metric.key);
      const maxPart = metric.max ? ` <small>/ ${metric.max}</small>` : "";
      const unitPart = metric.unit ? ` <small>${escapeHtml(metric.unit)}</small>` : "";
      return `
        <div class="result-metric">
          <span class="result-metric-label">${escapeHtml(metric.label)}</span>
          <strong class="result-metric-value">${metric.value}${maxPart}${unitPart}</strong>
          ${trendBadge(metric, previous)}
        </div>`;
    }).join("");
    const note = resultInterpretations(item);
    return `
      <article class="result-card">
        <div class="result-card-head">
          <strong>${escapeHtml(typeLabel)}</strong>
          <span class="result-date mono">${escapeHtml(dateLabel)}</span>
        </div>
        <div class="result-metrics">${metricTiles}</div>
        ${note ? `<p class="result-note">${escapeHtml(note)}</p>` : ""}
      </article>`;
  });

  el.resultsList.innerHTML = cards.join("");
}

async function openResults() {
  if (!el.resultsPanel) return;
  if (!state.activeUser) {
    setText(el.messageValue, "Сначала выберите пользователя.");
    return;
  }
  setHidden(el.resultsPanel, false);
  if (el.resultsSub) {
    setText(el.resultsSub, `${state.activeUser.name} — история проверок`);
  }
  if (el.resultsList) {
    el.resultsList.innerHTML = '<p class="placeholder-text">Загружаю...</p>';
  }
  try {
    const data = await fetchJson("/api/results");
    renderResults(data.items || []);
  } catch (error) {
    if (el.resultsList) {
      el.resultsList.innerHTML =
        `<p class="placeholder-text">Не удалось загрузить результаты: ${escapeHtml(error.message || String(error))}</p>`;
    }
  }
}

function closeResults() {
  setHidden(el.resultsPanel, true);
}

// ---- Контроль условий сессии (ТЗ 6.3.2) ----

// Какие проверки нужны каждому сценарию; required — без чего запуск заблокирован
const CHECK_REQUIREMENTS = {
  screening: { camera: true, face: true, mic: true, voice: true, required: ["camera", "face"] },
  moca: { camera: false, face: false, mic: true, voice: true, required: ["mic", "voice"] },
  // HADS можно пройти нажатием — микрофон желателен, но не обязателен
  hads: { camera: false, face: false, mic: true, voice: true, required: [] },
};

const CHECK_NAMES = ["camera", "face", "mic", "voice"];

const sessionCheck = {
  scenario: null,
  results: {},
  running: false,
  audioStream: null,
  audioCtx: null,
  analyser: null,
};

function checkItemEl(name) {
  return document.querySelector(`.check-item[data-check="${name}"]`);
}

function setCheckItem(name, checkState, note) {
  const item = checkItemEl(name);
  if (item) {
    setHidden(item, false);
    const icon = item.querySelector(".check-icon");
    if (icon) icon.dataset.state = checkState;
  }
  const noteEl = $(`check-note-${name}`);
  if (noteEl) setText(noteEl, note || "");
  sessionCheck.results[name] = {
    ...(sessionCheck.results[name] || {}),
    state: checkState,
    note: note || "",
  };
}

async function openSessionCheck(scenario) {
  if (!el.checkPanel) return;
  sessionCheck.scenario = scenario;
  sessionCheck.results = {};

  const req = CHECK_REQUIREMENTS[scenario] || CHECK_REQUIREMENTS.hads;
  for (const name of CHECK_NAMES) {
    const item = checkItemEl(name);
    if (item) {
      setHidden(item, !req[name]);
      const icon = item.querySelector(".check-icon");
      if (icon) icon.dataset.state = "idle";
    }
    const noteEl = $(`check-note-${name}`);
    if (noteEl) setText(noteEl, "");
  }
  setText(el.checkStatus, "");
  setDisabled(el.checkStart, true);
  setHidden(el.checkRetry, true);
  setHidden(el.checkPanel, false);

  runSessionChecks().catch((error) => {
    setText(el.checkStatus, `Ошибка проверки: ${error.message || error}`);
    setHidden(el.checkRetry, false);
  });
}

function closeSessionCheck() {
  stopCheckAudio();
  setHidden(el.checkPanel, true);
}

async function runSessionChecks() {
  if (sessionCheck.running) return;
  sessionCheck.running = true;
  const req = CHECK_REQUIREMENTS[sessionCheck.scenario] || CHECK_REQUIREMENTS.hads;
  try {
    if (req.camera) await checkCameraAndFace();
    if (req.mic) await checkMicAndNoise();
    if (req.voice) await checkVoiceSample();
  } finally {
    stopCheckAudio();
    sessionCheck.running = false;
  }
  finalizeSessionCheck();
}

function captureCameraFrame() {
  const video = el.cameraPreview;
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
  setCheckItem("camera", "wait", "Включаю камеру...");
  if (!state.cameraActive) {
    try {
      await toggleCamera();
    } catch (_) {
      // toggleCamera сам показывает ошибку
    }
  }
  if (!state.cameraActive) {
    setCheckItem("camera", "fail", "Камера недоступна. Проверьте подключение и разрешение в браузере.");
    setCheckItem("face", "fail", "Без камеры проверить лицо и свет нельзя.");
    return;
  }
  setCheckItem("camera", "ok", "Камера работает");

  setCheckItem("face", "wait", "Смотрю на кадр...");
  // Пауза, чтобы автоэкспозиция камеры успела подстроиться
  await new Promise((resolve) => setTimeout(resolve, 900));
  const frame = captureCameraFrame();
  if (!frame) {
    setCheckItem("face", "fail", "Не удалось получить кадр с камеры.");
    return;
  }
  let data;
  try {
    data = await fetchJson("/api/session/check-face", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_base64: frame }),
    });
  } catch (error) {
    setCheckItem("face", "fail", `Проверка кадра не удалась: ${error.message || error}`);
    return;
  }
  sessionCheck.results.face = { ...(sessionCheck.results.face || {}), data };

  const advice = (data.advice || []).join(" ");
  if (data.face_detected && data.brightness_ok && data.face_close_enough) {
    setCheckItem("face", "ok", advice || "Лицо видно, света достаточно");
  } else if (data.face_detected && data.brightness_ok) {
    // Только дистанция — предупреждение, не блокируем
    setCheckItem("face", "warn", advice || "Приблизьтесь к экрану.");
  } else {
    setCheckItem("face", "fail", advice || "Поправьте положение и освещение, затем проверьте снова.");
  }
}

function setupCheckAnalyser(stream) {
  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtor) return false;
  sessionCheck.audioCtx = new AudioCtor();
  const source = sessionCheck.audioCtx.createMediaStreamSource(stream);
  sessionCheck.analyser = sessionCheck.audioCtx.createAnalyser();
  sessionCheck.analyser.fftSize = 2048;
  source.connect(sessionCheck.analyser);
  return true;
}

function stopCheckAudio() {
  if (sessionCheck.audioStream) {
    for (const track of sessionCheck.audioStream.getTracks()) track.stop();
    sessionCheck.audioStream = null;
  }
  if (sessionCheck.audioCtx) {
    sessionCheck.audioCtx.close().catch(() => {});
    sessionCheck.audioCtx = null;
  }
  sessionCheck.analyser = null;
}

async function measureRms(durationMs, mode) {
  const analyser = sessionCheck.analyser;
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
    await new Promise((resolve) => setTimeout(resolve, 60));
  }
  if (samples.length === 0) return 0;
  if (mode === "peak") return Math.max(...samples);
  return samples.reduce((a, b) => a + b, 0) / samples.length;
}

async function checkMicAndNoise() {
  setCheckItem("mic", "wait", "Проверяю микрофон...");
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    setCheckItem("mic", "fail", "Микрофон недоступен. Проверьте подключение и разрешение в браузере.");
    setCheckItem("voice", "fail", "Без микрофона проба голоса невозможна.");
    return;
  }
  sessionCheck.audioStream = stream;
  if (!setupCheckAnalyser(stream)) {
    setCheckItem("mic", "warn", "Микрофон подключён, но замерить уровень звука не удалось.");
    return;
  }

  setCheckItem("mic", "wait", "Побудьте в тишине — замеряю фоновый шум...");
  const noise = await measureRms(1800, "avg");
  sessionCheck.results.mic = { ...(sessionCheck.results.mic || {}), noise };

  if (noise < 0.025) {
    setCheckItem("mic", "ok", "Микрофон работает, фон тихий");
  } else if (noise < 0.06) {
    setCheckItem("mic", "warn", "Слышен фоновый шум — по возможности уберите его.");
  } else {
    setCheckItem("mic", "warn", "Сильный фоновый шум — выключите телевизор или музыку.");
  }
}

async function checkVoiceSample() {
  if (!sessionCheck.analyser) {
    if ((sessionCheck.results.voice || {}).state !== "fail") {
      setCheckItem("voice", "fail", "Проба голоса недоступна без микрофона.");
    }
    return;
  }
  setCheckItem("voice", "wait", "Скажите вслух: «раз, два, три»");
  const voice = await measureRms(4000, "peak");
  const noise = (sessionCheck.results.mic || {}).noise || 0;
  sessionCheck.results.voice = { ...(sessionCheck.results.voice || {}), level: voice };

  if (voice > Math.max(0.04, noise * 2.2)) {
    setCheckItem("voice", "ok", "Голос слышно хорошо");
  } else {
    setCheckItem("voice", "fail", "Голос слишком тихий — сядьте ближе, говорите громче и проверьте снова.");
  }
}

function finalizeSessionCheck() {
  const req = CHECK_REQUIREMENTS[sessionCheck.scenario] || CHECK_REQUIREMENTS.hads;
  const stateOf = (name) => (sessionCheck.results[name] || {}).state || "idle";
  const failedRequired = req.required.filter((name) => stateOf(name) === "fail");
  const anyFail = CHECK_NAMES.some((name) => req[name] && stateOf(name) === "fail");

  setHidden(el.checkRetry, false);
  if (failedRequired.length > 0) {
    setDisabled(el.checkStart, true);
    setText(el.checkStatus, "Исправьте отмеченное красным и нажмите «Проверить снова».");
    return;
  }
  setDisabled(el.checkStart, false);
  if (anyFail && sessionCheck.scenario === "hads") {
    setText(el.checkStatus, "Голос недоступен — можно начинать, отвечать будете нажатием на варианты.");
  } else if (anyFail) {
    setText(el.checkStatus, "Часть проверок не пройдена — результат может быть ограничен.");
  } else {
    setText(el.checkStatus, "Всё готово — нажмите «Начать тест».");
  }
}

function collectSessionConditions() {
  const stateOf = (name) => (sessionCheck.results[name] || {}).state || "skipped";
  const faceData = (sessionCheck.results.face || {}).data || {};
  const req = CHECK_REQUIREMENTS[sessionCheck.scenario] || {};
  const conditions = {
    scenario: sessionCheck.scenario,
    checked_at: new Date().toISOString(),
  };
  if (req.camera) {
    conditions.camera_ok = stateOf("camera") === "ok";
    conditions.face_detected = Boolean(faceData.face_detected);
    conditions.face_close_enough = Boolean(faceData.face_close_enough);
    conditions.brightness = faceData.brightness ?? null;
    conditions.brightness_ok = Boolean(faceData.brightness_ok);
  }
  if (req.mic) {
    conditions.mic_ok = stateOf("mic") !== "fail";
    conditions.noise_level = Number(((sessionCheck.results.mic || {}).noise || 0).toFixed(4));
    conditions.noise_ok = stateOf("mic") === "ok";
  }
  if (req.voice) {
    conditions.voice_ok = stateOf("voice") === "ok";
    conditions.voice_level = Number(((sessionCheck.results.voice || {}).level || 0).toFixed(4));
  }
  return conditions;
}

async function startCheckedTest() {
  const scenario = sessionCheck.scenario;
  const conditions = collectSessionConditions();
  closeSessionCheck();
  try {
    await unlockAudioPlayback();
  } catch (_) {}
  try {
    switch (scenario) {
      case "screening":
        await startScreening(conditions);
        break;
      case "moca":
        await fetchJson("/api/actions/start_moca", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_conditions: conditions }),
        });
        break;
      case "hads":
        await fetchJson("/api/actions/start_hads", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_conditions: conditions }),
        });
        break;
      default:
        break;
    }
  } catch (error) {
    setText(el.messageValue, `Не удалось запустить тест: ${error.message || error}`);
    appendLogLine(`[check] start ${scenario} error: ${error.message || error}`);
  }
}

function bindSessionCheckEvents() {
  el.checkStart && el.checkStart.addEventListener("click", startCheckedTest);
  el.checkRetry && el.checkRetry.addEventListener("click", () => {
    openSessionCheck(sessionCheck.scenario);
  });
  el.checkCancel && el.checkCancel.addEventListener("click", closeSessionCheck);
}

// ---- Main menu ----

function openMainMenu() {
  if (!el.mainMenu) return;
  setHidden(el.mainMenu, false);
}

function closeMainMenu() {
  if (!el.mainMenu) return;
  setHidden(el.mainMenu, true);
}

async function handleMenuAction(item) {
  closeMainMenu();
  try {
    switch (item) {
      // Тесты запускаются только через проверку условий сессии (ТЗ 6.3.2)
      case "screening":
      case "moca":
      case "hads":
        await unlockAudioPlayback().catch(() => {});
        await openSessionCheck(item);
        break;
      case "training":
        setText(el.messageValue, "Режим «Тренировка» пока в разработке.");
        break;
      case "report":
        await openResults();
        break;
      case "about": {
        const config = state.config || {};
        const scenarios = config.scenario_versions || {};
        const parts = [
          `«Нейро-зеркало» — версия ${config.app_version || "?"}.`,
          scenarios.screening ? `Сценарий скрининга ${scenarios.screening},` : "",
          scenarios.moca ? `MoCA ${scenarios.moca},` : "",
          scenarios.hads ? `HADS ${scenarios.hads}.` : "",
          config.assistant_backend_label ? `Ассистент: ${config.assistant_backend_label}.` : "",
          "Результаты являются скрининговой информацией и не заменяют консультацию врача.",
        ].filter(Boolean);
        setText(el.messageValue, parts.join(" "));
        break;
      }
      default:
        break;
    }
  } catch (error) {
    setText(el.messageValue, `Не удалось выполнить действие: ${error.message || error}`);
    appendLogLine(`[menu] ${item} error: ${error.message || error}`);
  }
}

function bindMainMenuEvents() {
  el.menuButton && el.menuButton.addEventListener("click", openMainMenu);
  el.mainMenuClose && el.mainMenuClose.addEventListener("click", closeMainMenu);
  el.mainMenu && el.mainMenu.addEventListener("click", (event) => {
    if (event.target === el.mainMenu) closeMainMenu();
  });
  for (const item of document.querySelectorAll(".menu-item[data-menu]")) {
    item.addEventListener("click", () => handleMenuAction(item.dataset.menu));
  }
  for (const item of document.querySelectorAll(".dock-item[data-dock]")) {
    item.addEventListener("click", () => handleMenuAction(item.dataset.dock));
  }
  el.hadsStop && el.hadsStop.addEventListener("click", stopHadsTest);
  el.resultsClose && el.resultsClose.addEventListener("click", closeResults);
  el.resultsPanel && el.resultsPanel.addEventListener("click", (event) => {
    if (event.target === el.resultsPanel) closeResults();
  });
  bindSessionCheckEvents();
}

function cleanupSpeechAudio() {
  if (state.currentSpeechAudio) {
    state.currentSpeechAudio.pause();
    state.currentSpeechAudio.removeAttribute("src");
    state.currentSpeechAudio.load();
    state.currentSpeechAudio = null;
  }
  if (state.currentSpeechUrl) {
    URL.revokeObjectURL(state.currentSpeechUrl);
    state.currentSpeechUrl = null;
  }
  if (state.audioContext) {
    state.audioContext.close().catch(() => {});
    state.audioContext = null;
  }
  state.analyser = null;
  setMascotState("idle");
}

function animateMouth() {
  if (!state.analyser || !el.mascotMouth) return;

  const values = new Uint8Array(state.analyser.frequencyBinCount);

  const tick = () => {
    if (!state.analyser || !el.mascotMouth) return;
    state.analyser.getByteFrequencyData(values);
    let total = 0;
    for (const value of values) total += value;
    const average = total / values.length;
    const height = Math.max(8, Math.min(30, average / 4));
    const width = 32 + height / 2;
    el.mascotMouth.style.height = `${height}px`;
    el.mascotMouth.style.width = `${width}px`;
    requestAnimationFrame(tick);
  };

  requestAnimationFrame(tick);
}

async function maybeSpeak(snapshot) {
  if (!state.ttsEnabled) return;
  if (!snapshot.message || !snapshot.assistant_source) return;
  if (snapshot.message === state.lastSpokenText) return;

  // Speak assistant replies, summaries and screening instructions —
  // skip other status/system messages (tests speak through their own channel)
  const screen = snapshot.screen || "";
  if (screen !== "assistant" && screen !== "summary" && screen !== "screening") return;

  // Skip intermediate/status messages — only speak final assistant replies
  const source = String(snapshot.assistant_source || "").toLowerCase();
  if (source === "обработка запроса" || source === "ошибка ассистента") return;

  const messageText = String(snapshot.message || "").trim().toLowerCase();
  // Skip transcription echoes, status lines, and intermediate processing messages
  if (
    messageText.startsWith("обрабатываю запрос") ||
    messageText.startsWith("запрос распознан") ||
    messageText.startsWith("сейчас оцениваю") ||
    messageText.startsWith("сейчас посмотрю") ||
    messageText.startsWith("анализирую кадр") ||
    messageText.startsWith("распознан текст:") ||
    messageText.startsWith("распознано неуверенно") ||
    messageText.startsWith("речь не распознана") ||
    messageText.startsWith("запускаю скрининг") ||
    messageText.includes("речь распознана неуверенно") ||
    messageText.includes("это может занять")
  ) {
    return;
  }

  state.lastSpokenText = snapshot.message;
  setMascotSpeech(snapshot.message, { visible: false });

  const spokenText = stripTrailingSpeechMeta(snapshot.message);
  if (!spokenText) return;

  // Cancel any playing speech before starting new one
  const requestId = state.ttsRequestId + 1;
  state.ttsRequestId = requestId;
  cleanupSpeechAudio();

  try {
    const response = await fetch("/api/tts/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: spokenText }),
    });

    if (!response.ok) {
      throw new Error((await response.text()) || `${response.status}`);
    }

    const audioBlob = await response.blob();
    if (!audioBlob.size) throw new Error("empty TTS audio");
    if (requestId !== state.ttsRequestId) return;

    const objectUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(objectUrl);
    state.currentSpeechAudio = audio;
    state.currentSpeechUrl = objectUrl;

    audio.addEventListener("ended", () => {
      if (state.currentSpeechAudio === audio) cleanupSpeechAudio();
    }, { once: true });
    audio.addEventListener("error", () => {
      if (state.currentSpeechAudio === audio) cleanupSpeechAudio();
    }, { once: true });

    setupAudioAnalyser(audio);
    setMascotState("speaking");
    await audio.play();
  } catch (error) {
    if (requestId === state.ttsRequestId) cleanupSpeechAudio();
    setText(el.mascotNote, "Click the page once to unlock browser audio.");
    console.error("TTS error", error);
  }
}

function setupAudioAnalyser(audio) {
  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtor) return;

  try {
    const context = new AudioCtor();
    if (context.state === "suspended") {
      context.resume();
    }
    const source = context.createMediaElementSource(audio);
    const analyser = context.createAnalyser();
    analyser.fftSize = 128;
    source.connect(analyser);
    analyser.connect(context.destination);
    state.audioContext = context;
    state.analyser = analyser;
    animateMouth();
  } catch (_) {
    cleanupSpeechAudio();
  }
}

function connectWebSocket() {
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
  if (state.pingTimer) {
    clearInterval(state.pingTimer);
    state.pingTimer = null;
  }

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/ws/app`);
  state.websocket = socket;

  socket.addEventListener("open", () => {
    el.connectionDot && el.connectionDot.classList.add("connected");
    if (el.connectionDot) el.connectionDot.title = "WebSocket connected";
    appendLogLine("[client] websocket connected");
    state.pingTimer = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 15000);
  });

  socket.addEventListener("message", async (event) => {
    const packet = JSON.parse(event.data);
    if (!packet || !packet.payload) return;
    renderSnapshot(packet.payload);
    await maybeSpeak(packet.payload);
  });

  socket.addEventListener("close", () => {
    el.connectionDot && el.connectionDot.classList.remove("connected");
    if (el.connectionDot) el.connectionDot.title = "WebSocket disconnected";
    appendLogLine("[client] websocket closed");
    if (state.pingTimer) {
      clearInterval(state.pingTimer);
      state.pingTimer = null;
    }
    state.reconnectTimer = setTimeout(connectWebSocket, 1500);
  });

  socket.addEventListener("error", () => {
    el.connectionDot && el.connectionDot.classList.remove("connected");
    appendLogLine("[client] websocket error");
  });
}

function updateBrowserCameraModuleStatus(active) {
  if (!el.modulesValue) return;
  const cameraRow = el.modulesValue.querySelector('[data-module="camera"]');
  if (cameraRow) {
    const dot = cameraRow.querySelector('.module-dot');
    const detail = cameraRow.querySelector('.module-detail');
    if (dot) {
      dot.classList.toggle('ok', active);
      dot.classList.toggle('fail', !active);
    }
    if (detail) {
      detail.textContent = active ? 'Камера браузера активна' : 'Камера выключена';
    }
  }
}

function stopCamera() {
  if (state.mediaStream) {
    for (const track of state.mediaStream.getTracks()) {
      track.stop();
    }
  }
  state.mediaStream = null;
  state.cameraActive = false;

  if (el.cameraPreview) {
    try {
      el.cameraPreview.pause();
    } catch (_) {
      // ignore
    }
    el.cameraPreview.srcObject = null;
  }

  setCameraOverlay("Camera is off");
  setButtonLabel(el.cameraToggle, "Turn camera on");
  setDisabled(el.appearanceButton, true);
  updateBrowserCameraModuleStatus(false);
}

async function toggleCamera() {
  if (state.cameraActive) {
    stopCamera();
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setCameraOverlay("Browser camera API is unavailable");
    return;
  }

  try {
    await unlockAudioPlayback();
  } catch (_) {
    // ignore unlock failure
  }

  // Ask the backend to release its camera worker first. Even if this fails
  // (e.g. the worker takes longer than the server-side wait), the browser
  // camera is independent — proceed and let getUserMedia report real problems.
  try {
    const releaseResult = await fetchJson("/api/actions/release_camera", { method: "POST" });
    appendLogLine(`[client] backend camera release: ${JSON.stringify(releaseResult.worker_statuses || {})}`);
    await new Promise((resolve) => setTimeout(resolve, 120));
  } catch (error) {
    appendLogLine(`[client] backend camera release failed (continuing): ${error.message || error}`);
    // Give the worker a moment to finish releasing in the background
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  setButtonLoading(el.cameraToggle, true);
  setCameraOverlay("Connecting camera...");

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: "user",
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    });

    const track = stream.getVideoTracks()[0];
    if (!track) {
      throw new Error("no video track returned");
    }

    if (!el.cameraPreview) {
      throw new Error("camera preview element is missing");
    }

    state.mediaStream = stream;
    el.cameraPreview.srcObject = stream;
    el.cameraPreview.muted = true;
    el.cameraPreview.playsInline = true;

    try {
      await el.cameraPreview.play();
    } catch (_) {
      // wait for metadata
    }

    await waitForVideoReady(el.cameraPreview, 7000);

    if (el.cameraPreview.paused) {
      await el.cameraPreview.play();
    }

    state.cameraActive = true;
    setHidden(el.cameraOverlay, true);
    setButtonLabel(el.cameraToggle, "Turn camera off");
    setDisabled(el.appearanceButton, false);
    updateBrowserCameraModuleStatus(true);
    appendLogLine(`[client] camera ready: ${JSON.stringify(track.getSettings ? track.getSettings() : {})}`);
  } catch (error) {
    const details = describeMediaError(error);
    stopCamera();
    setCameraOverlay(`Camera error: ${details}`);
    appendLogLine(`[client] camera error: ${details}`);
  } finally {
    setButtonLoading(el.cameraToggle, false);
  }
}

async function analyzeAppearance() {
  if (!state.cameraActive || !el.cameraPreview) {
    setCameraOverlay("Turn on the camera first");
    return;
  }

  setButtonLoading(el.appearanceButton, true);
  state.busy = true;
  setMascotState("thinking");
  const pendingSnapshot = {
    screen: "assistant",
    message: "Сейчас оцениваю внешний вид по кадру. Это может занять несколько секунд.",
    assistant_source: "visual analysis",
    transcript_text: "",
    report: null,
    worker_statuses: {},
    event_log: [],
  };
  renderSnapshot(pendingSnapshot);

  try {
    const canvas = document.createElement("canvas");
    canvas.width = el.cameraPreview.videoWidth || 640;
    canvas.height = el.cameraPreview.videoHeight || 480;

    const context = canvas.getContext("2d");
    if (!context) {
      throw new Error("2d canvas context is unavailable");
    }
    context.drawImage(el.cameraPreview, 0, 0, canvas.width, canvas.height);

    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((value) => {
        if (value) resolve(value);
        else reject(new Error("failed to encode frame"));
      }, "image/jpeg", 0.92);
    });

    const formData = new FormData();
    formData.append("image", blob, "frame.jpg");

    const response = await fetch("/api/appearance/analyze", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error((await response.text()) || `${response.status}`);
    }

    const payload = await response.json();
    const snapshot = {
      screen: "summary",
      message: payload.reply,
      assistant_source: "visual analysis",
      transcript_text: "",
      report: payload.report,
      worker_statuses: {},
      event_log: [],
    };
    renderSnapshot(snapshot);
    await maybeSpeak(snapshot);
  } catch (error) {
    setText(el.messageValue, `Appearance analysis failed: ${error.message || error}`);
    appendLogLine(`[client] appearance error: ${error.message || error}`);
  } finally {
    state.busy = false;
    setButtonLoading(el.appearanceButton, false);
  }
}

async function captureFrameAsBase64() {
  if (!state.cameraActive || !el.cameraPreview) {
    return null;
  }
  const canvas = document.createElement("canvas");
  canvas.width = el.cameraPreview.videoWidth || 640;
  canvas.height = el.cameraPreview.videoHeight || 480;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.drawImage(el.cameraPreview, 0, 0, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
  // Strip the "data:image/jpeg;base64," prefix
  return dataUrl.split(",")[1] || null;
}

async function cameraVisionQuery(userText) {
  const imageBase64 = await captureFrameAsBase64();
  if (!imageBase64) {
    setText(el.messageValue, "Включите камеру, чтобы ассистент мог посмотреть на кадр.");
    appendLogLine("[client] camera_vision_query: camera is not active");
    return;
  }

  state.busy = true;
  setMascotState("thinking");
  setText(el.messageValue, "Анализирую кадр с камеры...");

  try {
    const result = await fetchJson("/api/camera/vision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: userText, image_base64: imageBase64 }),
    });

    const snapshot = {
      screen: "assistant",
      message: result.reply,
      assistant_source: result.backend || "vision:камера",
      transcript_text: "",
      report: null,
      worker_statuses: {},
      event_log: [],
    };
    renderSnapshot(snapshot);
    await maybeSpeak(snapshot);
  } catch (error) {
    setText(el.messageValue, `Vision request failed: ${error.message || error}`);
    appendLogLine(`[client] camera vision error: ${error.message || error}`);
  } finally {
    state.busy = false;
  }
}

function autoGrowAssistantInput() {
  const input = el.assistantInput;
  if (!input) return;
  input.style.height = "auto";
  const grownHeight = Math.min(input.scrollHeight, 120);
  input.style.height = `${grownHeight}px`;
  // Show the scrollbar only when the text no longer fits the max height
  input.style.overflowY = input.scrollHeight > 120 ? "auto" : "hidden";
}

async function submitAssistantMessage(event) {
  event.preventDefault();
  const text = el.assistantInput ? el.assistantInput.value.trim() : "";
  if (!text) return;

  try {
    await unlockAudioPlayback();
  } catch (_) {
    // ignore unlock failure
  }

  setButtonLoading(el.askButton, true);
  state.busy = true;
  setMascotState("thinking");
  setText(el.messageValue, "Processing request...");

  try {
    const payload = await fetchJson("/api/assistant/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    if (payload.command === "analyze_appearance") {
      await analyzeAppearance();
    } else if (payload.command === "camera_vision_query") {
      await cameraVisionQuery(text);
    }
  } catch (error) {
    setText(el.messageValue, `Assistant request failed: ${error.message || error}`);
    appendLogLine(`[client] assistant error: ${error.message || error}`);
  } finally {
    state.busy = false;
    setButtonLoading(el.askButton, false);
  }
}

async function startScreening(sessionConditions) {
  try {
    await unlockAudioPlayback();
  } catch (_) {}

  // Camera must be active to stream frames for rPPG
  if (!state.cameraActive) {
    setText(el.messageValue, "Включите камеру перед запуском скрининга.");
    appendLogLine("[screening] camera not active, skipping");
    return;
  }

  setButtonLoading(el.screeningButton, true);
  try {
    // Tell server screening is starting (shows screening screen on UI)
    await fetchJson("/api/actions/start_screening", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_conditions: sessionConditions || null }),
    });
  } catch (error) {
    setText(el.messageValue, `Screening start failed: ${error.message || error}`);
    appendLogLine(`[client] screening error: ${error.message || error}`);
    setButtonLoading(el.screeningButton, false);
    return;
  }

  // Stream camera frames to /ws/rppg — camera stays active in browser
  await _streamRppgFrames();
  setButtonLoading(el.screeningButton, false);
}

async function _streamRppgFrames() {
  const DURATION_MS = 20000;
  const FPS = 15;
  const INTERVAL_MS = Math.round(1000 / FPS);
  const MAX_FRAMES = Math.ceil((DURATION_MS / 1000) * FPS);

  const videoEl = el.cameraPreview;
  if (!videoEl || !state.cameraActive) {
    appendLogLine("[screening] no camera stream, skipping rPPG frame capture");
    return;
  }

  // Use offscreen canvas to capture JPEG frames from the <video> element
  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 240;
  const ctx2d = canvas.getContext("2d");

  const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${wsProto}//${location.host}/ws/rppg`;
  let ws;
  try {
    ws = new WebSocket(wsUrl);
  } catch (err) {
    appendLogLine(`[screening] WebSocket open failed: ${err.message || err}`);
    return;
  }

  await new Promise((resolve) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", resolve, { once: true });
  });

  if (ws.readyState !== WebSocket.OPEN) {
    appendLogLine("[screening] WebSocket not open, skipping frame stream");
    return;
  }

  appendLogLine(`[screening] streaming ${MAX_FRAMES} frames to server (~${DURATION_MS / 1000}s)`);
  let sent = 0;

  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.done) {
        appendLogLine(`[screening] rPPG done: bpm=${msg.heart_rate_bpm} status=${msg.heart_rate_status}`);
      } else if (msg.received != null) {
        // progress ack — silent
      }
    } catch (_) {}
  });

  const startedAt = Date.now();
  while (sent < MAX_FRAMES && ws.readyState === WebSocket.OPEN) {
    try {
      ctx2d.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.75));
      if (blob && ws.readyState === WebSocket.OPEN) {
        const buf = await blob.arrayBuffer();
        ws.send(buf);
        sent++;
      }
    } catch (err) {
      appendLogLine(`[screening] frame capture error: ${err.message || err}`);
      break;
    }

    const elapsed = Date.now() - startedAt;
    const expected = sent * INTERVAL_MS;
    const delay = Math.max(0, expected - elapsed);
    if (delay > 0) await new Promise((r) => setTimeout(r, delay));
  }

  appendLogLine(`[screening] sent ${sent} frames, waiting for rPPG result…`);
  // Give server time to finish processing and close; wait up to 60s
  if (ws.readyState === WebSocket.OPEN) {
    await new Promise((resolve) => {
      const timer = setTimeout(() => { ws.close(); resolve(); }, 60000);
      ws.addEventListener("close", () => { clearTimeout(timer); resolve(); }, { once: true });
    });
  }
}

function stopPulseMonitor() {
  if (state.hrMonitorAbort) {
    state.hrMonitorAbort();
    state.hrMonitorAbort = null;
  }
  state.hrMonitoring = false;
  if (el.hrMonitorBtn) {
    el.hrMonitorBtn.textContent = "♥ Мониторинг";
    el.hrMonitorBtn.classList.remove("monitoring");
  }
  _hrProgressHide();
  appendLogLine("[hr] pulse monitor stopped");
}

function _hrProgressShow(totalSeconds) {
  if (!el.hrProgressWrap) return;
  setHidden(el.hrProgressWrap, false);
  if (el.hrProgressBar) el.hrProgressBar.style.width = "0%";
  if (el.hrProgressLabel) el.hrProgressLabel.textContent = `${totalSeconds} с`;
}

function _hrProgressHide() {
  if (el.hrProgressWrap) setHidden(el.hrProgressWrap, true);
  if (el.hrProgressBar) el.hrProgressBar.style.width = "0%";
  if (el.hrProgressLabel) el.hrProgressLabel.textContent = "";
}

function _hrProgressUpdate(elapsedSeconds, totalSeconds) {
  const remaining = Math.max(0, Math.ceil(totalSeconds - elapsedSeconds));
  const pct = Math.min(100, (elapsedSeconds / totalSeconds) * 100);
  if (el.hrProgressBar) el.hrProgressBar.style.width = `${pct}%`;
  if (el.hrProgressLabel) {
    const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
    const ss = String(remaining % 60).padStart(2, "0");
    const timeStr = totalSeconds >= 60 ? `${mm}:${ss}` : `${remaining} с`;
    if (elapsedSeconds < 20) {
      el.hrProgressLabel.textContent = `калибровка ${timeStr}`;
    } else {
      el.hrProgressLabel.textContent = timeStr;
    }
  }
}

async function startPulseMonitor(durationSeconds) {
  if (state.hrMonitoring) {
    stopPulseMonitor();
    return;
  }
  if (!state.cameraActive) {
    setText(el.messageValue, "Включите камеру для мониторинга пульса.");
    return;
  }

  state.hrMonitoring = true;
  if (el.hrMonitorBtn) {
    el.hrMonitorBtn.textContent = "■ Стоп";
    el.hrMonitorBtn.classList.add("monitoring");
  }
  setHidden(el.hrWidget, false);
  const total = durationSeconds || 60;
  _hrProgressShow(total);
  appendLogLine(`[hr] pulse monitor started (${total}s)`);

  let aborted = false;
  state.hrMonitorAbort = () => { aborted = true; };

  await _streamRppgMonitor(total, () => aborted);

  if (!aborted) stopPulseMonitor();
}

async function _streamRppgMonitor(totalSeconds, isAborted) {
  const FPS = 15;
  const INTERVAL_MS = Math.round(1000 / FPS);

  const videoEl = el.cameraPreview;
  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 240;
  const ctx2d = canvas.getContext("2d");

  const wsProto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${wsProto}//${location.host}/ws/rppg?mode=monitor&duration=${totalSeconds}`);

  await new Promise((resolve) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", resolve, { once: true });
  });

  if (ws.readyState !== WebSocket.OPEN) {
    appendLogLine("[hr] monitor WebSocket failed to open");
    return;
  }

  ws.addEventListener("message", (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.heart_rate_bpm != null) {
        updateHrWidget(msg.heart_rate_bpm, msg.heart_rate_algorithm, msg.heart_rate_status);
        appendLogLine(`[hr] bpm=${msg.heart_rate_bpm} algo=${msg.heart_rate_algorithm || "?"}`);
      }
      if (msg.done) {
        appendLogLine("[hr] monitor session complete");
      }
    } catch (_) {}
  });

  const deadline = Date.now() + totalSeconds * 1000;
  let sent = 0;
  const startedAt = Date.now();

  while (Date.now() < deadline && ws.readyState === WebSocket.OPEN && !isAborted()) {
    try {
      ctx2d.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.75));
      if (blob && ws.readyState === WebSocket.OPEN && !isAborted()) {
        ws.send(await blob.arrayBuffer());
        sent++;
      }
    } catch (_) { break; }

    const elapsed = (Date.now() - startedAt) / 1000;
    _hrProgressUpdate(elapsed, totalSeconds);

    const elapsedMs = Date.now() - startedAt;
    const delay = Math.max(0, sent * INTERVAL_MS - elapsedMs);
    if (delay > 0) await new Promise((r) => setTimeout(r, delay));
  }

  try { ws.close(); } catch (_) {}
}

function stopVoiceRecording() {
  state.recording = false;
  el.voiceButton && el.voiceButton.classList.remove("recording");
  const label = state.wakeWordEnabled
    ? `Скажите ${WAKE_WORD_DISPLAY} или нажмите`
    : "Нажми и говори";
  setText(el.voiceButtonLabel, label);
  state.mediaRecorder && state.mediaRecorder.stop();
}

// ---- Wake-word detection via Web Speech API ----

function isSpeechRecognitionSupported() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

function isSecureContext() {
  // Web Speech API requires HTTPS in production; localhost is exempt
  if (window.isSecureContext) return true;
  const host = location.hostname;
  return host === "localhost" || host === "127.0.0.1" || host === "::1";
}

function getWakeWordUnavailableReason() {
  if (!isSpeechRecognitionSupported()) {
    return "SpeechRecognition API не поддерживается этим браузером (используйте Chrome или Edge)";
  }
  if (!isSecureContext()) {
    return "Голосовая активация требует HTTPS-соединения (или localhost)";
  }
  return "";
}

function createSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) return null;

  const recognition = new SpeechRecognition();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "ru-RU";
  recognition.maxAlternatives = 3;
  return recognition;
}

function matchesWakeWord(transcript) {
  const normalized = transcript.toLowerCase().trim().replace(/[.,!?;:«»"']+/g, "");
  for (const ww of WAKE_WORDS) {
    if (normalized.includes(ww)) return true;
  }
  // Fuzzy: any word starting with "зеркал" covers all inflections
  const words = normalized.split(/\s+/);
  for (const w of words) {
    if (w.startsWith("зеркал")) return true;
  }
  // Common STT misrecognitions for "зеркало" (Chrome/Edge on Russian)
  const sttVariants = [
    "серкало", "серкала", "зиркало", "зиркала", "зёркало", "зеркола", "серкол",
    "зерколо", "зеркаль", "зеркалл", "зиркал", "серкал", "зерк",
    "mirror", "зеркала", "зерколе",
  ];
  for (const w of words) {
    for (const variant of sttVariants) {
      if (w.startsWith(variant)) return true;
    }
  }
  // Levenshtein-distance-1 check against "зеркало" for very short words
  if (words.some((w) => w.length >= 5 && levenshtein(w, "зеркало") <= 2)) return true;
  return false;
}

function levenshtein(a, b) {
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1]
        : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[m][n];
}

// ---- Wake-word engine (single persistent recognition object) ----
// Design: one recognition object lives for the whole page session.
// Instead of destroying/recreating it, we use a `wakeWordPaused` flag.
// When paused, onresult is ignored. onend always restarts unless fully stopped.

const _ww = {
  recognition: null,   // the single SpeechRecognition instance
  running: false,      // recognition.start() has been called and not yet ended
  paused: false,       // mic is in use by MediaRecorder — ignore results
  enabled: false,      // user toggle
  cooldown: false,     // debounce after a match
  retryTimer: null,    // pending restart timer
};
// expose for console debugging: type `ww` in browser console to see state
window.ww = _ww;

function _wwScheduleRetry(delayMs) {
  if (_ww.retryTimer) return;
  _ww.retryTimer = setTimeout(() => {
    _ww.retryTimer = null;
    _wwEnsureRunning();
  }, delayMs);
}

function _wwEnsureRunning() {
  if (!_ww.enabled || _ww.paused || _ww.running) return;
  if (getWakeWordUnavailableReason()) return;
  if (!_ww.recognition) {
    const r = createSpeechRecognition();
    if (!r) return;
    _ww.recognition = r;

    r.onresult = (event) => {
      if (_ww.paused || _ww.cooldown || state.recording) return;
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const isFinal = result.isFinal;
        const texts = Array.from({ length: result.length }, (_, j) => result[j].transcript.trim());
        appendLogLine(`[wake-word] STT ${isFinal ? "final" : "interim"}: ${JSON.stringify(texts)}`);
        for (let j = 0; j < result.length; j++) {
          if (matchesWakeWord(result[j].transcript)) {
            appendLogLine(`[wake-word] ✓ MATCH (${isFinal ? "final" : "interim"}): "${result[j].transcript.trim()}"`);
            triggerWakeWordActivation();
            return;
          }
        }
      }
    };

    r.onerror = (event) => {
      appendLogLine(`[wake-word] error: ${event.error}`);
      if (event.error === "not-allowed") {
        _ww.enabled = false;
        _ww.running = false;
        stopWakeWordListening();
        if (el.wakeWordToggle) el.wakeWordToggle.checked = false;
        state.wakeWordEnabled = false;
        updateWakeWordIndicator();
        return;
      }
      // no-speech / aborted / audio-capture — all transient, onend will retry
    };

    r.onend = () => {
      _ww.running = false;
      appendLogLine(`[wake-word] onend: enabled=${_ww.enabled} paused=${_ww.paused}`);
      if (_ww.enabled && !_ww.paused) {
        // Small gap lets the browser breathe before restart
        _wwScheduleRetry(300);
      }
    };
  }

  try {
    _ww.recognition.start();
    _ww.running = true;
    appendLogLine("[wake-word] recognition started");
    setText(el.voiceStatus, `Голосовая активация: скажите ${WAKE_WORD_DISPLAY}`);
    updateWakeWordIndicator();
  } catch (err) {
    _ww.running = false;
    appendLogLine(`[wake-word] start error: ${err.message || err}, retry in 1000ms`);
    _wwScheduleRetry(1000);
  }
}

function startWakeWordListening() {
  appendLogLine("[wake-word] startWakeWordListening");
  _ww.enabled = true;
  state.wakeWordEnabled = true;
  state.wakeWordListening = true;
  _ww.paused = false;
  updateWakeWordIndicator();
  _wwEnsureRunning();
}

function stopWakeWordListening() {
  appendLogLine("[wake-word] stopWakeWordListening");
  _ww.enabled = false;
  state.wakeWordEnabled = false;
  state.wakeWordListening = false;
  _ww.paused = false;
  if (_ww.retryTimer) { clearTimeout(_ww.retryTimer); _ww.retryTimer = null; }
  if (_ww.recognition) {
    try { _ww.recognition.abort(); } catch (_) {}
    _ww.recognition = null;
    _ww.running = false;
  }
  updateWakeWordIndicator();
}

function pauseWakeWordForRecording() {
  if (!_ww.enabled) return;
  appendLogLine("[wake-word] pausing for recording");
  _ww.paused = true;
  state.wakeWordListening = false;
  if (_ww.retryTimer) { clearTimeout(_ww.retryTimer); _ww.retryTimer = null; }
  if (_ww.recognition && _ww.running) {
    try { _ww.recognition.abort(); } catch (_) {}
    // running will be set false in onend
  }
  updateWakeWordIndicator();
}

function resumeWakeWordAfterRecording() {
  appendLogLine("[wake-word] resumeWakeWordAfterRecording");
  if (!_ww.enabled) return;
  // Wait for browser to release mic before restarting recognition
  setTimeout(() => {
    appendLogLine("[wake-word] resume timer fired");
    _ww.paused = false;
    state.wakeWordListening = true;
    updateWakeWordIndicator();
    _wwEnsureRunning();
  }, 1500);
}

function triggerWakeWordActivation() {
  if (state.recording) return;

  // Cooldown to avoid double-triggering
  _ww.cooldown = true;
  state.wakeWordCooldown = true;
  setTimeout(() => { _ww.cooldown = false; state.wakeWordCooldown = false; }, 2000);

  // Stop current TTS playback if active, so user can speak immediately
  if (state.currentSpeechAudio) {
    try {
      state.currentSpeechAudio.pause();
      state.currentSpeechAudio.currentTime = 0;
    } catch (_) { /* ignore */ }
    state.currentSpeechAudio = null;
  }
  state.busy = false;

  // Pause wake-word recognition before starting recording
  pauseWakeWordForRecording();

  // Play a short beep to confirm activation
  playActivationBeep();

  // Auto-start voice recording after a tiny delay for the beep
  setTimeout(() => {
    if (el.voiceButton && !state.recording) {
      el.voiceButton.click();
      // Fallback hard-stop — VAD in the audio backend stops earlier on silence
      const autoStopMs = 15000;
      setTimeout(() => {
        if (state.recording) {
          stopVoiceRecording();
        }
      }, autoStopMs);
    }
  }, 300);
}

function playActivationBeep() {
  try {
    const ctx = state.sharedAudioCtx;
    if (!ctx || ctx.state === "closed") return;
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.2);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.2);
  } catch (_) {
    // Ignore audio context errors
  }
}

function updateWakeWordIndicator() {
  if (el.wakeWordIndicator) {
    if (state.wakeWordListening) {
      el.wakeWordIndicator.classList.add("active");
      el.wakeWordIndicator.title = `Голосовая активация: слушаю ${WAKE_WORD_DISPLAY}`;
    } else {
      el.wakeWordIndicator.classList.remove("active");
      el.wakeWordIndicator.title = "Голосовая активация выключена";
    }
  }
  if (el.wakeWordHint) {
    el.wakeWordHint.hidden = !state.wakeWordEnabled;
  }
  // Update voice button label if not recording
  if (el.voiceButtonLabel && !state.recording) {
    const label = state.wakeWordEnabled
      ? `Скажите ${WAKE_WORD_DISPLAY} или нажмите`
      : "Нажми и говори";
    setText(el.voiceButtonLabel, label);
  }
}

function setupWakeWord() {
  if (!el.wakeWordToggle) return;

  const unavailableReason = getWakeWordUnavailableReason();

  if (unavailableReason) {
    el.wakeWordToggle.disabled = true;
    el.wakeWordToggle.parentElement.title = unavailableReason;
    appendLogLine(`[wake-word] disabled: ${unavailableReason}`);
    return;
  }

  // Restore saved preference
  const saved = localStorage.getItem("neuro_mirror_wake_word");
  if (saved === "true") {
    state.wakeWordEnabled = true;
    el.wakeWordToggle.checked = true;
    // Delay start to not conflict with bootstrap
    setTimeout(() => startWakeWordListening(), 2000);
  }

  el.wakeWordToggle.addEventListener("change", (event) => {
    localStorage.setItem("neuro_mirror_wake_word", event.target.checked ? "true" : "false");
    if (event.target.checked) {
      startWakeWordListening();
    } else {
      stopWakeWordListening();
      setText(el.voiceStatus, "");
    }
  });
}

// ---- Voice recording ----

function setupVoiceRecorder() {
  if (!el.voiceButton) return;

  el.voiceButton.addEventListener("click", async () => {
    if (state.recording) {
      stopVoiceRecording();
      return;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setText(el.voiceStatus, "Browser microphone API is unavailable");
      return;
    }

    // Pause wake-word while recording to avoid mic conflict
    pauseWakeWordForRecording();

    try {
      await unlockAudioPlayback();
    } catch (_) {
      // ignore unlock failure
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      const mimeType = typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      state.mediaRecorder = new MediaRecorder(stream, { mimeType });
      state.mediaChunks = [];

      // --- Browser-side VAD via AudioContext ---
      let vadAudioCtx = null;
      let vadInterval = null;
      const VAD_SILENCE_THRESHOLD = 0.012; // RMS below this = silence
      const VAD_SILENCE_MS = 1800;         // stop after 1.8s of silence post-speech
      const VAD_MIN_SPEECH_MS = 400;       // must hear speech for at least 400ms first
      let vadSpeechMs = 0;
      let vadSilenceMs = 0;
      let vadSpeechStarted = false;

      function stopVad() {
        if (vadInterval) { clearInterval(vadInterval); vadInterval = null; }
        if (vadAudioCtx) { try { vadAudioCtx.close(); } catch (_) {} vadAudioCtx = null; }
      }

      try {
        vadAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const source = vadAudioCtx.createMediaStreamSource(stream);
        const analyser = vadAudioCtx.createAnalyser();
        analyser.fftSize = 512;
        source.connect(analyser);
        const buf = new Float32Array(analyser.fftSize);

        vadInterval = setInterval(() => {
          if (!state.recording) { stopVad(); return; }
          analyser.getFloatTimeDomainData(buf);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
          const rms = Math.sqrt(sum / buf.length);

          if (rms >= VAD_SILENCE_THRESHOLD) {
            vadSpeechMs += 50;
            vadSilenceMs = 0;
            if (vadSpeechMs >= VAD_MIN_SPEECH_MS) vadSpeechStarted = true;
          } else {
            vadSilenceMs += 50;
            if (vadSpeechStarted && vadSilenceMs >= VAD_SILENCE_MS) {
              appendLogLine(`[vad] silence detected after speech, stopping recording`);
              stopVad();
              stopVoiceRecording();
            }
          }
        }, 50);
      } catch (vadErr) {
        appendLogLine(`[vad] AudioContext unavailable: ${vadErr.message || vadErr}`);
      }

      state.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) state.mediaChunks.push(event.data);
      };

      state.mediaRecorder.onstop = async () => {
        stopVad();
        const blob = new Blob(state.mediaChunks, { type: state.mediaRecorder.mimeType || "audio/webm" });
        const formData = new FormData();
        formData.append("audio", blob, "voice.webm");
        const startedAt = performance.now();

        setText(el.voiceStatus, "Transcribing voice in speech worker...");
        state.busy = true;
        setMascotState("thinking");

        try {
          const response = await fetch("/api/speech/transcribe", {
            method: "POST",
            body: formData,
          });
          if (!response.ok) {
            throw new Error((await response.text()) || `${response.status}`);
          }

          const payload = await response.json();
          const elapsedMs = Math.round(performance.now() - startedAt);
          if (payload.transcript && payload.accepted !== false) {
            const meta = describeSttRun(payload, elapsedMs);
            const notes = payload.notes ? ` (${payload.notes})` : "";
            setText(el.voiceStatus, `${meta}: ${payload.transcript}${notes}`);
            if (payload.command === "analyze_appearance") {
              setText(el.voiceStatus, "Запрос распознан, запускаю оценку внешнего вида...");
              await analyzeAppearance();
            } else if (payload.command === "camera_vision_query") {
              setText(el.voiceStatus, "Запрос распознан, анализирую кадр с камеры...");
              await cameraVisionQuery(payload.transcript);
            }
          } else if (payload.transcript) {
            setText(el.voiceStatus, payload.message || `Распознано неуверенно за ${elapsedMs} мс: ${payload.transcript}`);
          } else {
            setText(el.voiceStatus, payload.message || `Речь не распознана за ${elapsedMs} мс.`);
          }
        } catch (error) {
          setText(el.voiceStatus, `Ошибка обработки голоса: ${error.message || error}`);
          appendLogLine(`[client] voice error: ${error.message || error}`);
        } finally {
          state.busy = false;
          for (const track of stream.getTracks()) {
            track.stop();
          }
          // Resume wake-word listening after recording finishes
          resumeWakeWordAfterRecording();
        }
      };

      state.mediaRecorder.start();
      state.recording = true;
      el.voiceButton.classList.add("recording");
      setText(el.voiceButtonLabel, "Stop recording");
      setText(el.voiceStatus, "Recording...");
      setMascotState("listening");
    } catch (error) {
      setText(el.voiceStatus, `Microphone error: ${error.message || error}`);
      appendLogLine(`[client] microphone error: ${error.message || error}`);
      // Resume wake-word if mic grab failed
      resumeWakeWordAfterRecording();
    }
  });
}

// ---- User profiles (личный кабинет) ----

function updateUserChip() {
  if (!el.userChip) return;
  if (state.activeUser) {
    if (el.userChipAvatar) el.userChipAvatar.src = state.activeUser.avatar_url;
    setText(el.userChipName, state.activeUser.name);
    setHidden(el.userChip, false);
  } else {
    setHidden(el.userChip, true);
  }
}

function showUserCreateError(message) {
  if (!el.userCreateError) return;
  if (message) {
    setText(el.userCreateError, message);
    setHidden(el.userCreateError, false);
  } else {
    setHidden(el.userCreateError, true);
  }
}

function syncUserCreateSubmit() {
  const nameOk = Boolean(el.userNameInput && el.userNameInput.value.trim());
  const consentOk = Boolean(el.userConsent && el.userConsent.checked);
  setDisabled(el.userCreateSubmit, !(nameOk && consentOk));
}

function renderUserGrid(users) {
  if (!el.userGrid) return;
  el.userGrid.innerHTML = "";
  for (const user of users) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "user-card";
    const avatar = document.createElement("img");
    avatar.className = "user-card-avatar";
    avatar.src = user.avatar_url;
    avatar.alt = "";
    const name = document.createElement("span");
    name.className = "user-card-name";
    name.textContent = user.name;
    const idBadge = document.createElement("span");
    idBadge.className = "user-card-id mono";
    idBadge.textContent = `ID ${user.id}`;
    card.append(avatar, name, idBadge);
    card.addEventListener("click", () => {
      selectUser(user.id).catch((error) => {
        reportClientError(error, "Не удалось выбрать пользователя");
      });
    });
    el.userGrid.appendChild(card);
  }
}

function renderAvatarPicker() {
  if (!el.avatarPicker) return;
  el.avatarPicker.innerHTML = "";
  for (const preset of state.userPresets) {
    const option = document.createElement("button");
    option.type = "button";
    option.className = "avatar-option";
    option.dataset.presetId = preset.id;
    const img = document.createElement("img");
    img.src = preset.url;
    img.alt = "";
    option.appendChild(img);
    option.addEventListener("click", () => {
      state.userSelectedPreset = preset.id;
      state.userPhotoDataUrl = "";
      setText(el.avatarPhotoHint, "");
      highlightSelectedAvatar();
    });
    el.avatarPicker.appendChild(option);
  }
  highlightSelectedAvatar();
}

function highlightSelectedAvatar() {
  if (!el.avatarPicker) return;
  for (const option of el.avatarPicker.querySelectorAll(".avatar-option")) {
    option.classList.toggle(
      "selected",
      !state.userPhotoDataUrl && option.dataset.presetId === state.userSelectedPreset
    );
  }
}

function resetUserCreateForm() {
  if (el.userNameInput) el.userNameInput.value = "";
  if (el.userConsent) el.userConsent.checked = false;
  state.userPhotoDataUrl = "";
  state.userSelectedPreset = state.userPresets.length ? state.userPresets[0].id : "";
  setText(el.avatarPhotoHint, "");
  showUserCreateError("");
  stopAvatarCamera();
  highlightSelectedAvatar();
  syncUserCreateSubmit();
}

function showUserGateView(view, { allowBack = true } = {}) {
  setHidden(el.userSelectView, view !== "select");
  setHidden(el.userCreateView, view !== "create");
  setHidden(el.userCreateBack, view !== "create" || !allowBack);
  if (view !== "create") stopAvatarCamera();
}

async function openUserGate() {
  const data = await fetchJson("/api/users");
  state.userPresets = data.avatar_presets || [];
  if (el.consentText && data.consent_text) setText(el.consentText, data.consent_text);
  renderUserGrid(data.users || []);
  renderAvatarPicker();
  resetUserCreateForm();
  const hasUsers = Boolean(data.users && data.users.length);
  showUserGateView(hasUsers ? "select" : "create", { allowBack: hasUsers });
  setHidden(el.userGate, false);
}

function closeUserGate() {
  stopAvatarCamera();
  setHidden(el.userGate, true);
}

async function selectUser(userId) {
  const result = await fetchJson(`/api/users/${encodeURIComponent(userId)}/select`, {
    method: "POST",
  });
  state.activeUser = result.user;
  updateUserChip();
  updateClockDisplay();
  closeUserGate();
  appendLogLine(`[client] active user: ${result.user.name} (${result.user.id})`);
}

async function startAvatarCamera() {
  stopAvatarCamera();
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user" },
      audio: false,
    });
    state.avatarCameraStream = stream;
    if (el.avatarCameraVideo) el.avatarCameraVideo.srcObject = stream;
    setHidden(el.avatarCamera, false);
  } catch (error) {
    showUserCreateError(`Не удалось открыть камеру: ${error.message || error}`);
  }
}

function stopAvatarCamera() {
  if (state.avatarCameraStream) {
    for (const track of state.avatarCameraStream.getTracks()) {
      track.stop();
    }
    state.avatarCameraStream = null;
  }
  if (el.avatarCameraVideo) el.avatarCameraVideo.srcObject = null;
  setHidden(el.avatarCamera, true);
}

function captureAvatarPhoto() {
  const video = el.avatarCameraVideo;
  if (!video || !video.videoWidth) {
    showUserCreateError("Камера ещё не готова, подождите секунду.");
    return;
  }
  const size = 320;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  const side = Math.min(video.videoWidth, video.videoHeight);
  const sx = (video.videoWidth - side) / 2;
  const sy = (video.videoHeight - side) / 2;
  // Mirror the frame so the saved photo matches what the user saw in preview
  ctx.translate(size, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, sx, sy, side, side, 0, 0, size, size);
  state.userPhotoDataUrl = canvas.toDataURL("image/png");
  setText(el.avatarPhotoHint, "Фото сделано ✓");
  showUserCreateError("");
  stopAvatarCamera();
  highlightSelectedAvatar();
}

async function submitUserCreate(event) {
  event.preventDefault();
  const name = el.userNameInput ? el.userNameInput.value.trim() : "";
  showUserCreateError("");
  setButtonLoading(el.userCreateSubmit, true);
  try {
    const result = await fetchJson("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        consent: Boolean(el.userConsent && el.userConsent.checked),
        avatar_preset: state.userPhotoDataUrl ? "" : state.userSelectedPreset,
        photo_base64: state.userPhotoDataUrl,
      }),
    });
    await selectUser(result.user.id);
  } catch (error) {
    let message = error.message || String(error);
    try {
      const parsed = JSON.parse(message);
      if (parsed && parsed.detail) message = parsed.detail;
    } catch (_) {
      // not JSON, keep as-is
    }
    showUserCreateError(message);
  } finally {
    setButtonLoading(el.userCreateSubmit, false);
    syncUserCreateSubmit();
  }
}

function bindUserGateEvents() {
  if (state.userGateBound) return;
  state.userGateBound = true;

  el.userCreateOpen && el.userCreateOpen.addEventListener("click", () => {
    resetUserCreateForm();
    showUserGateView("create");
  });
  el.userCreateBack && el.userCreateBack.addEventListener("click", () => {
    showUserGateView("select");
  });
  el.userCreateForm && el.userCreateForm.addEventListener("submit", submitUserCreate);
  el.userNameInput && el.userNameInput.addEventListener("input", syncUserCreateSubmit);
  el.userConsent && el.userConsent.addEventListener("change", syncUserCreateSubmit);
  el.avatarPhotoBtn && el.avatarPhotoBtn.addEventListener("click", startAvatarCamera);
  el.avatarCaptureBtn && el.avatarCaptureBtn.addEventListener("click", captureAvatarPhoto);
  el.avatarCameraCancel && el.avatarCameraCancel.addEventListener("click", stopAvatarCamera);
  el.userChip && el.userChip.addEventListener("click", () => {
    openUserGate().catch((error) => {
      reportClientError(error, "Не удалось открыть выбор пользователя");
    });
  });
  // Allow dismissing the gate by clicking the backdrop, but only when
  // someone is already signed in — a user must always be selected.
  el.userGate && el.userGate.addEventListener("click", (event) => {
    if (event.target === el.userGate && state.activeUser) closeUserGate();
  });
}

async function initUserGate() {
  bindUserGateEvents();
  // If the server already has an active user (page reload mid-session),
  // pick it up silently instead of blocking the UI with the gate again.
  const data = await fetchJson("/api/users");
  if (data.active_user) {
    state.userPresets = data.avatar_presets || [];
    state.activeUser = data.active_user;
    updateUserChip();
    updateClockDisplay();
    return;
  }
  await openUserGate();
}

function bindEvents() {
  if (!el.assistantForm || !el.assistantInput) {
    throw new Error("required UI elements are missing");
  }

  el.assistantForm.addEventListener("submit", submitAssistantMessage);
  el.assistantInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      el.assistantForm.requestSubmit();
    }
  });
  el.assistantInput.addEventListener("input", autoGrowAssistantInput);

  // Composer is collapsed by default; expand on hint click (touch screens)
  // and collapse back when it loses focus while empty
  el.composerHint && el.composerHint.addEventListener("click", () => {
    if (el.composerShell) el.composerShell.classList.add("expanded");
    el.assistantInput && el.assistantInput.focus();
  });
  el.composerShell && el.composerShell.addEventListener("focusout", (event) => {
    if (!el.composerShell.contains(event.relatedTarget) &&
        el.assistantInput && !el.assistantInput.value.trim()) {
      el.composerShell.classList.remove("expanded");
    }
  });

  el.cameraToggle && el.cameraToggle.addEventListener("click", toggleCamera);
  el.appearanceButton && el.appearanceButton.addEventListener("click", analyzeAppearance);
  el.screeningButton && el.screeningButton.addEventListener("click", startScreening);
  el.hrMonitorBtn && el.hrMonitorBtn.addEventListener("click", () => startPulseMonitor(300));
  el.ttsEnabled && el.ttsEnabled.addEventListener("change", (event) => {
    state.ttsEnabled = event.target.checked;
  });
  el.logClear && el.logClear.addEventListener("click", () => {
    if (el.logValue) el.logValue.textContent = "Log cleared.";
  });
  el.devicesForm && el.devicesForm.addEventListener("submit", submitDeviceSelection);
  el.devicesRefresh && el.devicesRefresh.addEventListener("click", () => {
    loadDevices().catch((error) => {
      renderDeviceErrors([error.message || String(error)]);
    });
  });
  el.cameraSelect && el.cameraSelect.addEventListener("change", syncDeviceSelectionStatus);
  el.microphoneSelect && el.microphoneSelect.addEventListener("change", syncDeviceSelectionStatus);

  setupVoiceRecorder();
  setupWakeWord();
  bindMainMenuEvents();
}

async function bootstrap() {
  appendLogLine("[client] bootstrap started");
  updateClockDisplay();
  window.setInterval(updateClockDisplay, 1000);
  await loadConfig();
  try {
    await loadDevices();
  } catch (error) {
    appendLogLine(`[client] loadDevices failed (continuing): ${error.message || error}`);
  }
  // Live2D грузится с внешнего CDN — без интернета он не должен
  // блокировать запуск зеркала (останется статичная картинка маскота)
  try {
    await Promise.race([
      setupLive2D(),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("live2d load timeout")), 8000)
      ),
    ]);
  } catch (error) {
    appendLogLine(`[client] live2d unavailable (continuing): ${error.message || error}`);
  }
  setButtonLabel(el.cameraToggle, "Turn camera on");
  setButtonLabel(el.appearanceButton, "Analyze appearance");
  appendLogLine("[client] requesting /api/state");
  const snapshot = await fetchJson("/api/state");
  renderSnapshot(snapshot);
  installAudioUnlockHandlers();
  bindEvents();
  connectWebSocket();
  try {
    await initUserGate();
  } catch (error) {
    reportClientError(error, "Не удалось загрузить пользователей");
  }
  // Service deep-links: /?results=1 opens the results screen,
  // /?check=<scenario> opens the session-conditions check right away
  const searchParams = new URLSearchParams(window.location.search);
  if (searchParams.has("results")) {
    openResults().catch(() => {});
  }
  const checkScenario = searchParams.get("check");
  if (checkScenario && CHECK_REQUIREMENTS[checkScenario]) {
    openSessionCheck(checkScenario).catch(() => {});
  }
  appendLogLine("[client] bootstrap completed");
}

window.addEventListener("error", (event) => {
  reportClientError(event.error || event.message, "Frontend runtime error");
});

window.addEventListener("unhandledrejection", (event) => {
  reportClientError(event.reason, "Frontend promise rejection");
});

function startApp() {
  bootstrap().catch((error) => {
    reportClientError(error, "Frontend bootstrap failed");
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startApp, { once: true });
} else {
  startApp();
}

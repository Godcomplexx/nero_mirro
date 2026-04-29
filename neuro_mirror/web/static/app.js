const WAKE_WORDS = ["зеркало", "привет зеркало", "hey mirror"];
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
};

const SCREEN_LABELS = {
  idle: "Idle",
  assistant: "Assistant",
  screening: "Screening",
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
  if (!el.logValue) return;
  const current = el.logValue.textContent ? `${el.logValue.textContent}\n` : "";
  const next = `${current}${line}`.trim();
  const lines = next.split("\n").slice(-80);
  el.logValue.textContent = lines.join("\n");
  el.logValue.scrollTop = el.logValue.scrollHeight;
}

function reportClientError(error, prefix) {
  const message = error instanceof Error ? (error.stack || error.message) : String(error);
  console.error(prefix, error);
  setText(el.messageValue, `${prefix}: ${message}`);
  appendLogLine(`[client] ${prefix}: ${message}`);
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
  if (el.currentGreeting) setText(el.currentGreeting, formatGreeting(now.getHours()));
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

  const context = new AudioCtor();
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
  } finally {
    try {
      await context.close();
    } catch (_) {
      // ignore close failure
    }
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
    if (domains.speech != null) rows.push(reportRow("Speech", formatNumber(domains.speech)));
    if (domains.reaction != null) rows.push(reportRow("Reaction", `${domains.reaction} ms`));

    const sources = report.sources || {};
    const video = sources.video || {};
    const voice = sources.voice || {};

    if (Object.keys(video).length > 0) {
      rows.push('<div class="report-section">Video</div>');
      if (video.attention_score != null) rows.push(reportRow("Attention", formatNumber(video.attention_score)));
      if (video.face_detected !== undefined) rows.push(reportRow("Face", video.face_detected ? "Yes" : "No"));
      if (video.notes) rows.push(reportRow("Notes", video.notes));
    }

    if (Object.keys(voice).length > 0) {
      rows.push('<div class="report-section">Voice</div>');
      if (voice.speech_score != null) rows.push(reportRow("Speech", formatNumber(voice.speech_score)));
      if (voice.reaction_ms != null) rows.push(reportRow("Reaction", `${voice.reaction_ms} ms`));
      if (voice.notes) rows.push(reportRow("Notes", voice.notes));
    }

    el.reportValue.innerHTML = rows.join("");
    return;
  }

  el.reportValue.innerHTML = `<pre>${escapeHtml(JSON.stringify(report, null, 2))}</pre>`;
}

function formatNumber(value) {
  return typeof value === "number" ? value.toFixed(2) : value;
}

function reportRow(label, value) {
  return `<div class="report-row"><span class="report-label">${escapeHtml(label)}</span><span class="report-val">${escapeHtml(value)}</span></div>`;
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

function renderSnapshot(snapshot) {
  setText(el.screenValue, SCREEN_LABELS[snapshot.screen] || snapshot.screen || "-");
  setText(el.sourceValue, snapshot.assistant_source || "-");
  setText(el.messageValue, snapshot.message || "-");
  setText(el.transcriptValue, snapshot.transcript_text ? `Transcript: ${snapshot.transcript_text}` : "");
  setMascotSpeech(snapshot.message || "", { visible: shouldShowMascotSpeech(snapshot) });

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
  if (el.detailsDrawer && (snapshot.screen === "device_setup" || (snapshot.device_errors && snapshot.device_errors.length))) {
    el.detailsDrawer.open = true;
  }
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

  // Only speak messages on assistant/summary screens — skip status/system messages
  const screen = snapshot.screen || "";
  if (screen !== "assistant" && screen !== "summary") return;

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

  try {
    const releaseResult = await fetchJson("/api/actions/release_camera", { method: "POST" });
    appendLogLine(`[client] backend camera release: ${JSON.stringify(releaseResult.worker_statuses || {})}`);
    await new Promise((resolve) => setTimeout(resolve, 120));
  } catch (error) {
    const details = describeMediaError(error);
    appendLogLine(`[client] backend camera release failed: ${details}`);
    setCameraOverlay(`Camera error: ${details}`);
    return;
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

async function startScreening() {
  try {
    await unlockAudioPlayback();
  } catch (_) {
    // ignore unlock failure
  }

  setButtonLoading(el.screeningButton, true);
  try {
    await fetchJson("/api/actions/start_screening", { method: "POST" });
  } catch (error) {
    setText(el.messageValue, `Screening start failed: ${error.message || error}`);
    appendLogLine(`[client] screening error: ${error.message || error}`);
  } finally {
    setButtonLoading(el.screeningButton, false);
  }
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
  const normalized = transcript.toLowerCase().trim().replace(/[.,!?;:]+/g, "");
  for (const ww of WAKE_WORDS) {
    if (normalized.includes(ww)) return true;
  }
  // Fuzzy: check if any word starts with "зеркал" (covers "зеркало", "зеркала", "зеркалу", etc.)
  const words = normalized.split(/\s+/);
  for (const w of words) {
    if (w.startsWith("зеркал")) return true;
  }
  // Common STT misrecognitions for "зеркало"
  const sttVariants = ["серкало", "серкала", "зиркало", "зиркала", "зёркало", "зеркола", "серкол"];
  for (const w of words) {
    for (const variant of sttVariants) {
      if (w.startsWith(variant)) return true;
    }
  }
  return false;
}

function startWakeWordListening() {
  appendLogLine(`[wake-word] startWakeWordListening called: listening=${state.wakeWordListening}`);
  if (state.wakeWordListening) {
    appendLogLine("[wake-word] already listening, skip");
    return;
  }
  const unavailableReason = getWakeWordUnavailableReason();
  if (unavailableReason) {
    setText(el.voiceStatus, unavailableReason);
    appendLogLine(`[wake-word] unavailable: ${unavailableReason}`);
    return;
  }

  const recognition = createSpeechRecognition();
  if (!recognition) {
    appendLogLine("[wake-word] failed to create SpeechRecognition");
    return;
  }

  state.wakeWordRecognition = recognition;
  state.wakeWordListening = true;
  updateWakeWordIndicator();

  recognition.onresult = (event) => {
    // Log every STT result for debugging wake-word recognition
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      const isFinal = result.isFinal;
      const texts = [];
      for (let j = 0; j < result.length; j++) {
        texts.push(result[j].transcript.trim());
      }
      appendLogLine(`[wake-word] STT ${isFinal ? "final" : "interim"}: ${JSON.stringify(texts)}`);
    }

    if (state.recording || state.wakeWordCooldown) return;

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      for (let j = 0; j < result.length; j++) {
        const transcript = result[j].transcript;
        if (matchesWakeWord(transcript)) {
          appendLogLine(`[wake-word] ✓ MATCH: "${transcript.trim()}"`);
          triggerWakeWordActivation();
          return;
        }
      }
    }
  };

  recognition.onerror = (event) => {
    appendLogLine(`[wake-word] error: ${event.error}`);
    // "no-speech" and "aborted" are normal during continuous listening
    if (event.error === "no-speech" || event.error === "aborted") return;
    if (event.error === "not-allowed") {
      setText(el.voiceStatus, "Микрофон не разрешён для голосовой активации");
      stopWakeWordListening();
      if (el.wakeWordToggle) el.wakeWordToggle.checked = false;
      state.wakeWordEnabled = false;
      return;
    }
  };

  recognition.onend = () => {
    // Auto-restart if still enabled and not currently recording
    if (state.wakeWordEnabled && !state.recording) {
      try {
        recognition.start();
      } catch (err) {
        appendLogLine(`[wake-word] restart failed: ${err.message || err}, will retry`);
        state.wakeWordListening = false;
        state.wakeWordRecognition = null;
        updateWakeWordIndicator();
        // Retry with a fresh recognition instance
        setTimeout(() => {
          if (state.wakeWordEnabled && !state.recording) {
            startWakeWordListening();
          }
        }, 1000);
      }
    } else {
      state.wakeWordListening = false;
      state.wakeWordRecognition = null;
      updateWakeWordIndicator();
    }
  };

  try {
    recognition.start();
    appendLogLine(`[wake-word] listening started, wake word: ${WAKE_WORD_DISPLAY}`);
    setText(el.voiceStatus, `Голосовая активация: скажите ${WAKE_WORD_DISPLAY}`);
  } catch (error) {
    appendLogLine(`[wake-word] start failed: ${error.message || error}`);
    state.wakeWordListening = false;
    updateWakeWordIndicator();
  }
}

function stopWakeWordListening() {
  state.wakeWordListening = false;
  if (state.wakeWordRecognition) {
    try {
      state.wakeWordRecognition.abort();
    } catch (_) { /* ignore */ }
    state.wakeWordRecognition = null;
  }
  updateWakeWordIndicator();
}

function pauseWakeWordForRecording() {
  if (state.wakeWordRecognition && state.wakeWordListening) {
    appendLogLine("[wake-word] pausing for recording");
    state.wakeWordListening = false;
    try {
      state.wakeWordRecognition.abort();
    } catch (_) { /* ignore */ }
    state.wakeWordRecognition = null;
    updateWakeWordIndicator();
  }
}

function resumeWakeWordAfterRecording() {
  appendLogLine(`[wake-word] resumeWakeWordAfterRecording called: enabled=${state.wakeWordEnabled}, listening=${state.wakeWordListening}, recording=${state.recording}`);
  if (state.wakeWordEnabled && !state.wakeWordListening) {
    // Longer delay to ensure browser fully releases the mic after MediaRecorder/getUserMedia
    appendLogLine("[wake-word] scheduling resume in 1500ms");
    setTimeout(() => {
      appendLogLine(`[wake-word] resume timer fired: enabled=${state.wakeWordEnabled}, recording=${state.recording}, listening=${state.wakeWordListening}`);
      if (state.wakeWordEnabled && !state.recording) {
        startWakeWordListening();
      }
    }, 1500);
  }
}

function triggerWakeWordActivation() {
  if (state.recording) return;

  // Cooldown to avoid double-triggering
  state.wakeWordCooldown = true;
  setTimeout(() => { state.wakeWordCooldown = false; }, 1500);

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
      // Auto-stop recording after configurable seconds
      const autoStopMs = 8000;
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
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
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
    setTimeout(() => ctx.close(), 300);
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
    state.wakeWordEnabled = event.target.checked;
    localStorage.setItem("neuro_mirror_wake_word", state.wakeWordEnabled ? "true" : "false");

    if (state.wakeWordEnabled) {
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

      state.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) state.mediaChunks.push(event.data);
      };

      state.mediaRecorder.onstop = async () => {
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

  el.cameraToggle && el.cameraToggle.addEventListener("click", toggleCamera);
  el.appearanceButton && el.appearanceButton.addEventListener("click", analyzeAppearance);
  el.screeningButton && el.screeningButton.addEventListener("click", startScreening);
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
}

async function bootstrap() {
  appendLogLine("[client] bootstrap started");
  updateClockDisplay();
  window.setInterval(updateClockDisplay, 1000);
  await loadConfig();
  await loadDevices();
  await setupLive2D();
  setButtonLabel(el.cameraToggle, "Turn camera on");
  setButtonLabel(el.appearanceButton, "Analyze appearance");
  appendLogLine("[client] requesting /api/state");
  const snapshot = await fetchJson("/api/state");
  renderSnapshot(snapshot);
  installAudioUnlockHandlers();
  bindEvents();
  connectWebSocket();
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

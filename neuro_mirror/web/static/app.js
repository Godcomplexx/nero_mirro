// neuro_mirror/web/static/app.js
//
// Classic (non-module) script with the core still shared by the new
// ES-module UI (js/): API helpers, camera, audio unlock, device selection,
// the server WebSocket (re-dispatched as the `nm:snapshot` event), research
// dataset capture and the profile gate. Modules reach these top-level
// bindings only through js/core/legacy.js. The old mirror HUD (mascot,
// voice orb, wake word, assistant chat, telemetry) was removed in the
// redesign (docs/superpowers/specs/2026-09-22-frontend-sidebar-redesign-design.md).

const state = {
  websocket: null,
  reconnectTimer: null,
  pingTimer: null,
  mediaStream: null,
  audioUnlocked: false,
  sharedAudioCtx: null,
  config: null,
  deviceCatalog: { cameras: [], microphones: [] },
  selectedDevices: { camera_id: "", microphone_id: "" },
  cameraActive: false,
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
  devicesForm: $("devices-form"),
  devicesRefresh: $("devices-refresh"),
  devicesSave: $("devices-save"),
  devicesStatus: $("devices-status"),
  devicesErrors: $("devices-errors"),
  cameraSelect: $("camera-select"),
  microphoneSelect: $("microphone-select"),
  cameraPreview: $("camera-preview"),
  datasetRecording: $("dataset-recording"),
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
  userConsentPersonal: $("user-consent-personal"),
  userConsentAudio: $("user-consent-audio"),
  userConsentVideo: $("user-consent-video"),
  userConsentDataset: $("user-consent-dataset"),
  consentTextPersonal: $("consent-text-personal"),
  consentTextAudio: $("consent-text-audio"),
  consentTextVideo: $("consent-text-video"),
  consentTextDataset: $("consent-text-dataset"),
  userCreateError: $("user-create-error"),
  userCreateSubmit: $("user-create-submit"),
  userCreateBack: $("user-create-back"),
  userChip: $("user-chip"),
  userChipAvatar: $("user-chip-avatar"),
  userChipName: $("user-chip-name"),
};

// ---- Helpers ----

function setText(node, value) {
  if (node) node.textContent = value;
}

function setHidden(node, hidden) {
  if (node) node.hidden = hidden;
}

function setDisabled(node, disabled) {
  if (node) node.disabled = disabled;
}

function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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
  sendClientLog("error", `${prefix}: ${message}`);
  // Failures of a user's own action carry a Russian prefix and are shown on
  // screen (js/components/notify.js); internal "Frontend …" errors stay in the log
  if (window.nmNotify && !/^Frontend/.test(prefix)) {
    const reason = error instanceof Error ? error.message : String(error || "");
    window.nmNotify(reason ? `${prefix}. ${reason}` : `${prefix}. Повторите попытку.`);
  }
}

// Why the camera could not be switched on, in words for the user
function cameraProblemText(error) {
  const name = (error && error.name) || "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Доступ к камере запрещён. Разрешите приложению использовать камеру и повторите попытку.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "Камера не найдена. Проверьте, что она подключена, и повторите попытку.";
  }
  if (name === "NotReadableError" || name === "AbortError") {
    return "Камера занята другой программой. Закройте её и повторите попытку.";
  }
  return "Камера не включилась. Проверьте подключение и повторите попытку.";
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
    throw new Error(await responseErrorMessage(response));
  }
  return response.json();
}

async function responseErrorMessage(response) {
  const raw = (await response.text()).trim();
  if (raw) {
    try {
      const payload = JSON.parse(raw);
      if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail.trim();
      if (typeof payload.message === "string" && payload.message.trim()) return payload.message.trim();
    } catch (_) {
      // The endpoint may return plain text.
    }
    return raw;
  }
  return `Сервер вернул ошибку ${response.status}. Повторите попытку.`;
}

function setButtonLoading(button, loading) {
  if (!button) return;
  button.disabled = loading;
  button.classList.toggle("loading", loading);
}

// ---- Audio unlock (browsers block sound until a user gesture) ----

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

// ---- Config and device selection (service screen, js/screens/service.js) ----

async function loadConfig() {
  appendLogLine("[client] requesting /api/config");
  state.config = await fetchJson("/api/config");
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
  } catch (error) {
    renderDeviceErrors([error.message || String(error)]);
    appendLogLine(`[client] device selection error: ${error.message || error}`);
  } finally {
    setButtonLoading(el.devicesSave, false);
  }
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

// ---- Server state ----

function renderSnapshot(snapshot) {
  // Start/stop dataset recording on screen transitions (no-op without consent)
  syncDatasetCapture(snapshot.screen);
  // MoCA and HADS screens follow the snapshots themselves (js/core/*-controller.js)
  if (snapshot.screen === "moca" || snapshot.screen === "hads") return;

  renderDeviceWizard(snapshot);
  if (snapshot.screen === "device_setup" && state.lastScreen !== "device_setup") {
    // The device selection form lives on the service screen (js/screens/service.js)
    if (window.nmOpenSection) window.nmOpenSection("service");
  }
  state.lastScreen = snapshot.screen;
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
    appendLogLine("[client] websocket connected");
    state.pingTimer = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) socket.send("ping");
    }, 15000);
  });

  socket.addEventListener("message", (event) => {
    const packet = JSON.parse(event.data);
    if (!packet || !packet.payload) return;
    renderSnapshot(packet.payload);
    // Screens of the new shell (js/screens/*) follow server state through this event
    window.dispatchEvent(new CustomEvent("nm:snapshot", { detail: packet.payload }));
  });

  socket.addEventListener("close", () => {
    appendLogLine("[client] websocket closed");
    if (state.pingTimer) {
      clearInterval(state.pingTimer);
      state.pingTimer = null;
    }
    state.reconnectTimer = setTimeout(connectWebSocket, 1500);
  });

  socket.addEventListener("error", () => {
    appendLogLine("[client] websocket error");
  });
}

// ---- Dataset capture: raw session video for the research dataset ----
//
// Only runs when the profile granted the separate "dataset" consent, which the
// server confirms via /api/dataset/status. Recording is deliberately limited to
// the MoCA and HADS screens: during "screening" the vision worker owns the
// camera exclusively (MSMF fails if a second handle is open), so the browser
// must not hold a stream at that time.

const DATASET_CAPTURE_SCREENS = new Set(["moca", "hads"]);
const DATASET_CHUNK_MS = 5000;

const datasetCapture = {
  recorder: null,
  stream: null,
  sessionId: "",
  sequence: 0,
  screen: null,
  busy: false,
  uploadChain: Promise.resolve(),
  // Monotonic base for chunk offsets: wall clock can jump, performance.now cannot
  startedAt: 0,
};

async function syncDatasetCapture(screen) {
  const next = String(screen || "");
  if (datasetCapture.screen === next) return;
  datasetCapture.screen = next;
  if (DATASET_CAPTURE_SCREENS.has(next)) {
    await startDatasetCapture(next);
  } else {
    stopDatasetCapture();
  }
}

async function startDatasetCapture(screen) {
  if (datasetCapture.busy || datasetCapture.recorder) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
  if (typeof MediaRecorder === "undefined") return;

  datasetCapture.busy = true;
  try {
    const status = await fetchJson("/api/dataset/status");
    if (!status.capture || !status.session_id) return;

    // The vision worker may still hold the camera after a screening run.
    try {
      await fetchJson("/api/actions/release_camera", { method: "POST" });
      await new Promise((resolve) => setTimeout(resolve, 120));
    } catch (_) {
      // Independent of the browser stream — let getUserMedia report real problems.
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: true,
    });

    const mimeType = typeof MediaRecorder.isTypeSupported === "function"
      && MediaRecorder.isTypeSupported("video/webm;codecs=vp9,opus")
      ? "video/webm;codecs=vp9,opus"
      : "video/webm";
    const recorder = new MediaRecorder(stream, { mimeType });

    datasetCapture.stream = stream;
    datasetCapture.recorder = recorder;
    datasetCapture.sessionId = status.session_id;
    datasetCapture.sequence = Number.isInteger(status.next_video_sequence)
      ? status.next_video_sequence
      : 0;
    datasetCapture.uploadChain = Promise.resolve();
    recorder._datasetSessionId = status.session_id;
    recorder._datasetSequence = datasetCapture.sequence;
    recorder._datasetStartedAt = performance.now();

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        const sessionId = recorder._datasetSessionId;
        const sequence = recorder._datasetSequence++;
        datasetCapture.sequence = recorder._datasetSequence;
        const offsetMs = performance.now() - recorder._datasetStartedAt;
        datasetCapture.uploadChain = datasetCapture.uploadChain.then(
          () => uploadDatasetChunk(event.data, offsetMs, sessionId, sequence)
        );
      }
    };
    recorder.onerror = (event) => {
      appendLogLine(`[dataset] recorder error: ${event.error?.name || "unknown"}`);
      stopDatasetCapture();
    };
    datasetCapture.startedAt = performance.now();
    recorder.start(DATASET_CHUNK_MS);
    // Pin the video timeline to the server clock before any chunk arrives
    await registerDatasetVideoStart(mimeType);
    setDatasetRecordingIndicator(true);
    appendLogLine(`[dataset] запись начата (${status.scenario || screen})`);
    postDatasetTimeline(screen, "capture_started");
  } catch (error) {
    appendLogLine(`[dataset] не удалось начать запись: ${error.message || error}`);
    releaseDatasetStream();
  } finally {
    datasetCapture.busy = false;
  }
}

function stopDatasetCapture() {
  const recorder = datasetCapture.recorder;
  if (recorder) {
    postDatasetTimeline(datasetCapture.screen, "capture_stopped");
    try {
      // requestData() flushes the tail so the last seconds are not lost
      if (recorder.state === "recording") recorder.requestData();
      if (recorder.state !== "inactive") recorder.stop();
    } catch (_) {
      // already stopped
    }
  }
  releaseDatasetStream();
}

function setDatasetRecordingIndicator(active) {
  // The patient must be able to see that recording is happening, at all times
  if (el.datasetRecording) setHidden(el.datasetRecording, !active);
}

function releaseDatasetStream() {
  setDatasetRecordingIndicator(false);
  if (datasetCapture.stream) {
    for (const track of datasetCapture.stream.getTracks()) {
      try {
        track.stop();
      } catch (_) {
        // ignore
      }
    }
  }
  datasetCapture.stream = null;
  datasetCapture.recorder = null;
  datasetCapture.sessionId = "";
}

async function registerDatasetVideoStart(mimeType) {
  const sessionId = datasetCapture.sessionId;
  if (!sessionId) return;
  try {
    await fetch("/api/dataset/video-start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        client_started_at: new Date().toISOString(),
        mime_type: mimeType || "",
      }),
    });
  } catch (error) {
    appendLogLine(`[dataset] не удалось записать точку отсчёта: ${error.message || error}`);
  }
}

async function uploadDatasetChunk(blob, offsetMs, sessionId, sequence) {
  if (!sessionId) return;
  const body = new FormData();
  body.append("session_id", sessionId);
  body.append("sequence", String(sequence));
  if (Number.isFinite(offsetMs)) body.append("offset_ms", String(Math.round(offsetMs)));
  body.append("chunk", blob, `${String(sequence).padStart(6, "0")}.webm`);
  try {
    const response = await fetch("/api/dataset/video-chunk", { method: "POST", body });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch (error) {
    appendLogLine(`[dataset] фрагмент ${sequence} не сохранён: ${error.message || error}`);
  }
}

async function postDatasetTimeline(screen, stage, details = {}) {
  const sessionId = datasetCapture.sessionId;
  if (!sessionId) return;
  try {
    await fetch("/api/dataset/timeline", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, screen: screen || "", stage, details }),
    });
  } catch (_) {
    // timeline is auxiliary — never interrupt the test for it
  }
}

window.addEventListener("pagehide", stopDatasetCapture);

// ---- Camera (one browser stream, shared by checks, rPPG and dataset capture) ----

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
}

async function toggleCamera() {
  if (state.cameraActive) {
    stopCamera();
    return;
  }
  const consents = (state.activeUser && state.activeUser.consents) || {};
  // The reason is kept in state.cameraProblem; callers (session check,
  // «Зеркало») show it to the user instead of a bare "camera unavailable"
  state.cameraProblem = "";
  if (consents.video === false) {
    state.cameraProblem =
      "В профиле нет согласия на обработку видеоданных, поэтому камера не включается. " +
      "Выберите или создайте профиль с таким согласием.";
    appendLogLine("[client] camera blocked: no video consent");
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    state.cameraProblem = "Камера недоступна на этом компьютере. Проверьте подключение и перезапустите приложение.";
    appendLogLine("[client] browser camera API is unavailable");
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
    appendLogLine(`[client] camera ready: ${JSON.stringify(track.getSettings ? track.getSettings() : {})}`);
  } catch (error) {
    const details = describeMediaError(error);
    stopCamera();
    state.cameraProblem = cameraProblemText(error);
    appendLogLine(`[client] camera error: ${details}`);
  }
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
  const consentOk = Boolean(el.userConsentPersonal && el.userConsentPersonal.checked);
  setDisabled(el.userCreateSubmit, !(nameOk && consentOk));
  if (el.avatarPhotoBtn) {
    setDisabled(el.avatarPhotoBtn, !(el.userConsentVideo && el.userConsentVideo.checked));
  }
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
  if (el.userConsentPersonal) el.userConsentPersonal.checked = false;
  if (el.userConsentAudio) el.userConsentAudio.checked = false;
  if (el.userConsentVideo) el.userConsentVideo.checked = false;
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
  const consentTexts = data.consent_texts || {};
  if (el.consentTextPersonal && consentTexts.personal) setText(el.consentTextPersonal, consentTexts.personal);
  if (el.consentTextAudio && consentTexts.audio) setText(el.consentTextAudio, consentTexts.audio);
  if (el.consentTextVideo && consentTexts.video) setText(el.consentTextVideo, consentTexts.video);
  if (el.consentTextDataset && consentTexts.dataset) setText(el.consentTextDataset, consentTexts.dataset);
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
  if (!state.activeUser.consents || state.activeUser.consents.video !== true) stopCamera();
  updateUserChip();
  closeUserGate();
  appendLogLine(`[client] active user: ${result.user.name} (${result.user.id})`);
}

async function startAvatarCamera() {
  stopAvatarCamera();
  if (!(el.userConsentVideo && el.userConsentVideo.checked)) {
    showUserCreateError("Для фото-аватара сначала разрешите обработку видеоданных.");
    return;
  }
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
        consent: Boolean(el.userConsentPersonal && el.userConsentPersonal.checked),
        personal_data_consent: Boolean(el.userConsentPersonal && el.userConsentPersonal.checked),
        audio_data_consent: Boolean(el.userConsentAudio && el.userConsentAudio.checked),
        video_data_consent: Boolean(el.userConsentVideo && el.userConsentVideo.checked),
        dataset_consent: Boolean(el.userConsentDataset && el.userConsentDataset.checked),
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
  el.userConsentPersonal && el.userConsentPersonal.addEventListener("change", syncUserCreateSubmit);
  el.userConsentAudio && el.userConsentAudio.addEventListener("change", syncUserCreateSubmit);
  el.userConsentVideo && el.userConsentVideo.addEventListener("change", syncUserCreateSubmit);
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
    return;
  }
  await openUserGate();
}

function bindEvents() {
  el.devicesForm && el.devicesForm.addEventListener("submit", submitDeviceSelection);
  el.devicesRefresh && el.devicesRefresh.addEventListener("click", () => {
    loadDevices().catch((error) => {
      renderDeviceErrors([error.message || String(error)]);
    });
  });
  el.cameraSelect && el.cameraSelect.addEventListener("change", syncDeviceSelectionStatus);
  el.microphoneSelect && el.microphoneSelect.addEventListener("change", syncDeviceSelectionStatus);
}


async function bootstrap() {
  appendLogLine("[client] bootstrap started");
  await loadConfig();
  try {
    await loadDevices();
  } catch (error) {
    appendLogLine(`[client] loadDevices failed (continuing): ${error.message || error}`);
  }
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
  // Service deep-links: /?results=1 opens «Отчёты»,
  // /?check=<scenario> opens that test's screen (it starts with the check)
  const searchParams = new URLSearchParams(window.location.search);
  if (searchParams.has("results")) {
    if (window.nmOpenSection) window.nmOpenSection("reports");
  }
  const checkScenario = searchParams.get("check");
  if (checkScenario && ["screening", "moca", "hads"].includes(checkScenario)) {
    if (window.nmOpenSection) window.nmOpenSection(checkScenario);
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

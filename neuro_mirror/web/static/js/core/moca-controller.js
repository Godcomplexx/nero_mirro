// neuro_mirror/web/static/js/core/moca-controller.js
//
// Follows the voice MoCA test run by the server (plugins/moca_test): task
// texts, the order of tasks, recording and scoring all live in the backend;
// this module keeps the latest state, plays the voiced instructions and the
// "answer now" cue. Moved out of app.js (renderMoca / _mocaPlayTts /
// playMocaRecordingCue / stopMocaTest).

import { createVoiceChannel } from "./test-voice.js";

const voice = createVoiceChannel({ finishedUrl: "/api/actions/moca_tts_finished", idField: "moca_tts_id" });

// status: "idle" | "running" | "finished" | "stopped"
const moca = {
  status: "idle",
  taskIndex: 0,
  taskTotal: 11,
  taskId: "",
  domain: "",
  hint: "",
  recording: false,
  recordingSince: 0,
  speaking: false,
  message: "",
  // Ядро ждёт нажатия «Приступить»; пределы времени приходят оттуда же.
  awaitingStart: false,
  taskLimitSeconds: 0,
  startGraceSeconds: 0,
};

const listeners = new Set();

function emit() {
  for (const listener of listeners) listener(moca);
}

// Short tone marking the moment the patient should start answering
function playRecordingCue() {
  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtor) return;
  try {
    const context = new AudioCtor();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 880;
    gain.gain.setValueAtTime(0.08, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.16);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.16);
    oscillator.onended = () => context.close().catch(() => {});
  } catch (_) {
    // The visible "answer now" indicator remains if audio is blocked
  }
}

function onSnapshot(event) {
  const snap = event.detail || {};
  if (snap.screen === "moca") {
    moca.status = "running";
    moca.taskIndex = typeof snap.moca_task_index === "number" ? snap.moca_task_index : 0;
    moca.taskTotal = typeof snap.moca_task_total === "number" ? snap.moca_task_total : 11;
    moca.taskId = snap.moca_task_id || "";
    moca.domain = snap.moca_domain || "";
    if (snap.moca_hint) moca.hint = snap.moca_hint;
    const recording = Boolean(snap.moca_recording);
    if (recording && !moca.recording) {
      playRecordingCue();
      moca.recordingSince = Date.now();
    }
    moca.recording = recording;
    moca.message = snap.message || "";
    // Ядро ждёт нажатия «Приступить»: пока ждёт, инструкцию можно переслушать.
    if (snap.moca_awaiting_start !== undefined) {
      moca.awaitingStart = Boolean(snap.moca_awaiting_start);
    }
    if (snap.moca_task_limit_seconds) moca.taskLimitSeconds = snap.moca_task_limit_seconds;
    if (snap.moca_start_grace_seconds !== undefined) {
      moca.startGraceSeconds = snap.moca_start_grace_seconds;
    }
    if (snap.moca_tts_text) {
      moca.speaking = true;
      voice.playOnce(snap.moca_tts_text, snap.moca_tts_id || "");
    }
    if (recording) moca.speaking = false;
    emit();
    return;
  }
  if (moca.status !== "running") return;
  voice.stop();
  moca.recording = false;
  moca.speaking = false;
  const report = snap.report || {};
  if (snap.screen === "summary" && report.report_type === "moca") {
    moca.status = "finished";
  } else {
    moca.status = "stopped";
    moca.message = snap.message || "";
  }
  emit();
}

window.addEventListener("nm:snapshot", onSnapshot);

export const mocaController = {
  get state() {
    return moca;
  },
  subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  async stop() {
    voice.stop();
    try {
      await fetch("/api/actions/stop_moca", { method: "POST" });
    } catch (_) {
      // The server-side test ends on its own timeouts as well
    }
  },
  // Инструкцию можно переслушать в любой момент задания.
  async repeatPrompt() {
    try {
      await fetch("/api/actions/moca_repeat_prompt", { method: "POST" });
    } catch (_) {
      // Повтор — удобство, а не обязательный шаг: отказ не прерывает тест
    }
  },
  // Задание начинается по готовности человека, а не само собой.
  async beginTask() {
    moca.awaitingStart = false;
    emit();
    try {
      await fetch("/api/actions/moca_begin_task", { method: "POST" });
    } catch (_) {
      // Ядро начнёт задание само по истечении ожидания
    }
  },
  reset() {
    moca.status = "idle";
    moca.hint = "";
    moca.awaitingStart = false;
    emit();
  },
};

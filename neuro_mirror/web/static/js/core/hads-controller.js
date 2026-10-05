// neuro_mirror/web/static/js/core/hads-controller.js
//
// Follows the HADS test run by the server (plugins/hads_test): questions,
// answer options and scoring all come from the backend; this module only
// keeps the latest state, plays the voiced prompts and sends clicks.
// Moved out of app.js (renderHads / submitHadsAnswer / stopHadsTest / TTS).

import { createVoiceChannel } from "./test-voice.js";

const voice = createVoiceChannel({ finishedUrl: "/api/actions/hads_tts_finished", idField: "hads_tts_id" });

// status: "idle" | "running" | "finished" | "stopped"
const hads = {
  status: "idle",
  questionIndex: -1,
  questionTotal: 14,
  questionId: "",
  part: "",
  text: "",
  options: [],
  selected: null,
  recording: false,
  message: "",
};

const listeners = new Set();

function emit() {
  for (const listener of listeners) listener(hads);
}

function onSnapshot(event) {
  const snap = event.detail || {};
  if (snap.screen === "hads") {
    hads.status = "running";
    hads.questionIndex = typeof snap.hads_question_index === "number" ? snap.hads_question_index : -1;
    hads.questionTotal = typeof snap.hads_question_total === "number" ? snap.hads_question_total : 14;
    hads.questionId = snap.hads_question_id || "";
    hads.part = snap.hads_part || "";
    hads.text = snap.hads_question_text || "";
    hads.options = Array.isArray(snap.hads_options) ? snap.hads_options : [];
    hads.selected = snap.hads_selected_option ?? null;
    hads.recording = Boolean(snap.hads_recording);
    hads.message = snap.message || "";
    // An answer accepted while the question is still being read cuts the speech
    if (hads.selected != null) voice.stop();
    if (snap.hads_tts_text) voice.playOnce(snap.hads_tts_text, snap.hads_tts_id || "");
    emit();
    return;
  }
  if (hads.status !== "running") return;
  voice.stop();
  const report = snap.report || {};
  if (snap.screen === "summary" && (report.report_type === "hads" || report.report_type === "screening")) {
    // The summary message contains the scores — kept out of the state on purpose
    hads.status = "finished";
  } else {
    hads.status = "stopped";
    hads.message = snap.message || "";
  }
  emit();
}

window.addEventListener("nm:snapshot", onSnapshot);

export const hadsController = {
  get state() {
    return hads;
  },
  subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  async answer(optionIndex) {
    await fetch("/api/actions/hads_answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_index: hads.questionIndex, option_index: optionIndex }),
    });
  },
  async stop() {
    voice.stop();
    try {
      await fetch("/api/actions/stop_hads", { method: "POST" });
    } catch (_) {
      // The server-side test also stops on its own answer timeout
    }
  },
  // Lets a screen start fresh after showing a finished/stopped run
  reset() {
    hads.status = "idle";
    emit();
  },
};

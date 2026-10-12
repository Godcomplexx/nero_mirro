// neuro_mirror/web/static/js/core/legacy.js
//
// The single seam between the new ES modules and the classic app.js script.
// Top-level const/let/function declarations of a classic script live in the
// shared global scope, so module code can reference them by name — but only
// this file does, so the coupling stays in one place while app.js shrinks.
// Deleted in the final cleanup stage together with app.js.

/* global state, el, fetchJson, toggleCamera, stopCamera, updateUserChip, unlockAudioPlayback, appendLogLine */

export function activeUser() {
  return state.activeUser || null;
}

// The profile as the server returned it after a change (e.g. of consents).
// Without the video consent the camera is switched off, as on profile select.
export function setActiveUser(user) {
  state.activeUser = user;
  if (!user.consents || user.consents.video !== true) stopCamera();
  updateUserChip();
}

export function userConsents() {
  return (state.activeUser && state.activeUser.consents) || {};
}

// /api/config as loaded by app.js at startup (app version etc.)
export function appConfig() {
  return state.config || {};
}

export function isCameraActive() {
  return Boolean(state.cameraActive);
}

export function cameraStream() {
  return state.mediaStream || null;
}

// The hidden full-screen <video> that app.js keeps the camera stream on;
// frame grabs (face check, rPPG) read from it.
export function cameraVideo() {
  return el.cameraPreview || null;
}

export async function ensureCamera() {
  if (!state.cameraActive) await toggleCamera();
  return Boolean(state.cameraActive);
}

// Why the last attempt to switch the camera on failed ("" when it did not)
export function cameraProblem() {
  return state.cameraProblem || "";
}

export function api(url, options) {
  return fetchJson(url, options);
}

export async function unlockAudio() {
  try {
    await unlockAudioPlayback();
  } catch (_) {
    // Autoplay unlock is best-effort.
  }
}

export function log(line) {
  appendLogLine(line);
}

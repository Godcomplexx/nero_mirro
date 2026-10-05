// neuro_mirror/web/static/js/core/test-voice.js
//
// Voiced instructions for HADS and MoCA (moved from app.js, where the same
// player existed twice as _hadsPlayTts / _mocaPlayTts). The server sends a
// prompt text + id, waits until the browser reports playback finished, then
// continues the test — so "finished" is reported even when synthesis or
// playback fails, otherwise the test would stall.

export function createVoiceChannel({ finishedUrl, idField }) {
  let sequence = 0;
  let currentAudio = null;
  let lastKey = null;

  async function notifyFinished(ttsId) {
    if (!ttsId) return;
    try {
      await fetch(finishedUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [idField]: ttsId }),
      });
    } catch (_) {
      // The server has its own timeout for a missing confirmation
    }
  }

  // Cuts current speech and invalidates any synthesis still in flight, so
  // audio for an old prompt never starts after a newer one or after a stop.
  function stop() {
    sequence += 1;
    if (!currentAudio) return;
    // pause + clearing src fires "abort", which resolves the playback promise
    // below, so the server still gets its "finished" notice
    currentAudio.pause();
    currentAudio.removeAttribute("src");
    currentAudio.load();
    currentAudio = null;
  }

  async function play(text, ttsId) {
    stop();
    const mySequence = sequence;
    try {
      const resp = await fetch("/api/tts/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!resp.ok) return;
      const blob = await resp.blob();
      if (mySequence !== sequence) return; // superseded or stopped
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      currentAudio = audio;
      const playbackDone = new Promise((resolve) => {
        audio.onended = resolve;
        audio.onerror = resolve;
        audio.onabort = resolve;
      });
      await audio.play();
      await playbackDone;
      URL.revokeObjectURL(url);
      if (currentAudio === audio) currentAudio = null;
    } catch (_) {
      // Autoplay blocked or synthesis failed — text stays on screen
    } finally {
      await notifyFinished(ttsId);
    }
  }

  // Plays a prompt once per id, however many snapshots repeat it
  function playOnce(text, ttsId) {
    const key = ttsId || text;
    if (key === lastKey) return;
    lastKey = key;
    play(text, ttsId);
  }

  return { play, playOnce, stop };
}

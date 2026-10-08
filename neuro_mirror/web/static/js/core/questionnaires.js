// neuro_mirror/web/static/js/core/questionnaires.js
//
// Questionnaire content (questions, answer scales) belongs to the backend,
// like HADS and MoCA already do — the frontend only renders it. The SAN
// questionnaire comes from GET /api/questionnaires/san; if the server returns
// nothing usable this returns null and the screen shows a stub instead of
// hardcoded questions.
//
// Expected contract for GET /api/questionnaires/san:
//   {
//     "questions": [{ "id": "wellbeing_1", "group": "Самочувствие", "text": "…" }, …],
//     "scale":     [{ "value": 1, "label": "Очень плохое" }, … ]   // negative → positive
//   }

import { api, log } from "./legacy.js";

function isValidQuestionnaire(data) {
  return Boolean(
    data &&
      Array.isArray(data.questions) &&
      data.questions.length > 0 &&
      data.questions.every((q) => q && typeof q.text === "string" && q.text.trim()) &&
      Array.isArray(data.scale) &&
      data.scale.length >= 2 &&
      data.scale.every((option) => option && option.value != null && typeof option.label === "string")
  );
}

export async function loadSanQuestionnaire() {
  try {
    const data = await api("/api/questionnaires/san");
    if (isValidQuestionnaire(data)) return data;
    log("[san] questionnaire from server has an unexpected shape — showing stub");
  } catch (_) {
    // Endpoint not implemented on the server yet — expected for now.
  }
  return null;
}

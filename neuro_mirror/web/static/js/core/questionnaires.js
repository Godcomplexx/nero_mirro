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
//     "questions": [{ "id": "wellbeing_1", "group": "Самочувствие", "text": "…",
//                     "options": [{ "value": 1, "label": "…" }, …] }, …],  // options optional
//     "scale":     [{ "value": 1, "label": "Очень плохое" }, … ]   // negative → positive
//   }
//
// Answers go to POST /api/questionnaires/san as
//   { "moment": "before" | "after", "answers": { "<question id>": value }, "session_id": "…" }

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
    // A server without the questionnaire — the screen shows a stub.
  }
  return null;
}

// answers: [{ id, value }] as handed over by the SAN survey's onDone.
// Throws when the server did not store them.
export function saveSanAnswers(answers, { moment, sessionId = "" }) {
  const byId = {};
  for (const answer of answers) {
    if (answer.id != null && answer.value != null) byId[answer.id] = answer.value;
  }
  return api("/api/questionnaires/san", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ moment, answers: byId, session_id: sessionId }),
  });
}

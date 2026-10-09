// neuro_mirror/web/static/js/core/training.js
//
// Training course data that already exists on the server: after a completed
// MoCA the aggregator stores the composition of the next session in the
// report (domains.moca_training_plan, built by screening/training_plan.py —
// rows { domain, score, max_score, shortfall, tasks }). Training is unlocked
// by the presence of such a report. The session itself — one of the twelve
// sessions of the course, ten games in order — comes ready from
// GET /api/training/session; the games are played through js/core/games.js.

import { api } from "./legacy.js";

async function detailOf(response) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail.trim();
  } catch (_) {
    // no readable body
  }
  return "";
}

// The session of the course the core keeps for the user:
// GET /api/training/session → { course: { session_number, sessions_total,
// completed_sessions, stage: { id, title } }, status,
// games: [{ position, domain, domain_code, game_code, title, stimulus_set,
// difficulty_level, adaptation, flags, reasons,
// status: pending | started | done | abandoned | not_presented }],
// plan: { domain: count }, profile, session_size, skipped, level_changes,
// source_session_id }.
// The core saves the plan when it composes the session, so asking again
// returns the same session until it is finished. Nothing is computed here —
// the list is played in the order given.
//
// Returns one of
//   { status: "ready", session }
//   { status: "locked", message }   — 409: a state, shown as is
//   { status: "unsupported" }       — the core has no such request yet
//   { status: "failed", message }
export async function loadTrainingSession() {
  let response;
  try {
    response = await fetch("/api/training/session");
  } catch (_) {
    return { status: "failed", message: "Нет связи с ядром программы. Перезапустите приложение и повторите попытку." };
  }
  if (response.ok) return { status: "ready", session: await response.json() };
  const message = await detailOf(response);
  if (response.status === 409) return { status: "locked", message };
  if (response.status === 404 || response.status === 405) return { status: "unsupported" };
  return { status: "failed", message: message || "Не удалось подобрать занятие. Повторите попытку." };
}

// The end of a session, normal or early (from the pause screen). A game
// started and not finished becomes "abandoned" in the core. Returns
// { finished, status, done, total } or null when the core is unreachable.
export async function finishTrainingSession(reason) {
  try {
    const response = await fetch("/api/training/session/finish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason || "" }),
    });
    return response.ok ? await response.json() : null;
  } catch (_) {
    return null;
  }
}

// Pauses go to the session journal; a failed note must not stop the pause.
export async function notePause(position) {
  try {
    await fetch("/api/training/session/pause", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position }),
    });
  } catch (_) {
    // the pause itself works without the journal
  }
}

export async function noteResume() {
  try {
    await fetch("/api/training/session/resume", { method: "POST" });
  } catch (_) {
    // the pause itself works without the journal
  }
}

// Returns { unlocked, plan: [{ domain, tasks, score, max_score }], total, testedAt }
export async function loadTrainingPlan() {
  const empty = { unlocked: false, plan: [], total: 0, testedAt: null };
  let items;
  try {
    const data = await api("/api/results");
    items = data.items || [];
  } catch (_) {
    return empty;
  }
  const mocaReports = items
    .filter((item) => item.report_type === "moca")
    .sort((a, b) => String(b.stored_at || "").localeCompare(String(a.stored_at || "")));
  if (mocaReports.length === 0) return empty;

  const latest = mocaReports[0];
  const rows = Array.isArray((latest.domains || {}).moca_training_plan) ? latest.domains.moca_training_plan : [];
  const plan = rows
    .filter((row) => row && row.domain && Number(row.tasks) > 0)
    .map((row) => ({
      domain: String(row.domain),
      tasks: Number(row.tasks),
      score: row.score,
      max_score: row.max_score,
    }));
  return {
    unlocked: true,
    plan,
    total: plan.reduce((sum, row) => sum + row.tasks, 0),
    testedAt: latest.stored_at || null,
  };
}

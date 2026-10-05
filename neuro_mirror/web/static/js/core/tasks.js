// neuro_mirror/web/static/js/core/tasks.js
//
// Library of social-everyday tasks (deck slide 9). Its content — task list,
// categories, difficulty — belongs to the backend and the methodology is
// still being worked out, so no endpoint exists yet; until it does this
// returns null and the screen shows a stub instead of invented tasks.
//
// Expected contract for GET /api/tasks:
//   {
//     "domains": [{ "id": "memory", "label": "Память" }, …],
//     "tasks": [{ "id": "shopping_list", "title": "Список покупок",
//                 "description": "…", "domain": "memory",
//                 "level": "Базовый", "image_url": "/static/…" (optional) }, …]
//   }

import { api, log } from "./legacy.js";

function isValidLibrary(data) {
  return Boolean(
    data &&
      Array.isArray(data.domains) &&
      Array.isArray(data.tasks) &&
      data.tasks.every((task) => task && task.id && typeof task.title === "string")
  );
}

export async function loadTaskLibrary() {
  try {
    const data = await api("/api/tasks");
    if (isValidLibrary(data)) return data;
    log("[tasks] library from server has an unexpected shape — showing stub");
  } catch (_) {
    // Endpoint not implemented on the server yet — expected for now.
  }
  return null;
}

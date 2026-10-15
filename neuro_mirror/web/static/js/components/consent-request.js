// neuro_mirror/web/static/js/components/consent-request.js
//
// Asks for one consent, always the same way: where it is missing (e.g. the
// video consent on «Базовый скрининг») and on «Устройства, согласия».
// The exact consent text comes from the server and is shown before anything
// is recorded; the consent is given only by pressing «Даю согласие».
// The server stores it the same way as on the consents screen
// (POST /api/users/{id}/consents). Resolves true when the consent was given.

import { activeUser, api, setActiveUser } from "../core/legacy.js";
import { confirmDialog } from "./confirm-dialog.js";
import { notify } from "./notify.js";

const TITLES = {
  audio: "Согласие на обработку аудиоданных",
  video: "Согласие на обработку видеоданных",
  dataset: "Согласие на сохранение записей в набор данных",
};

// doneMessage: the confirmation shown once the consent is stored
export async function requestConsent(type, { doneMessage = "" } = {}) {
  const user = activeUser();
  if (!user) return false;
  let text = "";
  try {
    const data = await api("/api/users");
    text = (data.consent_texts || {})[type] || "";
  } catch (_) {
    // the text could not be loaded: the consent is not asked for without it
  }
  if (!text) {
    notify("Не удалось загрузить текст согласия. Его можно дать в разделе «Устройства, согласия и сведения о программе».");
    return false;
  }
  const confirmed = await confirmDialog({
    title: TITLES[type] || "Согласие",
    message: `${text} Согласие можно отозвать в разделе «Устройства, согласия и сведения о программе».`,
    confirmLabel: "Даю согласие",
    cancelLabel: "Не сейчас",
  });
  if (!confirmed) return false;
  try {
    const result = await api(`/api/users/${encodeURIComponent(user.id)}/consents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent_type: type, given: true }),
    });
    if (result && result.user) setActiveUser(result.user);
    notify(doneMessage || "Согласие дано.", { kind: "info" });
    return true;
  } catch (error) {
    notify(`Согласие не сохранено: ${error.message || error}`);
    return false;
  }
}

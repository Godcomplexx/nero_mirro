// neuro_mirror/web/static/js/screens/service.js
//
// «Устройства и сведения о программе»: camera/microphone selection and the
// app version, which used to live only in the old main-menu overlay. Not in
// the sidebar (a service page) — opened from the link under Главное меню and
// automatically when the server asks for device setup.
//
// The device form itself is still driven by app.js (loadDevices,
// submitDeviceSelection, … look its fields up by id), so the existing
// <form id="devices-form"> node is moved here rather than rebuilt.
//
// «Согласия»: the active profile's consents with a button to withdraw or give
// each one (POST /api/users/{id}/consents). The server decides what is
// allowed — personal data processing cannot be withdrawn, the dataset needs
// audio and video, withdrawing audio or video also withdraws the dataset.

import { activeUser, api, appConfig, setActiveUser } from "../core/legacy.js";
import { confirmDialog } from "../components/confirm-dialog.js";
import { notify } from "../components/notify.js";
import { requestConsent } from "../components/consent-request.js";

const devicesForm = document.getElementById("devices-form");

const CONSENTS = [
  { type: "personal", title: "Обработка персональных данных", required: true },
  { type: "audio", title: "Аудиоданные", withdrawNote: "Тест MoCA и задания с ответом голосом станут недоступны." },
  { type: "video", title: "Видеоданные", withdrawNote: "Камера выключится, видеоанализ станет недоступен. Согласие на набор данных тоже будет отозвано." },
  { type: "dataset", title: "Сохранение записей в набор данных", withdrawNote: "Новые записи ваших прохождений сохраняться не будут." },
];

let consentTexts = null;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

async function changeConsent(item, given, list) {
  const user = activeUser();
  if (!user) return;
  // Giving a consent: the same window with its full text as everywhere else
  if (given) {
    await requestConsent(item.type, { doneMessage: `Согласие «${item.title}» дано.` });
    renderConsents(list);
    return;
  }
  const confirmed = await confirmDialog({
    title: `Отозвать согласие «${item.title}»?`,
    message: item.withdrawNote || "Согласие можно будет дать снова здесь же.",
    confirmLabel: "Отозвать",
    cancelLabel: "Оставить",
  });
  if (!confirmed) return;
  try {
    const result = await api(`/api/users/${encodeURIComponent(user.id)}/consents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent_type: item.type, given: false }),
    });
    if (result && result.user) setActiveUser(result.user);
    notify(`Согласие «${item.title}» отозвано.`, { kind: "info" });
  } catch (error) {
    notify(`Согласие не изменено: ${error.message || error}`);
  }
  renderConsents(list);
}

function renderConsents(list) {
  if (!list.isConnected) return;
  const user = activeUser();
  list.replaceChildren();
  if (!user) {
    list.appendChild(el("li", "nm-panel-text", "Сначала выберите профиль."));
    return;
  }
  const consents = user.consents || {};
  for (const item of CONSENTS) {
    const given = consents[item.type] === true;
    const row = el("li", "nm-consent-row");
    const info = el("div", "nm-consent-info");
    info.append(el("strong", null, item.title));
    const text = consentTexts && consentTexts[item.type];
    if (text) info.append(el("span", "nm-consent-text", text));
    info.append(el("span", `nm-consent-state nm-consent-state-${given ? "on" : "off"}`, given ? "Согласие дано" : "Согласие не дано"));
    row.appendChild(info);
    if (item.required) {
      row.appendChild(el("span", "nm-consent-note", "Обязательно для работы программы"));
    } else {
      row.appendChild(
        button(given ? "Отозвать" : "Дать согласие", given ? "secondary" : "primary", () => changeConsent(item, !given, list)),
      );
    }
    list.appendChild(row);
  }
}

function button(label, variant, onClick) {
  const node = el("button", `nm-btn nm-btn-${variant}`, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

function buildConsents() {
  const panel = el("section", "nm-panel nm-service nm-service-consents");
  const list = el("ul", "nm-consent-list");
  list.setAttribute("aria-live", "polite");
  panel.append(
    el("h2", "nm-panel-title", "Согласия"),
    el("p", "nm-panel-text", "Здесь можно отозвать согласие или дать его снова. Уже сохранённые результаты при этом не удаляются."),
    list,
  );
  // Drawn once the panel is on the page: the screen inserts it right after
  // this returns, and renderConsents skips a list that is not on the page
  queueMicrotask(() => renderConsents(list));
  if (!consentTexts) {
    api("/api/users")
      .then((data) => {
        consentTexts = data.consent_texts || {};
        renderConsents(list);
      })
      .catch(() => {
        // Without the texts the consents are listed by their titles only
      });
  }
  return panel;
}

export const serviceScreen = {
  mount(container) {
    container.appendChild(el("p", "nm-workarea-subtitle", "Выбор камеры и микрофона, согласия, версия программы"));

    const devices = el("section", "nm-panel nm-service nm-service-devices");
    devices.append(
      el("h2", "nm-panel-title", "Устройства"),
      el("p", "nm-panel-text", "Выберите камеру и микрофон, которые будет использовать программа, и нажмите «Подтвердить»."),
    );
    if (devicesForm) devices.appendChild(devicesForm);

    const version = appConfig().app_version || "—";
    const about = el("section", "nm-panel nm-service nm-service-about");
    about.append(
      el("h2", "nm-panel-title", "Сведения о программе"),
      el("p", "nm-panel-text", `«Нейро-зеркало», версия ${version}.`),
      el("p", "nm-panel-text", "Локальное приложение для скрининга, тестов MoCA и HADS и видеоанализа. Работает без подключения к интернету."),
      el("p", "nm-panel-text", "Результаты являются скрининговой информацией и не заменяют консультацию врача."),
    );

    container.append(devices, buildConsents(), about);
  },
  unmount() {
    // Keep the form in the document so app.js can still update it
    const holder = document.getElementById("nm-service-holder");
    if (devicesForm && holder) holder.appendChild(devicesForm);
  },
  isBusy() {
    return false;
  },
  leaveWarning() {
    return null;
  },
};

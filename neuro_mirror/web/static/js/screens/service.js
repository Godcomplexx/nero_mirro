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

import { appConfig } from "../core/legacy.js";

const devicesForm = document.getElementById("devices-form");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export const serviceScreen = {
  mount(container) {
    container.appendChild(el("p", "nm-workarea-subtitle", "Выбор камеры и микрофона, версия программы"));

    const devices = el("section", "nm-panel nm-service");
    devices.append(
      el("h2", "nm-panel-title", "Устройства"),
      el("p", "nm-panel-text", "Выберите камеру и микрофон, которые будет использовать программа, и нажмите «Подтвердить»."),
    );
    if (devicesForm) devices.appendChild(devicesForm);

    const version = appConfig().app_version || "—";
    const about = el("section", "nm-panel nm-service");
    about.append(
      el("h2", "nm-panel-title", "Сведения о программе"),
      el("p", "nm-panel-text", `«Нейро-зеркало», версия ${version}.`),
      el("p", "nm-panel-text", "Локальное приложение для скрининга, тестов MoCA и HADS и видеоанализа. Работает без подключения к интернету."),
      el("p", "nm-panel-text", "Результаты являются скрининговой информацией и не заменяют консультацию врача."),
    );

    container.append(devices, about);
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

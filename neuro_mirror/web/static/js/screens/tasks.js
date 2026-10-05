// neuro_mirror/web/static/js/screens/tasks.js
//
// «Задачи» — library of social-everyday tasks grouped by cognitive domain
// (deck slide 9: search, domain filter, cards with level). Marked in the deck
// itself as «в разработке, уточнение методики»: the content comes from the
// server (js/core/tasks.js) and, until the server provides it, the screen is
// a stub. Running a task is not available yet either.

import { loadTaskLibrary } from "../core/tasks.js";
import { createDomainTag } from "../components/domain-tag.js";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function buildStub() {
  const panel = el("section", "nm-panel nm-stub");
  panel.append(
    el("h2", "nm-panel-title", "Библиотека задач в разработке"),
    el(
      "p",
      "nm-panel-text",
      "Здесь появятся социально-бытовые задачи — покупки, маршрут, оплата счетов, общение, — сгруппированные по когнитивным доменам. Методика задач сейчас уточняется, поэтому раздел пока недоступен.",
    ),
  );
  return panel;
}

function buildLibrary(library) {
  const wrap = el("div", "nm-tasks");
  const domainLabel = new Map(library.domains.map((d) => [d.id, d.label]));
  let filterDomain = null;
  let query = "";

  const toolbar = el("div", "nm-tasks-toolbar");
  const searchLabel = el("label", "nm-visually-hidden", "Найти задачу");
  searchLabel.htmlFor = "nm-tasks-search";
  const search = el("input", "nm-input nm-tasks-search");
  search.type = "search";
  search.id = "nm-tasks-search";
  search.placeholder = "Найти задачу";
  toolbar.append(searchLabel, search);

  const filters = el("div", "nm-tasks-filters");
  filters.setAttribute("role", "group");
  filters.setAttribute("aria-label", "Когнитивный домен");
  const chips = library.domains.map((domain) => {
    const chip = el("button", "nm-chip");
    chip.type = "button";
    chip.appendChild(createDomainTag(domain.label));
    chip.addEventListener("click", () => {
      filterDomain = filterDomain === domain.id ? null : domain.id;
      render();
    });
    return { chip, id: domain.id };
  });
  filters.append(...chips.map((c) => c.chip));

  const grid = el("div", "nm-tasks-grid");
  grid.setAttribute("aria-live", "polite");

  function render() {
    for (const { chip, id } of chips) chip.setAttribute("aria-pressed", String(filterDomain === id));
    const q = query.trim().toLowerCase();
    const visible = library.tasks.filter(
      (task) =>
        (!filterDomain || task.domain === filterDomain) &&
        (!q || `${task.title} ${task.description || ""}`.toLowerCase().includes(q)),
    );
    grid.innerHTML = "";
    if (visible.length === 0) {
      grid.appendChild(el("p", "nm-panel-text", "Задачи не найдены. Измените поиск или фильтр."));
      return;
    }
    for (const task of visible) {
      const card = el("article", "nm-task-card");
      if (task.image_url) {
        const img = el("img", "nm-task-image");
        img.src = task.image_url;
        img.alt = "";
        card.appendChild(img);
      }
      const body = el("div", "nm-task-body");
      body.append(el("h3", "nm-task-title", task.title));
      if (task.description) body.appendChild(el("p", "nm-task-desc", task.description));
      const foot = el("div", "nm-task-foot");
      if (task.domain) foot.appendChild(createDomainTag(domainLabel.get(task.domain) || task.domain));
      if (task.level) foot.appendChild(el("span", "nm-task-level", task.level));
      const open = el("button", "nm-btn nm-btn-primary", "Открыть");
      open.type = "button";
      open.disabled = true;
      open.title = "Запуск задач появится позже";
      foot.appendChild(open);
      body.appendChild(foot);
      card.appendChild(body);
      grid.appendChild(card);
    }
  }

  search.addEventListener("input", () => {
    query = search.value;
    render();
  });

  wrap.append(toolbar, filters, grid, el("p", "nm-status-line", "Запуск задач появится после утверждения методики."));
  render();
  return wrap;
}

export const tasksScreen = {
  mount(container) {
    container.appendChild(el("p", "nm-workarea-subtitle", "Библиотека социально-бытовых задач"));
    const body = el("div");
    body.appendChild(el("p", "nm-panel-text", "Загружаю…"));
    container.appendChild(body);
    loadTaskLibrary().then((library) => {
      if (!body.isConnected) return;
      body.innerHTML = "";
      body.appendChild(library ? buildLibrary(library) : buildStub());
    });
  },
  unmount() {},
  isBusy() {
    return false;
  },
  leaveWarning() {
    return null;
  },
};

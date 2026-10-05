// neuro_mirror/web/static/js/screens/reports.js
//
// «Отчёты» (deck slide 12) in the work area, replacing the old «Мои
// результаты» overlay. «Последняя сессия» lists the stored reports from
// GET /api/results with the same metrics and trends as before (moved from
// app.js: extractResultMetrics, findPreviousMetric, trendBadge, …). Scores
// stay visible — there is no specialist role yet (user decision 2026-09-23).
// «Динамика» (per-domain charts over a period), the detailed report and PDF
// export need server data that does not exist yet, so they are stubs.

import { activeUser, api } from "../core/legacy.js";

const REPORT_TYPE_LABELS = {
  screening: "Базовый скрининг",
  hads: "Проверка самочувствия (HADS)",
  moca: "Когнитивный тест (MoCA)",
  appearance: "Оценка внешности",
};

// betterWhen: "lower" — чем меньше, тем лучше; "higher" — наоборот; null — нейтрально
function extractResultMetrics(item) {
  const domains = (item && item.domains) || {};
  const metrics = [];
  if (domains.hads_anxiety_score != null) {
    metrics.push({
      key: "anxiety",
      label: "Тревога",
      value: Number(domains.hads_anxiety_score),
      max: Number(domains.hads_anxiety_max || 21),
      betterWhen: "lower",
    });
  }
  if (domains.hads_depression_score != null) {
    metrics.push({
      key: "depression",
      label: "Депрессия",
      value: Number(domains.hads_depression_score),
      max: Number(domains.hads_depression_max || 21),
      betterWhen: "lower",
    });
  }
  if (domains.moca_score != null) {
    metrics.push({
      key: "moca",
      label: "MoCA",
      value: Number(domains.moca_score),
      max: Number(domains.moca_max_score || 0) || null,
      betterWhen: "higher",
    });
  }
  if (domains.heart_rate_bpm != null) {
    metrics.push({
      key: "pulse",
      label: "Пульс",
      value: Math.round(Number(domains.heart_rate_bpm)),
      unit: "уд/мин",
      betterWhen: null,
    });
  }
  return metrics;
}

function findPreviousMetric(items, startIndex, reportType, metricKey) {
  for (let i = startIndex + 1; i < items.length; i += 1) {
    if (items[i].report_type !== reportType) continue;
    const previous = extractResultMetrics(items[i]).find((m) => m.key === metricKey);
    if (previous) return previous;
  }
  return null;
}

// Trend vs the previous result of the same test: arrow + word, not color alone
function trendInfo(metric, previous) {
  if (!previous || metric.betterWhen == null) return null;
  const delta = metric.value - previous.value;
  if (delta === 0) return { cls: "same", text: "— так же, как в прошлый раз" };
  const improved = metric.betterWhen === "lower" ? delta < 0 : delta > 0;
  return {
    cls: improved ? "better" : "worse",
    text: `${delta < 0 ? "▼" : "▲"} ${improved ? "лучше" : "хуже"}, чем в прошлый раз`,
  };
}

function formatResultDate(isoText) {
  const date = new Date(isoText);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}, ${date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

function resultInterpretations(item) {
  const summary = (item && item.summary) || {};
  return [
    summary.hads_anxiety_interpretation,
    summary.hads_depression_interpretation,
    summary.moca_interpretation,
    summary.hads_notes,
    summary.limitations,
  ].filter(Boolean).join(" · ");
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

// ---- «Последняя сессия» -----------------------------------------------------

function buildResultCard(item, index, testItems) {
  const card = el("article", "nm-report-card");
  const head = el("div", "nm-report-card-head");
  head.append(
    el("h3", "nm-report-card-title", REPORT_TYPE_LABELS[item.report_type] || item.report_type || "Проверка"),
    el("span", "nm-report-card-date", formatResultDate(item.stored_at)),
  );
  card.appendChild(head);

  const metrics = el("div", "nm-report-metrics");
  for (const metric of extractResultMetrics(item)) {
    const tile = el("div", "nm-report-metric");
    tile.appendChild(el("span", "nm-report-metric-label", metric.label));
    const value = el("strong", "nm-report-metric-value", String(metric.value));
    if (metric.max) value.appendChild(el("small", null, ` / ${metric.max}`));
    if (metric.unit) value.appendChild(el("small", null, ` ${metric.unit}`));
    tile.appendChild(value);
    const trend = trendInfo(metric, findPreviousMetric(testItems, index, item.report_type, metric.key));
    if (trend) tile.appendChild(el("span", `nm-report-trend nm-report-trend-${trend.cls}`, trend.text));
    metrics.appendChild(tile);
  }
  card.appendChild(metrics);

  const note = resultInterpretations(item);
  if (note) card.appendChild(el("p", "nm-report-note", note));
  return card;
}

async function loadSessions(list) {
  list.innerHTML = "";
  list.appendChild(el("p", "nm-panel-text", "Загружаю результаты…"));
  let items;
  try {
    const data = await api("/api/results");
    items = data.items || [];
  } catch (error) {
    list.innerHTML = "";
    list.appendChild(el("p", "nm-panel-text", `Не удалось загрузить результаты: ${error.message || error}`));
    return;
  }
  // Only medically meaningful records (tests with numbers)
  const testItems = items.filter((item) => extractResultMetrics(item).length > 0);
  list.innerHTML = "";
  if (testItems.length === 0) {
    list.appendChild(el("p", "nm-panel-text", "Результатов пока нет. Пройдите скрининг или тест — они появятся здесь."));
    return;
  }
  testItems.forEach((item, index) => list.appendChild(buildResultCard(item, index, testItems)));
}

function buildSessionsTab() {
  const panel = el("section", "nm-panel");
  const user = activeUser();
  panel.appendChild(el("h2", "nm-panel-title", "История проверок"));
  if (user) panel.appendChild(el("p", "nm-panel-text", `${user.name} — результаты, новые сверху.`));
  const list = el("div", "nm-report-list");
  list.setAttribute("aria-live", "polite");
  panel.appendChild(list);
  loadSessions(list);
  return panel;
}

// ---- «Динамика» (stub until the server provides per-domain history) --------

function buildDynamicsTab() {
  const panel = el("section", "nm-panel nm-stub");
  panel.append(
    el("h2", "nm-panel-title", "Динамика за период"),
    el(
      "p",
      "nm-panel-text",
      "Графики по доменам «Память», «Внимание», «Абстракция» и «Речь» за выбранный период появятся, когда сервер начнёт сохранять и отдавать историю результатов по доменам.",
    ),
  );
  const row = el("div", "nm-btn-row");
  for (const label of ["Сформировать детальный отчёт", "Скачать PDF"]) {
    const btn = el("button", "nm-btn nm-btn-secondary", label);
    btn.type = "button";
    btn.disabled = true;
    row.appendChild(btn);
  }
  panel.append(row, el("p", "nm-status-line", "Детальный отчёт и выгрузка в PDF — в разработке."));
  return panel;
}

// ---- Screen ------------------------------------------------------------------

const TABS = [
  { id: "sessions", label: "Последняя сессия", build: buildSessionsTab },
  { id: "dynamics", label: "Динамика", build: buildDynamicsTab },
];

let activeTab = "sessions";

export const reportsScreen = {
  mount(container) {
    container.appendChild(el("p", "nm-workarea-subtitle", "Результаты последних проверок и динамика за период"));

    const tablist = el("div", "nm-tabs");
    tablist.setAttribute("role", "tablist");
    tablist.setAttribute("aria-label", "Вид отчёта");
    const panelHost = el("div", "nm-tab-panel");
    panelHost.setAttribute("role", "tabpanel");

    const buttons = TABS.map((tab) => {
      const button = el("button", "nm-tab", tab.label);
      button.type = "button";
      button.id = `nm-tab-${tab.id}`;
      button.setAttribute("role", "tab");
      return button;
    });

    function show(tabId, { focus = false } = {}) {
      activeTab = tabId;
      TABS.forEach((tab, i) => {
        const selected = tab.id === tabId;
        buttons[i].setAttribute("aria-selected", String(selected));
        buttons[i].tabIndex = selected ? 0 : -1;
        if (selected && focus) buttons[i].focus();
      });
      panelHost.setAttribute("aria-labelledby", `nm-tab-${tabId}`);
      panelHost.innerHTML = "";
      panelHost.appendChild(TABS.find((tab) => tab.id === tabId).build());
    }

    buttons.forEach((button, i) => {
      button.addEventListener("click", () => show(TABS[i].id));
      // Arrow keys move between tabs (WAI-ARIA tabs pattern)
      button.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        event.preventDefault();
        const step = event.key === "ArrowRight" ? 1 : -1;
        show(TABS[(i + step + TABS.length) % TABS.length].id, { focus: true });
      });
    });

    tablist.append(...buttons);
    container.append(tablist, panelHost);
    show(activeTab);
  },
  unmount() {},
  isBusy() {
    return false;
  },
  leaveWarning() {
    return null;
  },
};

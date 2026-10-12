// neuro_mirror/web/static/js/screens/reports.js
//
// «Отчёты» (deck slide 12) in the work area, replacing the old «Мои
// результаты» overlay. «Последняя сессия» lists the stored reports from
// GET /api/results with the same metrics and trends as before (moved from
// app.js: extractResultMetrics, findPreviousMetric, trendBadge, …).
//
// ТЗ, reporting module: the user gets a brief report — what was done, the
// overall result and its dynamics, limitations, a recommendation. The core
// already sends the user's view (screening/report_views.py): no HADS score
// or interpretation, no speech markers. For HADS the user only sees that the
// questionnaire was filled in. The extended report lives in «Для
// специалиста» (js/screens/specialist-report.js), behind the specialist PIN.
//
// «Динамика» draws per-domain bars from the same stored reports
// (domains.moca_domains). The PDF export is not implemented yet; its button
// stays disabled. «Выгрузить результаты игр» saves
// GET /api/results/games/export as a file.

import { activeUser, api } from "../core/legacy.js";
import { notify } from "../components/notify.js";
import { buildSpecialistTab } from "./specialist-report.js";

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

// The previous result of the same test, with the record it came from
function findPreviousMetric(items, startIndex, reportType, metricKey) {
  for (let i = startIndex + 1; i < items.length; i += 1) {
    if (items[i].report_type !== reportType) continue;
    const previous = extractResultMetrics(items[i]).find((m) => m.key === metricKey);
    if (previous) return { metric: previous, item: items[i] };
  }
  return null;
}

const isLimited = (item) => Boolean(item && item.quality && item.quality.limited);

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

// ТЗ: when the data quality is low, the interpretation is explicitly
// limited — the core sends the plain-language reason (screening/data_quality.py)
function qualityLimit(item) {
  const quality = (item && item.quality) || {};
  return quality.limited ? quality.text || "" : "";
}

// HADS: only a neutral confirmation for the user (ТЗ, HADS module)
function hadsCompletion(item) {
  const domains = (item && item.domains) || {};
  if (domains.hads_answered_count == null) return "";
  const answered = Number(domains.hads_answered_count);
  const total = Number(domains.hads_question_count || 14);
  return `Опросник о тревоге и депрессии (HADS) заполнен: ${answered} из ${total} ответов. Результаты доступны специалисту.`;
}

const hasContent = (item) => extractResultMetrics(item).length > 0 || Boolean(hadsCompletion(item));

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
    // Methodology: dynamics only between reliable sessions — no arrow when
    // either result may be inaccurate
    const previous = findPreviousMetric(testItems, index, item.report_type, metric.key);
    const comparable = previous && !isLimited(item) && !isLimited(previous.item);
    const trend = comparable ? trendInfo(metric, previous.metric) : null;
    if (trend) tile.appendChild(el("span", `nm-report-trend nm-report-trend-${trend.cls}`, trend.text));
    metrics.appendChild(tile);
  }
  if (metrics.children.length) card.appendChild(metrics);

  const hads = hadsCompletion(item);
  if (hads) card.appendChild(el("p", "nm-report-note", hads));
  const limits = qualityLimit(item);
  if (limits) {
    const note = el("p", "nm-report-note nm-report-limited");
    note.append(el("strong", null, "Результат может быть неточным. "), limits);
    card.appendChild(note);
  }
  return card;
}

async function loadSessions(list) {
  list.innerHTML = "";
  list.appendChild(el("p", "nm-panel-text", "Загружаю результаты…"));
  let items;
  let recommendation = "";
  try {
    const data = await api("/api/results");
    items = data.items || [];
    recommendation = data.recommendation || "";
  } catch (error) {
    list.innerHTML = "";
    list.appendChild(el("p", "nm-panel-text", `Не удалось загрузить результаты: ${error.message || error}`));
    return;
  }
  // Records of completed tests: with numbers or a filled-in questionnaire
  const testItems = items.filter(hasContent);
  list.innerHTML = "";
  if (testItems.length === 0) {
    list.appendChild(el("p", "nm-panel-text", "Результатов пока нет. Пройдите скрининг или тест — они появятся здесь."));
    return;
  }
  if (recommendation) list.appendChild(el("p", "nm-help-bar", recommendation));
  testItems.forEach((item, index) => list.appendChild(buildResultCard(item, index, testItems)));
}

// ---- Export of training-game results ------------------------------------------

function resultsWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return "результат";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "результата";
  return "результатов";
}

async function exportGameResults(button, status) {
  button.disabled = true;
  status.textContent = "Готовлю файл…";
  try {
    const data = await api("/api/results/games/export");
    const count = (data.game_results || []).length;
    if (count === 0) {
      status.textContent = "Результатов игр пока нет — выгружать нечего.";
      return;
    }
    const day = String(data.exported_at || new Date().toISOString()).slice(0, 10);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `game-results-${data.user_id || "user"}-${day}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = `Файл сохранён: ${count} ${resultsWord(count)} игр.`;
  } catch (error) {
    status.textContent = "";
    notify(`Не удалось выгрузить результаты игр: ${error.message || error}`);
  } finally {
    button.disabled = false;
  }
}

function buildExportRow() {
  const row = el("div", "nm-btn-row");
  const button = el("button", "nm-btn nm-btn-secondary", "Выгрузить результаты игр");
  button.type = "button";
  const status = el("p", "nm-status-line");
  status.setAttribute("role", "status");
  button.addEventListener("click", () => exportGameResults(button, status));
  row.appendChild(button);
  const wrap = el("div");
  wrap.append(row, status);
  return wrap;
}

function buildSessionsTab() {
  const panel = el("section", "nm-panel");
  const user = activeUser();
  panel.appendChild(el("h2", "nm-panel-title", "История проверок"));
  if (user) panel.appendChild(el("p", "nm-panel-text", `${user.name} — результаты, новые сверху.`));
  panel.appendChild(buildExportRow());
  const list = el("div", "nm-report-list");
  list.setAttribute("aria-live", "polite");
  panel.appendChild(list);
  loadSessions(list);
  return panel;
}

// ---- «Динамика» -------------------------------------------------------------
//
// Профиль по доменам лежит в каждом сохранённом отчёте о скрининге
// (domains.moca_domains), поэтому динамика строится из той же истории, что и
// вкладка «Последняя сессия» — отдельного запроса к ядру не нужно.

const DOMAIN_ORDER = ["Память", "Внимание", "Речь", "Абстракция"];

// Прохождения с профилем по доменам, от старых к новым.
function domainHistory(items) {
  return (items || [])
    .filter((item) => Array.isArray(item?.domains?.moca_domains) && item.domains.moca_domains.length)
    .map((item) => ({
      at: item.stored_at || "",
      byDomain: new Map(item.domains.moca_domains.map((row) => [row.domain, row])),
      limited: Boolean(item.quality && item.quality.limited),
    }))
    .sort((a, b) => String(a.at).localeCompare(String(b.at)));
}

function shortDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : date.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

// Столбики по доле набранного: домены имеют разные максимумы, и сравнивать
// их в баллах нельзя.
function domainRow(domain, passes) {
  const row = el("div", "nm-dyn-row");
  row.append(el("div", "nm-dyn-name", domain));
  const bars = el("div", "nm-dyn-bars");
  for (const pass of passes) {
    const entry = pass.byDomain.get(domain);
    const bar = el("div", "nm-dyn-bar");
    if (entry && entry.max_score) {
      const share = Math.max(0, Math.min(1, Number(entry.score) / Number(entry.max_score)));
      bar.style.setProperty("--nm-dyn-share", String(Math.round(share * 100)));
      bar.title = `${shortDate(pass.at)}: ${entry.score} из ${entry.max_score}`
        + (pass.limited ? " — результат может быть неточным" : "");
      bar.dataset.filled = "true";
      if (pass.limited) bar.dataset.limited = "true";
    } else {
      bar.title = `${shortDate(pass.at)}: нет данных`;
    }
    bars.appendChild(bar);
  }
  row.append(bars);
  return row;
}

async function loadDynamics(host) {
  host.innerHTML = "";
  host.appendChild(el("p", "nm-panel-text", "Загружаю историю…"));
  try {
    const data = await api("/api/results");
    host.innerHTML = "";
    renderDynamics(host, data.items || []);
  } catch (error) {
    host.innerHTML = "";
    host.appendChild(
      el("p", "nm-panel-text", `Не удалось загрузить историю: ${error.message || error}`),
    );
  }
}

function buildDynamicsTab() {
  const panel = el("section", "nm-panel");
  panel.append(el("h2", "nm-panel-title", "Динамика за период"));
  const host = el("div", "nm-dyn-host");
  host.setAttribute("aria-live", "polite");
  panel.append(host);
  loadDynamics(host);

  const row = el("div", "nm-btn-row");
  const pdf = el("button", "nm-btn nm-btn-secondary", "Скачать PDF");
  pdf.type = "button";
  pdf.disabled = true;
  row.appendChild(pdf);
  panel.append(row, el("p", "nm-status-line", "Подробный отчёт — во вкладке «Для специалиста». Выгрузка в PDF — в разработке."));
  return panel;
}

function renderDynamics(panel, items) {
  const passes = domainHistory(items);
  if (!passes.length) {
    panel.append(
      el("p", "nm-panel-text",
        "Динамика появится после первого когнитивного теста: она строится по его результатам."),
    );
    return;
  }
  if (passes.length === 1) {
    panel.append(
      el("p", "nm-panel-text",
        "Пройден один тест. Динамика покажется, когда появится второй — сравнивать пока не с чем."),
    );
  }

  const chart = el("div", "nm-dyn-chart");
  for (const domain of DOMAIN_ORDER) chart.append(domainRow(domain, passes));
  panel.append(chart);

  const first = passes[0];
  const last = passes[passes.length - 1];
  panel.append(
    el("p", "nm-status-line",
      // Сокращённый месяц уже кончается точкой («10 окт.»): вторую не ставим
      `Прохождений: ${passes.length}. С ${shortDate(first.at)} по ${shortDate(last.at).replace(/\.$/, "")}. ` +
      "Высота столбика — доля набранных баллов домена."),
  );
  if (passes.some((pass) => pass.limited)) {
    panel.append(el("p", "nm-status-line",
      "Столбики с пунктирной рамкой — прохождения, результат которых может быть неточным " +
      "(условия прохождения или нераспознанные ответы). Сравнивайте их с осторожностью."));
  }

}

// ---- Screen ------------------------------------------------------------------

const TABS = [
  { id: "sessions", label: "Последняя сессия", build: buildSessionsTab },
  { id: "dynamics", label: "Динамика", build: buildDynamicsTab },
  { id: "specialist", label: "Для специалиста", build: buildSpecialistTab },
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

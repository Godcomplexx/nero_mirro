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

// Речевые показатели по всем ответам теста. Считаются ядром при оценке
// (summarize_speech_metrics) и до отчёта раньше не доходили.
//
// Показываются только измеренные значения: пустое поле означает, что измерить
// было нечем — например, записи не сохранялись, — и подставлять туда ноль
// нельзя, он неотличим от настоящего нуля.
const SPEECH_ROWS = [
  { key: "words_per_minute", label: "Темп речи", unit: "слов/мин" },
  { key: "average_time_to_first_response_seconds", label: "Задержка ответа", unit: "с" },
  { key: "pause_count", label: "Пауз в ответах", unit: "" },
  { key: "total_pause_seconds", label: "Время пауз", unit: "с" },
  { key: "lexical_diversity", label: "Лексическое разнообразие", unit: "" },
  { key: "fillers", label: "Слов-заполнителей", unit: "" },
  { key: "self_corrections", label: "Самоисправлений", unit: "" },
  { key: "word_repetitions", label: "Повторов слов", unit: "" },
  { key: "unfinished_utterances", label: "Незаконченных фраз", unit: "" },
];

function countOf(value) {
  if (value && typeof value === "object") return value.count;
  return value;
}

function speechPanel(item) {
  const summary = item?.domains?.moca_speech_summary;
  if (!summary || typeof summary !== "object") return null;

  const rows = [];
  for (const row of SPEECH_ROWS) {
    const value = countOf(summary[row.key]);
    if (value == null) continue;
    rows.push({ ...row, value: typeof value === "number" ? Math.round(value * 100) / 100 : value });
  }
  if (!rows.length) return null;

  const panel = el("div", "nm-speech-panel");
  panel.append(el("h4", "nm-speech-title", "Показатели речи"));
  const list = el("div", "nm-speech-rows");
  for (const row of rows) {
    const line = el("div", "nm-speech-row");
    line.append(
      el("span", "nm-speech-label", row.label),
      el("strong", "nm-speech-value", row.unit ? `${row.value} ${row.unit}` : String(row.value)),
    );
    list.appendChild(line);
  }
  panel.appendChild(list);
  return panel;
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

  const speech = speechPanel(item);
  if (speech) card.appendChild(speech);

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
      bar.title = `${shortDate(pass.at)}: ${entry.score} из ${entry.max_score}`;
      bar.dataset.filled = "true";
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
  for (const label of ["Сформировать детальный отчёт", "Скачать PDF"]) {
    const btn = el("button", "nm-btn nm-btn-secondary", label);
    btn.type = "button";
    btn.disabled = true;
    row.appendChild(btn);
  }
  panel.append(row, el("p", "nm-status-line", "Детальный отчёт и выгрузка в PDF — в разработке."));
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
      `Прохождений: ${passes.length}. С ${shortDate(first.at)} по ${shortDate(last.at)}. ` +
      "Высота столбика — доля набранных баллов домена."),
  );

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

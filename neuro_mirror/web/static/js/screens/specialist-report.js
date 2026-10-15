// neuro_mirror/web/static/js/screens/specialist-report.js
//
// «Для специалиста» — the extended report of the ТЗ (reporting module):
// scores, domains, markers, data quality, event journal, HADS results and
// training results. The user's own tabs show a brief view without the HADS
// score and interpretation; this tab opens only after the specialist PIN.
//
// The core decides everything: GET /api/specialist/status { configured,
// active }, POST /api/specialist/login { pin } | logout and
// GET /api/specialist/report (403 when the mode is closed — it closes by
// itself after a while without requests). This screen only shows them.
// The PIN is set by the administrator in the environment variable
// NEURO_MIRROR_SPECIALIST_PIN; it is neither set nor changed from here.

import { api } from "../core/legacy.js";
import { notify } from "../components/notify.js";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function button(label, variant, onClick) {
  const node = el("button", `nm-btn nm-btn-${variant}`, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

function formatDate(isoText) {
  const date = new Date(isoText);
  if (Number.isNaN(date.getTime())) return "—";
  return `${date.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })}, ${date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

const dash = (value) => (value == null || value === "" ? "—" : String(value));
const outOf = (score, max) => (score == null ? "—" : max ? `${score} из ${max}` : String(score));

function table(headers, rows) {
  const wrap = el("div", "nm-spec-table-wrap");
  const node = el("table", "nm-spec-table");
  const head = el("thead");
  const headRow = el("tr");
  for (const header of headers) headRow.appendChild(el("th", null, header));
  head.appendChild(headRow);
  const body = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    for (const cell of row) tr.appendChild(el("td", null, dash(cell)));
    body.appendChild(tr);
  }
  node.append(head, body);
  wrap.appendChild(node);
  return wrap;
}

function section(title, ...children) {
  const node = el("section", "nm-spec-section");
  node.appendChild(el("h3", "nm-spec-title", title));
  return appendAll(node, ...children);
}

function details(summary, ...children) {
  const node = el("details", "nm-spec-details");
  node.appendChild(el("summary", null, summary));
  return appendAll(node, ...children);
}

// Optional blocks come as null; append() would print them as the text "null"
function appendAll(node, ...children) {
  node.append(...children.filter(Boolean));
  return node;
}

function line(label, value) {
  const node = el("p", "nm-spec-line");
  node.append(el("span", "nm-spec-label", `${label}: `), el("strong", null, dash(value)));
  return node;
}

// ---- Sections -----------------------------------------------------------------

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

// Only measured values: an empty field means there was nothing to measure,
// and a zero put there would be indistinguishable from a real zero
function speechMarkers(markers) {
  const values = (markers && markers.values) || {};
  const rows = [];
  for (const row of SPEECH_ROWS) {
    let value = values[row.key];
    if (value && typeof value === "object") value = value.count;
    if (value == null) continue;
    const shown = typeof value === "number" ? Math.round(value * 100) / 100 : value;
    rows.push([row.label, row.unit ? `${shown} ${row.unit}` : String(shown)]);
  }
  if (!rows.length) return null;
  const panel = el("div", "nm-speech-panel");
  panel.append(
    el("h4", "nm-speech-title", "Речевые маркеры"),
    el("p", "nm-speech-note", markers.note),
    table(["Показатель", "Значение"], rows),
  );
  return panel;
}

// ТЗ: an explicit limit of interpretation when the data quality is low;
// methodology 6.1: unrecognized answers and the «низкая достоверность» mark
function qualityBlock(quality) {
  if (!quality) return null;
  const wrap = el("div", quality.limited ? "nm-spec-quality nm-spec-quality-limited" : "nm-spec-quality");
  wrap.appendChild(line("Ограничение интерпретации", quality.limited ? "да" : "нет"));
  if ((quality.low_confidence_domains || []).length) {
    wrap.appendChild(line("Низкая достоверность", quality.low_confidence_domains.join(", ")));
  }
  const unrecognized = quality.unrecognized;
  if (unrecognized) {
    const byDomain = Object.entries(unrecognized.by_domain || {}).map(([domain, count]) => `${domain} — ${count}`).join(", ");
    wrap.appendChild(line("Нераспознанные ответы", `${unrecognized.count} из ${unrecognized.total}${byDomain ? ` (${byDomain})` : ""}`));
  }
  if ((quality.reasons || []).length) {
    const list = el("ul", "nm-spec-reasons");
    for (const reason of quality.reasons) list.appendChild(el("li", null, reason));
    wrap.appendChild(list);
  }
  return wrap;
}

// Methodology 8: MoCA change by total and domain; HADS change as context
function changeText(change) {
  if (change == null) return "—";
  if (change === 0) return "без изменений";
  return change > 0 ? `+${change}` : `−${Math.abs(change)}`;
}

function fromTo(before, after, change) {
  return `${dash(before)} → ${dash(after)} (${changeText(change)})`;
}

function dynamicsSection(data) {
  if (!data || (!data.moca && !data.hads)) {
    return section("Динамика", el("p", "nm-panel-text", "Для динамики нужны хотя бы два прохождения теста."));
  }
  const children = [];
  const moca = data.moca;
  if (moca) {
    children.push(
      el("h4", "nm-spec-subtitle", `Аудио-MoCA: ${formatDate(moca.from.stored_at)} → ${formatDate(moca.to.stored_at)}`),
      line("Сумма", fromTo(moca.from.score, moca.to.score, moca.total_change)),
      table(
        ["Домен", "Было", "Стало", "Изменение"],
        (moca.domains || []).map((row) => [row.domain, row.from, row.to, changeText(row.change)]),
      ),
    );
    if (!moca.comparable) {
      const box = el("div", "nm-spec-quality nm-spec-quality-limited");
      box.appendChild(line("Сопоставимость", "ограничена"));
      const list = el("ul", "nm-spec-reasons");
      for (const note of moca.comparability_notes || []) list.appendChild(el("li", null, note));
      box.appendChild(list);
      children.push(box);
    }
  }
  const hads = data.hads;
  if (hads) {
    children.push(
      el("h4", "nm-spec-subtitle", `HADS: ${formatDate(hads.from.stored_at)} → ${formatDate(hads.to.stored_at)}`),
      line("Тревога", fromTo(hads.anxiety.from, hads.anxiety.to, hads.anxiety.change)),
      line("Депрессия", fromTo(hads.depression.from, hads.depression.to, hads.depression.change)),
      el("p", "nm-status-line", hads.note),
    );
  }
  children.push(el("p", "nm-status-line", data.note));
  return section("Динамика", ...children);
}

function mocaSection(entries) {
  if (!entries.length) return section("Когнитивный тест (MoCA)", el("p", "nm-panel-text", "Тест ещё не проходили."));
  const cards = entries.map((entry, index) => {
    const card = el("article", "nm-report-card");
    appendAll(
      card,
      el("h4", "nm-spec-subtitle", `${formatDate(entry.stored_at)} — ${outOf(entry.score, entry.max_score)}`),
      line("Интерпретация", entry.interpretation),
      entry.notes ? line("Примечания", entry.notes) : null,
      table(
        ["Домен", "Балл", "Максимум", "Дефицит"],
        (entry.domains || []).map((row) => [row.domain, row.score, row.max_score, row.deficit]),
      ),
      qualityBlock(entry.quality),
      line("Пульс", entry.heart_rate_bpm == null ? entry.heart_rate_status : `${Math.round(entry.heart_rate_bpm)} уд/мин`),
    );
    const speech = speechMarkers(entry.speech_markers);
    if (speech) card.appendChild(speech);
    card.appendChild(details(
      "Ответы по заданиям",
      table(
        ["Задание", "Домен", "Балл", "Ответ (распознанный)", "Ожидалось"],
        (entry.tasks || []).map((task) => [task.task_id, task.domain, outOf(task.score, task.max_score), task.transcript, task.expected]),
      ),
    ));
    card.dataset.latest = String(index === 0);
    return card;
  });
  return section("Когнитивный тест (MoCA)", ...cards);
}

function hadsSection(entries) {
  if (!entries.length) return section("Тревога и депрессия (HADS)", el("p", "nm-panel-text", "Опросник ещё не заполняли."));
  const cards = entries.map((entry) => {
    const card = el("article", "nm-report-card");
    appendAll(
      card,
      el("h4", "nm-spec-subtitle", formatDate(entry.stored_at)),
      line("Тревога", `${outOf(entry.anxiety.score, entry.anxiety.max_score)} — ${dash(entry.anxiety.interpretation)}`),
      line("Депрессия", `${outOf(entry.depression.score, entry.depression.max_score)} — ${dash(entry.depression.interpretation)}`),
      line("Ответов", outOf(entry.answered_count, entry.question_count)),
      entry.notes ? line("Примечания", entry.notes) : null,
      qualityBlock(entry.quality),
    );
    if ((entry.answers || []).length) {
      card.appendChild(details(
        "Ответы на вопросы",
        table(["Вопрос", "Ответ", "Балл"], entry.answers.map((answer) => [answer.question, answer.option_text, answer.score])),
      ));
    }
    return card;
  });
  return section("Тревога и депрессия (HADS)", ...cards);
}

function screeningSection(entries) {
  if (!entries.length) return null;
  return section(
    "Базовый скрининг: видеоанализ",
    table(
      ["Дата", "Пульс", "Статус измерения", "Видео пригодно", "Ограничения"],
      entries.map((entry) => [
        formatDate(entry.stored_at),
        entry.heart_rate_bpm == null ? null : `${Math.round(entry.heart_rate_bpm)} уд/мин`,
        entry.heart_rate_status,
        entry.video_usable == null ? null : entry.video_usable ? "да" : "нет",
        ((entry.quality || {}).reasons || []).join(" ") || "нет",
      ]),
    ),
  );
}

const MOMENT_LABELS = { before: "до занятия", after: "после занятия", screening: "на скрининге" };

function sanSection(entries) {
  if (!entries.length) return null;
  return section(
    "Самочувствие (опросник)",
    table(
      ["Дата", "Когда", "Самочувствие", "Активность", "Настроение"],
      entries.map((entry) => {
        const byGroup = Object.fromEntries((entry.groups || []).map((group) => [group.group, group.mean]));
        return [formatDate(entry.stored_at), MOMENT_LABELS[entry.moment] || entry.moment,
          byGroup["Самочувствие"], byGroup["Активность"], byGroup["Настроение"]];
      }),
    ),
    el("p", "nm-status-line", "Среднее по блоку, шкала 1–5."),
  );
}

const SESSION_STATUS = { planned: "запланировано", in_progress: "идёт", completed: "выполнено", incomplete: "завершено досрочно" };

function trainingSection(course) {
  if (!course) return section("Тренировки", el("p", "nm-panel-text", "Курс тренировок ещё не начат."));
  const plan = Object.entries(course.plan || {}).map(([domain, count]) => `${domain} ${count}`).join(", ");
  const levels = Object.entries(course.levels || {}).map(([code, state]) => [code, state.level, (state.flags || []).join(", ") || "—"]);
  const children = [
    line("Состав занятия", plan),
    table(
      ["Занятие", "Этап", "Статус", "Выполнено", "Пауз"],
      (course.sessions || []).map((session) => [session.number, session.stage, SESSION_STATUS[session.status] || session.status,
        session.status === "planned" ? null : `${session.done} из ${session.total}`, session.status === "planned" ? null : session.pauses]),
    ),
  ];
  if (levels.length) children.push(el("h4", "nm-spec-subtitle", "Уровни форм"), table(["Форма", "Уровень", "Отметки"], levels));
  if ((course.level_changes || []).length) {
    children.push(details(
      "Переходы уровней",
      table(
        ["Перед занятием", "Форма", "Было", "Стало", "Успешность"],
        course.level_changes.map((change) => [change.before_session, change.game_code, change.from_level, change.to_level,
          change.success ? `${change.success.correct} из ${change.success.total}` : null]),
      ),
    ));
  }
  children.push(el("p", "nm-status-line", course.note));
  return section("Тренировки", ...children);
}

const SCENARIO_LABELS = { screening: "Базовый скрининг", hads: "HADS", moca: "MoCA", training_game: "Игра" };

function journalSection(rows) {
  if (!rows.length) return null;
  return section(
    "Журнал событий",
    table(
      ["Начало", "Сценарий", "Статус", "Окончание", "Причина прерывания"],
      rows.map((row) => [formatDate(row.started_at), SCENARIO_LABELS[row.scenario] || row.scenario, row.status,
        row.finished_at ? formatDate(row.finished_at) : null, row.interruption_reason]),
    ),
  );
}

// ---- Access -------------------------------------------------------------------

function pinField(labelText, id) {
  const wrap = el("div", "nm-spec-field");
  const label = el("label", null, labelText);
  label.htmlFor = id;
  const input = el("input", "nm-input");
  input.id = id;
  input.type = "password";
  input.inputMode = "numeric";
  input.autocomplete = "off";
  input.maxLength = 8;
  wrap.append(label, input);
  return { wrap, input };
}

function buildAccess(status, onOpened) {
  const panel = el("section", "nm-panel");
  panel.appendChild(el("h2", "nm-panel-title", "Отчёт для специалиста"));
  if (!status.configured) {
    panel.appendChild(el("p", "nm-panel-text",
      "PIN специалиста не задан. Его задаёт администратор при установке программы: " +
      "переменная окружения NEURO_MIRROR_SPECIALIST_PIN, от 4 до 8 цифр."));
    return panel;
  }
  panel.appendChild(el("p", "nm-panel-text",
    "Расширенный отчёт с баллами, результатами HADS и журналом событий доступен специалисту. Введите PIN."));
  const field = pinField("PIN", "nm-spec-pin");
  const message = el("p", "nm-status-line");
  message.setAttribute("role", "status");
  const form = el("form", "nm-spec-form");
  const submit = el("button", "nm-btn nm-btn-primary", "Открыть отчёт");
  submit.type = "submit";
  form.append(field.wrap, submit, message);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    try {
      await api("/api/specialist/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: field.input.value.trim() }),
      });
      onOpened();
    } catch (error) {
      message.textContent = error.message || String(error);
      field.input.value = "";
      field.input.focus();
    } finally {
      submit.disabled = false;
    }
  });
  panel.appendChild(form);
  setTimeout(() => field.input.isConnected && field.input.focus(), 0);
  return panel;
}

function buildReport(report, onClosed) {
  const panel = el("section", "nm-panel nm-spec-report");
  const head = el("div", "nm-spec-head");
  head.append(
    el("h2", "nm-panel-title", `Отчёт специалиста — ${report.user ? report.user.name : ""}`),
    button("Выйти из режима специалиста", "secondary", async () => {
      try {
        await api("/api/specialist/logout", { method: "POST" });
      } finally {
        onClosed();
      }
    }),
  );
  appendAll(
    panel,
    head,
    el("p", "nm-status-line", `Сформирован: ${formatDate(report.generated_at)}. Режим закрывается сам через 15 минут без действий.`),
    dynamicsSection(report.dynamics),
    mocaSection(report.moca || []),
    hadsSection(report.hads || []),
    screeningSection(report.screening || []),
    sanSection(report.san || []),
    trainingSection(report.training),
    journalSection(report.journal || []),
  );
  return panel;
}

// ---- Tab ------------------------------------------------------------------------

export function buildSpecialistTab() {
  const host = el("div", "nm-spec-host");
  host.setAttribute("aria-live", "polite");

  async function refresh() {
    host.replaceChildren(el("p", "nm-panel-text", "Загружаю…"));
    let status;
    try {
      status = await api("/api/specialist/status");
    } catch (error) {
      host.replaceChildren(el("p", "nm-panel-text", `Не удалось связаться с ядром: ${error.message || error}`));
      return;
    }
    if (!status.active) {
      host.replaceChildren(buildAccess(status, refresh));
      return;
    }
    try {
      const report = await api("/api/specialist/report");
      host.replaceChildren(buildReport(report, refresh));
    } catch (error) {
      // The mode closed meanwhile (idle timeout): ask for the PIN again
      host.replaceChildren(buildAccess({ configured: true, active: false }, refresh));
      notify(`Отчёт не открылся: ${error.message || error}`);
    }
  }

  refresh();
  return host;
}

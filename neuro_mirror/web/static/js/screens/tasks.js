// Pilot patient flow for the social-everyday situational task.
// The approved memory narrative is still isolated from automatic screening.

import { api, userConsents } from "../core/legacy.js";
import { loadTaskLibrary } from "../core/tasks.js";
import { createDomainTag } from "../components/domain-tag.js";
import { requestConsent } from "../components/consent-request.js";

const SESSION_KEY = "nm-situational-memory-session";
let busy = false;
let currentAudio = null;
let speechController = null;
let storyPlaybackCancelled = false;
let exiting = false;
let currentRecorder = null;
let currentStream = null;
let recordingTimer = null;
let discardRecording = false;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function post(url, body = {}) {
  return api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function statusMessage(panel, message, error = false) {
  let status = panel.querySelector(".nm-situational-status");
  if (!status) {
    status = el("p", "nm-situational-status");
    status.setAttribute("role", "status");
    panel.appendChild(status);
  }
  status.textContent = message;
  status.classList.toggle("is-error", error);
}

async function speak(text) {
  const controller = new AbortController();
  speechController = controller;
  let audio = null;
  try {
    const response = await fetch("/api/tts/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal: controller.signal,
    });
    if (!response.ok) throw new Error("Не удалось воспроизвести голосовую инструкцию.");
    audio = new Audio(URL.createObjectURL(await response.blob()));
    currentAudio = audio;
    await audio.play();
    await new Promise((resolve) => {
      audio.addEventListener("ended", resolve, { once: true });
      audio.addEventListener("error", resolve, { once: true });
      audio.addEventListener("abort", resolve, { once: true });
    });
  } finally {
    if (audio?.src) URL.revokeObjectURL(audio.src);
    if (currentAudio === audio) currentAudio = null;
    if (speechController === controller) speechController = null;
  }
}

function progress(state) {
  const wrap = el("div", "nm-situational-progress");
  const bar = el("div", "nm-situational-progress-bar");
  const ratio = state.progress?.total
    ? Math.min(100, Math.round((state.progress.current / state.progress.total) * 100))
    : 0;
  bar.style.width = `${ratio}%`;
  wrap.appendChild(bar);
  wrap.setAttribute("role", "progressbar");
  wrap.setAttribute("aria-valuenow", String(ratio));
  wrap.setAttribute("aria-valuemin", "0");
  wrap.setAttribute("aria-valuemax", "100");
  return wrap;
}

function answerForm(panel, state, action, label, placeholder, render) {
  const form = el("form", "nm-situational-form");
  const textarea = el("textarea", "nm-input nm-situational-answer");
  textarea.rows = 5;
  textarea.placeholder = placeholder;
  textarea.setAttribute("aria-label", placeholder);
  const submit = el("button", "nm-btn nm-btn-primary", label);
  submit.type = "submit";
  form.append(recordingControls(panel, textarea), textarea, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = textarea.value.trim();
    if (!value) {
      statusMessage(panel, "Введите тестовый ответ.", true);
      textarea.focus();
      return;
    }
    await perform(panel, state.session_id, action, value, render);
  });
  panel.appendChild(form);
  textarea.focus();
}

function additionForm(panel, state, submitAction, skipAction, placeholder, render) {
  const form = el("form", "nm-situational-form");
  const textarea = el("textarea", "nm-input nm-situational-answer");
  textarea.rows = 4;
  textarea.placeholder = placeholder;
  textarea.setAttribute("aria-label", placeholder);
  const actions = el("div", "nm-btn-row");
  const submit = el("button", "nm-btn nm-btn-primary", "Добавить ответ");
  submit.type = "submit";
  const skip = el("button", "nm-btn nm-btn-secondary", "Больше нечего добавить");
  skip.type = "button";
  skip.addEventListener("click", () => perform(panel, state.session_id, skipAction, "", render));
  actions.append(submit, skip);
  form.append(recordingControls(panel, textarea), textarea, actions);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = textarea.value.trim();
    if (!value) {
      statusMessage(panel, "Добавьте ответ или нажмите «Больше нечего добавить».", true);
      textarea.focus();
      return;
    }
    await perform(panel, state.session_id, submitAction, value, render);
  });
  panel.appendChild(form);
  textarea.focus();
}

function recordingControls(panel, textarea) {
  const wrap = el("div", "nm-situational-recording");
  const record = el("button", "nm-btn nm-btn-secondary", "Записать ответ голосом");
  const timer = el("span", "nm-situational-recording-time", "");
  record.type = "button";
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    record.disabled = true;
    record.title = "Браузер не поддерживает запись звука";
  }
  record.addEventListener("click", async () => {
    if (currentRecorder?.state === "recording") {
      currentRecorder.stop();
      return;
    }
    try {
      if (userConsents().audio !== true) {
        const granted = await requestConsent("audio", {
          doneMessage: "Согласие на временную обработку аудио сохранено. Можно начинать запись.",
        });
        if (!granted) {
          statusMessage(panel, "Для голосового ответа нужно согласие на временную обработку аудиоданных.", true);
          return;
        }
      }
      discardRecording = false;
      currentStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      const preferred = MediaRecorder.isTypeSupported?.("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      currentRecorder = new MediaRecorder(currentStream, { mimeType: preferred });
      currentRecorder.addEventListener("dataavailable", (event) => {
        if (event.data?.size) chunks.push(event.data);
      });
      currentRecorder.addEventListener("stop", async () => {
        clearInterval(recordingTimer);
        recordingTimer = null;
        currentStream?.getTracks().forEach((track) => track.stop());
        currentStream = null;
        if (discardRecording) {
          discardRecording = false;
          currentRecorder = null;
          return;
        }
        record.disabled = true;
        record.textContent = "Распознаю ответ…";
        timer.textContent = "";
        busy = true;
        try {
          const formData = new FormData();
          formData.append("audio", new Blob(chunks, { type: preferred }), "situational-answer.webm");
          const result = await api("/api/speech/transcribe", { method: "POST", body: formData });
          if (!result.accepted || !String(result.transcript || "").trim()) {
            throw new Error(result.message || "Речь не распознана. Повторите запись или введите ответ.");
          }
          textarea.value = String(result.transcript).trim();
          textarea.focus();
          statusMessage(panel, "Ответ распознан. Проверьте текст и нажмите кнопку сохранения.");
        } catch (error) {
          statusMessage(panel, error.message || "Не удалось распознать ответ.", true);
        } finally {
          busy = false;
          currentRecorder = null;
          record.disabled = false;
          record.textContent = "Записать ответ заново";
        }
      });
      currentRecorder.start(250);
      record.textContent = "Остановить запись";
      const started = Date.now();
      timer.textContent = "Запись: 0:00";
      recordingTimer = setInterval(() => {
        const seconds = Math.floor((Date.now() - started) / 1000);
        timer.textContent = `Запись: ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
        if (seconds >= 120 && currentRecorder?.state === "recording") currentRecorder.stop();
      }, 250);
      statusMessage(panel, "Говорите. Когда закончите, остановите запись.");
    } catch (error) {
      currentStream?.getTracks().forEach((track) => track.stop());
      currentStream = null;
      currentRecorder = null;
      statusMessage(panel, "Не удалось включить микрофон. Проверьте разрешение браузера и согласие на аудио.", true);
    }
  });
  wrap.append(record, timer);
  return wrap;
}

async function perform(panel, sessionId, action, value, render) {
  if (busy) return;
  busy = true;
  for (const button of panel.querySelectorAll("button")) button.disabled = true;
  statusMessage(panel, "Сохраняю…");
  try {
    const next = await post(`/api/situational-task/demo/${encodeURIComponent(sessionId)}/action`, {
      action,
      value,
    });
    render(next);
  } catch (error) {
    statusMessage(panel, error.message || "Не удалось продолжить задачу.", true);
    for (const button of panel.querySelectorAll("button")) button.disabled = false;
  } finally {
    busy = false;
  }
}

async function interruptAndExit(host, panel, sessionId) {
  if (busy && !currentAudio && !speechController) return;
  const confirmed = window.confirm(
    "Прервать эту попытку и вернуться к выбору задач? Введённые в этой попытке ответы изменить будет нельзя.",
  );
  if (!confirmed) return;
  exiting = true;
  storyPlaybackCancelled = true;
  speechController?.abort();
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.dispatchEvent(new Event("abort"));
  }
  if (currentRecorder?.state === "recording") {
    discardRecording = true;
    currentRecorder.stop();
  }
  currentStream?.getTracks().forEach((track) => track.stop());
  busy = true;
  for (const button of panel.querySelectorAll("button")) button.disabled = true;
  statusMessage(panel, "Завершаю попытку…");
  try {
    await post(`/api/situational-task/demo/${encodeURIComponent(sessionId)}/interrupt`);
    localStorage.removeItem(SESSION_KEY);
    const library = await loadTaskLibrary();
    host.innerHTML = "";
    if (library?.tasks?.length) host.appendChild(buildLibrary(library, host));
    else host.appendChild(el("p", "nm-panel-text", "Пилотный материал пока не подготовлен."));
  } catch (error) {
    statusMessage(panel, error.message || "Не удалось выйти из задачи.", true);
    for (const button of panel.querySelectorAll("button")) button.disabled = false;
  } finally {
    exiting = false;
    busy = false;
  }
}

function renderDemo(host, state) {
  host.innerHTML = "";
  const panel = el("section", "nm-panel nm-situational");
  panel.append(
    el("span", "nm-situational-demo-label", "ПИЛОТНЫЙ МАТЕРИАЛ · НЕ ДЛЯ КЛИНИЧЕСКОЙ ИНТЕРПРЕТАЦИИ"),
    el("h2", "nm-panel-title", state.title),
    el("p", "nm-situational-counter", `${state.narrative_code || "СБС-ПАМ-01"} · версия ${state.narrative_version || "пилот"}`),
    progress(state),
  );
  const render = (next) => renderDemo(host, next);

  if (!["completed", "deferred", "not_conducted"].includes(state.step)) {
    const exit = el("button", "nm-btn nm-btn-secondary", "Прервать и выйти");
    exit.type = "button";
    exit.addEventListener("click", () => interruptAndExit(host, panel, state.session_id));
    panel.appendChild(exit);
  }

  if (state.step === "intro") {
    panel.append(
      el("h3", "nm-situational-step", "Перед началом"),
      el("p", "nm-panel-text", "Вы один раз услышите короткую бытовую историю, перескажете её, рассмотрите продолжение на картинке и ответите на вопросы."),
      el("p", "nm-situational-note", "Это пилотная форма. Результаты предварительные и требуют проверки специалистом."),
    );
    const button = el("button", "nm-btn nm-btn-primary", "Продолжить");
    button.addEventListener("click", () => perform(panel, state.session_id, "begin", "", render));
    panel.appendChild(button);
  } else if (state.step === "readiness") {
    panel.append(
      el("h3", "nm-situational-step", "Готовность"),
      el("p", "nm-panel-text", "Следующее задание займёт около 10 минут. Продолжим сейчас или сделаем перерыв?"),
    );
    const actions = el("div", "nm-btn-row");
    const proceed = el("button", "nm-btn nm-btn-primary", "Продолжить");
    const pause = el("button", "nm-btn nm-btn-secondary", "Перерыв");
    proceed.addEventListener("click", () => perform(panel, state.session_id, "continue_now", "", render));
    pause.addEventListener("click", () => perform(panel, state.session_id, "defer", "", render));
    actions.append(proceed, pause);
    panel.appendChild(actions);
  } else if (state.step === "glasses") {
    panel.append(
      el("h3", "nm-situational-step", "Подготовка"),
      el("p", "nm-panel-text", "Если вы пользуетесь очками для чтения, наденьте их."),
    );
    const ready = el("button", "nm-btn nm-btn-primary", "Готово");
    ready.addEventListener("click", () => perform(panel, state.session_id, "glasses_ready", "", render));
    panel.appendChild(ready);
  } else if (state.step === "hearing") {
    panel.append(
      el("h3", "nm-situational-step", "Проверка звука"),
      el("p", "nm-panel-text", "Нажмите «Проверить звук», затем подтвердите, хорошо ли слышна тестовая фраза."),
    );
    const actions = el("div", "nm-btn-row");
    const test = el("button", "nm-btn nm-btn-secondary", "Проверить звук");
    const good = el("button", "nm-btn nm-btn-primary", "Слышно хорошо");
    const bad = el("button", "nm-btn nm-btn-secondary", "Плохо слышно");
    test.addEventListener("click", async () => {
      try {
        await speak("Проверка звука. Один, два, три.");
      } catch (error) {
        statusMessage(panel, error.message, true);
      }
    });
    good.addEventListener("click", () => perform(panel, state.session_id, "hearing_good", "", render));
    bad.addEventListener("click", () => perform(panel, state.session_id, "hearing_bad", "", render));
    actions.append(test, good, bad);
    panel.appendChild(actions);
    if ((state.preparation?.hearing_attempts || 0) === 1) {
      statusMessage(panel, "Сделайте звук громче или наденьте наушники, затем проверьте ещё раз.", true);
    }
  } else if (state.step === "story") {
    panel.append(
      el("h3", "nm-situational-step", "Прослушайте историю"),
      el("p", "nm-panel-text", "История прозвучит один раз. Её текст не показывается на экране."),
    );
    const button = el("button", "nm-btn nm-btn-primary", "Прослушать историю");
    button.addEventListener("click", async () => {
      if (busy) return;
      storyPlaybackCancelled = false;
      busy = true;
      button.disabled = true;
      try {
        await speak(state.story);
        if (storyPlaybackCancelled) return;
        busy = false;
        await perform(panel, state.session_id, "story_heard", "", render);
      } catch (error) {
        if (!storyPlaybackCancelled) {
          statusMessage(panel, error.message, true);
          button.disabled = false;
        }
      } finally {
        if (!exiting) busy = false;
      }
    });
    panel.appendChild(button);
  } else if (state.step === "retelling") {
    panel.append(
      el("h3", "nm-situational-step", "Перескажите историю"),
      el("p", "nm-panel-text", "Расскажите всё, что запомнили. Ответ можно записать голосом; распознанный текст разрешено проверить перед сохранением."),
    );
    answerForm(panel, state, "submit_retelling", "Сохранить пересказ", "Введите пересказ истории", render);
  } else if (state.step === "retelling_addition") {
    panel.append(
      el("h3", "nm-situational-step", "Дополнение к пересказу"),
      el("p", "nm-situational-question", "Что-нибудь ещё?"),
    );
    additionForm(panel, state, "submit_retelling_addition", "skip_retelling_addition", "Добавьте то, что ещё вспомнили", render);
  } else if (["orientation", "memory", "image_questions"].includes(state.step)) {
    const names = {
      orientation: "Вопросы по истории",
      memory: "Память и внимание",
      image_questions: "Риск и безопасное действие",
    };
    panel.append(el("h3", "nm-situational-step", names[state.step]));
    if (state.image_url) panel.appendChild(taskImage(state.image_url));
    panel.append(
      el("p", "nm-situational-counter", `Вопрос ${state.question_index + 1} из ${state.question_count}`),
      el("p", "nm-situational-question", state.question),
    );
    if (state.prompt) panel.appendChild(el("p", "nm-situational-prompt", state.prompt));
    if (state.step === "memory" && (state.prompt_level || 0) < 2) {
      const prompt = el("button", "nm-btn nm-btn-secondary", "Нужна подсказка");
      prompt.type = "button";
      prompt.addEventListener("click", () => perform(panel, state.session_id, "request_prompt", "", render));
      panel.appendChild(prompt);
    }
    answerForm(panel, state, "submit_answer", "Ответить", "Введите тестовый ответ", render);
  } else if (state.step === "image_description") {
    panel.append(
      el("h3", "nm-situational-step", "Опишите продолжение ситуации"),
      taskImage(state.image_url),
      el("p", "nm-panel-text", "Опишите, что происходит на картинке. Для настоящей методики этап ограничен двумя минутами."),
    );
    answerForm(panel, state, "submit_image_description", "Сохранить описание", "Опишите изображение", render);
  } else if (state.step === "image_description_addition") {
    panel.append(
      el("h3", "nm-situational-step", "Дополнение к описанию"),
      taskImage(state.image_url),
      el("p", "nm-situational-question", "Есть ли на картинке ещё что-то важное?"),
    );
    additionForm(panel, state, "submit_image_description_addition", "skip_image_description_addition", "Добавьте важную деталь", render);
  } else if (state.step === "completed") {
    localStorage.removeItem(SESSION_KEY);
    panel.append(
      el("h3", "nm-situational-step", "Ситуационная задача завершена"),
      el("p", "nm-panel-text", "Ответы сохранены и переданы на предварительный подсчёт."),
      el("p", "nm-situational-note", "Пилотные показатели должен проверить и подтвердить специалист."),
    );
    const again = el("button", "nm-btn nm-btn-secondary", "Начать заново");
    again.addEventListener("click", () => startDemo(host));
    panel.appendChild(again);
  } else if (state.step === "deferred") {
    localStorage.removeItem(SESSION_KEY);
    panel.append(
      el("h3", "nm-situational-step", "Задание отложено"),
      el("p", "nm-panel-text", "История ещё не предъявлялась. При следующем запуске подготовка начнётся заново."),
    );
    const again = el("button", "nm-btn nm-btn-primary", "Вернуться к заданию");
    again.addEventListener("click", () => startDemo(host));
    panel.appendChild(again);
  } else if (state.step === "not_conducted") {
    localStorage.removeItem(SESSION_KEY);
    panel.append(
      el("h3", "nm-situational-step", "Задание не проводится"),
      el("p", "nm-panel-text", "После двух проверок звук по-прежнему слышен плохо. Причина сохранена в протоколе."),
    );
  }
  host.appendChild(panel);
}

function taskImage(url) {
  const wrap = el("div", "nm-situational-image-wrap");
  const image = el("img", "nm-situational-image");
  image.src = url;
  image.alt = "Продолжение бытовой ситуации";
  image.addEventListener("error", () => {
    wrap.innerHTML = "";
    wrap.appendChild(el("p", "nm-situational-image-missing", "Изображение нарратива не найдено."));
  });
  wrap.appendChild(image);
  return wrap;
}

async function startDemo(host, narrativeId = "sbs-pam-01") {
  host.innerHTML = "";
  host.appendChild(el("p", "nm-panel-text", "Создаю пилотную сессию…"));
  try {
    const state = await post(`/api/situational-task/demo/start?narrative_id=${encodeURIComponent(narrativeId)}`);
    localStorage.setItem(SESSION_KEY, state.session_id);
    renderDemo(host, state);
  } catch (error) {
    host.innerHTML = "";
    host.appendChild(el("p", "nm-situational-status is-error", error.message));
  }
}

function buildLibrary(library, host) {
  const wrap = el("div", "nm-tasks");
  for (const task of library.tasks) {
    const card = el("article", "nm-task-card");
    if (task.image_url) card.appendChild(taskImage(task.image_url));
    const body = el("div", "nm-task-body");
    body.append(el("h3", "nm-task-title", task.title), el("p", "nm-task-desc", task.description));
    const foot = el("div", "nm-task-foot");
    foot.append(createDomainTag("Память"), el("span", "nm-task-level", task.level || "Пилот"));
    const open = el("button", "nm-btn nm-btn-primary", "Открыть задачу");
    open.type = "button";
    open.addEventListener("click", () => startDemo(host, task.id));
    foot.appendChild(open);
    body.appendChild(foot);
    card.appendChild(body);
    wrap.appendChild(card);
  }
  return wrap;
}

export const tasksScreen = {
  async mount(container) {
    container.appendChild(el("p", "nm-workarea-subtitle", "Социально-бытовая ситуационная задача"));
    const host = el("div");
    host.appendChild(el("p", "nm-panel-text", "Загружаю…"));
    container.appendChild(host);
    const saved = localStorage.getItem(SESSION_KEY);
    if (saved) {
      try {
        let state = await api(`/api/situational-task/demo/${encodeURIComponent(saved)}`);
        const terminal = ["completed", "deferred", "not_conducted"].includes(state.step);
        if (state.status === "interrupted" || (state.status !== "in_progress" && !terminal)) {
          state = await post(`/api/situational-task/demo/${encodeURIComponent(saved)}/resume`);
        }
        renderDemo(host, state);
        return;
      } catch (_) {
        localStorage.removeItem(SESSION_KEY);
      }
    }
    const library = await loadTaskLibrary();
    host.innerHTML = "";
    if (library?.tasks?.length) host.appendChild(buildLibrary(library, host));
    else host.appendChild(el("p", "nm-panel-text", "Пилотный материал пока не подготовлен."));
  },
  unmount() {
    storyPlaybackCancelled = true;
    speechController?.abort();
    speechController = null;
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.dispatchEvent(new Event("abort"));
    }
    currentAudio = null;
    clearInterval(recordingTimer);
    recordingTimer = null;
    if (currentRecorder?.state === "recording") {
      discardRecording = true;
      currentRecorder.stop();
    }
    currentStream?.getTracks().forEach((track) => track.stop());
    currentRecorder = null;
    currentStream = null;
  },
  isBusy() {
    return busy || currentRecorder?.state === "recording";
  },
  leaveWarning() {
    return busy ? { title: "Ответ сохраняется", message: "Дождитесь сохранения текущего этапа." } : null;
  },
};

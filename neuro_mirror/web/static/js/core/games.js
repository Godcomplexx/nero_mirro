// neuro_mirror/web/static/js/core/games.js
//
// Training games. Each game is owned by the core: its rules, scoring and its
// own drawing module (GET /api/games/{code}/renderer.js, contract
// `mount({ container, definition, api, close })` → optional cleanup). The
// interface only gives the game a place on the screen and the two requests
// it plays through: POST /api/games/{code}/start and …/answer.
//
// Two things are common to every game and live here, not in the games:
// – continuing after a pause («Методика подбора и оценки тренировочного
//   курса» v2, 4.5, п. 5): with `resumeSessionId` the game's start asks the
//   core to present the interrupted trial again (POST …/resume) instead of
//   starting the task over; the core answers like a start, so the game draws
//   it as usual. If the core cannot continue (409), the task starts over;
// – the time limit of a task (GM-01, GM-10): the core says in every answer
//   how much time is left (`time_left_ms`); when it runs out, the core is
//   told so (`action: "timeout"`) and ends the task by its own clock.

import { api } from "./legacy.js";
import { fitToBox } from "../components/fit-box.js";
import { adjustmentsFor } from "./game-adjustments.js";
import { practiceFor, usesInterfacePractice } from "../practice/index.js";
import { runGameIntro } from "../components/game-intro.js";

let catalogPromise = null;

// Definitions of all games (GET /api/games/catalog), loaded once
export function loadCatalog() {
  if (!catalogPromise) {
    catalogPromise = api("/api/games/catalog").catch((error) => {
      catalogPromise = null;
      throw error;
    });
  }
  return catalogPromise;
}

// A start screen (instruction, example, start button) is not blown up to the
// whole field the way a playing field is
function startScreenLimit(box) {
  const startScreen = [...box.querySelectorAll("[data-start]")].some((node) => node.offsetParent !== null);
  return startScreen ? 1.3 : undefined;
}

const sameCode = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();

// The game's own start keeps a place for a recorded GIF. The button that
// leaves that screen and starts the task is «Начать игру».
function skipRecordedExample(container) {
  const begin = container.querySelector("[data-confirm-start]")
    || container.querySelector("[data-complete] [data-start]");
  if (begin) begin.click();
}

// Puts the game `gameCode` into `container`.
//   onClose()    — the game's own «close» button was pressed
//   onFinished() — the core answered that the game is over
//   onError(text) — the core refused a request of the game (the game modules
//                   do not show such refusals themselves)
// Resolves with a function that removes the game from the screen.
export async function mountGame(
  gameCode,
  container,
  {
    onClose = () => {},
    onFinished = () => {},
    onError = () => {},
    fallbackTitle = "",
    // Step to start at (intro | practice | done | game) and a report of steps
    introStage = "intro",
    onIntroStage = () => {},
    // Что сказать ядру при запуске. У задания курса это номер занятия и
    // задания ({ course_session, course_position }): уровень, стимульный
    // набор и зерно ядро берёт из сохранённого плана занятия.
    startOptions = null,
    // Стимульный набор задания курса — из плана занятия; его же ядро
    // поставит при запуске. В свободной игре набор выбирается случайно,
    // чтобы не показывать всегда первый.
    stimulusSet = null,
    // Игровая сессия, прерванная паузой: продолжить с прерванной пробы
    resumeSessionId = "",
    // Ядро открыло игровую сессию (её id нужен, чтобы продолжить после паузы)
    onSessionStarted = () => {},
  } = {},
) {
  const catalog = await loadCatalog();
  const definition = catalog.find((item) => sameCode(item.code, gameCode)) || { code: gameCode, title: fallbackTitle };
  const availableSets = Array.isArray(definition.stimulus_sets) ? definition.stimulus_sets : [];
  const selectedSet = availableSets.includes(stimulusSet)
    ? stimulusSet
    : availableSets.length
      ? availableSets[Math.floor(Math.random() * availableSets.length)]
      : "";
  // The game's own example shows the same set as the task itself
  const runtimeDefinition = { ...definition, selected_stimulus_set: selectedSet };
  const base = `/api/games/${encodeURIComponent(definition.code)}`;

  // Instruction, the self-playing example and a practice round. The games'
  // own start screens still contain a GIF slot; after this example the slot
  // is skipped and the task itself begins.
  const practice = practiceFor(definition.code);
  const showExample = introStage !== "game" && practice && (await usesInterfacePractice(definition.code));
  if (showExample) {
    await runGameIntro(container, {
      title: definition.title || fallbackTitle,
      practice,
      startAt: introStage,
      onStage: onIntroStage,
    });
    if (!container.isConnected) return () => {};
  }
  onIntroStage("game");
  let renderer;
  try {
    renderer = await import(`${base}/renderer.js`);
  } catch (_) {
    // A failed module load is remembered for its address, so after a
    // temporary failure the same address would fail forever — ask again
    // under a fresh one
    renderer = await import(`${base}/renderer.js?retry=${Date.now()}`);
  }
  if (typeof renderer.mount !== "function") {
    throw new Error("Задание не удалось открыть: у него нет модуля отображения.");
  }

  const adjust = adjustmentsFor(definition.code);
  let finished = false;
  let previous = null; // the core's last answer, for adjustments that compare
  let sessionId = "";
  let resumeFrom = resumeSessionId || "";
  const request = async (url, options) => {
    try {
      return await api(url, options);
    } catch (error) {
      // After the end (e.g. the time ran out) a late press of the game is
      // refused by the core; that is not a problem to show
      if (!finished) onError(error.message || String(error));
      throw error;
    }
  };

  // Time limit of the task: the core's own clock decides, this only asks it
  let timeTimer = null;
  let timeBadge = null;
  const stopTime = () => {
    if (timeTimer) clearTimeout(timeTimer);
    timeTimer = null;
    if (timeBadge) clearInterval(timeBadge.tick);
  };
  const showTime = (deadline) => {
    if (!timeBadge) {
      timeBadge = document.createElement("p");
      timeBadge.className = "nm-game-time";
      timeBadge.setAttribute("aria-live", "off");
    }
    if (!timeBadge.isConnected) container.prepend(timeBadge);
    const draw = () => {
      const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      timeBadge.textContent = `Осталось времени: ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    };
    draw();
    timeBadge.tick = setInterval(draw, 1000);
  };
  const followTime = (reply) => {
    stopTime();
    if (!reply || reply.finished || typeof reply.time_left_ms !== "number") return;
    const deadline = Date.now() + reply.time_left_ms;
    if (reply.time_visible) showTime(deadline);
    timeTimer = setTimeout(async () => {
      timeTimer = null;
      if (finished || !sessionId || !container.isConnected) return;
      try {
        await gameApi.answer({ session_id: sessionId, action: "timeout" });
      } catch (_) {
        // the core keeps the task going if its clock disagrees
      }
    }, reply.time_left_ms);
  };

  const remember = (reply) => {
    previous = reply;
    if (reply && reply.session_id && reply.session_id !== sessionId) {
      sessionId = reply.session_id;
      onSessionStarted(sessionId);
    }
    followTime(reply);
    return reply;
  };

  const gameApi = {
    async start() {
      // Back from a pause: the interrupted trial is presented again
      if (resumeFrom) {
        const from = resumeFrom;
        resumeFrom = "";
        try {
          return remember(await api(`${base}/resume`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: from, ...(startOptions || {}) }),
          }));
        } catch (_) {
          // the core cannot continue this task — it starts over below
        }
      }
      const options = { method: "POST" };
      // A course task names itself; the core takes level and set from the
      // plan. A free game asks for the set chosen above.
      const body = startOptions ? { ...startOptions } : selectedSet ? { stimulus_set: selectedSet } : null;
      if (body) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(body);
      }
      return remember(await request(`${base}/start`, options));
    },
    async answer(payload) {
      // While an answer is on its way (and an adjustment holds it back), the
      // field is marked, so adjustments can hold the player's next presses
      container.classList.add("nm-game-answering");
      let reply;
      try {
        reply = await request(`${base}/answer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (adjust.beforeReply) {
          try {
            await adjust.beforeReply(reply, previous, container, payload);
          } catch (_) {
            // an adjustment must never break the game itself
          }
        }
      } finally {
        container.classList.remove("nm-game-answering");
      }
      // An answer that only reports a wrong attempt keeps the trial and its time
      if (reply && (reply.finished || typeof reply.time_left_ms === "number")) remember(reply);
      else previous = reply;
      if (reply && reply.finished && !finished) {
        finished = true;
        stopTime();
        onFinished(reply);
      }
      return reply;
    },
  };

  container.replaceChildren();
  const cleanup = await renderer.mount({ container, definition: runtimeDefinition, api: gameApi, close: onClose });
  if (adjust.onMounted) adjust.onMounted(container);
  // The interface example already played, or the person is returning straight
  // to the task: do not stop on the game's own «here will be a GIF» screen.
  if (practice && (showExample || introStage === "game")) skipRecordedExample(container);
  // The game field is scaled to the room it has instead of getting a scrollbar
  const stopFitting =
    adjust.fit === false ? () => {} : fitToBox(container, ".game-stage-new", { maxZoom: startScreenLimit });
  return () => {
    stopTime();
    stopFitting();
    if (typeof cleanup === "function") {
      try {
        cleanup();
      } catch (_) {
        // a game's cleanup must not break leaving the screen
      }
    }
    container.replaceChildren();
  };
}

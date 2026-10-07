// neuro_mirror/web/static/js/core/games.js
//
// Training games. Each game is owned by the core: its rules, scoring and its
// own drawing module (GET /api/games/{code}/renderer.js, contract
// `mount({ container, definition, api, close })` → optional cleanup). The
// interface only gives the game a place on the screen and the two requests
// it plays through: POST /api/games/{code}/start and …/answer.

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
    // Сложность задания. Её назначает ядро по прошлым занятиям и отдаёт в
    // составе занятия; интерфейс только передаёт её обратно при запуске.
    difficultyLevel = null,
  } = {},
) {
  const catalog = await loadCatalog();
  const definition = catalog.find((item) => sameCode(item.code, gameCode)) || { code: gameCode, title: fallbackTitle };
  const base = `/api/games/${encodeURIComponent(definition.code)}`;

  // Instruction, example and a practice round first — unless the game's own
  // screen already has them
  const practice = practiceFor(definition.code);
  if (introStage !== "game" && practice && (await usesInterfacePractice(definition.code, `${base}/renderer.js`))) {
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
  const request = async (url, options) => {
    try {
      return await api(url, options);
    } catch (error) {
      onError(error.message || String(error));
      throw error;
    }
  };
  const gameApi = {
    async start() {
      const options = { method: "POST" };
      if (difficultyLevel != null) {
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify({ difficulty_level: difficultyLevel });
      }
      previous = await request(`${base}/start`, options);
      return previous;
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
      previous = reply;
      if (reply && reply.finished && !finished) {
        finished = true;
        onFinished();
      }
      return reply;
    },
  };

  container.replaceChildren();
  const cleanup = await renderer.mount({ container, definition, api: gameApi, close: onClose });
  if (adjust.onMounted) adjust.onMounted(container);
  // The game field is scaled to the room it has instead of getting a scrollbar
  const stopFitting =
    adjust.fit === false ? () => {} : fitToBox(container, ".game-stage-new", { maxZoom: startScreenLimit });
  return () => {
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

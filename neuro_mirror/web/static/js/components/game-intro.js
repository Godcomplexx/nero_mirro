// neuro_mirror/web/static/js/components/game-intro.js
//
// Start of a game, made the way «Запомни последовательность» does it:
//   1. «Как выполнять задание» — steps on the left, a live example on the
//      right (the practice round playing by itself), «Перейти к тренировке»;
//   2. «Тренировочный пример» — the same example to do yourself; it is
//      checked on the screen and never counts in the results;
//   3. «Обучение завершено» — repeat the practice or start the game.
// The layout uses the game frame's classes (css/screens/game.css,
// css/screens/practice.css) and is scaled to the field like a game.

import { el, button, createDemoPointer } from "../practice/kit.js";
import { fitToBox } from "./fit-box.js";

const DEMO_PAUSE_MS = 1200;

function header(title, text) {
  const head = el("header", "game-header-new");
  const box = el("div");
  box.append(el("h2", null, title), el("p", null, text));
  head.append(box);
  return head;
}

// A wide or tall example is scaled down to fit the example box (never up)
function fitDemo(demoBox, area, line) {
  let frame = 0;
  const fit = () => {
    frame = 0;
    area.style.zoom = "";
    const style = getComputedStyle(demoBox);
    const width = demoBox.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const height = demoBox.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom) - line.offsetHeight - 8;
    const scale = Math.min(1, width / area.scrollWidth, height / area.scrollHeight);
    if (scale < 1) area.style.zoom = String(Math.floor(scale * 100) / 100);
  };
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(fit);
  };
  const watcher = new MutationObserver((records) => {
    if (records.some((record) => record.target !== area || record.attributeName !== "style")) schedule();
  });
  watcher.observe(area, { childList: true, subtree: true, attributes: true, characterData: true });
  fit();
  return () => {
    if (frame) cancelAnimationFrame(frame);
    watcher.disconnect();
  };
}

// Resolves when the person chooses to start the game.
export function runGameIntro(container, { title, practice, startAt = "intro", onStage = () => {} }) {
  return new Promise((resolve) => {
    let current = null; // practice instance on screen
    let pointer = null;
    const stopFitting = fitToBox(container, ".game-stage-new", {
      maxZoom: (box) => (box.querySelector("[data-start]") ? 1.3 : undefined),
    });

    function clear() {
      if (current) current.destroy();
      current = null;
      if (pointer) pointer.stop();
      pointer = null;
    }

    function finish() {
      clear();
      stopFitting();
      resolve();
    }

    function stage(child) {
      const main = el("main", "game-stage-new nm-practice");
      main.append(child);
      return main;
    }

    // 1. Instruction with the example playing by itself
    function showIntro() {
      clear();
      onStage("intro");
      const intro = el("div", "game-intro-new nm-intro");
      const steps = el("ol", "nm-intro-steps");
      for (const line of practice.steps) steps.append(el("li", null, line));
      const start = button("icon-btn primary-btn", "Перейти к тренировке", showPractice);
      start.dataset.start = "";
      const actions = el("div", "nm-intro-actions");
      actions.append(start);

      const example = el("figure", "nm-intro-example");
      const demoBox = el("div", "nm-pr-demo");
      demoBox.setAttribute("aria-hidden", "true");
      example.append(el("figcaption", null, "Посмотрите пример"), demoBox);

      intro.append(
        el("h3", null, "Как выполнять задание"),
        steps,
        el("p", "nm-intro-note", "Сначала выполним тренировочный пример. Он не учитывается в результате игры."),
        actions,
        example,
      );
      container.replaceChildren(
        header(title, "Посмотрите, как выполняется задание, и попробуйте сами."),
        stage(intro),
      );
      playDemo(demoBox);
    }

    // The example plays, pauses and starts over while it is on screen
    async function playDemo(demoBox) {
      while (demoBox.isConnected) {
        const area = el("div", "nm-pr-area");
        const line = el("p", "nm-pr-status");
        demoBox.replaceChildren(line, area);
        const demo = createDemoPointer(demoBox);
        pointer = demo;
        const instance = practice.create(area, { status: (text) => { line.textContent = text; }, solved: () => {}, demo: true });
        current = instance;
        const stopFitting = fitDemo(demoBox, area, line);
        try {
          await instance.demo(demo.act);
        } catch (_) {
          // a preview must never break the screen
        }
        await new Promise((r) => setTimeout(r, DEMO_PAUSE_MS));
        stopFitting();
        instance.destroy();
        demo.stop();
        if (current === instance) current = null;
      }
    }

    // 2. The practice round
    function showPractice() {
      clear();
      onStage("practice");
      const run = el("div", "nm-practice-run");
      const line = el("p", "nm-pr-status");
      line.setAttribute("role", "status");
      const area = el("div", "nm-pr-area");
      run.append(el("p", "nm-practice-label", "Тренировочный пример"), line, area);
      container.replaceChildren(header(title, "Тренировочный пример — он не учитывается в результате."), stage(run));
      current = practice.create(area, {
        status: (text) => { line.textContent = text; },
        solved: () => setTimeout(showDone, 1400),
      });
    }

    // 3. Done
    function showDone() {
      if (!container.isConnected) return;
      clear();
      onStage("done");
      const done = el("div", "game-intro-new nm-practice-done");
      const actions = el("div", "nm-intro-actions");
      actions.append(
        button("icon-btn", "Повторить обучение", showPractice),
        button("icon-btn primary-btn", "Да, начать игру", finish),
      );
      done.append(
        el("h3", null, "Обучение завершено"),
        el("p", null, "Вы правильно выполнили тренировочный пример. Начать игру?"),
        actions,
      );
      container.replaceChildren(header(title, "Тренировка пройдена."), stage(done));
      actions.lastChild.focus();
    }

    if (startAt === "practice") showPractice();
    else if (startAt === "done") showDone();
    else showIntro();
  });
}

// «Стоп-сигнал»: letters appear one by one — press on the normal «В», hold
// back on the mirrored one.

import { el, button, sleep } from "./kit.js";

const LETTERS = [false, true, false, true]; // mirrored?
const SHOW_MS = 1800;

export default {
  steps: [
    "На экране по одной появляются буквы «В».",
    "Если буква обычная — нажмите кнопку «Нажать».",
    "Если буква зеркальная — ничего не нажимайте и ждите следующую.",
  ],
  create(area, { status, solved }) {
    let alive = true;
    let index = -1;
    let pressed = false;
    const stimulus = el("span", "nm-pr-tile nm-pr-stimulus", "");
    const press = button("nm-btn nm-btn-primary", "Нажать", () => {
      if (index < 0 || pressed) return;
      pressed = true;
      if (LETTERS[index]) {
        mistake("Эту букву нажимать не нужно — она зеркальная.");
      } else {
        stimulus.classList.add("is-right");
        status("Верно, обычную букву нажали.");
      }
    });
    const box = el("div", "nm-pr-column");
    box.append(stimulus, press);
    area.append(box);

    let failed = false;
    function mistake(text) {
      failed = true;
      stimulus.classList.add("is-wrong");
      status(text);
    }

    async function run() {
      failed = false;
      status("Следите за буквами.");
      for (index = 0; index < LETTERS.length; index += 1) {
        if (!alive) return;
        pressed = false;
        stimulus.classList.remove("is-right", "is-wrong");
        stimulus.textContent = "В";
        stimulus.classList.toggle("is-mirrored", LETTERS[index]);
        await sleep(SHOW_MS);
        if (!alive) return;
        if (!LETTERS[index] && !pressed) mistake("Обычную букву нужно было нажать.");
        if (LETTERS[index] && !pressed) status("Верно, на зеркальную не нажали.");
        stimulus.textContent = "";
        await sleep(failed ? 1300 : 400);
        if (failed) break;
      }
      index = -1;
      if (!alive) return;
      if (failed) {
        status("Попробуем ещё раз.");
        await sleep(900);
        run();
      } else {
        status("Верно, все буквы пройдены.");
        solved();
      }
    }

    run();
    return {
      async demo(act) {
        for (let i = 0; i < LETTERS.length && act.alive(); i += 1) {
          while (index !== i && act.alive()) await act.wait(80);
          if (!LETTERS[i]) await act.click(press);
          while (index === i && act.alive()) await act.wait(80);
        }
      },
      destroy() {
        alive = false;
      },
    };
  },
};

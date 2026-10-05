// «Что изменилось?»: remember where the objects are, then say where one was.

import { el, button, picture } from "./kit.js";

const OBJECTS = { 0: ["cup.png", "Чашка"], 4: ["apple.png", "Яблоко"], 7: ["kettle.png", "Чайник"] };
const ASK = 4;
const STUDY_SECONDS = 4;

export default {
  steps: [
    "На поле на несколько секунд покажут предметы — запомните, где какой лежит.",
    "Потом предметы исчезнут, и вас спросят, где находился один из них.",
    "Нажмите на клетку, где был этот предмет.",
  ],
  create(area, { status, solved }) {
    let timer = null;
    let asking = false;
    const grid = el("div", "nm-pr-grid nm-pr-grid-3 nm-pr-cells");
    const cells = Array.from({ length: 9 }, (_, index) =>
      button("nm-pr-cell nm-pr-cell-object", "", () => pick(index)),
    );
    grid.append(...cells);
    area.append(grid);

    function study() {
      asking = false;
      cells.forEach((cell, index) => {
        cell.replaceChildren();
        if (OBJECTS[index]) cell.append(picture(...OBJECTS[index]));
      });
      let left = STUDY_SECONDS;
      status(`Запоминайте: ${left}`);
      timer = setInterval(() => {
        left -= 1;
        if (left > 0) {
          status(`Запоминайте: ${left}`);
          return;
        }
        clearInterval(timer);
        cells.forEach((cell) => cell.replaceChildren());
        status(`Где находился предмет «${OBJECTS[ASK][1]}»?`);
        asking = true;
      }, 1000);
    }

    function pick(index) {
      if (!asking) return;
      asking = false;
      if (index === ASK) {
        cells[index].classList.add("is-right");
        cells[index].append(picture(...OBJECTS[ASK]));
        status("Верно, яблоко было здесь.");
        solved();
      } else {
        cells[index].classList.add("is-wrong");
        status("Не здесь. Посмотрите на предметы ещё раз.");
        setTimeout(() => {
          cells[index].classList.remove("is-wrong");
          study();
        }, 1300);
      }
    }

    study();
    return {
      async demo(act) {
        while (!asking && act.alive()) await act.wait(100);
        await act.click(cells[ASK]);
      },
      destroy() {
        clearInterval(timer);
      },
    };
  },
};

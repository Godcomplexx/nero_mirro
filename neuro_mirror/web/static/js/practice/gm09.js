// «Отслеживание объекта»: two of five circles are marked, then all move;
// pick the two that were marked.

import { el, button, sleep } from "./kit.js";

const START = [
  [10, 15],
  [45, 10],
  [80, 20],
  [25, 70],
  [70, 72],
];
const MOVES = [
  [
    [60, 65],
    [15, 55],
    [40, 30],
    [80, 15],
    [20, 15],
  ],
  [
    [30, 20],
    [75, 60],
    [12, 70],
    [55, 15],
    [45, 72],
  ],
];
const TARGETS = [1, 3];

export default {
  steps: [
    "Несколько кругов на поле — некоторые из них ненадолго подсветятся. Это цели.",
    "Потом все круги станут одинаковыми и начнут двигаться — следите за целями глазами.",
    "Когда круги остановятся, нажмите на цели и нажмите «Готово».",
  ],
  create(area, { status, solved }) {
    let alive = true;
    let input = false;
    const chosen = new Set();
    const field = el("div", "nm-pr-field");
    const dots = START.map((_, index) =>
      button("nm-pr-dot", "", () => {
        if (!input) return;
        if (chosen.has(index)) chosen.delete(index);
        else chosen.add(index);
        dots[index].classList.toggle("is-selected", chosen.has(index));
      }),
    );
    field.append(...dots);
    const done = button("nm-btn nm-btn-primary", "Готово", async () => {
      if (!input) return;
      input = false;
      const right = chosen.size === TARGETS.length && TARGETS.every((index) => chosen.has(index));
      if (right) {
        TARGETS.forEach((index) => dots[index].classList.add("is-target"));
        status("Верно, обе цели найдены.");
        solved();
      } else {
        status("Не совсем. Давайте ещё раз.");
        await sleep(1300);
        run();
      }
    });
    const box = el("div", "nm-pr-column");
    box.append(field, done);
    area.append(box);

    function place(positions) {
      dots.forEach((dot, index) => {
        dot.style.left = `${positions[index][0]}%`;
        dot.style.top = `${positions[index][1]}%`;
      });
    }

    async function run() {
      chosen.clear();
      dots.forEach((dot) => dot.classList.remove("is-selected", "is-target"));
      field.classList.add("is-still");
      place(START);
      await sleep(50);
      field.classList.remove("is-still");
      TARGETS.forEach((index) => dots[index].classList.add("is-target"));
      status("Запомните подсвеченные круги.");
      await sleep(2000);
      if (!alive) return;
      TARGETS.forEach((index) => dots[index].classList.remove("is-target"));
      status("Следите за ними…");
      for (const positions of MOVES) {
        place(positions);
        await sleep(1700);
        if (!alive) return;
      }
      status("Нажмите на круги, которые были подсвечены, затем «Готово».");
      input = true;
    }

    run();
    return {
      async demo(act) {
        while (!input && act.alive()) await act.wait(100);
        for (const index of TARGETS) await act.click(dots[index]);
        await act.click(done);
      },
      destroy() {
        alive = false;
      },
    };
  },
};

// «Запомни последовательность»: cells light up one after another; repeat the
// order. Replaces the game's own instruction with the recorded animation.

import { el, button, sleep } from "./kit.js";

const SEQUENCE = [1, 5, 6];

export default {
  steps: [
    "Несколько клеток по очереди подсветятся.",
    "Запомните клетки и порядок их подсвечивания.",
    "Когда появится надпись «Повторите последовательность», нажмите эти клетки в том же порядке.",
  ],
  create(area, { status, solved }) {
    let input = false;
    let clicks = [];
    let alive = true;
    const grid = el("div", "nm-pr-grid nm-pr-grid-3 nm-pr-cells");
    const cells = Array.from({ length: 9 }, (_, index) =>
      button("nm-pr-cell", "", () => press(index)),
    );
    cells.forEach((cell, index) => cell.setAttribute("aria-label", `Клетка ${index + 1}`));
    grid.append(...cells);
    area.append(grid);

    async function show() {
      input = false;
      clicks = [];
      cells.forEach((cell) => cell.classList.remove("is-lit"));
      status("Смотрите и запоминайте…");
      await sleep(700);
      for (const index of SEQUENCE) {
        if (!alive) return;
        cells[index].classList.add("is-lit");
        await sleep(650);
        cells[index].classList.remove("is-lit");
        await sleep(250);
      }
      if (!alive) return;
      status("Повторите последовательность.");
      input = true;
    }

    async function press(index) {
      if (!input) return;
      // A pressed cell lights up like the shown ones and stays lit until the
      // round ends
      cells[index].classList.add("is-lit");
      clicks.push(index);
      if (index !== SEQUENCE[clicks.length - 1]) {
        input = false;
        status("Порядок неверный. Посмотрите ещё раз.");
        await sleep(1300);
        show();
        return;
      }
      if (clicks.length === SEQUENCE.length) {
        input = false;
        status("Верно, порядок повторён.");
        solved();
      }
    }

    show();
    return {
      async demo(act) {
        while (!input && act.alive()) await act.wait(100);
        for (const index of SEQUENCE) await act.click(cells[index]);
      },
      destroy() {
        alive = false;
      },
    };
  },
};

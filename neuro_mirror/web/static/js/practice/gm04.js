// «Запомни расположение»: some cells light up; mark them all, then «Готово».

import { el, button, sleep } from "./kit.js";

const LIT = [2, 4];

export default {
  steps: [
    "На несколько секунд подсветятся некоторые клетки — запомните, какие.",
    "Затем подсветка исчезнет.",
    "Отметьте все клетки, которые были подсвечены, и нажмите «Готово».",
  ],
  create(area, { status, solved }) {
    let input = false;
    let alive = true;
    const chosen = new Set();
    const grid = el("div", "nm-pr-grid nm-pr-grid-3 nm-pr-cells");
    const cells = Array.from({ length: 9 }, (_, index) =>
      button("nm-pr-cell", "", () => {
        if (!input) return;
        if (chosen.has(index)) chosen.delete(index);
        else chosen.add(index);
        // A marked cell looks like the lit ones
        cells[index].classList.toggle("is-lit", chosen.has(index));
      }),
    );
    grid.append(...cells);
    const done = button("nm-btn nm-btn-primary", "Готово", async () => {
      if (!input) return;
      const right = chosen.size === LIT.length && LIT.every((index) => chosen.has(index));
      if (right) {
        input = false;
        status("Верно, все клетки отмечены.");
        solved();
        return;
      }
      input = false;
      status("Не совсем. Посмотрите на подсветку ещё раз.");
      await sleep(1300);
      show();
    });
    const box = el("div", "nm-pr-column");
    box.append(grid, done);
    area.append(box);

    async function show() {
      chosen.clear();
      cells.forEach((cell) => cell.classList.remove("is-lit"));
      status("Запоминайте подсвеченные клетки…");
      LIT.forEach((index) => cells[index].classList.add("is-lit"));
      await sleep(2500);
      if (!alive) return;
      LIT.forEach((index) => cells[index].classList.remove("is-lit"));
      status("Отметьте клетки, которые были подсвечены.");
      input = true;
    }

    show();
    return {
      async demo(act) {
        while (!input && act.alive()) await act.wait(100);
        for (const index of LIT) await act.click(cells[index]);
        await act.click(done);
      },
      destroy() {
        alive = false;
      },
    };
  },
};

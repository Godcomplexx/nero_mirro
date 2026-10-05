// «Найди цель»: among turned and dark letters find the red upright «Т».

import { button, el } from "./kit.js";

// [colour, turn in degrees]; the target is red and not turned
const LETTERS = [
  ["dark", 90],
  ["red", 180],
  ["dark", 0],
  ["red", 0],
  ["red", 270],
  ["dark", 270],
];
const TARGET = 3;

export default {
  steps: [
    "Сначала покажут цель — красную букву «Т», которая стоит ровно.",
    "Затем появится поле с буквами: повёрнутыми и другого цвета.",
    "Нажмите на цель. Если её на поле нет, нажмите «Цели нет».",
  ],
  create(area, { status, solved }) {
    const sample = el("div", "nm-pr-row nm-pr-sample");
    sample.append(el("span", null, "Цель:"), el("span", "nm-pr-tile nm-pr-letter is-red", "Т"));
    const grid = el("div", "nm-pr-grid nm-pr-grid-3");
    let done = false;
    const cells = LETTERS.map(([colour, turn], index) => {
      const letter = el("span", null, "Т");
      letter.style.transform = `rotate(${turn}deg)`;
      const cell = button(`nm-pr-tile nm-pr-letter${colour === "red" ? " is-red" : ""}`, letter, () => {
        if (done) return;
        if (index === TARGET) {
          done = true;
          cell.classList.add("is-right");
          status("Верно, это цель.");
          solved();
        } else {
          cell.classList.add("is-wrong");
          status("Это не цель: она повёрнута или другого цвета.");
          setTimeout(() => cell.classList.remove("is-wrong"), 900);
        }
      });
      cell.setAttribute("aria-label", colour === "red" ? "Красная буква Т" : "Тёмная буква Т");
      return cell;
    });
    grid.append(...cells);
    const absent = button("nm-btn nm-btn-secondary", "Цели нет", () => {
      if (!done) status("Цель на поле есть — поищите ещё.");
    });
    const box = el("div", "nm-pr-column");
    box.append(sample, grid, absent);
    area.append(box);
    status("Найдите и нажмите цель.");
    return {
      async demo(act) {
        await act.wait(800);
        await act.click(cells[1]);
        await act.wait(700);
        await act.click(cells[TARGET]);
      },
      destroy() {},
    };
  },
};

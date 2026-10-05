// «Продолжи закономерность»: a 3 × 3 pattern with the last place missing.

import { el, singleChoice } from "./kit.js";

const ROWS = [
  ["●", "▲", "■"],
  ["▲", "■", "●"],
  ["■", "●", "?"],
];
const OPTIONS = ["●", "■", "▲", "★"];

export default {
  steps: [
    "На экране будет таблица из фигур, в которой не хватает одной.",
    "Посмотрите, как фигуры меняются по строкам и столбцам.",
    "Выберите фигуру, которая должна стоять вместо знака вопроса.",
  ],
  create(area, opts) {
    const matrix = el("div", "nm-pr-grid nm-pr-grid-3");
    for (const row of ROWS) for (const cell of row) matrix.append(el("span", "nm-pr-tile nm-pr-shape", cell));
    const choice = singleChoice(opts, {
      options: OPTIONS.map((label) => ({ label })),
      right: 2,
      columns: 4,
      tileClass: "nm-pr-shape",
      texts: {
        ask: "Какая фигура должна стоять вместо «?»",
        right: "Верно: в каждой строке и столбце все три фигуры разные.",
        wrong: "Не подходит. В каждой строке и столбце фигуры не повторяются.",
      },
    });
    const box = el("div", "nm-pr-row nm-pr-gap-large");
    box.append(matrix, choice.grid);
    area.append(box);
    return {
      async demo(act) {
        await act.wait(1200);
        await act.click(choice.buttons[2]);
      },
      destroy() {},
    };
  },
};

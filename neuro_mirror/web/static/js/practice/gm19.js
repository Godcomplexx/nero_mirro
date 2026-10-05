// «Лабиринт»: draw a path from the green start to the red finish without
// letting go. A 3 × 3 maze; walls are wherever there is no passage.

import { el } from "./kit.js";

const SIZE = 3;
// Passages between cells (index = row * 3 + column)
const OPEN = [
  [0, 1],
  [1, 4],
  [4, 7],
  [7, 8],
  [1, 2],
  [4, 3],
  [3, 6],
];
const PATH = [0, 1, 4, 7, 8];
const START = 0;
const FINISH = 8;

const linked = (a, b) => OPEN.some(([x, y]) => (x === a && y === b) || (x === b && y === a));

export default {
  steps: [
    "Найдите путь от зелёного круга до красного.",
    "Нажмите на зелёный круг и, не отпуская, ведите линию по проходам.",
    "Через стены проходить нельзя. Если отпустить раньше финиша — начните сначала.",
  ],
  create(area, { status, solved }) {
    let path = [];
    let drawing = false;
    let done = false;
    const maze = el("div", "nm-pr-maze");
    const cells = Array.from({ length: SIZE * SIZE }, (_, index) => {
      const cell = el("span", "nm-pr-maze-cell");
      cell.dataset.index = String(index);
      const row = Math.floor(index / SIZE);
      const column = index % SIZE;
      // Walls on the sides without a passage
      if (row === 0 || !linked(index, index - SIZE)) cell.classList.add("wall-top");
      if (column === SIZE - 1 || !linked(index, index + 1)) cell.classList.add("wall-right");
      if (row === SIZE - 1 || !linked(index, index + SIZE)) cell.classList.add("wall-bottom");
      if (column === 0 || !linked(index, index - 1)) cell.classList.add("wall-left");
      if (index === START) cell.append(el("span", "nm-pr-maze-start"));
      if (index === FINISH) cell.append(el("span", "nm-pr-maze-finish"));
      return cell;
    });
    maze.append(...cells);
    area.append(maze);

    function paint() {
      cells.forEach((cell, index) => cell.classList.toggle("is-path", path.includes(index)));
    }

    function reset(text) {
      path = [];
      drawing = false;
      paint();
      status(text);
    }

    function step(index) {
      if (done || !drawing) return;
      const last = path[path.length - 1];
      if (index === last) return;
      if (path.length > 1 && index === path[path.length - 2]) {
        path.pop(); // going back
        paint();
        return;
      }
      if (!linked(last, index)) {
        reset("Здесь стена. Начните снова от зелёного круга.");
        return;
      }
      path.push(index);
      paint();
      if (index === FINISH) {
        done = true;
        drawing = false;
        maze.classList.add("is-solved");
        status("Верно, вы дошли до финиша.");
        solved();
      }
    }

    function begin(index) {
      if (done) return;
      if (index !== START) {
        status("Начинайте от зелёного круга.");
        return;
      }
      drawing = true;
      path = [START];
      paint();
      status("Ведите линию, не отпуская.");
    }

    const cellAt = (event) => {
      const node = document.elementFromPoint(event.clientX, event.clientY);
      const cell = node && node.closest && node.closest(".nm-pr-maze-cell");
      return cell && maze.contains(cell) ? Number(cell.dataset.index) : null;
    };
    maze.addEventListener("pointerdown", (event) => {
      const index = cellAt(event);
      if (index === null) return;
      maze.setPointerCapture(event.pointerId);
      begin(index);
    });
    maze.addEventListener("pointermove", (event) => {
      if (!drawing) return;
      const index = cellAt(event);
      if (index !== null) step(index);
    });
    maze.addEventListener("pointerup", () => {
      if (drawing && !done) reset("Вы отпустили раньше финиша. Начните снова.");
    });

    status("Нажмите на зелёный круг и ведите к красному.");
    return {
      // The preview presses on the start and draws the path without letting go
      async demo(act) {
        await act.wait(900);
        await act.drag(
          PATH.map((index) => cells[index]),
          (k) => (k === 0 ? begin(START) : step(PATH[k])),
        );
      },
      destroy() {},
    };
  },
};

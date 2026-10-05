// «Башня»: move two disks to the right rod; a larger disk never goes on a
// smaller one. Choose the rod with a disk, then the rod to put it on.

import { el, button } from "./kit.js";

export default {
  steps: [
    "На левом стержне башня из дисков. Её нужно перенести на правый стержень.",
    "Нажмите на стержень, с которого берёте верхний диск, затем на стержень, куда кладёте.",
    "Больший диск нельзя класть на меньший.",
  ],
  create(area, { status, solved }) {
    const rods = [[2, 1], [], []]; // disk sizes, bottom first
    let from = null;
    let done = false;
    const board = el("div", "nm-pr-row nm-pr-tower");
    const rodButtons = rods.map((_, index) => {
      const rod = button("nm-pr-rod", "", () => choose(index));
      rod.setAttribute("aria-label", ["Левый стержень", "Средний стержень", "Правый стержень"][index]);
      return rod;
    });
    board.append(...rodButtons);
    area.append(board);

    function draw() {
      rodButtons.forEach((rod, index) => {
        rod.replaceChildren(el("span", "nm-pr-rod-pole"));
        rods[index].forEach((size) => {
          const disk = el("span", `nm-pr-disk is-size-${size}`);
          rod.append(disk);
        });
        rod.classList.toggle("is-selected", from === index);
      });
    }

    function choose(index) {
      if (done) return;
      if (from === null) {
        if (!rods[index].length) {
          status("На этом стержне нет дисков. Выберите стержень с диском.");
          return;
        }
        from = index;
        status("Теперь выберите, куда положить диск.");
        draw();
        return;
      }
      if (from === index) {
        from = null;
        status("Выберите стержень с диском.");
        draw();
        return;
      }
      const disk = rods[from][rods[from].length - 1];
      const top = rods[index][rods[index].length - 1];
      if (top !== undefined && top < disk) {
        status("Больший диск нельзя класть на меньший.");
        from = null;
        draw();
        return;
      }
      rods[index].push(rods[from].pop());
      from = null;
      draw();
      if (rods[2].length === 2) {
        done = true;
        board.classList.add("is-solved");
        status("Верно, башня перенесена.");
        solved();
      } else {
        status("Продолжайте.");
      }
    }

    draw();
    status("Выберите стержень, с которого возьмёте диск.");
    return {
      async demo(act) {
        await act.wait(900);
        for (const [a, b] of [
          [0, 1],
          [0, 2],
          [1, 2],
        ]) {
          await act.click(rodButtons[a]);
          await act.click(rodButtons[b]);
        }
      },
      destroy() {},
    };
  },
};

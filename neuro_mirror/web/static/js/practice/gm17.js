// «Поверни фигуру»: which of two figures is the sample turned (the other one
// is its mirror image).

import { el, singleChoice } from "./kit.js";

// An «L» made of four squares on a 3 × 3 grid
const SHAPE = [0, 3, 6, 7];

function figure(turn, mirrored) {
  const box = el("span", "nm-pr-figure");
  for (let i = 0; i < 9; i += 1) box.append(el("span", SHAPE.includes(i) ? "is-on" : null));
  box.style.transform = `rotate(${turn}deg)${mirrored ? " scaleX(-1)" : ""}`;
  return box;
}

export default {
  steps: [
    "Слева — образец, справа — два варианта.",
    "Один вариант — тот же образец, только повёрнутый. Другой — зеркальный.",
    "Нажмите на вариант, который совпадает с образцом после поворота.",
  ],
  create(area, opts) {
    const sample = el("div", "nm-pr-column nm-pr-small-gap");
    sample.append(el("span", "nm-pr-caption", "Образец"), el("span", "nm-pr-tile nm-pr-frame"));
    sample.lastChild.append(figure(0, false));
    const choice = singleChoice(opts, {
      options: [
        { label: "Зеркальная фигура", node: figure(90, true) },
        { label: "Повёрнутая фигура", node: figure(90, false) },
      ],
      right: 1,
      tileClass: "nm-pr-frame",
      texts: {
        ask: "Какой вариант — это образец после поворота?",
        right: "Верно, это та же фигура, только повёрнутая.",
        wrong: "Это зеркальная фигура — её нельзя получить поворотом.",
      },
    });
    const box = el("div", "nm-pr-row nm-pr-gap-large");
    box.append(sample, choice.grid);
    area.append(box);
    return {
      async demo(act) {
        await act.wait(1200);
        await act.click(choice.buttons[1]);
      },
      destroy() {},
    };
  },
};

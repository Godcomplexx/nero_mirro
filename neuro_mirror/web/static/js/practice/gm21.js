// «Лишний предмет»: three of one kind and one that does not belong.

import { el, picture, singleChoice } from "./kit.js";

const ITEMS = [
  ["apple.png", "Яблоко"],
  ["pear.png", "Груша"],
  ["dog.png", "Собака"],
  ["orange.png", "Апельсин"],
];

export default {
  steps: [
    "На экране будут четыре картинки.",
    "Три из них относятся к одной группе, одна — лишняя.",
    "Нажмите на лишнюю картинку.",
  ],
  create(area, opts) {
    const choice = singleChoice(opts, {
      options: ITEMS.map(([file, label]) => ({ label, node: picture(file) })),
      right: 2,
      tileClass: "nm-pr-frame",
      texts: {
        ask: "Какая картинка лишняя?",
        right: "Верно: собака — не фрукт.",
        wrong: "Эта подходит к остальным. Найдите ту, что не подходит.",
      },
    });
    const box = el("div", "nm-pr-column");
    box.append(choice.grid);
    area.append(box);
    return {
      async demo(act) {
        await act.wait(900);
        await act.click(choice.buttons[2]);
      },
      destroy() {},
    };
  },
};

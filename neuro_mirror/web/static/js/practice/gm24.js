// «Категориальное называние»: what unites three words. In the game aloud.

import { el, singleChoice } from "./kit.js";

const OPTIONS = ["овощи", "фрукты", "мебель", "животные"];

export default {
  steps: [
    "На экране будут три слова.",
    "Подумайте, что их объединяет.",
    "После сигнала назовите вслух общую категорию одним-двумя словами.",
  ],
  create(area, opts) {
    const words = el("div", "nm-pr-row");
    for (const word of ["яблоко", "груша", "слива"]) words.append(el("span", "nm-pr-tile", word));
    const choice = singleChoice(opts, {
      options: OPTIONS.map((label) => ({ label })),
      right: 1,
      texts: {
        ask: "Что объединяет эти слова? В игре это говорят вслух, здесь — нажмите.",
        right: "Верно, это фрукты.",
        wrong: "Не подходит. Подумайте, что общего у этих трёх слов.",
      },
    });
    const box = el("div", "nm-pr-column");
    box.append(words, choice.grid);
    area.append(box);
    return {
      async demo(act) {
        await act.wait(1100);
        await act.click(choice.buttons[1]);
      },
      destroy() {},
    };
  },
};

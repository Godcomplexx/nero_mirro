// «Категории»: name as many words of a category as you can. In the game the
// words are said aloud; the practice picks them from a list.

import { el, multiChoice } from "./kit.js";

const OPTIONS = ["яблоко", "стол", "груша", "морковь", "слива", "кошка"];
const RIGHT = ["яблоко", "груша", "слива"];

export default {
  steps: [
    "На экране появится категория, например «Фрукты».",
    "После сигнала называйте вслух как можно больше слов этой категории.",
    "Говорите, пока идёт запись, — она закончится сама.",
  ],
  create(area, opts) {
    const title = el("strong", "nm-pr-heading", "Фрукты");
    const choice = multiChoice(opts, {
      options: OPTIONS,
      right: RIGHT,
      texts: {
        ask: "Отметьте все фрукты. В игре их называют вслух.",
        right: "Верно, это все фрукты.",
        wrong: "Не совсем: отметьте только фрукты, и все.",
      },
    });
    const box = el("div", "nm-pr-column");
    box.append(title, choice.grid, choice.done);
    area.append(box);
    return {
      async demo(act) {
        await act.wait(900);
        for (const word of RIGHT) await act.click(choice.pick(word));
        await act.click(choice.done);
      },
      destroy() {},
    };
  },
};

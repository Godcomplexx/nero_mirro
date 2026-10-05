// «Фонемная вербальная беглость»: words beginning with a given letter. In the
// game aloud; the practice picks them from a list.

import { el, multiChoice } from "./kit.js";

const OPTIONS = ["мяч", "дом", "мост", "кот", "мыло", "лес"];
const RIGHT = ["мяч", "мост", "мыло"];

export default {
  steps: [
    "На экране появится буква, например «М».",
    "После сигнала называйте вслух как можно больше разных слов на эту букву.",
    "Имена и одно и то же слово в разных формах не считаются.",
  ],
  create(area, opts) {
    const letter = el("strong", "nm-pr-number", "М");
    const choice = multiChoice(opts, {
      options: OPTIONS,
      right: RIGHT,
      texts: {
        ask: "Отметьте слова на букву «М». В игре их называют вслух.",
        right: "Верно, все слова на «М» найдены.",
        wrong: "Не совсем: отметьте только слова на «М», и все.",
      },
    });
    const box = el("div", "nm-pr-column");
    box.append(letter, choice.grid, choice.done);
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

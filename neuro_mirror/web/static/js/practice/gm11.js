// «Серийный счёт вслух»: subtract 7. In the game the answer is said aloud;
// the practice shows the idea with a choice of answers.

import { el, singleChoice } from "./kit.js";

const OPTIONS = ["97", "93", "107", "90"];

export default {
  steps: [
    "На экране будет число и правило, например «вычитайте 7».",
    "Вычтите и после сигнала произнесите ответ вслух.",
    "Затем вычитайте из нового числа — и так несколько шагов подряд.",
  ],
  create(area, opts) {
    const rule = el("p", "nm-pr-caption", "Вычитайте 7");
    const number = el("strong", "nm-pr-number", "100");
    const choice = singleChoice(opts, {
      options: OPTIONS.map((label) => ({ label })),
      right: 1,
      columns: 4,
      texts: {
        ask: "Сколько будет 100 − 7? В игре ответ говорят вслух, здесь — нажмите.",
        right: "Верно: 100 − 7 = 93.",
        wrong: "Не так. Вычтите 7 из 100 ещё раз.",
      },
    });
    const box = el("div", "nm-pr-column");
    box.append(rule, number, choice.grid);
    area.append(box);
    return {
      async demo(act) {
        await act.wait(1000);
        await act.click(choice.buttons[1]);
      },
      destroy() {},
    };
  },
};

// «Быстрое называние изображений»: name the picture. In the game aloud.

import { el, OBJECT, singleChoice } from "./kit.js";

const WORDS = ["кошка", "собака", "лиса", "медведь"];

export default {
  steps: [
    "На экране по очереди появляются картинки.",
    "После сигнала как можно быстрее назовите вслух, что изображено.",
    "Затем появится следующая картинка.",
  ],
  create(area, opts) {
    const image = el("img", "nm-pr-picture nm-pr-picture-large");
    image.src = OBJECT("dog.png");
    image.alt = "Картинка";
    const frame = el("div", "nm-pr-tile nm-pr-frame");
    frame.append(image);
    const choice = singleChoice(opts, {
      options: WORDS.map((label) => ({ label })),
      right: 1,
      texts: {
        ask: "Что на картинке? В игре это говорят вслух, здесь — нажмите.",
        right: "Верно, это собака.",
        wrong: "Не то. Посмотрите на картинку ещё раз.",
      },
    });
    const box = el("div", "nm-pr-column");
    box.append(frame, choice.grid);
    area.append(box);
    return {
      async demo(act) {
        await act.wait(900);
        await act.click(choice.buttons[1]);
      },
      destroy() {},
    };
  },
};

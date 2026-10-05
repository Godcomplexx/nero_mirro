// «Соедини слово и картинку»: one picture, four words.

import { button, el, OBJECT } from "./kit.js";

const WORDS = ["собака", "кошка", "мышь", "лиса"];
const RIGHT = "кошка";

export default {
  steps: [
    "На экране будет картинка и четыре слова под ней.",
    "Посмотрите на картинку и нажмите слово, которое ей подходит.",
    "Сразу после ответа появится следующая картинка.",
  ],
  create(area, { status, solved }) {
    const image = el("img", "nm-pr-picture nm-pr-picture-large");
    image.src = OBJECT("cat.png");
    image.alt = "Картинка для выбора слова";
    const frame = el("div", "nm-pr-tile nm-pr-frame");
    frame.append(image);
    const grid = el("div", "nm-pr-grid nm-pr-grid-2");
    let done = false;
    const options = WORDS.map((word) =>
      button("nm-pr-tile nm-pr-choice", word, (event) => {
        if (done) return;
        const option = event.currentTarget;
        if (word === RIGHT) {
          done = true;
          option.classList.add("is-right");
          status("Верно, это кошка.");
          solved();
        } else {
          option.classList.add("is-wrong");
          status("Не подходит. Посмотрите на картинку ещё раз.");
          setTimeout(() => option.classList.remove("is-wrong"), 900);
        }
      }),
    );
    grid.append(...options);
    const box = el("div", "nm-pr-column");
    box.append(frame, grid);
    area.append(box);
    status("Выберите слово для картинки.");
    return {
      async demo(act) {
        await act.wait(900);
        await act.click(options[WORDS.indexOf(RIGHT)]);
      },
      destroy() {},
    };
  },
};

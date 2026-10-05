// «Парные карточки»: four cards, two pairs. Same card markup as the game, so
// the card back, the turn and the press-in look the same.

import { button, el, picture } from "./kit.js";
import { watchCardFlips } from "../core/game-adjustments.js";

const CARDS = [
  ["apple.png", "Яблоко"],
  ["key.png", "Ключ"],
  ["key.png", "Ключ"],
  ["apple.png", "Яблоко"],
];

export default {
  steps: [
    "Все карточки лежат рубашкой вверх.",
    "Откройте две карточки: если картинки одинаковые, пара найдена и остаётся открытой.",
    "Если разные — карточки закроются. Запоминайте, где что лежит, и найдите все пары.",
  ],
  create(area, { status, solved }) {
    const board = el("div", "gm01-board nm-pr-cards");
    const open = new Set();
    let first = null;
    let locked = false;
    const cards = CARDS.map(([file, name], index) => {
      const card = button("gm01-card", "?", async () => {
        if (locked || open.has(index) || first === index) return;
        card.replaceChildren(picture(file, name));
        if (first === null) {
          first = index;
          status("Откройте вторую карточку.");
          return;
        }
        const other = first;
        first = null;
        if (CARDS[other][1] === name) {
          open.add(index).add(other);
          card.disabled = true;
          cards[other].disabled = true;
          if (open.size === CARDS.length) {
            status("Все пары найдены.");
            solved();
          } else {
            status("Пара найдена! Найдите следующую.");
          }
          return;
        }
        locked = true;
        status("Картинки разные — карточки закроются.");
        setTimeout(() => {
          card.replaceChildren("?");
          cards[other].replaceChildren("?");
          locked = false;
          status("Откройте две карточки.");
        }, 1300);
      });
      return card;
    });
    board.append(...cards);
    area.append(board);
    watchCardFlips(area);
    status("Откройте две карточки.");
    return {
      async demo(act) {
        for (const index of [0, 1]) await act.click(cards[index]);
        await act.wait(1700);
        for (const index of [0, 3, 1, 2]) await act.click(cards[index]);
      },
      destroy() {},
    };
  },
};

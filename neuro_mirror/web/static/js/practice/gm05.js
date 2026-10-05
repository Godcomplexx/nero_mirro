// «Список слов»: three words to remember, then find them among six.

import { button, el } from "./kit.js";

const WORDS = ["дом", "кот", "сад"];
const CHOICES = ["мяч", "кот", "река", "дом", "стол", "сад"];
const STUDY_SECONDS = 4;

export default {
  steps: [
    "На экране на несколько секунд появятся слова — запомните их.",
    "Потом слова исчезнут, и появится список побольше.",
    "Выберите в нём все слова, которые вы видели, и нажмите «Готово».",
  ],
  create(area, { status, solved }) {
    let timer = null;
    let chosen = new Set();
    const box = el("div", "nm-pr-column");
    area.append(box);

    function study(seconds) {
      chosen = new Set();
      const words = el("div", "nm-pr-row");
      for (const word of WORDS) words.append(el("span", "nm-pr-tile", word));
      box.replaceChildren(words);
      let left = seconds;
      status(`Запомните слова: ${left}`);
      timer = setInterval(() => {
        left -= 1;
        if (left > 0) {
          status(`Запомните слова: ${left}`);
          return;
        }
        clearInterval(timer);
        choose();
      }, 1000);
    }

    function choose() {
      status("Выберите слова, которые вы видели.");
      const grid = el("div", "nm-pr-grid nm-pr-grid-3");
      const tiles = CHOICES.map((word) => {
        const tile = button("nm-pr-tile nm-pr-choice", word, () => {
          if (chosen.has(word)) chosen.delete(word);
          else chosen.add(word);
          tile.classList.toggle("is-selected", chosen.has(word));
          tile.setAttribute("aria-pressed", String(chosen.has(word)));
        });
        tile.setAttribute("aria-pressed", "false");
        return tile;
      });
      grid.append(...tiles);
      const done = button("nm-btn nm-btn-primary", "Готово", () => {
        const right = chosen.size === WORDS.length && WORDS.every((word) => chosen.has(word));
        if (right) {
          status("Верно, все слова найдены.");
          done.disabled = true;
          solved();
        } else {
          status("Не совсем. Посмотрите на слова ещё раз.");
          setTimeout(() => study(STUDY_SECONDS), 1500);
        }
      });
      box.replaceChildren(grid, done);
      api.tiles = tiles;
      api.done = done;
    }

    const api = {
      tiles: [],
      done: null,
      async demo(act) {
        await act.wait((STUDY_SECONDS + 0.3) * 1000);
        for (const word of WORDS) await act.click(api.tiles[CHOICES.indexOf(word)]);
        await act.click(api.done);
      },
      destroy() {
        clearInterval(timer);
      },
    };
    study(STUDY_SECONDS);
    return api;
  },
};

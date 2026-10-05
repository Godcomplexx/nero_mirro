// «Собери слово»: pick letters in order to build a word.

import { el, button } from "./kit.js";

const WORD = "КОТ";
const LETTERS = ["Т", "К", "О"];

export default {
  steps: [
    "Буквы слова перемешаны.",
    "Нажимайте на буквы по порядку — они встанут в ячейки слева направо.",
    "Чтобы убрать букву из ячейки, нажмите на неё.",
  ],
  create(area, { status, solved }) {
    let done = false;
    const slots = Array.from({ length: WORD.length }, () => button("nm-pr-tile nm-pr-slot", "", null));
    const bank = LETTERS.map((letter) => {
      const tile = button("nm-pr-tile nm-pr-letter-tile", letter, () => place(tile));
      return tile;
    });
    slots.forEach((slot) => {
      slot.addEventListener("click", () => {
        if (done || !slot.dataset.letter) return;
        const tile = bank.find((item) => item.dataset.used === slot.dataset.index);
        if (tile) {
          tile.hidden = false;
          delete tile.dataset.used;
        }
        slot.textContent = "";
        delete slot.dataset.letter;
      });
    });
    slots.forEach((slot, index) => (slot.dataset.index = String(index)));

    function place(tile) {
      if (done) return;
      const slot = slots.find((item) => !item.dataset.letter);
      if (!slot) return;
      slot.textContent = tile.textContent;
      slot.dataset.letter = tile.textContent;
      tile.dataset.used = slot.dataset.index;
      tile.hidden = true;
      const word = slots.map((item) => item.dataset.letter || "").join("");
      if (word.length < WORD.length) return;
      if (word === WORD) {
        done = true;
        slots.forEach((item) => item.classList.add("is-right"));
        status("Верно, получилось слово «кот».");
        solved();
      } else {
        status("Не то слово. Уберите буквы из ячеек и попробуйте ещё.");
      }
    }

    const row = el("div", "nm-pr-row");
    row.append(...slots);
    const letters = el("div", "nm-pr-row nm-pr-bank");
    letters.append(...bank);
    const box = el("div", "nm-pr-column");
    box.append(row, letters);
    area.append(box);
    status("Соберите слово из букв.");
    return {
      async demo(act) {
        await act.wait(900);
        for (const letter of WORD) await act.click(bank.find((tile) => tile.textContent === letter));
      },
      destroy() {},
    };
  },
};

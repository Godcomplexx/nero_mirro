// «Сортировка по правилу»: the rule (here — by colour) is not told; the
// feedback after each answer shows it. Two cards to sort.

import { el, button } from "./kit.js";

// [colour, shape, count]
const REFERENCES = [
  ["red", "▲", 1],
  ["green", "●", 2],
  ["blue", "■", 3],
];
const CARDS = [
  ["blue", "▲", 2], // → blue
  ["red", "●", 3], // → red
];

// Each figure is its own element, so the group sits exactly in the middle
function cardFace([colour, shape, count]) {
  const face = el("span", `nm-pr-card-face is-${colour}`);
  for (let i = 0; i < count; i += 1) face.append(el("span", null, shape));
  return face;
}

export default {
  steps: [
    "Наверху — карточки-образцы, внизу — карточка, которую нужно к ним отнести.",
    "Правило, по которому сортировать, не говорят: цвет, форма или количество.",
    "После каждого ответа появится «верно» или «неверно» — по ним определите правило.",
  ],
  create(area, { status, solved }) {
    let index = 0;
    let busy = false;
    const sorted = el("div", "nm-pr-tile nm-pr-frame");
    const refs = REFERENCES.map((ref) =>
      button("nm-pr-tile nm-pr-frame nm-pr-choice", cardFace(ref), () => answer(ref, refsButtons[REFERENCES.indexOf(ref)])),
    );
    const refsButtons = refs;
    function showCard() {
      sorted.replaceChildren(cardFace(CARDS[index]));
    }
    function answer(ref, node) {
      if (busy) return;
      const card = CARDS[index];
      if (ref[0] === card[0]) {
        node.classList.add("is-right");
        busy = true;
        setTimeout(() => {
          node.classList.remove("is-right");
          busy = false;
          index += 1;
          if (index === CARDS.length) {
            status("Верно. Правило здесь — по цвету.");
            solved();
          } else {
            showCard();
            status("Верно! Отнесите следующую карточку по тому же правилу.");
          }
        }, 700);
        status("Верно!");
      } else {
        node.classList.add("is-wrong");
        status("Неверно. Правило другое — попробуйте иначе.");
        setTimeout(() => node.classList.remove("is-wrong"), 900);
      }
    }
    const row = el("div", "nm-pr-row");
    row.append(...refs);
    const box = el("div", "nm-pr-column");
    box.append(el("span", "nm-pr-caption", "Образцы"), row, el("span", "nm-pr-caption", "Карточка"), sorted);
    area.append(box);
    showCard();
    status("К какому образцу отнести карточку внизу?");
    return {
      async demo(act) {
        await act.wait(900);
        await act.click(refs[0]);
        await act.wait(500);
        await act.click(refs[2]);
        await act.wait(900);
        await act.click(refs[0]);
      },
      destroy() {},
    };
  },
};

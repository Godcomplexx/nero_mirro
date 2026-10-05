// «Пазлы»: a picture cut into four; two pieces are swapped. Pick two pieces
// to swap them back. The solved picture is shown whole and marked.

import { el, button } from "./kit.js";
import { animateSwap } from "../components/animate-swap.js";

const IMAGE = "/game-assets/differences/park_a.png";
const START = [0, 3, 2, 1]; // piece shown in each place

export default {
  steps: [
    "Картинка разрезана на части, и части перепутаны. Справа — образец.",
    "Нажмите на одну часть, затем на другую — они поменяются местами.",
    "Меняйте части, пока картинка не станет как на образце.",
  ],
  create(area, { status, solved }) {
    let order = [...START];
    let selected = null;
    let done = false;
    let moving = false;
    const board = el("div", "nm-pr-puzzle");
    const pieces = order.map((_, place) => {
      const piece = button("nm-pr-piece", "", () => choose(place));
      piece.setAttribute("aria-label", `Часть ${place + 1}`);
      return piece;
    });
    board.append(...pieces);
    const sample = el("img", "nm-pr-puzzle-sample");
    sample.src = IMAGE;
    sample.alt = "Образец";
    const sampleBox = el("div", "nm-pr-column nm-pr-small-gap");
    sampleBox.append(el("span", "nm-pr-caption", "Образец"), sample);
    const box = el("div", "nm-pr-row nm-pr-gap-large");
    box.append(board, sampleBox);
    area.append(box);

    function draw() {
      pieces.forEach((piece, place) => {
        const part = order[place];
        piece.style.backgroundImage = `url('${IMAGE}')`;
        piece.style.backgroundPosition = `${(part % 2) * 100}% ${Math.floor(part / 2) * 100}%`;
        piece.classList.toggle("is-selected", selected === place);
      });
    }

    async function choose(place) {
      if (done || moving) return;
      if (selected === null) {
        selected = place;
        status("Теперь выберите вторую часть.");
        draw();
        return;
      }
      const first = selected;
      selected = null;
      if (first !== place) {
        // The two pieces glide into each other's place, then swap for real
        moving = true;
        draw();
        const reset = await animateSwap(pieces[first], pieces[place]);
        [order[first], order[place]] = [order[place], order[first]];
        draw();
        reset();
        moving = false;
      } else {
        draw();
      }
      if (order.every((part, index) => part === index)) {
        done = true;
        board.classList.add("is-solved");
        status("✓ Пазл собран верно");
        solved();
      } else {
        status("Поменяйте ещё части, чтобы картинка сложилась.");
      }
    }

    draw();
    status("Выберите часть, которую нужно переставить.");
    return {
      async demo(act) {
        await act.wait(1000);
        await act.click(pieces[1]);
        await act.click(pieces[3]);
      },
      destroy() {},
    };
  },
};

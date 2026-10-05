// «Найди отличие»: two simple pictures side by side, one difference; mark it
// on the right picture only.

import { el, button } from "./kit.js";

function scene(withSun) {
  const box = el("span", "nm-pr-scene");
  box.append(
    el("span", "nm-pr-scene-house"),
    el("span", "nm-pr-scene-roof"),
    el("span", "nm-pr-scene-door"),
    el("span", "nm-pr-scene-tree"),
  );
  if (withSun) box.append(el("span", "nm-pr-scene-sun"));
  return box;
}

export default {
  steps: [
    "Будут две похожие картинки: слева образец, справа — с отличиями.",
    "Сравните их и найдите, что на правой картинке не так.",
    "Нажимайте на отличие только на правой картинке.",
  ],
  create(area, { status, solved }) {
    let done = false;
    const left = el("div", "nm-pr-column nm-pr-small-gap");
    left.append(el("span", "nm-pr-caption", "Образец"), scene(true));
    const right = el("div", "nm-pr-column nm-pr-small-gap");
    const picture = button("nm-pr-scene-button", scene(false), (event) => {
      if (done) return;
      const target = event.target.closest(".nm-pr-scene-spot");
      if (target) {
        done = true;
        target.classList.add("is-found");
        status("Верно: на правой картинке нет солнца.");
        solved();
      } else {
        status("Здесь отличия нет. Сравните ещё раз.");
      }
    });
    picture.setAttribute("aria-label", "Картинка с отличием");
    // Where the sun should be — the difference
    const spot = el("span", "nm-pr-scene-spot");
    picture.firstChild.append(spot);
    right.append(el("span", "nm-pr-caption nm-pr-caption-active", "Ищите здесь"), picture);
    const box = el("div", "nm-pr-row nm-pr-gap-large");
    box.append(left, right);
    area.append(box);
    status("Найдите отличие на правой картинке.");
    return {
      async demo(act) {
        await act.wait(1300);
        await act.click(spot);
      },
      destroy() {},
    };
  },
};

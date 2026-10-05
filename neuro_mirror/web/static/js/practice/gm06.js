// «Ритмическое повторение»: three coloured buttons sound and light in turn;
// repeat the order. Sound only in the practice itself, never in the preview.

import { el, button, sleep, beep } from "./kit.js";

const TONES = [
  ["low", "Низкий звук", 330],
  ["middle", "Средний звук", 440],
  ["high", "Высокий звук", 587],
];
const SEQUENCE = [0, 2, 1];

export default {
  steps: [
    "Три цветные кнопки по очереди прозвучат и подсветятся.",
    "Запомните порядок звуков.",
    "Когда появится «Повторите», нажмите кнопки в том же порядке и ритме.",
  ],
  create(area, { status, solved, demo }) {
    let input = false;
    let alive = true;
    let clicks = [];
    const row = el("div", "nm-pr-row nm-pr-gap-large");
    const pads = TONES.map(([tone, label, frequency], index) => {
      const pad = button(`nm-pr-pad is-${tone}`, "", () => press(index));
      pad.setAttribute("aria-label", label);
      pad.dataset.frequency = String(frequency);
      return pad;
    });
    row.append(...pads);
    area.append(row);

    function light(index) {
      pads[index].classList.add("is-lit");
      if (!demo) beep(TONES[index][2]);
      setTimeout(() => pads[index].classList.remove("is-lit"), 350);
    }

    async function play() {
      input = false;
      clicks = [];
      status("Слушайте и запоминайте…");
      await sleep(700);
      for (const index of SEQUENCE) {
        if (!alive) return;
        light(index);
        await sleep(750);
      }
      if (!alive) return;
      status("Повторите.");
      input = true;
    }

    async function press(index) {
      if (!input) return;
      light(index);
      clicks.push(index);
      if (index !== SEQUENCE[clicks.length - 1]) {
        input = false;
        status("Порядок другой. Послушайте ещё раз.");
        await sleep(1300);
        play();
        return;
      }
      if (clicks.length === SEQUENCE.length) {
        input = false;
        status("Верно, порядок повторён.");
        solved();
      }
    }

    play();
    return {
      async demo(act) {
        while (!input && act.alive()) await act.wait(100);
        for (const index of SEQUENCE) await act.click(pads[index]);
      },
      destroy() {
        alive = false;
      },
    };
  },
};

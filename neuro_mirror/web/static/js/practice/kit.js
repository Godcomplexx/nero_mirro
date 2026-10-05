// neuro_mirror/web/static/js/practice/kit.js
//
// Small helpers shared by the practice rounds (js/practice/gmNN.js).
// A practice round is a fixed example checked right on the screen: nothing is
// sent to the core, so it never counts in the results.
//
// Practice module contract:
//   steps: [string]   — «Как выполнять задание», one line per step
//   create(area, { status, solved }) → { demo(act), destroy() }
//     status(text) — the line of guidance above the example
//     solved()     — the person has done the example correctly
//     demo(act)    — plays the example by itself (the preview on the start
//                    screen); act.click(node) moves the pointer and presses
//                    it, act.wait(ms) pauses, act.alive() says whether the
//                    preview is still on screen

export const OBJECT = (file) => `/game-assets/objects/${file}`;

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function button(className, content, onClick) {
  const node = el("button", className);
  node.type = "button";
  if (typeof content === "string") node.textContent = content;
  else if (content) node.append(content);
  if (onClick) node.addEventListener("click", onClick);
  return node;
}

export function picture(file, label) {
  const wrap = document.createDocumentFragment();
  const image = el("img", "nm-pr-picture");
  image.src = OBJECT(file);
  image.alt = "";
  wrap.append(image);
  if (label) wrap.append(el("small", null, label));
  return wrap;
}

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// The pointer of the preview: an arrow that comes in, moves to a target and
// presses it. While the example is only showing something (cells lighting
// up, a countdown), the pointer is not on screen.
const IDLE_AFTER_MS = 700;

export function createDemoPointer(box) {
  const pointer = el("span", "nm-pr-pointer is-idle");
  pointer.setAttribute("aria-hidden", "true");
  pointer.innerHTML =
    '<svg viewBox="0 0 24 24" width="28" height="28"><path d="M5 2l14 10-6.5 1.2L16 21l-3 1.3-3.4-7.9L5 19z" fill="#0f172a" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></svg>';
  box.append(pointer);
  let alive = true;
  let idleTimer = null;
  const act = {
    alive: () => alive && box.isConnected,
    async wait(ms) {
      await sleep(ms);
    },
    async click(node) {
      if (!act.alive() || !node) return;
      await moveTo(node);
      if (!act.alive()) return;
      pointer.classList.add("is-pressing");
      await sleep(160);
      pointer.classList.remove("is-pressing");
      node.click();
      await sleep(300);
      idleTimer = setTimeout(() => pointer.classList.add("is-idle"), IDLE_AFTER_MS);
    },
    // Press on the first node, move through the others without letting go,
    // release on the last; reached(index) is called on arriving at each node
    async drag(nodes, reached = () => {}) {
      if (!act.alive() || !nodes.length) return;
      await moveTo(nodes[0]);
      if (!act.alive()) return;
      pointer.classList.add("is-pressing", "is-dragging");
      await sleep(200);
      reached(0);
      for (let index = 1; index < nodes.length; index += 1) {
        if (!act.alive()) return;
        place(nodes[index]);
        await sleep(380);
        reached(index);
      }
      await sleep(200);
      pointer.classList.remove("is-pressing", "is-dragging");
      idleTimer = setTimeout(() => pointer.classList.add("is-idle"), IDLE_AFTER_MS);
    },
  };

  // Where a node's centre is, in the box's own pixels (the field and the
  // preview are scaled)
  function centre(node) {
    const outer = box.getBoundingClientRect();
    const zoom = outer.width / box.offsetWidth || 1;
    const rect = node.getBoundingClientRect();
    return [(rect.left + rect.width / 2 - outer.left) / zoom, (rect.top + rect.height / 2 - outer.top) / zoom];
  }

  function place(node) {
    const [x, y] = centre(node);
    pointer.style.transform = `translate(${x}px, ${y}px)`;
  }

  async function moveTo(node) {
    clearTimeout(idleTimer);
    const [x, y] = centre(node);
    if (pointer.classList.contains("is-idle")) {
      // Comes in from a little below and to the right of the target
      pointer.classList.add("is-placing");
      pointer.style.transform = `translate(${x + 40}px, ${y + 50}px)`;
      void pointer.offsetWidth;
      pointer.classList.remove("is-placing", "is-idle");
      await sleep(30);
    }
    pointer.style.transform = `translate(${x}px, ${y}px)`;
    await sleep(600);
  }


  return {
    act,
    stop() {
      alive = false;
      clearTimeout(idleTimer);
      pointer.remove();
    },
  };
}

// One right answer among several (picture or word, then options).
//   options: [{ label, node? }]  right: index of the right option
//   texts: { ask, right, wrong }
// Returns the option buttons (for the preview) and the wrapper.
export function singleChoice({ status, solved }, { options, right, texts, columns = 2, tileClass = "" }) {
  const grid = el("div", `nm-pr-grid nm-pr-grid-${columns}`);
  let done = false;
  const buttons = options.map((option, index) => {
    const node = button(`nm-pr-tile nm-pr-choice ${tileClass}`.trim(), option.node || option.label, () => {
      if (done) return;
      if (index === right) {
        done = true;
        node.classList.add("is-right");
        status(texts.right);
        solved();
      } else {
        node.classList.add("is-wrong");
        status(texts.wrong);
        setTimeout(() => node.classList.remove("is-wrong"), 900);
      }
    });
    if (option.node && option.label) node.setAttribute("aria-label", option.label);
    return node;
  });
  grid.append(...buttons);
  status(texts.ask);
  return { grid, buttons };
}

// Several right answers: tiles are marked, then «Готово».
export function multiChoice({ status, solved }, { options, right, texts, columns = 3 }) {
  const chosen = new Set();
  const grid = el("div", `nm-pr-grid nm-pr-grid-${columns}`);
  const buttons = options.map((label) => {
    const node = button("nm-pr-tile nm-pr-choice", label, () => {
      if (chosen.has(label)) chosen.delete(label);
      else chosen.add(label);
      node.classList.toggle("is-selected", chosen.has(label));
      node.setAttribute("aria-pressed", String(chosen.has(label)));
    });
    node.setAttribute("aria-pressed", "false");
    return node;
  });
  grid.append(...buttons);
  const done = button("nm-btn nm-btn-primary", "Готово", () => {
    const ok = chosen.size === right.length && right.every((label) => chosen.has(label));
    if (ok) {
      done.disabled = true;
      status(texts.right);
      solved();
    } else {
      status(texts.wrong);
    }
  });
  status(texts.ask);
  return { grid, buttons, done, pick: (label) => buttons[options.indexOf(label)] };
}

// Simple beep for the sound games (only in the practice, never in the preview)
let audio = null;
export function beep(frequency, ms = 260) {
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.frequency.value = frequency;
    gain.gain.value = 0.08;
    osc.connect(gain);
    gain.connect(audio.destination);
    osc.start();
    osc.stop(audio.currentTime + ms / 1000);
  } catch (_) {
    // sound is a help, not required
  }
}

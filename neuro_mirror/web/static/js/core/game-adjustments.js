// neuro_mirror/web/static/js/core/game-adjustments.js
//
// Presentation adjustments for particular games. The games themselves (rules,
// scoring and their drawing modules) belong to the core and are not edited;
// what is listed here only changes how a game is shown inside the interface's
// frame. Their styles are in css/screens/game.css. Each entry may have:
//   fit: false           — the game already sizes itself to its field
//   onMounted(container) — once the game has drawn itself
//   beforeReply(reply, previous, container, request) — before an answer of the core is
//                          handed to the game; may wait (returns a promise)
//
// If a game's own module starts doing the same thing, its entry is removed.

import { animateSwap } from "../components/animate-swap.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// «Парные карточки» draws a card by replacing its content ("?" or the
// picture). Watching those replacements, the interface gives closed cards a
// card back and turns a card over when its side changes: the side that was
// there turns away, then the new one turns in.
const FLIP_MS = 480;

function cardContent(card) {
  return [...card.childNodes]
    .filter((node) => !(node.classList && node.classList.contains("nm-card-turn-part")))
    .map((node) => (node.outerHTML !== undefined ? node.outerHTML : node.textContent))
    .join("");
}

function turnPart(className) {
  const part = document.createElement("span");
  part.className = `nm-card-turn-part ${className}`;
  part.setAttribute("aria-hidden", "true");
  return part;
}

function turnCard(card, oldSideHtml, oldSideIsBack) {
  card.querySelectorAll(".nm-card-turn-part").forEach((node) => node.remove());
  const oldSide = turnPart(oldSideIsBack ? "nm-card-old-side nm-card-back-face" : "nm-card-old-side");
  if (!oldSideIsBack) oldSide.innerHTML = oldSideHtml;
  card.append(oldSide);
  card.classList.remove("nm-card-flip");
  void card.offsetWidth; // restart the animation
  card.classList.add("nm-card-flip");
  setTimeout(() => {
    oldSide.remove();
    card.classList.remove("nm-card-flip");
  }, FLIP_MS + 50);
}

export function watchCardFlips(container) {
  let sides = []; // per card: content html when open, "" when closed
  const sync = () => {
    const board = container.querySelector(".gm01-board");
    if (!board) return;
    const cards = [...board.querySelectorAll(".gm01-card")];
    const now = cards.map((card) => (card.querySelector(":scope > img") ? cardContent(card) : ""));
    // A new field (other number of cards) is laid out without turning
    const sameField = sides.length === now.length;
    cards.forEach((card, index) => {
      card.classList.toggle("nm-card-back", !now[index]);
      if (sameField && Boolean(sides[index]) !== Boolean(now[index])) {
        // Opening: the back turns away; closing: the picture turns away
        turnCard(card, sides[index], !sides[index]);
      }
    });
    sides = now;
  };
  // Only the game's own changes of the cards matter, not the turning layers
  new MutationObserver((records) => {
    const own = (record) =>
      [...record.addedNodes, ...record.removedNodes].every(
        (node) => node.classList && node.classList.contains("nm-card-turn-part"),
      );
    if (!records.every(own)) sync();
  }).observe(container, { childList: true, subtree: true });
  sync();
  watchCardPress(container);
}

// Hovering a card presses it in under the pointer: the card tilts so that
// the point under the pointer goes down (styles: --nm-press-x/-y)
function watchCardPress(container) {
  container.addEventListener("pointermove", (event) => {
    const card = event.target.closest && event.target.closest(".gm01-card");
    if (!card || card.disabled) return;
    const rect = card.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    card.style.setProperty("--nm-press-x", x.toFixed(3));
    card.style.setProperty("--nm-press-y", y.toFixed(3));
  });
  container.addEventListener("pointerout", (event) => {
    const card = event.target.closest && event.target.closest(".gm01-card");
    if (!card || card.contains(event.relatedTarget)) return;
    card.style.removeProperty("--nm-press-x");
    card.style.removeProperty("--nm-press-y");
  });
}

const ADJUSTMENTS = {
  // «Запомни последовательность»: the interface has already shown the
  // instruction, example and practice — go straight to the game
  "GM-02": {
    onMounted(container) {
      const start = container.querySelector("[data-confirm-start]");
      if (start) start.click();
    },
  },

  "GM-01": {
    onMounted: watchCardFlips,
    // The second card of a pair stays open for its whole turn before the
    // game closes a wrong pair
    async beforeReply(reply) {
      if (reply && !reply.first_pick) await sleep(FLIP_MS);
    },
  },

  // «Найди отличие»: the two pictures stand side by side (wide field) instead
  // of one above the other, so the instruction names the right picture
  "GM-10": {
    fit: false,
    onMounted(container) {
      const hint = container.querySelector(".game-header-new p:not(.game-kicker-new)");
      if (hint) hint.textContent = hint.textContent.replace("на нижней картинке", "на правой картинке");
    },
  },

  // «Пазлы»: the two chosen pieces glide into each other's place before the
  // game redraws the board; a solved picture then stays on screen for two
  // seconds, marked as correct, before the core's next puzzle is shown
  "GM-18": {
    // The move counter goes beside the sample, so the line above the board
    // only names the puzzle (layout: css/screens/game.css)
    onMounted(container) {
      const moves = container.querySelector("[data-moves]");
      const reference = container.querySelector(".gm18-reference");
      if (moves && reference) reference.prepend(moves);
    },
    async beforeReply(reply, previous, container, request) {
      if (!previous || !previous.image) return;
      const pieces = [...container.querySelectorAll("[data-board] .gm18-piece")];
      // The moved pieces stay where they went: the game replaces the whole
      // board with new pieces right after
      if (request && pieces.length) await animateSwap(pieces[request.first_index], pieces[request.second_index]);
      const solved =
        reply.finished ||
        reply.round_number !== previous.round_number ||
        Boolean(reply.bonus) !== Boolean(previous.bonus);
      const board = container.querySelector("[data-board]");
      if (!solved || !board) return;
      const status = container.querySelector("[data-status]");
      board.style.backgroundImage = `url('/game-assets/differences/${previous.image}')`;
      board.classList.add("nm-puzzle-solved");
      if (status) {
        status.textContent = "✓ Пазл собран верно";
        status.classList.add("nm-puzzle-solved-note");
      }
      await sleep(2000);
      board.classList.remove("nm-puzzle-solved");
      board.style.backgroundImage = "";
      if (status) status.classList.remove("nm-puzzle-solved-note");
    },
  },
};

export function adjustmentsFor(gameCode) {
  return ADJUSTMENTS[String(gameCode).toUpperCase()] || {};
}

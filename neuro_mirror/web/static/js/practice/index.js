// neuro_mirror/web/static/js/practice/index.js
//
// Start of every game made by the interface: instruction, live example and a
// practice round (js/components/game-intro.js). A game whose own screen code
// already brings its own practice (the core's feature/game-difficulty branch
// does that for all games) is shown as it is — see usesInterfacePractice().
// «Запомни последовательность» is the exception: its own start (with a
// recorded animation) is replaced by the interface's one.

import gm01 from "./gm01.js";
import gm02 from "./gm02.js";
import gm03 from "./gm03.js";
import gm04 from "./gm04.js";
import gm05 from "./gm05.js";
import gm06 from "./gm06.js";
import gm07 from "./gm07.js";
import gm08 from "./gm08.js";
import gm09 from "./gm09.js";
import gm10 from "./gm10.js";
import gm11 from "./gm11.js";
import gm12 from "./gm12.js";
import gm13 from "./gm13.js";
import gm14 from "./gm14.js";
import gm15 from "./gm15.js";
import gm16 from "./gm16.js";
import gm17 from "./gm17.js";
import gm18 from "./gm18.js";
import gm19 from "./gm19.js";
import gm20 from "./gm20.js";
import gm21 from "./gm21.js";
import gm22 from "./gm22.js";
import gm23 from "./gm23.js";
import gm24 from "./gm24.js";

const PRACTICES = {
  "GM-01": gm01,
  "GM-02": gm02,
  "GM-03": gm03,
  "GM-04": gm04,
  "GM-05": gm05,
  "GM-06": gm06,
  "GM-07": gm07,
  "GM-08": gm08,
  "GM-09": gm09,
  "GM-10": gm10,
  "GM-11": gm11,
  "GM-12": gm12,
  "GM-13": gm13,
  "GM-14": gm14,
  "GM-15": gm15,
  "GM-16": gm16,
  "GM-17": gm17,
  "GM-18": gm18,
  "GM-19": gm19,
  "GM-20": gm20,
  "GM-21": gm21,
  "GM-22": gm22,
  "GM-23": gm23,
  "GM-24": gm24,
};

// Games whose own start screen is skipped in favour of the interface's one
// (js/core/game-adjustments.js jumps straight to the game)
const REPLACES_OWN_START = new Set(["GM-02"]);

export function practiceFor(gameCode) {
  return PRACTICES[String(gameCode).toUpperCase()] || null;
}

// Whether the interface's start should be shown for this game
export async function usesInterfacePractice(gameCode, rendererUrl) {
  const code = String(gameCode).toUpperCase();
  if (!PRACTICES[code]) return false;
  if (REPLACES_OWN_START.has(code)) return true;
  try {
    const source = await fetch(rendererUrl).then((response) => response.text());
    return !source.includes("data-training");
  } catch (_) {
    return true;
  }
}

// neuro_mirror/web/static/js/components/animate-swap.js
//
// Two elements glide into each other's place (puzzle pieces). Only the
// movement is shown; the caller swaps the actual content afterwards and calls
// the returned reset. Works inside scaled boxes: the distance is measured on
// screen and turned into the elements' own pixels.

export const SWAP_MS = 380;

export async function animateSwap(a, b, ms = SWAP_MS) {
  if (!a || !b || a === b) return () => {};
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return () => {};
  const ra = a.getBoundingClientRect();
  const rb = b.getBoundingClientRect();
  const scale = ra.width / (a.offsetWidth || ra.width) || 1;
  const dx = (rb.left - ra.left) / scale;
  const dy = (rb.top - ra.top) / scale;
  const options = { duration: ms, easing: "ease-in-out", fill: "forwards" };
  const lift = "0 0.75rem 1.5rem rgba(15, 23, 42, 0.3)";
  a.style.position = a.style.position || "relative";
  b.style.position = b.style.position || "relative";
  a.style.zIndex = "3";
  b.style.zIndex = "2";
  const moves = [
    a.animate(
      [
        { transform: "translate(0, 0)", boxShadow: "none" },
        { transform: `translate(${dx / 2}px, ${dy / 2}px) scale(1.04)`, boxShadow: lift, offset: 0.5 },
        { transform: `translate(${dx}px, ${dy}px)`, boxShadow: "none" },
      ],
      options,
    ),
    b.animate(
      [
        { transform: "translate(0, 0)" },
        { transform: `translate(${-dx / 2}px, ${-dy / 2}px) scale(0.97)`, offset: 0.5 },
        { transform: `translate(${-dx}px, ${-dy}px)` },
      ],
      options,
    ),
  ];
  await Promise.all(moves.map((move) => move.finished.catch(() => {})));
  return () => {
    moves.forEach((move) => move.cancel());
    a.style.zIndex = "";
    b.style.zIndex = "";
  };
}

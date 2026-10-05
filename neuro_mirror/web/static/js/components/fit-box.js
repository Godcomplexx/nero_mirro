// neuro_mirror/web/static/js/components/fit-box.js
//
// Scales the content of a fixed-size box to the room the box has: up, so the
// content uses the space instead of sitting small in the middle, and down, so
// a scrollbar never appears. CSS `zoom` is used, so clicks and dragging
// inside keep working. Made for the training games: their field is drawn by
// the core's modules in fixed sizes, while the room for it depends on the
// window.
//
// `host` is watched for changes; the box is looked up by `selector` on every
// pass because a game may redraw it. Returns a function that stops watching.

const MIN_ZOOM = 0.6; // below this the content is too small — scrolling is kept
const MAX_ZOOM = 1.8;
const FILL = 0.9; // share of the box height the content is grown to
const STEADY = 0.08; // smaller changes of the content do not move the scale

// options.maxZoom(box) may return a lower limit of growth for the box's
// current content (undefined keeps the default)
export function fitToBox(host, selector, { maxZoom = () => undefined } = {}) {
  let frame = 0;

  const overflow = (box) =>
    Math.min(box.clientHeight / box.scrollHeight, box.clientWidth / box.scrollWidth);

  // Height the visible content takes on screen at the current scale
  function contentHeight(box) {
    let top = Infinity;
    let bottom = -Infinity;
    for (const child of box.children) {
      const rect = child.getBoundingClientRect();
      if (rect.height === 0) continue;
      top = Math.min(top, rect.top);
      bottom = Math.max(bottom, rect.bottom);
    }
    return bottom > top ? bottom - top : 0;
  }

  // Runs inside one animation frame, so no intermediate state is painted
  function fit() {
    frame = 0;
    const box = host.querySelector(selector);
    if (!box || box.clientHeight === 0) return;
    const current = Number(box.style.zoom) || 1;
    const style = getComputedStyle(box);
    const room =
      box.getBoundingClientRect().height -
      (parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)) * current;
    const height = contentHeight(box);
    if (!height || room <= 0) return;

    const fits = overflow(box) >= 0.999;
    // Air around the content is left only when growing; content that has to
    // shrink keeps every pixel it can get
    const exact = room / height;
    const ratio = exact > 1 ? Math.max(1, exact * FILL) : exact;
    // Small changes (a line of feedback, a counter) keep the scale steady
    if (fits && Math.abs(ratio - 1) < STEADY && current <= (maxZoom(box) || MAX_ZOOM)) return;

    const limit = maxZoom(box) || MAX_ZOOM;
    let zoom = Math.min(limit, Math.max(MIN_ZOOM, current * ratio));
    zoom = Math.floor(zoom * 100) / 100;
    box.style.zoom = String(zoom);
    // Wider content may not fit by width, or text may wrap differently at the
    // new scale — step down until nothing overflows
    for (let pass = 0; pass < 5 && zoom > MIN_ZOOM; pass += 1) {
      const fit = overflow(box);
      if (fit >= 0.999) break;
      zoom = Math.max(MIN_ZOOM, Math.floor(zoom * fit * 100) / 100);
      box.style.zoom = String(zoom);
    }
  }

  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(fit);
  };
  const mutations = new MutationObserver((records) => {
    // Our own change of the box's zoom must not start another pass
    const own = (record) =>
      record.type === "attributes" && record.attributeName === "style" && record.target.matches(selector);
    if (!records.every(own)) schedule();
  });
  mutations.observe(host, { subtree: true, childList: true, attributes: true, characterData: true });
  const resizes = new ResizeObserver(schedule);
  resizes.observe(host);
  // Pictures change the size of the content when they arrive
  host.addEventListener("load", schedule, true);
  schedule();

  return () => {
    if (frame) cancelAnimationFrame(frame);
    mutations.disconnect();
    resizes.disconnect();
    host.removeEventListener("load", schedule, true);
  };
}

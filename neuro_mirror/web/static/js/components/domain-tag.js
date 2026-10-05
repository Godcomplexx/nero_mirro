// neuro_mirror/web/static/js/components/domain-tag.js
//
// Cognitive-domain label with the deck's color coding (Память — красный,
// Внимание — синий, Абстракция — зелёный, Речь — жёлтый). The domain name
// itself comes from the server; the color is presentation and always sits
// next to the text, never alone. Styles: css/components/domain.css.

const TONES = [
  ["памят", "memory"],
  ["вниман", "attention"],
  ["абстрак", "abstraction"],
  ["реч", "speech"],
];

export function domainTone(name) {
  const lower = String(name || "").toLowerCase();
  const match = TONES.find(([prefix]) => lower.startsWith(prefix));
  return match ? match[1] : "other";
}

export function createDomainTag(name) {
  const tag = document.createElement("span");
  tag.className = "nm-domain";
  tag.dataset.tone = domainTone(name);
  const dot = document.createElement("span");
  dot.className = "nm-domain-dot";
  dot.setAttribute("aria-hidden", "true");
  tag.append(dot, document.createTextNode(name));
  return tag;
}

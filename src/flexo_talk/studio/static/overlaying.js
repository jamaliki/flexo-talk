// Overlaying slides (across.js): which of a deck's slides are drawn over the one shown, in what
// tint each, and where Page Up and Page Down go among them -- the sums alone, read in Node as in
// the studio.
//
// - The slides chosen in the list (two or more): those, the one shown solid among them -- a set
//   that stays as it is while the slides shown are among it.
// - One chosen: the presented slides either side of the one shown (a skipped slide passed over),
//   following the slide shown as it changes.
// - Each overlaid slide but the one shown is a ghost. Four or fewer: those before it in a cool
//   blue and those after it in a warm red, as an animator's onion skin, each fainter the further
//   it is from the one shown. More: a hue of its own each, kept by its place in the set (so a
//   slide keeps its hue as the slides are gone through), all equally faint. Each tint has a
//   lighter one for a dark slide, drawn over it as light ink is.
// - The setting kept for the person ("on": the slides either side overlaid as a deck opens, or
//   "off"), in this browser -- carried over from Show Neighbouring Slides, which it replaces.

export const KEY = "flexo-studio-overlay";
const OLD = "flexo-studio-neighbours";

// Before the slide shown, and after it: [the tint, the lighter one for a dark slide].
export const BEFORE = ["#2f63d6", "#8fb3ff"];
export const AFTER = ["#d8452b", "#ff9d86"];
// More than four ghosts: a hue each, neighbours far apart round the wheel.
export const HUES = [
  ["#7b3fd6", "#c3a2ff"], ["#1f8fd8", "#8fd0ff"], ["#1fa35b", "#86e3ae"], ["#d8452b", "#ff9d86"],
  ["#c98a00", "#ffd36e"], ["#d6338a", "#ff9fd0"], ["#0f9c9c", "#7fe3e0"], ["#4c5fd6", "#a8b4ff"],
];
export const MOST = 4;  // ghosts tinted by their side; more, a hue each
const NEAREST = 0.55, FADING = 0.62, MANY = 0.36;

// -- the setting --

// "on" or "off", as kept -- Show Neighbouring Slides' "before" or "both" read as on, once, and
// kept so.
export function keptOverlay(storage = globalThis.localStorage) {
  try {
    const now = storage?.getItem?.(KEY);
    if (now === "on" || now === "off") return now;
    const old = storage?.getItem?.(OLD);
    if (old === null || old === undefined) return "off";
    const value = old === "before" || old === "both" ? "on" : "off";
    storage.setItem(KEY, value);
    storage.removeItem?.(OLD);
    return value;
  } catch { return "off"; }
}
export function keepOverlay(value, storage = globalThis.localStorage) {
  try { storage?.setItem?.(KEY, value === "on" ? "on" : "off"); } catch { /* this window's alone */ }
}

// -- which slides --

// The presented slide before (`way` -1) or after (1) `here` among `slides`, or null.
export function presented(slides, here, way) {
  for (let at = here + way; at >= 0 && at < slides.length; at += way) if (slides[at]?.skip !== true) return at;
  return null;
}

// Two or more slides chosen, as a set of their own (sorted, once each, on the deck); else null.
export function setOf(chosen, count) {
  const set = [...new Set((chosen || []).filter((index) => Number.isInteger(index) && index >= 0 && index < count))].sort((a, b) => a - b);
  return set.length > 1 ? set : null;
}

// The slides overlaid now, in the deck's order, `here` among them: the set (`chosen`), or the
// presented slides either side of `here`. A set that no longer has `here` in it, or has fewer
// than two slides left on the deck, is none (null): the overlay stops.
export function overlaidOf(slides, here, chosen = null) {
  if (chosen) {
    const set = setOf(chosen, slides.length);
    return set && set.includes(here) ? set : null;
  }
  return [presented(slides, here, -1), here, presented(slides, here, 1)].filter((index) => index !== null);
}

// Where Page Up (`way` -1) and Page Down (1) go among `overlaid` from `here`: the overlaid slide
// before or after it, or null at either end.
export function stepAmong(overlaid, here, way) {
  const sorted = [...overlaid].sort((a, b) => a - b);
  return (way > 0 ? sorted.find((index) => index > here) : sorted.reverse().find((index) => index < here)) ?? null;
}

// -- tints --

// Each ghost's tint: Map index -> { colour, light, opacity, side ("before" or "after"), away
// (how many overlaid slides from the one shown) }.
export function tintsOf(overlaid, here) {
  const sorted = [...overlaid].sort((a, b) => a - b), at = sorted.indexOf(here);
  const ghosts = sorted.filter((index) => index !== here), out = new Map();
  const many = ghosts.length > MOST;
  sorted.forEach((index, n) => {
    if (index === here) return;
    const side = index < here ? "before" : "after";
    const away = at < 0 ? Math.abs(n) + 1 : Math.abs(n - at);
    const [colour, light] = many ? HUES[n % HUES.length] : side === "before" ? BEFORE : AFTER;
    out.set(index, { colour, light, side, away, opacity: many ? MANY : Math.round(NEAREST * FADING ** (away - 1) * 1000) / 1000 });
  });
  return out;
}

// How light a colour is (#rrggbb, or rgb(...)): its luminance, 0 to 1 (none said: 1, light).
export function lightness(colour) {
  const found = /#([0-9a-f]{6})/i.exec(String(colour || ""));
  const rgb = found ? [0, 2, 4].map((at) => parseInt(found[1].slice(at, at + 2), 16) / 255) : (/rgba?\(([^)]+)\)/.exec(String(colour || ""))?.[1].split(",").slice(0, 3).map((value) => Number(value) / 255));
  return rgb && rgb.length >= 3 && rgb.every(Number.isFinite) ? 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] : 1;
}
export const isDark = (colour) => lightness(colour) < 0.45;

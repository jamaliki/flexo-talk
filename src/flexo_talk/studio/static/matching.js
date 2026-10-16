// Match on Other Slides (across.js): what on another slide is the same object as one chosen on
// this one, which slides it is matched on, and how it is put where this one is -- the sums
// alone, read in Node as in the studio.
//
// The same object, on another slide, is the first of these it has:
// - a picture: one of the same file;
// - a figure: the same figure -- the deck's own by name ('#pipeline'), the same figure file, or
//   one written with the same id (`figure: {id: ...}`);
// - a shape (a group too): one with the same id -- or, where it has none, one of the same kind
//   at the same place in the slide's list of shapes;
// - else the object at the same place -- the same region, the same place in it -- of the same
//   kind (a picture for a picture, words for words).
// A slide with none of them is passed over, and said why.
//
// Put where this one is: an object stands where this one stands, as wide (its `at` and `width`,
// as a placed object's are: places.js) -- this one's own `at` and `width` if it is placed, else
// its frame as the slide drew it. A figure is put in this one's frame too (`frame`: drawn as one
// with it, at its scale -- flexo_talk.framing), a frame made and named for it if it has none,
// and this one, if in line, placed where it stands so that both are drawn the same size. A shape
// takes this one's place and size: a box its `at`, `size` and turn, a line its ends, any other
// (points, a path, a group) its outline moved and stretched to this one's bounds.

import * as P from "./places.js";

// The kinds of objects a deck's block may be, by their key, as the editor knows them.
export const KINDS = ["bullets", "text", "figure", "image", "plot", "table", "gallery", "code", "quote", "stats", "callout", "math", "mechanism"];
export const kindOf = (block) => (typeof block === "string" ? "text" : KINDS.find((key) => block && key in block) || "unknown");
const WORDS = new Set(["bullets", "text", "quote", "callout", "code", "stats", "math"]);
// Kinds alike enough to be one another's match at the same place: words with words.
const alike = (a, b) => a === b || (WORDS.has(a) && WORDS.has(b));

// A figure block's figure, as it is known on other slides: by name, by file, by id.
export function figureOf(block, figures = {}) {
  const value = block?.figure;
  if (typeof value === "string" && value.startsWith("#")) {
    const shared = figures?.[value.slice(1)];
    return { name: value.slice(1), file: null, id: shared?.figure?.id ?? null };
  }
  if (typeof value === "string") return { name: null, file: value, id: null };
  if (value && typeof value === "object") return { name: null, file: null, id: value.figure?.id ?? null };
  return { name: null, file: null, id: null };
}
const sameFigure = (a, b) => Boolean((a.name && a.name === b.name) || (a.file && a.file === b.file) || (a.id && a.id === b.id));

// Every object of `slide`, as `{ region, index, block }`, in its regions' order.
export function placesOf(slide, regions, blocksAt) {
  return regions(slide).flatMap((region) => blocksAt(slide, region).map((block, index) => ({ region, index, block })));
}

// What of `slide` matches the object `source` (a block) at `at` ({ region, index }) on its
// own slide: `{ region, index }`, or `{ why }` -- what it has none of.
export function matchObject(source, at, slide, { regions, blocksAt, figures = {} }) {
  const kind = kindOf(source);
  const all = placesOf(slide, regions, blocksAt);
  const there = (found) => ({ region: found.region, index: found.index });
  // (Of several, the one at the same place first.)
  const first = (found) => found.find((one) => one.region === at.region && one.index === at.index) || found[0];
  if (kind === "image") {
    const same = all.filter((one) => kindOf(one.block) === "image" && one.block.image === source.image);
    if (same.length) return there(first(same));
  }
  if (kind === "figure") {
    const own = figureOf(source, figures);
    const same = all.filter((one) => kindOf(one.block) === "figure" && sameFigure(own, figureOf(one.block, figures)));
    if (same.length) return there(first(same));
  }
  const placed = all.find((one) => one.region === at.region && one.index === at.index);
  if (placed && alike(kindOf(placed.block), kind)) return there(placed);
  const what = { image: "such picture, nor one in its place", figure: "such figure, nor one in its place" }[kind] || "object like this one in its place";
  return { why: `no ${what}` };
}

// What of `shapes` (another slide's) matches the shape `source` at `index` on its own slide:
// `{ index }`, or `{ why }`.
export function matchShape(source, index, shapes = []) {
  if (source?.id !== undefined && source.id !== null && source.id !== "") {
    const found = shapes.findIndex((spec) => spec?.id === source.id);
    return found >= 0 ? { index: found } : { why: `no shape “${source.id}”` };
  }
  const there = shapes[index];
  if (there && there.kind === source?.kind && (there.id === undefined || there.id === null || there.id === "")) return { index };
  return { why: "no shape like this one in its place" };
}

// The slides either side of `index` that each have a match (`has(slide index)`), up to the first
// that has none: the run it is in, as [first, last].
export function runOf(count, index, has) {
  let first = index, last = index;
  while (first - 1 >= 0 && has(first - 1)) first -= 1;
  while (last + 1 < count && has(last + 1)) last += 1;
  return [first, last];
}

// Slides said as a person says them: "Slide 4", "Slides 4–7", "Slides 2, 5 and 9".
export function slidesSaid(indices) {
  const numbers = [...new Set(indices)].sort((a, b) => a - b).map((index) => index + 1);
  if (!numbers.length) return "no slides";
  if (numbers.length === 1) return `Slide ${numbers[0]}`;
  const together = numbers.every((number, n) => n === 0 || number === numbers[n - 1] + 1);
  if (together) return `Slides ${numbers[0]}–${numbers[numbers.length - 1]}`;
  return `Slides ${numbers.slice(0, -1).join(", ")} and ${numbers[numbers.length - 1]}`;
}

// A name for a new frame for a figure: its own name, file or id, made one no other frame of the
// deck has (`taken`).
export function frameName(block, figures = {}, taken = []) {
  const own = figureOf(block, figures);
  const stem = own.name || (own.file ? own.file.split("/").pop().replace(/\.[^.]+$/, "") : null) || own.id || "figure";
  const base = String(stem).trim().replace(/\s+/g, "-") || "figure";
  const used = new Set(taken);
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

// The object `target` (of `kind`) put where `frame` says -- [x, y, width, height], in the slide's
// shapes' units -- as wide: placed there, its frame `name` if it is a figure. Just where the one
// matched stands, to a ten-thousandth of a point (places.js rounds a place taken out of line to
// a hundredth: two objects matched would then be drawn a hair apart), a plot in its proportions.
const exact = (value) => Math.round(Number(value) * 10000) / 10000;
export function placedAs(target, frame, kind, { name = null } = {}) {
  target.at = [exact(frame[0]), exact(frame[1])];
  target.width = exact(frame[2]);
  if (kind === "plot" && !target.aspect && frame[3] > 0) target.aspect = Math.round((frame[2] / frame[3]) * 1000) / 1000;
  delete target.placeholder;
  if (kind === "figure" && name) target.frame = name;
  return target;
}

// Where an object stands, as Match copies it: its own `at` and `width` if it is placed (its
// drawn height beside them), else its frame as drawn.
export function standing(block, drawn) {
  if (P.placed(block) && block.width != null) return [Number(block.at[0]), Number(block.at[1]), Number(block.width), drawn ? drawn[3] : 0];
  return drawn;
}

const BOX_KEYS = ["at", "size", "rotate", "flip"];

// The shape `target` given `source`'s place and size: a box -- both of the same kind, or both a
// box -- its `at`, `size`, turn and flip; a line its ends; a box of words its `at` and width;
// anything else its outline mapped onto `source`'s bounds (`bounds(spec)`, [left, top, right,
// bottom]; `mapped(spec, map)`, freeform.js's).
export function shapeAs(target, source, { bounds, mapped, family }) {
  const made = structuredClone(target);
  const form = family(source.kind), own = family(target.kind);
  if (source.kind === "text" && target.kind === "text") {
    made.at = [...source.at];
    if (source.width != null) made.width = source.width; else delete made.width;
    for (const key of ["rotate", "flip"]) if (source[key] !== undefined) made[key] = source[key]; else delete made[key];
    return made;
  }
  if (form === "box" && own === "box" && Array.isArray(source.at) && Array.isArray(source.size)) {
    for (const key of BOX_KEYS) if (source[key] !== undefined) made[key] = structuredClone(source[key]); else delete made[key];
    return made;
  }
  if (form === "line" && own === "line") {
    made.from = structuredClone(source.from);
    made.to = structuredClone(source.to);
    return made;
  }
  const from = bounds(target), to = bounds(source);
  if (!from || !to) return made;
  const sx = (to[2] - to[0]) / ((from[2] - from[0]) || 1), sy = (to[3] - to[1]) / ((from[3] - from[1]) || 1);
  const round = (value) => Math.round(value * 100) / 100;
  return mapped(made, ([x, y]) => [round(to[0] + (x - from[0]) * sx), round(to[1] + (y - from[1]) * sy)]);
}

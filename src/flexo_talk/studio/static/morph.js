// Morph: Keynote's Magic Move, PowerPoint's Morph. A slide that says `transition: morph` arrives
// from the slide shown before it by moving what the two share into place: each thing they share
// slides and grows from where it was to where it is, what only the slide before had fades out by
// the first quarter of the time, and what only this one has fades in over the last quarter (fixed
// windows: a diagram's many new pieces fade as one). Halfway, what has moved is stacked as this
// slide stacks it. Words are set from where their ink starts and grow by their type's size, never
// by their box's: a title whose box widened does not stretch. Two equations that differ move
// glyph by glyph -- each symbol they share to its new place, what is new fading in over the second
// half, what is gone fading out by four tenths -- and the parts of a figure each go to the part
// with their id (a frame's figures share theirs: flexo_talk.framing).
//
// What is shared is found as flexo_talk.morphing finds it for a PowerPoint (`paired` is its
// `paired`), each step among what the steps before left: the same `morph:` name; the same frame;
// the same thing (a picture, a figure, a shape's id, the same words; a title, a number, a logo);
// an object of the same kind in the same place of the layout, where the other was. Nothing is
// paired for looking alike.
//
// Played only going forward, from the last build of a slide to the first of the next one shown:
// going back, or jumping, the slide is simply shown; and not at all where the system asks for
// less motion. The slide settled is the slide as drawn: every animation leaves it as it is.
//
// The ideas, and the glyph matching (`matchGlyphs`), are adapted from DeckWerk
// (src/shared/morph.ts, src/renderer/player/morphTransform.ts and player.ts, equationMorph.ts,
// src/shared/glyphMatch.ts), MIT licence, Copyright (c) 2026 Vincent Sitzmann.

import { ownResources } from "/static/studio/drawings.js";
import { showStep } from "/static/kinds/deck/stepping.js";
import { DURATION, centre, matchGlyphs, owned, paired, transitionOf } from "/static/kinds/deck/morphpairs.js";

export { DURATION, LONGEST, SHORTEST, matchGlyphs, paired, transitionOf, transitionWritten } from "/static/kinds/deck/morphpairs.js";

const EASE = "cubic-bezier(.45,.05,.55,.95)";
const OUT = 0.25;
const IN = 0.75;
const GLYPHS_OUT = 0.4;
const GLYPHS_IN = 0.5;
const SVG = "http://www.w3.org/2000/svg";

// -- what a drawing has (the DOM) --

const CONTAINERS = new Set(["region", "placed", "shapes"]);
const REGION = /^(body|left|right|column\d+)\.(\d+)$/;
const SHAPE = /^shapes\.\d+$/;
const OWN = /^(?:presented-)?slide\d+\.(.+)$/;
const TEXTY = new Set(["text", "bullets", "quote", "callout", "code", "table", "stats", "math"]);
const UNDRAWN = new Set(["defs", "style", "title", "desc", "metadata", "clipPath", "mask", "marker", "linearGradient", "radialGradient", "pattern", "filter", "symbol"]);
// (Not its fonts: the slide arrived at has the deck's own.)
const RESOURCES = "marker, linearGradient, radialGradient, clipPath, mask, pattern, filter, symbol";
const INHERITED = ["fill", "stroke", "stroke-width", "font-family", "font-size", "font-weight", "font-style", "text-anchor"];
const ALIGN = { start: 0, middle: 0.5, end: 1 };

const shownNow = (el) => { const look = getComputedStyle(el); return look.display !== "none" && look.visibility !== "hidden"; };

// Where on the slide each point of `el`'s own drawing is: its matrix into the slide's units.
const slideMatrix = (el, toSlide) => toSlide.multiply(DOMMatrix.fromMatrix(el.getScreenCTM()));

function boxOf(el, toSlide) {
  let box;
  try { box = el.getBBox(); } catch { return null; }
  if (!(box.width > 0 || box.height > 0)) return null;
  const matrix = slideMatrix(el, toSlide);
  const corners = [[box.x, box.y], [box.x + box.width, box.y], [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]]
    .map(([x, y]) => new DOMPoint(x, y).matrixTransform(matrix));
  const xs = corners.map((point) => point.x), ys = corners.map((point) => point.y);
  const x = Math.min(...xs), y = Math.min(...ys);
  const found = [x, y, Math.max(...xs) - x, Math.max(...ys) - y];
  return found.every(Number.isFinite) ? found : null;
}

// The layers of a slide's drawing a morph moves things in: its page, and its slide as presented.
function layersOf(svg) {
  const kids = [...svg.children].filter((el) => el.localName === "g");
  let content = kids.filter((el) => el.id.endsWith(".content") && shownNow(el));
  const presented = [...svg.querySelectorAll("[data-flexo-presented]")].filter(shownNow);
  if (presented.length) content = presented;
  return [...kids.filter((el) => el.id === "layer.background"), ...content];
}

function* walk(parent) {
  for (const child of parent.children) {
    if (UNDRAWN.has(child.localName) || !shownNow(child)) continue;
    const found = OWN.exec(child.id || ""), key = found ? found[1] : child.id || "";
    if (CONTAINERS.has(child.getAttribute("data-flexo-talk")) && !SHAPE.test(key)) yield* walk(child);
    else if (key) yield [child, key];
    else if (child.localName === "g") yield* walk(child);
  }
}

// What a morph moves whole on a drawing's slide, in the order it is drawn, each measured.
function unitsOf(svg, toSlide) {
  const units = [];
  for (const layer of layersOf(svg)) {
    for (const [el, key] of walk(layer)) {
      const box = boxOf(el, toSlide);
      if (!box) continue;
      const region = REGION.exec(key)?.[1] || (SHAPE.test(key) ? "shapes" : "");
      const talk = el.getAttribute("data-flexo-talk") || "";
      const kind = region === "shapes" ? `shape:${el.getAttribute("data-flexo-shape") || ""}` : talk || el.localName;
      const unit = { el, key, kind, box, region, morph: el.getAttribute("data-flexo-morph") || "", framed: el.getAttribute("data-flexo-framed") || "",
        same: el.getAttribute("data-flexo-same") || "", owner: "", texty: TEXTY.has(kind) };
      // A title, a number, a footer, a logo, the page: the same on every slide it is on.
      if (!region && !unit.same) unit.same = `furniture:${key}`;
      units.push(unit);
    }
  }
  owned(units);
  return units;
}

// What a unit is made of that moves apart: a figure's parts, a list's items, an equation's glyphs.
function piecesOf(unit) {
  const el = unit.el, prefix = `${el.id}.`;
  if (unit.kind === "figure") {
    const found = [];
    const visit = (parent) => {
      for (const child of parent.children) {
        if (UNDRAWN.has(child.localName) || !shownNow(child)) continue;
        if (!child.id) { if (child.localName === "g") visit(child); continue; }
        // A group's own pieces (its box, its name) apart from its members, each apart.
        if (child.querySelector("[data-flexo-entity]")) { visit(child); continue; }
        const key = (child.id.startsWith(prefix) ? child.id.slice(prefix.length) : child.id).replace(/^edge\.\d+\./, "edge.");
        found.push({ el: child, key, same: key });
      }
    };
    visit(el);
    // (A part drawn twice -- two lines between the same shapes -- the second its own.)
    const seen = new Map();
    for (const piece of found) { const n = (seen.get(piece.same) || 0) + 1; seen.set(piece.same, n); if (n > 1) piece.same += `#${n}`; }
    return found;
  }
  if (unit.kind === "bullets") {
    return [...el.children].filter((child) => child.id && shownNow(child)).map((child) => {
      const key = child.id.startsWith(prefix) ? child.id.slice(prefix.length) : child.id;
      const mark = /\.mark$/.test(key);
      return { el: child, key, owner: mark ? key.replace(/\.mark$/, "") : "", words: mark ? "" : words(child) };
    });
  }
  if (unit.kind === "math") {
    return [...el.querySelectorAll("[data-g]")].filter(shownNow).map((child) => ({ el: child, key: child.getAttribute("data-g") }));
  }
  return null;
}
const LIST_TIERS = [["words", (piece) => (piece.words ? `w:${piece.words}` : "")], ["index", (piece) => piece.key]];
const PART_TIERS = [["same", (piece) => piece.same]];

// A unit measured as it is drawn: its box, its matrix and its parent's, its type's size, how it
// stands, and what is painted around it -- all that is needed of it once its drawing is gone.
function measured(unit, toSlide, inherited) {
  const el = unit.el;
  unit.matrix = slideMatrix(el, toSlide);
  unit.parentMatrix = el.parentNode?.getScreenCTM ? slideMatrix(el.parentNode, toSlide) : new DOMMatrix();
  unit.opacity = Number(getComputedStyle(el).opacity);
  unit.inherited = inherited(el.parentNode);
  if (unit.texty || el.localName === "text") {
    const text = el.localName === "text" ? el : el.querySelector("text");
    const scale = Math.sqrt(Math.abs(unit.matrix.a * unit.matrix.d - unit.matrix.b * unit.matrix.c));
    if (unit.kind === "math") {
      unit.size = Number(el.getAttribute("data-flexo-size")) * scale || 0;
      unit.align = el.getAttribute("data-flexo-align") || "middle";
    } else if (text) {
      const own = slideMatrix(text, toSlide);
      unit.size = parseFloat(getComputedStyle(text).fontSize) * Math.sqrt(Math.abs(own.a * own.d - own.b * own.c)) || 0;
      unit.align = text.getAttribute("text-anchor") || getComputedStyle(text).textAnchor || "start";
    }
    unit.texty = true;
  }
  return unit;
}

// A slide's drawing measured, as it is shown, for a morph from it: taken before it goes.
export function measure(svg) {
  const screen = svg?.getScreenCTM?.();
  if (!screen) return null;
  const toSlide = DOMMatrix.fromMatrix(screen).inverse();
  const looks = new Map();
  const inherited = (parent) => {
    if (!parent || parent.nodeType !== 1) return {};
    if (!looks.has(parent)) {
      const look = getComputedStyle(parent);
      looks.set(parent, Object.fromEntries(INHERITED.map((name) => [name, look.getPropertyValue(name)]).filter(([, value]) => value)));
    }
    return looks.get(parent);
  };
  const units = unitsOf(svg, toSlide).map((unit) => measured(unit, toSlide, inherited));
  for (const unit of units) unit.pieces = piecesMeasured(unit, toSlide, inherited);
  return { svg, units };
}

// -- playing --

const words = (el) => (el.textContent || "").replace(/\s+/g, " ").trim();
const PAINTS = ["fill", "stroke", "stroke-width", "opacity", "fill-opacity", "stroke-opacity", "font-family", "font-weight", "font-style",
  "visibility", "href", "stroke-dasharray", "data-flexo-show"];
// What a unit looks like, where it is aside: its pieces, their paint, their words.
function lookOf(el, most = 3000) {
  let said = "", count = 0;
  const visit = (node) => {
    if (node.nodeType === 3) { said += node.nodeValue.trim(); return; }
    if (node.nodeType !== 1 || ++count > most) return;
    said += `<${node.localName}`;
    for (const name of PAINTS) { const value = node.getAttribute(name); if (value !== null) said += ` ${name}=${value}`; }
    for (const child of node.childNodes) visit(child);
  };
  visit(el);
  return said;
}

const ratio = (a, b) => (b > 0.01 && a > 0.01 ? a / b : 1);

// The move that draws `now` where `old` was, in the slide's units: `now`'s point `to` drawn at
// `old`'s point `from`, turned by `angle` (degrees) and grown by `sx`, `sy` about it. Words go
// from the corner they are set from, grown by their type's size; a line from its middle, turned
// to its old slope; a shape turned on the slide by its turn; anything else box onto box.
function moveOf(old, now) {
  const [ox, oy, ow, oh] = old.box, [nx, ny, nw, nh] = now.box;
  if (old.texty && now.texty && old.size > 0 && now.size > 0) {
    const scale = old.size / now.size, ax = ALIGN[now.align] ?? 0;
    return { from: [ox + ax * ow, oy], to: [nx + ax * nw, ny], angle: 0, sx: scale, sy: scale };
  }
  const a = endsOf(old), b = endsOf(now);
  if (a && b) {
    const [la, lb] = [Math.hypot(a[2] - a[0], a[3] - a[1]), Math.hypot(b[2] - b[0], b[3] - b[1])];
    const turn = (Math.atan2(a[3] - a[1], a[2] - a[0]) - Math.atan2(b[3] - b[1], b[2] - b[0])) * 180 / Math.PI;
    const scale = ratio(la, lb);
    return { from: [(a[0] + a[2]) / 2, (a[1] + a[3]) / 2], to: [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2],
      angle: ((turn + 540) % 360) - 180, sx: scale, sy: scale };
  }
  const turned = [old, now].map((unit) => Number(unit.el.getAttribute("data-flexo-turn")) || 0);
  const sized = [old, now].map((unit) => unit.el.getAttribute("data-flexo-box")?.split(/\s+/).map(Number));
  if ((turned[0] || turned[1]) && sized.every((box) => box?.length === 4 && box.every(Number.isFinite))) {
    return { from: [ox + ow / 2, oy + oh / 2], to: [nx + nw / 2, ny + nh / 2], angle: turned[0] - turned[1],
      sx: ratio(sized[0][2], sized[1][2]), sy: ratio(sized[0][3], sized[1][3]) };
  }
  return { from: [ox + ow / 2, oy + oh / 2], to: [nx + nw / 2, ny + nh / 2], angle: 0, sx: ratio(ow, nw), sy: ratio(oh, nh) };
}

// A line's ends on the slide (a shape's arrow, line or connector), or null.
function endsOf(unit) {
  const ends = unit.el.getAttribute?.("data-flexo-ends")?.split(/\s+/).map(Number);
  if (ends?.length !== 4 || !ends.every(Number.isFinite) || !unit.parentMatrix) return null;
  const a = new DOMPoint(ends[0], ends[1]).matrixTransform(unit.parentMatrix), b = new DOMPoint(ends[2], ends[3]).matrixTransform(unit.parentMatrix);
  return Math.hypot(b.x - a.x, b.y - a.y) > 0.5 ? [a.x, a.y, b.x, b.y] : null;
}

const still = (move) => Math.hypot(move.from[0] - move.to[0], move.from[1] - move.to[1]) < 0.25 && Math.abs(move.angle) < 0.05
  && Math.abs(move.sx - 1) < 0.002 && Math.abs(move.sy - 1) < 0.002;
const backwards = (move) => ({ from: move.to, to: move.from, angle: -move.angle, sx: 1 / move.sx, sy: 1 / move.sy });

// `move` as an element whose parent's matrix into the slide is `parent` is drawn by its
// `transform`, as its progress goes from 0 (where `move` puts it) to 1 (where it is): an anchor
// that goes straight to its place, turning and growing about it, before what the element's own
// transform (`tail`) does. (Reversed: from where it is, at 0, to `move`, at 1.)
//
// Drawn by its transform attribute, a step a frame, rather than by a CSS transform animation:
// Chrome lays out a whole page's layers again as each of those starts and ends, half a second
// on a slide of a protein's surface; a step of a transform attribute costs a frame's repaint.
function stepsOf(move, parent, tail, reversed = false) {
  const simple = Math.abs(parent.b) < 1e-9 && Math.abs(parent.c) < 1e-9 && Math.abs(parent.a - parent.d) < 1e-9 * Math.max(1, Math.abs(parent.a));
  const own = tail ? ` ${tail}` : "";
  let at;
  if (simple) {
    const inverse = parent.inverse();
    const [from, to] = [move.from, move.to].map(([x, y]) => new DOMPoint(x, y).matrixTransform(inverse));
    at = (e) => `translate(${from.x + (to.x - from.x) * e} ${from.y + (to.y - from.y) * e}) rotate(${move.angle * (1 - e)}) `
      + `scale(${move.sx + (1 - move.sx) * e} ${move.sy + (1 - move.sy) * e}) translate(${-to.x} ${-to.y})${own}`;
  } else {
    // (Under a turned or stretched group: the move's matrix in its parent's units, eased to none.)
    const matrix = new DOMMatrix().translate(...move.from).rotate(move.angle).scale(move.sx, move.sy).translate(-move.to[0], -move.to[1]);
    const m = parent.inverse().multiply(matrix).multiply(parent);
    at = (e) => `matrix(${m.a + (1 - m.a) * e} ${m.b * (1 - e)} ${m.c * (1 - e)} ${m.d + (1 - m.d) * e} ${m.e * (1 - e)} ${m.f * (1 - e)})${own}`;
  }
  return reversed ? (e) => at(1 - e) : at;
}

// The easing of a move (CSS's cubic-bezier(x1, y1, x2, y2)), as a function of progress.
function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const x = (t) => ((ax * t + bx) * t + cx) * t, slope = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (progress) => {
    let t = progress;
    for (let i = 0; i < 8; i += 1) {
      const off = x(t) - progress, d = slope(t);
      if (Math.abs(off) < 1e-6 || Math.abs(d) < 1e-6) break;
      t -= off / d;
    }
    t = Math.min(1, Math.max(0, t));
    return ((ay * t + by) * t + cy) * t;
  };
}
const eased = bezier(0.45, 0.05, 0.55, 0.95);

// One morph being played: its animations, and what it put in the drawing for them, taken out
// when it is done -- finished, or cut short.
function playing(onEnd) {
  const animations = [], temporary = [], movers = new Map();
  let ended = false, pending = 0, clock = null;
  const end = () => {
    if (ended) return;
    ended = true;
    for (const [el, { was }] of movers) { if (was === null) el.removeAttribute("transform"); else el.setAttribute("transform", was); }
    for (const node of temporary) node.remove();
    job.done = true;
    onEnd?.();
  };
  // Each frame, every move stepped to where the clock says (all of them: one progress).
  const step = () => {
    if (ended) return;
    const progress = clock?.effect?.getComputedTiming().progress;
    if (progress !== null && progress !== undefined) {
      const e = eased(progress);
      for (const [el, { at }] of movers) el.setAttribute("transform", at(e));
    }
    requestAnimationFrame(step);
  };
  const job = {
    done: false,
    animate(el, frames, options) {
      if (typeof el.animate !== "function") return null;
      const animation = el.animate(frames, options);
      animations.push(animation);
      pending += 1;
      const settled = () => { pending -= 1; if (!pending) end(); };
      animation.finished.then(settled, settled);
      return animation;
    },
    keep(node) { temporary.push(node); return node; },
    // `el` drawn as `at` says, as the morph's progress goes (eased) from 0 to 1, against the
    // clock: an animation of nothing on `svg`, that every other is timed alike to.
    move(el, at, svg, ms) {
      if (!movers.has(el)) movers.set(el, { at, was: el.getAttribute("transform") });
      el.setAttribute("transform", at(0));
      if (!clock) {
        clock = job.animate(svg, [{ offset: 0 }, { offset: 1 }], { duration: ms, fill: "none" });
        requestAnimationFrame(step);
      }
    },
    stepsOf(el) { return movers.get(el)?.at || null; },
    finish() { for (const animation of [...animations]) { try { animation.finish(); } catch { animation.cancel(); } } end(); },
    cancel() { for (const animation of [...animations]) animation.cancel(); end(); },
    get count() { return animations.length; },
  };
  return job;
}

// Play the morph from `before` (`measure` of the slide shown before) into `svg`, the slide now
// drawn in its place. A job ({ finish, cancel, done }), or null where there is nothing to do.
export function play(before, svg, { duration = DURATION, onEnd } = {}) {
  const screen = svg?.getScreenCTM?.();
  if (!before || !screen) return null;
  const ms = Math.max(1, duration * 1000);
  const toSlide = DOMMatrix.fromMatrix(screen).inverse();
  // All that is needed of the slide arrived at is read before anything is written in it: a write
  // between two reads has the browser lay the whole drawing out again (a large slide's tenth of
  // a second, each time).
  const none = () => ({});
  const now = unitsOf(svg, toSlide).map((unit) => measured(unit, toSlide, none));
  const pairs = paired(before.units, now);
  for (const [i, j] of pairs) {
    if (before.units[i].pieces && before.units[i].kind === now[j].kind) now[j].pieces = piecesMeasured(now[j], toSlide, none);
  }
  const content = layersOf(svg).at(-1) || svg;
  const contentMatrix = content === svg ? new DOMMatrix() : slideMatrix(content, toSlide);

  const job = playing(onEnd);
  let resources = null;
  // What the slide before refers to (its arrowheads, clips, gradients), for what of it is drawn
  // again while it goes.
  const ownedResources = () => {
    if (resources) return;
    resources = job.keep(document.createElementNS(SVG, "defs"));
    resources.setAttribute("data-flexo-morph-ghosts", "");
    const all = [...before.svg.querySelectorAll(RESOURCES)];
    const set = new Set(all);
    for (const node of all) {
      let above = node.parentNode, inner = false;
      while (above && above !== before.svg) { if (set.has(above)) { inner = true; break; } above = above.parentNode; }
      if (!inner) resources.append(node.cloneNode(true));
    }
    svg.prepend(resources);
  };
  // A copy of what was drawn, drawn where it was, put in `parent` (whose matrix into the slide
  // is `matrix`), before `next`.
  const ghost = (old, parent, matrix, next = null) => {
    ownedResources();
    const wrap = job.keep(document.createElementNS(SVG, "g"));
    const into = matrix.inverse().multiply(old.parentMatrix);
    wrap.setAttribute("transform", `matrix(${into.a} ${into.b} ${into.c} ${into.d} ${into.e} ${into.f})`);
    for (const [name, value] of Object.entries(old.inherited || {})) wrap.setAttribute(name, value);
    wrap.setAttribute("pointer-events", "none");
    wrap.setAttribute("aria-hidden", "true");
    const copy = old.el.cloneNode(true);
    wrap.append(copy);
    parent.insertBefore(wrap, next && next.parentNode === parent ? next : null);
    return copy;
  };
  const hard = (a, b) => [{ opacity: a }, { opacity: a, offset: 0.5 }, { opacity: b, offset: 0.5 }, { opacity: b }];
  const fadeIn = (item, from = IN) => {
    job.animate(item.el, [{ opacity: 0 }, { opacity: 0, offset: from }, { opacity: item.opacity }], { duration: ms, easing: "linear", fill: "none" });
  };
  const fadeOut = (copy, by = OUT, opacity = 1) => {
    job.animate(copy, [{ opacity }, { opacity: 0, offset: by }, { opacity: 0 }], { duration: ms, easing: "linear", fill: "forwards" });
  };
  // `item` moved from `move` (in the slide's units) to where it is drawn.
  const glide = (item, move) => job.move(item.el, stepsOf(move, item.parentMatrix, item.el.getAttribute("transform")), svg, ms);
  // A copy of `old` riding along with `item` as it moves (`move`), fading (`swap`: gone halfway).
  const rider = (old, item, move, swap) => {
    const copy = ghost(old, item.el.parentNode, item.parentMatrix, item.el.nextSibling);
    job.move(copy, stepsOf(backwards(move), old.parentMatrix, old.el.getAttribute("transform"), true), svg, ms);
    if (swap) {
      job.animate(copy, hard(old.opacity, 0), { duration: ms, easing: "linear", fill: "forwards" });
      job.animate(item.el, hard(0, item.opacity), { duration: ms, easing: "linear", fill: "none" });
    } else {
      job.animate(copy, [{ opacity: old.opacity, easing: EASE }, { opacity: 0 }], { duration: ms, fill: "forwards" });
    }
    item.halves = swap;
  };
  // One thing the two slides share, from where it was to where it is.
  const moveOne = (old, item) => {
    const move = moveOf(old, item);
    const changed = lookOf(old.el) !== lookOf(item.el);
    if (still(move) && !changed) return;
    if (!still(move)) glide(item, move);
    if (changed) rider(old, item, move, item.texty && words(old.el) !== words(item.el));
  };
  // What a unit is made of, each piece to its own (a figure's parts, a list's items, glyphs).
  const moveApart = (old, unit) => {
    const pieces = unit.pieces;
    if (!pieces || !old.pieces) return false;
    let glyphs = false, pairs;
    if (unit.kind === "math") {
      if (old.el.getAttribute("data-flexo-math") === unit.el.getAttribute("data-flexo-math") || !old.pieces.length || !pieces.length) return false;
      pairs = matchGlyphs(old.pieces, pieces);
      if (!pairs.length) return false;
      glyphs = true;
    } else pairs = paired(old.pieces, pieces, unit.kind === "bullets" ? LIST_TIERS : PART_TIERS);
    const pairedOld = new Set(pairs.map(([i]) => i)), pairedNow = new Set(pairs.map(([, j]) => j));
    for (const [i, j] of pairs) {
      const a = old.pieces[i], b = pieces[j];
      if (glyphs) {
        // A glyph grows by its height (a rule, a bar, stretched), from its middle to its middle.
        const rule = b.key === "rule";
        const sx = rule ? ratio(a.box[2], b.box[2]) : ratio(a.box[3], b.box[3]), sy = ratio(a.box[3], b.box[3]);
        const move = { from: centre(a), to: centre(b), angle: 0, sx, sy };
        if (!still(move)) glide(b, move);
        if (lookOf(a.el) !== lookOf(b.el)) rider(a, b, move, false);
      } else moveOne(a, b);
    }
    pieces.forEach((piece, j) => { if (!pairedNow.has(j)) fadeIn(piece, glyphs ? GLYPHS_IN : IN); });
    old.pieces.forEach((piece, i) => { if (!pairedOld.has(i)) fadeOut(ghost(piece, unit.el, unit.matrix), glyphs ? GLYPHS_OUT : OUT, piece.opacity); });
    return true;
  };

  const partnerOf = new Map(pairs.map(([i, j]) => [i, now[j]]));
  for (const [i, j] of pairs) {
    const old = before.units[i], unit = now[j];
    if (old.kind === unit.kind && moveApart(old, unit)) continue;
    moveOne(old, unit);
  }
  const pairedNow = new Set(pairs.map(([, j]) => j));
  now.forEach((unit, j) => { if (!pairedNow.has(j)) fadeIn(unit); });
  // What only the slide before had: a copy where it was, under what it was under, fading.
  const after = (i) => before.units.slice(i + 1).map((_, k) => partnerOf.get(i + 1 + k)).find(Boolean) || null;
  before.units.forEach((old, i) => {
    if (partnerOf.has(i)) return;
    const next = after(i);
    fadeOut(next ? ghost(old, next.el.parentNode, next.parentMatrix, next.el) : ghost(old, content, contentMatrix), OUT, old.opacity);
  });
  // Halfway, what moved past another is stacked as this slide stacks it: till then, a copy of it
  // stands where the slide before had it, moving with it.
  const crossed = new Set();
  for (const [i1, j1] of pairs) for (const [i2, j2] of pairs) if (i1 < i2 && j1 > j2) { crossed.add(j1); crossed.add(j2); }
  const order = new Map(pairs.map(([i, j]) => [j, i]));
  for (const j of crossed) {
    const unit = now[j], at = job.stepsOf(unit.el);
    // (Not one that does not move, nor one whose words swap halfway: it has its halves already.)
    if (!at || unit.halves) continue;
    const next = before.units.slice(order.get(j) + 1).map((_, k) => partnerOf.get(order.get(j) + 1 + k)).find((other) => other && other !== unit) || null;
    const copy = ghost({ el: unit.el, parentMatrix: unit.parentMatrix }, next ? next.el.parentNode : content, next ? next.parentMatrix : contentMatrix, next?.el);
    job.move(copy, at, svg, ms);
    job.animate(copy, hard(unit.opacity, 0), { duration: ms, easing: "linear", fill: "forwards" });
    job.animate(unit.el, hard(0, unit.opacity), { duration: ms, easing: "linear", fill: "none" });
  }
  if (!job.count) { job.finish(); return null; }
  return job;
}

// A unit's pieces, each measured as `measured` measures a unit.
function piecesMeasured(unit, toSlide, inherited) {
  return piecesOf(unit)?.map((piece) => ({ ...piece, box: boxOf(piece.el, toSlide) })).filter((piece) => piece.box)
    .map((piece) => measured(piece, toSlide, inherited)) || null;
}

const reduced = () => Boolean(globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches);

// -- presenting (present.js) --

// Called as a show draws a slide (`state`: index, step, ended, blank) over the one it showed in
// `root`, before that one goes: what to put in its place -- the frame given (`arrive(shown)`), the
// slide morphing into it from the one before where it says so and the show went forward to it.
// The show keeps a slide's drawing and shows each of its clicks by changing it (stepping.js): the
// slide before is measured as it stands after its last click, and the slide arrived at morphs into
// it as it stands before its first. The same slide drawn again as it arrives (the hint going) is
// the same drawing, moved into the new frame: it goes on arriving. A click as it arrives ends the
// morph -- the slide as it is, then the click -- as going back or jumping does.
export function arriving(root, deck, state) {
  const was = root.ssMorph || null;
  const slide = deck.slides[state.index];
  const now = { index: state.index, step: state.step, svg: slide?.svg, shown: !state.ended && !state.blank, job: null };
  root.ssMorph = now;
  const old = root.querySelector(":scope > .ss-frame");
  const same = (shown) => shown;
  if (was?.job && !was.job.done) {
    if (now.shown && was.shown && was.index === now.index && was.step === now.step && was.svg === now.svg) {
      now.job = was.job;
      return same;
    }
    was.job.cancel();
  }
  const into = transitionOf(slide?.transition);
  if (!into || !old || !was?.shown || !now.shown || reduced()) return same;
  if (now.index !== was.index + 1 || now.step !== 1 || was.step < (deck.slides[was.index]?.steps || 1)) return same;
  const before = measure(old.querySelector(".ss-slide > svg"));
  if (!before) return same;
  return (shown) => {
    queueMicrotask(() => {
      const svg = shown.querySelector(".ss-slide > svg");
      if (svg?.isConnected && root.ssMorph === now) now.job = play(before, svg, { duration: into.duration });
    });
    return shown;
  };
}

// -- previewing (the editor) --

// The morph into a slide played over `host` (the stage's page), from `from` to `to` (each a
// slide's page: { svg, steps }), as presenting plays it: the slide before shown a moment as it
// stands after its last click, morphing into this one as it stands before its first, which is
// held a moment, then gone. A click or a key ends it. { finish }, or null.
export function preview(host, from, to, transition, { onEnd } = {}) {
  if (!host || !from?.svg || !to?.svg) return null;
  dress();
  const layer = document.createElement("div");
  layer.className = "morph-preview";
  const drawn = (page, step) => {
    const box = document.createElement("div");
    box.className = "morph-preview-slide";
    box.innerHTML = String(page.svg).replace(/^<\?xml[^>]*>\s*/, "");
    const svg = ownResources(box.querySelector("svg"));
    if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); }
    showStep(svg, step);
    return box;
  };
  const first = drawn(from, Math.max(1, Number(from.steps) || 1));
  layer.append(first);
  host.append(layer);
  let job = null, timer = 0, gone = false;
  const done = () => {
    if (gone) return;
    gone = true;
    clearTimeout(timer);
    job?.cancel();
    layer.remove();
    window.removeEventListener("keydown", stop, true);
    onEnd?.();
  };
  const stop = (event) => { event.preventDefault(); event.stopPropagation(); done(); };
  layer.addEventListener("pointerdown", stop);
  window.addEventListener("keydown", stop, true);
  const seconds = transition?.duration ?? DURATION;
  timer = setTimeout(() => {
    const before = measure(first.querySelector("svg"));
    const second = drawn(to, 1);
    first.replaceWith(second);
    // (Held a moment once it has arrived, then gone.)
    const settle = () => { if (!gone) timer = setTimeout(done, 450); };
    job = reduced() ? null : play(before, second.querySelector("svg"), { duration: seconds, onEnd: settle });
    if (!job) settle();
  }, 350);
  return { finish: done };
}

function dress() {
  if (document.getElementById("flexo-morph-preview")) return;
  const style = document.createElement("style");
  style.id = "flexo-morph-preview";
  style.textContent = `
.morph-preview { position: absolute; inset: 0; z-index: 30; background: #fff; line-height: 0; overflow: hidden; cursor: default; border-radius: inherit; }
.morph-preview-slide, .morph-preview-slide > svg { display: block; width: 100%; height: 100%; }
.morph-preview svg { text-rendering: geometricPrecision; }
.morph-preview [data-flexo-placeholder], .morph-preview [data-flexo-editing], .morph-preview [data-flexo-later] { display: none; }
.morph-preview [data-flexo-presented] { display: inline; }
.morph-preview svg [data-flexo-show="hidden"] { visibility: hidden !important; opacity: 1 !important; }
`;
  document.head.append(style);
}

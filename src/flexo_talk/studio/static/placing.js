// A slide's objects -- its words, lists, pictures, figures, tables -- placed where they are put,
// as its shapes are (a block's `at`, its `width` its width there: flexo_talk.document), and so
// arranged as Keynote and Inkscape arrange anything: what the deck's editor (editor.js) needs.
//
// - Where each is: its frame (compose.py's data-flexo-frame -- its words' room across, a
//   picture's or a table's own width, from its top to its end) and what it draws (its box, as
//   a shape's is), in the units the slide's shapes are placed in.
// - Taken out of line (Place Freely, ⌘ held as a drag starts, or X and Y given): placed at its
//   frame, that wide, so nothing about it moves or changes (a
//   plot keeping its proportions as its aspect, a gallery its pictures' height); the rest of its
//   place laid out without it. Put Back in Line: in its place's flow again, where it is in its
//   list, the width it was given dropped where it would fill its place anyway.
// - The Arrange tab's commands and fields -- X, Y, W, H, Align (every Relative to, Beside, Move
//   as a Group), Distribute, a set gap, Arrange in a Grid -- move the objects chosen, every one
//   in line among them taken out of line where it stands as one of them moves (the rest of its
//   place would close up under the others else); and Lock keeps one where it is. Their names
//   for the palette and the Mac app's Arrange menu (aligntools.js's, as shapes have them).
// - A placed object is dragged anywhere -- ⇧ along one way, ⌥ a copy -- and sized by its
//   handles (words wrapped again in their new width as they are, the rest in proportion),
//   catching at the slide's edges and middles and at the shapes' and other objects', and where
//   it is as far from its neighbours as they are apart, as a shape does (the magnet, ⌘ free:
//   snapping.js) -- or, snapping to the grid, at the grid's lines and the slide's layout's
//   (grid.js). An object in line is dragged between places as ever; ⌘ held as it starts
//   takes it out of line, to be placed where it is let go (⌘ let go, it catches again).
// - The arrows nudge placed objects (⇧: ten points), one step however many presses; those in
//   line keep the arrows for going from one object to the next.
// - With shapes chosen too (mixed.js): Align and the rest move both, a drag of either kind
//   placed moves them all, and the arrows nudge them all -- the objects in line staying laid out
//   but for Align and its kin, which take them out of line as they move them.
//
// `ctx` is the editor's: studio, shapes (the slide's shapes' editor), pageNode(), slideAt(),
// blocksAt(slide, region), kindOf(block), blockName(block), element(region, index) (an object's
// drawing), editSlide(mutate, options), picks() (the objects chosen, in the order they were:
// [{ region, index }]), focus() (the one chosen alone, if any), frame() ([x, y, width, height]
// of the slide in the shapes' units), scale() (the slide's points in one of them), room(region)
// (a place's width, in the slide's points), mover(element) (a group round a drawing, moved by
// its style), markMany(before, after), markMixed(before, after) (what an undo chooses again),
// mixedOn(), render(), renderInspector(), showArrange(), swallowRelease(held), away(what),
// undoNote(text, options), hideChosen(on), beside() (the slides overlaid: beside.js), grid()
// (the slide's grid: grid.js).

import { h, ui, toast } from "/static/studio/studio.js";
import { alignTools, nearer, drawSpacing, sizeCatch } from "/static/studio/aligntools.js";
import * as Align from "/static/studio/aligning.js";
import * as Snap from "/static/studio/snapping.js";
import * as Beside from "/static/studio/beside.js";
import * as Grid from "/static/studio/grid.js";
import * as F from "/static/studio/freeform.js";
import { sizer } from "/static/kinds/deck/resize.js";
import * as P from "/static/kinds/deck/places.js";

const SVG_NS = "http://www.w3.org/2000/svg";
function S(name, attributes = {}, ...children) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attributes)) if (value !== null && value !== undefined && value !== false) node.setAttribute(key, String(value));
  for (const child of children.flat()) if (child) node.append(child);
  return node;
}

const NEAR = 6; // pixels: how near a guide catches, as a shape's
const { round, roundUp: up } = P;
const keyOf = (pick) => `${pick.region}:${pick.index}`;
const pickOf = (key) => { const at = String(key).lastIndexOf(":"); return { region: key.slice(0, at), index: Number(key.slice(at + 1)) }; };
const counted = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;
// Words: sized by their sides, wrapped again; the rest by their corners, in proportion.
const WORDS = new Set(["text", "bullets", "quote", "callout", "code", "stats", "math"]);
// What keeps its proportions as it is made wider: H sets its width; a plot's, its aspect.
const PROPORTIONED = new Set(["figure", "image", "mechanism", "gallery", "table"]);

export const { placed } = P;

export function placing(ctx) {
  const { studio, shapes } = ctx;
  const blockOf = (pick, slide = ctx.slideAt()) => (slide ? ctx.blocksAt(slide, pick.region)[pick.index] : null);
  const exists = (pick) => Boolean(blockOf(pick));
  const chosen = () => ctx.picks().filter(exists);
  const isLocked = (pick) => Boolean(blockOf(pick)?.locked);
  const nameOf = (pick) => ctx.blockName(blockOf(pick));
  // "Text", "2 Objects".
  const called = (picks) => (picks.length === 1 ? nameOf(picks[0]) : counted(picks.length, "Object"));

  // -- where each is, in the shapes' units --

  // (While a drag or a sizing goes on the slide stays where it is on the screen: how a point
  // there is one in the shapes' units is read once, as it starts -- read at every move, the
  // page would be laid out again each time, the drawings moved meanwhile.)
  let held = null;
  const toUnits = (x, y) => (held ? [held.origin[0] + x / held.px, held.origin[1] + y / held.px] : shapes.pointAt(x, y));
  // The screen's pixels in one of the shapes' units.
  const unit = () => { if (held) return held.px; const a = toUnits(0, 0), b = toUnits(100, 0); return 100 / ((b[0] - a[0]) || 1); };
  const hold = () => { held = null; const px = unit(); held = { origin: shapes.pointAt(0, 0), px }; };
  // Its frame, as compose.py says it set it: [x, y, width, height].
  function frameOf(pick) {
    const element = ctx.element(pick.region, pick.index);
    const values = String(element?.getAttribute("data-flexo-frame") || "").split(" ").map(Number);
    const matrix = element?.parentNode?.getScreenCTM?.();
    if (values.length !== 4 || values.some((value) => !Number.isFinite(value)) || !matrix) return null;
    const [x, y, width, height] = values;
    const a = new DOMPoint(x, y).matrixTransform(matrix), b = new DOMPoint(x + width, y + height).matrixTransform(matrix);
    const p = toUnits(a.x, a.y), q = toUnits(b.x, b.y);
    return [p[0], p[1], q[0] - p[0], q[1] - p[1]];
  }
  // What it draws, [left, top, right, bottom]: what it is lined up and spaced by, as a shape is.
  function boxOf(pick) {
    const rect = ctx.element(pick.region, pick.index)?.getBoundingClientRect();
    if (!rect || (!rect.width && !rect.height)) return null;
    const a = toUnits(rect.left, rect.top), b = toUnits(rect.right, rect.bottom);
    return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
  }
  const framesOf = (picks) => new Map(picks.map((pick) => [keyOf(pick), frameOf(pick)]));
  // Where it stands, as X and Y say: its top left as placed, else its frame's.
  const whereOf = (pick) => { const block = blockOf(pick); if (placed(block)) return block.at.map(Number); const frame = frameOf(pick); return frame ? frame.slice(0, 2) : null; };

  // -- out of line, and back --

  // Each of `picks` in line in `slide` (the document's, being changed) placed where it stands:
  // at its frame (`frames`, read before), as wide. (A plot's proportions kept as its aspect; a
  // gallery's pictures as tall as they are drawn, not as its place would let them be.)
  function outOfLine(slide, picks, frames) {
    for (const pick of picks) {
      const block = blockOf(pick, slide), frame = frames.get(keyOf(pick));
      if (!block || placed(block) || !frame) continue;
      stand(block, frame, ctx.element(pick.region, pick.index));
    }
  }
  // One block made to stand at `frame`, that wide, as it is drawn (`element`: a gallery's
  // pictures as tall as its cells say).
  function stand(block, frame, element) {
    const cells = String(element?.getAttribute("data-flexo-cells") || "").split(" ").map(Number);
    P.stand(block, frame, ctx.kindOf(block), { pictures: cells[2] });
  }
  // Each of `picks` placed put back in its place's flow: its width dropped where it would fill
  // its place anyway (on a slide of another size, its width the place's points again).
  function inLine(slide, picks) {
    const k = ctx.scale();
    for (const pick of picks) {
      const block = blockOf(pick, slide);
      if (block && placed(block)) P.inLine(block, k, ctx.room(pick.region));
    }
  }
  // Place Freely: each of `picks` in line taken out of it where it stands, to be dragged
  // anywhere (as ⌘ held as a drag starts does, or X and Y given), the rest of its place laid out
  // without it.
  function placeFreely(picks = chosen()) {
    const free = picks.filter((pick) => !placed(blockOf(pick)) && !isLocked(pick));
    if (!free.length || ctx.away("move objects")) return false;
    const all = chosen(), frames = framesOf(free);
    ctx.editSlide((slide) => outOfLine(slide, free, frames), { label: `Place ${called(free)} Freely` });
    if (all.length > 1) ctx.markMany(all, all);
    ctx.render();
    return true;
  }
  function putBack(picks = chosen()) {
    const back = picks.filter((pick) => placed(blockOf(pick)));
    if (!back.length || ctx.away("move objects")) return false;
    const all = chosen();
    ctx.editSlide((slide) => inLine(slide, back), { label: `Put ${called(back)} Back in Line` });
    if (all.length > 1) ctx.markMany(all, all);
    ctx.render();
    return true;
  }

  // -- moves, one step --

  // `moves` (key → { dx, dy }) made, one step named `label`: every one of `picks` in line taken
  // out of line where it stands first (`frames`, read before), as one of them moves -- and, in
  // that step, `also(slide)` (the shapes moved with them).
  function commit(moves, label, { picks = chosen(), frames = null, merge = null, also = null } = {}) {
    const moving = [...moves].filter(([, move]) => Math.abs(move.dx) > 0.004 || Math.abs(move.dy) > 0.004);
    if (!moving.length && !also) return false;
    if (ctx.away("move objects")) return false;
    const read = frames || framesOf(picks);
    let made = false;
    ctx.editSlide((slide) => {
      if (moving.length) outOfLine(slide, picks, read);
      for (const [key, { dx, dy }] of moving) {
        const block = blockOf(pickOf(key), slide);
        if (!block || !placed(block)) continue;
        P.movedBy(block, dx, dy);
        made = true;
      }
      if (also) { also(slide); made = true; }
    }, { label, ...(merge ? { merge, hold: true } : {}) });
    return made;
  }

  // -- the drawings moved meanwhile --

  // Objects drawn moved by `moves` ({ key, dx, dy }, in the shapes' units), as a drag draws them;
  // none: as they are. Each stays so until the slide's drawing that comes of it takes its place.
  const lifted = new Map();
  function showMoves(moves) {
    const px = unit();
    const now = new Set();
    for (const { key, dx, dy } of moves || []) {
      const pick = pickOf(key), element = ctx.element(pick.region, pick.index);
      if (!element) continue;
      const wrap = ctx.mover(element);
      const scale = held ? (held.scales[key] ??= 1 / (wrap.parentNode?.getScreenCTM?.()?.a || 1)) : 1 / (wrap.parentNode?.getScreenCTM?.()?.a || 1);
      wrap.style.transform = `translate(${dx * px * scale}px, ${dy * px * scale}px)`;
      lifted.set(key, wrap);
      now.add(key);
    }
    for (const [key, wrap] of lifted) if (!now.has(key)) { wrap.style.transform = ""; lifted.delete(key); }
  }
  // (Held while the change is on its way; put back if it never comes -- nothing changed.)
  let holding = 0;
  function waitFor() {
    const mine = ++holding;
    setTimeout(() => { if (holding === mine) showMoves(null); }, 6000);
  }
  // The slide drawn again: what was moved here is where it is drawn now.
  function drawn() { lifted.clear(); attach(); }

  // -- the guides --

  const layer = S("svg", { class: "shape-layer object-guides", preserveAspectRatio: "xMidYMid meet", "aria-hidden": "true" });
  const guides = S("g", { class: "shape-guides" });
  layer.append(guides);
  const tip = h("div.size-tip.shape-tip", { hidden: true });
  function attach() {
    const node = ctx.pageNode();
    if (!node) return;
    const [x, y, width, height] = ctx.frame();
    layer.setAttribute("viewBox", `${x} ${y} ${width} ${height}`);
    if (layer.parentNode !== node) node.append(layer);
    if (tip.parentNode !== node) node.append(tip);
  }
  function guide(axis, at, from = Beside.besideAt(gesture?.targets, axis, at)) {
    const [x0, y0, width, height] = ctx.frame(), px = 1 / unit();
    // (One on a slide overlaid, in that slide's tint, with its box: beside.js.)
    const kind = from ? "shape-guide beside" : "shape-guide", style = from?.tint ? `--beside:${from.tint}` : null;
    guides.append(axis === "x" ? S("line", { x1: at, y1: y0, x2: at, y2: y0 + height, class: kind, "stroke-width": px, style })
      : S("line", { x1: x0, y1: at, x2: x0 + width, y2: at, class: kind, "stroke-width": px, style }));
    if (from) guides.append(S("rect", { x: from[0], y: from[1], width: from[2] - from[0], height: from[3] - from[1], class: "shape-beside", "stroke-width": px, style }));
  }
  function say(text, event) {
    const node = ctx.pageNode();
    if (!node || !event) return;
    const outer = node.getBoundingClientRect();
    tip.textContent = text;
    tip.hidden = false;
    tip.style.left = `${event.clientX - outer.left + 14}px`;
    tip.style.top = `${event.clientY - outer.top + 16}px`;
  }
  // What a drag catches at: the slide's edges and middles, and the edges and middles of the
  // shapes and objects not moving -- each box, but lines, spaced among (aligning.js); or,
  // snapping to the grid, its lines (grid.js).
  function targetsFor(movingObjects, movingShapes) {
    if (Snap.toGrid()) return Grid.targetsOf(ctx.frame(), ctx.grid?.());
    const [x0, y0, width, height] = ctx.frame();
    const xs = [x0, x0 + width / 2, x0 + width], ys = [y0, y0 + height / 2, y0 + height], boxes = [];
    const add = (box, spaced = true) => {
      if (!box) return;
      xs.push(box[0], (box[0] + box[2]) / 2, box[2]);
      ys.push(box[1], (box[1] + box[3]) / 2, box[3]);
      if (spaced) boxes.push(box);
    };
    const slide = ctx.slideAt() || {};
    for (const region of ctx.regions(slide)) {
      ctx.blocksAt(slide, region).forEach((_, index) => { if (!movingObjects.has(`${region}:${index}`)) add(boxOf({ region, index })); });
    }
    shapes.list().forEach((spec, index) => {
      if (!spec || movingShapes.includes(index)) return;
      add(shapes.boxOf(index), F.family(spec.kind) !== "line");
    });
    // And what is on the slides overlaid on it (across.js), caught at too.
    return Beside.withBeside({ xs, ys, boxes }, ctx.beside?.());
  }
  // The nearest of `values` to any of `mine` within reach: how far to move to it, and where.
  const catchAt = (mine, values) => Snap.nearest(mine, values, NEAR / unit());

  // -- dragged --

  let gesture = null;
  // Pressed on one of the slide's objects (`part`): a placed one is dragged anywhere -- with
  // those chosen with it, objects and shapes -- and one in line too while ⌘ is held as it is
  // pressed, out of line where it is let go. (A click, let go where it was, chooses as ever.)
  function press(event, part) {
    if (event.button !== 0 || event.shiftKey || event.ctrlKey || gesture || part?.kind !== "block") return false;
    const pick = { region: part.region, index: part.index }, block = blockOf(pick);
    if (!block) return false;
    const out = event.metaKey && !placed(block);
    // In line, as ever -- but locked, kept where it is: not carried to another place either.
    // (Either way the click it ends in chooses it.)
    if (!placed(block) && !out) return Boolean(block.locked);
    if (block.locked) return true;
    const all = chosen(), mine = all.some((each) => keyOf(each) === keyOf(pick));
    // Those chosen with it, if it is: placed ones (and, ⌘ held, those in line too), and the
    // shapes chosen with them; else it alone.
    const objects = (mine ? all : [pick]).filter((each) => (out || placed(blockOf(each))) && !isLocked(each));
    const drawn = mine && ctx.mixedOn() ? shapes.chosen().filter((index) => !shapes.lockedAt(index)) : [];
    begin(event, { type: "move", pick, objects, drawn, out, copy: false, mine });
    return true;
  }
  // Pressed on a shape chosen with placed objects (mixed.js): they all move together.
  function pressShape(event) {
    if (event.button !== 0 || event.shiftKey || event.metaKey || event.ctrlKey || gesture || !ctx.mixedOn() || shapes.armed?.()) return false;
    const index = shapes.at(event);
    if (index === null || !shapes.chosen().includes(index)) return false;
    const objects = chosen().filter((pick) => placed(blockOf(pick)) && !isLocked(pick));
    if (!objects.length) return false;
    begin(event, { type: "move", objects, drawn: shapes.chosen().filter((one) => !shapes.lockedAt(one)), out: false, onShape: index });
    // (The shapes': no band across the slide from it.)
    event.shapes = true;
    return true;
  }
  function begin(event, state) {
    hold();
    held.scales = {};
    gesture = { ...state, start: [event.clientX, event.clientY], from: toUnits(event.clientX, event.clientY), started: false, frame: 0 };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("keyup", onKey, true);
  }
  function finish() {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", cancel);
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("keyup", onKey, true);
    const was = gesture;
    gesture = null;
    held = null;
    if (was?.frame) cancelAnimationFrame(was.frame);
    guides.replaceChildren();
    tip.hidden = true;
    ctx.pageNode()?.classList.remove("block-dragging", "object-dragging");
    document.body.classList.remove("block-grabbing");
    return was;
  }
  function onMove(event) {
    const g = gesture;
    if (!g) return;
    g.last = event;
    if (!g.started) {
      if (Math.hypot(event.clientX - g.start[0], event.clientY - g.start[1]) < 3) return;
      if (g.type === "move" && ctx.away("move objects")) { finish(); return; }
      g.started = true;
      startDrag(g);
    }
    event.preventDefault();
    if (!g.frame) g.frame = requestAnimationFrame(() => { if (gesture === g) { g.frame = 0; step(g.last); } });
  }
  function onKey(event) {
    const g = gesture;
    if (!g) return;
    if (event.type === "keydown" && event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      cancel();
      ctx.swallowRelease(true);
      return;
    }
    // ⇧, ⌥ or ⌘ pressed or let go mid-drag: drawn again with them.
    if (g.started && g.last && ["Shift", "Alt", "Meta", "Control"].includes(event.key)) {
      g.last = new PointerEvent("pointermove", { clientX: g.last.clientX, clientY: g.last.clientY, shiftKey: event.shiftKey, altKey: event.altKey, metaKey: event.metaKey, ctrlKey: event.ctrlKey });
      step(g.last);
    }
  }
  function cancel() {
    const was = finish();
    if (!was) return;
    if (was.started) {
      if (was.type === "size") sizeUndone(was);
      else { showMoves(null); if (was.drawn?.length) shapes.showMoves(null); }
      ctx.render();
    }
  }
  function onUp(event) {
    const g = gesture;
    if (!g) return;
    if (g.started) step(event);
    const was = finish();
    if (!was.started) return;
    ctx.swallowRelease();
    if (was.type === "size") { sizeDone(was); return; }
    drop(was);
  }
  function startDrag(g) {
    attach();
    attachTip();
    ctx.pageNode()?.classList.add("block-dragging", "object-dragging");
    document.body.classList.add("block-grabbing");
    window.getSelection?.()?.removeAllRanges();
    if (g.type !== "move") return;
    g.frames = framesOf(g.objects);
    g.boxes = g.objects.map(boxOf);
    const all = [...g.boxes, ...g.drawn.map((index) => shapes.boxOf(index))].filter(Boolean);
    g.box = all.length ? [Math.min(...all.map((b) => b[0])), Math.min(...all.map((b) => b[1])), Math.max(...all.map((b) => b[2])), Math.max(...all.map((b) => b[3]))] : null;
    g.targets = targetsFor(new Set(g.objects.map(keyOf)), g.drawn);
    g.spacing = Align.spacing(g.targets.boxes);
  }
  const attachTip = () => { const node = ctx.pageNode(); if (node && tip.parentNode !== node) node.append(tip); };
  function step(event) {
    const g = gesture;
    if (!g?.started) return;
    guides.replaceChildren();
    if (g.type === "size") { stepSize(g, event); return; }
    const point = toUnits(event.clientX, event.clientY), free = Snap.free(event);
    let dx = point[0] - g.from[0], dy = point[1] - g.from[1];
    if (event.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
    if (!free && g.box) {
      const [x0, y0, x1, y1] = g.box;
      let across = event.shiftKey && dx === 0 ? null : catchAt([x0 + dx, (x0 + x1) / 2 + dx, x1 + dx], g.targets.xs);
      let down = event.shiftKey && dy === 0 ? null : catchAt([y0 + dy, (y0 + y1) / 2 + dy, y1 + dy], g.targets.ys);
      const even = g.spacing.caught([x0 + dx, y0 + dy, x1 + dx, y1 + dy], NEAR / unit(), { x: !(event.shiftKey && dx === 0), y: !(event.shiftKey && dy === 0) });
      [across, even.x] = nearer(across, even.x);
      [down, even.y] = nearer(down, even.y);
      if (across) { dx += across.gap; guide("x", across.at); } else if (even.x) dx += even.x.shift;
      if (down) { dy += down.gap; guide("y", down.at); } else if (even.y) dy += even.y.shift;
      const now = [x0 + dx, y0 + dy, x1 + dx, y1 + dy];
      drawSpacing(guides, [...g.spacing.marks(even.x, now), ...g.spacing.marks(even.y, now)], 1 / unit(), S);
    }
    g.dx = dx; g.dy = dy;
    // ⌥: a copy goes, they stay (objects alone).
    g.copy = event.altKey && !g.drawn.length;
    showMoves(g.objects.map((pick) => ({ key: keyOf(pick), dx, dy })));
    if (g.drawn.length) shapes.showMoves(g.drawn.map((id) => ({ id, dx, dy })));
    const corner = g.box ? [g.box[0] + dx, g.box[1] + dy] : [dx, dy];
    say(`${Math.round(corner[0])}, ${Math.round(corner[1])}`, event);
  }
  function drop(g) {
    const dx = g.dx || 0, dy = g.dy || 0;
    if (Math.abs(dx) < 0.005 && Math.abs(dy) < 0.005) { showMoves(null); if (g.drawn.length) shapes.showMoves(null); ctx.render(); return; }
    const moves = new Map(g.objects.map((pick) => [keyOf(pick), { dx, dy }]));
    const before = chosen();
    if (g.copy) {
      // Copies, each after the one it is of in its place, placed where they were let go.
      showMoves(null);
      // (The last of each place first: those before it keep their places.)
      const picks = [...g.objects].sort((a, b) => (a.region === b.region ? b.index - a.index : 0));
      ctx.editSlide((slide) => {
        for (const pick of picks) {
          const list = ctx.blocksAt(slide, pick.region), block = list[pick.index], frame = g.frames.get(keyOf(pick));
          if (!block) continue;
          const copy = structuredClone(block);
          if (!placed(copy) && frame) stand(copy, frame, ctx.element(pick.region, pick.index));
          if (!placed(copy)) continue;
          P.movedBy(copy, dx, dy);
          delete copy.locked;
          list.splice(pick.index + 1, 0, copy);
        }
      }, { label: `Duplicate ${called(g.objects)}` });
      ctx.render();
      return;
    }
    const label = g.drawn.length ? `Move ${[counted(g.objects.length, "Object"), counted(g.drawn.length, "Shape")].join(" and ")}` : `Move ${called(g.objects)}`;
    // (One dragged that was not chosen is chosen, as a shape dragged is.)
    if (g.pick && !g.mine) ctx.chooseOne(g.pick);
    const shapesBefore = shapes.chosen();
    commit(moves, label, {
      picks: g.objects, frames: g.frames,
      also: g.drawn.length ? (slide) => { for (const index of g.drawn) if (slide.shapes?.[index]) shapes.moveIn(slide.shapes, index, dx, dy); } : null,
    });
    waitFor();
    if (g.drawn.length) ctx.markMixed({ own: before, shapes: shapesBefore }, { own: chosen(), shapes: shapes.chosen() });
    else if (before.length > 1) ctx.markMany(before, before);
    ctx.render();
  }

  // -- sized by its handles --

  // A handle of the placed object chosen alone pressed: words by their sides, wrapped again as
  // they are; the rest by their corners, in proportion -- the edge or corner not dragged staying
  // where it is, and the one dragged catching where a shape's would. (Not one placed: false.)
  function size(event, handle) {
    const pick = ctx.focus(), block = pick && blockOf(pick);
    if (!placed(block) || event.button !== 0 || gesture) return false;
    event.preventDefault();
    event.stopPropagation();
    if (block.locked) return true;
    const element = ctx.element(pick.region, pick.index), frame = frameOf(pick), box = boxOf(pick);
    if (!element || !frame || !box) return true;
    const kind = ctx.kindOf(block), words = WORDS.has(kind);
    const wrap = ctx.mover(element);
    Object.assign(wrap.style, { transformBox: "", transformOrigin: "0 0", transform: "" });
    const kept = element.cloneNode(true);
    const k = ctx.scale();
    // (Words, a table, a gallery or a plot set again as the slide will, in its points, as
    // they are sized in line: resize.js. A picture or a figure scaled.)
    const spanned = String(element.getAttribute("data-flexo-span") || "").split(" ").map(Number);
    const span = spanned.length === 2 && spanned.every(Number.isFinite) ? { x: spanned[0], width: spanned[1] } : { x: frame[0] * k, width: frame[2] * k };
    const share = kind === "math" ? ({ start: 0, end: 1 }[block.align] ?? 0.5) : 0;
    const set = words || ["table", "gallery", "plot"].includes(kind) ? sizer(element, kind, span, { share, higher: (wide) => wide / span.width }) : null;
    const least = Math.max(Number(element.getAttribute("data-flexo-least")) / k || 0, 12);
    begin(event, { type: "size", pick, block, kind, handle, rect: frame, box, element, wrap, kept, set, words, least, span });
    return true;
  }
  function stepSize(g, event) {
    const point = toUnits(event.clientX, event.clientY), free = Snap.free(event);
    const [x, y, width, height] = g.rect;
    const west = g.handle.includes("w"), north = g.handle.startsWith("n") && g.handle.length === 2;
    // The point that stays, and the edges that move.
    const fixed = [west ? x + width : x, north ? y + height : y];
    let px = point[0], py = point[1];
    if (!free) {
      const targets = g.targets ||= targetsFor(new Set([keyOf(g.pick)]), []);
      g.spacing ||= Align.spacing(targets.boxes);
      const caught = sizeCatch(g.spacing, { point: [px, py], fixed, box: [x, y, x + width, y + height], sides: { x: true, y: !g.words }, reach: NEAR / unit(),
        guide: (at, axis) => catchAt([at], axis === "x" ? targets.xs : targets.ys) });
      [px, py] = caught.point;
      for (const line of caught.guides) guide(line.axis, line.at);
      g.marks = caught.marks;
    }
    let wide = Math.max(g.least, west ? fixed[0] - px : px - fixed[0]);
    if (!g.words && height > 0) {
      // In proportion: the nearer of the width and the height the pointer gives.
      const tall = Math.max(1, north ? fixed[1] - py : py - fixed[1]);
      const byHeight = tall * (width / height);
      if (Math.abs(byHeight - width) > Math.abs(wide - width) || event.shiftKey) wide = Math.max(g.least, byHeight);
    }
    const scale = wide / width;
    const left = west ? fixed[0] - wide : fixed[0], top = north ? fixed[1] - height * scale : fixed[1];
    g.at = [left, top];
    g.wide = wide;
    const px2 = unit(), k = ctx.scale(), wrapScale = (g.wrapScale ??= 1 / (g.wrap.parentNode?.getScreenCTM?.()?.a || 1));
    if (g.set) {
      const down = g.set(left * k, wide * k) || 0;
      g.wrap.style.transform = !g.words && top !== y ? `translate(0px, ${(top - y) * px2 * wrapScale}px)` : "";
      g.tall = g.rect[3] + down / k;
    } else if (g.words) {
      g.wrap.style.transform = `translate(${(left - x) * px2 * wrapScale}px, 0px)`;
    } else {
      // (Scaled about its frame's top left, moved to where that is now.)
      const origin = [x * k, y * k];
      g.wrap.style.transformOrigin = `${origin[0]}px ${origin[1]}px`;
      g.wrap.style.transform = `translate(${(left - x) * px2 * wrapScale}px, ${(top - y) * px2 * wrapScale}px) scale(${scale})`;
    }
    if (g.marks) drawSpacing(guides, g.marks([left, top, left + wide, top + height * scale]), 1 / unit(), S);
    ctx.hideChosen(true);
    say(`${Math.round(wide)} × ${Math.round(g.words ? height : height * scale)} pt`, event);
  }
  function sizeDone(g) {
    if (!g.at || Math.abs(g.wide - g.rect[2]) < 0.05) { sizeUndone(g); return; }
    const [left, top] = g.at;
    ctx.editSlide((slide) => {
      const block = blockOf(g.pick, slide);
      if (!block) return;
      block.at = [round(left), round(top)];
      block.width = up(g.wide);
      delete block.placeholder;
    }, { label: `Resize ${nameOf(g.pick)}` });
    waitFor();
    ctx.hideChosen(false);
    ctx.render();
  }
  function sizeUndone(g) {
    if (g.set && g.element?.isConnected && g.kept) g.element.replaceWith(g.kept);
    g.wrap.style.transform = "";
    g.wrap.style.transformOrigin = "";
    ctx.hideChosen(false);
    ctx.render();
  }

  // -- nudged --

  // The arrows: the placed objects chosen (with the shapes chosen with them, `drawn`) moved a
  // point, ⇧ ten -- one step however many presses, as a shape's are. None placed: false.
  let nudged = null;
  function nudge(event, { drawn = [] } = {}) {
    const k = event.key;
    if (!k.startsWith("Arrow") || event.metaKey || event.ctrlKey || event.altKey) return false;
    const objects = chosen().filter((pick) => placed(blockOf(pick)) && !isLocked(pick));
    if (!objects.length) return false;
    const by = event.shiftKey ? 10 : 1;
    const [dx, dy] = { ArrowLeft: [-by, 0], ArrowRight: [by, 0], ArrowUp: [0, -by], ArrowDown: [0, by] }[k];
    const key = [...objects.map(keyOf), ...drawn].join(",");
    const run = nudged && nudged.slide === ctx.slideIndex() && nudged.key === key && Date.now() - nudged.at < 1500 ? nudged : { slide: ctx.slideIndex(), key, id: Date.now() };
    run.at = Date.now();
    nudged = run;
    const before = chosen(), shapesBefore = shapes.chosen();
    // Stopped where it would pass a guide on a slide overlaid, snapping on (beside.js).
    const reach = (boxes) => (boxes.length ? [Math.min(...boxes.map((b) => b[0])), Math.min(...boxes.map((b) => b[1])), Math.max(...boxes.map((b) => b[2])), Math.max(...boxes.map((b) => b[3]))] : null);
    const caught = Snap.toGuides() && ctx.beside ? Beside.nudgeCaught(reach([...objects.map(boxOf), ...drawn.map((index) => shapes.boxOf(index))].filter(Boolean)), dx, dy, ctx.beside()) : null;
    if (caught) ({ dx, dy } = caught);
    const moves = new Map(objects.map((pick) => [keyOf(pick), { dx, dy }]));
    const label = drawn.length ? `Move ${[counted(objects.length, "Object"), counted(drawn.length, "Shape")].join(" and ")}` : `Move ${called(objects)}`;
    commit(moves, label, { picks: objects, merge: `object-nudge-${run.id}`,
      also: drawn.length ? (slide) => { for (const index of drawn) if (slide.shapes?.[index]) shapes.moveIn(slide.shapes, index, dx, dy); } : null });
    if (drawn.length) ctx.markMixed({ own: before, shapes: shapesBefore }, { own: chosen(), shapes: shapes.chosen() });
    else if (before.length > 1) ctx.markMany(before, before);
    ctx.render();
    if (caught?.guides.length) {
      attach();
      guides.replaceChildren();
      for (const line of caught.guides) guide(line.axis, line.at, line.box);
      clearTimeout(nudge.shown);
      nudge.shown = setTimeout(() => { if (!gesture) guides.replaceChildren(); }, 900);
    }
    return true;
  }

  // -- Align and Distribute, the objects alone --

  // (Each by its key, "left:0"; what moves of them gathered as its change is made, then made.)
  let gathered = null;
  const arranging = alignTools({
    picks: () => chosen().map(keyOf),
    box: (key) => boxOf(pickOf(key)),
    locked: (key) => isLocked(pickOf(key)),
    name: (key) => nameOf(pickOf(key)),
    frame: () => ctx.frame(), noun: "slide", word: "Object",
    few: () => "Choose three or more objects",
    move: (_, key, dx, dy) => { gathered?.set(key, { dx, dy }); },
    edit: (mutate, said) => {
      gathered = new Map();
      try { mutate([]); } finally { /* gathered kept */ }
      const moves = gathered;
      gathered = null;
      const all = chosen();
      const made = commit(moves, said, { picks: all });
      if (made && all.length > 1) ctx.markMany(all, all);
      if (made) { ctx.render(); }
      return made;
    },
    renderInspector: () => ctx.renderInspector(), showPanel: () => ctx.showArrange(),
    show: (moves) => showMoves(moves ? moves.map(({ id, dx, dy }) => ({ key: id, dx, dy })) : null),
    tab: () => true, showTab: () => ctx.showArrange(),
  });

  // For mixed.js: the page's own, moved with the shapes -- one step, the shapes' change in it.
  // (`moves`: [{ pick, dx, dy }]; `shapesChange(list)`: the shapes' list changed in place.)
  function moveWith(moves, label, shapesChange) {
    const all = chosen();
    const map = new Map(moves.map(({ pick, dx, dy }) => [keyOf(pick), { dx, dy }]));
    const made = commit(map, label, { picks: all, also: shapesChange ? (slide) => { if (Array.isArray(slide.shapes)) shapesChange(slide.shapes); } : null });
    ctx.render();
    return made;
  }

  // -- the Arrange tab --

  // Where those chosen are (X, Y: a placed one's top left, else where it would be placed --
  // its frame's; several, where their frames reach), how wide one is (W) and tall (H: a picture's, a figure's, a
  // table's sets its width in proportion; a plot's, its aspect; words are as tall as they are),
  // Put Back in Line, Locked; then Align and Distribute.
  function fields() {
    const picks = chosen();
    if (!picks.length) return null;
    const one = picks.length === 1 ? picks[0] : null, block = one ? blockOf(one) : null;
    // (Their frames' top left, as one's is: what is placed, at, is where the frame is.)
    const reach = () => (one ? whereOf(one) : P.reach(picks.map((pick) => { const frame = frameOf(pick); return frame && [frame[0], frame[1], frame[0] + frame[2], frame[1] + frame[3]]; })));
    const where = reach();
    const moveTo = (axis) => (value) => {
      if (value === null || value === undefined || !where) return;
      const now = reach(), delta = value - now[axis === "x" ? 0 : 1];
      if (Math.abs(delta) < 0.005) return;
      const moves = new Map(picks.filter((pick) => !isLocked(pick)).map((pick) => [keyOf(pick), axis === "x" ? { dx: delta, dy: 0 } : { dx: 0, dy: delta }]));
      if (commit(moves, `Move ${called(picks)}`, { picks })) { if (picks.length > 1) ctx.markMany(picks, picks); ctx.render(); }
    };
    const out = [];
    if (where) {
      out.push(h("div.row", {},
        ui.field("X", ui.number({ value: round(where[0]), step: 1, unit: "pt", key: "object.x", onChange: moveTo("x") })),
        ui.field("Y", ui.number({ value: round(where[1]), step: 1, unit: "pt", key: "object.y", onChange: moveTo("y") }))));
    }
    const frame = one ? frameOf(one) : null;
    if (one && frame) {
      const kind = ctx.kindOf(block);
      const wide = placed(block) && block.width != null ? Number(block.width) : frame[2];
      const tall = frame[3] * (wide / (frame[2] || 1));
      const resize = (width, extra = null) => {
        if (!width || width < 1 || isLocked(one) || ctx.away("resize objects")) return;
        const frames = framesOf(picks);
        ctx.editSlide((slide) => {
          outOfLine(slide, [one], frames);
          const b = blockOf(one, slide);
          if (!b) return;
          b.width = round(width);
          extra?.(b);
          delete b.placeholder;
        }, { label: `Resize ${nameOf(one)}` });
        ctx.render();
      };
      const height = ui.number({ value: round(tall), min: 1, step: 1, unit: "pt", key: "object.h",
        onChange: (value) => {
          if (!value) return;
          if (kind === "plot") resize(wide, (b) => { b.aspect = Math.round((wide / value) * 1000) / 1000; });
          else if (PROPORTIONED.has(kind) || kind === "plot") resize(wide * (value / (tall || 1)));
        } });
      // (Words are as tall as they are set: their height is theirs, not to be given.)
      if (WORDS.has(kind)) { height.input.disabled = true; height.title = "As tall as its words"; }
      out.push(h("div.row", {},
        ui.field("Width", ui.number({ value: round(wide), min: 1, step: 1, unit: "pt", key: "object.w", onChange: (value) => resize(value) })),
        ui.field("Height", height)));
    }
    const back = picks.filter((pick) => placed(blockOf(pick)));
    if (back.length) {
      out.push(h("div.row", {}, ui.button("Put Back in Line", () => putBack(back), { small: true, icon: "layout", title: "Into its place on the slide again, where it is in its list" })));
    }
    out.push(ui.toggle({ value: picks.every(isLocked), label: "Locked", key: "object.locked", onChange: (on) => lock(on) }));
    return h("div.section", {}, h("div.section-title", {}, "Arrange"), out);
  }
  // With shapes chosen too: X and Y of where they all reach, moving them all -- the objects in
  // line among them taken out of line as they move -- one step.
  function mixedFields() {
    const picks = chosen(), drawn = shapes.chosen();
    if (!picks.length || !drawn.length) return null;
    const frameBox = (pick) => { const frame = frameOf(pick); return frame && [frame[0], frame[1], frame[0] + frame[2], frame[1] + frame[3]]; };
    const reach = () => P.reach([...picks.map(frameBox), ...drawn.map((index) => shapes.boxOf(index))]);
    const where = reach();
    if (!where) return null;
    const moveTo = (axis) => (value) => {
      if (value === null || value === undefined) return;
      const delta = value - reach()[axis === "x" ? 0 : 1];
      if (Math.abs(delta) < 0.005) return;
      const [dx, dy] = axis === "x" ? [delta, 0] : [0, delta];
      const objects = picks.filter((pick) => !isLocked(pick)), moving = drawn.filter((index) => !shapes.lockedAt(index));
      const before = { own: picks, shapes: drawn };
      const made = commit(new Map(objects.map((pick) => [keyOf(pick), { dx, dy }])), `Move ${[counted(objects.length, "Object"), counted(moving.length, "Shape")].filter((said) => !said.startsWith("0 ")).join(" and ")}`, {
        picks, also: moving.length ? (slide) => { for (const index of moving) if (slide.shapes?.[index]) shapes.moveIn(slide.shapes, index, dx, dy); } : null });
      if (made) { ctx.markMixed(before, { own: chosen(), shapes: shapes.chosen() }); ctx.render(); }
    };
    return h("div.section", {}, h("div.section-title", {}, "Arrange"), h("div.row", {},
      ui.field("X", ui.number({ value: round(where[0]), step: 1, unit: "pt", key: "object.x", onChange: moveTo("x") })),
      ui.field("Y", ui.number({ value: round(where[1]), step: 1, unit: "pt", key: "object.y", onChange: moveTo("y") }))));
  }
  function lock(on, picks = chosen()) {
    if (!picks.length || ctx.away("lock objects")) return false;
    const all = chosen();
    ctx.editSlide((slide) => {
      for (const pick of picks) {
        const block = blockOf(pick, slide);
        if (!block) continue;
        if (on) block.locked = true; else delete block.locked;
      }
    }, { label: `${on ? "Lock" : "Unlock"} ${called(picks)}` });
    if (all.length > 1) ctx.markMany(all, all);
    ctx.render();
    return true;
  }
  const arrangePanel = () => [fields(), arranging.section({ tab: true })].filter(Boolean);

  // -- by name --

  // For the palette and the Mac app's Arrange menu: what may be done with the objects chosen.
  function commands() {
    const picks = chosen();
    if (!picks.length) return [];
    const name = called(picks), out = [];
    const back = picks.filter((pick) => placed(blockOf(pick)));
    if (back.length) out.push({ icon: "layout", label: "Put Back in Line", hint: name, run: () => putBack(back) });
    const free = picks.filter((pick) => !placed(blockOf(pick)) && !isLocked(pick));
    if (free.length) out.push({ icon: "arrange", label: "Place Freely", hint: name, run: () => placeFreely(free) });
    out.push(...arranging.commands(name));
    const locked = picks.every(isLocked);
    out.push(locked ? { icon: "lock", label: "Unlock", keys: "⌥⌘L", hint: name, run: () => lock(false) } : { icon: "lock", label: "Lock", keys: "⌘L", hint: name, run: () => lock(true) });
    return out;
  }

  return {
    placed, frameOf, boxOf, press, pressShape, size, nudge, drawn, attach, putBack, placeFreely, lock, moveWith, commands, arrangePanel, mixedFields,
    reveal: () => arranging.reveal(), align: (side) => arranging.align(side),
    showMoves: (moves) => showMoves(moves ? moves.map(({ pick, dx, dy }) => ({ key: keyOf(pick), dx, dy })) : null),
    busy: () => Boolean(gesture?.started),
    // (Which, for the help bar's keys: "move" or "size".)
    dragging: () => (gesture?.started ? gesture.type : null),
    // (A press on one of them, held: they are carried together if it is dragged.)
    pressing: () => Boolean(gesture && gesture.type === "move" && gesture.objects.length > 1),
    any: () => chosen().length > 0,
    // Whether any of `picks` (else those chosen) stands where it says.
    anyPlaced: (picks = chosen()) => picks.some((pick) => placed(blockOf(pick))),
    isPlaced: (pick) => placed(blockOf(pick)),
    locked: (pick) => isLocked(pick),
    called,
  };
}

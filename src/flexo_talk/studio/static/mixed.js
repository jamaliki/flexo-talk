// A slide's objects (its words, lists, pictures, figures) chosen with the shapes drawn on it, as
// Keynote chooses a text box and a drawing together (the studio's mixed.js) -- or, a figure on
// it being edited, the figure's shapes chosen with them: what the slide's editor needs of it,
// and what it needs of the editor.
//
// Chosen with shapes, the objects are kept as several are (⌘A, ⇧-click: framed each, in the
// editor's `many`), even one: never the one object chosen alone, whose keys type in it and whose
// figure is opened. ⇧-click or ⌘-click on an object or a shape puts it in, or takes it out; one
// left alone is chosen as it is alone. A figure being edited, its shapes chosen, ⇧-click on a
// shape over the slide chooses both: the figure stays open, its shapes chosen in it (each as
// { region, index, part }: the figure's place, the shape's id). ⇧-click on another object then
// chooses the figure whole with it and the shapes, and says so: a figure's shapes are never
// chosen with the slide's other objects (see press).
//
// `ctx` is the editor's: studio, shapes (its shapes' editor), state; many() (the objects chosen
// together: [{ region, index }], none when they are not), setMany(picks) (they are, none: not),
// focusBlock(region, index, then), leave() (no words typed, no figure opened, the slide's list
// without the keys), figure() (the figure being edited: { parts, region, index }, else null),
// inFigure(event), partElement(id), blocksAt(slide, region), slideAt(), regionsOf(slide),
// blockName(block), element(region, index) (an object's drawing), partAt(event),
// editSlide(mutate, options), copyOf(block), pasteClip(clip), select(slide), render(), crumb(),
// frame(), clipChosen(cut), clipItems(), undoNote(text, options), away(what), showPanel(),
// swallowRelease(held), placing (placing.js's: the slide's objects moved with the shapes --
// by Align and its kin, taken out of line as they are; by the arrows and a drag, those placed).

import { mixedChoice } from "/static/studio/mixed.js";
import { toast } from "/static/studio/studio.js";

// What ⇧-click on another object says, a figure's shapes chosen with the slide's.
export const WHOLE = "A figure’s shapes can’t be selected with other objects, so the whole figure is selected instead.";

const samePlace = (a, b) => a?.region === b?.region && a?.index === b?.index;
const samePick = (a, b) => samePlace(a, b) && a?.part === b?.part;

export function slideMixed(ctx) {
  const { studio, shapes, state } = ctx;
  const blocksOn = (region) => ctx.blocksAt(ctx.slideAt() || {}, region);
  const exists = (pick) => Boolean(pick && blocksOn(pick.region)[pick.index]);
  // The figure being edited, with shapes of it chosen: those, by their ids.
  const opened = () => { const figure = ctx.figure(); return figure && figure.parts.selected.some((id) => isPart(figure, id)) ? figure : null; };
  const isPart = (figure, id) => Boolean(id && id !== figure.parts.model?.root && figure.parts.typeOf(id));
  const parts = () => { const figure = opened(); return figure ? figure.parts.selected.filter((id) => isPart(figure, id)).map((part) => ({ region: figure.region, index: figure.index, part })) : []; };
  // The objects chosen: several together, else the one chosen -- or the figure's shapes chosen.
  const picks = () => {
    if (opened()) return parts();
    const many = ctx.many();
    if (many.length) return many;
    return state.focus && exists(state.focus) ? [{ region: state.focus.region, index: state.focus.index }] : [];
  };
  function choose(list) {
    const kept = list.filter(exists);
    // A figure's shapes: in it, opened (as a click on one opens it), its shapes chosen.
    if (kept.length && kept[0].part !== undefined) {
      const ids = kept.map((pick) => pick.part), [{ region, index }] = kept;
      const figure = ctx.figure();
      if (figure && samePlace(figure, kept[0])) figure.parts.select(ids, { reveal: false });
      else { ctx.setMany([]); ctx.focusBlock(region, index, () => ctx.figure()?.parts.select(ids, { reveal: false })); }
      return;
    }
    ctx.leave();
    state.focus = null; state.field = null; state.logo = null; state.tab = "slide";
    ctx.setMany(kept.map(({ region, index }) => ({ region, index })));
  }
  // An object's (or a figure's shape's) box on the slide, in the shapes' units, as drawn.
  function box(pick) {
    const drawn = (pick.part !== undefined ? ctx.partElement(pick.part) : ctx.element(pick.region, pick.index))?.getBoundingClientRect();
    if (!drawn || (!drawn.width && !drawn.height)) return null;
    const a = shapes.pointAt(drawn.left, drawn.top), b = shapes.pointAt(drawn.right, drawn.bottom);
    return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
  }
  const figureOf = (list) => (list[0]?.part !== undefined ? ctx.figure() : null);
  // Those chosen taken away, one step, the last of each column first.
  function remove(list, cut) {
    const figure = figureOf(list);
    if (figure) { figure.parts.remove(list.map((pick) => pick.part), [], { cut }); return; }
    const gone = list.filter(exists).sort((a, b) => b.index - a.index);
    if (!gone.length) return;
    ctx.setMany([]);
    ctx.editSlide((slide) => { for (const { region, index } of gone) ctx.blocksAt(slide, region).splice(index, 1); },
      { label: `${cut ? "Cut" : "Delete"} ${gone.length === 1 ? "Object" : `${gone.length} Objects`}` });
  }
  // Each copied after the last of those chosen in its column, the copies chosen, one step.
  function duplicate(list) {
    const figure = figureOf(list);
    if (figure) { figure.parts.duplicate(list.map((pick) => pick.part)); return; }
    const chosen = list.filter(exists);
    if (!chosen.length) return;
    const columns = [...new Set(chosen.map((pick) => pick.region))].map((region) => [region, chosen.filter((pick) => pick.region === region).map((pick) => pick.index).sort((a, b) => a - b)]);
    ctx.setMany([]);
    ctx.editSlide((slide) => {
      for (const [region, mine] of columns) { const blocks = ctx.blocksAt(slide, region); blocks.splice(mine.at(-1) + 1, 0, ...mine.map((index) => ctx.copyOf(blocks[index]))); }
    }, { label: `Duplicate ${chosen.length === 1 ? "Object" : `${chosen.length} Objects`}` });
    choose(columns.flatMap(([region, mine]) => mine.map((_, n) => ({ region, index: mine.at(-1) + 1 + n }))));
  }
  function clip() {
    const figure = opened();
    if (figure) {
      const copied = figure.parts.clip();
      return copied ? { what: "parts", parts: copied, label: copied.top.length > 1 ? `${copied.top.length} shapes` : "shape" } : null;
    }
    const blocks = picks().map((pick) => structuredClone(blocksOn(pick.region)[pick.index]));
    if (!blocks.length) return null;
    return blocks.length === 1 ? { what: "block", block: blocks[0], label: ctx.blockName(blocks[0]).toLowerCase() } : { what: "blocks", blocks, label: `${blocks.length} objects` };
  }

  const mixed = mixedChoice({
    studio, shapes, noun: "slide",
    words: () => (opened() ? ["Figure Shape", "Shape"] : ["Object", "Shape"]),
    own: {
      picks,
      name: (pick) => (pick.part !== undefined ? ctx.figure()?.parts.nameOf(pick.part) || "Shape" : ctx.blockName(blocksOn(pick.region)[pick.index])),
      box,
      at: (event) => {
        const figure = opened();
        if (figure) { const id = ctx.inFigure(event) ? figure.parts.idAt(event) : null; return id && figure.parts.selected.includes(id) ? { region: figure.region, index: figure.index, part: id } : null; }
        const part = ctx.partAt(event);
        return part?.kind === "block" && picks().some((pick) => samePlace(pick, part)) ? { region: part.region, index: part.index } : null;
      },
      choose,
      // (One left alone: an object chosen as it is alone; a figure's shape stays chosen in it.)
      alone: () => { const [one] = picks(); if (!one || one.part !== undefined) return; ctx.setMany([]); ctx.focusBlock(one.region, one.index); },
      remove, duplicate, clip,
      // (Pasted as a copy of objects is: after those chosen, the copies chosen; a figure's
      // shapes into the figure being edited, else as a figure of their own.)
      paste: (clipped) => ctx.pasteClip(clipped),
      accepts: (clipped) => ["block", "blocks", "parts"].includes(clipped?.what),
      count: (clipped) => (clipped.what === "blocks" ? clipped.blocks.length : clipped.what === "parts" && opened() ? clipped.parts.top.length : 1),
      all: () => {
        const figure = opened();
        if (figure) return (figure.parts.groupOf(figure.parts.model?.root)?.children || []).filter((id) => isPart(figure, id)).map((part) => ({ region: figure.region, index: figure.index, part }));
        return ctx.regionsOf(ctx.slideAt() || {}).flatMap((region) => blocksOn(region.key).map((_, index) => ({ region: region.key, index })));
      },
      settled: () => ctx.figure()?.parts.idle?.(),
      // The slide's objects move with the shapes (placing.js): never a figure's shapes, which
      // the figure lays out.
      movable: (pick) => pick.part === undefined && Boolean(ctx.placing),
      locked: (pick) => pick.part === undefined && Boolean(ctx.placing?.locked(pick)),
      move: (moves, label, shapesChange) => Boolean(ctx.placing?.moveWith(moves, label, shapesChange)),
      show: (moves) => ctx.placing?.showMoves(moves),
      nudge: (event) => (opened() ? false : Boolean(ctx.placing?.nudge(event, { drawn: shapes.chosen().filter((index) => !shapes.lockedAt(index)) }))),
    },
    page: () => state.slide, goTo: (index) => ctx.select(index),
    // (The editor's own on their right-click menu: Show ▸.)
    menuItems: (point) => ctx.menuItems?.(point) || [],
    render: () => ctx.render(), crumb: () => ctx.crumb(), frame: () => ctx.frame(),
    clipChosen: (cut) => ctx.clipChosen(cut), clipItems: () => ctx.clipItems(),
    undoNote: (text, options) => ctx.undoNote(text, options), away: (what) => ctx.away(what), showPanel: () => ctx.showPanel(),
  });

  // Pressed with ⇧ or ⌘: a shape, objects (or a figure's shapes) chosen; or an object, shapes
  // chosen -- put in or taken out, the rest kept. (Chosen as it is pressed, the click its
  // release makes is none.) A figure's shape, the figure open: its own ⇧-click, the shapes kept.
  function press(event) {
    if (!(event.shiftKey || event.metaKey) || event.button !== 0 || shapes.armed()) return false;
    if (mixed.pressShape(event)) { event.shapes = true; return true; }
    if (shapes.at(event) !== null || !shapes.any()) return false;
    if (opened() && ctx.inFigure(event)) return false;
    const part = ctx.partAt(event);
    if (part?.kind !== "block") return false;
    // (Another object, a figure's shapes chosen: the figure chosen whole with it, and the shapes
    // -- as ⇧-click on another object chooses the figure whole when no shape is chosen. Its
    // shapes are edited in it, through its own edits, where it is on the slide: chosen with the
    // slide's other objects, a change of all of them would move it under its own edits. Said.)
    const open = opened();
    if (open) {
      mixed.together(() => choose([{ region: open.region, index: open.index }]));
      toast(WHOLE, { icon: "figure", seconds: 5 });
    }
    mixed.pickOwn({ region: part.region, index: part.index }, samePick);
    ctx.swallowRelease(true);
    event.shapes = true;
    return true;
  }
  // A press that keeps both: on a shape chosen with them (a drag of the shapes).
  const keeps = (event) => mixed.on() && shapes.chosen().includes(shapes.at(event));
  // A band across the slide: what it touches of both, with ⇧ those chosen as it began.
  function band(objects, indices, keep) {
    const all = [...keep.objects, ...objects.filter((at) => !keep.objects.some((kept) => samePlace(kept, at)))];
    const drawn = [...new Set([...keep.shapes, ...indices])];
    return mixed.band(all, drawn);
  }
  return { ...mixed, press, keeps, band };
}

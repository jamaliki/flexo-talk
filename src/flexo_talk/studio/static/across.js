// Across slides: a deck's slides seen, caught at and lined up one with the next -- for a
// visualisation that changes a little from slide to slide, whose parts that stay the same
// must not jump. What the deck's editor (editor.js) needs.
//
// - Show Neighbouring Slides (View, the palette, a toggle in the zoom bar): the slide before
//   drawn faintly on the one shown -- and, with Include Next Slide (the toggle beside it), the
//   one after too, in another tint -- in the studio alone, never presented or exported. The
//   slides either side that are presented: a skipped one is passed over. One setting for the
//   person, kept in this browser, as the magnet is (snapping.js).
// - Caught at: a shape or a placed object dragged, sized or nudged catches at the edges and
//   middles of what is on the slides either side, as at the slide's own -- with the magnet, ⌘
//   the other way -- its guide in a colour of its own, the box it caught at outlined (beside.js),
//   whether they are shown or not.
// - Match on Other Slides…: what is chosen (a shape, a group, a placed object, a picture, a
//   figure) put where it is, as large, on the next slide, the one before, every slide of its run
//   (those either side that each have its match) or the slides chosen in the list -- its match
//   on each found as matching.js says, a slide with none passed over and said; one step. A
//   figure and its matches are put in one frame, drawn at one scale (flexo_talk.framing).
// - A figure's Frame, in its panel: the frame it is drawn in with others, chosen or left.
//
// `ctx` is the editor's: studio, pages() (each slide's drawing: { svg, hash }), slides(),
// index() (the slide shown), pageNode(), frame() and scale() (the slide in the shapes' units, and
// its points in one of them), regions(slide) and blocksAt(slide, region), kindOf(block),
// blockName(block), objects() (the objects chosen: [{ region, index }]), objectFrame(pick) (where
// one stands, in the shapes' units), element(region, index), shapes (the slide's shapes' editor),
// chosenSlides(), figures() (the deck's own), away(what), undoNote(text, options), render().

import { h, ui, icon, toast, menu } from "/static/studio/studio.js";
import * as F from "/static/studio/freeform.js";
import * as P from "/static/kinds/deck/places.js";
import * as M from "/static/kinds/deck/matching.js";

const KEY = "flexo-studio-neighbours";
const read = () => { try { return globalThis.localStorage?.getItem?.(KEY) || "off"; } catch { return "off"; } };
const write = (value) => { try { globalThis.localStorage?.setItem?.(KEY, value); } catch { /* this window's alone */ } };
const SHOWN = ["off", "before", "both"];
// (Each object and shape a slide draws, by its id: slide4.right.0, slide4.shapes.2.)
const DRAWN = /^slide\d+\.(?:body|left|right|column\d+|shapes)\.\d+$/;
const STYLE = ":host{display:block}svg{display:block;width:100%;height:100%;text-rendering:geometricPrecision}"
  // Its own page left out, and what an editor alone sees of it: only what it draws, faintly.
  + "[id='layer.background']{display:none}[data-flexo-placeholder]{display:none}[data-flexo-show=hidden]{visibility:hidden}";

// Two slides, one over the other, the one behind dashed: the slides either side, faintly.
function neighboursIcon() {
  const node = icon("slide");
  node.replaceChildren();
  const S = (name, attributes) => { const item = document.createElementNS("http://www.w3.org/2000/svg", name); for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, value); return item; };
  node.append(S("path", { d: "M5.5 3.5h8v6h-8z", "stroke-dasharray": "1.6 1.4" }), S("path", { d: "M2.5 6.5h8v6h-8z", fill: "var(--raised, #fff)" }));
  return node;
}

export function acrossSlides(ctx) {
  const { studio } = ctx;
  if (!document.querySelector('link[href="/static/kinds/deck/across.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/across.css" }));
  }
  let shown = SHOWN.includes(read()) ? read() : "off";
  const listeners = new Set();
  const on = () => shown !== "off";
  const withNext = () => shown === "both";

  // -- the slides either side --

  // The presented slide before (`way` -1) or after (1) the one shown, if any.
  function neighbour(way) {
    const list = ctx.slides();
    for (let at = ctx.index() + way; at >= 0 && at < list.length; at += way) if (list[at]?.skip !== true) return at;
    return null;
  }
  // Each neighbour's drawing in a page of its own (a shadow root, its ids and styles its own),
  // made once for each drawing (by its hash): the few lately seen kept.
  const made = new Map();
  function drawingOf(page) {
    if (!page?.svg || !page.hash) return null;
    let one = made.get(page.hash);
    if (one) { made.delete(page.hash); made.set(page.hash, one); return one; }
    const node = h("div.onion", { "aria-hidden": "true" });
    const root = node.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE;
    const holder = document.createElement("template");
    holder.innerHTML = page.svg.replace(/^<\?xml[^>]*>\s*/, "");
    const svg = holder.content.querySelector("svg");
    if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); svg.setAttribute("preserveAspectRatio", "xMidYMid meet"); }
    for (const link of holder.content.querySelectorAll("a")) { link.removeAttribute("href"); link.removeAttributeNS("http://www.w3.org/1999/xlink", "href"); }
    root.append(style, holder.content);
    one = { node, hash: page.hash, boxes: null };
    made.set(page.hash, one);
    for (const [hash, old] of made) { if (made.size <= 6) break; if (!old.node.isConnected) made.delete(hash); }
    return one;
  }
  // Those shown now, before and after, put on the slide (under its frames and handles, over its
  // drawing), each faint or kept out of sight -- there all the same, to be caught at.
  let laid = { before: null, after: null, key: "" };
  function lay({ now = on() } = {}) {
    const page = ctx.pageNode(), svg = page?.querySelector(":scope > svg");
    if (!svg) return;
    const pages = ctx.pages(), before = neighbour(-1), after = neighbour(1);
    const key = `${before}:${pages[before]?.hash}:${after}:${pages[after]?.hash}`;
    if (key !== laid.key) {
      // (Made when first needed -- shown, or caught at -- else a moment after the slide is drawn.)
      if (!now) { schedule(); return; }
      laid = { before: before === null ? null : drawingOf(pages[before]), after: after === null ? null : drawingOf(pages[after]), key };
    }
    for (const old of page.querySelectorAll(":scope > .onion")) if (old !== laid.before?.node && old !== laid.after?.node) old.remove();
    // A dark slide's faint copy lightens it; a light one's darkens it, as ink under it would.
    const dark = lightness(page.style.background || "") < 0.45;
    let last = svg;
    for (const [one, side] of [[laid.before, "before"], [laid.after, "after"]]) {
      if (!one) continue;
      if (last.nextElementSibling !== one.node) last.after(one.node);
      last = one.node;
      one.node.className = `onion ${side}${dark ? " dark" : ""}${(side === "before" ? on() : withNext()) ? " shown" : ""}`;
    }
  }
  let waiting = 0;
  function schedule() {
    if (waiting) return;
    const later = globalThis.requestIdleCallback || ((then) => setTimeout(then, 200));
    waiting = later(() => { waiting = 0; lay({ now: true }); }, { timeout: 600 });
  }
  const lightness = (colour) => {
    const found = /#([0-9a-f]{6})/i.exec(colour) || null;
    const rgb = found ? [0, 2, 4].map((at) => parseInt(found[1].slice(at, at + 2), 16) / 255) : (/rgb\(([^)]+)\)/.exec(colour)?.[1].split(",").map((value) => Number(value) / 255));
    return rgb && rgb.length >= 3 ? 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] : 1;
  };

  // What each neighbour draws -- its objects' and shapes' boxes, [left, top, right, bottom] in
  // the shapes' units -- measured once for each drawing.
  function boxesOf(one) {
    if (!one) return [];
    if (one.boxes) return one.boxes;
    const svg = one.node.shadowRoot?.querySelector("svg"), matrix = svg?.getScreenCTM?.();
    if (!svg || !matrix || !one.node.isConnected) return [];
    const back = matrix.inverse(), k = ctx.scale() || 1, boxes = [];
    for (const element of svg.querySelectorAll("[id]")) {
      if (!DRAWN.test(element.id) || element.closest("[data-flexo-placeholder]")) continue;
      const rect = element.getBoundingClientRect();
      if (!rect.width && !rect.height) continue;
      const a = new DOMPoint(rect.left, rect.top).matrixTransform(back), b = new DOMPoint(rect.right, rect.bottom).matrixTransform(back);
      boxes.push([a.x / k, a.y / k, b.x / k, b.y / k].map((value) => Math.round(value * 100) / 100));
    }
    one.boxes = boxes;
    return boxes;
  }
  // What a drag catches at beside the slide (beside.js): what is on the slides either side.
  function beside() {
    lay({ now: true });
    const boxes = [...boxesOf(laid.before), ...boxesOf(laid.after)];
    return boxes.length ? { boxes } : null;
  }

  // -- shown, or not --

  function set(value) {
    if (!SHOWN.includes(value) || value === shown) return;
    shown = value;
    write(value);
    lay({ now: true });
    for (const listener of listeners) listener();
  }
  const toggle = () => set(on() ? "off" : withNext() ? "both" : "before");
  // (Include Next Slide is the toggle's own: turned on, the slides either side are shown.)
  const toggleNext = () => set(withNext() ? "before" : "both");
  // Turned in another tab of this browser: here too.
  window.addEventListener("storage", (event) => { if (event.key === KEY) { shown = SHOWN.includes(read()) ? read() : "off"; lay({ now: true }); for (const listener of listeners) listener(); } });

  // The zoom bar's toggles: the slides either side, and with them the next.
  function zoomButtons() {
    const button = h("button.btn.ghost.small.icon.neighbours", { type: "button", onclick: () => toggle() }, neighboursIcon());
    const next = h("button.btn.ghost.small.neighbours-next", { type: "button", onclick: () => toggleNext() }, "Next");
    const show = () => {
      button.classList.toggle("on", on());
      button.setAttribute("aria-pressed", String(on()));
      button.title = on() ? "Hide Neighbouring Slides" : "Show Neighbouring Slides";
      button.setAttribute("aria-label", button.title);
      next.hidden = !on();
      next.classList.toggle("on", withNext());
      next.setAttribute("aria-pressed", String(withNext()));
      next.title = withNext() ? "Leave Out Next Slide" : "Include Next Slide";
    };
    for (const one of [button, next]) one.addEventListener("mousedown", (event) => event.preventDefault());
    listeners.add(show);
    show();
    return [h("span.zoom-sep"), button, next];
  }

  // -- Match on Other Slides --

  const shapeList = (slide) => (Array.isArray(slide?.shapes) ? slide.shapes : []);
  const groupBounds = (spec) => {
    if (spec?.kind === "group") {
      const all = (spec.shapes || []).map(groupBounds).filter(Boolean);
      return all.length ? [Math.min(...all.map((b) => b[0])), Math.min(...all.map((b) => b[1])), Math.max(...all.map((b) => b[2])), Math.max(...all.map((b) => b[3]))] : null;
    }
    try { return F.bounds(F.normalised(spec)); } catch { return null; }
  };
  // What is chosen that has a place to copy: the objects chosen, the shapes chosen.
  function chosenNow() {
    const slide = ctx.slides()[ctx.index()];
    const objects = ctx.objects().filter((pick) => ctx.blocksAt(slide, pick.region)[pick.index] !== undefined);
    const shapes = ctx.shapes.chosen().filter((index) => shapeList(slide)[index]);
    return { objects, shapes, count: objects.length + shapes.length };
  }
  const named = (picks) => {
    const slide = ctx.slides()[ctx.index()];
    if (picks.count > 1) return `${picks.count} Objects`;
    if (picks.objects.length) return ctx.blockName(ctx.blocksAt(slide, picks.objects[0].region)[picks.objects[0].index]);
    const spec = shapeList(slide)[picks.shapes[0]];
    return spec?.kind === "group" ? "Group" : F.LABELS[spec?.kind] || "Shape";
  };
  // Each chosen with where it stands now and its match on `slide` (the document's), or why none.
  function matches(picks, target, document = studio.doc) {
    const here = document.slides?.[ctx.index()], slide = document.slides?.[target];
    const options = { regions: ctx.regions, blocksAt: ctx.blocksAt, figures: document.figures || {} };
    return [
      ...picks.objects.map((pick) => {
        const block = ctx.blocksAt(here, pick.region)[pick.index];
        const found = slide ? M.matchObject(block, pick, slide, options) : { why: "no such slide" };
        const there = found.why ? null : ctx.blocksAt(slide, found.region)[found.index];
        return { what: "object", pick, block, found: there?.locked ? { why: "its match is locked" } : found };
      }),
      ...picks.shapes.map((index) => {
        const spec = shapeList(here)[index];
        const found = slide ? M.matchShape(spec, index, shapeList(slide)) : { why: "no such slide" };
        return { what: "shape", index, spec, found: !found.why && shapeList(slide)[found.index]?.locked ? { why: "its match is locked" } : found };
      }),
    ];
  }
  const matchesOn = (picks, target) => matches(picks, target).some((one) => !one.found.why);
  // The slides each way chosen could go: next, previous, its run, those chosen in the list.
  function targets(picks) {
    const count = ctx.slides().length, here = ctx.index();
    const next = here + 1 < count ? here + 1 : null, previous = here > 0 ? here - 1 : null;
    const [first, last] = M.runOf(count, here, (index) => matchesOn(picks, index));
    const run = Array.from({ length: last - first + 1 }, (_, n) => first + n).filter((index) => index !== here);
    const listed = ctx.chosenSlides().filter((index) => index !== here);
    return { next, previous, run, listed };
  }
  // Why a slide has no match for what is chosen, said short.
  const whyNot = (picks, index) => matches(picks, index).find((one) => one.found.why)?.found.why || "";

  // Put each of `picks` where it is now on each of `indices`: one step. What was done, said.
  function matchOn(indices, picks = chosenNow()) {
    if (!indices.length || !picks.count || ctx.away("match objects on other slides")) return false;
    const here = ctx.index(), document = studio.doc;
    const herePlace = document.slides[here];
    const sources = matches(picks, here);
    // Where each object stands now -- its own place if placed, its frame as drawn else (as the
    // slide says it, in its points: not by way of the screen, a hair off).
    const drawnFrame = (pick) => {
      const values = String(ctx.element(pick.region, pick.index)?.getAttribute("data-flexo-frame") || "").split(" ").map(Number);
      const k = ctx.scale() || 1;
      return values.length === 4 && values.every(Number.isFinite) ? values.map((value) => value / k) : ctx.objectFrame(pick);
    };
    const frames = new Map(picks.objects.map((pick) => [`${pick.region}:${pick.index}`, M.standing(ctx.blocksAt(herePlace, pick.region)[pick.index], drawnFrame(pick))]));
    if ([...frames.values()].some((frame) => !frame)) { toast("Can’t tell where it stands yet: try again once the slide is drawn", { icon: "info" }); return false; }
    const taken = new Set((document.slides || []).flatMap((slide) => ctx.regions(slide).flatMap((region) => ctx.blocksAt(slide, region).map((block) => block?.frame).filter(Boolean))));
    const names = new Map();
    for (const source of sources) {
      if (source.what !== "object" || ctx.kindOf(source.block) !== "figure") continue;
      const name = source.block.frame || M.frameName(source.block, document.figures || {}, [...taken]);
      taken.add(name);
      names.set(`${source.pick.region}:${source.pick.index}`, name);
    }
    const done = new Set(), passed = new Map();
    const plan = indices.map((index) => ({ index, found: matches(picks, index) }));
    for (const { index, found } of plan) {
      const why = found.find((one) => one.found.why)?.found.why;
      if (found.some((one) => !one.found.why)) done.add(index);
      if (why) passed.set(index, why);
    }
    if (!done.size) {
      toast(`Nothing to match on ${M.slidesSaid(indices)}: ${[...passed.values()][0] || "no match"}`, { icon: "info", seconds: 4 });
      return false;
    }
    const name = named(picks);
    studio.change((d) => {
      const own = d.slides[here];
      for (const source of sources) {
        if (source.what !== "object") continue;
        const key = `${source.pick.region}:${source.pick.index}`, frameName = names.get(key);
        // A figure put in its frame, with its matches -- and, in line, placed where it stands, so
        // that both are drawn the same size.
        if (frameName) {
          const block = ctx.blocksAt(own, source.pick.region)[source.pick.index];
          if (block && typeof block === "object") {
            if (!P.placed(block)) M.placedAs(block, frames.get(key), "figure");
            block.frame = frameName;
          }
        }
      }
      for (const { index, found } of plan) {
        const slide = d.slides[index];
        if (!slide) continue;
        for (const one of found) {
          if (one.found.why) continue;
          if (one.what === "shape") {
            const list = shapeList(slide);
            list[one.found.index] = M.shapeAs(list[one.found.index], one.spec, { bounds: groupBounds, mapped: F.mapped, family: F.family });
            continue;
          }
          const blocks = ctx.blocksAt(slide, one.found.region);
          if (typeof blocks[one.found.index] === "string") blocks[one.found.index] = { text: blocks[one.found.index] };
          const target = blocks[one.found.index], key = `${one.pick.region}:${one.pick.index}`;
          M.placedAs(target, frames.get(key), ctx.kindOf(one.block), { name: names.get(key) });
        }
      }
    }, { label: `Match ${name} on ${M.slidesSaid([...done])}` });
    const skipped = [...passed.keys()];
    ctx.undoNote(`Matched on ${M.slidesSaid([...done])}${skipped.length ? ` · ${M.slidesSaid(skipped)} passed over: ${passed.get(skipped[0])}` : ""}`, { icon: "arrange", seconds: skipped.length ? 7 : 5 });
    ctx.render();
    return true;
  }

  // Where to open the choice of slides: the last menu's place, else over what is chosen.
  let pointed = null;
  document.addEventListener("contextmenu", (event) => { pointed = { x: event.clientX, y: event.clientY, at: Date.now() }; }, true);
  function anchor(picks) {
    if (pointed && Date.now() - pointed.at < 30000 && document.querySelector(".menu") === null) {
      const slide = ctx.pageNode()?.getBoundingClientRect();
      if (slide && pointed.x >= slide.left && pointed.x <= slide.right && pointed.y >= slide.top && pointed.y <= slide.bottom) return { x: pointed.x, y: pointed.y };
    }
    const element = picks.objects.length ? ctx.element(picks.objects[0].region, picks.objects[0].index)
      : ctx.pageNode()?.querySelector(`[id="slide${ctx.index() + 1}.shapes.${picks.shapes[0]}"]`);
    const box = (element || ctx.pageNode())?.getBoundingClientRect();
    return box ? { x: box.left + box.width / 2, y: box.top + Math.min(box.height / 2, 40) } : { x: innerWidth / 2, y: innerHeight / 2 };
  }
  // The slides to match on, to choose from: each with the slides it means, or why it can't be.
  function chooser(where = null) {
    const picks = chosenNow();
    if (!picks.count) return;
    const ways = targets(picks);
    const item = (label, indices, none) => {
      const ok = indices.length && indices.some((index) => matchesOn(picks, index));
      const why = indices.length === 1 && !ok ? `${M.slidesSaid(indices)} has ${whyNot(picks, indices[0])}` : none;
      return { icon: "arrange", label: indices.length > 1 && ok ? `${label} · ${M.slidesSaid(indices)}` : label, hint: ok ? M.slidesSaid(indices) : why, disabled: !ok, run: () => matchOn(indices, picks) };
    };
    menu(where || anchor(picks), [
      { title: `Match ${named(picks)} On` },
      item("Next Slide", ways.next === null ? [] : [ways.next], "No slide after this one"),
      item("Previous Slide", ways.previous === null ? [] : [ways.previous], "No slide before this one"),
      item("This Run", ways.run, "The slides either side have no match"),
      item("Slides Chosen in the List", ways.listed, "⌘-click or ⇧-click slides in the list to choose them"),
    ]);
  }
  const LABEL = "Match on Other Slides…";
  // For the palette and the Mac app's Arrange menu: the choice, and each way of it that matches.
  function matching(picks, own = false) {
    if (!picks.count) return [];
    const ways = targets(picks);
    return [
      { icon: "arrange", label: LABEL, hint: named(picks), ...(own ? { menu: true } : {}), run: () => chooser() },
      ...[["Match on Next Slide", "next"], ["Match on Previous Slide", "previous"], ["Match on This Run", "run"]].flatMap(([label, way]) => {
        const indices = way === "run" ? ways.run : ways[way] === null ? [] : [ways[way]];
        return indices.length && indices.some((index) => matchesOn(picks, index)) ? [{ icon: "arrange", label, hint: `${named(picks)} on ${M.slidesSaid(indices)}`, run: () => matchOn(indices, picks) }] : [];
      }),
    ];
  }
  // Objects chosen (shapes with them or not): the editor's. Shapes alone: the shapes' editor's,
  // the first in their right-click menu too (shapes.js's `menu`).
  const commands = () => { const picks = chosenNow(); return picks.objects.length ? matching(picks) : []; };
  const shapeCommands = () => { const picks = chosenNow(); return picks.objects.length ? [] : matching(picks, true); };
  const menuItem = () => (chosenNow().count ? { icon: "arrange", label: LABEL, run: () => chooser() } : null);
  // The Arrange tab's section: the button, with what is chosen.
  function section() {
    const picks = chosenNow();
    if (!picks.count) return null;
    const button = ui.button(LABEL, (event) => { const box = event.currentTarget.getBoundingClientRect(); chooser({ x: box.left, y: box.bottom + 4 }); }, { small: true, icon: "arrange" });
    return h("div.section.across", {}, h("div.section-title", {}, "Other Slides"), h("div.row", {}, button));
  }

  // -- a figure's frame --

  // The frames of the deck, by name, with how many slides draw each.
  function frames() {
    const found = new Map();
    (studio.doc.slides || []).forEach((slide, index) => {
      for (const region of ctx.regions(slide)) for (const block of ctx.blocksAt(slide, region)) {
        if (block && typeof block === "object" && typeof block.frame === "string" && block.frame) found.set(block.frame, new Set([...(found.get(block.frame) || []), index]));
      }
    });
    return found;
  }
  // Its panel's Frame: None, a frame of the deck's (with the slides it is on), or a new one.
  function frameField(block, at, edit) {
    const all = frames(), now = typeof block?.frame === "string" ? block.frame : "";
    const NEW = "\u0000new";
    const options = [{ value: "", label: "None" }, ...[...all.keys()].sort().map((name) => ({ value: name, label: `${name} · ${M.slidesSaid([...all.get(name)])}` })), "-", { value: NEW, label: "New Frame" }]
      .map((option) => (option === "-" ? { line: true } : option));
    return ui.field("Frame", ui.select({ value: now, options, key: "figure.frame", onChange: (value) => {
      const name = value === NEW ? M.frameName(block, studio.doc.figures || {}, [...all.keys()]) : value;
      edit((b) => { if (name) b.frame = name; else delete b.frame; }, name ? `Draw in Frame ${name}` : "Draw in No Frame");
    } }));
  }

  // The slide drawn again (another slide shown, or its drawing come): its neighbours with it.
  function drawn() { lay(); }
  studio.on?.("drawn", () => requestAnimationFrame(() => lay()));

  return {
    drawn, beside, zoomButtons, toggle, toggleNext, shown: on, withNext, commands, shapeCommands, menuItem, section, frameField,
    chooser, matchOn, targets: () => targets(chosenNow()),
    viewCommands: () => [
      // (Each one command named for what it will do, as Show Speaker Notes is.)
      { icon: "slide", label: on() ? "Hide Neighbouring Slides" : "Show Neighbouring Slides", run: () => toggle() },
      { icon: "slide", label: withNext() ? "Leave Out Next Slide" : "Include Next Slide", run: () => toggleNext() },
    ],
  };
}

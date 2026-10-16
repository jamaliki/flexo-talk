// Across slides: a deck's slides overlaid, caught at and lined up one with the next -- for a
// visualisation that changes a little from slide to slide, whose parts that stay the same
// must not jump. What the deck's editor (editor.js) needs.
//
// - Overlay Slides (O; the slide list's right-click, the palette, View, the toggle in the zoom
//   bar -- each again: Stop Overlaying): the slides chosen in the list drawn over the one shown
//   -- or, one chosen, the presented slides either side of it, following it as it changes --
//   each a ghost in a tint of its own, under its frames and handles, in the studio alone:
//   never presented or exported (overlaying.js says which, and how). The zoom bar keys them,
//   each a chip in its tint (clicked: that slide); the list marks each with a stripe in its
//   tint. Page Up and Page Down go from one overlaid slide to the next. Going to a slide out of
//   a set chosen stops it, as Esc does when it has nothing else to do. Kept for the person, in
//   this browser: the slides either side, overlaid as a deck opens, or not.
// - Caught at: a shape or a placed object dragged, sized or nudged while slides are overlaid
//   catches at the edges and middles of what is on each, as at the slide's own -- with the
//   magnet, ⌘ the other way; the grid's lines alone while it snaps to the grid -- its guide in
//   the ghost's tint, the box it caught at outlined (beside.js).
// - Pointed at: where nothing of the slide shown is under the pointer, an object of a ghost is
//   outlined, dashed, in its tint, its slide named; clicked, that slide is shown and the object
//   chosen on it, the overlay kept.
// - Match on Other Slides…: what is chosen (a shape, a group, a placed object, a picture, a
//   figure) put where it is, as large, on the next slide, the one before, every slide of its run
//   (those either side that each have its match) or the slides chosen in the list -- its match
//   on each found as matching.js says, a slide with none passed over and said; one step. A
//   figure and its matches are put in one frame, drawn at one scale (flexo_talk.framing). While
//   slides are overlaid, Match on Overlaid Slides does so on each of them, the first of the
//   chosen's right-click menu.
// - A figure's Frame, in its panel: the frame it is drawn in with others, chosen or left.
//
// `ctx` is the editor's: studio, pages() (each slide's drawing: { svg, hash }), slides(),
// index() (the slide shown), pageNode(), frame() and scale() (the slide in the shapes' units, and
// its points in one of them), regions(slide) and blocksAt(slide, region), kindOf(block),
// blockName(block), objects() (the objects chosen: [{ region, index }]), objectFrame(pick) (where
// one stands, in the shapes' units), element(region, index), shapes (the slide's shapes' editor),
// chosenSlides(), figures() (the deck's own), away(what), undoNote(text, options), render(),
// go(index) (that slide shown), goTo(index, { region, index } | { shape }) (shown, and that
// chosen on it), rail() (the slide list).

import { h, ui, icon, toast, menu } from "/static/studio/studio.js";
import { pagesKey } from "/static/studio/magnet.js";
import * as F from "/static/studio/freeform.js";
import * as P from "/static/kinds/deck/places.js";
import * as M from "/static/kinds/deck/matching.js";
import * as O from "/static/kinds/deck/overlaying.js";

// (Each object and shape a slide draws, by its id: slide4.right.0, slide4.shapes.2.)
const DRAWN = /^slide\d+\.(body|left|right|column\d+|shapes)\.(\d+)$/;
// A ghost's own page: white (on a dark slide, black) under its drawing in greys, its tint laid
// over that -- screened, so ink takes the tint and white stays white (multiplied, on a dark
// slide: light ink the light tint, black black) -- the whole then multiplied onto the slide
// (screened, on a dark one), as ink under it would be. No more than CSS: no filter to find by
// its id in a shadow root. Its own page left out, and what an editor alone sees of it.
// A picture keeps its own colours whatever the slide's, its white page and all: on a dark slide
// its ghost is drawn apart (`pictures`), as on a light one -- screened with the rest, its white
// would wash out the slide's own picture under it.
const STYLE = ":host{display:block;background:#fff}:host(.dark){background:#000}"
  + "svg{display:block;width:100%;height:100%;text-rendering:geometricPrecision;filter:grayscale(1)}"
  + ".tint{position:absolute;inset:0;background:var(--tint);mix-blend-mode:screen}:host(.dark) .tint{background:var(--tint-light);mix-blend-mode:multiply}"
  + ":host(.pictures) svg{visibility:hidden}"
  + "[id='layer.background']{display:none}[data-flexo-placeholder]{display:none}[data-flexo-show=hidden]{visibility:hidden}";
const KEPT = 6;  // drawings kept made, out of sight, for slides lately overlaid
const OVERLAY = "Overlay Slides", STOP = "Stop Overlaying", MATCH = "Match on Overlaid Slides";

export function acrossSlides(ctx) {
  const { studio } = ctx;
  if (!document.querySelector('link[href="/static/kinds/deck/across.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/across.css" }));
  }
  const listeners = new Set();
  // Off (null), the slides either side ({ set: null }), or a set chosen ({ set: [indices] }).
  let overlay = O.keptOverlay() === "on" ? { set: null } : null;
  const on = () => overlay !== null;

  // -- which slides --

  // The slides overlaid now, the one shown among them, and each ghost's tint -- or null, off.
  function now() {
    if (!overlay) return null;
    const here = ctx.index(), overlaid = O.overlaidOf(ctx.slides(), here, overlay.set);
    if (!overlaid) return null;
    return { here, overlaid, ghosts: overlaid.filter((index) => index !== here), tints: O.tintsOf(overlaid, here) };
  }
  // What a press of O (or Overlay Slides) does: the slides chosen in the list overlaid -- they
  // differing from those overlaid, or none -- else it stops.
  const chosenSet = () => O.setOf(ctx.chosenSlides(), ctx.slides().length);
  const stops = () => on() && !(chosenSet() && chosenSet().join() !== (overlay.set || []).join());
  const label = () => (stops() ? STOP : OVERLAY);

  function start() {
    const set = chosenSet();
    overlay = { set: set && set.includes(ctx.index()) ? set : null };
    // (The slides either side are kept for next time; a set is this deck's, now.)
    if (!overlay.set) O.keepOverlay("on");
    changed();
  }
  function stop() {
    if (!overlay) return;
    overlay = null;
    O.keepOverlay("off");
    changed();
  }
  const toggle = () => (stops() ? stop() : start());
  function changed() {
    lay();
    for (const listener of listeners) listener();
    // (What can be done now is said again: the Mac app's View item, the help bar, Arrange's.)
    ctx.render?.();
  }

  // -- the ghosts --

  // Each ghost's drawing in a page of its own (a shadow root, its ids and styles its own), made
  // once for each drawing (by its hash); those lately overlaid kept, out of sight.
  const made = new Map();
  function ghostNode(svgText, own = "") {
    const node = h("div.onion", { "aria-hidden": "true" });
    const root = node.attachShadow({ mode: "open" });
    const style = document.createElement("style");
    style.textContent = STYLE + own;
    const holder = document.createElement("template");
    holder.innerHTML = svgText.replace(/^<\?xml[^>]*>\s*/, "");
    const svg = holder.content.querySelector("svg");
    if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); svg.setAttribute("preserveAspectRatio", "xMidYMid meet"); }
    for (const link of holder.content.querySelectorAll("a")) { link.removeAttribute("href"); link.removeAttributeNS("http://www.w3.org/1999/xlink", "href"); }
    root.append(style, holder.content, h("div.tint"));
    return node;
  }
  function drawingOf(page) {
    if (!page?.svg || !page.hash) return null;
    let one = made.get(page.hash);
    if (one) { made.delete(page.hash); made.set(page.hash, one); return one; }
    one = { node: ghostNode(page.svg), svg: page.svg, hash: page.hash, found: null, look: "", pictures: undefined };
    made.set(page.hash, one);
    return one;
  }
  // Its pictures alone, for a dark slide -- the slide's pictures (drawn inline, an SVG's, or as
  // an image) and any image else -- left out of the rest: made when first needed (none, null).
  const drawnAs = (key) => (key.startsWith("columns.") ? `column${Number(key.split(".")[1]) + 1}` : key);
  function picturesOf(one, index) {
    if (one.pictures !== undefined) return one.pictures;
    const slide = ctx.slides()[index];
    const ids = slide ? ctx.regions(slide).flatMap((key) => ctx.blocksAt(slide, key).flatMap((block, n) => (ctx.kindOf(block) === "image" ? [`slide${index + 1}.${drawnAs(key)}.${n}`] : []))) : [];
    if (!ids.length && !one.node.shadowRoot.querySelector("image")) return (one.pictures = null);
    const chosen = ["image", ...ids.map((id) => `[id="${id}"]`)].join(",");
    one.node.shadowRoot.append(h("style", {}, `:host(.dark) :is(${chosen}){visibility:hidden}`));
    return (one.pictures = ghostNode(one.svg, `:host(.pictures) :is(${chosen}){visibility:visible}`));
  }
  // Those overlaid now, put on the slide over its drawing and under its frames and handles, in
  // the deck's order, each in its tint: [{ one, index, tint }].
  let laid = [];
  function lay() {
    const page = ctx.pageNode(), svg = page?.querySelector(":scope > svg");
    let shown = now();
    // Gone to a slide out of the set chosen (or the set gone from the deck): stopped.
    if (overlay && !shown) { overlay = null; O.keepOverlay("off"); for (const listener of listeners) listener(); }
    if (!svg) shown = null;
    if (shown) hook(page);
    const pages = ctx.pages(), dark = O.isDark(page?.style.background || ""), wanted = [];
    for (const index of shown?.ghosts || []) {
      const one = drawingOf(pages[index]);
      if (one && !wanted.some((each) => each.one === one)) wanted.push({ one, index, tint: shown.tints.get(index) });
    }
    const nodes = new Set(wanted.flatMap(({ one, index }) => [one.node, ...(dark && picturesOf(one, index) ? [one.pictures] : [])]));
    for (const old of page?.querySelectorAll(":scope > .onion") || []) if (!nodes.has(old)) old.remove();
    let last = svg;
    for (const { one, index, tint } of wanted) {
      const pictures = dark ? picturesOf(one, index) : null;
      for (const node of [one.node, pictures]) {
        if (!node) continue;
        if (last.nextElementSibling !== node) last.after(node);
        last = node;
      }
      const look = `${index}:${tint.colour}:${tint.opacity}:${dark}`;
      if (one.look === look) continue;
      one.look = look;
      one.node.className = `onion${dark ? " dark" : ""}`;
      if (pictures) pictures.className = "onion pictures";
      for (const node of [one.node, pictures]) {
        if (!node) continue;
        node.style.setProperty("--tint", tint.colour);
        node.style.setProperty("--tint-light", tint.light);
        node.style.opacity = String(tint.opacity);
      }
    }
    laid = wanted.map((each) => ({ ...each, dark }));
    // (The few lately overlaid kept, made, beside those now.)
    for (const [hash, old] of made) { if (made.size <= KEPT + laid.length) break; if (!old.node.isConnected) made.delete(hash); }
    if (!laid.some((each) => each.one === aimed?.one)) unpoint();
    showKey();
    rail();
  }
  // (Each drawing's colour on a dark slide: its light tint, as the ghost shows it.)
  const shownTint = (each) => (each.dark ? each.tint.light : each.tint.colour);

  // What each ghost draws -- its objects' and shapes' boxes, [left, top, right, bottom] in the
  // shapes' units, with which each is -- measured once for each drawing.
  const regionOf = (drawn) => (/^column\d+$/.test(drawn) ? `columns.${Number(drawn.slice(6)) - 1}` : drawn);
  function foundIn(one) {
    if (one.found) return one.found;
    const svg = one.node.shadowRoot?.querySelector("svg"), matrix = svg?.getScreenCTM?.();
    if (!svg || !matrix || !one.node.isConnected) return [];
    const back = matrix.inverse(), k = ctx.scale() || 1, found = [];
    for (const element of svg.querySelectorAll("[id]")) {
      const id = DRAWN.exec(element.id);
      if (!id || element.closest("[data-flexo-placeholder]")) continue;
      const rect = element.getBoundingClientRect();
      if (!rect.width && !rect.height) continue;
      const a = new DOMPoint(rect.left, rect.top).matrixTransform(back), b = new DOMPoint(rect.right, rect.bottom).matrixTransform(back);
      const box = [a.x / k, a.y / k, b.x / k, b.y / k].map((value) => Math.round(value * 100) / 100);
      found.push({ box, what: id[1] === "shapes" ? { shape: Number(id[2]) } : { region: regionOf(id[1]), index: Number(id[2]) } });
    }
    one.found = found;
    return found;
  }
  // What a drag catches at beside the slide (beside.js): what is on each slide overlaid, the
  // nearest first, each box with its ghost's tint for its guide.
  function beside() {
    if (!on()) return null;
    lay();
    const boxes = [];
    for (const each of [...laid].sort((a, b) => a.tint.away - b.tint.away)) {
      for (const { box } of foundIn(each.one)) { box.tint = shownTint(each); boxes.push(box); }
    }
    return boxes.length ? { boxes } : null;
  }

  // -- a ghost's object, pointed at --

  const ring = h("div.ghost-ring", { hidden: true, "aria-hidden": "true" }, h("span.ghost-tag"));
  let aimed = null, claimed = null;
  function unpoint() { aimed = null; ring.hidden = true; }
  // A move the editor did not hand on (something of the slide's under the pointer, a drag, a
  // crop) points at no ghost; nor does the pointer gone from the slide. (Heard after the
  // editor's own, on each slide's page.)
  const hooked = new WeakSet();
  function hook(page) {
    if (!page || hooked.has(page)) return;
    hooked.add(page);
    page.addEventListener("mousemove", (event) => { if (aimed && event !== claimed) unpoint(); });
    page.addEventListener("mouseleave", () => { if (aimed) unpoint(); });
  }
  // The ghost's object under the pointer, if any: the smallest there, the nearest slide's first.
  function ghostAt(event) {
    const svg = ctx.pageNode()?.querySelector(":scope > svg"), matrix = svg?.getScreenCTM?.();
    if (!matrix || !laid.length) return null;
    const k = ctx.scale() || 1, at = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    const x = at.x / k, y = at.y / k, slack = 3 / ((matrix.a || 1) * k);
    let best = null;
    for (const each of laid) {
      for (const found of foundIn(each.one)) {
        const [left, top, right, bottom] = found.box;
        if (x < left - slack || x > right + slack || y < top - slack || y > bottom + slack) continue;
        const area = (right - left) * (bottom - top);
        if (!best || area < best.area - 1e-6 || (Math.abs(area - best.area) <= 1e-6 && each.tint.away < best.each.tint.away)) best = { area, each, found };
      }
    }
    return best;
  }
  // Pointed at where nothing of the slide shown is (the editor asks, else `event` null): the
  // ghost's object there outlined, its slide named. Whether one is.
  function point(event) {
    claimed = event;
    const found = event && on() && !event.buttons ? ghostAt(event) : null;
    if (!found) { if (aimed) unpoint(); return false; }
    if (aimed?.one === found.each.one && aimed.found === found.found) return true;
    aimed = { one: found.each.one, found: found.found, index: found.each.index };
    const page = ctx.pageNode(), matrix = page?.querySelector(":scope > svg")?.getScreenCTM?.();
    if (!matrix) { unpoint(); return false; }
    const k = ctx.scale() || 1, outer = page.getBoundingClientRect(), [left, top, right, bottom] = found.found.box;
    const a = new DOMPoint(left * k, top * k).matrixTransform(matrix), b = new DOMPoint(right * k, bottom * k).matrixTransform(matrix);
    if (ring.parentNode !== page) page.append(ring);
    ring.classList.toggle("dark", found.each.dark);
    ring.style.setProperty("--tint", shownTint(found.each));
    Object.assign(ring.style, { left: `${a.x - outer.left - 3}px`, top: `${a.y - outer.top - 3}px`, width: `${b.x - a.x + 6}px`, height: `${b.y - a.y + 6}px` });
    ring.firstChild.textContent = `Slide ${found.each.index + 1}`;
    ring.hidden = false;
    return true;
  }
  // Clicked there (the editor asks, nothing of the slide shown under it): that slide shown and
  // the object chosen on it, the overlay kept. Whether it was.
  function pick(event) {
    if (!aimed || !on() || event.button !== 0 || event.shiftKey || event.metaKey || event.ctrlKey || event.altKey) return false;
    const found = ghostAt(event);
    if (!found || found.found !== aimed.found) return false;
    unpoint();
    ctx.goTo(found.each.index, found.found.what);
    return true;
  }

  // -- the zoom bar's key, and the list's stripes --

  // Two slides, one over the other, the one behind dashed: slides overlaid.
  const overlayIcon = () => icon("overlay");
  let key = null, keyShown = "";
  function zoomButtons() {
    // (Pressed, it stops, whatever is chosen in the list now: it says it is on.)
    const button = h("button.btn.ghost.small.icon.overlay-toggle", { type: "button", onclick: () => (on() ? stop() : start()) }, overlayIcon());
    key = h("span.overlay-key", { hidden: true });
    // Clicked, a chip leaves the keys where they were, as the zoom bar's buttons do.
    key.addEventListener("mousedown", (event) => event.preventDefault());
    const show = () => {
      button.classList.toggle("on", on());
      button.setAttribute("aria-pressed", String(on()));
      button.title = `${on() ? STOP : OVERLAY} (O)`;
      button.setAttribute("aria-label", on() ? STOP : OVERLAY);
    };
    button.addEventListener("mousedown", (event) => event.preventDefault());
    listeners.add(show);
    show();
    showKey();
    return [h("span.zoom-sep"), button, key];
  }
  // Each slide overlaid, by its number, in its tint (the one shown in ink): clicked, shown.
  function showKey() {
    if (!key) return;
    const shown = now(), tints = shown?.tints;
    const said = shown ? shown.overlaid.map((index) => `${index}:${tints.get(index)?.colour || ""}`).join() + `|${shown.here}` : "";
    if (said === keyShown) return;
    keyShown = said;
    key.hidden = !shown;
    key.replaceChildren(...(shown?.overlaid || []).map((index) => {
      const tint = tints.get(index), solid = index === shown.here;
      const chip = h(`button.overlay-chip${solid ? ".solid" : ""}`, { type: "button", tabindex: -1, title: solid ? `Slide ${index + 1}, Shown` : `Show Slide ${index + 1}`,
        onclick: () => { if (!solid) ctx.go(index); } }, String(index + 1));
      if (tint) { chip.style.setProperty("--tint", tint.colour); chip.style.setProperty("--tint-light", tint.light); }
      return chip;
    }));
  }
  // The list: each ghost's thumbnail marked down its edge in its tint.
  function rail() {
    const list = ctx.rail?.();
    if (!list) return;
    const tints = now()?.tints || new Map();
    for (const thumb of list.querySelectorAll(":scope > .thumb")) {
      const tint = tints.get(Number(thumb.dataset.index));
      let stripe = thumb.querySelector(":scope > .overlay-stripe");
      if (!tint) { stripe?.remove(); continue; }
      if (!stripe) { stripe = h("span.overlay-stripe", { "aria-hidden": "true" }); thumb.append(stripe); }
      if (stripe.dataset.tint !== tint.colour) { stripe.dataset.tint = tint.colour; stripe.style.setProperty("--tint", tint.colour); stripe.style.setProperty("--tint-light", tint.light); }
    }
  }

  // -- the keys --

  // Page Up (`way` -1) and Page Down (1), overlaying: the overlaid slide that way (none, it
  // stays). Whether they were the overlay's.
  function page(way) {
    const shown = now();
    if (!shown) return false;
    const to = O.stepAmong(shown.overlaid, shown.here, way);
    if (to !== null) ctx.go(to);
    return true;
  }
  // Esc with nothing else to do (the editor's last): it stops. Whether it did.
  function escape() {
    if (!on()) return false;
    stop();
    return true;
  }
  // O, while the page has the keys (magnet.js): before an editor's, as % and # are.
  document.addEventListener("keydown", (event) => {
    if (!studio.active || (event.key !== "o" && event.key !== "O") || event.altKey || !pagesKey(event)) return;
    if (document.querySelector(".menu, .popover") || !ctx.slides().length || !ctx.pageNode()?.isConnected) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    toggle();
  });

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
  // -- Match on Overlaid Slides --

  // While slides are overlaid and something is chosen: the command for the slides overlaid but
  // the one shown -- greyed, said why, where none has its match (as a Mac's item is). Else null.
  function overlaidMatch(picks = chosenNow()) {
    const ghosts = now()?.ghosts || [];
    if (!picks.count || !ghosts.length) return null;
    const ok = ghosts.some((index) => matchesOn(picks, index));
    return { icon: "arrange", label: MATCH, hint: ok ? `${named(picks)} on ${M.slidesSaid(ghosts)}` : `${M.slidesSaid(ghosts)}: ${whyNot(picks, ghosts[0]) || "no match"}`,
      disabled: !ok, run: () => matchOn(ghosts, picks) };
  }
  // First in the right-click menu of what is chosen, overlaying: it, and a line.
  const overlaidItems = () => { const item = overlaidMatch(); return item ? [item, "-"] : []; };

  // Objects chosen (shapes with them or not): the editor's. Shapes alone: the shapes' editor's,
  // in their right-click menu too (shapes.js's `menu`; Match on Overlaid Slides, its first).
  const commands = () => {
    const picks = chosenNow();
    return picks.objects.length ? [overlaidMatch(picks), ...matching(picks)].filter(Boolean) : [];
  };
  const shapeCommands = () => {
    const picks = chosenNow(), first = picks.objects.length ? null : overlaidMatch(picks);
    return picks.objects.length ? [] : [...(first ? [{ ...first, menu: "first" }] : []), ...matching(picks, true)];
  };
  const menuItem = () => (chosenNow().count ? { icon: "arrange", label: LABEL, run: () => chooser() } : null);
  // The Arrange tab's section: the buttons, with what is chosen.
  function section() {
    const picks = chosenNow();
    if (!picks.count) return null;
    const button = ui.button(LABEL, (event) => { const box = event.currentTarget.getBoundingClientRect(); chooser({ x: box.left, y: box.bottom + 4 }); }, { small: true, icon: "arrange" });
    const overlaid = overlaidMatch(picks);
    const matched = overlaid ? ui.button(MATCH, () => overlaid.run(), { small: true, icon: "arrange", disabled: overlaid.disabled, title: overlaid.hint }) : null;
    return h("div.section.across", {}, h("div.section-title", {}, "Other Slides"), h("div.row", {}, matched, button));
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

  // The slide drawn again (another slide shown, or its drawing come): the slides overlaid on it.
  function drawn() { lay(); }
  studio.on?.("drawn", () => requestAnimationFrame(() => lay()));
  // (Out of the slide, nothing of a ghost is pointed at; pressed, its outline goes.)
  document.addEventListener("pointerdown", () => { ring.hidden = true; }, true);

  // The overlay toggled: named for what it will do, as Show Speaker Notes is, its key O.
  const overlayCommand = () => ({ icon: "overlay", label: label(), keys: "O", run: () => toggle() });
  return {
    drawn, beside, zoomButtons, toggle, shown: on, commands, shapeCommands, menuItem, section, frameField,
    chooser, matchOn, targets: () => targets(chosenNow()),
    point, pick, page, escape, rail, overlaidItems, leave: () => unpoint(),
    // The slide list's right-click: first, the overlay -- of the slides chosen, or those either side.
    listItems: () => [overlayCommand(), "-"],
    viewCommands: () => [overlayCommand()],
  };
}

// The people beside a slide's title, on the slide: a portrait (or its name) pointed at is
// framed, and chosen by a click, as a logo is -- ← and → choose the one beside it, ⌥← and ⌥→
// move it along the row, ⌫ removes it, Esc leaves it, and its menu (a right-click) and the
// palette offer the same, with Reset People Size once a size is set. A corner of the one
// chosen sizes every portrait on the slide at once: drawn here as it is dragged (the slide is
// not asked for each move), about the row's right end on the title's middle, catching at the
// size the title gives them (⌘ drags freely). Let go, they are that wide: one step, "Resize
// People"; Esc puts them back; a double-click on a corner goes back to the default.

import { h } from "/static/studio/studio.js";
import { peopleOf, peopleSize } from "/static/kinds/deck/peoplelist.js";

const PERSON = /^slide(\d+)\.person(\d+)(?:\.|$)/;

// `people`: people.js's. `deck`, the editor's: { pageNode(), slide() (its index), slideAt(),
// place(node, box, label), boxOf(id), tip(text, x, y) (null: put away), swallowRelease(held),
// free(event) (whether a drag snaps nowhere), putHeld() (a drawing held back while they were
// sized, put in), dropHeld() (one held is not wanted: a drawing of the change follows),
// clearChoice() (nothing else chosen), othersChosen(), refresh() (frames, the
// inspector, where this person is), menu(point, items) }.
export function slidePortraits(people, deck) {
  let chosen = null, chosenOn = null, sizing = null;
  const idOf = (index) => `slide${deck.slide() + 1}.person${index}`;
  const count = () => peopleOf(deck.slideAt()).length;
  people.choosing(() => (chosen !== null && chosenOn === deck.slide() ? chosen : null));

  // The portrait an event is on (its picture, or its name under it), on the slide shown.
  function at(event) {
    const page = deck.pageNode();
    if (!page || !page.contains(event.target)) return null;
    for (let node = event.target; node && node !== page; node = node.parentNode) {
      const found = PERSON.exec(node.id || "");
      if (found && Number(found[1]) === deck.slide() + 1) return Number(found[2]);
    }
    return null;
  }

  // The chosen one's frame, as a logo's, with a handle at each corner that sizes them all.
  const frame = h("div.hit.selected.sizable.portrait-frame", { hidden: true }, h("span.hit-label"),
    ["nw", "ne", "sw", "se"].map((corner) => h(`span.size-handle.${corner}`, {
      title: "Drag to resize every portrait · Double-click to reset size",
      onpointerdown: (event) => sizeStart(event, corner),
      ondblclick: (event) => { event.stopPropagation(); event.preventDefault(); people.resetSize(); },
    })));

  function place() {
    const page = deck.pageNode();
    if (!page) return;
    if (frame.parentNode !== page) page.append(frame);
    if (sizing) return;  // its frame follows them as they are sized
    if (chosen !== null && (chosenOn !== deck.slide() || chosen >= count() || deck.othersChosen())) chosen = null;
    deck.place(frame, chosen === null ? null : deck.boxOf(idOf(chosen)), "Person");
    for (const row of document.querySelectorAll(".person-row")) row.classList.toggle("chosen", chosen !== null && Number(row.dataset.index) === chosen);
  }
  function choose(index) {
    deck.clearChoice();
    chosen = index;
    chosenOn = deck.slide();
    deck.refresh();
    document.querySelector(`.person-row[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }
  function leave() { chosen = null; deck.refresh(); }

  // Pointed at: framed and named, unless it is the one chosen (framed already).
  function hover(event, show) {
    const index = at(event);
    if (index === null) return false;
    show(index === chosen ? null : deck.boxOf(idOf(index)), "Person");
    return true;
  }
  // Pressed: nothing to drag but its corners (the slide's other gestures leave it alone).
  function press(event) { return at(event) !== null && event.button === 0; }
  // Clicked: chosen. A click anywhere else leaves the one chosen, and is the slide's.
  function pick(event) {
    const index = at(event);
    if (index === null) { if (chosen !== null) chosen = null; return false; }
    choose(index);
    return true;
  }
  function items(index) {
    const many = count();
    return [
      { icon: "left", label: "Move Left", keys: "⌥←", disabled: index === 0, run: () => moveTo(index, index - 1) },
      { icon: "right", label: "Move Right", keys: "⌥→", disabled: index >= many - 1, run: () => moveTo(index, index + 1) },
      { icon: "undo", label: "Reset People Size", disabled: peopleSize(deck.slideAt()) === null, run: () => people.resetSize() },
      "-",
      { icon: "trash", label: "Remove Person", keys: "⌫", danger: true, run: () => removeAt(index) },
    ];
  }
  function context(event) {
    const index = at(event);
    if (index === null) return false;
    choose(index);
    deck.menu({ x: event.clientX, y: event.clientY }, items(index));
    return true;
  }
  // The palette's, with one chosen.
  const commands = () => (chosen === null ? [] : items(chosen).filter((item) => item !== "-" && !item.disabled));

  function moveTo(index, to) {
    if (to < 0 || to >= count()) return;
    people.move(index, to);
    if (chosen === index) { chosen = to; place(); }
  }
  function removeAt(index) {
    chosen = null;
    people.remove(index);
    deck.refresh();
  }
  // The keys with one chosen. Whether the key was one of these.
  function key(event) {
    if (chosen === null || event.metaKey || event.ctrlKey) return false;
    if (chosenOn !== deck.slide() || deck.othersChosen()) { chosen = null; return false; }
    const now = chosen;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      const to = now + (event.key === "ArrowLeft" ? -1 : 1);
      if (event.altKey) moveTo(now, to);
      else if (to >= 0 && to < count()) choose(to);
      return true;
    }
    if (event.key === "Backspace" || event.key === "Delete") { removeAt(now); return true; }
    if (event.key === "Escape") { leave(); return true; }
    return false;
  }

  // The slide's portraits and their names, as drawn (not the parts inside one, nor what
  // they are drawn with: a clip, a picture kept to fill one).
  function drawnPeople() {
    const page = deck.pageNode(), prefix = `[id^="slide${deck.slide() + 1}.person"]`;
    return [...(page?.querySelectorAll(prefix) || [])].filter((node) => PERSON.test(node.id) && node instanceof SVGGraphicsElement
      && !node.closest("defs, clipPath, mask, pattern") && !node.parentNode.closest?.(prefix));
  }
  function sizeStart(event, corner) {
    if (event.button !== 0 || sizing || chosen === null) return;
    event.preventDefault();
    event.stopPropagation();
    const mine = deck.pageNode()?.querySelector(`[id="${CSS.escape(idOf(chosen))}"]`);
    const matrix = mine?.getScreenCTM?.();
    const elements = drawnPeople();
    if (!mine || !matrix || !elements.length) return;
    // In the slide's points: the row's right end stays where it is, its portraits' middle too.
    const own = mine.getBBox();
    const right = Math.max(...elements.map((element) => { const box = element.getBBox(); return box.x + box.width; }));
    const handle = { x: corner.endsWith("w") ? own.x : own.x + own.width, y: corner.startsWith("n") ? own.y : own.y + own.height };
    const far = { x: corner.endsWith("w") ? own.x + own.width : own.x, y: corner.startsWith("n") ? own.y + own.height : own.y };
    const fallback = Number(mine.getAttribute("data-flexo-default")) || null;
    sizing = { elements, anchor: { x: right, y: own.y + own.height / 2 }, handle, far, inverse: matrix.inverse(), start: own.width, now: own.width,
      fallback, snapped: false, pixels: Math.abs(matrix.a), from: { x: event.clientX, y: event.clientY }, moved: false };
    deck.pageNode().classList.add("block-sizing");
    window.addEventListener("pointermove", sizeMove);
    window.addEventListener("pointerup", sizeEnd);
    window.addEventListener("pointercancel", sizeCancel);
    window.addEventListener("keydown", sizeKey, true);
  }
  // (One frame's worth of moves drawn at once: the pointer may report several between two.)
  let pending = null;
  function sizeMove(event) {
    if (!sizing) return;
    if (!sizing.moved && Math.hypot(event.clientX - sizing.from.x, event.clientY - sizing.from.y) < 3) return;
    sizing.moved = true;
    const first = !pending;
    pending = { x: event.clientX, y: event.clientY, free: deck.free(event) };
    if (first) requestAnimationFrame(sizeDraw);
  }
  function sizeDraw() {
    const was = pending, now = sizing;
    pending = null;
    if (!was || !now) return;
    // The size that puts the corner held nearest the pointer, the portrait sized about its far corner.
    const point = new DOMPoint(was.x, was.y).matrixTransform(now.inverse);
    const { handle, far, anchor } = now;
    const ax = handle.x - far.x, ay = handle.y - far.y, reach = ax * ax + ay * ay;
    const scale = reach > 0 ? Math.max(((point.x - far.x) * ax + (point.y - far.y) * ay) / reach, 0) : 1;
    const [least, most] = people.sizes;
    let size = Math.round(Math.min(most, Math.max(least, now.start * scale)));
    // It catches at the size the title gives them (a few pixels either side of it), unless ⌘ is held.
    now.snapped = Boolean(now.fallback) && !was.free && Math.abs(size - now.fallback) * now.pixels < 6;
    if (now.snapped) size = now.fallback;
    now.now = size;
    const k = size / now.start;
    for (const element of now.elements) element.setAttribute("transform", `translate(${anchor.x} ${anchor.y}) scale(${k}) translate(${-anchor.x} ${-anchor.y})`);
    deck.place(frame, deck.boxOf(idOf(chosen)), "Person");
    deck.tip(now.snapped ? `${Math.round(size)} pt · Default Size` : `${size} pt`, was.x, was.y);
  }
  function sizeFinish() {
    const was = sizing;
    sizing = null;
    pending = null;
    window.removeEventListener("pointermove", sizeMove);
    window.removeEventListener("pointerup", sizeEnd);
    window.removeEventListener("pointercancel", sizeCancel);
    window.removeEventListener("keydown", sizeKey, true);
    deck.pageNode()?.classList.remove("block-sizing");
    deck.tip(null);
    if (was?.moved) deck.swallowRelease();
    return was;
  }
  function sizeEnd() {
    const was = sizeFinish();
    if (!was) return;
    if (was.moved && Math.abs(was.now - was.start) >= 0.5) {
      // (Drawn so until the slide is drawn again that size: the drawing held meanwhile is older.)
      deck.dropHeld();
      if (people.resize(was.snapped ? null : was.now)) return;
    }
    sizeBack(was);
  }
  function sizeBack(was) {
    for (const element of was.elements) element.removeAttribute("transform");
    deck.putHeld();
    place();
  }
  function sizeCancel() { const was = sizeFinish(); if (was) sizeBack(was); }
  function sizeKey(event) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    sizeCancel();
    deck.swallowRelease(true);
  }

  return { hover, press, pick, context, key, place, commands, busy: () => Boolean(sizing), chosen: () => chosen };
}

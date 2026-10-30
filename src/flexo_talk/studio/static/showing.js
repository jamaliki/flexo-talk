// Show: anything on a slide -- an object, a part of one, a shape -- Shown, Highlighted, Dimmed
// or Hidden where it stands, as a figure's parts are (flexo_talk.showing). The same control, menu
// and commands for every one of them:
// - the inspector's Show, for what is chosen (several at once), and for a list, a table, a
//   gallery, numbers or code, each of its parts by itself;
// - Show ▸ on a right-click: on an object, a shape, or a part of an object (Item 2 of a list,
//   Row 3 of a table) -- a second menu of the four, the one it is ticked;
// - the palette's Show, Highlight, Dim and Hide of what is chosen (the Mac app's Format › Show As
//   runs them by those names), and Show All on Slide.
// Each change is a step of its own, named for what it did ("Dim List Item 2", "Hide Picture").
// With the stage showing the slide at a click (showsteps.js), each shows and says how it is shown
// from that click on ("Dim List Item 2 from Click 2": its `click 2`, flexo_talk.onclick).
//
// `ctx` is the editor's: studio, slideAt(), blocksAt(slide, region), editSlide(mutate, options),
// objectName(block), shapeName(index), blockId({ region, index }), pageNode(), render(), and
// click() -- the click the stage shows the slide at (0: as it is before its first) -- and
// from() -- the control choosing it, for the Show section.

import { h, ui, menu } from "/static/studio/studio.js";
import { WAYS, VERBS, NAMES, AS, PARTS, wholeOf, setWhole, partOf, setPart, partsOf, partName, anyApart, showAll, partAt,
  saidAt, entryAt, tidyClicks, showAllAt } from "/static/kinds/deck/shown.js";

const TITLES = {
  shown: "Drawn as it is",
  highlighted: "Drawn as it is, and the rest of the slide faint",
  dimmed: "Drawn faint, where it stands",
  hidden: "Not presented or exported: its place is kept, and nothing else moves",
};
const PART_TITLES = {
  shown: "Drawn as it is",
  highlighted: "Drawn as it is, and the others faint",
  dimmed: "Drawn faint, where it stands",
  hidden: "Not presented or exported: its place is kept",
};
// What the menu calls each, as the figure's parts' menu does.
const MENU = { shown: "Shown", highlighted: "Highlight", dimmed: "Dim", hidden: "Hide" };

// Where the last right-click was: a second menu opens there.
let pressed = null;
if (typeof document !== "undefined") document.addEventListener("contextmenu", (event) => { pressed = { x: event.clientX, y: event.clientY }; }, true);

export function showStates(ctx) {
  const click = () => ctx.click?.() || 0;
  // From the click the stage shows: said so after what it does ("Dim Picture from Click 2").
  const fromClick = () => (click() ? ` from Click ${click()}` : "");
  // How `spec` (an object, or a shape) is shown as a whole at the click shown.
  const wholeAt = (spec, shape = false) => { const said = saidAt(spec, click()); return wholeOf(said, { shape: shape && said === spec }); };
  const kindOf = (block) => (typeof block === "string" ? "text" : Object.keys(block || {}).find((key) => PARTS[key] || key === "figure") || "other");
  const blockAt = (slide, at) => ctx.blocksAt(slide || {}, at.region)[at.index];
  // What is chosen, as { blocks: [{ region, index }], shapes: [index] }, each there still.
  const live = (targets) => {
    const slide = ctx.slideAt();
    return { blocks: (targets?.blocks || []).filter((at) => blockAt(slide, at) !== undefined),
      shapes: (targets?.shapes || []).filter((index) => slide?.shapes?.[index]) };
  };
  const empty = (targets) => !targets.blocks.length && !targets.shapes.length;
  // How they are all shown, as a whole: one way, or "" where they differ.
  function wayOf(targets) {
    const slide = ctx.slideAt();
    const ways = [...targets.blocks.map((at) => wholeAt(blockAt(slide, at))), ...targets.shapes.map((index) => wholeAt(slide.shapes[index], true))];
    return ways.every((way) => way === ways[0]) ? ways[0] || "shown" : "";
  }
  // What they are called, for the history and the palette: "Picture", "Shape", "3 Objects".
  function called(targets) {
    const slide = ctx.slideAt(), count = targets.blocks.length + targets.shapes.length;
    if (count === 1 && targets.blocks.length) return ctx.objectName(blockAt(slide, targets.blocks[0]));
    if (count === 1) return ctx.shapeName?.(targets.shapes[0]) || "Shape";
    return targets.blocks.length ? `${count} Objects` : `${count} Shapes`;
  }

  // Each shown `how` as a whole: one step.
  function set(targets, how) {
    targets = live(targets);
    if (empty(targets)) return;
    ctx.editSlide((slide) => {
      for (const at of targets.blocks) {
        const list = ctx.blocksAt(slide, at.region);
        if (list[at.index] === undefined) continue;
        // (Words written bare are an object of words, which says how it is shown.)
        if (!list[at.index] || typeof list[at.index] !== "object") list[at.index] = { text: String(list[at.index] ?? "") };
        setWhole(entryAt(list[at.index], click()), how);
        tidyClicks(list[at.index]);
      }
      for (const index of targets.shapes) {
        const shape = slide.shapes?.[index];
        if (!shape) continue;
        setWhole(entryAt(shape, click(), { shape: true }), how, { shape: !click() });
        tidyClicks(shape, { shape: true });
      }
    }, { label: `${VERBS[how]} ${called(targets)}${fromClick()}` });
    ctx.render();
  }
  // A part of an object (`names`: its parts' names) shown `how`: one step.
  function setParts(at, names, how) {
    const block = blockAt(ctx.slideAt(), at);
    if (!block || typeof block !== "object" || !names.length) return;
    const what = names.length === 1 ? partName(block, names[0]) : `${names.length} ${PARTS[kindOf(block)]?.[0] || "Part"}s`;
    ctx.editSlide((slide) => {
      const own = blockAt(slide, at);
      if (!own || typeof own !== "object") return;
      setPart(entryAt(own, click()), names, how);
      tidyClicks(own);
    }, { label: `${VERBS[how]} ${what}${fromClick()}` });
    ctx.render();
  }

  const segmented = (value, key, titles, onChange) => ui.segmented({ value, key, onChange,
    options: WAYS.map((way) => ({ value: way, label: NAMES[way], title: titles[way] })) });

  // The inspector's Show: for what is chosen as a whole, and -- one object of parts chosen --
  // each of its parts.
  function section(targets) {
    targets = live(targets);
    if (empty(targets)) return null;
    const one = targets.blocks.length === 1 && !targets.shapes.length ? targets.blocks[0] : null;
    return h("div.section.show-section", {}, h("div.section-title", {}, "Show"),
      ctx.from?.() || null,
      segmented(wayOf(targets), "show.whole", TITLES, (how) => set(targets, how)),
      one ? partsList(one) : null);
  }
  function partsList(at) {
    const block = blockAt(ctx.slideAt(), at), kind = kindOf(block);
    const parts = PARTS[kind] ? partsOf(block) : [];
    if (parts.length < 2) return null;
    return h("div.show-parts", {}, h("div.show-parts-title", {}, `${PARTS[kind][0]}s`),
      parts.map((part) => h("div.show-part", {},
        h("span.show-part-name", {}, part.name),
        // (An item under another, in from it, as on the slide.)
        h("span.show-part-words", { title: part.label, style: part.level ? { paddingLeft: `${part.level * 12}px` } : {} }, part.label || "—"),
        ui.select({ value: partOf(saidAt(block, click()), part.name), key: `show.part:${part.name}`, title: partName(block, part.name),
          options: WAYS.map((way) => ({ value: way, label: NAMES[way], title: PART_TITLES[way] })),
          onChange: (how) => setParts(at, [part.name], how) }))));
  }

  // Show ▸ on a right-click: the four, the one it is ticked, in a menu of their own where it was
  // opened. `label`: what it shows ("Show Item 2"), `now`: how it is shown, `run(how)`.
  function submenu(label, now, run, point) {
    return { icon: "eye", label, keys: "▸", run: () => menu(point || pressed || { x: innerWidth / 2, y: innerHeight / 3 }, [{ title: label },
      ...WAYS.map((way) => ({ label: MENU[way], checked: now === way, run: () => run(way) }))]) };
  }
  // The item for what is chosen (`targets`), on its right-click menu.
  function menuItem(targets, point) {
    targets = live(targets);
    return empty(targets) ? null : submenu("Show", wayOf(targets), (how) => set(targets, how), point);
  }
  // The item for the part of an object under the pointer -- a list's item, a table's row, a
  // gallery's picture, a number, a line of code -- if there is one: "Show Item 2 ▸".
  function partItem(at, event, point) {
    const block = blockAt(ctx.slideAt(), at), name = partUnder(at, event);
    if (!name) return null;
    return submenu(`Show ${PARTS[kindOf(block)][0]} ${name}`, partOf(saidAt(block, click()), name), (how) => setParts(at, [name], how), point);
  }
  // The part under the pointer, by name: the nearest of the object's parts as drawn.
  function partUnder(at, event) {
    const block = blockAt(ctx.slideAt(), at), page = ctx.pageNode?.();
    if (!block || !PARTS[kindOf(block)] || !page) return null;
    const id = ctx.blockId(at);
    let best = null;
    for (const node of page.querySelectorAll(`[id^="${CSS.escape(`${id}.`)}"]`)) {
      const rest = node.id.slice(id.length + 1);
      if (!/^\d+(?:\.\d+)?(?:\.(?:mark|label|caption|cell))?$/.test(rest)) continue;
      const box = node.getBoundingClientRect();
      if (!box.width && !box.height) continue;
      const far = Math.hypot(Math.max(box.left - event.clientX, 0, event.clientX - box.right), Math.max(box.top - event.clientY, 0, event.clientY - box.bottom));
      if (!best || far < best.far) best = { far, rest, of: node.getAttribute("data-flexo-of") };
    }
    return best && best.far < 24 ? partAt(block, best.rest, best.of) : null;
  }

  // The palette's: each way what is chosen is not, named for it; and, anything on the slide shown
  // apart, Show All on Slide. (Format › Show As runs them by their `also`.)
  function commands(targets) {
    targets = live(targets);
    const out = [];
    if (!empty(targets)) {
      const now = wayOf(targets), name = called(targets);
      out.push(...WAYS.filter((way) => way !== now).map((way) => ({ icon: "eye", label: `${VERBS[way]} ${name}${fromClick()}`, also: [AS[way]], run: () => set(targets, way) })));
    }
    const slide = ctx.slideAt();
    if (slide && anyApart(slide, click())) out.push({ icon: "eye", label: `Show All on Slide${fromClick()}`, hint: "Nothing on it hidden, dimmed or highlighted", run: () => showAllNow() });
    return out;
  }
  function showAllNow() {
    if (!ctx.slideAt() || !anyApart(ctx.slideAt(), click())) return;
    ctx.editSlide((slide) => { if (click()) showAllAt(slide, click()); else showAll(slide); }, { label: `Show All on Slide${fromClick()}` });
    ctx.render();
  }
  // A figure's parts chosen on a slide: the palette's Show, Highlight, Dim and Hide of them, as
  // its own editor has them (`parts`: the figure's, flexo's parts.js).
  function figureCommands(parts, name) {
    const ids = (parts?.selected || []).filter((id) => id !== parts.model?.root && (parts.nodeOf(id) || parts.groupOf(id) || parts.edgeOf?.(id) || parts.netOf?.(id)));
    if (!ids.length) return [];
    const ways = ids.map((id) => parts.shownAs(id) || "shown"), now = ways.every((way) => way === ways[0]) ? ways[0] : "";
    return WAYS.filter((way) => way !== now).map((way) => ({ icon: "eye", label: `${VERBS[way]} ${name}${fromClick()}`, also: [AS[way]], run: () => parts.showAs(way, ids) }));
  }

  return { section, menuItem, partItem, commands, figureCommands, set, setParts, showAll: showAllNow, wayOf: (targets) => wayOf(live(targets)) };
}

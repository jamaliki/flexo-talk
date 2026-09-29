// The deck editor. The slide is where you work: click a part to choose it,
// double-click words to edit them in place, add slides and parts from the bar
// above. The inspector on the right shows what is chosen -- a part, or the
// slide -- and the deck's design. Others' edits (people, agents) arrive live:
// the slides they touch flash in their colour.

import { h, clear, icon, ui, menu, popover, closeMenu, dialog, toast, keepFocus, avatar, colourOf, picture, same } from "/static/studio/studio.js";
import { figureParts, widenLines } from "/static/kinds/figure/parts.js";

const BLOCKS = {
  text: { icon: "text", label: "Text", hint: "A paragraph" },
  bullets: { icon: "list", label: "List", hint: "Bullets or numbers, nested" },
  figure: { icon: "figure", label: "Figure", hint: "A flexo figure, laid out for its place" },
  image: { icon: "image", label: "Picture", hint: "PNG, JPEG, or SVG (drawn as vectors)" },
  table: { icon: "table", label: "Table", hint: "Ruled as in a paper" },
  stats: { icon: "stats", label: "Numbers", hint: "Numbers to remember, very large" },
  quote: { icon: "quote", label: "Quote", hint: "Set large, with who said it" },
  callout: { icon: "callout", label: "Callout", hint: "A key point on a tinted panel" },
  code: { icon: "code", label: "Code", hint: "A monospace listing" },
  gallery: { icon: "gallery", label: "Gallery", hint: "Logos or people in a grid" },
  plot: { icon: "plot", label: "Plot", hint: "A matplotlib figure made in Python" },
};
const MAIN_BLOCKS = ["text", "bullets", "figure", "image", "table"];
const MORE_BLOCKS = ["stats", "quote", "callout", "code", "gallery", "plot"];
const INLINE = new Set(["text", "bullets", "quote", "callout", "code"]);

const LAYOUT_NAMES = {
  content: "Content", "two-columns": "Two columns", columns: "Columns", figure: "Figure", title: "Title",
  section: "Section", statement: "Statement", agenda: "Agenda", blank: "Blank",
};
const LAYOUT_ORDER = ["content", "two-columns", "columns", "figure", "title", "section", "statement", "agenda", "blank"];
const WORDLESS = new Set(["title", "section", "statement", "agenda"]);
const TONES = ["accent", "accent2", "accent3", "accent4", "accent5", "accent6"];

const NEW_SLIDES = {
  content: () => ({ title: "A new slide", body: [{ bullets: ["The first point", "The second point"] }] }),
  "two-columns": () => ({ layout: "two-columns", title: "Two sides", left: [{ bullets: ["On the left"] }], right: [{ text: "On the right." }] }),
  columns: () => ({ layout: "columns", title: "Three things", columns: [[{ text: "**One**" }], [{ text: "**Two**" }], [{ text: "**Three**" }]] }),
  figure: () => ({ layout: "figure", title: "The model", body: [NEW_BLOCKS.figure()] }),
  title: () => ({ layout: "title", title: "A talk worth giving", subtitle: "What we found" }),
  section: () => ({ layout: "section", title: "Part two" }),
  statement: () => ({ layout: "statement", words: "One sentence that [matters]{accent}." }),
  agenda: () => ({ layout: "agenda" }),
  blank: () => ({ layout: "blank", body: [{ text: "Anything at all." }] }),
};

const NEW_BLOCKS = {
  bullets: () => ({ bullets: ["A point", "Another point"] }),
  text: () => ({ text: "A paragraph." }),
  figure: () => ({ figure: { figure: { id: `figure-${Date.now().toString(36)}` }, nodes: [
    { id: "x", kind: "text", label: "Input $x$" },
    { id: "model", label: "Model", properties: { tone: "encoder" } },
    { id: "y", kind: "text", label: "Output $y$" }],
    edges: [{ from: "x", to: "model" }, { from: "model", to: "y" }] } }),
  image: () => ({ image: "" }),
  table: () => ({ table: [["Model", "Params", "Score"], ["Baseline", "25.6M", "76.1"], ["Ours", "24.0M", "**81.2**"]] }),
  stats: () => ({ stats: [{ value: "93%", label: "accuracy" }, { value: "4×", label: "faster" }] }),
  quote: () => ({ quote: "Words worth repeating.", by: "Someone wise" }),
  callout: () => ({ callout: "The one thing to remember.", title: "Key point" }),
  code: () => ({ code: "def model(x):\n    # the whole idea\n    return head(encoder(x))" }),
  gallery: () => ({ gallery: [] }),
  plot: () => ({ plot: "" }),
};

// -- the document ---------------------------------------------------------------------

const layoutOf = (slide) => slide?.layout || "content";

function regionsOf(slide) {
  const layout = layoutOf(slide);
  if (!slide || WORDLESS.has(layout)) return [];
  if (layout === "two-columns") return [{ key: "left", label: "Left", svg: "left" }, { key: "right", label: "Right", svg: "right" }];
  if (layout === "columns") return (slide.columns || []).map((_, i) => ({ key: `columns.${i}`, label: `Column ${i + 1}`, svg: `column${i + 1}` }));
  return [{ key: "body", label: layout === "figure" ? "Figure" : "Body", svg: "body" }];
}

function blocksAt(slide, key, create = false) {
  if (!slide) return [];
  if (key.startsWith("columns.")) {
    const index = Number(key.split(".")[1]);
    slide.columns ||= [];
    if (create) slide.columns[index] ||= [];
    return slide.columns[index] || [];
  }
  if (create && !Array.isArray(slide[key])) slide[key] = [];
  return slide[key] || [];
}

const kindOf = (block) => Object.keys(block || {}).find((key) => key in BLOCKS) || "text";

function setOption(target, key, value, fallback = undefined) {
  if (value === null || value === undefined || value === "" || value === fallback) delete target[key];
  else target[key] = value;
}

function plain(markup) {
  return String(markup ?? "").replace(/\[([^\]]+)\]\{[^}]+\}/g, "$1").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\*\*|\*|`/g, "").replace(/\$([^$]*)\$/g, "$1").split("\n")[0];
}

function summary(block) {
  const kind = kindOf(block);
  const value = block[kind];
  switch (kind) {
    case "bullets": { const first = (Array.isArray(value) ? value : [value]).find((item) => !Array.isArray(item)); return plain(first) || "Empty list"; }
    case "table": return Array.isArray(value) ? `${value.length} rows × ${Math.max(0, ...value.map((row) => (Array.isArray(row) ? row.length : 1)))} columns` : "";
    case "stats": return Array.isArray(value) ? value.map((item) => item?.value ?? item?.[0] ?? item).join("  ·  ") : "";
    case "gallery": { const n = Array.isArray(value) ? value.length : 0; return `${n} picture${n === 1 ? "" : "s"}`; }
    case "figure": return typeof value === "string" ? value : `Drawn here · ${(value?.nodes || []).length} parts`;
    case "image": case "plot": return value || "Not chosen yet";
    case "callout": return plain(block.title) || plain(value);
    default: return plain(value);
  }
}

function slideTitle(slide) {
  return plain(slide?.words || slide?.title) || LAYOUT_NAMES[layoutOf(slide)];
}

function bulletsText(items, level = 0) {
  const lines = [];
  for (const item of Array.isArray(items) ? items : [items]) {
    if (Array.isArray(item)) lines.push(...bulletsText(item, level + 1));
    else lines.push("  ".repeat(level) + String(item ?? ""));
  }
  return level === 0 ? lines.join("\n") : lines;
}

function bulletsFrom(text) {
  const root = [];
  const stack = [root];
  for (const raw of text.split("\n")) {
    if (!raw.trim()) continue;
    const indent = raw.match(/^[ \t]*/)[0].replace(/\t/g, "  ").length;
    let level = Math.min(Math.floor(indent / 2), stack.length);
    if (level > 0 && !stack[level - 1].some((item) => !Array.isArray(item))) level = stack.length - 1;
    if (level === stack.length) { const nested = []; stack[level - 1].push(nested); stack.push(nested); }
    stack.length = level + 1;
    stack[level].push(raw.trim());
  }
  return root;
}

function numeric(cell) {
  if (typeof cell === "number") return true;
  const text = String(cell).trim().replace(/\$/g, "").replace(/\*/g, "").replace(/,/g, "").replace(/\\pm/g, "±").replace(/%$/, "").trim();
  return /^[-+−]?\d+(\.\d+)?(\s*±\s*\d+(\.\d+)?)?\s*[kKMGTBx×]?$/.test(text);
}

function autoAlign(rows, header) {
  const columns = Math.max(0, ...rows.map((row) => row.length));
  const body = rows.slice(header ? 1 : 0);
  return Array.from({ length: columns }, (_, i) => (body.length && body.every((row) => i >= row.length || numeric(row[i])) ? "end" : "start"));
}

function alignList(value, columns) {
  const names = { l: "start", c: "middle", r: "end" };
  if (typeof value === "string" && value && [...value].every((ch) => ch in names)) value = [...value].map((ch) => names[ch]);
  return Array.isArray(value) && value.length === columns ? value : null;
}

function placeOf(where) {
  const match = /slides\[(\d+)\](?:\.(body|left|right|columns\[(\d+)\])\[(\d+)\])?/.exec(where || "");
  if (!match) return null;
  const region = match[2] ? (match[3] !== undefined ? `columns.${match[3]}` : match[2]) : null;
  return { slide: Number(match[1]), region, index: match[4] !== undefined ? Number(match[4]) : null };
}

// -- small pictures ---------------------------------------------------------------------

function glyph(layout) {
  const bar = (x, y, w, hgt, accent) => h(`i${accent ? ".a" : ""}`, { style: { left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${hgt}%` } });
  const parts = {
    content: [bar(10, 14, 50, 12), bar(10, 38, 70, 7), bar(10, 54, 60, 7), bar(10, 70, 64, 7)],
    "two-columns": [bar(10, 14, 50, 12), bar(10, 40, 36, 7), bar(10, 56, 30, 7), bar(54, 38, 36, 44, true)],
    columns: [bar(10, 14, 50, 12), bar(10, 40, 22, 40), bar(39, 40, 22, 40), bar(68, 40, 22, 40)],
    figure: [bar(10, 14, 50, 12), bar(18, 36, 64, 50, true)],
    title: [bar(20, 34, 60, 14, true), bar(30, 56, 40, 7), bar(38, 70, 24, 6)],
    section: [bar(20, 30, 60, 4, true), bar(20, 42, 50, 16), bar(20, 64, 34, 7)],
    statement: [bar(14, 38, 72, 10), bar(24, 54, 52, 10, true)],
    agenda: [bar(10, 14, 40, 12), bar(10, 38, 6, 7, true), bar(20, 38, 50, 7), bar(10, 54, 6, 7, true), bar(20, 54, 44, 7), bar(10, 70, 6, 7, true), bar(20, 70, 48, 7)],
    blank: [bar(10, 12, 80, 76)],
  }[layout] || [];
  return h("div.glyph", {}, parts);
}

function lookArt(name) {
  const bar = (x, y, w, hgt, colour) => h("i", { style: { left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${hgt}%`, background: colour } });
  const ink = "#3b3834", soft = "#c9c4bc", accent = "#3d5afe";
  const body = (x = 10, centred = false) => [0, 1, 2].map((i) => bar(centred ? 22 + i * 3 : x, 48 + i * 13, centred ? 56 - i * 6 : 64 - i * 10, 6, soft));
  const art = {
    classic: [bar(10, 14, 48, 10, ink), bar(10, 30, 12, 3, accent), ...body()],
    band: [bar(0, 0, 100, 34, accent), bar(10, 12, 48, 10, "#fff"), ...body()],
    editorial: [bar(10, 14, 52, 10, ink), bar(10, 30, 80, 1.5, soft), ...body()],
    keynote: [bar(26, 16, 48, 11, ink), ...body(0, true)],
    margin: [bar(0, 0, 3, 100, accent), bar(10, 14, 48, 10, accent), ...body()],
  }[name] || [];
  return h("div.look-art", {}, art);
}

function layoutGrid(current, onPick, layouts) {
  return h("div.layout-grid", {}, layouts.map((layout) => h(`button.layout-card${layout.name === current ? ".on" : ""}`, {
    type: "button", title: layout.note, onclick: () => onPick(layout.name),
  }, glyph(layout.name), h("span.name", {}, LAYOUT_NAMES[layout.name]))));
}

// -- the editor -------------------------------------------------------------------------

export function mount(studio, container) {
  if (!document.querySelector('link[href="/static/kinds/deck/editor.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/editor.css" }));
  }
  const catalog = studio.catalog;
  const layouts = LAYOUT_ORDER.map((name) => catalog.layouts.find((layout) => layout.name === name)).filter(Boolean);
  const state = { slide: 0, focus: null, tab: "slide", notes: remembered("notes", "0") === "1" };
  let pages = [];
  let messages = [];
  let pending = false;
  let inline = null;

  studio.hints = () => ({ focus: state.slide });
  const doc = () => studio.doc;
  const slides = () => doc().slides || [];
  const slideAt = (d = doc()) => (d.slides || [])[state.slide];

  const editSlide = (mutate, options = {}) => studio.change((d) => { const slide = (d.slides || [])[state.slide]; if (slide) mutate(slide, d); }, options);
  const editBlock = (place, mutate, options = {}) => editSlide((slide) => {
    const block = blocksAt(slide, place.region)[place.index];
    if (block) mutate(block, slide);
  }, { quiet: true, ...options });

  // -- the frame --
  const railList = h("div.rail-list.scroll-thin", { tabindex: 0 });
  const rail = h("aside.panel.rail", {}, railList);
  const stage = h("div.stage.deck-stage.scroll-thin");
  const notesArea = ui.textarea({ rows: 3, key: "notes", placeholder: "What to say on this slide", onInput: (text) =>
    editSlide((slide) => setOption(slide, "notes", text), { quiet: true, merge: `notes-${state.slide}` }) });
  const notesPreview = h("span.notes-preview");
  const notes = h(`div.notes${state.notes ? ".open" : ""}`, {},
    h("button.notes-head", { type: "button", onclick: () => { state.notes = !state.notes; remember("notes", state.notes ? "1" : "0"); notes.classList.toggle("open", state.notes); if (state.notes) notesArea.focus(); } },
      icon("chevron", { class: "caret" }), h("span.notes-label", {}, "Notes"), notesPreview),
    h("div.notes-body", {}, notesArea));
  const center = h("section.deck-center", {}, stage, notes);
  const inspectorHead = h("div.insp-head");
  const inspectorBody = h("div.panel-body.scroll-thin");
  const inspector = h("aside.panel.inspector", {}, inspectorHead, inspectorBody);
  const root = h("div.deck", {}, rail, center, inspector);
  clear(container, root);

  // -- the bar --
  const insertButtons = MAIN_BLOCKS.map((kind) => ui.button(BLOCKS[kind].label, () => insertBlock(kind), { kind: "ghost", icon: BLOCKS[kind].icon, title: `Add ${BLOCKS[kind].label.toLowerCase()}: ${BLOCKS[kind].hint}` }));
  const moreButton = ui.button("More", (event) => menu(event.currentTarget, MORE_BLOCKS.map((kind) => ({ icon: BLOCKS[kind].icon, label: BLOCKS[kind].label, hint: BLOCKS[kind].hint, run: () => insertBlock(kind) }))), { kind: "ghost", icon: "chevron-down" });
  const layoutButton = h("button.btn.ghost.layout-button", { type: "button", title: "The slide's layout", onclick: (event) => layoutPopover(event.currentTarget) });
  const newSlideButton = ui.button("Slide", (event) => newSlidePopover(event.currentTarget), { kind: "ghost", icon: "plus", title: "Add a slide after this one (N)" });
  studio.tools.append(newSlideButton, layoutButton, h("span.sep"), ...insertButtons, moreButton);
  studio.actions.append(
    ui.button("Present", () => present(), { kind: "ghost", icon: "play", title: "Present from this slide (⌘⏎)" }),
    ui.button("Export", (event) => menu(event.currentTarget, [
      { icon: "export", label: "PowerPoint", hint: "Native, editable shapes and text", run: () => studio.exportFiles(["pptx"]) },
      { icon: "export", label: "PDF", hint: "A page per slide, fonts embedded", run: () => studio.exportFiles(["pdf"]) },
      { icon: "image", label: "PNG per slide", run: () => studio.exportFiles(["png"]) },
      { icon: "image", label: "SVG per slide", run: () => studio.exportFiles(["svg"]) },
      "-",
      { icon: "export", label: "Everything", hint: "PPTX, PDF, SVG and PNG", run: () => studio.exportFiles(["pptx", "pdf", "svg", "png"]) },
    ], { align: "end" }), { kind: "ghost", icon: "export" }));

  const renderBar = () => {
    const slide = slideAt();
    clear(layoutButton, glyph(layoutOf(slide)), h("span", {}, LAYOUT_NAMES[layoutOf(slide)] || "Layout"), icon("chevron-down"));
    layoutButton.disabled = !slide;
    const room = regionsOf(slide).length > 0;
    for (const button of [...insertButtons, moreButton]) button.disabled = !room;
    moreButton.title = room ? "More kinds of part" : "This slide's layout has no room for parts";
  };

  function layoutPopover(anchor) {
    const slide = slideAt();
    if (!slide) return;
    popover(anchor, [h("div.menu-title", {}, "Layout"), layoutGrid(layoutOf(slide), (name) => { closeMenu(); changeLayout(name); }, layouts)], { className: "layout-menu" });
  }

  function newSlidePopover(anchor, at = state.slide + 1) {
    popover(anchor, [h("div.menu-title", {}, "New slide"), layoutGrid(null, (name) => { closeMenu(); addSlide(name, at); }, layouts)], { className: "layout-menu" });
  }

  // -- slides --
  function addSlide(layout, at = slides().length) {
    studio.change((d) => { d.slides ||= []; d.slides.splice(at, 0, NEW_SLIDES[layout]()); });
    select(at);
    if (layout !== "agenda") setTimeout(() => openInline({ kind: "field", field: layout === "statement" ? "words" : "title" }, { selectAll: true }), 300);
  }

  function moveSlide(from, to) {
    if (from === to || to < 0 || to >= slides().length) return;
    studio.change((d) => { const [slide] = d.slides.splice(from, 1); d.slides.splice(to, 0, slide); });
    select(to);
  }

  function duplicateSlide(index) {
    studio.change((d) => { d.slides.splice(index + 1, 0, structuredClone(d.slides[index])); });
    select(index + 1);
  }

  function deleteSlide(index) {
    const title = slideTitle(slides()[index]);
    studio.change((d) => { d.slides.splice(index, 1); });
    select(Math.min(index, slides().length - 1));
    toast(h("span", {}, `Deleted “${title}”. `, h("a", { href: "#", onclick: (event) => { event.preventDefault(); studio.undo(); } }, "Undo")), { icon: "trash", seconds: 5 });
  }

  function slideMenu(anchor, index) {
    const count = slides().length;
    menu(anchor, [
      { icon: "plus", label: "New slide after", run: () => newSlidePopover(anchor, index + 1) },
      { icon: "copy", label: "Duplicate", keys: "⌘D", run: () => duplicateSlide(index) },
      ...(index > 0 ? [{ icon: "up", label: "Move up", run: () => moveSlide(index, index - 1) }] : []),
      ...(index < count - 1 ? [{ icon: "down", label: "Move down", run: () => moveSlide(index, index + 1) }] : []),
      "-",
      { icon: "trash", label: "Delete", danger: true, run: () => deleteSlide(index) },
    ]);
  }

  function select(index, focus = null) {
    closeInline();
    leaveFigure(false);
    state.slide = Math.max(0, Math.min(index, slides().length - 1));
    state.focus = focus;
    renderRail();
    renderStage();
    renderInspector();
    renderBar();
    railList.querySelector(".thumb.on")?.scrollIntoView({ block: "nearest" });
    if (pages[state.slide]?.stale) studio.requestDraw(0);
    reportFocus();
  }

  function reportFocus() {
    const slide = slideAt();
    if (!slide) { studio.focus(null); return; }
    const block = state.focus && blocksAt(slide, state.focus.region)[state.focus.index];
    const part = block ? ` · ${BLOCKS[kindOf(block)].label}` : "";
    studio.focus({ page: state.slide + 1, label: `Slide ${state.slide + 1}${part}`, block: state.focus ? `${state.focus.region}[${state.focus.index}]` : null });
  }

  // -- the rail --
  // Each thumbnail is built again only when what it shows changes; a drawing
  // arriving for one slide leaves the others' nodes alone.
  let dragFrom = null;
  let railKeys = [];

  function renderRail() {
    const list = slides();
    const others = studio.others();
    const old = [...railList.querySelectorAll(":scope > .thumb")];
    const keys = [];
    const nodes = list.map((slide, index) => {
      const page = pages[index];
      const own = messages.filter((m) => m.page === `slide${index + 1}` && m.severity !== "note");
      const worst = own.some((m) => m.severity === "error") ? "error" : own.length ? "warning" : null;
      const here = others.filter((entry) => entry.where?.page === index + 1);
      const key = JSON.stringify([index, page?.svg ? page.hash : slideTitle(slide), Boolean(page?.stale), index === state.slide,
        worst, own.map((m) => m.text), page?.steps, here.map((entry) => [entry.who.id, entry.who.name, colourOf(entry.who)])]);
      keys.push(key);
      if (railKeys[index] === key && old[index]) return old[index];
      return thumbNode(slide, index, page, own, worst, here);
    });
    railKeys = keys;
    const kept = new Set(nodes);
    for (const node of old) if (!kept.has(node)) node.remove();
    let at = railList.firstChild;
    for (const node of nodes) {
      if (at === node) { at = at.nextSibling; continue; }
      railList.insertBefore(node, at);
    }
    if (!railList.querySelector(":scope > .rail-add")) {
      railList.append(h("button.rail-add", { type: "button", onclick: (event) => newSlidePopover(event.currentTarget, slides().length) }, icon("plus"), "New slide"));
    } else railList.append(railList.querySelector(":scope > .rail-add"));
  }

  function thumbNode(slide, index, page, own, worst, here) {
    const clearDrops = () => railList.querySelectorAll(".drop-before,.drop-after").forEach((el) => el.classList.remove("drop-before", "drop-after"));
    const node = h(`div.thumb${index === state.slide ? ".on" : ""}${page?.stale ? ".stale" : ""}`, {
      draggable: true, dataset: { index },
      onclick: () => select(index),
      oncontextmenu: (event) => { event.preventDefault(); slideMenu({ x: event.clientX, y: event.clientY }, index); },
      ondragstart: (event) => { dragFrom = index; node.classList.add("dragging"); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(index)); },
      ondragend: () => { dragFrom = null; node.classList.remove("dragging"); clearDrops(); },
      ondragover: (event) => {
        if (dragFrom === null) return;
        event.preventDefault();
        const box = node.getBoundingClientRect();
        clearDrops();
        node.classList.add(event.clientY > box.top + box.height / 2 ? "drop-after" : "drop-before");
      },
      ondrop: (event) => {
        if (dragFrom === null) return;
        event.preventDefault();
        let to = index + (node.classList.contains("drop-after") ? 1 : 0);
        if (dragFrom < to) to -= 1;
        moveSlide(dragFrom, to);
      },
    },
    h("div.num", {}, index + 1),
    h("div.frame", { style: here.length ? { boxShadow: `0 0 0 2px ${colourOf(here[0].who)}` } : {} },
      page?.svg ? picture(page.svg, page.hash) : h("div.placeholder", {}, slideTitle(slide)),
      worst ? h(`div.badge.${worst}`, { title: own.map((m) => m.text).join("\n") }, icon(worst === "error" ? "close" : "warning", { weight: "2" })) : null,
      page?.steps > 1 ? h("div.steps", { title: "Revealed one item at a time" }, `${page.steps} steps`) : null,
      here.length ? h("div.here", {}, here.slice(0, 2).map((entry) => avatar(entry.who, { size: 18 }))) : null,
      slideMoreButton(index)),
    h("button.insert-after", { type: "button", title: "Add a slide here", onclick: (event) => { event.stopPropagation(); newSlidePopover(event.currentTarget, index + 1); } }, icon("plus")));
    return node;
  }

  function slideMoreButton(index) {
    const button = ui.button("", (event) => { event.stopPropagation(); slideMenu(event.currentTarget, index); }, { kind: "ghost", icon: "more", small: true, title: "Slide actions" });
    button.classList.add("more");
    return button;
  }

  railList.addEventListener("keydown", (event) => {
    if (event.target !== railList) return;
    if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); if (slides().length) deleteSlide(state.slide); }
  });

  // -- the stage --
  const hover = h("div.hit.hover", { hidden: true }, h("span.hit-label"));
  const chosen = h("div.hit.selected", { hidden: true }, h("span.hit-label"));
  let pageNode = null;
  const stageMeta = h("div.slide-meta");
  const stageMessages = h("div.slide-messages.messages", { hidden: true });
  const stageWrap = h("div.slide-wrap", {}, stageMeta, stageMessages);

  function renderStage() {
    const list = slides();
    const slide = slideAt();
    if (document.activeElement !== notesArea) {
      notesArea.value = slide?.notes || "";
      requestAnimationFrame(() => { notesArea.style.height = "auto"; notesArea.style.height = `${Math.max(notesArea.scrollHeight + 2, 60)}px`; });
    }
    notesPreview.textContent = slide?.notes ? plain(slide.notes) : "What to say on this slide";
    notesPreview.classList.toggle("empty", !slide?.notes);
    notes.hidden = !list.length;
    if (!list.length) {
      clear(stage, h("div.stage-empty", {}, h("h2", {}, "An empty deck"), h("div", {}, "Start with a slide:"),
        h("div.layout-grid.big", {}, layouts.map((layout) => h("button.layout-card", { type: "button", onclick: () => addSlide(layout.name, 0) },
          glyph(layout.name), h("span.name", {}, LAYOUT_NAMES[layout.name]), h("span.note", {}, layout.note))))));
      return;
    }
    const page = pages[state.slide];
    // The slide's drawing is put in the page again only when it changed: parsing
    // and laying out an SVG is the costliest thing the stage does.
    const shows = page?.svg ? `${state.slide}:${page.hash}` : "";
    if (!pageNode || pageNode.dataset.shows !== shows) {
      pageNode = h("div.slide-page", { dataset: { shows } });
      if (page?.svg) pageNode.innerHTML = page.svg.replace(/^<\?xml[^>]*>\s*/, "");
      else pageNode.append(h("div.placeholder", {}, h("div.spinner")));
      const svg = pageNode.querySelector("svg");
      if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); svg.setAttribute("preserveAspectRatio", "xMidYMid meet"); }
      if (svg) widenLines(svg);
      pageNode.append(hover, chosen);
      pageNode.addEventListener("mousemove", onHover);
      pageNode.addEventListener("mouseleave", () => { hover.hidden = true; });
      pageNode.addEventListener("click", onPick);
      pageNode.addEventListener("dblclick", onEdit);
    }
    pageNode.classList.toggle("error", Boolean(page?.error));
    pageNode.classList.toggle("pending", Boolean(pending || page?.stale));
    const own = messages.filter((m) => m.page === `slide${state.slide + 1}`);
    const here = studio.others().filter((entry) => entry.where?.page === state.slide + 1);
    if (stageWrap.parentNode !== stage) clear(stage, stageWrap);
    if (stageWrap.firstChild !== pageNode) stageWrap.replaceChildren(pageNode, stageMeta, stageMessages);
    clear(stageMeta,
      h("span.slide-count", {}, `${state.slide + 1} / ${list.length}`),
      page?.steps > 1 ? h("span.chip", {}, icon("reveal"), `${page.steps} steps`) : null,
      here.map((entry) => h("span.here-chip", { style: { borderColor: colourOf(entry.who) } }, avatar(entry.who, { size: 16 }), entry.who.name, entry.doing ? h("span.muted", {}, ` · ${entry.doing}`) : null)),
      h("span.spacer", { style: { flex: 1 } }),
      pending ? h("span.row.drawing", {}, h("span.spinner"), "Drawing…") : h("span.stage-hint", {}, "Click to choose · double-click words to edit"));
    clear(stageMessages, own.map(messageView));
    stageMessages.hidden = !own.length;
    fitStage();
    placeChosen();
    if (inline) positionInline();
    if (figureMarks.parentNode !== pageNode) pageNode.append(figureMarks, figureBar);
    placeFigure();
    figure?.parts.placeInline();
  }

  function messageView(message) {
    const where = placeOf(message.where);
    const link = where && where.region !== null;
    return h(`div.message.${message.severity}${link ? ".link" : ""}`, { onclick: () => { if (link) focusBlock(where.region, where.index); } },
      icon(message.severity === "error" ? "error" : message.severity === "note" ? "info" : "warning"),
      h("div", {}, message.text, message.where ? h("div.where", {}, message.where) : null));
  }

  function fitStage() {
    const room = stage.getBoundingClientRect();
    const width = Math.max(320, Math.min(room.width - 80, (room.height - 110) * 16 / 9));
    stage.style.setProperty("--slide-max", `${width}px`);
  }
  new ResizeObserver(() => { fitStage(); placeChosen(); if (inline) positionInline(); placeFigure(); figure?.parts.placeInline(); }).observe(stage);

  const PART = /^slide(\d+)\.(body|left|right|column(\d+))\.(\d+)(?:\.|$)/;
  const WORDS = /^slide(\d+)\.(title|subtitle|byline)$/;
  const BLOCK_ID = /^slide\d+\.(body|left|right|column\d+)\.\d+$/;

  function partOf(target) {
    for (let node = target; node && node !== pageNode; node = node.parentNode) {
      const id = node.id || "";
      const part = PART.exec(id);
      if (part) return { kind: "block", region: part[3] ? `columns.${Number(part[3]) - 1}` : part[2], index: Number(part[4]), id: `slide${part[1]}.${part[2]}.${part[4]}` };
      const words = WORDS.exec(id);
      if (words) return { kind: "field", field: words[2], id };
    }
    return null;
  }

  function partAt(event) {
    const direct = partOf(event.target);
    if (direct || !pageNode) return direct;
    let best = null;
    for (const node of pageNode.querySelectorAll("[id]")) {
      if (!BLOCK_ID.test(node.id)) continue;
      const box = node.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) continue;
      const area = box.width * box.height;
      if (!best || area < best.area) best = { node, area };
    }
    return best ? partOf(best.node) : null;
  }

  function boxOf(id) {
    const target = pageNode?.querySelector(`[id="${CSS.escape(id)}"]`);
    if (!target) return null;
    const outer = pageNode.getBoundingClientRect(), inner = target.getBoundingClientRect();
    if (!inner.width && !inner.height) return null;
    return { left: inner.left - outer.left - 5, top: inner.top - outer.top - 5, width: inner.width + 10, height: inner.height + 10 };
  }

  function place(node, box, label) {
    node.hidden = !box;
    if (!box) return;
    Object.assign(node.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` });
    if (label !== undefined) node.firstChild.textContent = label;
  }

  function labelOf(part) {
    if (part.kind === "field") return { title: "Title", subtitle: "Subtitle", byline: "Byline" }[part.field] || "Words";
    const block = blocksAt(slideAt() || {}, part.region)[part.index];
    return block ? BLOCKS[kindOf(block)].label : "";
  }

  function onHover(event) {
    if (inFigure(event)) {
      const id = figure.parts.idAt(event);
      const box = id && figure.parts.model ? boxOf(figurePrefix() + id) : null;
      place(hover, box, id ? figure.parts.nameOf(id) : "");
      return;
    }
    const part = partAt(event);
    place(hover, part && boxOf(part.id), part ? labelOf(part) : "");
  }

  function onPick(event) {
    if (event.target.closest(".fig-inline, .figure-bar")) return;
    if (figure && figureBlock() && (figure.parts.connecting || inFigure(event))) { figure.parts.click(event); return; }
    const part = partAt(event);
    if (!part) { state.focus = null; placeChosen(); renderInspector(); reportFocus(); return; }
    if (part.kind === "block") focusBlock(part.region, part.index);
    else {
      state.focus = null; state.tab = "slide"; placeChosen(); renderInspector(); reportFocus();
      const field = part.field === "byline" ? "author" : layoutOf(slideAt()) === "statement" ? "words" : part.field;
      inspectorBody.querySelector(`[data-key="slide.${field}"]`)?.focus();
    }
  }

  function onEdit(event) {
    if (event.target.closest(".fig-inline, .figure-bar")) return;
    if (inFigure(event)) { figure.parts.dblclick(event); return; }
    const part = partAt(event);
    if (!part) return;
    if (part.kind === "field") openInline({ kind: "field", field: part.field === "byline" ? "author" : layoutOf(slideAt()) === "statement" ? "words" : part.field });
    else {
      const block = blocksAt(slideAt(), part.region)[part.index];
      if (block && INLINE.has(kindOf(block))) openInline({ kind: "block", region: part.region, index: part.index });
    }
  }

  function placeChosen() {
    const focus = state.focus;
    if (!focus || !pageNode) { chosen.hidden = true; return; }
    const region = regionsOf(slideAt()).find((r) => r.key === focus.region);
    const box = region && boxOf(`slide${state.slide + 1}.${region.svg}.${focus.index}`);
    const block = blocksAt(slideAt() || {}, focus.region)[focus.index];
    place(chosen, box, block ? BLOCKS[kindOf(block)].label : "");
  }

  function focusBlock(region, index) {
    closeInline();
    state.tab = "slide";
    state.focus = { region, index };
    const block = blocksAt(slideAt(), region)[index];
    if (block && kindOf(block) === "figure") enterFigure(region, index);
    else leaveFigure(false);
    renderInspector();
    placeChosen();
    reportFocus();
  }

  // -- a figure's parts, edited on the slide --
  // A figure chosen on the slide is edited in place: clicks inside it choose its
  // parts, a bar above it adds and connects them, and the inspector shows the part
  // (parts.js, as in the figure editor). Edits go to where the figure is written --
  // the deck, for a figure written in it, so they undo with the deck's; or the
  // figure's own file.
  const figureMarks = h("div.fig-marks");
  const figureBar = h("div.figure-bar", { hidden: true });
  let figure = null;

  function figureBlock() {
    if (!figure || figure.slide !== state.slide) return null;
    const block = blocksAt(slideAt() || {}, figure.region)[figure.index];
    return block && kindOf(block) === "figure" ? block : null;
  }
  const editable = (block) => {
    const value = block?.figure;
    return Boolean(value) && (typeof value === "object" || (typeof value === "string" && !value.includes(".py:")));
  };
  function figurePrefix() {
    const region = figure && regionsOf(slideAt()).find((r) => r.key === figure.region);
    return region ? `slide${state.slide + 1}.${region.svg}.${figure.index}.` : null;
  }
  function inFigure(event) {
    if (!figureBlock()) return false;
    const part = partAt(event);
    return part?.kind === "block" && part.region === figure.region && part.index === figure.index;
  }

  function enterFigure(region, index) {
    const block = blocksAt(slideAt(), region)[index];
    if (!editable(block)) { leaveFigure(false); return; }
    if (figure && figure.slide === state.slide && figure.region === region && figure.index === index) return;
    leaveFigure(false);
    figure = { slide: state.slide, region, index };
    figure.parts = figureParts({
      catalog: catalog.figure_editor,
      get overlay() { return pageNode; },
      element: (id) => { const prefix = figurePrefix(); return prefix && pageNode ? pageNode.querySelector(`[id="${CSS.escape(prefix + id)}"]`) : null; },
      idOf: (id) => { const prefix = figurePrefix(); return prefix && id.startsWith(prefix) ? id.slice(prefix.length) : null; },
      box: (id) => { const prefix = figurePrefix(); return prefix ? boxOf(prefix + id) : null; },
      changed: () => { renderInspector(); placeFigure(); },
      chooseFile,
      addAnchor: () => figureBar.querySelector(".add") || figureBar,
      groupAnchor: () => figureBar.querySelector(".group") || figureBar,
      crumbs: () => h("button.crumb", { type: "button", onclick: () => { state.focus = null; renderInspector(); placeChosen(); reportFocus(); } }, `Slide ${state.slide + 1}`),
      nothing: () => [...blockPanel(slideAt(), figureBlock()), figure.parts.howTo()],
      run: runFigure,
    });
    figure.parts.act({ do: "read" }, { select: false });
  }

  function leaveFigure(render = true) {
    if (!figure) return;
    figure.parts.closeInline(false);
    figure = null;
    clear(figureMarks);
    figureBar.hidden = true;
    root.classList.remove("wide");
    if (render) renderInspector();
  }

  // The server makes the edit where the figure is written; if the deck changed while
  // it did, the edit is made again on the deck as it is now.
  async function runFigure(action, { merge }) {
    if (!figure) return null;
    const at = { slide: figure.slide, region: figure.region, index: figure.index };
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const sent = studio.doc;
      const result = await studio.api("/api/act", { file: studio.file, document: sent, action: { do: "figure", at, edit: action } });
      if (!same(studio.doc, sent)) continue;
      if (result.file) { if (action.do !== "read") studio.requestDraw(0); }
      else if (!same(result.document, sent)) studio.change(() => result.document, { merge, quiet: true });
      return result;
    }
    return null;
  }

  function placeFigure() {
    const block = figureBlock();
    if (!block || !figure.parts.model || !pageNode) { clear(figureMarks); figureBar.hidden = true; return; }
    clear(figureMarks, figure.parts.marks().map(({ box, group, name }) => h(`div.fig-mark${group ? ".group" : ""}`, { style: {
      left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` } },
    group ? h("span.fig-mark-label", {}, name) : null)));
    const region = regionsOf(slideAt()).find((r) => r.key === figure.region);
    const box = region && boxOf(`slide${state.slide + 1}.${region.svg}.${figure.index}`);
    figureBar.hidden = !box;
    if (!box) return;
    const words = figure.parts.hint();
    clear(figureBar, words ? h("span.figure-hint", {}, words) : [
      ui.button("Add part", (event) => figure.parts.addPalette(event.currentTarget), { small: true, icon: "plus", kind: "primary", title: "Add a part to the figure (A)", id: undefined }),
      ui.button("Connect", () => figure.parts.toggleConnect(), { small: true, kind: "ghost", icon: "right", title: "Draw a line from one part to another (C)" }),
      ui.button("Group", (event) => figure.parts.groupMenu(event.currentTarget), { small: true, kind: "ghost", icon: "layout", title: "Gather the chosen parts (G)" }),
      figure.parts.selected.length ? ui.button("", () => figure.parts.remove(), { small: true, kind: "ghost", icon: "trash", title: "Delete the chosen parts (⌫)" }) : null,
    ]);
    figureBar.querySelector(".btn.primary")?.classList.add("add");
    figureBar.querySelectorAll(".btn")[2]?.classList.add("group");
    // Over the figure's right end: its left end carries the part's own tag.
    const left = Math.max(4, Math.min(box.left + box.width - figureBar.offsetWidth, pageNode.clientWidth - figureBar.offsetWidth - 4));
    Object.assign(figureBar.style, { left: `${left}px`, top: `${box.top > 44 ? box.top - 40 : box.top + 6}px` });
    stage.classList.toggle("connecting", Boolean(words));
  }

  // -- editing words in place --
  function openInline(target, { selectAll = false } = {}) {
    closeInline();
    const slide = slideAt();
    if (!slide) return;
    let editor, id, bullets = false;
    if (target.kind === "field") {
      const key = target.field;
      if (!catalog.slide_keys[layoutOf(slide)].includes(key)) return;
      editor = ui.markup({ value: slide[key] ?? "", rows: 1, placeholder: { title: "Title", subtitle: "Subtitle", words: "Words", author: "Author" }[key],
        onInput: (text) => editSlide((s) => setOption(s, key, text), { quiet: true, merge: `${state.slide}-${key}` }) });
      id = `slide${state.slide + 1}.${key === "author" ? "byline" : key === "words" ? "title" : key}`;
    } else {
      const block = blocksAt(slide, target.region)[target.index];
      if (!block) return;
      const kind = kindOf(block);
      const at = { region: target.region, index: target.index };
      const merge = `${state.slide}-${at.region}-${at.index}-inline`;
      bullets = kind === "bullets";
      if (bullets) editor = ui.markup({ value: bulletsText(block.bullets), rows: 3, tabs: true, onInput: (text) => editBlock(at, (b) => { b.bullets = bulletsFrom(text); }, { merge }) });
      else if (kind === "code") editor = ui.textarea({ value: block.code, rows: 4, mono: true, onInput: (text) => editBlock(at, (b) => { b.code = text; }, { merge }) });
      else editor = ui.markup({ value: block[kind], rows: 2, onInput: (text) => editBlock(at, (b) => { b[kind] = text; }, { merge }) });
      const region = regionsOf(slide).find((r) => r.key === at.region);
      id = `slide${state.slide + 1}.${region.svg}.${at.index}`;
      state.focus = at;
      renderInspector();
      placeChosen();
      reportFocus();
    }
    const area = editor.area || editor;
    const node = h("div.inline-editor", { onmousedown: (event) => event.stopPropagation() }, editor,
      h("div.inline-foot", {}, h("span", {}, bullets ? "Tab sets a line a level below · " : "", target.kind === "field" ? "Enter or Esc when done" : "Esc when done")));
    area.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeInline(); }
      if (event.key === "Enter" && !event.shiftKey && target.kind === "field") { event.preventDefault(); closeInline(); }
    });
    inline = { node, id };
    center.append(node);
    positionInline();
    area.focus();
    if (selectAll) area.select(); else area.setSelectionRange(area.value.length, area.value.length);
    setTimeout(() => document.addEventListener("mousedown", closeOnOutside, true), 0);
  }

  // The editor floats over the slide, beside the words it edits, and stays put
  // (keeping its caret) when the slide is drawn again underneath it.
  function positionInline() {
    if (!inline || !pageNode?.isConnected) return;
    const outer = center.getBoundingClientRect();
    const slide = pageNode.getBoundingClientRect();
    const box = boxOf(inline.id);
    const width = Math.min(Math.max(box ? box.width : 420, 380), slide.width);
    const left = slide.left - outer.left + Math.max(0, Math.min(box ? box.left : 40, slide.width - width));
    const height = inline.node.offsetHeight || 120;
    const below = slide.top - outer.top + (box ? box.top + box.height + 6 : 60);
    const above = slide.top - outer.top + (box ? box.top - height - 6 : 0);
    const top = below + height > outer.height - 8 && above > 8 ? above : below;
    Object.assign(inline.node.style, { left: `${left}px`, top: `${Math.max(8, top)}px`, width: `${width}px` });
  }
  stage.addEventListener("scroll", () => { if (inline) positionInline(); });

  function closeOnOutside(event) {
    if (inline && !inline.node.contains(event.target)) closeInline();
  }

  function closeInline() {
    if (!inline) return;
    inline.node.remove();
    inline = null;
    document.removeEventListener("mousedown", closeOnOutside, true);
  }

  // Pictures dropped on the slide become picture parts.
  let dropNote = null;
  stage.addEventListener("dragover", (event) => {
    if (![...(event.dataTransfer?.types || [])].includes("Files") || !regionsOf(slideAt()).length) return;
    event.preventDefault();
    if (!dropNote) { dropNote = h("div.drop-note", {}, "Drop pictures to add them to this slide"); center.append(dropNote); }
  });
  stage.addEventListener("dragleave", (event) => { if (!stage.contains(event.relatedTarget)) { dropNote?.remove(); dropNote = null; } });
  stage.addEventListener("drop", async (event) => {
    dropNote?.remove(); dropNote = null;
    const files = [...(event.dataTransfer?.files || [])].filter((file) => /\.(png|jpe?g|svg|gif|webp)$/i.test(file.name));
    if (!files.length) return;
    event.preventDefault();
    for (const file of files) await insertBlock("image", { image: await studio.upload(file) });
    toast(`Added ${files.length} picture${files.length > 1 ? "s" : ""}`, { icon: "image" });
  });

  // -- adding parts --
  async function insertBlock(kind, given = null, where = null) {
    const slide = slideAt();
    const regions = regionsOf(slide);
    if (!regions.length) { toast("This slide's layout has no room for parts: choose another layout first.", { icon: "info" }); return; }
    let block = given || NEW_BLOCKS[kind]();
    if (!given && kind === "image") {
      const path = await chooseFile({ title: "Choose a picture", types: ["image"] });
      if (!path) return;
      block = { image: path };
    } else if (!given && kind === "plot") {
      const target = await chooseFunction();
      if (!target) return;
      block = { plot: target };
    } else if (!given && kind === "gallery") {
      const path = await chooseFile({ title: "The gallery's first picture", types: ["image"] });
      if (!path) return;
      block = { gallery: [path] };
    }
    const anchor = where || state.focus;
    const region = anchor && regions.some((r) => r.key === anchor.region) ? anchor.region : regions[0].key;
    let index = 0;
    editSlide((s) => {
      const list = blocksAt(s, region, true);
      index = anchor?.region === region ? Math.min(anchor.index + 1, list.length) : list.length;
      list.splice(index, 0, block);
    });
    focusBlock(region, index);
    if (INLINE.has(kind) && !given) setTimeout(() => openInline({ kind: "block", region, index }, { selectAll: true }), 300);
  }

  function moveBlock(from, to) {
    editSlide((slide) => {
      const source = blocksAt(slide, from.region, true);
      const [block] = source.splice(from.index, 1);
      const target = blocksAt(slide, to.region, true);
      let index = to.index;
      if (from.region === to.region && from.index < index) index -= 1;
      target.splice(Math.min(index, target.length), 0, block);
      state.focus = { region: to.region, index: Math.min(index, target.length - 1) };
    });
    renderInspector();
    placeChosen();
  }

  function deleteBlock(at) {
    const block = blocksAt(slideAt(), at.region)[at.index];
    const label = block ? BLOCKS[kindOf(block)].label : "part";
    editSlide((s) => { blocksAt(s, at.region).splice(at.index, 1); });
    state.focus = null;
    renderInspector();
    placeChosen();
    reportFocus();
    toast(h("span", {}, `Deleted the ${label.toLowerCase()}. `, h("a", { href: "#", onclick: (event) => { event.preventDefault(); studio.undo(); } }, "Undo")), { icon: "trash", seconds: 5 });
  }

  // -- the inspector --
  function renderInspector() {
    // A figure is edited while it is the part chosen on the slide shown.
    const focus = state.focus;
    if (figure && !(focus && figure.slide === state.slide && focus.region === figure.region && focus.index === figure.index)) leaveFigure(false);
    root.classList.toggle("wide", Boolean(figure && figureBlock() && figure.parts.wantsRoom()));
    keepFocus(inspectorBody, () => {
      const slide = slideAt();
      const block = slide && state.focus && blocksAt(slide, state.focus.region)[state.focus.index];
      if (state.focus && !block) state.focus = null;
      clear(inspectorHead, h("div.insp-tabs", {},
        h(`button.insp-tab${state.tab === "slide" ? ".on" : ""}`, { type: "button", onclick: () => { state.tab = "slide"; renderInspector(); } }, icon("slide"), block ? "Part" : "Slide"),
        h(`button.insp-tab${state.tab === "design" ? ".on" : ""}`, { type: "button", onclick: () => { state.tab = "design"; renderInspector(); } }, icon("palette"), "Design")));
      if (state.tab === "design") clear(inspectorBody, designForm());
      else if (!slide) clear(inspectorBody, h("div.empty", {}, "No slides yet."));
      else if (block && figure && figureBlock() === block && figure.parts.model) clear(inspectorBody, figure.parts.panel());
      else if (block) clear(inspectorBody, blockPanel(slide, block));
      else clear(inspectorBody, slidePanel(slide));
      markBlockErrors();
    });
  }

  function crumbs(slide, block) {
    return h("div.crumbs", {},
      h(`button.crumb${block ? "" : ".here"}`, { type: "button", onclick: () => { state.focus = null; renderInspector(); placeChosen(); reportFocus(); } }, glyph(layoutOf(slide)), `Slide ${state.slide + 1}`),
      block ? [icon("chevron"), h("span.crumb.here", {}, icon(BLOCKS[kindOf(block)].icon), BLOCKS[kindOf(block)].label)] : null);
  }

  function blockPanel(slide, block) {
    const kind = kindOf(block);
    const at = state.focus;
    const regions = regionsOf(slide);
    const count = blocksAt(slide, at.region).length;
    return [
      h("div.section.block-top", {}, crumbs(slide, block),
        h("div.block-actions", {},
          INLINE.has(kind) ? ui.button("Edit on the slide", () => openInline({ kind: "block", ...at }), { small: true, icon: "pencil", title: "Or double-click it (Enter)" }) : null,
          h("span.spacer", { style: { flex: 1 } }),
          ui.button("", () => moveBlock(at, { region: at.region, index: at.index - 1 }), { kind: "ghost", small: true, icon: "up", title: "Move up", disabled: at.index === 0 }),
          ui.button("", () => moveBlock(at, { region: at.region, index: at.index + 2 }), { kind: "ghost", small: true, icon: "down", title: "Move down", disabled: at.index >= count - 1 }),
          ui.button("", () => { editSlide((s) => { const list = blocksAt(s, at.region); list.splice(at.index + 1, 0, structuredClone(list[at.index])); }); focusBlock(at.region, at.index + 1); }, { kind: "ghost", small: true, icon: "copy", title: "Duplicate" }),
          ui.button("", () => deleteBlock(at), { kind: "ghost", small: true, icon: "trash", title: "Delete (⌫)" })),
        regions.length > 1 ? ui.field("In", ui.segmented({ value: at.region, options: regions.map((r) => ({ value: r.key, label: r.label })),
          onChange: (value) => moveBlock(at, { region: value, index: blocksAt(slideAt(), value).length }) })) : null),
      h("div.section.block-form", { dataset: { region: at.region, index: at.index } }, blockForm(block, kind, at)),
    ];
  }

  function slidePanel(slide) {
    const layout = layoutOf(slide);
    const allowed = new Set(catalog.slide_keys[layout]);
    const text = (key, label, { placeholder = "", markup = true, rows = 1 } = {}) => allowed.has(key)
      ? ui.field(label, (markup ? ui.markup : ui.input)({ value: slide[key] ?? "", rows, placeholder, key: `slide.${key}`,
        onInput: (value) => editSlide((s) => setOption(s, key, value), { quiet: true, merge: `${state.slide}-${key}` }) }))
      : null;
    const parts = [
      h("div.section", {}, crumbs(slide, null),
        layout === "statement" ? text("words", "Words", { rows: 2, placeholder: "One sentence, large" }) : text("title", layout === "agenda" ? "Heading" : "Title", { placeholder: layout === "agenda" ? "Outline" : "What this slide says" }),
        text("subtitle", "Subtitle"),
        layout === "title" ? h("div.grid2", {}, text("author", "Author", { markup: false }), text("date", "Date", { markup: false })) : null,
        text("by", "Said by", { markup: false }),
        layout === "agenda" ? h("div.hint-line", {}, "Lists the deck's section slides, wherever they are.") : null),
    ];
    const regions = regionsOf(slide);
    if (regions.length) parts.push(h("div.section", {}, h("div.section-title", {}, "On this slide"), regions.map((region) => regionView(slide, region))));
    parts.push(h("div.section", {}, h("div.section-title", {}, "Layout"), layoutGrid(layout, (name) => changeLayout(name), layouts),
      layout === "two-columns" ? splitControl(slide) : null,
      layout === "columns" ? columnsControls(slide) : null,
      allowed.has("align") ? ui.field("Content sits", ui.segmented({ value: slide.align ?? "", options: [
        { value: "", label: "Deck's" }, { value: "auto", label: "Auto" }, { value: "top", label: "Top" }, { value: "middle", label: "Middle" }],
        onChange: (value) => editSlide((s) => setOption(s, "align", value), { quiet: true }) })) : null));
    parts.push(h("div.section", {}, h("div.section-title", {}, "Background"), backgroundControls(slide, allowed)));
    parts.push(h("div.section", {}, h("div.section-title", {}, "Footnotes"), footnotesControls(slide)));
    return parts;
  }

  function splitControl(slide) {
    const split = slide.split ?? 0.5;
    const value = h("span.value", {}, `${Math.round(split * 100)}%`);
    const range = h("input", { type: "range", min: 0.15, max: 0.85, step: 0.01, value: split, oninput: () => {
      value.textContent = `${Math.round(range.value * 100)}%`;
      editSlide((s) => setOption(s, "split", Number(range.value), 0.5), { quiet: true, merge: `${state.slide}-split` });
    } });
    return ui.field("Left column's share", h("div.slider", {}, range, value));
  }

  function changeLayout(layout) {
    const before = slideAt();
    const blocks = regionsOf(before).map((region) => blocksAt(before, region.key));
    const lost = WORDLESS.has(layout) && blocks.flat().length;
    editSlide((slide) => {
      const all = blocks.flat();
      const words = layoutOf(slide) === "statement" ? slide.words : slide.title;
      for (const key of ["body", "left", "right", "columns", "split", "widths"]) delete slide[key];
      if (layout === "content") delete slide.layout; else slide.layout = layout;
      if (layout === "statement") { if (words) slide.words = words; delete slide.title; }
      else if (words) { slide.title = words; delete slide.words; }
      if (layout === "two-columns") { slide.left = blocks[0] || []; slide.right = blocks.slice(1).flat(); }
      else if (layout === "columns") slide.columns = blocks.length > 1 ? blocks : [all, [], []];
      else if (!WORDLESS.has(layout)) slide.body = all;
      const allowed = new Set(catalog.slide_keys[layout]);
      for (const key of Object.keys(slide)) if (!allowed.has(key)) delete slide[key];
    });
    state.focus = null;
    renderInspector();
    renderBar();
    if (lost) toast(h("span", {}, `A ${LAYOUT_NAMES[layout].toLowerCase()} slide has no parts: they were set aside. `, h("a", { href: "#", onclick: (event) => { event.preventDefault(); studio.undo(); } }, "Undo")), { icon: "info", seconds: 6 });
  }

  function columnsControls(slide) {
    const count = (slide.columns || []).length;
    const widths = slide.widths;
    const setCount = (n) => { editSlide((s) => {
      s.columns ||= [];
      while (s.columns.length < n) s.columns.push([]);
      if (s.columns.length > n) { const extra = s.columns.splice(n).flat(); s.columns[n - 1].push(...extra); }
      if (s.widths) s.widths = Array.from({ length: n }, (_, i) => s.widths[i] ?? 1);
    }); renderInspector(); };
    const stepper = h("div.row", {},
      ui.button("", () => count > 1 && setCount(count - 1), { icon: "minus", small: true, disabled: count <= 1, title: "One column fewer" }),
      h("span", { style: { textAlign: "center", fontWeight: 600 } }, `${count} columns`),
      ui.button("", () => count < 6 && setCount(count + 1), { icon: "plus", small: true, disabled: count >= 6, title: "One column more" }));
    stepper.firstChild.classList.add("fixed"); stepper.lastChild.classList.add("fixed");
    const shares = h("div.row", {}, Array.from({ length: count }, (_, i) => ui.number({ value: widths?.[i] ?? "", placeholder: "1", min: 0.1, step: 0.5, key: `widths.${i}`,
      onChange: (value) => editSlide((s) => {
        const next = Array.from({ length: count }, (_, j) => (j === i ? value : s.widths?.[j]) ?? 1);
        if (next.every((v) => v === 1)) delete s.widths; else s.widths = next;
      }, { quiet: true, merge: `${state.slide}-widths-${i}` }) })));
    return h("div.field", {}, ui.field("Columns", stepper), ui.field("Widths", shares, { hint: "relative, e.g. 2 1 1" }));
  }

  function backgroundControls(slide, allowed) {
    const background = slide.background;
    const mode = !background ? "" : String(background).startsWith("#") ? "colour" : "picture";
    const parts = [ui.segmented({ value: mode, options: [{ value: "", label: "Page" }, { value: "colour", label: "Colour" }, { value: "picture", label: "Picture" }],
      onChange: async (value) => {
        if (value === "") editSlide((s) => { delete s.background; delete s.shade; delete s.dark; });
        else if (value === "colour") editSlide((s) => { s.background = "#1b2a41"; delete s.shade; });
        else {
          const path = await chooseFile({ title: "A picture to fill the slide", types: ["image"] });
          if (path) editSlide((s) => { s.background = path; s.shade = s.shade ?? 0.35; });
        }
        renderInspector();
      } })];
    if (mode === "colour") {
      const swatch = h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(background) ? background : "#1b2a41", style: { width: "44px", height: "30px", border: 0, background: "none", padding: 0 },
        oninput: () => { hex.value = swatch.value; editSlide((s) => { s.background = swatch.value; }, { quiet: true, merge: `${state.slide}-bg` }); } });
      const hex = ui.input({ value: background, mono: true, key: "background", onInput: (value) => { if (/^#[0-9a-f]{3,8}$/i.test(value)) { if (value.length === 7) swatch.value = value; editSlide((s) => { s.background = value; }, { quiet: true, merge: `${state.slide}-bg` }); } } });
      parts.push(h("div.row", {}, h("div.fixed", {}, swatch), hex));
    }
    if (mode === "picture") {
      parts.push(fileRow(background, ["image"], (path) => editSlide((s) => { s.background = path; }), "A picture file"));
      const shade = slide.shade ?? 0;
      const value = h("span.value", {}, `${Math.round(shade * 100)}%`);
      const range = h("input", { type: "range", min: 0, max: 0.9, step: 0.05, value: shade, oninput: () => {
        value.textContent = `${Math.round(range.value * 100)}%`;
        editSlide((s) => setOption(s, "shade", Number(range.value), 0), { quiet: true, merge: `${state.slide}-shade` });
      } });
      parts.push(ui.field("Darken", h("div.slider", {}, range, value)));
    }
    if (mode && allowed.has("dark")) {
      parts.push(ui.field("Words", ui.segmented({ value: slide.dark === true ? "light" : slide.dark === false ? "dark" : "", options: [
        { value: "", label: "Auto" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }],
        onChange: (value) => editSlide((s) => setOption(s, "dark", value === "light" ? true : value === "dark" ? false : null), { quiet: true }) })));
    }
    return h("div", { style: { display: "grid", gap: "8px" } }, parts);
  }

  function footnotesControls(slide) {
    const list = Array.isArray(slide.footnotes) ? slide.footnotes : slide.footnotes ? [slide.footnotes] : [];
    const rows = list.map((note, i) => h("div.list-row", {},
      ui.markup({ value: note, key: `footnote.${i}`, placeholder: "A reference, small at the foot", onInput: (value) => editSlide((s) => { s.footnotes = [...list]; s.footnotes[i] = value; }, { quiet: true, merge: `${state.slide}-fn-${i}` }) }),
      ui.button("", () => { editSlide((s) => { const next = list.filter((_, j) => j !== i); if (next.length) s.footnotes = next; else delete s.footnotes; }); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, title: "Remove" })));
    rows.forEach((row) => { row.firstChild.style.flex = "1"; });
    return h("div.list-rows", {}, rows,
      h("div", {}, ui.button("Footnote", () => { editSlide((s) => { s.footnotes = [...list, "[1] Author et al., *Venue* (2026)"]; }); renderInspector(); }, { kind: "ghost", icon: "plus", small: true })));
  }

  // -- the parts of a slide, listed --
  let dragBlock = null;

  function regionView(slide, region) {
    const blocks = blocksAt(slide, region.key);
    const node = h("div.region", { dataset: { region: region.key },
      ondragover: (event) => { if (dragBlock) { event.preventDefault(); node.classList.add("drop-target"); } },
      ondragleave: (event) => { if (!node.contains(event.relatedTarget)) node.classList.remove("drop-target"); },
      ondrop: (event) => {
        node.classList.remove("drop-target");
        if (!dragBlock || event.defaultPrevented) return;
        event.preventDefault();
        moveBlock(dragBlock, { region: region.key, index: blocks.length });
      } },
    regionsOf(slide).length > 1 ? h("div.region-head", {}, region.label) : null,
    h("div.blocks", {}, blocks.map((block, index) => blockRow(block, region, index)),
      h("button.add-row", { type: "button", onclick: (event) => menu(event.currentTarget, Object.entries(BLOCKS).map(([kind, info]) => ({
        icon: info.icon, label: info.label, hint: info.hint, run: () => insertBlock(kind, null, { region: region.key, index: blocks.length - 1 }),
      }))) }, icon("plus"), "Add a part")));
    return node;
  }

  function blockRow(block, region, index) {
    const kind = kindOf(block);
    const at = { region: region.key, index };
    const node = h("div.block-row", { dataset: { region: region.key, index }, onclick: () => focusBlock(region.key, index), draggable: true,
      ondragstart: (event) => { dragBlock = at; node.classList.add("dragging"); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", kind); },
      ondragend: () => { dragBlock = null; node.classList.remove("dragging"); },
      ondragover: (event) => {
        if (!dragBlock) return;
        event.preventDefault();
        const box = node.getBoundingClientRect();
        node.classList.remove("drop-before", "drop-after");
        node.classList.add(event.clientY > box.top + box.height / 2 ? "drop-after" : "drop-before");
      },
      ondragleave: () => node.classList.remove("drop-before", "drop-after"),
      ondrop: (event) => {
        if (!dragBlock) return;
        event.preventDefault();
        const after = node.classList.contains("drop-after");
        node.classList.remove("drop-before", "drop-after");
        moveBlock(dragBlock, { region: region.key, index: index + (after ? 1 : 0) });
      },
      onmouseenter: () => place(hover, boxOf(`slide${state.slide + 1}.${region.svg}.${index}`), BLOCKS[kind].label),
      onmouseleave: () => { hover.hidden = true; } },
    h("span.kind", {}, icon(BLOCKS[kind].icon)),
    h("span.summary", {}, h("span.what", {}, BLOCKS[kind].label), h("span.words", {}, summary(block))),
    icon("chevron"));
    return node;
  }

  function markBlockErrors() {
    for (const message of messages) {
      const where = placeOf(message.where);
      if (!where || where.slide !== state.slide || where.region === null || message.severity !== "error") continue;
      inspectorBody.querySelector(`.block-row[data-region="${where.region}"][data-index="${where.index}"]`)?.classList.add("error");
      const form = inspectorBody.querySelector(`.block-form[data-region="${where.region}"][data-index="${where.index}"]`);
      if (form && !form.querySelector(".block-error")) form.prepend(h("div.block-error", {}, icon("error"), message.text));
    }
  }

  // -- the form for each kind of part --
  function blockForm(block, kind, at) {
    const merge = (name) => `${state.slide}-${at.region}-${at.index}-${name}`;
    const key = (name) => `block.${name}`;
    const set = (name, fallback) => (value) => editBlock(at, (b) => setOption(b, name, value, fallback), { merge: merge(name) });
    const edit = (mutate, name) => editBlock(at, mutate, { merge: merge(name) });
    const size = () => ui.field("Size", ui.number({ value: block.size, placeholder: "auto", min: 4, step: 1, key: key("size"), onChange: set("size") }), { hint: "pt" });
    const toneSwatches = (name, { none = true, extra = [], fallback } = {}) => {
      const palette = studio.info?.palette || {};
      const colours = [...TONES.map((tone, i) => ({ value: tone, colour: palette[tone] || "#888", title: i === 0 ? "Accent" : `Accent ${i + 1}` })), ...extra];
      return ui.swatches({ value: block[name] ?? fallback ?? null, colours, none, onChange: (value) => editBlock(at, (b) => setOption(b, name, value, fallback)) });
    };
    switch (kind) {
      case "bullets":
        return [ui.markup({ value: bulletsText(block.bullets), rows: 3, tabs: true, key: key("bullets"), placeholder: "One item per line",
          onInput: (text) => edit((b) => { b.bullets = bulletsFrom(text); }, "items") }),
        h("div.hint-line", {}, "One item per line. ", h("kbd", {}, "Tab"), " sets a line a level below."),
        h("div.row", {}, ui.toggle({ value: block.numbered, label: "Numbered", onChange: set("numbered", false) }),
          ui.toggle({ value: block.reveal, label: "One at a time", onChange: set("reveal", false) })),
        size()];
      case "text":
        return [ui.markup({ value: block.text, rows: 2, key: key("text"), onInput: (text) => edit((b) => { b.text = text; }, "text") }),
          ui.field("Align", ui.segmented({ value: block.align || "start", options: [
            { value: "start", label: "Left" }, { value: "middle", label: "Centre" }, { value: "end", label: "Right" }],
          onChange: (value) => editBlock(at, (b) => setOption(b, "align", value, "start")) })),
          ui.field("Colour", toneSwatches("colour", { extra: [{ value: "muted", colour: studio.info?.palette?.muted || "#999", title: "Muted" }] })),
          size()];
      case "quote":
        return [ui.markup({ value: block.quote, rows: 2, key: key("quote"), onInput: (text) => edit((b) => { b.quote = text; }, "quote") }),
          ui.field("Said by", ui.input({ value: block.by, placeholder: "Who", key: key("by"), onInput: set("by") })), size()];
      case "callout":
        return [ui.field("Heading", ui.input({ value: block.title, placeholder: "Optional", key: key("title"), onInput: (text) => edit((b) => setOption(b, "title", text), "title") })),
          ui.field("Words", ui.markup({ value: block.callout, rows: 2, key: key("callout"), onInput: (text) => edit((b) => { b.callout = text; }, "words") })),
          ui.field("Tone", toneSwatches("colour", { none: false, fallback: "accent" })), size()];
      case "code":
        return [ui.textarea({ value: block.code, rows: 5, mono: true, key: key("code"), onInput: (text) => edit((b) => { b.code = text; }, "code") }),
          h("div.hint-line", {}, "Kept as written; whole-line comments are set muted."), size()];
      case "stats": return statsForm(block, at, edit, toneSwatches, size);
      case "table": return tableForm(block, at, edit, size);
      case "image": return imageForm(block, at);
      case "gallery": return galleryForm(block, at, edit, size);
      case "figure": return figureForm(block, at, edit);
      case "plot":
        return [ui.field("Made by", functionInput(block.plot, (value) => edit((b) => { b.plot = value; }, "plot")), { hint: "file.py:function" }),
          h("div.hint-line", {}, "A function returning a matplotlib figure; it runs inside ", h("code", {}, "deck.plotting()"), " and is given the deck if it takes an argument."),
          ui.field("Shape", ui.number({ value: block.aspect, placeholder: "fill the room", min: 0.2, step: 0.1, key: key("aspect"), onChange: set("aspect") }), { hint: "width ÷ height" })];
      default:
        return [h("div.hint-line", {}, "This part has no form yet.")];
    }
  }

  function statsForm(block, at, edit, toneSwatches, size) {
    const items = (Array.isArray(block.stats) ? block.stats : []).map((item) => (Array.isArray(item) ? { value: item[0], label: item[1] } : item && typeof item === "object" ? { ...item } : { value: item, label: "" }));
    const write = () => edit((b) => { b.stats = items.map((item) => ({ ...item })); }, "stats");
    const rows = items.map((item, i) => h("div.list-row", {},
      ui.input({ value: String(item.value ?? ""), placeholder: "93%", key: `stat.${i}.value`, onInput: (value) => { items[i].value = value; write(); } }),
      ui.input({ value: item.label ?? "", placeholder: "what it counts", key: `stat.${i}.label`, onInput: (value) => { items[i].label = value; write(); } }),
      ui.button("", () => { items.splice(i, 1); editBlock(at, (b) => { b.stats = items; }); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, disabled: items.length <= 1 })));
    rows.forEach((row) => { row.firstChild.style.flex = "0 0 96px"; });
    return [h("div.list-rows", {}, rows),
      h("div", {}, ui.button("Number", () => { editBlock(at, (b) => { b.stats = [...items, { value: "1", label: "more" }]; }); renderInspector(); }, { kind: "ghost", icon: "plus", small: true })),
      ui.field("Colour", toneSwatches("colour")), size()];
  }

  function tableForm(block, at, edit, size) {
    const source = Array.isArray(block.table) && block.table.length ? block.table : [[typeof block.table === "string" ? block.table : ""]];
    const rows = source.map((row) => (Array.isArray(row) ? row : [row]).map((cell) => String(cell ?? "")));
    const columns = Math.max(1, ...rows.map((row) => row.length));
    rows.forEach((row) => { while (row.length < columns) row.push(""); });
    const header = block.header !== false;
    const given = alignList(block.align, columns);
    const auto = autoAlign(rows, header);
    const write = () => edit((b) => { b.table = rows.map((row) => [...row]); }, "cells");
    const restructure = (mutate) => { mutate(); editBlock(at, (b) => { b.table = rows.map((row) => [...row]); if (b.align) delete b.align; }); renderInspector(); };
    const input = (r, c) => {
      const cell = h("input", { value: rows[r][c], spellcheck: false, dataset: { key: `cell.${r}.${c}` },
        oninput: () => { rows[r][c] = cell.value; write(); },
        onpaste: (event) => {
          const text = event.clipboardData.getData("text/plain");
          if (!text.includes("\t") && !text.includes("\n")) return;
          event.preventDefault();
          const grid = text.replace(/\r/g, "").replace(/\n$/, "").split("\n").map((line) => line.split("\t"));
          restructure(() => grid.forEach((line, i) => line.forEach((value, j) => {
            while (rows.length <= r + i) rows.push(Array(columns).fill(""));
            rows.forEach((row) => { while (row.length <= c + j) row.push(""); });
            rows[r + i][c + j] = value;
          })));
          toast(`Pasted ${grid.length} × ${Math.max(...grid.map((line) => line.length))} cells`, { icon: "table", seconds: 2 });
        } });
      return cell;
    };
    const alignRow = h("tr", {}, h("th.corner"), Array.from({ length: columns }, (_, c) => h("th", {},
      ui.select({ value: given ? given[c] : "", options: [{ value: "", label: `auto (${auto[c] === "end" ? "right" : "left"})` }, { value: "start", label: "left" }, { value: "middle", label: "centre" }, { value: "end", label: "right" }],
        onChange: (value) => editBlock(at, (b) => {
          const next = given ? [...given] : [...auto];
          next[c] = value || auto[c];
          if (next.every((v, i) => v === auto[i])) delete b.align; else b.align = next;
        }) }))), h("th.corner"));
    const table = h("table", {}, alignRow, rows.map((row, r) => h(`tr${header && r === 0 ? ".header" : ""}`, {},
      h("td.corner", {}, r + 1),
      row.map((_, c) => h("td", {}, input(r, c))),
      h("td.corner", {}, rows.length > 1 ? h("button", { type: "button", title: "Remove row", onclick: () => restructure(() => rows.splice(r, 1)) }, icon("close")) : null))),
    h("tr", {}, h("td.corner"), Array.from({ length: columns }, (_, c) => h("td.corner", {}, columns > 1 ? h("button", { type: "button", title: "Remove column", onclick: () => restructure(() => rows.forEach((row) => row.splice(c, 1))) }, icon("close")) : null)), h("td.corner")));
    table.querySelectorAll("th select").forEach((el) => el.classList.remove("select"));
    return [h("div.table-edit.scroll-thin", {}, table),
      h("div.row", {},
        ui.button("Row", () => restructure(() => rows.push(Array(columns).fill(""))), { kind: "ghost", icon: "plus", small: true }),
        ui.button("Column", () => restructure(() => rows.forEach((row) => row.push(""))), { kind: "ghost", icon: "plus", small: true }),
        h("span.spacer", { style: { flex: 1 } })),
      h("div.hint-line", {}, "Paste cells from a spreadsheet into any cell."),
      ui.toggle({ value: header, label: "First row is the header", onChange: (value) => editBlock(at, (b) => setOption(b, "header", value ? null : false)) }),
      size()];
  }

  function imageForm(block, at) {
    const preview = h("img.preview-pic", { src: block.image ? studio.raw(block.image) : "", alt: "", hidden: !block.image });
    return [preview,
      fileRow(block.image, ["image"], (path) => { editBlock(at, (b) => { b.image = path; }, {}); preview.src = studio.raw(path); preview.hidden = false; }, "picture.png"),
      h("div.hint-line", {}, "An SVG is drawn as vectors: native shapes and text in the PowerPoint."),
      ui.field("Width", ui.number({ value: block.width, placeholder: "as wide as fits", min: 10, step: 10, key: "block.width", onChange: (value) => editBlock(at, (b) => setOption(b, "width", value)) }), { hint: "pt" })];
  }

  function galleryForm(block, at, edit, size) {
    const items = (Array.isArray(block.gallery) ? block.gallery : []).map((item) => (typeof item === "string" ? { picture: item, caption: "" } : { picture: item?.picture || "", caption: item?.caption || "" }));
    const write = () => edit((b) => { b.gallery = items.map((item) => (item.caption ? { ...item } : item.picture)); }, "gallery");
    const round = block.crop === "circle";
    const rows = items.map((item, i) => h("div.list-row", {},
      h(`img.pic${round ? ".round" : ""}`, { src: studio.raw(item.picture), alt: "" }),
      h("div", { style: { flex: 1, display: "grid", gap: "4px" } },
        ui.input({ value: item.caption, key: `caption.${i}`, placeholder: "**Name**, Institute", onInput: (value) => { items[i].caption = value; write(); } }),
        h("span.hint-line", {}, item.picture)),
      ui.button("", () => { items.splice(i, 1); write(); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, title: "Remove" })));
    return [h("div.list-rows", {}, rows),
      h("div", {}, ui.button("Picture", async () => {
        const path = await chooseFile({ title: "Add a picture", types: ["image"] });
        if (path) { items.push({ picture: path, caption: "" }); write(); renderInspector(); }
      }, { kind: "ghost", icon: "plus", small: true })),
      h("div.grid2", {},
        ui.field("Columns", ui.number({ value: block.columns, placeholder: "auto", min: 1, step: 1, key: "gallery.columns", onChange: (value) => editBlock(at, (b) => setOption(b, "columns", value)) })),
        ui.field("Height", ui.number({ value: block.height, placeholder: "auto", min: 10, step: 5, key: "gallery.height", onChange: (value) => editBlock(at, (b) => setOption(b, "height", value)) }), { hint: "pt" })),
      ui.field("Crop", ui.segmented({ value: block.crop || "", options: [{ value: "", label: "None" }, { value: "circle", label: "Circle" }, { value: "square", label: "Square" }],
        onChange: (value) => { editBlock(at, (b) => setOption(b, "crop", value)); renderInspector(); } })),
      size()];
  }

  function figureForm(block, at, edit) {
    const value = block.figure;
    const mode = typeof value === "string" ? (value.includes(".py:") ? "python" : "file") : "inline";
    const parts = [ui.field("Made from", ui.segmented({ value: mode, options: [
      { value: "inline", label: "Here" }, { value: "file", label: "A figure file" }, { value: "python", label: "Python" }],
    onChange: async (next) => {
      if (next === mode) return;
      if (next === "inline") editBlock(at, (b) => { b.figure = NEW_BLOCKS.figure().figure; });
      else if (next === "file") {
        const path = await chooseFile({ title: "A flexo figure file", types: ["figure"], create: "figure" });
        if (path) editBlock(at, (b) => { b.figure = path; });
      } else {
        const target = await chooseFunction("A function returning a flexo figure");
        if (target) editBlock(at, (b) => { b.figure = target; });
      }
      renderInspector();
    } }))];
    if (mode === "inline") {
      parts.push(h("div.figure-card", {},
        h("div", {}, h("b", {}, `${(value?.nodes || []).length} parts, ${(value?.edges || []).length} lines`), h("div.hint-line", {}, "Drawn here, in the deck's theme.")),
        ui.button("Edit as a figure", async () => {
          const name = await ask("Give the figure a file of its own", `figures/${value?.figure?.id || "figure"}.yaml`);
          if (!name) return;
          try {
            const made = await createFile(name, "figure", value);
            editBlock(at, (b) => { b.figure = made; });
            renderInspector();
            studio.workspace.open(studio.folder() + made);
          } catch (error) { toast(error.message, { kind: "error", icon: "error" }); }
        }, { icon: "external", title: "Move it to a figure file and open the figure editor" })));
      const area = ui.textarea({ value: JSON.stringify(value, null, 2), rows: 8, mono: true, key: "figure.json", onInput: (text) => {
        try { const parsed = JSON.parse(text); area.style.borderColor = ""; edit((b) => { b.figure = parsed; }, "figure"); }
        catch { area.style.borderColor = "var(--error)"; }
      } });
      area.classList.remove("grow"); area.style.maxHeight = "300px"; area.style.overflow = "auto";
      parts.push(h("details.more", {}, h("summary", {}, icon("chevron"), "Its document (JSON)"), h("div.inner", {}, area)));
    } else if (mode === "file") {
      parts.push(fileRow(value, ["figure"], (path) => { editBlock(at, (b) => { b.figure = path; }); }, "figure.yaml"),
        h("div", {}, ui.button("Open in the figure editor", () => studio.workspace.open(studio.folder() + value), { icon: "external" })),
        h("div.hint-line", {}, "Changes there are drawn here as they happen."));
    } else {
      parts.push(functionInput(value, (text) => edit((b) => { b.figure = text; }, "figure")),
        h("div.hint-line", {}, "A function returning a ", h("code", {}, "flexo.Figure"), "; it runs again when its file changes."));
    }
    parts.push(ui.toggle({ value: block.turn !== false, label: "May turn to fit the slide", onChange: (on) => editBlock(at, (b) => setOption(b, "turn", on ? null : false)) }));
    return parts;
  }

  // -- files --
  function fileRow(value, types, onChoose, placeholder) {
    const input = ui.input({ value: value || "", placeholder, mono: true, onChange: (text) => text && onChoose(text) });
    return h("div.list-row", {}, input,
      ui.button("", async () => { const path = await chooseFile({ title: "Choose a file", types }); if (path) { input.value = path; onChoose(path); } }, { icon: "folder", small: true, title: "Choose…" }));
  }

  function functionInput(value, onInput) {
    const input = ui.input({ value: value || "", placeholder: "plots.py:loss", mono: true, key: "function", onInput });
    studio.files(["python"]).then((files) => {
      const id = `py-${Math.random().toString(36).slice(2)}`;
      input.setAttribute("list", id);
      input.after(h("datalist", { id }, files.map((file) => h("option", { value: `${file}:` }))));
    });
    return input;
  }

  function chooseFile({ title, types, create }) {
    return new Promise((resolve) => {
      let done = false;
      const finish = (value) => { if (!done) { done = true; resolve(value); box.close(); } };
      const list = h("div.list-rows", {}, h("div.empty", {}, h("div.spinner")));
      const upload = h("input", { type: "file", accept: types.includes("image") ? "image/*,.svg" : types.includes("structure") ? ".pdb,.cif,.mmcif,.ent" : ".yaml,.yml,.json", hidden: true,
        onchange: async () => { const file = upload.files[0]; if (file) finish(await studio.upload(file)); } });
      const actions = [];
      if (types.includes("image") || types.includes("figure")) actions.push({ label: "Upload…", run: () => { upload.click(); return false; } });
      if (create === "figure") actions.push({ label: "New figure file…", run: () => {
        ask("Name the new figure file", "figures/figure.yaml").then(async (name) => {
          if (!name) return;
          try { const made = await createFile(name, "figure"); finish(made); studio.workspace.open(studio.folder() + made, { activate: false }); }
          catch (error) { toast(error.message, { kind: "error", icon: "error" }); }
        });
        return false;
      } });
      actions.push({ label: "Cancel", run: () => finish(null) });
      const box = dialog({ title, body: [list, upload], actions, onClose: () => finish(null) });
      studio.files(types).then((files) => {
        const shown = files.filter((file) => file !== studio.file.split("/").pop());
        clear(list, shown.length ? shown.map((file) => h("button.menu-item", { type: "button", onclick: () => finish(file) },
          types.includes("image") ? h("img.pic", { src: studio.raw(file), alt: "" }) : icon(types.includes("python") ? "code" : "figure"),
          h("span.menu-text", {}, h("span", {}, file.split("/").pop()), h("span.menu-hint", {}, file))))
          : h("div.empty", {}, "No files of this kind beside the deck yet."));
      });
    });
  }

  function chooseFunction(title = "A Python function") {
    return new Promise((resolve) => {
      let value = "";
      const input = functionInput("", (text) => { value = text; });
      dialog({ title, body: [ui.field("file.py:function", input), h("div.hint-line", {}, "The file sits beside the deck; the function is called when the slide is drawn.")],
        actions: [{ label: "Cancel", run: () => resolve(null) }, { label: "Use it", kind: "primary", run: () => {
          if (!/\.py:\w+$/.test(value.trim())) { input.classList.add("invalid"); return false; }
          resolve(value.trim());
        } }], onClose: () => resolve(null) });
      setTimeout(() => input.focus(), 30);
    });
  }

  function ask(title, placeholder) {
    return new Promise((resolve) => {
      const input = ui.input({ value: placeholder, mono: true });
      input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); resolve(input.value.trim() || null); box.close(); } });
      const box = dialog({ title, body: [input], actions: [{ label: "Cancel", run: () => resolve(null) }, { label: "OK", kind: "primary", run: () => resolve(input.value.trim() || null) }], onClose: () => resolve(null) });
      setTimeout(() => { input.focus(); input.select(); }, 30);
    });
  }

  async function createFile(name, kind, data) {
    const folder = studio.folder();
    const result = await studio.api("/api/new", { file: folder + name, kind, data, client: studio.workspace.client, who: studio.workspace.me });
    await studio.workspace.refreshDocuments();
    return result.file.slice(folder.length);
  }

  // -- the deck's design --
  function designForm() {
    const deck = doc().deck || {};
    const editDeck = (mutate, options = {}) => studio.change((d) => { d.deck ||= {}; mutate(d.deck); }, options);
    const setDeck = (name, fallback) => (value) => editDeck((d) => setOption(d, name, value, fallback), { quiet: true, merge: `deck-${name}` });
    const look = deck.look || "classic";
    const looks = h("div.looks", {}, catalog.looks.map((item) => h(`button.look${item.name === look ? ".on" : ""}`, { type: "button",
      onclick: () => { editDeck((d) => setOption(d, "look", item.name, "classic")); renderInspector(); } },
    lookArt(item.name), h("span.name", {}, item.name), h("span.note", {}, item.note))));
    const themeIsFile = typeof deck.theme === "string" && /\.(ya?ml|json)$/i.test(deck.theme);
    const current = Array.isArray(deck.palette) ? "" : deck.palette || "default";
    const accents = () => Object.entries(studio.info?.palette || {}).filter(([k]) => k.startsWith("accent")).slice(0, 5).map(([, c]) => h("span", { style: { background: c } }));
    const paletteList = h("div.palette-list.scroll-thin", {},
      h(`button.palette-item${current === "default" ? ".on" : ""}`, { type: "button", onclick: () => { editDeck((d) => { delete d.palette; }); renderInspector(); } },
        h("span.palette-row", {}, accents()), h("span.name", {}, "The theme's own")),
      Object.entries(catalog.palettes).map(([name, colours]) => h(`button.palette-item${current === name ? ".on" : ""}`, { type: "button", onclick: () => { editDeck((d) => { d.palette = name; }); renderInspector(); } },
        h("span.palette-row", {}, colours.map((c) => h("span", { style: { background: c } }))), h("span.name", {}, name))));
    const fonts = (name, label, note) => ui.field(label, ui.combo({ value: deck[name] || "", options: catalog.fonts, placeholder: note, key: `deck.${name}`, onChange: setDeck(name) }));
    const lookStyle = catalog.looks.find((item) => item.name === look)?.style || {};
    const changes = deck.style || {};
    const styleRows = catalog.style.map((field) => {
      const fallback = lookStyle[field.name] ?? field.default;
      const setStyle = (value) => editDeck((d) => { d.style ||= {}; setOption(d.style, field.name, value, undefined); if (!Object.keys(d.style).length) delete d.style; }, { quiet: true, merge: `style-${field.name}` });
      let control;
      if (field.kind === "bool") control = ui.select({ value: changes[field.name] === undefined ? "" : String(changes[field.name]), options: [{ value: "", label: `look's (${fallback ? "on" : "off"})` }, { value: "true", label: "on" }, { value: "false", label: "off" }], onChange: (v) => setStyle(v === "" ? null : v === "true") });
      else if (field.kind === "choice") control = ui.select({ value: changes[field.name] ?? "", options: [{ value: "", label: `look's (${fallback})` }, ...field.choices], onChange: (v) => setStyle(v || null) });
      else control = ui.number({ value: changes[field.name], placeholder: String(fallback ?? "theme's"), step: "any", key: `style.${field.name}`, onChange: setStyle });
      const set = changes[field.name] !== undefined;
      return h("div.style-row", {}, h("span.name", {}, h(`span${set ? ".changed" : ""}`, {}, field.name.replace(/_/g, " ")), h("span.note", {}, field.note)), control,
        ui.button("", () => { setStyle(null); renderInspector(); }, { kind: "ghost", icon: "undo", small: true, title: "Back to the look's", disabled: !set }));
    });
    const changed = Object.keys(changes).length;
    return [
      h("div.section", {}, h("div.section-title", {}, "Look"), looks),
      h("div.section", {}, h("div.section-title", {}, "Theme"),
        themeIsFile
          ? h("div.theme-file", {}, icon("theme"), h("span", {}, deck.theme), ui.button("Edit", () => studio.workspace.open(studio.folder() + deck.theme), { small: true, icon: "external" }))
          : h("div.row", {}, ui.select({ value: deck.theme || "paper", options: catalog.themes, onChange: (value) => { editDeck((d) => setOption(d, "theme", value, "paper")); renderInspector(); } }),
            h("div.fixed", {}, ui.button("Customise", () => customiseTheme(deck), { small: true, icon: "pencil", title: "Start a theme file from this one: edit its colours, type, and lines" }))),
        themeIsFile ? h("div", {}, ui.button("Use a built-in theme instead", () => { editDeck((d) => { delete d.theme; }); renderInspector(); }, { kind: "ghost", small: true, icon: "undo" })) : null,
        ui.field("Palette", paletteList)),
      h("div.section", {}, h("div.section-title", {}, "Type"),
        fonts("font", "Words", "the theme's"), fonts("title_font", "Titles and headings", "as the words"), fonts("figure_font", "Figures", "as the words")),
      h("div.section", {}, h("div.section-title", {}, "Deck"),
        ui.field("Footer", ui.markup({ value: deck.footer || "", placeholder: "Group meeting · 2026", colours: false, key: "deck.footer", onInput: setDeck("footer") })),
        ui.field("Name of the outputs", ui.input({ value: deck.id || "", placeholder: "talk", mono: true, key: "deck.id", onInput: setDeck("id") }), { hint: "name.pptx, name.pdf" })),
      h("div.section", {}, h("details.more", { open: changed > 0 }, h("summary", {}, icon("chevron"), `Proportions${changed ? ` · ${changed} changed` : ""}`),
        h("div.inner", {}, styleRows))),
    ];
  }

  async function customiseTheme(deck) {
    const base = deck.theme && !/\.(ya?ml|json)$/i.test(deck.theme) ? deck.theme : "paper";
    const name = await ask("Save the theme as", `${deck.id || "talk"}.theme.yaml`);
    if (!name) return;
    const stem = name.split("/").pop().replace(/\.(ya?ml|json)$/i, "").replace(/\.theme$/i, "");
    try {
      const made = await createFile(name, "theme", { theme: { name: stem, base, description: `The look of ${deck.id || "this deck"}.` } });
      studio.change((d) => { d.deck ||= {}; d.deck.theme = made; });
      renderInspector();
      studio.workspace.open(studio.folder() + made);
      toast("Change the theme here: the deck redraws as you go.", { icon: "theme", seconds: 4 });
    } catch (error) { toast(error.message, { kind: "error", icon: "error" }); }
  }

  // -- presenting --
  function present() {
    if (!pages.length) return;
    let index = state.slide;
    let step = 1;
    const started = Date.now();
    const slideNode = h("div.present-slide");
    const noteNode = h("div");
    const count = h("div.count");
    const clock = h("div.clock");
    const stageNode = h("div.present-stage", {}, slideNode);
    const hint = h("div.present-hint", {}, "→ next · ← back · N notes · Esc to leave");
    const node = h("div.present", {}, stageNode, h("div.present-bar", {}, noteNode, h("div", {}, clock, count)), hint);
    const showNotes = () => node.classList.contains("with-notes");
    const svgAt = (page, number) => {
      if (!page?.svg || page.steps <= 1 || number >= page.steps) return page?.svg || "";
      const parsed = new DOMParser().parseFromString(page.svg, "image/svg+xml");
      parsed.querySelectorAll("[data-flexo-step]").forEach((el) => { if (Number(el.getAttribute("data-flexo-step")) > number) el.remove(); });
      return new XMLSerializer().serializeToString(parsed.documentElement);
    };
    const show = () => {
      const page = pages[index];
      slideNode.innerHTML = svgAt(page, step).replace(/^<\?xml[^>]*>\s*/, "");
      const svg = slideNode.querySelector("svg");
      if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); }
      noteNode.textContent = slides()[index]?.notes || "No notes for this slide.";
      count.textContent = `${index + 1} / ${pages.length}${page?.steps > 1 ? ` · step ${step} of ${page.steps}` : ""}`;
      node.style.setProperty("--notes-h", showNotes() ? `${node.querySelector(".present-bar").offsetHeight}px` : "0px");
    };
    const tick = () => { const s = Math.floor((Date.now() - started) / 1000); clock.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
    const timer = setInterval(tick, 1000);
    tick();
    const next = () => { const page = pages[index]; if (page?.steps > step) step += 1; else if (index < pages.length - 1) { index += 1; step = 1; } show(); };
    const back = () => { if (step > 1) step -= 1; else if (index > 0) { index -= 1; step = pages[index]?.steps || 1; } show(); };
    const leave = () => { clearInterval(timer); document.removeEventListener("keydown", keys, true); node.remove(); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); select(index); };
    const keys = (event) => {
      event.stopPropagation();
      if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(event.key)) { event.preventDefault(); next(); }
      else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(event.key)) { event.preventDefault(); back(); }
      else if (event.key === "Escape") leave();
      else if (event.key.toLowerCase() === "n") { node.classList.toggle("with-notes"); show(); }
      else if (event.key === "Home") { index = 0; step = 1; show(); }
      else if (event.key === "End") { index = pages.length - 1; step = 1; show(); }
    };
    let idle;
    stageNode.addEventListener("mousemove", () => { stageNode.classList.add("pointer"); clearTimeout(idle); idle = setTimeout(() => stageNode.classList.remove("pointer"), 1500); });
    stageNode.addEventListener("click", (event) => (event.clientX < innerWidth / 3 ? back() : next()));
    document.addEventListener("keydown", keys, true);
    document.body.append(node);
    node.requestFullscreen?.().catch(() => {});
    setTimeout(() => { hint.style.opacity = "0"; }, 2500);
    show();
  }

  // -- keys --
  document.addEventListener("keydown", (event) => {
    if (!studio.active) return;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "") || document.querySelector(".scrim, .present, .menu");
    const mod = event.metaKey || event.ctrlKey;
    if (mod && event.key === "Enter") { event.preventDefault(); present(); return; }
    if (typing) return;
    if (figure && figureBlock() && figure.parts.key(event)) return;
    const key = event.key;
    if (mod && key.toLowerCase() === "d") { event.preventDefault(); if (slides().length) duplicateSlide(state.slide); }
    else if (mod) return;
    else if (["ArrowDown", "PageDown"].includes(key) && state.slide < slides().length - 1) { event.preventDefault(); select(state.slide + 1); }
    else if (["ArrowUp", "PageUp"].includes(key) && state.slide > 0) { event.preventDefault(); select(state.slide - 1); }
    else if (key === "Escape" && state.focus) { state.focus = null; leaveFigure(false); renderInspector(); placeChosen(); reportFocus(); }
    else if (key === "Enter" && state.focus) {
      event.preventDefault();
      const block = blocksAt(slideAt(), state.focus.region)[state.focus.index];
      if (block && INLINE.has(kindOf(block))) openInline({ kind: "block", ...state.focus });
    } else if ((key === "Delete" || key === "Backspace") && state.focus) { event.preventDefault(); deleteBlock(state.focus); }
    else if (key.toLowerCase() === "n") { event.preventDefault(); newSlidePopover(newSlideButton); }
  });

  // -- the palette's commands, and following --
  studio.commands = () => [
    ...slides().map((slide, index) => ({ icon: "slide", label: `Slide ${index + 1}: ${slideTitle(slide)}`, run: () => select(index) })),
    ...layouts.map((layout) => ({ icon: "plus", label: `New ${LAYOUT_NAMES[layout.name].toLowerCase()} slide`, hint: layout.note, run: () => addSlide(layout.name, state.slide + 1) })),
    ...(slides().length ? layouts.map((layout) => ({ icon: "layout", label: `Layout: ${LAYOUT_NAMES[layout.name]}`, run: () => changeLayout(layout.name) })) : []),
    ...Object.entries(BLOCKS).map(([kind, info]) => ({ icon: info.icon, label: `Add ${info.label.toLowerCase()}`, hint: info.hint, run: () => insertBlock(kind) })),
    ...catalog.looks.map((look) => ({ icon: "palette", label: `Look: ${look.name}`, hint: look.note, run: () => { studio.change((d) => { d.deck ||= {}; setOption(d.deck, "look", look.name, "classic"); }); renderInspector(); } })),
    { icon: "theme", label: "Customise the theme…", run: () => customiseTheme(doc().deck || {}) },
    { icon: "play", label: "Present", keys: "⌘⏎", run: () => present() },
    { icon: "export", label: "Export PowerPoint", run: () => studio.exportFiles(["pptx"]) },
    { icon: "export", label: "Export PDF", run: () => studio.exportFiles(["pdf"]) },
  ];
  studio.reveal = (where) => {
    if (where?.label === "Design") { state.tab = "design"; renderInspector(); return; }
    if (where?.page && where.page - 1 !== state.slide) select(where.page - 1);
  };

  // -- what happens --
  let lastKey = "";
  studio.on("change", ({ quiet, source, who, before }) => {
    if (state.slide >= slides().length) state.slide = Math.max(0, slides().length - 1);
    pending = true;
    if (source === "remote" && before) flash(before, who);
    if (!quiet) { renderRail(); renderInspector(); renderStage(); renderBar(); }
    if (figure && source !== "edit") {
      if (figureBlock() && editable(figureBlock())) figure.parts.act({ do: "read" }, { select: false });
      else leaveFigure();
    }
    pageNode?.classList.add("pending");
  });
  studio.on("drawing", () => { pending = true; });
  studio.on("drawn", (result) => {
    pending = !result.latest || Boolean(result.unfinished);
    pages = result.pages;
    messages = result.messages || [];
    renderRail();
    renderStage();
    if (figure && typeof figureBlock()?.figure === "string") figure.parts.act({ do: "read" }, { select: false });
    const key = JSON.stringify(studio.info?.palette || {});
    if (key !== lastKey) { lastKey = key; renderInspector(); } else markBlockErrors();
    const deckError = messages.find((m) => m.severity === "error" && !m.page && !placeOf(m.where));
    stage.querySelector(":scope > .deck-error")?.remove();
    if (deckError) stage.prepend(h("div.messages.deck-error", {}, messageView(deckError)));
  });
  studio.workspace.on("presence", () => { if (studio.active) { renderRail(); renderStage(); } });
  studio.on("activate", () => { renderRail(); renderStage(); reportFocus(); });

  function flash(before, who) {
    const old = before.slides || [];
    const changed = slides().map((slide, index) => (same(slide, old[index]) ? -1 : index)).filter((index) => index >= 0);
    const colour = colourOf(who || {});
    requestAnimationFrame(() => {
      for (const index of changed) {
        const frame = railList.querySelector(`.thumb[data-index="${index}"] .frame`);
        if (frame) { frame.style.setProperty("--flash", colour); frame.classList.remove("flash"); void frame.offsetWidth; frame.classList.add("flash"); }
      }
      if (changed.includes(state.slide) && pageNode) {
        pageNode.style.setProperty("--flash", colour);
        pageNode.classList.remove("flash"); void pageNode.offsetWidth; pageNode.classList.add("flash");
      }
    });
  }

  renderRail();
  renderStage();
  renderInspector();
  renderBar();
}

function remembered(key, fallback) {
  try { return localStorage.getItem(`flexo-deck-${key}`) ?? fallback; } catch { return fallback; }
}

function remember(key, value) {
  try { localStorage.setItem(`flexo-deck-${key}`, value); } catch { /* private window */ }
}

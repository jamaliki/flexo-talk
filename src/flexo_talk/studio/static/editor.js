// The deck editor. The slide is where you work: click a part to choose it,
// double-click words to edit them in place, add slides and parts from the bar
// above. The inspector on the right shows what is chosen -- a part, or the
// slide -- and the deck's design. Others' edits (people, agents) arrive live:
// the slides they touch flash in their colour.

import { h, clear, icon, ui, menu, popover, closeMenu, dialog, toast, keepFocus, avatar, colourOf, picture, same, themeField, readable, mathWords } from "/static/studio/studio.js";
import { figureParts, widenLines, fileLabel } from "/static/kinds/figure/parts.js";
import { blockDrop, blockPlan, rearrange } from "/static/kinds/deck/slidedrop.js";
import { richText } from "/static/kinds/deck/richtext.js";

const BLOCKS = {
  text: { icon: "text", label: "Text", hint: "A paragraph of text" },
  bullets: { icon: "list", label: "List", hint: "A bulleted or numbered list" },
  figure: { icon: "figure", label: "Figure", hint: "A diagram of shapes and lines" },
  flow: { icon: "flow", label: "Flow Chart", hint: "Steps and decisions connected by arrows" },
  structure: { icon: "structure", label: "Structure", hint: "A protein structure from a PDB or mmCIF file or a PDB ID, drawn with mol-sketch" },
  image: { icon: "image", label: "Picture", hint: "PNG, JPEG or SVG (SVG stays as vectors)" },
  table: { icon: "table", label: "Table", hint: "Rows and columns with simple rules" },
  stats: { icon: "stats", label: "Numbers", hint: "Key numbers, shown large" },
  quote: { icon: "quote", label: "Quote", hint: "A large quotation with attribution" },
  callout: { icon: "callout", label: "Callout", hint: "A key point on a tinted panel" },
  code: { icon: "code", label: "Code", hint: "Code in a monospace font" },
  gallery: { icon: "gallery", label: "Gallery", hint: "A grid of logos or portraits" },
  plot: { icon: "plot", label: "Plot", hint: "A matplotlib chart from a Python function" },
  math: { icon: "math", label: "Equation", hint: "A LaTeX equation on its own line" },
  mechanism: { icon: "mechanism", label: "Mechanism", hint: "A reaction mechanism from SMILES, with checked curly arrows" },
};
// Flow charts and structures are figures: they are offered by name, and made as figures.
const MAIN_BLOCKS = ["text", "bullets", "figure", "flow", "structure", "image", "table"];
const MORE_BLOCKS = ["math", "mechanism", "stats", "quote", "callout", "code", "gallery", "plot"];

// What an equation's snippet buttons put in: [label, title, LaTeX]; "|" is where the cursor goes.
const MATH_SNIPPETS = [
  ["a⁄b", "Fraction", "\\frac{|}{}"],
  ["√", "Square root", "\\sqrt{|}"],
  ["xⁿ", "Superscript", "^{|}"],
  ["xᵢ", "Subscript", "_{|}"],
  ["Σ", "Sum with limits", "\\sum_{i=1}^{n} |"],
  ["∫", "Integral", "\\int_{a}^{b} | \\, dx"],
  ["( )", "Auto-sizing brackets", "\\left( | \\right)"],
  ["[ ]", "Matrix", "\\begin{bmatrix} | & b \\\\ c & d \\end{bmatrix}"],
  ["{", "Cases", "\\begin{cases} | & x \\ge 0 \\\\ -x & x < 0 \\end{cases}"],
  ["=", "Aligned equations", "|a &= b \\\\\n  &= c"],
  ["α", "Greek letter", "\\alpha|"],
  ["x̂", "Hat", "\\hat{|}"],
  ["Tt", "Text", "\\text{|}"],
];
const INLINE = new Set(["text", "bullets", "quote", "callout", "code", "math"]);
// Parts that are drawn rather than read: they take the right of a slide with words.
const VISUAL = new Set(["figure", "image", "plot", "table", "gallery", "mechanism"]);
// A figure on a slide, exported by itself: what flexo builds of it, or its document.
const FIGURE_EXPORTS = [
  { label: "SVG", formats: ["editable"], hint: "Editable SVG with Inkscape layers and live text" },
  { label: "PDF", formats: ["pdf"], hint: "PDF with embedded fonts" },
  { label: "PNG", formats: ["png"], hint: "PNG image" },
  { label: "YAML", formats: ["yaml"], hint: "Flexo figure file, using the deck's theme" },
];

const LAYOUT_NAMES = {
  content: "Content", "two-columns": "Two Columns", columns: "Columns", figure: "Figure", title: "Title",
  section: "Section", statement: "Statement", agenda: "Agenda", blank: "Blank",
};
const LAYOUT_ORDER = ["content", "two-columns", "columns", "figure", "title", "section", "statement", "agenda", "blank"];
const WORDLESS = new Set(["title", "section", "statement", "agenda"]);
// Objects that are words, which typing over (once chosen) replaces.
const WORDY = new Set(["text", "bullets", "quote", "callout"]);
const TONES = ["accent", "accent2", "accent3", "accent4", "accent5", "accent6"];
const ARROW_INK = "#d466d6";

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

// The words a new deck, slide or object starts with (and the studio's new deck, studio/__init__.py):
// opened, they are chosen whole, to be typed over, rather than edited word by word.
const STARTERS = new Set(["A talk worth giving", "What we found, and why it matters", "What we found", "Your name", "The question",
  "What we asked", "Why it was hard", "and why it still is", "A new slide", "The first point", "The second point", "Two sides",
  "On the left", "On the right.", "Three things", "**One**", "**Two**", "**Three**", "The model", "Part two",
  "One sentence that [matters]{accent}.", "Anything at all.", "A point", "Another point", "A paragraph."]);
const starter = (text) => String(text ?? "").split("\n").every((line) => !line.trim() || STARTERS.has(line.trim()));

const NEW_BLOCKS = {
  bullets: () => ({ bullets: ["A point", "Another point"] }),
  text: () => ({ text: "A paragraph." }),
  figure: () => ({ figure: { figure: { id: `figure-${Date.now().toString(36)}` }, nodes: [
    { id: "x", kind: "text", label: "Input $x$" },
    { id: "model", label: "Model", properties: { tone: "encoder" } },
    { id: "y", kind: "text", label: "Output $y$" }],
    edges: [{ from: "x", to: "model" }, { from: "model", to: "y" }] } }),
  flow: () => ({ figure: { figure: { id: `flow-${Date.now().toString(36)}` }, nodes: [
    { id: "start", kind: "terminal", label: "Start" },
    { id: "step", label: "Do the next step" },
    { id: "check", kind: "decision", label: "Done?" },
    { id: "end", kind: "terminal", label: "End" }],
    edges: [{ from: "start", to: "step" }, { from: "step", to: "check" }, { from: "check", to: "end", label: "yes" }, { from: "check", to: "step", label: "no" }] } }),
  image: () => ({ image: "" }),
  table: () => ({ table: [["Model", "Params", "Score"], ["Baseline", "25.6M", "76.1"], ["Ours", "24.0M", "**81.2**"]] }),
  stats: () => ({ stats: [{ value: "93%", label: "accuracy" }, { value: "4×", label: "faster" }] }),
  quote: () => ({ quote: "Words worth repeating.", by: "Someone wise" }),
  callout: () => ({ callout: "The one thing to remember.", title: "Key point" }),
  code: () => ({ code: "def model(x):\n    # the whole idea\n    return head(encoder(x))" }),
  gallery: () => ({ gallery: [] }),
  plot: () => ({ plot: "" }),
  math: () => ({ math: "\\mathcal{L}(\\theta) = -\\frac{1}{N} \\sum_{i=1}^{N} \\log p_\\theta(y_i \\mid x_i)" }),
  mechanism: () => ({ mechanism: [
    { smiles: "[OH-:5].[CH3:1][C:2](=[O:3])[Cl:4]", arrows: ["5 -> 2", "2=3 -> 3"], reagents: "NaOH" },
    { arrows: ["3 -> 2", "2-4 -> 4"], label: "tetrahedral intermediate" }] }),
};

// A structure file, as a figure's part: named for its file or PDB ID, its id made from that.
const STRUCTURE_FILE = /\.(pdb|cif|mmcif|ent)$/i;
function structureNode(source, taken = new Set()) {
  const stem = source.split("/").pop().replace(STRUCTURE_FILE, "");
  let slug = stem.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase().slice(0, 24) || "structure";
  if (!/^[a-z]/.test(slug)) slug = `pdb-${slug}`;
  let id = slug;
  for (let number = 2; taken.has(id); number += 1) id = `${slug}-${number}`;
  taken.add(id);
  return { id, kind: "structure", label: fileLabel(source), properties: { source } };
}
// Structures on a slide: one after another, an arrow from each to the next.
function structureFigure(sources) {
  const taken = new Set();
  const nodes = sources.map((source) => structureNode(source, taken));
  const edges = nodes.slice(1).map((node, index) => ({ from: nodes[index].id, to: node.id }));
  return { figure: { figure: { id: `structures-${Date.now().toString(36)}` }, nodes, ...(edges.length ? { edges } : {}) } };
}

// -- the document ---------------------------------------------------------------------

const layoutOf = (slide) => slide?.layout || "content";

function regionsOf(slide) {
  const layout = layoutOf(slide);
  if (!slide || WORDLESS.has(layout)) return [];
  if (layout === "two-columns") return [{ key: "left", label: "Left", name: "Left Column", svg: "left" }, { key: "right", label: "Right", name: "Right Column", svg: "right" }];
  if (layout === "columns") return (slide.columns || []).map((_, i) => ({ key: `columns.${i}`, label: `Column ${i + 1}`, name: `Column ${i + 1}`, svg: `column${i + 1}` }));
  const label = layout === "figure" ? "Figure" : "Body";
  return [{ key: "body", label, name: label, svg: "body" }];
}

function blocksAt(slide, key, create = false) {
  if (!slide) return [];
  if (key.startsWith("columns.")) {
    const index = Number(key.split(".")[1]);
    if (create) { slide.columns ||= []; slide.columns[index] ||= []; }
    return slide.columns?.[index] || [];
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
  return readable(String(markup ?? "")).split("\n")[0];
}

function summary(block) {
  const kind = kindOf(block);
  const value = block[kind];
  switch (kind) {
    case "bullets": { const first = (Array.isArray(value) ? value : [value]).find((item) => !Array.isArray(item)); return plain(first) || "Empty list"; }
    case "table": return Array.isArray(value) ? `${count(value.length, "row")} × ${count(Math.max(0, ...value.map((row) => (Array.isArray(row) ? row.length : 1))), "column")}` : "";
    case "stats": return Array.isArray(value) ? value.map((item) => item?.value ?? item?.[0] ?? item).join("  ·  ") : "";
    case "gallery": { const n = Array.isArray(value) ? value.length : 0; return `${n} picture${n === 1 ? "" : "s"}`; }
    case "figure": return typeof value === "string" ? value : count((value?.nodes || []).length, "shape");
    case "image": return value || "No picture chosen";
    case "plot": return value || "No function chosen";
    case "callout": return plain(block.title) || plain(value);
    case "math": return mathWords(value) || "Empty equation";
    case "mechanism": {
      const steps = Array.isArray(value) ? value : [value];
      const first = steps.map((step) => (typeof step === "string" ? step : step?.smiles)).find(Boolean) || "";
      return `${steps.length} step${steps.length === 1 ? "" : "s"} · ${first}`;
    }
    default: return plain(value);
  }
}

const count = (number, word) => `${number} ${word}${number === 1 ? "" : "s"}`;

// Words as a title-style label, "line width" -> "Line Width" (words with capitals of
// their own, "mmCIF", kept); and a key as one, "title_size" -> "Title Size".
const SMALL_WORDS = new Set(["a", "an", "the", "and", "or", "but", "nor", "as", "to", "of", "in", "on", "at", "by", "for", "from", "with", "into", "over", "onto", "upon", "like", "near"]);
function titled(text) {
  const words = String(text ?? "").trim().split(/\s+/).filter(Boolean);
  return words.map((word, i) => (/[A-Z]/.test(word) ? word : i > 0 && i < words.length - 1 && SMALL_WORDS.has(word)
    ? word : word.charAt(0).toUpperCase() + word.slice(1))).join(" ");
}
const keyTitle = (key) => titled(String(key ?? "").replace(/[_.-]+/g, " "));

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
  // The names the catalogue gives layouts, over the ones written here.
  for (const layout of catalog.layouts) if (layout.label) LAYOUT_NAMES[layout.name] = layout.label;
  const lookName = (item) => item?.label || keyTitle(item?.name);
  // A deck style setting's name, and a choice's: as the catalogue names them, else from the key.
  const styleField = (name) => catalog.style?.find((field) => field.name === name);
  const styleName = (name) => styleField(name)?.label || keyTitle(name);
  const choiceName = (name, choice) => styleField(name)?.labels?.[choice] || ({ start: "Left", middle: "Centre", end: "Right" })[choice] || keyTitle(choice);
  // How to work the slide, said under it the first few times the editor is opened, then not.
  const opened = Number(remembered("opened", "0")) || 0;
  remember("opened", String(opened + 1));
  const learning = opened < 5;
  const state = { slide: 0, picked: [], focus: null, field: null, tab: "slide", notes: remembered("notes", "0") === "1" };
  let pages = [];
  let messages = [];
  let mathNotes = null;
  let pending = false;
  let inline = null;
  // A part of the slide being dragged on it, and parts just moved, landing.
  let carry = null;
  let moving = null;
  let landing = null;
  let swallowClick = false;

  // Figures on slides keep their layouts while the deck is changed, and are laid out at
  // their best once it has been still a moment: the page asks the server to settle.
  let settling = false;
  let settleTimer = 0;
  studio.hints = () => ({ focus: state.slide, settle: settling });
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
  const notesArea = ui.textarea({ rows: 3, key: "notes", placeholder: "Click to add speaker notes", onInput: (text) =>
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
  const insertButtons = MAIN_BLOCKS.map((kind) => ui.button(BLOCKS[kind].label, () => insertBlock(kind), { kind: "ghost", icon: BLOCKS[kind].icon, title: `Add ${BLOCKS[kind].label}: ${BLOCKS[kind].hint}` }));
  const moreButton = ui.button("More", (event) => menu(event.currentTarget, MORE_BLOCKS.map((kind) => ({ icon: BLOCKS[kind].icon, label: BLOCKS[kind].label, hint: BLOCKS[kind].hint, run: () => insertBlock(kind) }))), { kind: "ghost", icon: "chevron-down" });
  // Its chevron after the word, as on the layout button: both open a menu.
  moreButton.classList.add("pulldown");
  moreButton.append(moreButton.querySelector("svg"));
  const layoutButton = h("button.btn.ghost.layout-button", { type: "button", title: "Slide layout", onclick: (event) => layoutPopover(event.currentTarget) });
  const newSlideButton = ui.button("Slide", (event) => newSlidePopover(event.currentTarget), { kind: "ghost", icon: "plus", title: "Add Slide" });
  newSlideButton.classList.add("keep-label");
  studio.tools.append(newSlideButton, layoutButton, h("span.sep"), ...insertButtons, moreButton);
  // Export lists what File › Export To does in the Mac app (`studio.exports`); each asks
  // where to save once. A deck with no slides has nothing to present or export.
  const presentButton = ui.button("Present", () => present(), { kind: "ghost", icon: "play" });
  const exportButton = ui.button("Export", (event) => menu(event.currentTarget, studio.exports.map(({ format, label, hint, icon: glyph }) =>
    ({ icon: glyph || "export", label, hint, run: () => studio.exportFiles([format]) })), { align: "end" }), { kind: "ghost", icon: "export" });
  studio.actions.append(presentButton, exportButton);
  const showable = () => {
    const none = !slides().length;
    presentButton.disabled = exportButton.disabled = none;
    presentButton.title = none ? "This deck has no slides to present" : "Present from this slide (⌘↩), or from the start (⌥⌘↩)";
    exportButton.title = none ? "This deck has no slides to export" : "Export to PDF, PowerPoint or images";
  };
  studio.on("change", showable);
  showable();

  const renderBar = () => {
    const slide = slideAt();
    clear(layoutButton, glyph(layoutOf(slide)), h("span.bar-label", {}, LAYOUT_NAMES[layoutOf(slide)] || "Layout"), icon("chevron-down"));
    layoutButton.disabled = !slide;
    const room = regionsOf(slide).length > 0;
    // Greyed out, each says why: the layout has no room (a title slide, a section).
    for (const button of [...insertButtons, moreButton]) {
      button.dataset.title ||= button.title || "More objects";
      button.disabled = !room;
      button.title = room ? button.dataset.title : `The ${LAYOUT_NAMES[layoutOf(slide)] || "slide's"} layout has no room for objects`;
    }
  };

  function layoutPopover(anchor) {
    const slide = slideAt();
    if (!slide) return;
    popover(anchor, [h("div.menu-title", {}, "Layout"), layoutGrid(layoutOf(slide), (name) => { closeMenu(); changeLayout(name); }, layouts)], { className: "layout-menu" });
  }

  function newSlidePopover(anchor, at = state.slide + 1) {
    popover(anchor, [h("div.menu-title", {}, "New Slide"), layoutGrid(null, (name) => { closeMenu(); addSlide(name, at); }, layouts)], { className: "layout-menu" });
  }

  // -- slides --
  function addSlide(layout, at = slides().length) {
    studio.change((d) => { d.slides ||= []; d.slides.splice(at, 0, NEW_SLIDES[layout]()); });
    select(at);
    // Its first words are ready to type over: the title, or a blank slide's text (it draws no title).
    if (layout === "blank") setTimeout(() => openInline({ kind: "block", region: "body", index: 0 }, { selectAll: true }), 300);
    else if (layout !== "agenda") setTimeout(() => openInline({ kind: "field", field: layout === "statement" ? "words" : "title" }, { selectAll: true }), 300);
  }

  function moveSlide(from, to) {
    if (from === to || to < 0 || to >= slides().length) return;
    studio.change((d) => { const [slide] = d.slides.splice(from, 1); d.slides.splice(to, 0, slide); });
    select(to);
  }

  function duplicateSlide(index) {
    if (chosenSlides().length > 1 && chosenSlides().includes(index)) { duplicateSlides(chosenSlides()); return; }
    studio.change((d) => { d.slides.splice(index + 1, 0, structuredClone(d.slides[index])); });
    select(index + 1);
  }

  // Slides chosen together in the slide list (⇧-click a run, ⌘-click one more), in order;
  // else the slide shown.
  const chosenSlides = () => (state.picked.length > 1 ? [...state.picked].sort((a, b) => a - b) : [state.slide]);
  function pickSlide(index, event) {
    if (event.shiftKey && slides().length) {
      const from = Math.min(state.slide, index), to = Math.max(state.slide, index);
      const run = Array.from({ length: to - from + 1 }, (_, n) => from + n);
      select(index);
      state.picked = run;
    } else if (event.metaKey || event.ctrlKey) {
      const now = new Set(chosenSlides());
      if (now.has(index) && now.size > 1) now.delete(index); else now.add(index);
      const shown = now.has(index) ? index : Math.min(...now);
      select(shown);
      state.picked = [...now];
    } else { select(index); return; }
    railList.focus({ preventScroll: true });
    renderRail();
  }
  function duplicateSlides(indices) {
    const last = indices[indices.length - 1];
    studio.change((d) => { d.slides.splice(last + 1, 0, ...indices.map((index) => structuredClone(d.slides[index]))); });
    select(last + 1);
    state.picked = indices.map((_, n) => last + 1 + n);
    renderRail();
  }
  function deleteSlides(indices) {
    if (indices.length === 1) { deleteSlide(indices[0]); return; }
    studio.change((d) => { for (const index of [...indices].sort((a, b) => b - a)) d.slides.splice(index, 1); });
    select(Math.min(indices[0], slides().length - 1));
    undoNote(`${indices.length} slides deleted`);
  }

  // "Slide deleted · Undo": the link takes back that change and no other, and the note
  // goes as soon as anything else changes (an undo with ⌘Z included).
  function undoNote(text, { icon: name = "trash", seconds = 5 } = {}) {
    const entry = studio.past[studio.past.length - 1];
    if (!entry) return;
    let open = true;
    const note = toast(h("span", {}, `${text} · `, h("a", { href: "#", onclick: (event) => {
      event.preventDefault();
      if (open && studio.past[studio.past.length - 1] === entry) studio.undo();
      close();
    } }, "Undo")), { icon: name, seconds });
    const close = () => { open = false; note.remove(); };
    studio.on("change", () => { if (open && studio.past[studio.past.length - 1] !== entry) close(); });
  }

  // A new slide after `index` in its layout (a content slide after a title slide), as
  // Keynote's New Slide does.
  const newSlideLike = (index) => addSlide(layoutOf(slides()[index]) === "title" ? "content" : layoutOf(slides()[index]) || "content", index + 1);

  function deleteSlide(index) {
    studio.change((d) => { d.slides.splice(index, 1); });
    select(Math.min(index, slides().length - 1));
    undoNote("Slide deleted");
  }

  function slideMenu(anchor, index) {
    const count = slides().length;
    // A thumbnail's menu is about its slide -- or the slides chosen with it -- which a
    // right-click chooses, as in Keynote.
    const together = chosenSlides().length > 1 && chosenSlides().includes(index) ? chosenSlides() : null;
    if (!together && (index !== state.slide || state.focus || state.field)) select(index);
    railList.focus({ preventScroll: true });
    const many = together ? ` ${together.length} Slides` : "";
    menu(anchor, [
      { icon: "plus", label: "New Slide…", run: () => newSlidePopover(anchor, (together ? Math.max(...together) : index) + 1) },
      "-",
      ...clipItems(),
      { icon: "copy", label: `Duplicate${many}`, keys: "⌘D", run: () => (together ? duplicateSlides(together) : duplicateSlide(index)) },
      "-",
      ...(!together && index > 0 ? [{ icon: "up", label: "Move Up", run: () => moveSlide(index, index - 1) }] : []),
      ...(!together && index < count - 1 ? [{ icon: "down", label: "Move Down", run: () => moveSlide(index, index + 1) }] : []),
      "-",
      { icon: "trash", label: `Delete${many}`, danger: true, run: () => deleteSlides(together || [index]) },
    ]);
  }

  function select(index, focus = null) {
    closeInline();
    leaveFigure(false);
    state.slide = Math.max(0, Math.min(index, slides().length - 1));
    state.picked = [];
    state.focus = focus;
    state.field = null;
    renderRail();
    renderStage();
    renderInspector();
    renderBar();
    railList.querySelector(".thumb.on")?.scrollIntoView({ block: "nearest" });
    if (pages[state.slide]?.stale) studio.requestDraw(0);
    reportFocus();
    readSlideAhead();
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
      const key = JSON.stringify([index, page?.svg ? page.hash : slideTitle(slide), Boolean(page?.stale), index === state.slide || (state.picked.length > 1 && state.picked.includes(index)),
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
      railList.append(h("button.rail-add", { type: "button", onclick: (event) => newSlidePopover(event.currentTarget, slides().length) }, icon("plus"), "New Slide"));
    } else railList.append(railList.querySelector(":scope > .rail-add"));
  }

  function thumbNode(slide, index, page, own, worst, here) {
    const clearDrops = () => railList.querySelectorAll(".drop-before,.drop-after").forEach((el) => el.classList.remove("drop-before", "drop-after"));
    const on = index === state.slide || (state.picked.length > 1 && state.picked.includes(index));
    const node = h(`div.thumb${on ? ".on" : ""}${page?.stale ? ".stale" : ""}`, {
      draggable: true, dataset: { index },
      onclick: (event) => pickSlide(index, event),
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
      page?.steps > 1 ? h("div.steps", { title: "Items appear one at a time" }, `${page.steps} steps`) : null,
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
    if (event.target !== railList || state.focus || state.field) return;
    if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); if (slides().length) deleteSlides(chosenSlides()); }
  });
  // Keys go to what was chosen last: once something on the slide is chosen, not the slides.
  const offRail = () => { if (railList.contains(document.activeElement)) document.activeElement.blur(); };

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
    notesPreview.textContent = slide?.notes ? plain(slide.notes) : "Click to add speaker notes";
    notesPreview.classList.toggle("empty", !slide?.notes);
    notes.hidden = !list.length;
    if (!list.length) {
      clear(stage, h("div.stage-empty", {}, h("h2", {}, "No slides"), h("div", {}, "Choose a layout for the first slide:"),
        h("div.layout-grid.big", {}, layouts.map((layout) => h("button.layout-card", { type: "button", onclick: () => addSlide(layout.name, 0) },
          glyph(layout.name), h("span.name", {}, LAYOUT_NAMES[layout.name]), h("span.note", {}, layout.note))))));
      return;
    }
    const page = pages[state.slide];
    // The slide's drawing is put in the page again only when it changed: parsing
    // and laying out an SVG is the costliest thing the stage does.
    const shows = page?.svg ? `${state.slide}:${page.hash}` : "";
    let before = null, moved = null;
    if (!pageNode || pageNode.dataset.shows !== shows) {
      // A figure's parts just moved on this slide: they land from where they were.
      before = figureBlock() ? figure.parts.landing() : null;
      // So do the slide's own parts, just moved or swapped.
      moved = blockLanding();
      landing = null;
      if (carry) dropCarry();
      pageNode = h("div.slide-page", { dataset: { shows } });
      if (page?.svg) pageNode.innerHTML = page.svg.replace(/^<\?xml[^>]*>\s*/, "");
      else pageNode.append(h("div.placeholder", {}, h("div.spinner")));
      const svg = pageNode.querySelector("svg");
      if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); svg.setAttribute("preserveAspectRatio", "xMidYMid meet"); }
      if (svg) widenLines(svg);
      // What the pointer was over has moved, or gone: shown again when it moves.
      hover.hidden = true;
      pageNode.append(hover, chosen);
      pageNode.addEventListener("mousemove", onHover);
      pageNode.addEventListener("mouseleave", () => { hover.hidden = true; });
      pageNode.addEventListener("click", onPick);
      pageNode.addEventListener("dblclick", onEdit);
      pageNode.addEventListener("contextmenu", onContext);
      pageNode.addEventListener("pointerdown", onPress);
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
      pending ? h("span.row.drawing", {}, h("span.spinner"), "Updating…") : learning ? h("span.stage-hint", {}, "Click to select · Drag to move · Double-click to edit text") : null);
    clear(stageMessages, own.map(messageView));
    stageMessages.hidden = !own.length;
    fitStage();
    placeChosen();
    if (inline) positionInline();
    if (figureMarks.parentNode !== pageNode) pageNode.append(figureMarks, figureBar);
    placeFigure();
    figure?.parts.placeInline();
    if (before && figureBlock()) figure.parts.land(before);
    if (moved) landBlocks(moved);
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
    if (part.kind === "field") return { title: "Title", subtitle: "Subtitle", byline: "Byline" }[part.field] || "Text";
    const block = blocksAt(slideAt() || {}, part.region)[part.index];
    return block ? BLOCKS[kindOf(block)].label : "";
  }

  function onHover(event) {
    if (figure?.parts.inline) hover.hidden = true;
    if (figure?.parts.dragging || carry?.started || inline || figure?.parts.inline) return;
    if (inFigure(event)) {
      const id = figure.parts.idAt(event);
      const box = id && figure.parts.model ? boxOf(figurePrefix() + id) : null;
      place(hover, box, id ? figure.parts.nameOf(id) : "");
      return;
    }
    const part = partAt(event);
    // A figure's parts are shown one by one, as they will be chosen: by the first click.
    const inner = part && figurePartAt(event, part);
    if (inner) { place(hover, boxOf(inner.element.id), inner.name); return; }
    place(hover, part && boxOf(part.id), part ? labelOf(part) : "");
  }

  // A part of the chosen figure, pressed and moved, is dragged to another place in it;
  // the figure itself -- pressed where none of its parts is, or before it is chosen, or
  // when it has one part only -- and any other part of the slide, to another place on the slide.
  function onPress(event) {
    if (event.target.closest(".fig-inline, .figure-bar")) return;
    if (figureBlock() && editable(figureBlock()) && inFigure(event) && figure.parts.model) {
      // A molecule chosen is grabbed to turn it.
      if (figure.parts.turnable(event)) { figure.parts.pointerdown(event); return; }
      const id = figure.parts.idAt(event);
      const holder = id && figure.parts.parentOf(id);
      const alone = holder?.id === figure.parts.model.root && (holder.children || []).length < 2;
      if (figure.parts.connecting || (id && holder && !alone)) { figure.parts.pointerdown(event); return; }
    }
    pressBlock(event, partAt(event));
  }

  // -- the slide's parts, moved on it --
  // A part pressed and moved is lifted and follows the pointer. Over the middle of
  // another part, the two swap: that one slides over to where this one was, and a frame
  // shows where this one lands. Near another part's top or bottom, it goes between them:
  // a line shows where, and the parts either side step apart for it. Over an empty
  // column, it goes into it. Let go, the slide is changed -- an edit like any other, ⌘Z
  // undoes it -- and when it is drawn again each part glides from where it was. Esc, or
  // letting go anywhere else, sends it home.
  const SVG_NS = "http://www.w3.org/2000/svg";
  // Parts are set from their top left, as words are: one goes where another was by it.
  const cornerOf = (box) => ({ x: box.left, y: box.top });
  const scaleOf = (element) => 1 / (element?.parentNode?.getScreenCTM?.()?.a || 1);
  const drawnBox = (element) => { const box = element?.getBoundingClientRect(); return box && (box.width || box.height) ? box : null; };
  const samePlace = (a, b) => a?.region === b?.region && a?.index === b?.index;

  // What is moved: a group round the part's drawing, so its own transform (an image's
  // scale, say) stays its own.
  function mover(element) {
    const parent = element.parentNode;
    if (parent?.classList?.contains("block-mover")) return parent;
    const wrap = document.createElementNS(SVG_NS, "g");
    wrap.setAttribute("class", "block-mover");
    parent.insertBefore(wrap, element);
    wrap.append(element);
    return wrap;
  }
  function blockElement(region, index) {
    const found = regionsOf(slideAt()).find((item) => item.key === region);
    return found && pageNode ? pageNode.querySelector(`[id="slide${state.slide + 1}.${found.svg}.${index}"]`) : null;
  }
  // A region's room on screen, from the box the slide's drawing gives it (in its parent's units).
  function roomOf(group) {
    const values = (group?.getAttribute("data-flexo-box") || "").split(" ").map(Number);
    const matrix = group?.parentNode?.getScreenCTM?.();
    if (values.length !== 4 || values.some(Number.isNaN) || !matrix) return null;
    const [x, y, width, height] = values;
    const a = new DOMPoint(x, y).matrixTransform(matrix), b = new DOMPoint(x + width, y + height).matrixTransform(matrix);
    return { left: Math.min(a.x, b.x), top: Math.min(a.y, b.y), right: Math.max(a.x, b.x), bottom: Math.max(a.y, b.y) };
  }
  function regionsDrawn() {
    const slide = slideAt();
    return regionsOf(slide).map((region) => ({
      key: region.key,
      label: region.label,
      name: region.name,
      room: roomOf(pageNode?.querySelector(`[id="slide${state.slide + 1}.${region.svg}"]`)),
      blocks: blocksAt(slide, region.key).map((block, index) => {
        const element = blockElement(region.key, index);
        return { index, label: BLOCKS[kindOf(block)].label, element, box: drawnBox(element) };
      }),
    }));
  }

  function pressBlock(event, part) {
    if (event.button !== 0 || event.shiftKey || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!part || part.kind !== "block" || carry || figure?.parts.dragging) return;
    const element = blockElement(part.region, part.index);
    if (!element) return;
    carry = { from: { region: part.region, index: part.index }, start: { x: event.clientX, y: event.clientY }, started: false, element, frame: 0, at: null };
    window.addEventListener("pointermove", carryMove);
    window.addEventListener("pointerup", carryEnd);
    window.addEventListener("pointercancel", carryCancel);
    window.addEventListener("keydown", carryKey, true);
  }

  function carryStart() {
    closeInline();
    window.getSelection?.()?.removeAllRanges();
    hover.hidden = true;
    const regions = regionsDrawn();
    const home = drawnBox(carry.element);
    if (!home) { dropCarry(); return; }
    const lifted = mover(carry.element);
    lifted.classList.add("block-lifted");
    const zone = h("div.block-drop-zone", {}, h("span.hit-label"));
    const line = h("div.block-drop-line");
    pageNode.append(zone, line);
    pageNode.classList.add("block-dragging");
    document.body.classList.add("block-grabbing");
    Object.assign(carry, { started: true, regions, home, lifted, scale: scaleOf(lifted), zone, line, shifted: [] });
  }

  function carryMove(event) {
    if (!carry) return;
    carry.pointer = { x: event.clientX, y: event.clientY };
    if (!carry.started) {
      if (Math.hypot(event.clientX - carry.start.x, event.clientY - carry.start.y) < 4) return;
      carryStart();
      if (!carry) return;
    }
    event.preventDefault();
    if (!carry.frame) carry.frame = requestAnimationFrame(carryFrame);
  }

  function carryFrame() {
    if (!carry?.started) return;
    carry.frame = 0;
    const dx = carry.pointer.x - carry.start.x, dy = carry.pointer.y - carry.start.y;
    carry.lifted.style.transform = `translate(${dx * carry.scale}px, ${dy * carry.scale}px)`;
    const at = dropAt(carry.pointer);
    if (JSON.stringify(at) !== JSON.stringify(carry.at)) { carry.at = at; showDrop(at); }
  }

  const dropAt = (point) => blockDrop(carry.regions, carry.from, point);

  function showDrop(at) {
    for (const wrap of carry.shifted) wrap.style.transform = "";
    carry.shifted = [];
    carry.zone.classList.remove("on");
    carry.line.classList.remove("on");
    carry.lifted.classList.toggle("block-astray", !at);
    if (!at || at.kind === "home") return;
    const origin = pageNode.getBoundingClientRect();
    // A mark not shown yet appears where it goes; one shown glides there.
    const put = (node, box, pad = 0) => {
      Object.assign(node.style, { left: `${box.left - origin.left - pad}px`, top: `${box.top - origin.top - pad}px`,
        width: `${box.right - box.left + 2 * pad}px`, height: `${box.bottom - box.top + 2 * pad}px` });
      if (!node.classList.contains("on")) void node.offsetWidth;
    };
    const region = carry.regions.find((item) => item.key === at.region);
    const shift = (block, x, y) => {
      const wrap = mover(block.element);
      const scale = scaleOf(wrap);
      wrap.style.transform = `translate(${x * scale}px, ${y * scale}px)`;
      carry.shifted.push(wrap);
    };
    if (at.kind === "swap") {
      // The part there slides to where this one was; this one lands where it is.
      const target = region.blocks[at.index];
      const there = cornerOf(target.box), home = cornerOf(carry.home);
      shift(target, home.x - there.x, home.y - there.y);
      put(carry.zone, target.box, 6);
      carry.zone.firstChild.textContent = `Swap with ${target.label.toLowerCase()}`;
      carry.zone.classList.add("on");
    } else if (at.kind === "into") {
      put(carry.zone, region.room, 4);
      carry.zone.firstChild.textContent = `Move to ${region.name.toLowerCase()}`;
      carry.zone.classList.add("on");
    } else {
      const isFrom = (block) => region.key === carry.from.region && block.index === carry.from.index;
      const placed = region.blocks.filter((block) => block.box && !isFrom(block));
      const above = placed.filter((block) => block.index < at.index).at(-1);
      const below = placed.find((block) => block.index >= at.index);
      const y = above && below ? (above.box.bottom + below.box.top) / 2 : above ? above.box.bottom + 8 : below ? below.box.top - 8 : region.room.top + 8;
      const span = region.room || (above || below).box;
      put(carry.line, { left: span.left, right: span.right, top: y - 1.5, bottom: y + 1.5 });
      carry.line.classList.add("on");
      if (above) shift(above, 0, -7);
      if (below) shift(below, 0, 7);
    }
  }

  // The drag over: listeners off, marks gone; what it was is returned (null for a click).
  function finishCarry() {
    window.removeEventListener("pointermove", carryMove);
    window.removeEventListener("pointerup", carryEnd);
    window.removeEventListener("pointercancel", carryCancel);
    window.removeEventListener("keydown", carryKey, true);
    const was = carry;
    carry = null;
    if (!was?.started) return null;
    if (was.frame) cancelAnimationFrame(was.frame);
    was.zone.remove();
    was.line.remove();
    pageNode?.classList.remove("block-dragging");
    document.body.classList.remove("block-grabbing");
    was.lifted.classList.remove("block-lifted", "block-astray");
    // The drag ends in a click on whatever is under the pointer: that click is not one.
    swallowClick = true;
    setTimeout(() => { swallowClick = false; }, 0);
    return was;
  }
  // Its drawing is going (drawn again under it): let go of it where it is.
  function dropCarry() { finishCarry(); }
  function sendHome(was) {
    for (const wrap of was.shifted) wrap.style.transform = "";
    was.lifted.style.transform = "";
    placeChosen();
  }
  function carryCancel() { const was = finishCarry(); if (was) sendHome(was); }
  function carryKey(event) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    carryCancel();
  }

  function carryEnd(event) {
    if (carry?.started && event) { carry.pointer = { x: event.clientX, y: event.clientY }; carryFrame(); }
    const was = finishCarry();
    if (!was) return;
    const at = was.at;
    if (!at || at.kind === "home") { sendHome(was); return; }
    const { from } = was;
    if (at.kind === "swap") {
      // It glides the rest of the way to where it goes.
      const target = was.regions.find((region) => region.key === at.region).blocks[at.index];
      const there = cornerOf(target.box), home = cornerOf(was.home);
      was.lifted.style.transform = `translate(${(there.x - home.x) * was.scale}px, ${(there.y - home.y) * was.scale}px)`;
    }
    const plan = planOf(from, at);
    moving = { slide: state.slide, at: Date.now(), plan, wraps: [was.lifted, ...was.shifted] };
    chosen.hidden = true;
    // Should no new drawing come (the edit changed nothing after all), the parts go home.
    const mine = moving;
    setTimeout(() => { if (moving === mine) { moving = null; for (const wrap of mine.wraps) wrap.style.transform = ""; placeChosen(); } }, 6000);
    editSlide((slide) => rearrange({ [from.region]: blocksAt(slide, from.region, true), [at.region]: blocksAt(slide, at.region, true) }, from, at),
      { label: movedLabel(from) });
    // It is the part chosen where it lands -- a figure still edited there.
    const landed = plan.find(([old]) => samePlace(old, from))[1];
    focusBlock(landed.region, landed.index);
  }

  // Where each part of the slide goes, as [where it was, where it goes].
  function planOf(from, at) {
    const slide = slideAt();
    return blockPlan(Object.fromEntries(regionsOf(slide).map((region) => [region.key, blocksAt(slide, region.key).length])), from, at);
  }

  // Before the slide is drawn again: where each moved part shows now, by where it goes.
  function blockLanding() {
    const was = moving;
    moving = null;
    if (!was || was.slide !== state.slide || Date.now() - was.at > 6000 || !pageNode) return null;
    const boxes = [];
    for (const [old, now] of was.plan) {
      const box = drawnBox(blockElement(old.region, old.index));
      if (box) boxes.push([now, box]);
    }
    return boxes;
  }
  function landBlocks(boxes) {
    const glides = [];
    for (const [now, was] of boxes) {
      const element = blockElement(now.region, now.index);
      const box = drawnBox(element);
      if (!box) continue;
      const dx = cornerOf(was).x - cornerOf(box).x, dy = cornerOf(was).y - cornerOf(box).y;
      // A part just sized grows or shrinks the rest of the way, too.
      const grown = was.width / (box.width || 1);
      if (Math.hypot(dx, dy) < 0.5 && Math.abs(grown - 1) < 0.01) continue;
      const wrap = mover(element);
      const scale = scaleOf(wrap);
      Object.assign(wrap.style, { transformBox: "fill-box", transformOrigin: "0 0" });
      glides.push(wrap.animate([{ transform: `translate(${dx * scale}px, ${dy * scale}px) scale(${grown})` }, { transform: "translate(0px, 0px) scale(1)" }],
        { duration: 300, easing: "cubic-bezier(.2,.8,.2,1)" }).finished.catch(() => {}));
    }
    // The chosen part's frame waits for the parts to arrive: one drawn while they glide
    // would be drawn where they pass.
    const mine = {};
    landing = mine;
    Promise.all(glides).then(() => { if (landing === mine) { landing = null; placeChosen(); } });
  }

  // -- a figure or picture, sized by its corners --
  // The chosen figure or picture has a handle at each corner. Dragged, it grows or
  // shrinks about the point the slide keeps still as it does -- its middle across; its
  // top, or nearer its middle when it stands alone -- no larger than its place allows.
  // Let go, it is drawn that wide: an edit like any other, ⌘Z undoes it. A handle
  // double-clicked sizes it to its place again.
  const SIZED = new Set(["figure", "image"]);
  const STANDING = new Set(["figure", "mechanism", "image", "plot", "gallery", "quote", "table", "code", "stats"]);
  let sizing = null;
  chosen.append(...["nw", "ne", "sw", "se"].map((corner) => h(`span.size-handle.${corner}`, {
    title: "Drag to resize · Double-click to reset size",
    onpointerdown: (event) => sizeStart(event, corner),
    ondblclick: (event) => { event.stopPropagation(); sizeFit(); },
  })));
  const sizeTip = h("div.size-tip", { hidden: true });

  // Where the slide draws the part at `scale` times its size: centred across its place,
  // and down it as the slide aligns its places (compose.py's `_region_row`): parts with
  // words among them from the top; pictures alone a little above the middle of the body;
  // pictures beside words centred against them while they are the shorter.
  function placerOf(region, regions, box) {
    const slide = slideAt();
    const standing = (item) => item.blocks.length && blocksAt(slide, item.key).every((block) => STANDING.has(kindOf(block)));
    const extent = (item) => {
      const boxes = item.blocks.map((block) => block.box).filter(Boolean);
      return boxes.length ? { top: Math.min(...boxes.map((b) => b.top)), bottom: Math.max(...boxes.map((b) => b.bottom)) } : null;
    };
    const { room } = region, own = extent(region);
    const used = own.bottom - own.top, below = box.top - own.top;
    const align = slide.align || studio.doc?.style?.align || "auto";
    const others = regions.filter((item) => item !== region && item.blocks.length && item.room);
    const tallest = (list, from) => Math.max(0, ...list.map((item) => { const e = extent(item); return e ? e.bottom - from(item, e) : 0; }));
    const words = tallest(others.filter((item) => !standing(item)), (item) => item.room.top);
    const pictures = tallest(others.filter(standing), (_, e) => e.top);
    const height = room.bottom - room.top, centre = (room.left + room.right) / 2;
    const alone = standing(region) && align !== "top";
    return (scale) => {
      const width = box.width * scale, tall = box.height * scale, now = used - box.height + tall;
      let top = own.top;
      if (alone && !words) top = room.top + Math.max(height - now, 0) * (align === "middle" ? 0.5 : 0.4);
      else if (alone) {
        const band = Math.max(now, words, pictures);
        top = room.top + (align === "middle" ? Math.max(height - band, 0) / 2 : 0) + (band - now) / 2;
      }
      return { left: centre - width / 2, top: top + below, width, height: tall };
    };
  }

  function sizeStart(event, corner) {
    if (event.button !== 0 || sizing || carry) return;
    event.preventDefault();
    event.stopPropagation();
    const focus = state.focus;
    const block = focus && blocksAt(slideAt() || {}, focus.region)[focus.index];
    if (!block || !SIZED.has(kindOf(block))) return;
    const element = blockElement(focus.region, focus.index);
    const unit = pageNode?.querySelector("svg")?.getScreenCTM?.()?.a;
    if (!element || !unit) return;
    const wrap = mover(element);
    // It follows the pointer at once, not gliding after it.
    wrap.classList.add("block-sized");
    Object.assign(wrap.style, { transformBox: "fill-box", transformOrigin: "0 0", transform: "" });
    const regions = regionsDrawn();
    const region = regions.find((item) => item.key === focus.region);
    const box = drawnBox(element);
    if (!region?.room || !box) return;
    closeInline();
    hover.hidden = true;
    // No wider than its place, nor taller than the room the parts above and below it leave.
    const across = region.room.right - region.room.left;
    const boxes = region.blocks.map((item) => item.box).filter(Boolean);
    const others = Math.max(...boxes.map((b) => b.bottom)) - Math.min(...boxes.map((b) => b.top)) - box.height;
    const most = Math.max(1, Math.min(across / box.width, (region.room.bottom - region.room.top - others) / box.height));
    const least = Math.min(1, 24 / Math.min(box.width, box.height));
    // Its width as the slide sets it (its ink, not the box round all it draws), in points.
    const points = Number(element.getAttribute("data-flexo-width")) || box.width / unit;
    sizing = { at: { ...focus }, block, wrap, box, corner, most, least, across, unit, points, place: placerOf(region, regions, box),
      scale: 1, moved: false, start: { x: event.clientX, y: event.clientY }, column: regions.length > 1 ? "column" : "slide" };
    pageNode.classList.add("block-sizing");
    if (sizeTip.parentNode !== pageNode) pageNode.append(sizeTip);
    window.addEventListener("pointermove", sizeMove);
    window.addEventListener("pointerup", sizeEnd);
    window.addEventListener("pointercancel", sizeCancel);
    window.addEventListener("keydown", sizeKey, true);
  }

  // The size that puts the corner held nearest the pointer, as the slide will draw it.
  function scaleFor(x, y) {
    const { least, most, place, corner } = sizing;
    const miss = (scale) => {
      const at = place(scale);
      return Math.hypot(x - (corner.endsWith("w") ? at.left : at.left + at.width), y - (corner.startsWith("n") ? at.top : at.top + at.height));
    };
    let best = 1, far = miss(1);
    const steps = 160, ratio = most / least;
    for (let i = 0; i <= steps; i++) {
      const scale = least * ratio ** (i / steps), d = miss(scale);
      if (d < far) { far = d; best = scale; }
    }
    // Then closer, between the steps either side.
    const step = ratio ** (1 / steps);
    for (let i = -20; i <= 20; i++) {
      const scale = Math.min(Math.max(best * step ** (i / 20), least), most), d = miss(scale);
      if (d < far) { far = d; best = scale; }
    }
    return best;
  }

  function sizeMove(event) {
    if (!sizing) return;
    const { box, most, across } = sizing;
    if (!sizing.moved && Math.hypot(event.clientX - sizing.start.x, event.clientY - sizing.start.y) < 3) return;
    sizing.moved = true;
    let scale = scaleFor(event.clientX, event.clientY);
    // It catches at the width of its place, and at the size it was.
    const full = across / box.width;
    if (full <= most && Math.abs(scale - full) * box.width < 8) scale = full;
    if (Math.abs(scale - 1) * box.width < 4) scale = 1;
    sizing.scale = scale;
    const at = sizing.place(scale), k = scaleOf(sizing.wrap);
    sizing.wrap.style.transform = `translate(${(at.left - box.left) * k}px, ${(at.top - box.top) * k}px) scale(${scale})`;
    const id = `slide${state.slide + 1}.${regionsOf(slideAt()).find((r) => r.key === sizing.at.region).svg}.${sizing.at.index}`;
    place(chosen, boxOf(id));
    const share = Math.round((100 * scale * sizing.points * sizing.unit) / across);
    sizeTip.textContent = scale === full ? `Full ${sizing.column} width` : scale === most ? "Maximum size" : `${share}% of ${sizing.column} width`;
    const outer = pageNode.getBoundingClientRect();
    Object.assign(sizeTip.style, { left: `${event.clientX - outer.left + 14}px`, top: `${event.clientY - outer.top + 16}px` });
    sizeTip.hidden = false;
  }

  function sizeFinish() {
    const was = sizing;
    sizing = null;
    window.removeEventListener("pointermove", sizeMove);
    window.removeEventListener("pointerup", sizeEnd);
    window.removeEventListener("pointercancel", sizeCancel);
    window.removeEventListener("keydown", sizeKey, true);
    pageNode?.classList.remove("block-sizing");
    sizeTip.hidden = true;
    if (was?.moved) { swallowClick = true; setTimeout(() => { swallowClick = false; }, 0); }
    return was;
  }

  function sizeEnd() {
    const was = sizeFinish();
    if (!was) return;
    const width = Math.round(was.points * was.scale);
    if (!was.moved || Math.abs(was.scale - 1) < 0.005 || width === was.block.width) { sizeCancelled(was); return; }
    resized(was.at, [was.wrap], (b) => setOption(b, "width", width));
  }

  // The parts of its place glide to where the slide is drawn with it sized.
  function resized(at, wraps, change) {
    const count = blocksAt(slideAt(), at.region).length;
    const plan = Array.from({ length: count }, (_, index) => [{ region: at.region, index }, { region: at.region, index }]);
    moving = { slide: state.slide, at: Date.now(), plan, wraps };
    chosen.hidden = true;
    const mine = moving;
    setTimeout(() => { if (moving === mine) { moving = null; for (const wrap of mine.wraps) wrap.style.transform = ""; placeChosen(); } }, 6000);
    editBlock(at, change);
    renderInspector();
  }

  function sizeCancel() {
    const was = sizeFinish();
    if (was) sizeCancelled(was);
  }
  // It glides back to the size it was.
  function sizeCancelled(was) {
    was.wrap.classList.remove("block-sized");
    was.wrap.style.transform = "";
    placeChosen();
  }
  function sizeKey(event) {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    sizeCancel();
  }

  // Sized to its place again, as it was before it was given a width.
  function sizeFit() {
    const focus = state.focus;
    const block = focus && blocksAt(slideAt() || {}, focus.region)[focus.index];
    if (!block || !SIZED.has(kindOf(block)) || block.width == null) return;
    resized({ ...focus }, [], (b) => setOption(b, "width", null));
  }

  function onPick(event) {
    if (figure?.parts.justDragged || swallowClick) return;
    if (event.target.closest(".fig-inline, .figure-bar, .size-handle, .fig-size")) return;
    if (figure && figureBlock() && (figure.parts.connecting || inFigure(event))) { figure.parts.click(event); return; }
    const part = partAt(event);
    if (!part) { state.focus = null; state.field = null; placeChosen(); renderInspector(); reportFocus(); return; }
    state.field = null;
    // A click on a figure's part chooses that part, the figure not chosen first.
    if (part.kind === "block") focusBlock(part.region, part.index, () => figure.parts.click(event));
    else {
      // A title, subtitle or byline is selected as an object is: Return or a double-click
      // edits it in place, and typing replaces it.
      leaveFigure(false);
      offRail();
      state.focus = null; state.tab = "slide";
      state.field = { field: fieldOf(part.field), id: part.id };
      placeChosen(); renderInspector(); reportFocus();
    }
  }
  const fieldOf = (drawn) => (drawn === "byline" ? "author" : layoutOf(slideAt()) === "statement" ? "words" : drawn);

  function onEdit(event) {
    if (event.target.closest(".fig-inline, .figure-bar")) return;
    hover.hidden = true;
    if (inFigure(event)) { whenFigure(() => figure.parts.dblclick(event)); return; }
    const part = partAt(event);
    if (!part) return;
    const point = { x: event.clientX, y: event.clientY };
    if (part.kind === "field") openInline({ kind: "field", field: fieldOf(part.field) }, { at: point });
    else {
      const block = blocksAt(slideAt(), part.region)[part.index];
      if (block && INLINE.has(kindOf(block))) openInline({ kind: "block", region: part.region, index: part.index }, { at: point });
      else if (block && kindOf(block) === "table") {
        const cell = cellAt(part.id, event);
        if (cell) openInline({ kind: "cell", region: part.region, index: part.index, ...cell });
      }
      else if (block && kindOf(block) === "figure") focusBlock(part.region, part.index, () => figure.parts.dblclick(event));
    }
  }

  // -- right-click, as in PowerPoint --
  // What is under the pointer is chosen, and a menu offers what can be done with it: a
  // part of a figure, a part of the slide, or the slide itself.
  function onContext(event) {
    if (event.target.closest(".fig-inline, .figure-bar, .inline-editor, .size-handle, .fig-size")) return;
    event.preventDefault();
    closeInline();
    hover.hidden = true;
    const point = { x: event.clientX, y: event.clientY };
    const part = partAt(event);
    if (part?.kind !== "block") {
      if (part?.kind === "field") { state.focus = null; placeChosen(); }
      menu(point, slideItems(part));
      return;
    }
    const block = blocksAt(slideAt(), part.region)[part.index];
    if (block && kindOf(block) === "figure" && editable(block)) {
      // Into the figure: the part under the pointer is chosen, with its own menu.
      const show = () => {
        const id = figure?.parts.model ? figure.parts.idAt(event) : null;
        if (id && id !== figure.parts.model.root) { menu(point, [...figure.parts.menuOf(id, point), "-", ...clipItems()]); return; }
        figure?.parts.select([]);
        blockMenu(point, part);
      };
      if (figureBlock() && figure.region === part.region && figure.index === part.index && figure.parts.model) show();
      else focusBlock(part.region, part.index, show);
      return;
    }
    focusBlock(part.region, part.index);
    blockMenu(point, part);
  }
  // Greyed out, as a Mac menu's are, when there is nothing to cut, copy or paste.
  const clipItems = () => [
    { icon: "cut", label: "Cut", keys: "⌘X", disabled: !clipOf(), run: () => { const clip = clipOf(); if (clip) { clipboard = clip; navigator.clipboard?.writeText(plainOf(clip)).catch(() => {}); cutAway(clip); } } },
    { icon: "copy", label: "Copy", keys: "⌘C", disabled: !clipOf(), run: () => { const clip = clipOf(); if (clip) { clipboard = clip; navigator.clipboard?.writeText(plainOf(clip)).catch(() => {}); copied(clip); } } },
    { icon: "paste", label: "Paste", keys: "⌘V", disabled: !clipboard, run: () => clipboard && pasteClip(clipboard) },
  ];
  function blockMenu(point, at) {
    const slide = slideAt(), block = blocksAt(slide, at.region)[at.index];
    if (!block) return;
    const kind = kindOf(block), count = blocksAt(slide, at.region).length;
    const items = [];
    if (INLINE.has(kind)) items.push({ icon: "pencil", label: kind === "math" ? "Edit Equation" : kind === "code" ? "Edit Code" : "Edit Text", run: () => openInline({ kind: "block", ...at }) });
    if (kind === "figure" && editable(block)) items.push({ icon: "plus", label: "Add Shape…", keys: "A", run: () => whenFigure(() => figure.parts.addPalette(point)) });
    if (SIZED.has(kind) && block.width != null) items.push({ icon: "refresh", label: "Reset Size", run: () => sizeFit() });
    if (kind === "figure") items.push(...FIGURE_EXPORTS.map(({ label, formats, hint }) => ({ icon: "export", label: `Export as ${label}`, hint, run: () => exportFigure(at, formats) })));
    if (items.length) items.push("-");
    items.push(...clipItems(), { icon: "copy", label: "Duplicate", keys: "⌘D", run: () => insertBlock(kind, structuredClone(block), at) });
    if (at.index > 0) items.push({ icon: "up", label: "Move Up", run: () => moveBlock(at, { region: at.region, index: at.index - 1 }) });
    if (at.index < count - 1) items.push({ icon: "down", label: "Move Down", run: () => moveBlock(at, { region: at.region, index: at.index + 2 }) });
    for (const other of regionsOf(slide)) {
      if (other.key !== at.region) items.push({ icon: "right", label: `Move to ${other.name}`, run: () => moveBlock(at, { region: other.key, index: blocksAt(slide, other.key).length }) });
    }
    items.push("-", { icon: "trash", label: "Delete", keys: "⌫", danger: true, run: () => deleteBlock(at) });
    menu(point, items);
  }
  // The slide's own: its words, what may be added to it, and the slide.
  function slideItems(part) {
    const index = state.slide, room = regionsOf(slideAt()).length > 0;
    const field = part?.kind === "field" ? part.field : null;
    return [
      field ? { icon: "pencil", label: `Edit ${layoutOf(slideAt()) === "statement" ? "Text" : { title: "Title", subtitle: "Subtitle", byline: "Byline" }[field] || "Text"}`, run: () => openInline({ kind: "field", field: field === "byline" ? "author" : layoutOf(slideAt()) === "statement" ? "words" : field }) } : null,
      { icon: "text", label: "Add Text", disabled: !room, run: () => insertBlock("text") },
      { icon: "flow", label: "Add Flow Chart", disabled: !room, run: () => insertBlock("flow") },
      { icon: "structure", label: "Add Structure…", disabled: !room, run: () => insertBlock("structure") },
      { icon: "image", label: "Add Picture…", disabled: !room, run: () => insertBlock("image") },
      "-",
      { icon: "paste", label: "Paste", keys: "⌘V", disabled: !clipboard, run: () => clipboard && pasteClip(clipboard) },
      { icon: "plus", label: "New Slide", keys: "⇧⌘N", run: () => newSlideLike(index) },
      { icon: "copy", label: "Duplicate Slide", keys: "⌘D", run: () => duplicateSlide(index) },
      { icon: "trash", label: "Delete Slide", danger: true, run: () => deleteSlide(index) },
    ].filter(Boolean);
  }

  function placeChosen() {
    const focus = state.focus;
    if (sizing) return;  // its frame follows it as it is sized
    if (!focus && state.field && pageNode && !inline && !moving && !landing) {
      place(chosen, boxOf(state.field.id), { title: "Title", subtitle: "Subtitle", author: "Byline", words: "Text", date: "Date" }[state.field.field] || "Text");
      chosen.classList.remove("sizable", "holder");
      return;
    }
    if (!focus || !pageNode || moving || landing || carry?.started || inline) { chosen.hidden = true; return; }
    const region = regionsOf(slideAt()).find((r) => r.key === focus.region);
    const box = region && boxOf(`slide${state.slide + 1}.${region.svg}.${focus.index}`);
    const block = blocksAt(slideAt() || {}, focus.region)[focus.index];
    place(chosen, box, block ? BLOCKS[kindOf(block)].label : "");
    chosen.classList.toggle("sizable", Boolean(block && SIZED.has(kindOf(block))));
    holding();
  }
  // A figure whose part is chosen is only outlined round it: the part is what is chosen.
  const holding = () => chosen.classList.toggle("holder", Boolean(figureBlock() && figure.parts.selected.length));

  // A figure chosen is edited at once: `then` (a click, a double-click on one of its
  // parts) is done to it as soon as its parts are known.
  function focusBlock(region, index, then = null) {
    closeInline();
    offRail();
    state.tab = "slide";
    state.focus = { region, index };
    state.field = null;
    const block = blocksAt(slideAt(), region)[index];
    if (block && kindOf(block) === "figure") enterFigure(region, index);
    else leaveFigure(false);
    renderInspector();
    placeChosen();
    reportFocus();
    if (then && figureBlock()) whenFigure(then);
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
  // Files a figure names are found beside it: a figure file in a folder of its own
  // names them from there, not from the deck's folder.
  function figureFolder() {
    const value = figureBlock()?.figure;
    return typeof value === "string" && value.includes("/") ? value.slice(0, value.lastIndexOf("/") + 1) : "";
  }
  function relativeTo(folder, path) {
    if (!folder || !path || (!path.includes("/") && !/\.[A-Za-z0-9]+$/.test(path))) return path;  // a PDB ID
    const from = folder.split("/").filter(Boolean), to = path.split("/");
    while (from.length && to.length > 1 && from[0] === to[0]) { from.shift(); to.shift(); }
    return [...from.map(() => ".."), ...to].join("/");
  }
  function figurePrefix() {
    const region = figure && regionsOf(slideAt()).find((r) => r.key === figure.region);
    return region ? `slide${state.slide + 1}.${region.svg}.${figure.index}.` : null;
  }
  function inFigure(event) {
    if (!figureBlock()) return false;
    const part = partAt(event);
    return part?.kind === "block" && part.region === figure.region && part.index === figure.index;
  }

  // Figures' parts are read ahead -- those on the slide shown, and any the pointer
  // passes over -- so the first click on a part chooses it, as on any other part of
  // the slide, with no step into the figure first.
  const known = new Map();
  const reading = new Set();
  const knownKey = (slide, region, index) => {
    const block = blocksAt(slides()[slide] || {}, region)[index];
    return editable(block) ? `${slide}|${region}|${index}|${JSON.stringify(block.figure)}` : null;
  };
  async function readAhead(region, index, slide = state.slide) {
    const key = knownKey(slide, region, index);
    if (!key || known.has(key) || reading.has(key)) return;
    reading.add(key);
    try {
      const result = await studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "figure", at: { slide, region, index }, edit: { do: "read" } } });
      if (result?.model) {
        if (known.size > 40) known.delete(known.keys().next().value);
        known.set(key, result.model);
      }
    } catch { /* a figure that does not read is said when it is drawn */ } finally {
      reading.delete(key);
    }
  }
  function readSlideAhead() {
    for (const region of regionsOf(slideAt())) {
      blocksAt(slideAt(), region.key).forEach((block, index) => { if (kindOf(block) === "figure") readAhead(region.key, index); });
    }
  }
  // The part of a figure not chosen yet under the pointer: its drawing, and its name.
  function figurePartAt(event, part) {
    if (part.kind !== "block" || (figure && inFigure(event))) return null;
    const block = blocksAt(slideAt(), part.region)[part.index];
    if (kindOf(block) !== "figure" || !editable(block)) return null;
    readAhead(part.region, part.index);
    const model = known.get(knownKey(state.slide, part.region, part.index));
    if (!model) return null;
    const prefix = `${part.id}.`;
    for (let at = event.target; at && at !== pageNode; at = at.parentElement) {
      if (!at.matches?.("[data-flexo-entity][id]") || !at.id.startsWith(prefix)) continue;
      const node = model.nodes.find((item) => item.id === at.id.slice(prefix.length));
      if (node) return { element: at, name: plain(Array.isArray(node.label) ? node.label.map((run) => run?.text ?? "").join("") : node.label) || catalog.figure_editor.parts[node.kind || "block"]?.title || node.kind };
    }
    return null;
  }
  // `then` is done once the chosen figure's parts are known: at once if they are.
  function whenFigure(then) {
    if (!figure) return;
    if (figure.parts.model) then();
    else figure.waiting = then;
  }

  function enterFigure(region, index) {
    const block = blocksAt(slideAt(), region)[index];
    if (!editable(block)) { leaveFigure(false); return; }
    if (figure && figure.slide === state.slide && figure.region === region && figure.index === index) return;
    leaveFigure(false);
    const ahead = known.get(knownKey(state.slide, region, index));
    figure = { slide: state.slide, region, index };
    figure.parts = figureParts({
      catalog: catalog.figure_editor,
      get overlay() { return pageNode; },
      element: (id) => { const prefix = figurePrefix(); return prefix && pageNode ? pageNode.querySelector(`[id="${CSS.escape(prefix + id)}"]`) : null; },
      idOf: (id) => { const prefix = figurePrefix(); return prefix && id.startsWith(prefix) ? id.slice(prefix.length) : null; },
      box: (id) => { const prefix = figurePrefix(); return prefix ? boxOf(prefix + id) : null; },
      changed: () => { renderInspector(); placeFigure(); },
      settled: () => placeFigure(),
      chooseFile: async (options) => relativeTo(figureFolder(), await chooseFile(options)),
      tones: () => studio.info?.tones,
      addAnchor: () => figureBar.querySelector(".add") || figureBar,
      groupAnchor: () => figureBar.querySelector(".group") || figureBar,
      crumbs: () => h("button.crumb", { type: "button", onclick: () => { state.focus = null; renderInspector(); placeChosen(); reportFocus(); } }, `Slide ${state.slide + 1}`),
      nothing: () => [...blockPanel(slideAt(), figureBlock()), figure.parts.howTo()],
      run: runFigure,
    });
    // Its parts as read ahead are good to choose from at once; the read brings them up to date.
    if (ahead) figure.parts.setModel(ahead);
    const mine = figure;
    const ready = () => { if (figure === mine && mine.waiting && mine.parts.model) { const then = mine.waiting; mine.waiting = null; then(); } };
    figure.parts.act({ do: "read" }, { select: false, then: ready, failed: () => { if (figure === mine) mine.waiting = null; } });
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
  async function runFigure(action, { merge, label: told = null }) {
    if (!figure) return null;
    const at = { slide: figure.slide, region: figure.region, index: figure.index };
    // What changed is read from the figure before and after, but for a part moved: a swap
    // read from the figure alone could be either part's, so it is said as the parts say it.
    const label = action.do === "move" || action.do === "step" ? told : null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const sent = studio.doc;
      const result = await studio.api("/api/act", { file: studio.file, document: sent, action: { do: "figure", at, edit: action } });
      if (!same(studio.doc, sent)) continue;
      if (result.file) {
        if (action.do !== "read") studio.requestDraw(0);
        if (result.was !== undefined) recordFile(result, at, label, merge);
      }
      else if (!same(result.document, sent)) studio.change(() => result.document, { merge, quiet: true, label });
      return result;
    }
    return null;
  }

  // An edit to a figure kept in its own file is written there, not in the deck: the
  // deck's history keeps it all the same, undone by putting the file back as it was
  // (if no one has changed it since).
  function recordFile(result, at, label, merge) {
    const file = result.file;
    const restore = (text, expect) => studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "figure-file", file, text, expect } });
    const [from, to] = result.change || [];
    const say = (a, b) => label || (a && b ? figureChange(a, b) : "Edit Figure");
    studio.record({
      label: say(from, to), place: `Slide ${at.slide + 1}`, where: at.slide, was: result.was, now: result.now, from, to,
      apply(target) { return target === "before" ? restore(this.was, this.now) : restore(this.now, this.was); },
      // Typing on in one part: one change, said from where it started to where it is.
      absorb(newer) {
        if (newer.was !== this.now) return false;
        Object.assign(this, { now: newer.now, to: newer.to, said: null });
        this.label = say(this.from, this.to);
        return true;
      },
    }, { merge });
  }

  function placeFigure() {
    holding();
    const block = figureBlock();
    if (!block || !figure.parts.model || !pageNode) { clear(figureMarks); figureBar.hidden = true; return; }
    clear(figureMarks, figure.parts.markViews());
    const region = regionsOf(slideAt()).find((r) => r.key === figure.region);
    const box = region && boxOf(`slide${state.slide + 1}.${region.svg}.${figure.index}`);
    figureBar.hidden = !box;
    if (!box) return;
    const words = figure.parts.hint();
    const grip = h("button.btn.ghost.small.icon.figure-grip", { type: "button", title: "Drag to move the figure",
      onpointerdown: (event) => { event.stopPropagation(); pressBlock(event, { kind: "block", region: figure.region, index: figure.index }); } }, icon("grip"));
    const group = ui.button("Group", (event) => figure.parts.groupMenu(event.currentTarget), { small: true, kind: "ghost", icon: "layout", title: "Group the selected shapes (G)" });
    clear(figureBar, words ? h("span.figure-hint", {}, words) : [
      grip,
      ui.button("Add Shape", (event) => figure.parts.addPalette(event.currentTarget), { small: true, icon: "plus", kind: "primary", title: "Add Shape (A)", id: undefined }),
      ui.button("Connect", () => figure.parts.toggleConnect(), { small: true, kind: "ghost", icon: "right", title: "Draw a line from one shape to another (C)" }),
      group,
      ui.button("", (event) => menu(event.currentTarget, FIGURE_EXPORTS.map(({ label, formats, hint }) => ({ icon: "export", label: `Export as ${label}`, hint, run: () => exportFigure(figure, formats) }))),
        { small: true, kind: "ghost", icon: "export", title: "Export figure (SVG, PDF, PNG, YAML)" }),
      figure.parts.selected.length ? ui.button("", () => figure.parts.remove(), { small: true, kind: "ghost", icon: "trash", title: "Delete selected shapes (⌫)" })
        : ui.button("", () => deleteBlock({ region: figure.region, index: figure.index }), { small: true, kind: "ghost", icon: "trash", title: "Delete Figure (⌫)" }),
    ]);
    figureBar.querySelector(".btn.primary")?.classList.add("add");
    group.classList.add("group");
    // Over the figure's right end (its left end carries the part's own tag) -- or under
    // it, when the words or parts just above would be covered and there is room below.
    const left = Math.max(4, Math.min(box.left + box.width - figureBar.offsetWidth, pageNode.clientWidth - figureBar.offsetWidth - 4));
    const height = figureBar.offsetHeight || 36;
    const above = box.top > height + 8 ? box.top - height - 4 : box.top + 6;
    // Under it, clear of the + beneath the part chosen.
    const below = box.top + box.height + (figureMarks.querySelector(".fig-next.bottom") ? 26 : 4);
    const span = (top) => ({ left, right: left + (figureBar.offsetWidth || 300), top, bottom: top + height });
    const covers = (bar) => [...pageNode.querySelectorAll("[id]")].some((node) => {
      if (!BLOCK_ID.test(node.id) && !WORDS.test(node.id)) return false;
      if (node.id === `slide${state.slide + 1}.${region.svg}.${figure.index}`) return false;
      const other = boxOf(node.id);
      return other && bar.left < other.left + other.width && bar.right > other.left && bar.top < other.top + other.height && bar.bottom > other.top;
    });
    const roomBelow = below + height < pageNode.clientHeight - 4;
    // Best of all off the slide, just above it, where it covers nothing and stays put
    // whatever is chosen: over the figure's middle, within the slide's width.
    const width = figureBar.offsetWidth || 300;
    if (pageNode.getBoundingClientRect().top - stage.getBoundingClientRect().top >= height + 12) {
      const middle = Math.max(0, Math.min(box.left + box.width / 2 - width / 2, pageNode.clientWidth - width));
      Object.assign(figureBar.style, { left: `${middle}px`, top: `${-height - 8}px` });
    } else {
      const top = covers(span(above)) && roomBelow && !covers(span(below)) ? below : above;
      Object.assign(figureBar.style, { left: `${left}px`, top: `${top}px` });
    }
    stage.classList.toggle("connecting", Boolean(words));
  }

  // -- editing words in place --
  function openInline(target, { selectAll = false, at: point = null, replaceWith = null } = {}) {
    closeInline();
    const slide = slideAt();
    if (!slide) return;
    // The slide shown and the block's place follow edits from elsewhere (followChange).
    const slideNow = () => slides()[state.slide];
    // Words are typed as the slide shows them: bold as bold, a list as a list.
    const rich = (value, options, onInput) => {
      const field = richText({ value, palette: studio.info?.palette || {}, ...options });
      field.addEventListener("input", () => onInput(field.value));
      return field;
    };
    let editor, idOf, at = null, bullets = false, read = () => undefined, mirror = null;
    if (target.kind === "field") {
      const key = target.field;
      if (!catalog.slide_keys[layoutOf(slide)].includes(key)) return;
      read = () => slideNow()?.[key] ?? "";
      mirror = `slide.${key}`;
      state.field = { field: key, id: fieldId(key) };
      editor = rich(slide[key] ?? "", { single: key !== "words", placeholder: { title: "Title", subtitle: "Subtitle", words: "Text", author: "Author" }[key] },
        (text) => editSlide((s) => setOption(s, key, text), { quiet: true, merge: `${state.slide}-${key}` }));
      idOf = () => fieldId(key);
    } else if (target.kind === "cell") {
      const block = blocksAt(slide, target.region)[target.index];
      const rows = tableRows(block);
      if (!rows[target.row] || target.col >= rows[target.row].length) return;
      at = { region: target.region, index: target.index };
      read = () => { const now = blocksAt(slideNow() || {}, at.region)[at.index]; return now && kindOf(now) === "table" ? tableRows(now)[target.row]?.[target.col] : undefined; };
      editor = rich(rows[target.row][target.col], { single: true },
        (text) => editBlock(at, (b) => { const cells = tableRows(b); cells[target.row][target.col] = text; b.table = cells; },
          { merge: `${state.slide}-${at.region}-${at.index}-cell-${target.row}-${target.col}` }));
      idOf = () => `${blockId(at)}.${target.row}.${target.col}`;
      state.focus = at;
      renderInspector();
      reportFocus();
    } else {
      const block = blocksAt(slide, target.region)[target.index];
      if (!block) return;
      const kind = kindOf(block);
      at = { region: target.region, index: target.index };
      const merge = `${state.slide}-${at.region}-${at.index}-inline`;
      read = () => {
        const now = blocksAt(slideNow() || {}, at.region)[at.index];
        if (!now || kindOf(now) !== kind) return undefined;
        return kind === "bullets" ? bulletsText(now.bullets) : now[kind] ?? "";
      };
      mirror = `block.${kind}`;
      bullets = kind === "bullets";
      if (bullets) editor = rich(bulletsText(block.bullets), { list: true, numbered: Boolean(block.numbered) }, (text) => editBlock(at, (b) => { b.bullets = bulletsFrom(text); }, { merge }));
      else if (kind === "code") editor = ui.textarea({ value: block.code, rows: 4, mono: true, onInput: (text) => editBlock(at, (b) => { b.code = text; }, { merge }) });
      else if (kind === "math") editor = ui.textarea({ value: block.math, rows: 2, mono: true, spelling: false, onInput: (text) => editBlock(at, (b) => { b.math = text; }, { merge }) });
      else editor = rich(block[kind] ?? "", {}, (text) => editBlock(at, (b) => { b[kind] = text; }, { merge }));
      idOf = () => blockId(at);
      state.focus = at;
      renderInspector();
      placeChosen();
      reportFocus();
    }
    const area = editor.area || editor;
    const cell = target.kind === "cell";
    const node = h(`div.inline-editor.in-place${cell ? ".cell" : ""}`, { onmousedown: (event) => event.stopPropagation(),
      title: cell ? "Tab: next cell · Return: cell below · ⌘B: bold · ⌘I: italic · Esc: done"
        : `${bullets ? "Tab: indent · Shift-Tab: outdent · " : ""}⌘B: bold · ⌘I: italic · ${target.kind === "field" ? "Return or Esc: done" : "Esc: done"}` }, editor);
    area.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeInline(); }
      if (event.key === "Enter" && !event.shiftKey && target.kind === "field") { event.preventDefault(); closeInline(); }
      // Tab goes on to the slide's next line of words (title, subtitle, byline), not to the inspector.
      if (event.key === "Tab" && target.kind === "field") {
        event.preventDefault();
        const order = ["title", "words", "subtitle", "author", "date"].filter((key) => catalog.slide_keys[layoutOf(slideAt())].includes(key) && key !== "date");
        const next = order[(order.indexOf(target.field) + (event.shiftKey ? -1 : 1) + order.length) % order.length];
        if (next && next !== target.field) openInline({ kind: "field", field: next }, { selectAll: true });
      }
      if (target.kind === "cell" && (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey))) { event.preventDefault(); nextCell(target, event.key, event.shiftKey); }
    });
    // An equation's LaTeX looks nothing like it: it is typed under the equation, which
    // stays in view and is drawn again as it changes.
    const under = target.kind === "block" && kindOf(blocksAt(slide, target.region)[target.index]) === "math";
    if (under) node.classList.add("under");
    const id = idOf();
    inline = { node, id, idOf, at, area, bullets, cell, under, read };
    // The inspector shows what is typed, as it is typed.
    if (mirror) area.addEventListener("input", () => {
      const twin = inspectorBody.querySelector(`[data-key="${CSS.escape(mirror)}"]`);
      if (twin && twin !== document.activeElement && twin.value !== area.value) twin.value = area.value;
    });
    center.append(node);
    positionInline();
    area.focus();
    if (area.rich) {
      if (replaceWith !== null) { area.value = replaceWith; area.dispatchEvent(new Event("input")); area.caretToEnd(); }
      else if (selectAll || (area.value.trim() && starter(area.value))) area.selectAll();
      else if (!(point && area.selectWordAt(point))) area.caretToEnd();
      setTimeout(() => document.addEventListener("mousedown", closeOnOutside, true), 0);
      return;
    }
    const word = point && wordAt(id, point, area.value);
    if (replaceWith !== null) {
      area.value = replaceWith;
      area.dispatchEvent(new Event("input"));
      area.setSelectionRange(area.value.length, area.value.length);
    } else if (selectAll) area.select();
    else if (word) area.setSelectionRange(word.start, word.end);
    else area.setSelectionRange(area.value.length, area.value.length);
    setTimeout(() => document.addEventListener("mousedown", closeOnOutside, true), 0);
  }

  // A table's cells, typed in on the slide as in a spreadsheet: Tab goes to the next
  // cell (a new row after the last, as in PowerPoint), Enter to the one below.
  function tableRows(block) {
    const source = Array.isArray(block?.table) && block.table.length ? block.table : [[typeof block?.table === "string" ? block.table : ""]];
    const rows = source.map((row) => (Array.isArray(row) ? row : [row]).map((cell) => String(cell ?? "")));
    const columns = Math.max(1, ...rows.map((row) => row.length));
    rows.forEach((row) => { while (row.length < columns) row.push(""); });
    return rows;
  }
  // The cell under the pointer: the one whose words it is on, else the one whose
  // column and row it is in (by the words drawn in them).
  function cellAt(tableId, event) {
    const cells = [...pageNode.querySelectorAll("[id]")].map((node) => ({ node, match: node.id.startsWith(`${tableId}.`) && /^(\d+)\.(\d+)$/.exec(node.id.slice(tableId.length + 1)) }))
      .filter((item) => item.match).map(({ node, match }) => ({ row: Number(match[1]), col: Number(match[2]), box: node.getBoundingClientRect() }));
    if (!cells.length) return null;
    const hit = cells.find(({ box }) => event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom);
    if (hit) return { row: hit.row, col: hit.col };
    const nearest = (key, centre) => cells.reduce((best, cell) => (Math.abs(centre(cell.box) - (key === "x" ? event.clientX : event.clientY)) < Math.abs(centre(best.box) - (key === "x" ? event.clientX : event.clientY)) ? cell : best));
    return { row: nearest("y", (box) => (box.top + box.bottom) / 2).row, col: nearest("x", (box) => (box.left + box.right) / 2).col };
  }
  // Where a cell is on the slide (as boxOf gives it): across, as its column's words
  // are; down, as its row's are -- or a row's pitch below the last, for a row just added.
  function cellBox(id) {
    const [, tableId, row, col] = /^(.*)\.(\d+)\.(\d+)$/.exec(id) || [];
    if (!tableId) return null;
    const own = boxOf(id);
    if (own) return own;
    const cells = [...pageNode.querySelectorAll("[id]")].map((node) => ({ id: node.id, match: node.id.startsWith(`${tableId}.`) && /^(\d+)\.(\d+)$/.exec(node.id.slice(tableId.length + 1)) }))
      .filter((item) => item.match).map(({ id: cell, match }) => ({ row: Number(match[1]), col: Number(match[2]), box: boxOf(cell) })).filter((cell) => cell.box);
    const across = cells.filter((cell) => cell.col === Number(col)), down = cells.filter((cell) => cell.row === Number(row));
    if (!across.length) return null;
    const left = Math.min(...across.map((cell) => cell.box.left)), width = Math.max(...across.map((cell) => cell.box.left + cell.box.width)) - left;
    if (down.length) return { left, width, top: Math.min(...down.map((cell) => cell.box.top)), height: Math.max(...down.map((cell) => cell.box.height)) };
    const rows = [...new Set(cells.map((cell) => cell.row))].sort((a, b) => a - b);
    const topOf = (r) => Math.min(...cells.filter((cell) => cell.row === r).map((cell) => cell.box.top));
    const last = rows[rows.length - 1], pitch = rows.length > 1 ? (topOf(last) - topOf(rows[0])) / (last - rows[0]) : 30;
    const height = Math.max(...cells.filter((cell) => cell.row === last).map((cell) => cell.box.height));
    return { left, width, top: topOf(last) + pitch * (Number(row) - last), height };
  }

  // An empty cell, drawn with no words, is typed in as the cells about it are set.
  function cellLook(id) {
    const [, tableId, row, col] = /^(.*)\.(\d+)\.(\d+)$/.exec(id) || [];
    for (const [r, c] of [[+row - 1, +col], [+row + 1, +col], [+row, +col - 1], [+row, +col + 1], [+row - 1, +col - 1]]) {
      const look = r > 0 && wordsLook(pageNode.querySelector(`[id="${CSS.escape(`${tableId}.${r}.${c}`)}"]`));
      if (look) return look;
    }
    return null;
  }

  function nextCell(target, key, back) {
    const at = { region: target.region, index: target.index };
    const rows = tableRows(blocksAt(slideAt(), at.region)[at.index]);
    const columns = rows[0].length;
    let { row, col } = target;
    if (key === "Enter") row += 1;
    else if (back) { col -= 1; if (col < 0) { col = columns - 1; row -= 1; } }
    else { col += 1; if (col >= columns) { col = 0; row += 1; } }
    if (row < 0) { closeInline(); return; }
    if (row >= rows.length) {
      if (key === "Enter") { closeInline(); return; }
      editBlock(at, (b) => { const cells = tableRows(b); cells.push(Array(columns).fill("")); b.table = cells; });
    }
    openInline({ kind: "cell", ...at, row, col }, { selectAll: true });
  }

  // The word double-clicked on the slide, found in the words as written, so the editor
  // opens with it selected (as a Mac text view does) rather than the caret at the end.
  function wordAt(id, point, written) {
    const element = pageNode?.querySelector(`[id="${CSS.escape(id)}"]`);
    if (!element) return null;
    const texts = element.matches("text") ? [element] : [...element.querySelectorAll("text")];
    let before = "", hit = null;
    for (const text of texts) {
      const box = text.getBoundingClientRect();
      const inside = point.x >= box.left && point.x <= box.right && point.y >= box.top && point.y <= box.bottom;
      if (inside && !hit && text.getCharNumAtPosition && text.getScreenCTM()) {
        const local = new DOMPoint(point.x, point.y).matrixTransform(text.getScreenCTM().inverse());
        const index = text.getCharNumAtPosition(local);
        const content = text.textContent || "";
        if (index >= 0 && /[\p{L}\p{N}]/u.test(content[index] || "")) {
          let start = index, end = index + 1;
          while (start > 0 && /[\p{L}\p{N}'’-]/u.test(content[start - 1])) start -= 1;
          while (end < content.length && /[\p{L}\p{N}'’-]/u.test(content[end])) end += 1;
          hit = { word: content.slice(start, end), before: before + content.slice(0, start) };
        }
      }
      before += `${text.textContent || ""} `;
    }
    if (!hit) return null;
    // The same word, as often as it came before, in what is written.
    const occurrence = hit.before.split(hit.word).length - 1;
    let from = -1;
    for (let n = 0; n <= occurrence; n += 1) {
      from = written.indexOf(hit.word, from + 1);
      if (from < 0) return null;
    }
    return { start: from, end: from + hit.word.length };
  }

  // Where a slide's line of text and a block are drawn on the slide shown.
  const fieldId = (key) => `slide${state.slide + 1}.${key === "author" ? "byline" : key === "words" ? "title" : key}`;
  const blockId = (at) => `slide${state.slide + 1}.${regionsOf(slideAt()).find((r) => r.key === at.region)?.svg}.${at.index}`;

  // Where each of `before`'s items is in `after` (-1 if it is gone): the items that are
  // the same, in the same order, first; then an item changed in place is the changed
  // one between the same neighbours -- the one that looks like it (`like`), else the
  // one in its turn.
  function follow(before, after, like) {
    const a = before.map((item) => JSON.stringify(item)), b = after.map((item) => JSON.stringify(item));
    const n = a.length, m = b.length;
    const common = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
    for (let i = n - 1; i >= 0; i -= 1) for (let j = m - 1; j >= 0; j -= 1) common[i][j] = a[i] === b[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1]);
    const map = new Array(n).fill(-1);
    for (let i = 0, j = 0; i < n && j < m;) {
      if (a[i] === b[j]) { map[i] = j; i += 1; j += 1; } else if (common[i + 1][j] >= common[i][j + 1]) i += 1; else j += 1;
    }
    let lastOld = -1, lastNew = -1;
    for (let k = 0; k <= n; k += 1) {
      if (k < n && map[k] < 0) continue;
      const nextNew = k < n ? map[k] : m;
      const olds = [], news = [];
      for (let x = lastOld + 1; x < k; x += 1) olds.push(x);
      for (let y = lastNew + 1; y < nextNew; y += 1) news.push(y);
      if (olds.length === news.length) olds.forEach((x, t) => { map[x] = news[t]; });
      else {
        const free = new Set(news);
        for (const x of olds) {
          const match = news.find((y) => free.has(y) && like(before[x]) === like(after[y]));
          if (match !== undefined) { map[x] = match; free.delete(match); }
        }
      }
      lastOld = k; lastNew = nextNew;
    }
    return map;
  }

  // After an edit from elsewhere (another person, an agent, the file on disk) or an undo,
  // the slide shown, the object selected and the text being typed are found where they
  // now are, by what they hold -- not left at a place that now holds something else.
  function followChange(was, who) {
    const before = Array.isArray(was?.slides) ? was.slides : [], after = slides();
    if (before === after || !before.length) return;
    const from = state.slide;
    const to = from < before.length ? follow(before, after, (slide) => `${layoutOf(slide)}:${slide?.title ?? ""}`)[from] : from;
    const gone = () => { closeInline(); toast(`${who?.name || "Someone else"} deleted the text you were editing`, { icon: "info", seconds: 5 }); };
    if (to < 0) {
      if (inline) gone();
      state.focus = null; state.field = null;
      state.slide = Math.min(from, Math.max(0, after.length - 1));
      return;
    }
    state.slide = to;
    const place = (at) => {
      const map = follow(blocksAt(before[from], at.region), blocksAt(after[to], at.region), (block) => kindOf(block));
      return map[at.index] ?? -1;
    };
    // The selection and the editor's block may be one object: each is placed from where it was.
    const focusTo = state.focus ? place(state.focus) : -1, inlineTo = inline?.at ? place(inline.at) : -1;
    const shared = inline?.at && inline.at === state.focus;
    if (inline?.at) { if (inlineTo < 0) gone(); else inline.at.index = inlineTo; }
    if (state.focus && !shared) { if (focusTo < 0) state.focus = null; else state.focus.index = focusTo; }
    else if (shared && inlineTo < 0) state.focus = null;
    if (state.field) state.field.id = fieldId(state.field.field);
    if (inline) inline.id = inline.idOf();
  }

  // After an undo or a redo, the object it changed is chosen, as Keynote does: the first
  // on the slide shown that is not as it was.
  function chooseChanged(was) {
    const before = was?.slides || [], after = slides();
    if (before.length !== after.length) { state.focus = null; return; }
    const old = partsOf(before[state.slide] || {}), now = partsOf(after[state.slide] || {});
    const changed = now.find((item, k) => !old[k] || item.region !== old[k].region || !same(item.block, old[k].block));
    const chosen = changed && state.focus?.region === changed.region && state.focus?.index === changed.index;
    if (changed && !chosen) focusBlock(changed.region, changed.index);
    else if (state.focus && !blocksAt(slideAt(), state.focus.region)[state.focus.index]) state.focus = null;
  }

  // After an undo or an edit from elsewhere, the editor open on the slide shows the words
  // as they now are -- typing on from what was undone would bring it back.
  function refreshInline() {
    if (!inline?.read) return;
    const value = inline.read();
    if (value === undefined) { closeInline(); return; }
    if (value === inline.area.value) return;
    inline.area.value = value;
    if (inline.area.rich) inline.area.caretToEnd();
    else {
      inline.area.setSelectionRange(value.length, value.length);
      inline.area.style.height = "auto";
      inline.area.style.height = `${inline.area.scrollHeight + 2}px`;
    }
    positionInline();
  }

  // Words are typed where they are on the slide, as they look there: the editor lies
  // over them in their face, size and colour, and the drawn words step aside while it
  // is open. It stays put (keeping its caret) when the slide is drawn again under it.
  function wordsLook(element) {
    const text = element?.matches("text") ? element : element?.querySelector("text");
    if (!text) return null;
    const style = getComputedStyle(text);
    const scale = text.getScreenCTM()?.a || 1;
    const first = text.getBoundingClientRect();
    return { size: parseFloat(style.fontSize) * scale, family: style.fontFamily, weight: style.fontWeight,
      colour: style.fill && style.fill !== "none" ? style.fill : "", anchor: text.getAttribute("text-anchor") || style.textAnchor || "start", left: first.left };
  }
  function positionInline() {
    if (!inline || !pageNode?.isConnected) return;
    const outer = center.getBoundingClientRect();
    const slide = pageNode.getBoundingClientRect();
    const element = pageNode.querySelector(`[id="${CSS.escape(inline.id)}"]`);
    const box = boxOf(inline.id);
    const look = wordsLook(element) || inline.look || (inline.cell ? cellLook(inline.id) : null);
    if (look) inline.look = look;
    if (inline.under) {
      chosen.hidden = true;
      hover.hidden = true;
      if (!box) return;
      const width = Math.min(Math.max(box.width + 40, 360), slide.width - 24);
      const left = slide.left - outer.left + Math.min(Math.max(12, box.left + box.width / 2 - width / 2), slide.width - width - 12);
      Object.assign(inline.node.style, { left: `${left}px`, top: `${slide.top - outer.top + box.top + box.height + 6}px`, width: `${width}px`, minHeight: "" });
      return;
    }
    if (element && inline.hidden !== element) { inline.hidden?.style.removeProperty("visibility"); element.style.visibility = "hidden"; inline.hidden = element; }
    // The words being typed are what is chosen: no frame over them.
    chosen.hidden = true;
    hover.hidden = true;
    const size = look?.size || 16;
    if (inline.cell) {
      const box = cellBox(inline.id);
      if (!box) return;
      const right = look?.anchor === "end", width = Math.max(box.width + 16, 60);
      const left = slide.left - outer.left + (right ? box.left + box.width - width : look?.anchor === "middle" ? box.left + box.width / 2 - width / 2 : box.left);
      Object.assign(inline.node.style, { left: `${left}px`, top: `${slide.top - outer.top + box.top}px`, width: `${width}px`, minHeight: `${box.height}px` });
      Object.assign(inline.area.style, { fontSize: `${size}px`, fontFamily: look?.family || "", fontWeight: look?.weight || "", color: look?.colour || "",
        textAlign: right ? "right" : look?.anchor === "middle" ? "center" : "left", paddingLeft: "5px" });
      return;
    }
    const centred = look?.anchor === "middle";
    // As wide as the room the words have on the slide: to its margin, both sides for centred
    // words, and not past the column beside them.
    const margin = box ? Math.max(12, centred ? Math.min(box.left, slide.width - box.left - box.width) : box.left) : 40;
    let width = box ? (centred ? slide.width - 2 * margin : Math.max(box.width, slide.width - box.left - margin)) : 420;
    const beside = box && !centred ? columnBeside(box) : null;
    if (beside !== null) width = Math.max(box.width, Math.min(width, beside - box.left - 8));
    const left = slide.left - outer.left + (box ? (centred ? margin : box.left) : 40);
    let top = slide.top - outer.top + (box ? box.top : 60);
    const rich = inline.area.rich;
    const indent = inline.bullets && look && box && !rich ? Math.max(0, look.left - slide.left - box.left - 5) : 0;
    // The rich editor's lines lie on the drawn lines: the same line spacing, the first
    // line's letters where the drawn ones are, and a list's bullets where they are drawn.
    const metrics = rich && element ? textMetrics(element, size) : null;
    // Words the slide wrapped wrap where it wrapped them: at their longest line, give or take a letter.
    if (metrics?.wrapped && box && !centred) width = Math.min(width, box.width + size * 0.6);
    if (metrics) {
      top = metrics.top - outer.top - (metrics.line - metrics.height) / 2 - 5;
      inline.area.style.setProperty("--rt-line", `${metrics.line}px`);
      if (inline.bullets) for (const [name, value] of Object.entries(listLook(element, metrics, slide.left + box.left + 5))) inline.area.style.setProperty(name, value);
    }
    Object.assign(inline.node.style, { left: `${left}px`, top: `${Math.max(8, top)}px`, width: `${width}px`, minHeight: box ? `${box.height}px` : "" });
    Object.assign(inline.area.style, { fontSize: `${size}px`, fontFamily: look?.family || "", fontWeight: look?.weight || "",
      color: look?.colour || "", textAlign: centred ? "center" : "left", paddingLeft: rich ? "" : `${5 + indent}px` });
  }

  // Where the next column's objects start, right of `box` (as boxOf gives boxes), if any.
  function columnBeside(box) {
    const slide = slideAt();
    const lefts = regionsOf(slide).flatMap((region) => blocksAt(slide, region.key).map((_, index) => boxOf(`slide${state.slide + 1}.${region.svg}.${index}`)))
      .filter((other) => other && other.left > box.left + box.width / 2).map((other) => other.left);
    return lefts.length ? Math.min(...lefts) : null;
  }

  // How words are set on the slide (in page pixels): the top of the first line's letters,
  // a line's height, and the distance from line to line -- from a text's own wrapped
  // lines, or one and a fifth of its size.
  function textMetrics(element, size) {
    const texts = element.matches("text") ? [element] : [...element.querySelectorAll("text")];
    if (!texts.length) return null;
    const first = (texts[0].querySelector("tspan") || texts[0]).getBoundingClientRect();
    let line = 0, wrapped = false;
    for (const text of texts) {
      const tops = [...new Set([...text.querySelectorAll("tspan")].map((span) => Math.round(span.getBoundingClientRect().top * 4) / 4))].sort((a, b) => a - b);
      if (tops.length > 1) { line ||= tops[1] - tops[0]; wrapped = true; }
    }
    return { top: first.top, height: first.height, line: line || first.height * 1.05 || size * 1.22, wrapped, texts };
  }

  // A list as the slide draws it: where its words start and its bullets sit, how far a
  // level indents, the space between items, and the bullets' size and colour -- as CSS
  // properties for the rich editor (editor.css), from `origin` (its words' left edge).
  function listLook(element, metrics, origin) {
    const id = element.id;
    const items = [];
    for (let n = 0; n < 200; n += 1) {
      const text = pageNode.querySelector(`[id="${CSS.escape(`${id}.${n}`)}"]`);
      if (!text) break;
      items.push({ text, box: text.getBoundingClientRect(), mark: pageNode.querySelector(`[id="${CSS.escape(`${id}.${n}.mark`)}"]`) });
    }
    if (!items.length) return {};
    const centre = (mark) => { const b = mark.getBoundingClientRect(); return b.left + b.width / 2; };
    const marked = items.filter((item) => item.mark);
    const outerMost = marked.length ? Math.min(...marked.map((item) => centre(item.mark))) : null;
    const top = marked.find((item) => Math.abs(centre(item.mark) - outerMost) < 1.5) || items[0];
    const deeper = marked.find((item) => centre(item.mark) - outerMost > 3);
    const look = {};
    look["--rt-text"] = `${top.box.left - origin}px`;
    if (top.mark) {
      const mark = top.mark.getBoundingClientRect();
      look["--rt-mark-x"] = `${centre(top.mark) - origin}px`;
      look["--rt-r"] = `${mark.width / 2}px`;
      look["--rt-mark-y"] = `${(metrics.line - metrics.height) / 2 + (mark.top + mark.height / 2 - top.box.top)}px`;
      look["--rt-mark"] = top.mark.getAttribute("fill") || "currentColor";
    }
    if (deeper) {
      look["--rt-step"] = `${centre(deeper.mark) - outerMost}px`;
      look["--rt-r2"] = `${deeper.mark.getBoundingClientRect().width / 2}px`;
      look["--rt-mark2"] = deeper.mark.getAttribute("fill") || "currentColor";
    }
    // From one item to the next, less its own lines: the space between items.
    const lines = (item) => new Set([...item.text.querySelectorAll("tspan")].map((span) => Math.round(span.getBoundingClientRect().top))).size || 1;
    const gaps = items.slice(1).map((item, n) => item.box.top - items[n].box.top - lines(items[n]) * metrics.line);
    if (gaps.length) look["--rt-gap"] = `${Math.max(0, Math.min(...gaps))}px`;
    return look;
  }
  stage.addEventListener("scroll", () => { if (inline) positionInline(); });
  // A click on the desk round the slide chooses nothing, as on Keynote's canvas.
  stage.addEventListener("click", (event) => {
    if (event.target !== stage && !event.target.classList?.contains("slide-wrap")) return;
    if (!state.focus && !state.field) return;
    state.focus = null; state.field = null;
    leaveFigure(false);
    placeChosen(); renderInspector(); reportFocus();
  });

  function closeOnOutside(event) {
    if (inline && !inline.node.contains(event.target) && !event.target.closest?.(".rt-bar")) closeInline();
  }

  function closeInline() {
    if (!inline) return;
    inline.area.dispose?.();
    inline.node.remove();
    pageNode?.querySelector(`[id="${CSS.escape(inline.id)}"]`)?.style.removeProperty("visibility");
    inline = null;
    document.removeEventListener("mousedown", closeOnOutside, true);
    // What was typed is shown in the panel too.
    renderInspector();
    placeChosen();
  }

  // Files dropped on the slide are added to it: pictures as pictures, and structures
  // (PDB, mmCIF) drawn by mol-sketch -- into the figure they are dropped on, after its
  // part chosen and joined to it, or else as a figure of their own, an arrow from each
  // to the next.
  let dropNote = null;
  stage.addEventListener("dragover", (event) => {
    if (![...(event.dataTransfer?.types || [])].includes("Files") || !regionsOf(slideAt()).length) return;
    event.preventDefault();
    if (!dropNote) { dropNote = h("div.drop-note", {}, "Drop pictures or structure files (PDB, mmCIF) to add them to the slide"); center.append(dropNote); }
    // Where structures would go: after the figure's part under the pointer, into the
    // figure, or a figure of their own. (Pictures always come as pictures.)
    const pictures = [...(event.dataTransfer?.items || [])].every((item) => item.type.startsWith("image/") || item.type === "application/pdf");
    const part = pictures ? null : partAt(event);
    const block = part?.kind === "block" ? blocksAt(slideAt(), part.region)[part.index] : null;
    if (block && kindOf(block) === "figure" && editable(block)) {
      const inner = figurePartAt(event, part) || (figure && inFigure(event) && figure.parts.model && figure.parts.idAt(event)
        ? { element: pageNode.querySelector(`[id="${CSS.escape(figurePrefix() + figure.parts.idAt(event))}"]`), name: figure.parts.nameOf(figure.parts.idAt(event)) } : null);
      if (inner?.element) place(hover, boxOf(inner.element.id), `Add after ${inner.name}`);
      else place(hover, boxOf(part.id), "Add to figure");
    } else hover.hidden = true;
  });
  stage.addEventListener("dragleave", (event) => { if (!stage.contains(event.relatedTarget)) { dropNote?.remove(); dropNote = null; hover.hidden = true; } });
  stage.addEventListener("drop", async (event) => {
    dropNote?.remove(); dropNote = null;
    hover.hidden = true;
    if (await addFiles([...(event.dataTransfer?.files || [])], partAt(event), event)) event.preventDefault();
  });

  // Files added to the slide, dropped or pasted: pictures, and structures into the figure
  // `part` is (where `at`, an event, says) or a figure of their own. Whether any were.
  async function addFiles(all, part, at = null) {
    const pictures = all.filter((file) => /\.(png|jpe?g|svg|gif|webp|pdf|ai)$/i.test(file.name));
    const structures = all.filter((file) => STRUCTURE_FILE.test(file.name));
    if (!pictures.length && !structures.length) {
      if (all.length) toast("Only pictures and structure files (PDB, mmCIF) can be added to a slide.", { icon: "info" });
      return all.length > 0;
    }
    for (const file of pictures) await insertBlock("image", { image: await studio.upload(file) });
    if (structures.length) {
      const sources = [];
      for (const file of structures) sources.push(await studio.upload(file));
      const block = part?.kind === "block" && !pictures.length ? blocksAt(slideAt(), part.region)[part.index] : null;
      if (block && kindOf(block) === "figure" && editable(block)) addStructures(part.region, part.index, sources, at);
      else await insertBlock("structure", structureFigure(sources));
    }
    const said = [pictures.length ? `${pictures.length} picture${pictures.length > 1 ? "s" : ""}` : "", structures.length ? `${structures.length} structure${structures.length > 1 ? "s" : ""}` : ""].filter(Boolean);
    toast(`${said.join(" and ")} added`, { icon: structures.length ? "structure" : "image" });
    return true;
  }

  // -- copy, cut and paste (⌘C, ⌘X, ⌘V) --
  // What is chosen is copied: a figure's parts, a part of the slide, or else the slide
  // (always the slide when the list of slides has the keys). Pasted, it comes after
  // what is chosen: parts into the figure chosen (or a new figure of their own), a part
  // onto the slide, a slide after this one. Pictures, structure files and words copied
  // elsewhere paste onto the slide too.
  const CLIP = "application/x-flexo-deck";
  let clipboard = null;
  // Words chosen to copy in the panel, a field, or a note -- not on the slide, a drawing.
  const wordsChosen = () => { const chosenWords = window.getSelection(); return Boolean(chosenWords?.toString()) && !pageNode?.contains(chosenWords.anchorNode); };
  const typingNow = () => /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "") || document.activeElement?.isContentEditable
    || Boolean(document.querySelector(".scrim, .present"));
  function clipOf() {
    if (figure && figureBlock() && figure.parts.selected.length) {
      const parts = figure.parts.clip();
      if (parts) return { what: "parts", parts, label: parts.top.length > 1 ? `${parts.top.length} shapes` : "shape" };
    }
    const slide = slideAt();
    if (!slide) return null;
    const block = state.focus && blocksAt(slide, state.focus.region)[state.focus.index];
    if (block) return { what: "block", block: structuredClone(block), label: BLOCKS[kindOf(block)].label.toLowerCase() };
    // The slide itself only when the slides have the keys (a thumbnail clicked last).
    if (!railList.contains(document.activeElement)) return null;
    const chosen = chosenSlides();
    if (chosen.length > 1) return { what: "slides", slides: chosen.map((index) => structuredClone(slides()[index])), indices: chosen, label: `${chosen.length} slides` };
    return { what: "slide", slide: structuredClone(slide), label: "slide" };
  }
  function plainOf(clip) {
    if (clip.what === "slide") return plain(slideTitle(clip.slide));
    if (clip.what === "slides") return clip.slides.map((slide) => plain(slideTitle(slide))).join("\n");
    if (clip.what === "parts") return clip.parts.nodes.map((node) => plain(Array.isArray(node.label) ? node.label.map((run) => run?.text ?? "").join("") : node.label || node.id)).join("\n");
    const block = clip.block;
    return block.bullets ? bulletsText(block.bullets) : String(block.text ?? block.quote ?? block.callout ?? block.code ?? block.math ?? "");
  }
  function copyNow(event) {
    if (!studio.active || typingNow() || wordsChosen()) return null;
    const clip = clipOf();
    if (!clip) return null;
    event.preventDefault();
    clipboard = clip;
    event.clipboardData?.setData(CLIP, JSON.stringify(clip));
    event.clipboardData?.setData("text/plain", plainOf(clip));
    return clip;
  }
  const copied = (clip) => toast(`${clip.label.charAt(0).toUpperCase()}${clip.label.slice(1)} copied`, { icon: "copy", seconds: 1.5 });
  function cutAway(clip) {
    if (clip.what === "parts") figure.parts.remove();
    else if (clip.what === "block") deleteBlock(state.focus);
    else if (clip.what === "slides") deleteSlides(clip.indices);
    else deleteSlide(state.slide);
  }
  document.addEventListener("copy", (event) => {
    keyed = null;
    const clip = copyNow(event);
    if (clip) copied(clip);
  });
  document.addEventListener("cut", (event) => {
    keyed = null;
    const clip = copyNow(event);
    if (clip) cutAway(clip);
  });
  // A web view that gives no copy, cut or paste to a page with nothing to type in (a
  // Mac app's, whose Edit menu waits for a selection) still passes the keys: if no such
  // event follows them, the page does it itself, with what it copied.
  let keyed = null;
  function clipKey(event) {
    const letter = event.key.toLowerCase();
    if (!(event.metaKey || event.ctrlKey) || event.shiftKey || event.altKey || !["c", "x", "v"].includes(letter)) return;
    if (!studio.active || typingNow() || wordsChosen()) return;
    keyed = letter;
    setTimeout(async () => {
      if (keyed !== letter) return;
      keyed = null;
      if (letter === "v") {
        if (clipboard) pasteClip(clipboard);
        return;
      }
      const clip = clipOf();
      if (!clip) return;
      clipboard = clip;
      navigator.clipboard?.writeText(plainOf(clip)).catch(() => {});
      if (letter === "c") copied(clip); else cutAway(clip);
    }, 80);
  }
  document.addEventListener("keydown", clipKey, true);
  document.addEventListener("paste", async (event) => {
    keyed = null;
    if (!studio.active || typingNow()) return;
    const data = event.clipboardData;
    let clip = null;
    try { clip = JSON.parse(data?.getData(CLIP) || "null"); } catch { clip = null; }
    // A clipboard that keeps only words: what was copied here, if they are its words.
    if (!clip && clipboard && data?.getData("text/plain") === plainOf(clipboard)) clip = clipboard;
    if (clip) { event.preventDefault(); pasteClip(clip); return; }
    const files = [...(data?.files || [])];
    if (files.length) { event.preventDefault(); await addFiles(files, state.focus ? { kind: "block", ...state.focus } : null); return; }
    const text = (data?.getData("text/plain") || "").replace(/\r/g, "").trim();
    if (!text) return;
    if (!regionsOf(slideAt()).length) { toast("This layout has no room for text. Choose a different layout first.", { icon: "info" }); return; }
    event.preventDefault();
    const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
    insertBlock(lines.length > 1 ? "bullets" : "text", lines.length > 1 ? { bullets: lines.map((line) => line.replace(/^[-*•·]\s+/, "")) } : { text });
  });
  function pasteClip(clip) {
    if (clip.what === "slides") {
      const at = Math.min(Math.max(...chosenSlides()) + 1, slides().length);
      studio.change((d) => { d.slides ||= []; d.slides.splice(at, 0, ...clip.slides.map((slide) => structuredClone(slide))); });
      select(at);
      state.picked = clip.slides.map((_, n) => at + n);
      renderRail();
    } else if (clip.what === "slide") {
      const at = Math.min(state.slide + 1, slides().length);
      studio.change((d) => { d.slides ||= []; d.slides.splice(at, 0, structuredClone(clip.slide)); });
      select(at);
    } else if (clip.what === "block") {
      if (!regionsOf(slideAt()).length) { toast("This layout has no room for objects. Choose a different layout first.", { icon: "info" }); return; }
      insertBlock(kindOf(clip.block), structuredClone(clip.block));
    } else if (clip.what === "parts") {
      if (figure && figureBlock() && editable(figureBlock())) figure.parts.paste(clip.parts);
      else insertBlock("figure", { figure: figureOfParts(clip.parts) });
    }
  }
  // Parts pasted where no figure is chosen: a figure of their own.
  function figureOfParts(parts) {
    const nodes = parts.nodes.map((node) => {
      const copy = structuredClone(node);
      if (Array.isArray(copy.ports) && copy.ports.every((port) => typeof port === "string")) delete copy.ports;
      return copy;
    });
    const groups = parts.groups.map(({ implied, ...group }) => structuredClone(group));
    const edges = parts.edges.map(({ id, ...edge }) => structuredClone(edge));
    return { figure: { id: `figure-${Date.now().toString(36)}` }, nodes, ...(groups.length ? { groups } : {}), ...(edges.length ? { edges } : {}) };
  }

  // Structures added to a figure on the slide, one after another: each after the part
  // chosen (the one added before it, from the second on), a line from it.
  function addStructures(region, index, sources, dropped = null) {
    focusBlock(region, index);
    if (!figureBlock()) return;
    // Dropped on one of its parts: they come after that one.
    const on = () => { const id = dropped && figure.parts.idAt(dropped); if (id && figure.parts.nodeOf(id)) figure.parts.select([id]); };
    const taken = new Set([...(figure.parts.model?.nodes || []).map((node) => node.id)]);
    const prefix = figureFolder();
    const next = (at) => {
      if (at >= sources.length || !figureBlock()) return;
      const chosen = figure.parts.selected.length === 1 ? figure.parts.selected[0] : null;
      const node = structureNode(relativeTo(prefix, sources[at]), taken);
      const where = chosen && figure.parts.nodeOf(chosen) ? { after: chosen, source: chosen }
        : chosen && figure.parts.groupOf(chosen) ? { parent: chosen } : {};
      figure.parts.act({ do: "add", kind: "structure", parent: where.parent || null, after: where.after || null, source: where.source || null,
        node: { id: node.id, label: node.label, properties: node.properties } }, { then: () => next(at + 1), failed: () => next(at + 1) });
    };
    whenFigure(() => { on(); next(0); });
  }

  // -- adding parts --
  async function insertBlock(kind, given = null, where = null) {
    const slide = slideAt();
    const regions = regionsOf(slide);
    if (!regions.length) { toast("This layout has no room for objects. Choose a different layout first.", { icon: "info" }); return; }
    let block = given || NEW_BLOCKS[kind]?.();
    if (!given && kind === "image") {
      const path = await chooseFile({ title: "Choose a Picture", types: ["image"] });
      if (!path) return;
      block = { image: path };
    } else if (!given && kind === "plot") {
      const target = await chooseFunction();
      if (!target) return;
      block = { plot: target };
    } else if (!given && kind === "gallery") {
      const path = await chooseFile({ title: "Choose a Picture", types: ["image"] });
      if (!path) return;
      block = { gallery: [path] };
    } else if (!given && kind === "structure") {
      const path = await chooseFile({ title: "Choose a Structure", types: ["structure"] });
      if (!path) return;
      block = structureFigure([path]);
    }
    // After what is chosen; else in the first empty column, as a new object fills the room there is.
    const anchor = where || state.focus;
    const empty = regions.find((r) => !blocksAt(slide, r.key).length);
    const region = anchor && regions.some((r) => r.key === anchor.region) ? anchor.region : (empty || regions[0]).key;
    let index = 0;
    editSlide((s) => {
      const list = blocksAt(s, region, true);
      index = anchor?.region === region ? Math.min(anchor.index + 1, list.length) : list.length;
      list.splice(index, 0, block);
    });
    focusBlock(region, index);
    if (INLINE.has(kind) && !given) setTimeout(() => openInline({ kind: "block", region, index }, { selectAll: true }), 300);
  }

  // The part moved, by name: a swap read from the slides alone could be either part's.
  const movedLabel = (from) => `Move ${blockLabel(blocksAt(slideAt() || {}, from.region)[from.index])}`;

  function moveBlock(from, to) {
    const label = movedLabel(from);
    editSlide((slide) => {
      const source = blocksAt(slide, from.region, true);
      const [block] = source.splice(from.index, 1);
      const target = blocksAt(slide, to.region, true);
      let index = to.index;
      if (from.region === to.region && from.index < index) index -= 1;
      target.splice(Math.min(index, target.length), 0, block);
      state.focus = { region: to.region, index: Math.min(index, target.length - 1) };
    }, { label });
    renderInspector();
    placeChosen();
  }

  function deleteBlock(at) {
    const block = blocksAt(slideAt(), at.region)[at.index];
    const label = block ? BLOCKS[kindOf(block)].label : "Object";
    editSlide((s) => { blocksAt(s, at.region).splice(at.index, 1); });
    state.focus = null;
    renderInspector();
    placeChosen();
    reportFocus();
    undoNote(`${label} deleted`);
  }

  // -- the inspector --
  function renderInspector() {
    // A figure is edited while it is the part chosen on the slide shown.
    const focus = state.focus;
    if (figure && !(focus && figure.slide === state.slide && focus.region === figure.region && focus.index === figure.index)) leaveFigure(false);
    keepFocus(inspectorBody, () => {
      const slide = slideAt();
      const block = slide && state.focus && blocksAt(slide, state.focus.region)[state.focus.index];
      if (state.focus && !block) state.focus = null;
      clear(inspectorHead, h("div.insp-tabs", {},
        h(`button.insp-tab${state.tab === "slide" ? ".on" : ""}`, { type: "button", onclick: () => { state.tab = "slide"; renderInspector(); } }, icon("slide"), "Format"),
        h(`button.insp-tab${state.tab === "design" ? ".on" : ""}`, { type: "button", onclick: () => { state.tab = "design"; renderInspector(); } }, icon("palette"), "Design")));
      if (state.tab === "design") clear(inspectorBody, designForm());
      else if (!slide) clear(inspectorBody, h("div.empty", {}, "No slides"));
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
          INLINE.has(kind) ? ui.button(kind === "math" ? "Edit Equation" : kind === "code" ? "Edit Code" : "Edit Text", () => openInline({ kind: "block", ...at }), { small: true, icon: "pencil", title: "Edit on the slide (↩), or double-click it" }) : null,
          h("span.spacer", { style: { flex: 1 } }),
          ui.button("", () => moveBlock(at, { region: at.region, index: at.index - 1 }), { kind: "ghost", small: true, icon: "up", title: "Move Up", disabled: at.index === 0 }),
          ui.button("", () => moveBlock(at, { region: at.region, index: at.index + 2 }), { kind: "ghost", small: true, icon: "down", title: "Move Down", disabled: at.index >= count - 1 }),
          ui.button("", () => { editSlide((s) => { const list = blocksAt(s, at.region); list.splice(at.index + 1, 0, structuredClone(list[at.index])); }); focusBlock(at.region, at.index + 1); }, { kind: "ghost", small: true, icon: "copy", title: "Duplicate" }),
          ui.button("", () => deleteBlock(at), { kind: "ghost", small: true, icon: "trash", title: "Delete (⌫)" })),
        regions.length > 1 ? ui.field("Column", ui.segmented({ value: at.region, options: regions.map((r) => ({ value: r.key, label: r.label })),
          onChange: (value) => moveBlock(at, { region: value, index: blocksAt(slideAt(), value).length }) })) : null),
      h("div.section.block-form", { dataset: { region: at.region, index: at.index } }, blockForm(block, kind, at)),
    ];
  }

  function slidePanel(slide) {
    const layout = layoutOf(slide);
    const allowed = new Set(catalog.slide_keys[layout]);
    // A blank slide draws no title: its title and subtitle are offered only once they are set.
    if (layout === "blank") for (const key of ["title", "subtitle"]) if (!slide[key]) allowed.delete(key);
    const text = (key, label, { placeholder = "", markup = true, rows = 1 } = {}) => {
      if (!allowed.has(key)) return null;
      const onInput = (value) => editSlide((s) => setOption(s, key, value), { quiet: true, merge: `${state.slide}-${key}` });
      return ui.field(label, markup ? richField({ value: slide[key] ?? "", single: rows === 1, placeholder, key: `slide.${key}`, onInput })
        : ui.input({ value: slide[key] ?? "", placeholder, key: `slide.${key}`, onInput }));
    };
    const parts = [
      h("div.section", {}, crumbs(slide, null),
        layout === "statement" ? text("words", "Text", { rows: 2, placeholder: "A short statement" }) : text("title", layout === "agenda" ? "Heading" : "Title", { placeholder: layout === "agenda" ? "Outline" : "Slide title" }),
        text("subtitle", "Subtitle"),
        // Each a whole row wide: an author's name and affiliation read without being cut off.
        layout === "title" ? [text("author", "Author", { markup: false }), text("date", "Date", { markup: false })] : null,
        text("by", "Attribution", { markup: false }),
        layout === "agenda" ? h("div.hint-line", {}, "Lists the titles of the deck's section slides automatically.") : null,
        layout === "blank" && (slide.title || slide.subtitle) ? h("div.hint-line", {}, "A blank slide doesn't show its title.") : null),
    ];
    const regions = regionsOf(slide);
    if (regions.length) parts.push(h("div.section", {}, h("div.section-title", {}, "Objects"), regions.map((region) => regionView(slide, region))));
    parts.push(h("div.section", {}, h("div.section-title", {}, "Layout"), layoutGrid(layout, (name) => changeLayout(name), layouts),
      layout === "two-columns" ? splitControl(slide) : null,
      layout === "columns" ? columnsControls(slide) : null,
      allowed.has("align") ? ui.field(styleName("align"), ui.segmented({ value: slide.align ?? "", options: [
        { value: "", label: "Default" }, ...["auto", "top", "middle"].map((value) => ({ value, label: choiceName("align", value) }))],
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
    return ui.field("Left Column Width", h("div.slider", {}, range, value));
  }

  // A layout tried and left keeps what it could not show: going back to the layout before
  // gives the slide back as it was there (if it was not changed in between), and objects
  // a layout without room for them set aside come back with the next layout that has room.
  const layoutStash = new Map();
  function changeLayout(layout) {
    const current = slideAt();
    if (!current || layoutOf(current) === layout) return;
    const earlier = layoutStash.get(JSON.stringify(current));
    if (earlier && layoutOf(earlier) === layout) {
      editSlide((slide) => { for (const key of Object.keys(slide)) delete slide[key]; Object.assign(slide, structuredClone(earlier)); });
      layoutStash.set(JSON.stringify(slideAt()), current);
      state.focus = null;
      renderInspector();
      renderBar();
      return;
    }
    // What the slide had: from before a layout without room, if it came from one.
    const before = earlier && !regionsOf(current).length ? earlier : current;
    const blocks = regionsOf(before).map((region) => blocksAt(before, region.key));
    const lost = WORDLESS.has(layout) && blocks.flat().length;
    editSlide((slide) => {
      for (const [key, value] of Object.entries(before)) if (!(key in slide) && !["layout", "body", "left", "right", "columns"].includes(key)) slide[key] = structuredClone(value);
      const all = blocks.flat();
      const words = layoutOf(slide) === "statement" ? slide.words : slide.title;
      for (const key of ["body", "left", "right", "columns", "split", "widths"]) delete slide[key];
      if (layout === "content") delete slide.layout; else slide.layout = layout;
      if (layout === "statement") { if (words) slide.words = words; delete slide.title; }
      else if (words) { slide.title = words; delete slide.words; }
      // One body made two or more columns: words on the left and what is drawn on the
      // right, as a slide with both is set out; else what is drawn shared across them.
      const drawn = (block) => VISUAL.has(kindOf(block));
      if (layout === "two-columns" && blocks.length === 1 && all.some(drawn) && !all.every(drawn)) {
        slide.left = all.filter((block) => !drawn(block));
        slide.right = all.filter(drawn);
      } else if (layout === "two-columns" && blocks.length === 1 && all.length > 1 && all.every(drawn)) {
        const half = Math.ceil(all.length / 2);
        slide.left = all.slice(0, half);
        slide.right = all.slice(half);
      } else if (layout === "two-columns") { slide.left = blocks[0] || []; slide.right = blocks.slice(1).flat(); }
      else if (layout === "columns" && blocks.length === 1 && all.length > 1) {
        const count = Math.min(all.length, 3), size = Math.ceil(all.length / count);
        slide.columns = Array.from({ length: count }, (_, index) => all.slice(index * size, (index + 1) * size));
      } else if (layout === "columns") slide.columns = blocks.length > 1 ? blocks : [all, [], []];
      else if (!WORDLESS.has(layout)) slide.body = all;
      const allowed = new Set([...catalog.slide_keys[layout], "layout"]);
      for (const key of Object.keys(slide)) if (!allowed.has(key)) delete slide[key];
    });
    layoutStash.set(JSON.stringify(slideAt()), current);
    state.focus = null;
    renderInspector();
    renderBar();
    if (lost) undoNote(`Objects removed: the ${LAYOUT_NAMES[layout]} layout has no room for them`, { icon: "info", seconds: 6 });
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
      ui.button("", () => count > 1 && setCount(count - 1), { icon: "minus", small: true, disabled: count <= 1, title: "Fewer columns" }),
      h("span", { style: { textAlign: "center", fontWeight: 600 } }, `${count} column${count === 1 ? "" : "s"}`),
      ui.button("", () => count < 6 && setCount(count + 1), { icon: "plus", small: true, disabled: count >= 6, title: "More columns" }));
    stepper.firstChild.classList.add("fixed"); stepper.lastChild.classList.add("fixed");
    const shares = h("div.row", {}, Array.from({ length: count }, (_, i) => ui.number({ value: widths?.[i] ?? "", placeholder: "1", min: 0.1, step: 0.5, key: `widths.${i}`,
      onChange: (value) => editSlide((s) => {
        const next = Array.from({ length: count }, (_, j) => (j === i ? value : s.widths?.[j]) ?? 1);
        if (next.every((v) => v === 1)) delete s.widths; else s.widths = next;
      }, { quiet: true, merge: `${state.slide}-widths-${i}` }) })));
    return h("div.field", {}, ui.field("Columns", stepper), ui.field("Widths", shares, { hint: "Relative, e.g. 2 1 1" }));
  }

  function backgroundControls(slide, allowed) {
    const background = slide.background;
    const mode = !background ? "" : String(background).startsWith("#") ? "colour" : "picture";
    const parts = [ui.segmented({ value: mode, options: [{ value: "", label: "Default" }, { value: "colour", label: "Colour" }, { value: "picture", label: "Picture" }],
      onChange: async (value) => {
        if (value === "") editSlide((s) => { delete s.background; delete s.shade; delete s.dark; });
        else if (value === "colour") editSlide((s) => { s.background = "#1b2a41"; delete s.shade; });
        else {
          const path = await chooseFile({ title: "Choose a Background Picture", types: ["image"] });
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
      parts.push(fileRow(background, ["image"], (path) => editSlide((s) => { s.background = path; }), "Picture file"));
      const shade = slide.shade ?? 0;
      const value = h("span.value", {}, `${Math.round(shade * 100)}%`);
      const range = h("input", { type: "range", min: 0, max: 0.9, step: 0.05, value: shade, oninput: () => {
        value.textContent = `${Math.round(range.value * 100)}%`;
        editSlide((s) => setOption(s, "shade", Number(range.value), 0), { quiet: true, merge: `${state.slide}-shade` });
      } });
      parts.push(ui.field("Darken", h("div.slider", {}, range, value)));
    }
    if (mode && allowed.has("dark")) {
      parts.push(ui.field("Text", ui.segmented({ value: slide.dark === true ? "light" : slide.dark === false ? "dark" : "", options: [
        { value: "", label: "Auto" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }],
        onChange: (value) => editSlide((s) => setOption(s, "dark", value === "light" ? true : value === "dark" ? false : null), { quiet: true }) })));
    }
    return h("div", { style: { display: "grid", gap: "8px" } }, parts);
  }

  function footnotesControls(slide) {
    const list = Array.isArray(slide.footnotes) ? slide.footnotes : slide.footnotes ? [slide.footnotes] : [];
    const rows = list.map((note, i) => h("div.list-row", {},
      ui.markup({ value: note, key: `footnote.${i}`, placeholder: "Reference or note", onInput: (value) => editSlide((s) => { s.footnotes = [...list]; s.footnotes[i] = value; }, { quiet: true, merge: `${state.slide}-fn-${i}` }) }),
      ui.button("", () => { editSlide((s) => { const next = list.filter((_, j) => j !== i); if (next.length) s.footnotes = next; else delete s.footnotes; }); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, title: "Delete" })));
    rows.forEach((row) => { row.firstChild.style.flex = "1"; });
    return h("div.list-rows", {}, rows,
      h("div", {}, ui.button("Add Footnote", () => { editSlide((s) => { s.footnotes = [...list, "[1] Author et al., *Venue* (2026)"]; }); renderInspector(); }, { kind: "ghost", icon: "plus", small: true })));
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
    regionsOf(slide).length > 1 ? h("div.region-head", {}, region.name) : null,
    h("div.blocks", {}, blocks.map((block, index) => blockRow(block, region, index)),
      h("button.add-row", { type: "button", onclick: (event) => menu(event.currentTarget, Object.entries(BLOCKS).map(([kind, info]) => ({
        icon: info.icon, label: info.label, hint: info.hint, run: () => insertBlock(kind, null, { region: region.key, index: blocks.length - 1 }),
      }))) }, icon("plus"), "Add Object")));
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
    // What was wrong before and is mended now goes; what is wrong now is marked.
    inspectorBody.querySelectorAll(".block-form > .block-error:not(.soft)").forEach((node) => node.remove());
    inspectorBody.querySelectorAll(".block-row.error").forEach((node) => node.classList.remove("error"));
    for (const message of messages) {
      const where = placeOf(message.where);
      if (!where || where.slide !== state.slide || where.region === null || message.severity !== "error") continue;
      inspectorBody.querySelector(`.block-row[data-region="${where.region}"][data-index="${where.index}"]`)?.classList.add("error");
      const form = inspectorBody.querySelector(`.block-form[data-region="${where.region}"][data-index="${where.index}"]`);
      if (form && !form.querySelector(".block-error")) form.prepend(h("div.block-error", {}, icon("error"), message.text));
    }
  }

  // Words in the inspector as the slide shows them (richtext.js), in a field's box: Return
  // in a one-line field is done, as in a Mac text field.
  function richField({ value, key, placeholder = "", list = false, single = false, numbered = false, onInput }) {
    const area = richText({ value, list, single, numbered, placeholder, palette: studio.info?.palette || {} });
    area.dataset.key = key;
    area.addEventListener("input", () => onInput(area.value));
    if (single) area.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) area.blur(); });
    return h(`div.rich-field${single ? ".single" : ""}`, {}, area);
  }

  // -- the form for each kind of part --
  function blockForm(block, kind, at) {
    const merge = (name) => `${state.slide}-${at.region}-${at.index}-${name}`;
    const key = (name) => `block.${name}`;
    const set = (name, fallback) => (value) => editBlock(at, (b) => setOption(b, name, value, fallback), { merge: merge(name) });
    const edit = (mutate, name) => editBlock(at, mutate, { merge: merge(name) });
    const size = () => ui.field("Font Size", ui.number({ value: block.size, placeholder: "Auto", min: 4, step: 1, key: key("size"), onChange: set("size") }), { hint: "In points" });
    const toneSwatches = (name, { none = true, extra = [], fallback } = {}) => {
      const palette = studio.info?.palette || {};
      const colours = [...TONES.map((tone, i) => ({ value: tone, colour: palette[tone] || "#888", title: i === 0 ? "Accent" : `Accent ${i + 1}` })), ...extra];
      return ui.swatches({ value: block[name] ?? fallback ?? null, colours, none, custom: true,
        onChange: (value) => editBlock(at, (b) => setOption(b, name, value, fallback), { merge: merge(name) }) });
    };
    switch (kind) {
      case "bullets":
        return [richField({ value: bulletsText(block.bullets), list: true, numbered: Boolean(block.numbered), key: key("bullets"),
          onInput: (text) => edit((b) => { b.bullets = bulletsFrom(text); }, "items") }),
        h("div.hint-line", {}, "Return starts the next item; ", h("kbd", {}, "Tab"), " and ", h("kbd", {}, "⇧Tab"), " change its level."),
        h("div.row", {}, ui.toggle({ value: block.numbered, label: "Numbered", onChange: set("numbered", false) }),
          ui.toggle({ value: block.reveal, label: "Reveal items one at a time", onChange: set("reveal", false) })),
        size()];
      case "text":
        return [richField({ value: block.text ?? "", key: key("text"), onInput: (text) => edit((b) => { b.text = text; }, "text") }),
          ui.field("Align", ui.segmented({ value: block.align || "start", options: [
            { value: "start", label: "Left" }, { value: "middle", label: "Centre" }, { value: "end", label: "Right" }],
          onChange: (value) => editBlock(at, (b) => setOption(b, "align", value, "start")) })),
          ui.field("Colour", toneSwatches("colour", { extra: [{ value: "muted", colour: studio.info?.palette?.muted || "#999", title: "Muted" }] })),
          size()];
      case "quote":
        return [richField({ value: block.quote ?? "", key: key("quote"), onInput: (text) => edit((b) => { b.quote = text; }, "quote") }),
          ui.field("Attribution", ui.input({ value: block.by, placeholder: "Name", key: key("by"), onInput: set("by") })), size()];
      case "callout":
        return [ui.field("Heading", ui.input({ value: block.title, placeholder: "Optional", key: key("title"), onInput: (text) => edit((b) => setOption(b, "title", text), "title") })),
          ui.field("Text", richField({ value: block.callout ?? "", key: key("callout"), onInput: (text) => edit((b) => { b.callout = text; }, "words") })),
          ui.field("Colour", toneSwatches("colour", { none: false, fallback: "accent" })), size()];
      case "code":
        return [ui.textarea({ value: block.code, rows: 5, mono: true, key: key("code"), onInput: (text) => edit((b) => { b.code = text; }, "code") }),
          h("div.hint-line", {}, "Shown exactly as typed. Whole-line comments are dimmed."), size()];
      case "stats": return statsForm(block, at, edit, toneSwatches, size);
      case "table": return tableForm(block, at, edit, size);
      case "image": return imageForm(block, at);
      case "gallery": return galleryForm(block, at, edit, size);
      case "figure": return figureForm(block, at, edit);
      case "plot":
        return [ui.field("Function", functionInput(block.plot, (value) => edit((b) => { b.plot = value; }, "plot")), { hint: "file.py:function" }),
          h("div.hint-line", {}, "A function that returns a matplotlib figure. It runs inside ", h("code", {}, "deck.plotting()"), " and receives the deck if it takes an argument."),
          ui.field("Aspect Ratio", ui.number({ value: block.aspect, placeholder: "Auto", min: 0.2, step: 0.1, key: key("aspect"), onChange: set("aspect") }), { hint: "Width ÷ height" })];
      case "math": return mathForm(block, at, edit, toneSwatches, size);
      case "mechanism": return mechanismForm(block, at, edit, toneSwatches);
      default:
        return [h("div.hint-line", {}, "No settings for this object")];
    }
  }

  function mathForm(block, at, edit, toneSwatches, size) {
    const area = ui.textarea({ value: block.math, rows: 3, mono: true, grow: true, key: "block.math",
      placeholder: "E = mc^2", onInput: (text) => edit((b) => { b.math = text; }, "math") });
    const insert = (snippet) => {
      const [before, after = ""] = snippet.split("|");
      const start = area.selectionStart, end = area.selectionEnd;
      const chosen = area.value.slice(start, end);
      area.value = area.value.slice(0, start) + before + chosen + after + area.value.slice(end);
      const at = start + before.length + chosen.length;
      area.focus();
      area.setSelectionRange(at, at);
      area.dispatchEvent(new Event("input"));
    };
    const chips = MATH_SNIPPETS.map(([label, title, snippet]) => h("button.math-chip", { type: "button", title,
      onmousedown: (event) => { event.preventDefault(); insert(snippet); } }, label));
    // What could not be read in it, said beside it (the slide shows it in red), and said
    // afresh with each drawing as it is typed.
    const notes = h("div.math-notes");
    const note = () => {
      const source = area.value.trim().slice(0, 20);
      const said = messages.filter((m) => m.page === `slide${state.slide + 1}` && m.text.includes(", in the maths “")
        && source && m.text.includes(source));
      clear(notes);
      notes.append(...said.map((m) => h("div.block-error.soft", {}, icon("warning"), m.text.replace(/, in the maths “[\s\S]*”$/, ""))));
    };
    note();
    mathNotes = note;
    return [area, h("div.math-chips", {}, chips), notes,
      h("div.hint-line", {}, "Type LaTeX. ", h("code", {}, "\\\\"), " starts a new line and ", h("code", {}, "&"),
        " aligns lines. In text, put maths between ", h("code", {}, "$"), " signs, or ", h("code", {}, "$$"), " for maths on its own line."),
      ui.field("Align", ui.segmented({ value: block.align || "middle", options: [
        { value: "start", label: "Left" }, { value: "middle", label: "Centre" }, { value: "end", label: "Right" }],
      onChange: (value) => editBlock(at, (b) => setOption(b, "align", value, "middle")) })),
      ui.field("Colour", toneSwatches("colour", { extra: [{ value: "muted", colour: studio.info?.palette?.muted || "#999", title: "Muted" }] })),
      size()];
  }

  function mechanismForm(block, at, edit, toneSwatches) {
    // Each step a card: its structure, its arrows, and what is written by it.
    const steps = (Array.isArray(block.mechanism) ? block.mechanism : [block.mechanism])
      .map((step) => (typeof step === "string" ? { smiles: step } : { ...(step || {}) }));
    const write = (what) => edit((b) => {
      b.mechanism = steps.map((step) => {
        const out = {};
        for (const [key, value] of Object.entries(step)) {
          if (key === "arrows" ? value && value.length : value !== "" && value !== undefined && value !== null) out[key] = value;
        }
        return out;
      });
    }, what);
    const arrowsText = (step) => (Array.isArray(step.arrows) ? step.arrows.join("; ") : step.arrows || "");
    const cards = steps.map((step, i) => h("div.step-card", {},
      h("div.step-head", {}, h("span", {}, `Step ${i + 1}`), h("div.spacer"),
        ui.button("Draw Arrows…", () => drawArrows(at, i), { kind: "ghost", icon: "mechanism", small: true,
          title: "Draw this step's arrows: click where the electrons come from, then where they go" }),
        ui.button("", () => { steps.splice(i, 1); write("steps"); renderInspector(); },
          { kind: "ghost", icon: "trash", small: true, disabled: steps.length <= 1 })),
      ui.field("Structure", ui.input({ value: step.smiles || "", mono: true, key: `step.${i}.smiles`,
        placeholder: i ? "Auto (result of the previous arrows)" : "SMILES with atom maps, e.g. [O-:5]",
        onInput: (value) => { step.smiles = value; write("smiles"); } })),
      ui.field("Arrows", ui.input({ value: arrowsText(step), mono: true, key: `step.${i}.arrows`, placeholder: "5 -> 2; 2=3 -> 3",
        onInput: (value) => { step.arrows = value.split(";").map((part) => part.trim()).filter(Boolean); write("arrows"); } })),
      ui.field("Label", ui.input({ value: step.label || "", key: `step.${i}.label`, placeholder: "Shown below the structure",
        onInput: (value) => { step.label = value; write("label"); } })),
      i < steps.length - 1 || (step.arrows && step.arrows.length)
        ? [ui.field("Above Arrow", ui.input({ value: step.reagents || "", key: `step.${i}.reagents`, placeholder: "NaOH",
            onInput: (value) => { step.reagents = value; write("reagents"); } })),
          ui.field("Below Arrow", ui.input({ value: step.conditions || "", key: `step.${i}.conditions`, placeholder: "heat",
            onInput: (value) => { step.conditions = value; write("conditions"); } })),
          ui.field("Arrow", ui.segmented({ value: step.arrow || "forward", options: [
            { value: "forward", label: "→" }, { value: "equilibrium", label: "⇌" },
            { value: "resonance", label: "↔" }, { value: "none", label: "None" }],
          onChange: (value) => { step.arrow = value === "forward" ? undefined : value; write("arrow"); renderInspector(); } }))]
        : null));
    return [h("div.step-cards", {}, cards),
      h("div", {}, ui.button("Add Step", () => { steps.push({ arrows: [] }); write("steps"); renderInspector(); },
        { kind: "ghost", icon: "plus", small: true })),
      h("div.hint-line", {}, "Atoms are numbered by their atom maps: ", h("code", {}, "[O-:5]"), " is atom 5. ",
        h("code", {}, "5 -> 2"), ": lone pair to atom. ", h("code", {}, "2=3 -> 3"), ": bond to atom. ",
        h("code", {}, "1=2 -> 2-6"), ": bond to bond. ", h("code", {}, "~>"), ": one electron. A step with no structure uses the result of the arrows before it; a structure you enter is checked."),
      ui.field("Lone Pairs", ui.segmented({ value: block.lone_pairs || "used", options: [
        { value: "used", label: "Used" }, { value: "all", label: "All" }, { value: "none", label: "None" }],
      onChange: (value) => editBlock(at, (b) => setOption(b, "lone_pairs", value, "used")) })),
      ui.field("Charges", ui.segmented({ value: block.charges || "circled", options: [
        { value: "circled", label: "Circled" }, { value: "plain", label: "Plain" }],
      onChange: (value) => editBlock(at, (b) => setOption(b, "charges", value, "circled")) })),
      // Any colour: the deck's accents, ink or muted ink follow its theme; magenta unless chosen.
      ui.field("Arrow Colour", toneSwatches("arrow_colour", { none: false, fallback: ARROW_INK, extra: [
        { value: ARROW_INK, colour: ARROW_INK, title: "Magenta" },
        { value: "ink", colour: studio.info?.palette?.ink || "#222", title: "Ink" },
        { value: "muted", colour: studio.info?.palette?.muted || "#999", title: "Muted" }] }))];
  }

  // -- drawing a mechanism's arrows by pointing (after mechazyme's editor) --
  // The structure a step acts on, drawn alone and large: an atom stands for its lone
  // pair, a bond for its electrons, and two clicks -- where the electrons come from,
  // where they go -- write an arrow. The page draws and points; Python decides what a
  // click means, and says when a step cannot be (between one arrow and the next it
  // usually cannot: that is drawn too). The step holds still while it is drawn on.
  function drawArrows(place, first) {
    const at = { slide: state.slide, region: place.region, index: place.index };
    const view = { step: first, holding: [], sheet: null, pending: null, asking: null, half: false,
      said: "", hovering: null, busy: false, shown: null, mode: "arrows", chosen: null };
    const nav = h("div.mech-nav");
    const sheetBox = h("div.mech-sheet");
    const banner = h("div.mech-banner-slot");
    const list = h("div.mech-arrows");
    // The step cards behind are written afresh when it closes: their arrows have changed.
    dialog({ title: "Draw Mechanism Arrows", wide: true, body: [nav, sheetBox, banner, list],
      actions: [{ label: "Done", kind: "primary" }], onClose: () => renderInspector() });
    const NS = "http://www.w3.org/2000/svg";
    const S = (tag, attributes = {}, ...children) => {
      const node = document.createElementNS(NS, tag);
      for (const [key, value] of Object.entries(attributes)) if (value !== undefined && value !== null && value !== false) node.setAttribute(key, value);
      for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
      return node;
    };
    const nameOf = (index) => view.sheet?.atoms.find((atom) => atom.index === index)?.name ?? String(index);
    const samePick = (a, b) => Boolean(a && b && a.kind === b.kind && (a.kind === "atom" ? a.index === b.index
      : [...a.atoms].sort().join() === [...b.atoms].sort().join()));
    const arrowsOf = (step) => {
      const slide = studio.doc?.slides?.[at.slide];
      const block = slide && blocksAt(slide, at.region)[at.index];
      const steps = block ? (Array.isArray(block.mechanism) ? block.mechanism : [block.mechanism]) : [];
      const arrows = steps[step] && typeof steps[step] === "object" ? steps[step].arrows : null;
      if (Array.isArray(arrows)) return arrows.map(String);
      return typeof arrows === "string" ? arrows.split(";").map((part) => part.trim()).filter(Boolean) : [];
    };
    // Laid out for the arrows the step has when it is opened (or tidied), and held so.
    const hold = () => { view.holding = arrowsOf(view.step); };

    async function act(extra) {
      view.busy = true;
      try {
        for (let attempt = 0; attempt < 3; attempt += 1) {
          const sent = studio.doc;
          const result = await studio.api("/api/act", { file: studio.file, document: sent,
            action: { do: "mechanism", at, step: view.step, holding: view.holding, ...extra } });
          if (!same(studio.doc, sent)) continue;
          if (result.document && !same(result.document, sent)) studio.change(() => result.document, { quiet: true });
          return result;
        }
        return null;
      } catch (error) {
        flash(error.message);
        return null;
      } finally {
        view.busy = false;
      }
    }
    async function load() {
      const result = await act({});
      if (result?.sheet) { view.sheet = result.sheet; view.step = result.sheet.step; }
      render();
    }
    async function go(step) {
      Object.assign(view, { step, pending: null, asking: null, hovering: null, chosen: null });
      hold();
      await load();
    }
    async function add(tail, head) {
      const result = await act({ add: { tail, head, half: view.half } });
      view.pending = null;
      if (result?.ends) view.asking = { ends: result.ends, tail, head };
      else if (result?.sheet) view.sheet = result.sheet;
      render();
    }
    // A molecule moved, turned, flipped or put back: Python keeps where it goes, by its atom.
    async function arrange(how) {
      if (view.chosen === null) return;
      const result = await act({ place: { atom: view.chosen, ...how } });
      if (result?.sheet) view.sheet = result.sheet;
      render();
    }
    const chosenMolecule = () => (view.sheet?.molecules || []).find((molecule) => molecule.atoms.includes(view.chosen));
    async function remove(index) {
      const result = await act({ remove: index });
      if (result?.sheet) view.sheet = result.sheet;
      render();
    }
    function flash(message) {
      view.said = message;
      render();
      setTimeout(() => { if (view.said === message) { view.said = ""; render(); } }, 3500);
    }
    function cancel() { view.pending = null; view.asking = null; render(); }

    function pick(kind, payload) {
      if (view.busy) return;
      const picked = { kind, ...payload };
      if (view.asking) {
        // Only the two ends it named will do; the answer finishes the arrow that asked.
        if (kind !== "atom" || !view.asking.ends.some((end) => end.index === payload.index)) {
          flash(`Click ${view.asking.ends.map((end) => end.name).join(" or ")}: the atom the new bond forms from.`);
          return;
        }
        const { tail, head } = view.asking;
        view.asking = null;
        add(tail, { bond: [payload.index, head.atom] });
        return;
      }
      if (!view.pending) { view.pending = picked; render(); return; }
      if (samePick(view.pending, picked)) { cancel(); return; }
      const from = view.pending;
      add(from.kind === "atom" ? { atom: from.index } : { bond: from.atoms },
        kind === "atom" ? { atom: payload.index } : { bond: payload.atoms });
    }

    function render() {
      renderNav();
      renderSheet();
      renderBanner();
      renderList();
    }
    function renderNav() {
      const states = view.sheet?.states || 1;
      const steps = view.sheet?.steps || 1;
      const name = view.step < steps ? `Step ${view.step + 1}` : "Product";
      clear(nav,
        ui.button("", () => go(view.step - 1), { kind: "ghost", icon: "left", small: true, disabled: view.step <= 0, title: "Previous step" }),
        h("span.mech-step", {}, name, h("span.mech-of", {}, ` · ${view.step + 1} of ${states}`)),
        ui.button("", () => go(view.step + 1), { kind: "ghost", icon: "right", small: true, disabled: view.step >= states - 1, title: "Next step" }),
        ui.segmented({ value: view.mode, options: [{ value: "arrows", label: "Arrows" }, { value: "arrange", label: "Arrange" }],
          onChange: (value) => { Object.assign(view, { mode: value, pending: null, asking: null, hovering: null }); render(); } }),
        h("div.spacer"),
        view.mode === "arrows"
          ? [ui.toggle({ value: view.half, label: "Single electron (fishhook)", onChange: (value) => { view.half = value; } }),
            ui.button("Clean Up", () => go(view.step), { kind: "ghost", small: true, title: "Lay out the structure again for the current arrows" })]
          : chosenMolecule()
            ? [ui.button("↺", () => arrange({ turn: -30 }), { kind: "ghost", small: true, title: "Rotate 30° anticlockwise" }),
              ui.button("↻", () => arrange({ turn: 30 }), { kind: "ghost", small: true, title: "Rotate 30° clockwise" }),
              ui.button("Flip", () => arrange({ flip: true }), { kind: "ghost", small: true, title: "Flip horizontally" }),
              ui.button("Reset", () => arrange({ reset: true }), { kind: "ghost", small: true, disabled: !chosenMolecule().placed,
                title: "Reset to the automatic layout" })]
            : null);
    }
    function renderSheet() {
      const sheet = view.sheet;
      if (!sheet?.svg) {
        view.shown = null;
        clear(sheetBox, h("div.mech-empty", {}, sheet ? "The first structure can't be read." : "Loading…"));
        return;
      }
      sheetBox.style.background = sheet.paper || "";
      if (view.shown !== sheet.svg) {
        // Only repainted when it differs: an identical drawing replaced flickers under the hand.
        const drawing = h("div.mech-drawing");
        drawing.innerHTML = sheet.svg;
        view.shown = sheet.svg;
        clear(sheetBox, drawing, hitLayer());
      } else {
        sheetBox.querySelector(".mech-hit")?.replaceWith(hitLayer());
      }
    }
    function hitLayer() {
      if (view.mode === "arrange") return arrangeLayer();
      const sheet = view.sheet;
      const r = sheet.bond;
      const asked = new Set((view.asking?.ends || []).map((end) => end.index));
      const layer = S("svg", { class: "mech-hit", viewBox: sheet.view.join(" "), preserveAspectRatio: "xMidYMid meet" });
      for (const bond of sheet.bonds) {
        const picked = samePick(view.pending, { kind: "bond", atoms: bond.atoms });
        const node = S("circle", { class: `mech-bond${picked ? " picked" : ""}`, cx: bond.x, cy: bond.y, r: r * 0.24 },
          S("title", {}, `${nameOf(bond.atoms[0])}–${nameOf(bond.atoms[1])} bond`));
        node.addEventListener("click", () => pick("bond", { atoms: bond.atoms }));
        layer.append(node);
      }
      for (const atom of sheet.atoms) {
        const picked = samePick(view.pending, { kind: "atom", index: atom.index });
        const node = S("circle", { class: `mech-atom${picked ? " picked" : ""}${asked.has(atom.index) ? " asked" : ""}`,
          cx: atom.x, cy: atom.y, r: r * 0.32 }, S("title", {}, atom.name));
        node.addEventListener("click", () => pick("atom", { index: atom.index }));
        node.addEventListener("mouseenter", () => hover(atom.index));
        layer.append(node);
      }
      layer.append(S("g", { class: "mech-pairs" }), S("g", { class: "mech-numbers" }));
      layer.addEventListener("mouseleave", () => hover(null));
      paintHover(layer);
      return layer;
    }
    // Each molecule one thing to take hold of: dragged, it moves under the pointer and is
    // placed where it is let go; clicked, it is chosen, to turn, flip or put back.
    function arrangeLayer() {
      const sheet = view.sheet;
      const r = sheet.bond;
      const layer = S("svg", { class: "mech-hit arrange", viewBox: sheet.view.join(" "), preserveAspectRatio: "xMidYMid meet" });
      for (const molecule of sheet.molecules || []) {
        const chosen = molecule.atoms.includes(view.chosen);
        const group = S("g", { class: `mech-molecule${chosen ? " chosen" : ""}` },
          S("title", {}, "Drag to move · Click to select, then rotate or flip"),
          sheet.atoms.filter((atom) => molecule.atoms.includes(atom.index)).map((atom) => S("circle", { cx: atom.x, cy: atom.y, r: r * 0.45 })),
          sheet.bonds.filter((bond) => molecule.atoms.includes(bond.atoms[0])).map((bond) => S("circle", { cx: bond.x, cy: bond.y, r: r * 0.36 })));
        group.addEventListener("pointerdown", (event) => drag(event, molecule, group, layer));
        layer.append(group);
      }
      return layer;
    }
    function drag(event, molecule, group, layer) {
      if (view.busy) return;
      event.preventDefault();
      const toSheet = (e) => {
        const point = layer.createSVGPoint();
        point.x = e.clientX;
        point.y = e.clientY;
        return point.matrixTransform(layer.getScreenCTM().inverse());
      };
      const start = toSheet(event);
      const drawing = sheetBox.querySelector(".mech-drawing svg");
      const parts = drawing ? molecule.ids.flatMap((id) => [...drawing.querySelectorAll(`[id="${CSS.escape(id)}"], [id^="${CSS.escape(id)}."]`)]) : [];
      const before = parts.map((part) => part.getAttribute("transform"));
      let moved = { x: 0, y: 0 };
      group.setPointerCapture(event.pointerId);
      const follow = (e) => {
        const here = toSheet(e);
        moved = { x: here.x - start.x, y: here.y - start.y };
        const shift = `translate(${moved.x} ${moved.y})`;
        parts.forEach((part, i) => part.setAttribute("transform", before[i] ? `${shift} ${before[i]}` : shift));
        group.setAttribute("transform", shift);
      };
      const end = () => {
        group.removeEventListener("pointermove", follow);
        group.removeEventListener("pointerup", end);
        group.removeEventListener("pointercancel", end);
        view.chosen = molecule.atoms[0];
        if (Math.hypot(moved.x, moved.y) < view.sheet.bond * 0.08) { render(); return; }
        arrange({ move: [moved.x / view.sheet.bond, moved.y / view.sheet.bond] });
      };
      group.addEventListener("pointermove", follow);
      group.addEventListener("pointerup", end);
      group.addEventListener("pointercancel", end);
    }
    function hover(index) {
      if (view.hovering === index) return;
      view.hovering = index;
      const layer = sheetBox.querySelector(".mech-hit");
      if (layer) paintHover(layer);
    }
    // The electrons an atom has to give, shown under the pointer where an arrow off them
    // would start, each pair a target of its own; and numbers on the atoms the arrows
    // name, the one pointed at, and the one picked -- a number on every atom is none.
    function paintHover(layer) {
      const sheet = view.sheet;
      const r = sheet.bond;
      const pairs = layer.querySelector(".mech-pairs");
      if (!pairs) return;
      const numbers = layer.querySelector(".mech-numbers");
      const atom = sheet.atoms.find((item) => item.index === view.hovering);
      clear(pairs, ...(atom ? atom.pairs.map(([x1, y1, x2, y2]) => {
        const grab = S("circle", { class: "mech-grab", cx: (x1 + x2) / 2, cy: (y1 + y2) / 2, r: r * 0.2 },
          S("title", {}, `Lone pair on ${atom.name}`));
        grab.addEventListener("click", () => pick("atom", { index: atom.index }));
        grab.addEventListener("mouseenter", () => hover(atom.index));
        return [S("circle", { class: "mech-dot", cx: x1, cy: y1, r: Math.max(sheet.dot, r * 0.055) }),
          S("circle", { class: "mech-dot", cx: x2, cy: y2, r: Math.max(sheet.dot, r * 0.055) }), grab];
      }) : []));
      const shown = new Set([...sheet.named, view.hovering, view.pending?.kind === "atom" ? view.pending.index : null,
        ...(view.pending?.kind === "bond" ? view.pending.atoms : []), ...(view.asking?.ends || []).map((end) => end.index)]);
      clear(numbers, ...sheet.atoms.filter((item) => shown.has(item.index)).map((item) =>
        S("text", { class: "mech-number", x: item.tag[0], y: item.tag[1], "font-size": r * 0.3,
          "text-anchor": "middle", "dominant-baseline": "central" }, item.number ?? "·")));
    }
    function renderBanner() {
      const sheet = view.sheet;
      const ask = (...words) => h("div.mech-banner.ask", {}, h("span.mech-light"), h("span.mech-words", {}, ...words));
      const stop = (label = "Cancel") => ui.button(label, cancel, { kind: "ghost", small: true });
      const pickWords = (pick) => (pick.kind === "atom" ? [`the lone pair on `, h("b", {}, nameOf(pick.index))]
        : ["the ", h("b", {}, `${nameOf(pick.atoms[0])}–${nameOf(pick.atoms[1])}`), " bond"]);
      let line;
      if (view.said) line = ask(view.said);
      else if (view.mode === "arrange") {
        const molecule = chosenMolecule();
        line = molecule
          ? ask("Molecule with ", h("b", {}, nameOf(view.chosen)), " selected. Drag to move it, or rotate, flip or reset it with the buttons above.")
          : ask(h("b", {}, "Drag"), " a molecule to move it. Click a molecule to select it, then rotate or flip it.");
      }
      else if (view.asking) {
        line = h("div.mech-banner.ask", {}, h("span.mech-light"), h("span.mech-words", {},
          "The new bond could form from either end. Click the atom it forms from: ",
          ...view.asking.ends.flatMap((end, i) => [i ? " or " : "", h("b", {}, end.name)]), "."), stop());
      } else if (view.pending) {
        line = h("div.mech-banner.ask", {}, h("span.mech-light"), h("span.mech-words", {},
          "Electrons from ", ...pickWords(view.pending),
          ". Now click where they go: an atom to bond to or land on, or a bond to strengthen."), stop());
      } else if (sheet?.problem) {
        line = h("div.mech-held", {}, h("div.mech-held-lead", {}, h("span.mech-tag", {}, "Error"),
          h("span.mech-code", {}, sheet.problem.code)), h("div", {}, sheet.problem.message),
          sheet.problem.hint ? h("div.mech-hint", {}, sheet.problem.hint) : null);
      } else if (!sheet?.arrows?.length) {
        line = ask("Click where the electrons ", h("b", {}, "come from"), ": an atom (for its lone pair) or a bond.");
      } else {
        const count = sheet.arrows.length;
        line = h("div.mech-banner.ok", {}, h("span.mech-light"), h("span.mech-words", {},
          `${view.step < sheet.steps ? `Step ${view.step + 1}` : "This step"} is valid with ${count} ${count === 1 ? "arrow" : "arrows"}. Click to add another.`));
      }
      clear(banner, line);
    }
    function renderList() {
      const rows = (view.sheet?.arrows || []).map((arrow, i) => h(`div.mech-arrow-row${arrow.problem ? ".wrong" : ""}`, {},
        h("span.mech-said", {}, arrow.said || arrow.problem || arrow.text),
        h("code", {}, arrow.text),
        ui.button("", () => remove(i), { kind: "ghost", icon: "trash", small: true, title: "Delete arrow" })));
      clear(list, rows.length ? [h("div.mech-list-head", {}, "Arrows in This Step"), rows] : null);
    }

    hold();
    render();
    load();
  }

  function statsForm(block, at, edit, toneSwatches, size) {
    const items = (Array.isArray(block.stats) ? block.stats : []).map((item) => (Array.isArray(item) ? { value: item[0], label: item[1] } : item && typeof item === "object" ? { ...item } : { value: item, label: "" }));
    const write = () => edit((b) => { b.stats = items.map((item) => ({ ...item })); }, "stats");
    const rows = items.map((item, i) => h("div.list-row", {},
      ui.input({ value: String(item.value ?? ""), placeholder: "93%", key: `stat.${i}.value`, onInput: (value) => { items[i].value = value; write(); } }),
      ui.input({ value: item.label ?? "", placeholder: "Label", key: `stat.${i}.label`, onInput: (value) => { items[i].label = value; write(); } }),
      ui.button("", () => { items.splice(i, 1); editBlock(at, (b) => { b.stats = items; }); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, disabled: items.length <= 1 })));
    rows.forEach((row) => { row.firstChild.style.flex = "0 0 96px"; });
    return [h("div.list-rows", {}, rows),
      h("div", {}, ui.button("Add Number", () => { editBlock(at, (b) => { b.stats = [...items, { value: "1", label: "more" }]; }); renderInspector(); }, { kind: "ghost", icon: "plus", small: true })),
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
      const cell = h("input", { value: rows[r][c], dataset: { key: `cell.${r}.${c}` },
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
          toast(`${grid.length} × ${Math.max(...grid.map((line) => line.length))} cells pasted`, { icon: "table", seconds: 2 });
        } });
      cell.spellcheck = false;  // h() leaves out what is false
      return cell;
    };
    const alignRow = h("tr", {}, h("th.corner"), Array.from({ length: columns }, (_, c) => h("th", {},
      ui.select({ value: given ? given[c] : "", options: [{ value: "", label: `Auto (${auto[c] === "end" ? "Right" : "Left"})` }, { value: "start", label: "Left" }, { value: "middle", label: "Centre" }, { value: "end", label: "Right" }],
        onChange: (value) => editBlock(at, (b) => {
          const next = given ? [...given] : [...auto];
          next[c] = value || auto[c];
          if (next.every((v, i) => v === auto[i])) delete b.align; else b.align = next;
        }) }))), h("th.corner"));
    const table = h("table", {}, alignRow, rows.map((row, r) => h(`tr${header && r === 0 ? ".header" : ""}`, {},
      h("td.corner", {}, r + 1),
      row.map((_, c) => h("td", {}, input(r, c))),
      h("td.corner", {}, rows.length > 1 ? h("button", { type: "button", title: "Delete Row", onclick: () => restructure(() => rows.splice(r, 1)) }, icon("close")) : null))),
    h("tr", {}, h("td.corner"), Array.from({ length: columns }, (_, c) => h("td.corner", {}, columns > 1 ? h("button", { type: "button", title: "Delete Column", onclick: () => restructure(() => rows.forEach((row) => row.splice(c, 1))) }, icon("close")) : null)), h("td.corner")));
    table.querySelectorAll("th select").forEach((el) => el.classList.remove("select"));
    return [h("div.table-edit.scroll-thin", {}, table),
      h("div.row", {},
        ui.button("Add Row", () => restructure(() => rows.push(Array(columns).fill(""))), { kind: "ghost", icon: "plus", small: true }),
        ui.button("Add Column", () => restructure(() => rows.forEach((row) => row.push(""))), { kind: "ghost", icon: "plus", small: true }),
        h("span.spacer", { style: { flex: 1 } })),
      h("div.hint-line", {}, "Paste cells from a spreadsheet into any cell."),
      ui.toggle({ value: header, label: "Header row", onChange: (value) => editBlock(at, (b) => setOption(b, "header", value ? null : false)) }),
      size()];
  }

  function imageForm(block, at) {
    const preview = h("img.preview-pic", { src: block.image ? studio.raw(block.image) : "", alt: "", hidden: !block.image });
    return [preview,
      fileRow(block.image, ["image"], (path) => { editBlock(at, (b) => { b.image = path; }, {}); preview.src = studio.raw(path); preview.hidden = false; }, "picture.png"),
      h("div.hint-line", {}, "SVG pictures stay as vectors: editable shapes and text in PowerPoint."),
      widthField(block, at)];
  }

  // A figure's or picture's width: as its place sets it, or as its corners were dragged to.
  function widthField(block, at) {
    return ui.field("Width", h("div.row", {},
      ui.number({ value: block.width, placeholder: "Auto", min: 10, step: 10, key: "block.width", onChange: (value) => editBlock(at, (b) => setOption(b, "width", value)) }),
      block.width != null ? ui.button("Reset Size", () => { editBlock(at, (b) => setOption(b, "width", null)); renderInspector(); }, { small: true, kind: "ghost" }) : null),
    { hint: "In points, or drag a corner on the slide" });
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
      ui.button("", () => { items.splice(i, 1); write(); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, title: "Delete" })));
    return [h("div.list-rows", {}, rows),
      h("div", {}, ui.button("Add Picture…", async () => {
        const path = await chooseFile({ title: "Add Picture", types: ["image"] });
        if (path) { items.push({ picture: path, caption: "" }); write(); renderInspector(); }
      }, { kind: "ghost", icon: "plus", small: true })),
      h("div.grid2", {},
        ui.field("Columns", ui.number({ value: block.columns, placeholder: "Auto", min: 1, step: 1, key: "gallery.columns", onChange: (value) => editBlock(at, (b) => setOption(b, "columns", value)) })),
        ui.field("Height", ui.number({ value: block.height, placeholder: "Auto", min: 10, step: 5, key: "gallery.height", onChange: (value) => editBlock(at, (b) => setOption(b, "height", value)) }), { hint: "In points" })),
      ui.field("Crop", ui.segmented({ value: block.crop || "", options: [{ value: "", label: "None" }, { value: "circle", label: "Circle" }, { value: "square", label: "Square" }],
        onChange: (value) => { editBlock(at, (b) => setOption(b, "crop", value)); renderInspector(); } })),
      size()];
  }

  function figureForm(block, at, edit) {
    const value = block.figure;
    const mode = typeof value === "string" ? (value.includes(".py:") ? "python" : "file") : "inline";
    const turn = ui.toggle({ value: block.turn !== false, label: "Allow rotated layout to fit", onChange: (on) => editBlock(at, (b) => setOption(b, "turn", on ? null : false)) });
    const parts = [ui.field("Source", ui.segmented({ value: mode, options: [
      { value: "inline", label: "In Deck" }, { value: "file", label: "File" }, { value: "python", label: "Python" }],
    onChange: async (next) => {
      if (next === mode) return;
      // A figure file's figure comes into the deck as it is; else a new one starts here.
      if (next === "inline" && mode === "file") {
        try {
          const result = await studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "inline", at: { slide: state.slide, region: at.region, index: at.index } } });
          studio.change(() => result.document);
          toast(`${value} copied into the deck. The file is unchanged.`, { icon: "check", seconds: 5 });
        } catch (error) { toast(error.message, { kind: "error", icon: "error" }); }
      } else if (next === "inline") editBlock(at, (b) => { b.figure = NEW_BLOCKS.figure().figure; });
      else if (next === "file") {
        const path = await chooseFile({ title: "Choose a Figure File", types: ["figure"], create: "figure" });
        if (path) editBlock(at, (b) => { b.figure = path; });
      } else {
        const target = await chooseFunction("Choose a Figure Function");
        if (target) editBlock(at, (b) => { b.figure = target; });
      }
      renderInspector();
    } }))];
    // A figure is made and changed on its slide; to use it elsewhere, it is exported.
    const exports = ui.field("Export", h("div.row", {}, FIGURE_EXPORTS.map(({ label, formats, hint }) =>
      ui.button(label, () => exportFigure(at, formats), { small: true, icon: "export", title: hint }))));
    if (mode === "inline") {
      parts.push(h("div.figure-card", {},
        h("div", {}, h("b", {}, `${count((value?.nodes || []).length, "shape")}, ${count((value?.edges || []).length, "line")}`), h("div.hint-line", {}, "Stored in the deck, using the deck's theme"))));
      const area = ui.textarea({ value: JSON.stringify(value, null, 2), rows: 8, mono: true, key: "figure.json", onInput: (text) => {
        try { const parsed = JSON.parse(text); area.style.borderColor = ""; edit((b) => { b.figure = parsed; }, "figure"); }
        catch { area.style.borderColor = "var(--error)"; }
      } });
      area.classList.remove("grow"); area.style.maxHeight = "300px"; area.style.overflow = "auto";
      parts.push(h("details.more", {}, h("summary", {}, icon("chevron"), "JSON"), h("div.inner", {}, area)));
      // Written in the deck, it is edited where it is drawn: where it is kept is put by.
      return [exports, widthField(block, at), turn, h("details.more", {}, h("summary", {}, icon("chevron"), "Source"), h("div.inner", {}, parts))];
    } else if (mode === "file") {
      parts.push(fileRow(value, ["figure"], (path) => { editBlock(at, (b) => { b.figure = path; }); }, "figure.yaml"),
        h("div.hint-line", {}, "Edit the figure on the slide. Your changes are saved to the file, and changes made to the file appear here."));
    } else {
      parts.push(functionInput(value, (text) => edit((b) => { b.figure = text; }, "figure")),
        h("div.hint-line", {}, "A function that returns a ", h("code", {}, "flexo.Figure"), ". It runs again when its file changes."));
    }
    parts.push(widthField(block, at), turn);
    return [exports, ...parts];
  }

  // The figure on the slide written out by itself, in the deck's look, laid out as written.
  function exportFigure(at, formats) {
    return studio.exportFiles(formats, { slide: state.slide, region: at.region, index: at.index });
  }

  // -- files --
  function fileRow(value, types, onChoose, placeholder) {
    const input = ui.input({ value: value || "", placeholder, mono: true, onChange: (text) => text && onChoose(text) });
    return h("div.list-row", {}, input,
      ui.button("", async () => { const path = await chooseFile({ title: "Choose a File", types }); if (path) { input.value = path; onChoose(path); } }, { icon: "folder", small: true, title: "Choose…" }));
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
      const upload = h("input", { type: "file", accept: types.includes("image") ? "image/*,.svg,.pdf,.ai" : types.includes("structure") ? ".pdb,.cif,.mmcif,.ent" : ".yaml,.yml,.json", hidden: true,
        onchange: async () => { const file = upload.files[0]; if (file) finish(await studio.upload(file)); } });
      const actions = [];
      if (types.some((type) => ["image", "figure", "structure"].includes(type))) actions.push({ label: "Upload…", run: () => { upload.click(); return false; } });
      if (types.includes("structure")) actions.push({ label: "PDB ID…", run: () => {
        ask("Enter a PDB ID", "1UBQ").then((id) => { if (id) finish(id.toUpperCase()); });
        return false;
      } });
      if (create === "figure") actions.push({ label: "New Figure File…", run: () => {
        ask("New Figure File", "figures/figure.yaml").then(async (name) => {
          if (!name) return;
          try { finish(await createFile(name, "figure")); }
          catch (error) { toast(error.message, { kind: "error", icon: "error" }); }
        });
        return false;
      } });
      actions.push({ label: "Cancel", run: () => finish(null) });
      const box = dialog({ title, body: [list, upload], actions, onClose: () => finish(null) });
      studio.files(types).then((files) => {
        const shown = files.filter((file) => file !== studio.file.split("/").pop());
        clear(list, shown.length ? shown.map((file) => h("button.menu-item", { type: "button", onclick: () => finish(file) },
          types.includes("image") ? h("img.pic", { src: studio.raw(file), alt: "" }) : icon(types.includes("python") ? "code" : types.includes("structure") ? "structure" : "figure"),
          h("span.menu-text", {}, h("span", {}, file.split("/").pop()), h("span.menu-hint", {}, file))))
          : h("div.empty", {}, types.includes("structure") ? "No structure files in the deck's folder. Upload a PDB or mmCIF file, or enter a PDB ID." : "No matching files in the deck's folder"));
      });
    });
  }

  function chooseFunction(title = "Choose a Python Function") {
    return new Promise((resolve) => {
      let value = "";
      const input = functionInput("", (text) => { value = text; });
      dialog({ title, body: [ui.field("file.py:function", input), h("div.hint-line", {}, "The file must be in the deck's folder. The function runs each time the slide is drawn.")],
        actions: [{ label: "Cancel", run: () => resolve(null) }, { label: "Choose", kind: "primary", run: () => {
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
    lookArt(item.name), h("span.name", {}, lookName(item)), h("span.note", {}, item.note))));
    const themeIsFile = typeof deck.theme === "string" && /\.(ya?ml|json)$/i.test(deck.theme);
    const current = Array.isArray(deck.palette) ? "" : deck.palette || "default";
    const accents = () => Object.entries(studio.info?.palette || {}).filter(([k]) => k.startsWith("accent")).slice(0, 5).map(([, c]) => h("span", { style: { background: c } }));
    // The palette as a pop-up button, like the theme above it: every palette is in its menu,
    // not in a box scrolling inside the inspector.
    const strip = (colours) => h("span.palette-strip", {}, colours ? colours.map((c) => h("span", { style: { background: c } })) : accents());
    const choosePalette = (name) => { closeMenu(); editDeck((d) => { if (name === "default") delete d.palette; else d.palette = name; }); renderInspector(); };
    const paletteList = h("button.palette-pick", { type: "button", title: "Choose the deck's palette", onclick: (event) => popover(event.currentTarget,
      h("div.palette-choices", {}, [["default", null], ...Object.entries(catalog.palettes)].map(([name, colours]) => h(`button.palette-choice${current === name ? ".on" : ""}`,
        { type: "button", onclick: () => choosePalette(name) }, strip(colours), h("span", {}, name === "default" ? "Default" : name)))), { className: "palette-menu" }) },
    strip(catalog.palettes[current]), h("span", {}, current === "default" ? "Default" : current || "Custom"), icon("chevron"));
    const fonts = (name, label, note) => ui.field(label, ui.combo({ value: deck[name] || "", options: catalog.fonts, placeholder: note, key: `deck.${name}`, onChange: setDeck(name) }));
    const lookStyle = catalog.looks.find((item) => item.name === look)?.style || {};
    const changes = deck.style || {};
    const styleRows = catalog.style.map((field) => {
      const fallback = lookStyle[field.name] ?? field.default;
      const setStyle = (value) => editDeck((d) => { d.style ||= {}; setOption(d.style, field.name, value, undefined); if (!Object.keys(d.style).length) delete d.style; }, { quiet: true, merge: `style-${field.name}` });
      const choiceLabel = (choice) => choiceName(field.name, choice);
      let control;
      if (field.kind === "bool") control = ui.select({ value: changes[field.name] === undefined ? "" : String(changes[field.name]), options: [{ value: "", label: `Default (${fallback ? "On" : "Off"})` }, { value: "true", label: "On" }, { value: "false", label: "Off" }], onChange: (v) => setStyle(v === "" ? null : v === "true") });
      else if (field.kind === "choice") control = ui.select({ value: changes[field.name] ?? "", options: [{ value: "", label: `Default (${choiceLabel(fallback)})` }, ...field.choices.map((choice) => ({ value: choice, label: choiceLabel(choice) }))], onChange: (v) => setStyle(v || null) });
      else control = ui.number({ value: changes[field.name], placeholder: String(fallback ?? "Auto"), step: "any", key: `style.${field.name}`, onChange: setStyle });
      const set = changes[field.name] !== undefined;
      return h("div.style-row", {}, h("span.name", {}, h(`span${set ? ".changed" : ""}`, {}, styleName(field.name)), h("span.note", {}, field.note)), control,
        ui.button("", () => { setStyle(null); renderInspector(); }, { kind: "ghost", icon: "undo", small: true, title: "Reset", disabled: !set }));
    });
    const changed = Object.keys(changes).length;
    return [
      h("div.section", {}, h("div.section-title", {}, "Theme"),
        themeField(studio, { value: deck.theme, fallback: "paper",
          onPick: (value) => { editDeck((d) => setOption(d, "theme", value, "paper")); renderInspector(); },
          onCustomise: () => themeIsFile ? studio.workspace.open(studio.folder() + deck.theme) : customiseTheme(deck) }),
        h("div.row", {},
          themeIsFile ? ui.button("Edit Theme", () => studio.workspace.open(studio.folder() + deck.theme), { small: true, icon: "external" })
            : ui.button("Customise…", () => customiseTheme(deck), { small: true, icon: "pencil", title: "Create a theme file based on this theme to edit its colours, fonts and lines" })),
        ui.field("Palette", paletteList)),
      h("div.section", {}, h("div.section-title", {}, "Look"), looks),
      h("div.section", {}, h("div.section-title", {}, "Fonts"),
        fonts("font", "Body", "Default"), fonts("title_font", "Titles", "Same as body"), fonts("figure_font", "Figures", "Same as body")),
      h("div.section", {}, h("div.section-title", {}, "Deck"),
        ui.field("Footer", ui.markup({ value: deck.footer || "", placeholder: "Group meeting · 2026", colours: false, key: "deck.footer", onInput: setDeck("footer") })),
        ui.field("Export File Name", ui.input({ value: deck.id || "", placeholder: "talk", mono: true, key: "deck.id", onInput: setDeck("id") }), { hint: "name.pptx, name.pdf" })),
      h("div.section", {}, h("details.more", { open: changed > 0 }, h("summary", {}, icon("chevron"), `Proportions${changed ? ` (${changed} changed)` : ""}`),
        h("div.inner", {}, styleRows))),
    ];
  }

  async function customiseTheme(deck) {
    const base = deck.theme && !/\.(ya?ml|json)$/i.test(deck.theme) ? deck.theme : "paper";
    const name = await ask("Save Theme As", `${deck.id || "talk"}.theme.yaml`);
    if (!name) return;
    const stem = name.split("/").pop().replace(/\.(ya?ml|json)$/i, "").replace(/\.theme$/i, "");
    try {
      const made = await createFile(name, "theme", { theme: { name: stem, base, description: `The look of ${deck.id || "this deck"}.` } });
      studio.change((d) => { d.deck ||= {}; d.deck.theme = made; });
      renderInspector();
      studio.workspace.open(studio.folder() + made);
      toast("Edit the theme here. The deck updates as you make changes.", { icon: "theme", seconds: 4 });
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
    const hint = h("div.present-hint", {}, "→ next · ← previous · N notes · Esc to exit");
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
      noteNode.textContent = slides()[index]?.notes || "No speaker notes";
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
    const typing = typingNow() || document.querySelector(".scrim, .present, .menu");
    const mod = event.metaKey || event.ctrlKey;
    if (mod && event.key === "Enter") { event.preventDefault(); present(); return; }
    if (typing) return;
    if (figure && figureBlock() && figure.parts.key(event)) return;
    const key = event.key;
    if (mod && event.shiftKey && key.toLowerCase() === "n") { event.preventDefault(); newSlideLike(state.slide); }
    else if (mod && key.toLowerCase() === "d") {
      event.preventDefault();
      // ⌘D duplicates what is chosen: the object on the slide, else the slide.
      const block = state.focus && blocksAt(slideAt(), state.focus.region)[state.focus.index];
      if (block) insertBlock(kindOf(block), structuredClone(block), { ...state.focus });
      else if (chosenSlides().length > 1) duplicateSlides(chosenSlides());
      else if (slides().length) duplicateSlide(state.slide);
    }
    // ⌘A outside a text field selects nothing on the page's own words.
    else if (mod && key.toLowerCase() === "a") event.preventDefault();
    else if (mod) return;
    // With a part of the slide chosen, arrows move it: up and down its column, across to
    // the next; a figure's part chosen, they leave the slide alone. Else they turn slides.
    else if (key.startsWith("Arrow") && state.focus) {
      event.preventDefault();
      if (figure && figureBlock() && figure.parts.selected.length) return;
      const at = state.focus, regions = regionsOf(slideAt()), count = blocksAt(slideAt(), at.region).length;
      const side = regions.findIndex((region) => region.key === at.region) + (key === "ArrowRight" ? 1 : key === "ArrowLeft" ? -1 : 0);
      if (key === "ArrowUp" && at.index > 0) moveBlock(at, { region: at.region, index: at.index - 1 });
      else if (key === "ArrowDown" && at.index < count - 1) moveBlock(at, { region: at.region, index: at.index + 2 });
      else if ((key === "ArrowLeft" || key === "ArrowRight") && regions[side] && side !== regions.findIndex((region) => region.key === at.region)) {
        moveBlock(at, { region: regions[side].key, index: blocksAt(slideAt(), regions[side].key).length });
      }
    }
    // Tab goes from one thing on the slide to the next (its title, then its objects), as in
    // Keynote; only when the keys are the slide's, not a panel's.
    else if (key === "Tab" && !event.altKey && (document.activeElement === document.body || stage.contains(document.activeElement)) && slideAt()) {
      event.preventDefault();
      const slide = slideAt();
      const stops = [
        ...["title", "words", "subtitle", "author"].filter((name) => slide[name] && catalog.slide_keys[layoutOf(slide)].includes(name)).map((name) => ({ field: name })),
        ...regionsOf(slide).flatMap((region) => blocksAt(slide, region.key).map((_, index) => ({ region: region.key, index }))),
      ];
      if (!stops.length) return;
      const now = stops.findIndex((stop) => (stop.field ? state.field?.field === stop.field : state.focus?.region === stop.region && state.focus?.index === stop.index));
      const next = stops[(now + (event.shiftKey ? -1 : 1) + stops.length + (now < 0 && event.shiftKey ? 1 : 0)) % stops.length];
      if (next.field) {
        leaveFigure(false);
        state.focus = null; state.field = { field: next.field, id: fieldId(next.field) };
        placeChosen(); renderInspector(); reportFocus();
      } else focusBlock(next.region, next.index);
    }
    else if (key === "Home" && slides().length) { event.preventDefault(); select(0); }
    else if (key === "End" && slides().length) { event.preventDefault(); select(slides().length - 1); }
    else if (["ArrowDown", "ArrowRight", "PageDown"].includes(key) && state.slide < slides().length - 1) { event.preventDefault(); select(state.slide + 1); }
    else if (["ArrowUp", "ArrowLeft", "PageUp"].includes(key) && state.slide > 0) { event.preventDefault(); select(state.slide - 1); }
    else if (state.field && key === "Escape") { state.field = null; placeChosen(); }
    else if (state.field && key === "Enter") { event.preventDefault(); openInline({ kind: "field", field: state.field.field }); }
    else if (state.field && (key === "Delete" || key === "Backspace")) { event.preventDefault(); openInline({ kind: "field", field: state.field.field }, { replaceWith: "" }); }
    else if (state.field && key.length === 1 && !event.altKey) {
      // Typing over a selected title replaces it, as in Keynote.
      event.preventDefault();
      openInline({ kind: "field", field: state.field.field }, { replaceWith: key });
    }
    else if (state.focus && key.length === 1 && key !== " " && !event.altKey && WORDY.has(kindOf(blocksAt(slideAt(), state.focus.region)[state.focus.index]))) {
      // And over a selected text or list: its words start again from the key.
      event.preventDefault();
      openInline({ kind: "block", ...state.focus }, { replaceWith: key });
    }
    else if (key === "Escape" && state.focus) { state.focus = null; leaveFigure(false); renderInspector(); placeChosen(); reportFocus(); }
    else if (key === "Enter" && state.focus) {
      event.preventDefault();
      const block = blocksAt(slideAt(), state.focus.region)[state.focus.index];
      // Return goes into what is chosen: its words, a table's first cell, a figure's first shape.
      if (block && INLINE.has(kindOf(block))) openInline({ kind: "block", ...state.focus });
      else if (block && kindOf(block) === "table") openInline({ kind: "cell", ...state.focus, row: 0, col: 0 }, { selectAll: true });
      else if (block && kindOf(block) === "figure" && figure && figureBlock() === block) {
        const first = figure.parts.model?.nodes?.[0]?.id;
        if (first) figure.parts.select([first]);
      }
    } else if ((key === "Delete" || key === "Backspace") && state.focus) { event.preventDefault(); deleteBlock(state.focus); }
  });

  // -- the palette's commands, and following --
  studio.exports = [
    { format: "pdf", label: "PDF…", hint: "One page per slide, with embedded fonts", options: [{ name: "steps", label: "Include each stage of builds", value: false }] },
    { format: "pptx", label: "PowerPoint…", hint: "Editable shapes and text" },
    { format: "png", label: "Images…", icon: "image", hint: "A PNG or SVG image of each slide", choose: [{ format: "png", label: "PNG" }, { format: "svg", label: "SVG" }] },
  ];
  studio.present = () => present();
  studio.commands = () => [
    ...slides().map((slide, index) => ({ icon: "slide", label: `Slide ${index + 1}: ${slideTitle(slide)}`, run: () => select(index) })),
    ...layouts.map((layout) => ({ icon: "plus", label: `New ${LAYOUT_NAMES[layout.name]} Slide`, hint: layout.note, run: () => addSlide(layout.name, state.slide + 1) })),
    ...(slides().length ? layouts.map((layout) => ({ icon: "layout", label: `Layout: ${LAYOUT_NAMES[layout.name]}`, run: () => changeLayout(layout.name) })) : []),
    ...Object.entries(BLOCKS).map(([kind, info]) => ({ icon: info.icon, label: `Add ${info.label}`, hint: info.hint, run: () => insertBlock(kind) })),
    ...catalog.looks.map((look) => ({ icon: "palette", label: `Look: ${lookName(look)}`, hint: look.note, run: () => { studio.change((d) => { d.deck ||= {}; setOption(d.deck, "look", look.name, "classic"); }); renderInspector(); } })),
    { icon: "theme", label: "Customise Theme…", run: () => customiseTheme(doc().deck || {}) },
    ...(figureBlock() ? FIGURE_EXPORTS.map(({ label, formats, hint }) => ({ icon: "export", label: `Export Figure as ${label}`, hint, run: () => exportFigure(figure, formats) })) : []),
    { icon: "play", label: "Present", keys: "⌘↩", run: () => present() },
    { icon: "export", label: "Export as PowerPoint", run: () => studio.exportFiles(["pptx"]) },
    { icon: "export", label: "Export as PDF", run: () => studio.exportFiles(["pdf"]) },
  ];
  studio.reveal = (where) => {
    if (where?.label === "Design") { state.tab = "design"; renderInspector(); return; }
    if (where?.page && where.page - 1 !== state.slide) select(where.page - 1);
  };

  // -- what happens --
  let lastKey = "";
  // -- the history, in words --
  // What a change did to the deck, for its history and its undo button: what it did,
  // on which slide -- where the deck goes when it is undone or redone.
  studio.describe = (before, after) => {
    const was = before?.slides || [], now = after?.slides || [];
    let first = 0;
    while (first < Math.min(was.length, now.length) && same(was[first], now[first])) first += 1;
    const on = (index, text) => ({ text, place: `Slide ${index + 1}`, where: index });
    if (now.length > was.length) {
      if (now.length - was.length > 1) return on(first, `Add ${now.length - was.length} Slides`);
      return on(first, first > 0 && same(now[first], now[first - 1]) ? "Duplicate Slide" : "Add Slide");
    }
    if (now.length < was.length) {
      const gone = was.length - now.length;
      // Where the slide was: undone, the slide comes back and is shown there.
      return { ...on(first, gone > 1 ? `Delete ${gone} Slides` : "Delete Slide"), place: `Slide ${first + 1}` };
    }
    const changed = now.map((_, index) => index).filter((index) => !same(was[index], now[index]));
    if (!changed.length) return deckChange(before?.deck || {}, after?.deck || {});
    if (changed.length > 1) {
      const a = changed[0], b = changed[changed.length - 1];
      if (same(was[a], now[b])) return on(b, "Move Slide");
      if (same(was[b], now[a])) return on(a, "Move Slide");
      return on(a, `Edit ${changed.length} Slides`);
    }
    return on(changed[0], slideChange(was[changed[0]], now[changed[0]]));
  };
  // History names are macOS undo names: title-style, present tense ("Move List",
  // "Rename “Model” to “Encoder”"); a shape is named in quotes where it helps.
  const quoted = (text, most = 28) => {
    const words = plain(text).trim();
    return words ? `“${words.length > most ? `${words.slice(0, most - 1)}…` : words}”` : "";
  };
  const differing = (a = {}, b = {}) => [...new Set([...Object.keys(a || {}), ...Object.keys(b || {})])].filter((key) => !same(a?.[key], b?.[key]));
  const blockLabel = (block) => BLOCKS[kindOf(block)]?.label || "Object";
  // Every part of a slide in order, read without touching it (blocksAt makes columns).
  const partsOf = (slide) => regionsOf(slide).flatMap((region) => {
    const list = region.key.startsWith("columns.") ? slide.columns?.[Number(region.key.split(".")[1])] : slide[region.key];
    return (Array.isArray(list) ? list : []).map((block, index) => ({ region: region.key, index, block }));
  });
  const DECK_NAMES = { id: "Export File Name", font: "Font", title_font: "Title Font", figure_font: "Figure Font", style: "Proportions" };
  function deckChange(a, b) {
    const keys = differing(a, b);
    if (keys.length === 1 && keys[0] === "style") {
      const fields = differing(a.style, b.style);
      if (fields.length === 1) return `Change ${styleName(fields[0])}`;
    }
    return keys.length === 1 ? `Change ${DECK_NAMES[keys[0]] || keyTitle(keys[0])}` : "Change Design";
  }
  const SLIDE_WORDS = [["title", "Title"], ["subtitle", "Subtitle"], ["words", "Text"], ["author", "Author"], ["date", "Date"]];
  const SLIDE_NAMES = { widths: "Column Widths", split: "Column Widths", align: styleName("align"), dark: "Text Colour", shade: "Background", background: "Background", by: "Attribution" };
  function slideChange(a, b) {
    if (layoutOf(a) !== layoutOf(b)) return "Change Layout";
    for (const [key, name] of SLIDE_WORDS) if (!same(a[key], b[key])) return `Edit ${name}`;
    if (!same(a.notes, b.notes)) return "Edit Notes";
    if (!same(a.footnotes, b.footnotes)) return "Edit Footnotes";
    const old = partsOf(a), next = partsOf(b);
    const found = (list, item) => list.some((other) => same(other.block, item.block));
    if (next.length > old.length) { const added = next.find((item) => !found(old, item)) || next[next.length - 1]; return `Add ${blockLabel(added.block)}`; }
    if (next.length < old.length) { const gone = old.find((item) => !found(next, item)) || old[old.length - 1]; return `Delete ${blockLabel(gone.block)}`; }
    const pairs = next.map((item, k) => [old[k], item]).filter(([was, now]) => !same(was.block, now.block) || was.region !== now.region);
    if (pairs.length && pairs.every(([, now]) => found(old, now))) return `Move ${blockLabel(pairs[0][1].block)}`;
    if (pairs.length === 1) return blockChange(pairs[0][0].block, pairs[0][1].block);
    if (pairs.length > 1) return `Edit ${pairs.length} Objects`;
    const keys = differing(a, b).filter((key) => key !== "body" && key !== "left" && key !== "right" && key !== "columns");
    if (keys.length && keys.every((key) => ["background", "shade", "dark"].includes(key)) && keys.some((key) => key !== "dark")) return "Change Background";
    return keys.length === 1 ? `Change ${SLIDE_NAMES[keys[0]] || keyTitle(keys[0])}` : "Edit Slide";
  }
  const BLOCK_NAMES = { align: "Alignment", size: "Font Size", turn: "Rotation", colour: "Colour", muted: "Colour", numbered: "Numbering",
    reveal: "Build", header: "Header Row", by: "Attribution", title: "Heading", aspect: "Aspect Ratio", arrow_colour: "Arrow Colour" };
  function blockChange(a, b) {
    const kind = kindOf(b), name = blockLabel(b), keys = differing(a, b);
    if (keys.length === 1 && keys[0] === "width") return b.width == null ? `Reset ${name} Size` : `Resize ${name}`;
    if (keys.includes(kind)) {
      if (kind === "figure" && typeof a.figure === "object" && typeof b.figure === "object") return figureChange(a.figure, b.figure);
      if (kind === "image") return "Change Picture";
      if (kind === "figure" && typeof b.figure === "string") return "Change Figure Source";
      return `Edit ${name}`;
    }
    return `Change ${BLOCK_NAMES[keys[0]] || keyTitle(keys[0])}`;
  }
  // A field's label in the figure editor's catalogue (a mol-sketch setting's among a
  // structure's), title-style: "properties.colors" -> "Colours", "fill" -> "Fill".
  function fieldLabel(kind, key, style = false) {
    const fields = catalog.figure_editor?.parts?.[kind || "block"]?.fields || [];
    const found = style
      ? fields.find((field) => field.key === "properties.style")?.sections?.flatMap((section) => section.fields || []).find((field) => field.key === key)
      : fields.find((field) => field.key === `properties.${key}`);
    return found?.label ? titled(found.label) : keyTitle(key);
  }
  // A change to a figure written in the deck: the shape it was made to, by name.
  function figureChange(a, b) {
    const byId = (list) => new Map((list || []).map((item) => [item.id, item]));
    const nodesA = byId(a.nodes), nodesB = byId(b.nodes), groupsA = byId(a.groups), groupsB = byId(b.groups);
    const named = (item, id) => quoted(item?.label || id || "", 24) || "Shape";
    const call = (id) => named(nodesB.get(id) || nodesA.get(id) || groupsB.get(id) || groupsA.get(id), id);
    const ref = (end) => (nodesB.has(end) || nodesA.has(end) ? end : String(end).slice(0, String(end).lastIndexOf(".")) || end);
    const added = [...nodesB.keys()].filter((id) => !nodesA.has(id)), removed = [...nodesA.keys()].filter((id) => !nodesB.has(id));
    if (added.length === 1 && !removed.length) return "Add Shape";
    if (removed.length === 1 && !added.length) return `Delete ${call(removed[0])}`;
    if (added.length > 1 && !removed.length) return `Add ${added.length} Shapes`;
    if (removed.length > 1 && !added.length) return `Delete ${removed.length} Shapes`;
    if (added.length || removed.length) return "Edit Shapes";
    const changed = [...nodesB.keys()].filter((id) => !same(nodesA.get(id), nodesB.get(id)));
    if (changed.length === 1) {
      const id = changed[0], was = nodesA.get(id), now = nodesB.get(id);
      if (!same(was.label, now.label)) return was.label && now.label ? `Rename ${named(was, id)} to ${named(now, id)}` : `Edit ${named(now, id)}`;
      if (!same(was.kind, now.kind)) return "Change Shape Type";
      const keys = differing(was.properties, now.properties);
      if (keys.length && keys.every((key) => ["yaw", "pitch", "roll"].includes(key))) return `Rotate ${call(id)}`;
      if (keys.length && keys.every((key) => key === "zoom")) return `Zoom ${call(id)}`;
      if (keys.length && keys.every((key) => key === "width" || key === "height")) return `Resize ${call(id)}`;
      // mol-sketch's settings, by name: "Change Line Width".
      if (keys.length === 1 && keys[0] === "style") {
        const flat = (value, prefix = "") => Object.entries(value || {}).flatMap(([key, part]) =>
          (part && typeof part === "object" && !Array.isArray(part) ? flat(part, `${prefix}${key}.`) : [[`${prefix}${key}`, part]]));
        const before = new Map(flat(was.properties?.style)), after = new Map(flat(now.properties?.style));
        const changed = [...new Set([...before.keys(), ...after.keys()])].filter((key) => !same(before.get(key), after.get(key)));
        if (!after.size) return "Reset Rendering";
        if (changed.length === 1) return `Change ${fieldLabel(now.kind, changed[0], true)}`;
        if (changed.length) return "Change Rendering";
      }
      if (keys.length === 1 && keys[0] === "palette") return now.properties?.palette ? "Change Palette" : "Reset Palette";
      if (keys.length === 1 && keys[0] === "density") return now.properties?.density ? "Add Density Map" : "Remove Density Map";
      if (keys.length === 1) return `Change ${fieldLabel(now.kind, keys[0])}`;
      return `Edit ${call(id)}`;
    }
    if (changed.length > 1) return `Edit ${changed.length} Shapes`;
    const edgeKey = (edge) => JSON.stringify(edge);
    const edgesA = (a.edges || []).map(edgeKey), edgesB = (b.edges || []).map(edgeKey);
    const newEdges = (b.edges || []).filter((edge) => !edgesA.includes(edgeKey(edge)));
    const oldEdges = (a.edges || []).filter((edge) => !edgesB.includes(edgeKey(edge)));
    if (newEdges.length === 1 && !oldEdges.length) return `Connect ${call(ref(newEdges[0].from))} to ${call(ref(newEdges[0].to))}`;
    if (oldEdges.length === 1 && !newEdges.length) return "Delete Line";
    if (newEdges.length || oldEdges.length) return newEdges.length === oldEdges.length && newEdges.length === 1 ? "Edit Line" : "Edit Lines";
    // Its shapes arranged: grouped, ungrouped, or one moved in its row or to another.
    const newGroups = [...groupsB.keys()].filter((id) => !groupsA.has(id)), oldGroups = [...groupsA.keys()].filter((id) => !groupsB.has(id));
    if (newGroups.length === 1 && !oldGroups.length) return `Group ${count((groupsB.get(newGroups[0]).children || []).length, "Shape")}`;
    if (oldGroups.length === 1 && !newGroups.length) return `Ungroup ${call(oldGroups[0])}`;
    const parentOf = (groups) => { const map = new Map(); for (const group of groups.values()) (group.children || []).forEach((child, index) => map.set(child, [group.id, index])); return map; };
    const homeA = parentOf(groupsA), homeB = parentOf(groupsB);
    const moved = [...homeB.keys()].filter((id) => homeA.get(id)?.[0] !== homeB.get(id)[0]);
    if (moved.length === 1) return `Move ${call(moved[0])}`;
    for (const [id, group] of groupsB) {
      const was = groupsA.get(id);
      if (!was || same(was, group)) continue;
      if (!same(was.children, group.children)) {
        const before = was.children || [], after = group.children || [];
        const k = after.findIndex((child, index) => child !== before[index]);
        const without = (list, child) => list.filter((item) => item !== child);
        const one = [after[k], before[k]].find((child) => same(without(before, child), without(after, child)));
        return one ? `Move ${call(one)}` : `Rearrange ${call(id)}`;
      }
      return id === b.groups?.[0]?.id ? "Change Figure Layout" : `Change Layout of ${call(id)}`;
    }
    return "Edit Figure";
  }

  let lastDoc = doc();
  // A deck just made opens ready to type its title over: no key typed into it is taken
  // for a command.
  if (studio.workspace?.justMade === studio.file) {
    studio.workspace.justMade = null;
    let started = false;
    studio.on("drawn", () => {
      if (started || !slides().length) return;
      started = true;
      setTimeout(() => openInline({ kind: "field", field: layoutOf(slides()[0]) === "statement" ? "words" : "title" }, { selectAll: true }), 60);
    });
  }
  // An undo waits for a figure's edits still on their way (shell.js).
  studio.settled = () => figure?.parts.idle?.() ?? Promise.resolve();
  studio.on("change", ({ quiet, source, who, before, entry }) => {
    clearTimeout(settleTimer);
    const was = lastDoc;
    lastDoc = doc();
    if (source === "history" || source === "remote") followChange(was, who);
    // Undone or redone, the deck goes to the slide the change was made on.
    if (source === "history" && Number.isInteger(entry?.where) && entry.where !== state.slide && entry.where < slides().length) {
      closeInline();
      leaveFigure(false);
      state.slide = entry.where;
      state.focus = null;
    }
    settling = false;
    if (state.slide >= slides().length) state.slide = Math.max(0, slides().length - 1);
    if (source === "history" && !inline) chooseChanged(was);
    pending = true;
    if (source === "remote" && before) flash(before, who);
    if (!quiet) { renderRail(); renderInspector(); renderStage(); renderBar(); }
    if (source === "history" || source === "remote") {
      refreshInline();
      if (document.activeElement === notesArea) notesArea.value = slideAt()?.notes || "";
      if (source === "history") figure?.parts.closeInline(false);
    }
    if (figure && source !== "edit") {
      if (figureBlock() && editable(figureBlock())) figure.parts.act({ do: "read" }, { select: false });
      else leaveFigure();
    }
    pageNode?.classList.add("pending");
  });
  studio.on("drawing", () => { pending = true; });
  studio.on("drawn", (result) => {
    pending = !result.latest || Boolean(result.unfinished);
    if (result.latest && !result.unfinished) {
      settling = false;
      clearTimeout(settleTimer);
      if (result.info?.unsettled) settleTimer = setTimeout(() => { settling = true; studio.requestDraw(0); }, 1200);
    }
    pages = result.pages;
    messages = result.messages || [];
    renderRail();
    renderStage();
    readSlideAhead();
    if (mathNotes && document.contains(inspectorBody.querySelector(".math-notes"))) mathNotes();
    if (figure && typeof figureBlock()?.figure === "string") figure.parts.act({ do: "read" }, { select: false });
    const key = JSON.stringify(studio.info?.palette || {});
    if (key !== lastKey) { lastKey = key; renderInspector(); } else markBlockErrors();
    const deckError = messages.find((m) => m.severity === "error" && !m.page && !placeOf(m.where));
    stage.querySelector(":scope > .deck-error")?.remove();
    if (deckError) stage.prepend(h("div.messages.deck-error", {}, messageView(deckError)));
  });
  studio.workspace.on("presence", () => { if (studio.active) { renderRail(); renderStage(); } });
  studio.on("activate", () => { renderRail(); renderStage(); reportFocus(); });

  // Someone typing flashes their slide once, not at every key: a slide flashed in the
  // last few seconds is left be.
  const flashed = new Map();
  function flash(before, who) {
    const old = before.slides || [];
    const now = Date.now();
    const changed = slides().map((slide, index) => (same(slide, old[index]) ? -1 : index))
      .filter((index) => index >= 0 && !(now - (flashed.get(`${who?.id}:${index}`) || 0) < 4000));
    for (const index of changed) flashed.set(`${who?.id}:${index}`, now);
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

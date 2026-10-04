// The deck editor. The slide is where you work: click a part to choose it,
// double-click words to edit them in place, add slides and parts from the bar
// above. The inspector on the right shows what is chosen -- a part, or the
// slide -- and the deck's design. Others' edits (people, agents) arrive live:
// the slides they touch flash in their colour.

import { h, clear, icon, ui, menu, popover, closeMenu, dialog, toast, keepFocus, avatar, colourOf, nameOf, picture, ownResources, same, themeField, readable, mathWords } from "/static/studio/studio.js";
import { figureParts, widenLines, fileLabel } from "/static/kinds/figure/parts.js";
import { blockDrop, blockPlan, rearrange, groupDrop, gather, gatherPlan } from "/static/kinds/deck/slidedrop.js";
import { present as presentSlides } from "/static/kinds/deck/present.js";
import { richText, markupOfWords, itemsOfHtml, cellsOf, linkOfWords, emphasised } from "/static/kinds/deck/richtext.js";
import { follows, merge3 } from "/static/studio/merge.js";

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
  // What the file holds but Flexo does not know: shown for what it is, never offered.
  unknown: { icon: "warning", label: "Object", hint: "Not a kind of object Flexo knows", hidden: true },
};
// Flow charts and structures are figures: they are offered by name, and made as figures.
const MAIN_BLOCKS = ["text", "bullets", "figure", "flow", "structure", "image", "table"];
// Those that ask for a file or function first.
const CHOOSE = new Set(["structure", "image", "gallery", "plot"]);
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
  { label: "Flexo Figure", formats: ["yaml"], hint: "A figure file of its own, in the deck's theme, to open in Flexo" },
];

const LAYOUT_NAMES = {
  content: "Content", "two-columns": "Two Columns", columns: "Columns", figure: "Figure", title: "Title",
  section: "Section", statement: "Statement", agenda: "Agenda", blank: "Blank",
};
const LAYOUT_ORDER = ["content", "two-columns", "columns", "figure", "title", "section", "statement", "agenda", "blank"];
const WORDLESS = new Set(["title", "section", "statement", "agenda"]);
// Objects that are words, which typing over (once chosen) replaces.
const WORDY = new Set(["text", "bullets", "quote", "callout"]);
// The lines of words an object has of its own besides its words, typed on the slide too, and
// what each shows while empty: a quote's attribution, a callout's heading.
const OWN_LINES = { quote: { by: "Who said it" }, callout: { title: "Heading" } };
const TONES = ["accent", "accent2", "accent3", "accent4", "accent5", "accent6"];
const ARROW_INK = "#d466d6";

const NEW_SLIDES = {
  // Empty words are placeholders, as Keynote's: each holds its place, shows faintly while
  // editing ("Title", "Text"), and is never presented or exported.
  content: () => ({ title: "", body: [{ bullets: [""] }] }),
  "two-columns": () => ({ layout: "two-columns", title: "", left: [{ bullets: [""] }], right: [{ bullets: [""] }] }),
  columns: () => ({ layout: "columns", title: "", columns: [[{ text: "" }], [{ text: "" }], [{ text: "" }]] }),
  figure: () => ({ layout: "figure", title: "", body: [NEW_BLOCKS.figure()] }),
  title: () => ({ layout: "title", title: "", subtitle: "" }),
  section: () => ({ layout: "section", title: "" }),
  statement: () => ({ layout: "statement", words: "" }),
  agenda: () => ({ layout: "agenda" }),
  blank: () => ({ layout: "blank", body: [] }),
};

// A new object starts empty, as Keynote's do: a placeholder, drawn faintly here with a word
// saying what goes there ("Column 1", "Start", an equation) and never presented or exported
// until something of its person's is in it -- no sample words that could reach an audience.
// A figure starts as one shape with no words (A adds more); a mechanism, which cannot start
// empty, as a sample marked `placeholder: true` until it is changed.
const NEW_BLOCKS = {
  bullets: () => ({ bullets: [""] }),
  text: () => ({ text: "" }),
  figure: () => ({ figure: { figure: { id: `figure-${Date.now().toString(36)}` }, nodes: [{ id: "shape", label: "" }] } }),
  flow: () => ({ figure: { figure: { id: `flow-${Date.now().toString(36)}` }, nodes: [{ id: "start", kind: "terminal", label: "" }] } }),
  image: () => ({ image: "" }),
  table: () => ({ table: [["", "", ""], ["", "", ""], ["", "", ""]] }),
  stats: () => ({ stats: [{ value: "", label: "" }, { value: "", label: "" }] }),
  quote: () => ({ quote: "" }),
  callout: () => ({ callout: "" }),
  code: () => ({ code: "" }),
  gallery: () => ({ gallery: [] }),
  plot: () => ({ plot: "" }),
  math: () => ({ math: "" }),
  mechanism: () => ({ placeholder: true, mechanism: [
    { smiles: "[OH-:5].[CH3:1][C:2](=[O:3])[Cl:4]", arrows: ["5 -> 2", "2=3 -> 3"], reagents: "NaOH" },
    { arrows: ["3 -> 2", "2-4 -> 4"], label: "tetrahedral intermediate" }] }),
};

// A structure file, as a figure's part: named for its file or PDB ID, its id made from that.
const STRUCTURE_FILE = /\.(pdb|cif|mmcif|ent)$/i;
function structureNode(source, taken = new Set(), name = null) {
  const stem = source.split("/").pop().replace(STRUCTURE_FILE, "");
  let slug = stem.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase().slice(0, 24) || "structure";
  if (!/^[a-z]/.test(slug)) slug = `pdb-${slug}`;
  let id = slug;
  for (let number = 2; taken.has(id); number += 1) id = `${slug}-${number}`;
  taken.add(id);
  return { id, kind: "structure", label: name || fileLabel(source), properties: { source } };
}
// Structures on a slide: one after another, an arrow from each to the next -- each named
// for what its file says it holds (`names`), where it says.
function structureFigure(sources, names = []) {
  const taken = new Set();
  const nodes = sources.map((source, index) => structureNode(source, taken, names[index]));
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

const kindOf = (block) => Object.keys(block || {}).find((key) => key in BLOCKS && !BLOCKS[key].hidden)
  || (block && typeof block === "object" ? "unknown" : "text");
// An object by the name of what it is to the person: a list with its marks taken away (None)
// reads as the text it now is.
const blockName = (block) => (kindOf(block) === "bullets" && block?.plain ? "Text" : BLOCKS[kindOf(block)]?.label || "Object");
const blockIcon = (block) => (kindOf(block) === "bullets" && block?.plain ? BLOCKS.text.icon : BLOCKS[kindOf(block)]?.icon || "text");

function setOption(target, key, value, fallback = undefined) {
  if (value === null || value === undefined || value === "" || value === fallback) delete target[key];
  else target[key] = value;
}

// Code as it is kept: no spaces at its lines' ends, which show nothing and would make the
// file write it as one escaped line rather than as it reads.
const codeOf = (text) => String(text ?? "").replace(/[ \t]+$/gm, "");

function plain(markup) {
  return readable(String(markup ?? "")).split("\n")[0];
}

function summary(block) {
  const kind = kindOf(block);
  const value = block[kind];
  switch (kind) {
    case "bullets": { const first = (Array.isArray(value) ? value : [value]).find((item) => !Array.isArray(item)); return plain(first) || "Empty list"; }
    case "table": return Array.isArray(value) ? `${count(value.length, "row")} × ${count(Math.max(0, ...value.map((row) => (Array.isArray(row) ? row.length : 1))), "column")}` : "";
    // Those given only: a new one's placeholders say nothing, as a new text's do.
    case "stats": return Array.isArray(value) ? value.map((item) => String(item?.value ?? item?.[0] ?? item ?? "").trim()).filter(Boolean).join("  ·  ") : "";
    case "gallery": { const n = Array.isArray(value) ? value.length : 0; return `${n} picture${n === 1 ? "" : "s"}`; }
    case "figure": return typeof value === "string" ? value : count((value?.nodes || []).length, "shape");
    case "image": return value || "No picture chosen";
    case "plot": return value || "No function chosen";
    case "callout": return plain(block.title) || plain(value);
    case "math": return mathWords(value) || "Empty equation";
    // Its steps, and what is written by them (a step's name, its reagents) -- never its SMILES.
    case "mechanism": {
      const steps = Array.isArray(value) ? value : [value];
      const said = steps.map((step) => (typeof step === "object" ? step?.label || step?.reagents : "")).find(Boolean);
      return `${count(steps.length, "step")}${said ? ` · ${said}` : ""}`;
    }
    case "unknown": return `Unknown: ${Object.keys(block).join(", ")}`;
    default: return plain(value);
  }
}

const count = (number, word) => `${number} ${word}${number === 1 ? "" : "s"}`;

// An object as a notice names it: by its first words, where it has words ("“Second
// paragraph…”"), as a figure's shape is by its label; else by its kind ("Picture").
function named(block, { the = false } = {}) {
  const kind = kindOf(block), label = BLOCKS[kind]?.label || "Object";
  const said = ["text", "bullets", "quote", "callout"].includes(kind) ? summary(block).trim() : "";
  const words = said && said !== "Empty list" ? said.split(/\s+/) : [];
  if (words.length) return `“${words.slice(0, 4).join(" ")}${words.length > 4 ? "…" : ""}”`;
  return the ? `the ${label.toLowerCase()}` : label;
}
// What someone deleted that is being edited here, as a notice says it.
const editedHere = (what) => (what.startsWith("“") ? `${what}, which you're editing` : `${what} you're editing`);

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

// `empty`: an item still empty is an item (a list being typed on the slide: its Return, its
// Tab, each a step in the history; closeInline leaves them out).
function bulletsFrom(text, empty = false) {
  const root = [];
  const stack = [root];
  for (const raw of text.split("\n")) {
    if (!raw.trim() && !empty) continue;
    const indent = raw.match(/^[ \t]*/)[0].replace(/\t/g, "  ").length;
    let level = Math.min(Math.floor(indent / 2), stack.length);
    if (level > 0 && !stack[level - 1].some((item) => !Array.isArray(item))) level = stack.length - 1;
    if (level === stack.length) { const nested = []; stack[level - 1].push(nested); stack.push(nested); }
    stack.length = level + 1;
    // (A space typed at an item's end stays while its words are typed: the next word goes
    // after it, wherever another's words come in. The editor leaves it off when it closes.)
    stack[level].push(raw.replace(/^\s+/, ""));
  }
  return root;
}

// An object's words a line each, as a paragraph and a list are made one of the other (each
// line an item, each item a line), if it is one of those.
// (A space at a line's end, typed and waiting for the next word, stays: as bulletsFrom.)
function linesOf(block) {
  const lines = (text) => text.split("\n").filter((line) => line.trim()).map((line) => line.replace(/^\s+/, ""));
  if (typeof block?.text === "string") return lines(block.text);
  if (!block || !("bullets" in block)) return null;
  return lines(bulletsText(block.bullets));
}
// How alike two objects' words are, from 0 to 1 (by the letters they share at their ends).
function alikeLines(first, second) {
  const a = first.join("\n"), b = second.join("\n");
  if (!a.length && !b.length) return 1;
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start += 1;
  let end = 0;
  while (end < a.length - start && end < b.length - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end += 1;
  return (2 * (start + end)) / (a.length + b.length);
}
// Two edits merged (session.js), as the deck's kind mends its own (flexo_talk.studio's
// _converted): an object kept for someone typing in it (a merge's `kept` note) while the
// other side made it another kind, beside it -- a paragraph a list -- made one, of the new
// kind, with both sides' words. Settled notes are taken out of `notes`.
function converted(document, notes, base) {
  if (!notes.some((note) => "kept" in note)) return document;
  const lists = (slide) => (slide && typeof slide === "object" ? [...["body", "left", "right"].map((key) => slide[key]), ...(slide.columns || [])].filter(Array.isArray) : []);
  const olds = (base?.slides || []).flatMap(lists).flat().filter((block) => block && typeof block === "object");
  for (const note of [...notes]) {
    const item = note.item;
    if (!("kept" in note) || !item || typeof item !== "object" || !linesOf(item)) continue;
    const kind = "text" in item ? "text" : "bullets";
    const blocks = (document.slides || []).flatMap(lists).find((list) => list.some((block) => same(block, item)));
    if (!blocks) continue;
    const index = blocks.findIndex((block) => same(block, item));
    for (const near of [index + 1, index - 1]) {
      const other = blocks[near];
      if (!other || typeof other !== "object" || !linesOf(other) || kind in other || alikeLines(linesOf(other), linesOf(item)) < 0.5) continue;
      // Both sides' words: from what it was, as the kind it became.
      const was = olds.find((old) => kind in old && alikeLines(linesOf(old), linesOf(item)) >= 0.5);
      const lines = merge3(was ? linesOf(was) : linesOf(other), linesOf(other), linesOf(item));
      blocks[near] = "bullets" in other ? { ...other, bullets: lines.length ? lines : [""] } : { ...other, text: lines.join("\n") };
      blocks.splice(index, 1);
      notes.splice(notes.indexOf(note), 1);
      break;
    }
  }
  return document;
}

function numeric(cell) {
  if (typeof cell === "number") return true;
  const text = String(cell).trim().replace(/\$/g, "").replace(/\*/g, "").replace(/,/g, "").replace(/\\pm/g, "±").replace(/%$/, "").trim();
  // As deck.py's _NUMBER: a number with a spread, a multiple or a unit (38 ms, 400 req/s).
  return /^[-+−]?([x×]\s?)?\d+(\.\d+)?(\s*±\s*\d+(\.\d+)?)?\s*([kKMGTBx×]|[A-Za-zµμ°Ω]{1,4}(\/[A-Za-zµμ]{1,3})?)?$/.test(text);
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

// A copy of a slide or object: its figures with ids of their own, so the copy is laid out
// and edited apart from what it was copied from.
function copyOf(value) {
  const copy = structuredClone(value);
  const renew = (item) => {
    if (Array.isArray(item)) { item.forEach(renew); return; }
    if (!item || typeof item !== "object") return;
    const inner = item.figure;
    if (inner && typeof inner === "object" && inner.figure && typeof inner.figure === "object" && inner.figure.id) {
      inner.figure.id = `${String(inner.figure.id).replace(/-copy(-\w+)?$/, "")}-copy-${Math.random().toString(36).slice(2, 6)}`;
    }
    Object.values(item).forEach(renew);
  };
  renew(copy);
  return copy;
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

// In the deck's own colours, when it is tinted (tinted below).
function lookArt(name) {
  const bar = (x, y, w, hgt, colour, opacity = 1) => h("i", { style: { left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${hgt}%`, background: colour, opacity } });
  const ink = "var(--deck-ink, #3b3834)", accent = "var(--deck-accent, #8f8a83)";
  const soft = "var(--deck-muted, #8f8a83)";
  const body = (x = 10, centred = false) => [0, 1, 2].map((i) => bar(centred ? 22 + i * 3 : x, 48 + i * 13, centred ? 56 - i * 6 : 64 - i * 10, 6, soft, 0.45));
  const art = {
    classic: [bar(10, 14, 48, 10, ink), bar(10, 30, 12, 3, accent), ...body()],
    band: [bar(0, 0, 100, 34, accent), bar(10, 12, 48, 10, "#fff"), ...body()],
    editorial: [bar(10, 14, 52, 10, ink), bar(10, 30, 80, 1.5, soft, 0.45), ...body()],
    keynote: [bar(26, 16, 48, 11, ink), ...body(0, true)],
    margin: [bar(0, 0, 3, 100, accent), bar(10, 14, 48, 10, accent), ...body()],
  }[name] || [];
  return h("div.look-art", {}, art);
}

// The deck's colours on the small pictures of its slides, so that a layout or look is
// seen as it will be.
function tinted(node, palette = {}) {
  for (const name of ["canvas", "ink", "muted", "accent"]) if (palette[name]) node.style.setProperty(`--deck-${name}`, palette[name]);
  return node;
}

// One stop for Tab, the arrow keys going from card to card -- ↓ to the card below -- and
// Return or Space choosing, the keys staying on the grid as the inspector is drawn again.
// A set of buttons, as Keynote's slide layouts are, not a radio group: a layout is changed
// on purpose (one may take a slide's objects away), never by an arrow passing over it.
function layoutGrid(current, onPick, layouts, palette) {
  const grid = tinted(h("div.layout-grid", { role: "group", "aria-label": "Layout" }, layouts.map((layout) => h(`button.layout-card${layout.name === current ? ".on" : ""}`, {
    type: "button", "aria-pressed": String(layout.name === current), title: layout.note, onclick: () => onPick(layout.name),
  }, glyph(layout.name), h("span.name", {}, LAYOUT_NAMES[layout.name])))), palette);
  ui.roving(grid, () => [...grid.children], "layouts");
  return grid;
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
  // A deck style setting as it is: the deck's own, else its look's, else the default.
  const deckStyle = (name) => doc().deck?.style?.[name]
    ?? catalog.looks.find((look) => look.name === (doc().deck?.look || "classic"))?.style?.[name] ?? styleField(name)?.default;
  const choiceName = (name, choice) => styleField(name)?.labels?.[choice] || ({ start: "Left", middle: "Centre", end: "Right" })[choice] || keyTitle(choice);
  // How to work the slide, said under it the first few times the editor is opened, then not.
  const opened = Number(remembered("opened", "0")) || 0;
  remember("opened", String(opened + 1));
  const learning = opened < 5;
  // Where this document was left -- its slide, and the panel's tab -- is where it opens again.
  const placeKey = `place-${studio.file}`;
  const leftAt = (() => { try { return JSON.parse(remembered(placeKey, "{}")) || {}; } catch { return {}; } })();
  const state = { slide: Math.max(0, Math.min(Number(leftAt.slide) || 0, (studio.doc?.slides?.length || 1) - 1)), picked: [], focus: null, field: null,
    tab: leftAt.tab === "design" ? "design" : "slide", notes: remembered("notes", "0") === "1" };
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
  // Merged, every slide's objects are in places its layout has (as the studio's DeckKind
  // puts them: _laid_out) -- an object kept where the layout has none is put in the first
  // place it has, unless it is there already.
  const PLACES = ["body", "left", "right", "columns"];
  const blocksIn = (value, key) => (!Array.isArray(value) ? [] : key === "columns" ? value.filter(Array.isArray).flat() : [...value]);
  const alikeBlocks = (first, second) => same(first, second) || (linesOf(first) && linesOf(second) && alikeLines(linesOf(first), linesOf(second)) >= 0.5);
  function laidOut(document) {
    for (const slide of Array.isArray(document?.slides) ? document.slides : []) {
      if (!slide || typeof slide !== "object") continue;
      const keys = catalog.slide_keys?.[slide.layout || "content"] || [];
      const places = PLACES.filter((key) => keys.includes(key)), stray = PLACES.filter((key) => key in slide && !keys.includes(key));
      if (!places.length || !stray.length) continue;
      const there = places.flatMap((key) => blocksIn(slide[key], key));
      const lost = stray.flatMap((key) => { const blocks = blocksIn(slide[key], key); delete slide[key]; return blocks; })
        .filter((block) => !there.some((other) => alikeBlocks(block, other)));
      if (!lost.length) continue;
      if (places[0] === "columns") {
        slide.columns = Array.isArray(slide.columns) && slide.columns.length ? [...slide.columns] : [[]];
        slide.columns[0] = [...slide.columns[0], ...lost];
      } else slide[places[0]] = [...(slide[places[0]] || []), ...lost];
    }
    return document;
  }
  studio.mended = (document, notes, base) => laidOut(converted(document, notes, base));
  const slides = () => doc().slides || [];
  const slideAt = (d = doc()) => (d.slides || [])[state.slide];

  const editSlide = (mutate, options = {}) => studio.change((d) => { const slide = (d.slides || [])[state.slide]; if (slide) mutate(slide, d); }, options);
  // A placeholder changed (a sample table typed in) is its person's own: presented and exported.
  const editBlock = (place, mutate, options = {}) => editSlide((slide) => {
    const block = blocksAt(slide, place.region)[place.index];
    if (block) { mutate(block, slide); delete block.placeholder; }
  }, { quiet: true, ...options });
  // Words made a list, a list words, or its bullets numbers, as Keynote's Bullets & Lists:
  // a line an item, the words kept, and what the other kind does not take left off.
  // None is words with no bullets: a list's keeps its levels (Keynote's None: a plain list),
  // a text is one already. "text" makes a list a text (Convert to Text), its items lines.
  const listStyle = (block) => (kindOf(block) !== "bullets" || block.plain ? "none" : block.numbered ? "numbered" : "bulleted");
  // (`words`: its words as they are now in its editor, taken with the change: marks typed
  // at its start that asked for the list, gone.)
  const restyle = (at, style, { words } = {}) => {
    const block = blocksAt(slideAt(), at.region)[at.index];
    if (!block || (style === "text" ? kindOf(block) === "text" : listStyle(block) === style)) return;
    // Its words being typed stay so, the caret where it was, as with Keynote's Bullets & Lists.
    const typing = inline && !inline.cell && inline.at && inline.at.region === at.region && inline.at.index === at.index ? inline.area.caretAt?.() || null : undefined;
    const renamed = (b, from, to, value, drop) => {
      const entries = Object.entries(b).filter(([key]) => !drop.includes(key)).map(([key, was]) => (key === from ? [to, value] : [key, was]));
      for (const key of Object.keys(b)) delete b[key];
      Object.assign(b, Object.fromEntries(entries));
    };
    const label = style === "text" ? "Convert to Text" : kindOf(block) === "text" ? "Convert to List"
      : style === "none" ? (block.numbered ? "Remove Numbers" : "Remove Bullets") : style === "numbered" ? "Number List" : "Bullet List";
    editBlock(at, (b) => {
      if (words !== undefined) { if (kindOf(b) === "text") b.text = words; else if (kindOf(b) === "bullets") b.bullets = bulletsFrom(words); }
      if (style === "text") {
        renamed(b, "bullets", "text", bulletsText(b.bullets).split("\n").map((line) => line.trim()).filter(Boolean).join("\n"), ["numbered", "reveal", "plain"]);
        return;
      }
      if (kindOf(b) === "text") {
        const lines = String(b.text ?? "").split("\n").map((line) => line.trim()).filter(Boolean);
        // Its colour goes with it (muted words a muted list); its alignment is the slide's.
        const colour = b.colour ?? (b.muted ? "muted" : undefined);
        renamed(b, "text", "bullets", lines.length ? lines : [""], ["align", "muted", "colour"]);
        if (colour) b.colour = colour;
      }
      setOption(b, "numbered", style === "numbered", false);
      setOption(b, "plain", style === "none", false);
    }, { label });
    // What the other kind cannot keep is said, with the way back.
    const levels = kindOf(block) === "bullets" && bulletsText(block.bullets).split("\n").some((line) => /^\s/.test(line));
    const looks = kindOf(block) === "text" && block.align !== undefined;
    if (style === "text" && levels) undoNote("Text has no levels: the list's items are now lines", { icon: "text" });
    else if (kindOf(block) === "text" && looks) undoNote("A list takes the slide's alignment", { icon: "list" });
    if (typing !== undefined) {
      if ((style === "text") || kindOf(block) === "text") {
        // Words made a list (or a list words) are typed on as the other kind; a new one is still new.
        const was = fresh;
        fresh = null;
        openInline({ kind: "block", ...at });
        fresh = was;
      } else {
        inline.area.classList.toggle("rt-numbered", style === "numbered");
        inline.area.classList.toggle("rt-plain", style === "none");
      }
      inline?.area.focus();
      if (typing) inline?.area.caretTo?.(...typing);
    }
    renderInspector();
  };
  // A list being typed in shows the marks the list has now: after an undo of Number List,
  // or another's change of it.
  studio.on("change", () => {
    if (!inline?.bullets || !inline.area.rich || !inline.at) return;
    const block = blocksAt(slideAt() || {}, inline.at.region)[inline.at.index];
    if (!block || kindOf(block) !== "bullets") return;
    inline.area.classList.toggle("rt-numbered", Boolean(block.numbered) && !block.plain);
    inline.area.classList.toggle("rt-plain", Boolean(block.plain));
  });
  // (Chosen while words are typed, it leaves them being typed: see closeOnOutside.)
  const listField = (at, block) => {
    const control = ui.segmented({ value: listStyle(block), options: [
      { value: "none", label: "None" }, { value: "bulleted", label: "Bulleted" }, { value: "numbered", label: "Numbered" }],
    onChange: (style) => restyle(at, style) });
    control.dataset.keepsTyping = "";
    return ui.field("List", control);
  };

  // -- the frame --
  const railList = h("div.rail-list.scroll-thin", { tabindex: 0 });
  const rail = h("aside.panel.rail", {}, railList);
  // Notes said in toasts stand over its foot, above the speaker notes (ui.js placeToasts).
  const stage = h("div.stage.deck-stage.scroll-thin", { "data-toast-area": true });
  // (Each time it is typed in, from focusing it to leaving it, a step of its own: `notesRun`.)
  let notesRun = 0;
  const notesArea = ui.textarea({ rows: 3, key: "notes", placeholder: "Click to add speaker notes", onInput: (text) =>
    editSlide((slide) => setOption(slide, "notes", text), { quiet: true, merge: `notes-${state.slide}-${notesRun}`, hold: true }) });
  notesArea.addEventListener("focusin", () => { notesRun += 1; });
  // The notes being typed in, changed by another (or an undo): the caret stays among the words
  // it was in, not sent to their end (an undo's words put back chosen, as TextEdit chooses them).
  const notesChanged = (undone) => {
    const was = notesArea.value, now = slideAt()?.notes || "";
    if (was === now) return;
    const chosen = [notesArea.selectionStart, notesArea.selectionEnd], [ahead, behind] = changeIn(was, now);
    notesArea.value = now;
    notesArea.setSelectionRange(...(undone ? [ahead, now.length - behind] : chosen.map((at) => caretThrough(was, now, at))));
  };
  const notesPreview = h("span.notes-preview");
  const notes = h(`div.notes${state.notes ? ".open" : ""}`, {},
    h("button.notes-head", { type: "button", onclick: () => showNotes(!state.notes) },
      icon("chevron", { class: "caret" }), h("span.notes-label", {}, "Notes"), notesPreview),
    h("div.notes-body", {}, notesArea));
  function showNotes(on) {
    state.notes = on;
    remember("notes", on ? "1" : "0");
    notes.classList.toggle("open", on);
    if (!on) return;
    // A long note opens at its top, not scrolled to its end: the caret where it was put,
    // else (the note just shown, the caret left at its end) at the start.
    const atEnd = notesArea.selectionStart === notesArea.value.length && notesArea.selectionEnd === notesArea.value.length;
    notesArea.focus({ preventScroll: true });
    if (atEnd) { notesArea.setSelectionRange(0, 0); notesArea.scrollTop = 0; }
  }
  const center = h("section.deck-center", {}, stage, notes);
  const inspectorHead = h("div.insp-head");
  const inspectorBody = h("div.panel-body.scroll-thin");
  const inspector = h("aside.panel.inspector", {}, inspectorHead, inspectorBody);
  // Its buttons, swatches and cards clicked leave the keys with the slide, as Keynote's
  // inspector does; its fields take them.
  inspector.addEventListener("mousedown", (event) => {
    // (Not where something is dragged from: a press held back is a drag never started.)
    if (event.target.closest("button, [role=button], .swatch") && !event.target.closest("input, select, textarea, [contenteditable=true], summary, [draggable=true]")) event.preventDefault();
  });
  // A field left ends its run of edits in the history: typed in again, however soon, it is
  // another step. (A field drawn again under the keys is not left: keepFocus.)
  const leftField = (event) => {
    const key = event.target?.dataset?.key, run = studio.lastMerge?.key;
    // (Once a figure's edits on their way are back: they join the run they belong to.)
    setTimeout(() => Promise.resolve(figure?.parts.idle?.()).then(() => {
      if (run && studio.lastMerge?.key === run && (!key || document.activeElement?.dataset?.key !== key)) studio.step();
      reportFocus();
    }), 0);
  };
  inspector.addEventListener("focusout", leftField);
  notesArea.addEventListener("focusout", leftField);
  // Words typed in one place -- on the slide, in a field of the panel, in the notes -- are one
  // run in the history however long its pauses; but, as in Pages and TextEdit, typing,
  // deleting, making or joining lines (a new item, two merged) and a line's level each make a
  // step of their own: the run starts again at each turn. (A figure's words, made by the
  // studio and back later, are its own: parts.js.)
  // (Kept by the field's key, as the panel is drawn again under the keys.)
  const turns = new Map(), turnOf = (target) => target.dataset?.key || target;
  const typingSteps = (container) => {
    const field = (event) => {
      const target = event.target;
      if (!(target?.isContentEditable || /^(INPUT|TEXTAREA)$/.test(target?.tagName || "")) || target.closest?.(".fig-inline")) return null;
      if (figure?.parts.model && inspectorBody.contains(target) && figureBlock()) return null;
      return target.rich ? target : target.closest?.(".rich") || target;
    };
    const words = (target) => (target.rich ? target.letters() : String(target.value ?? ""));
    // Words chosen as a key comes: what it types is typed over them (a word chosen and typed
    // over from its own first letter is no deletion with that letter kept).
    const chose = (target) => (target.rich ? (() => { const s = getSelection(); return Boolean(s.rangeCount && !s.isCollapsed && target.contains(s.anchorNode)); })()
      : target.selectionStart !== target.selectionEnd);
    const look = (event) => { const target = field(event); if (target) turns.set(turnOf(target), { ...turns.get(turnOf(target)), before: words(target), chose: chose(target) }); };
    container.addEventListener("keydown", look, true);
    container.addEventListener("beforeinput", look, true);
    container.addEventListener("input", (event) => {
      const target = field(event);
      if (!target || event.detail?.tidy) return;
      const turn = turns.get(turnOf(target)) || {}, was = turn.before ?? words(target), now = words(target);
      const lines = (text) => text.split("\n").length, type = event.inputType || "";
      // Letters typed over words chosen are typing, as in Keynote, not a deletion and then
      // typing: one "Undo Typing" puts the words chosen back. They start a step of their own.
      const [start, end] = changeIn(was, now), put = now.slice(start, now.length - end);
      const over = (Boolean(put) && !put.includes("\n") && start + end < was.length && !event.isComposing && !/^(delete|insert(Paragraph|LineBreak|Composition))/.test(type))
        || (Boolean(turn.chose) && was !== now && /^insert(Text|ReplacementText)$/.test(type));
      const kind = event.detail?.step || /^format/.test(type) || was === now ? "look"
        : over ? "type"
          : lines(was) !== lines(now) || /^insert(Paragraph|LineBreak)$/.test(type) ? "lines"
            : /^delete/.test(type) || now.length < was.length ? "delete" : "type";
      // (A field's first keys start no step: its run is new anyway -- or goes on, typed on in
      // an editor opened again on the same words made another kind.)
      if ((turn.last !== undefined && kind !== turn.last) || over) studio.step();
      if (turns.size > 200) turns.clear();
      turns.set(turnOf(target), { last: kind === "lines" || kind === "look" ? "edge" : kind });
    }, true);
  };
  typingSteps(center);
  typingSteps(inspector);
  inspector.addEventListener("focusin", () => reportFocus());
  const root = h("div.deck", {}, rail, center, inspector);
  clear(container, root);

  // What the drawings say, as shown. A warning that comes while words are typed (a formula
  // half written does not read) waits until the typing pauses, or stops: it does not flash
  // on and off at each key. (`messages` is what is shown; `drawnMessages`, all there is.)
  let drawnMessages = [], typedAt = 0, heldBack = 0;
  let swapAsked = null;  // the page a hand-arranged figure was asked to swap on (see "drawn")
  const messageKey = (m) => `${m.page}\n${m.severity}\n${m.text}`;
  function sayMessages() {
    clearTimeout(heldBack);
    heldBack = 0;
    const wait = typedAt + 800 - Date.now();
    const shown = new Set(messages.map(messageKey));
    const fresh = wait > 0 ? new Set(drawnMessages.filter((m) => m.severity !== "note" && !shown.has(messageKey(m)))) : new Set();
    messages = drawnMessages.filter((m) => !fresh.has(m));
    if (fresh.size) heldBack = setTimeout(sayHeld, wait);
  }
  function sayHeld() {
    if (!heldBack && messages.length === drawnMessages.length) return;
    sayMessages();
    renderRail();
    renderStage();
    if (mathNotes && document.contains(inspectorBody.querySelector(".math-notes"))) mathNotes();
    markBlockErrors();
  }
  root.addEventListener("input", () => { typedAt = Date.now(); }, true);

  // -- the bar --
  const insertButtons = MAIN_BLOCKS.map((kind) => ui.button(BLOCKS[kind].label, () => insertBlock(kind), { kind: "ghost", icon: BLOCKS[kind].icon, title: `Add ${BLOCKS[kind].label}: ${BLOCKS[kind].hint}` }));
  const moreButton = ui.button("More", (event) => menu(event.currentTarget, MORE_BLOCKS.map((kind) => ({ icon: BLOCKS[kind].icon, label: `${BLOCKS[kind].label}${CHOOSE.has(kind) ? "…" : ""}`, hint: BLOCKS[kind].hint, run: () => insertBlock(kind) }))), { kind: "ghost", icon: "chevron-down" });
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
  // The chosen object's placeholder note, kept to what it holds as it is typed in.
  studio.on("change", () => {
    const note = inspectorBody.querySelector(".placeholder-note");
    const block = note && state.focus && blocksAt(slideAt() || {}, state.focus.region)[state.focus.index];
    if (note && block) note.hidden = !blank(block);
  });

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
    popover(anchor, [h("div.menu-title", {}, "Layout"), layoutGrid(layoutOf(slide), (name) => { closeMenu(); changeLayout(name); }, layouts, studio.info?.palette)], { className: "layout-menu" });
  }

  function newSlidePopover(anchor, at = state.slide + 1) {
    const grid = layoutGrid(null, (name) => { closeMenu(); addSlide(name, at); }, layouts, studio.info?.palette);
    const menu = popover(anchor, [h("div.menu-title", {}, "New Slide"), grid], { className: "layout-menu" });
    // It opens on the layout ⇧⌘N would make (layoutAfter), the arrows going on from there.
    grid.children[Math.max(0, layouts.findIndex((layout) => layout.name === layoutAfter(at - 1)))]?.focus({ preventScroll: true });
    // Words typed at once are the new slide's title, as ⇧⌘N's are: the slide is made in the
    // layout highlighted, the letter the first of its title -- never a layout chosen by its
    // letter, nor one by the space after it. (The arrows, Return and Space choose one.)
    menu.addEventListener("keydown", (event) => {
      if ([...event.key].length !== 1 || event.key === " " || event.metaKey || event.ctrlKey || event.isComposing) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const card = [...grid.children].indexOf(document.activeElement);
      closeMenu();
      addSlide(layouts[card]?.name || layouts[0]?.name || "content", at);
      early?.keys.push({ text: event.key });
    }, true);
  }

  // -- slides --
  function addSlide(layout, at = slides().length) {
    const made = NEW_SLIDES[layout]();
    // (After a slide just like it there -- another's new slide, made a moment ago, not yet
    // typed in: merges know slides by what they hold, the first of two alike taken for the
    // first, so this one, made later, goes later, and neither is typed in for the other.)
    while (at < slides().length && same(slides()[at], made)) at += 1;
    studio.change((d) => { d.slides ||= []; d.slides.splice(at, 0, made); });
    select(at);
    // Its first words are ready to type: the title (a blank slide has none).
    if (layout !== "agenda" && layout !== "blank") openSoon({ kind: "field", field: layout === "statement" ? "words" : "title" });
  }

  // What was just added opens to be typed in a moment later, once it is drawn: the keys
  // typed meanwhile are kept and typed into it then, as Keynote keeps them -- none lost to
  // the page, none taken for a command. (`wait`: when to open, else whoever made it says.)
  let early = null;
  function openSoon(target, wait = 300) {
    const mine = early = { keys: [] };
    const open = () => {
      if (early !== mine) return;
      early = null;
      const where = typeof target === "function" ? target() : target;
      // A new figure's one shape: typed on as soon as it is drawn, the keys with it.
      if (where?.kind === "shape") {
        const id = blocksAt(slideAt(), where.region)[where.index]?.figure?.nodes?.[0]?.id;
        if (id && figure) figure.parts.typeSoon(id, mine.keys);
        return;
      }
      if (!inline && where) openInline(where, { selectAll: true });
      // Letters typed one after another go in at once: one run of typing, the same step in
      // the history as the typing that follows (typingSteps reads what was there before it).
      const keys = mine.keys.reduce((all, key) => {
        if (key.text && all[all.length - 1]?.text) all[all.length - 1] = { text: all[all.length - 1].text + key.text };
        else all.push(key);
        return all;
      }, []);
      for (const key of keys) {
        if (!inline) return;
        inline.area.focus();
        if (key.text) { inline.area.dispatchEvent(new Event("beforeinput", { bubbles: true })); document.execCommand("insertText", false, key.text); continue; }
        if (key.key === "Backspace") { document.execCommand("delete"); continue; }
        const event = new KeyboardEvent("keydown", { key: key.key, code: key.key, shiftKey: key.shift, bubbles: true, cancelable: true });
        inline.area.dispatchEvent(event);
        if (!event.defaultPrevented && key.key === "Enter") document.execCommand("insertText", false, "\n");
      }
    };
    if (wait !== null) setTimeout(open, wait);
    return open;
  }
  document.addEventListener("keydown", (event) => {
    if (!early || inline || !studio.active || event.metaKey || event.ctrlKey || event.isComposing || typingNow()) return;
    const key = event.key;
    if ([...key].length === 1) early.keys.push({ text: key });
    else if (["Backspace", "Enter", "Tab", "Escape"].includes(key)) early.keys.push({ key, shift: event.shiftKey });
    else return;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
  // A click elsewhere before it opens: it is not opened.
  document.addEventListener("mousedown", () => { early = null; }, true);

  function moveSlide(from, to) {
    if (from === to || to < 0 || to >= slides().length) return;
    studio.change((d) => { const [slide] = d.slides.splice(from, 1); d.slides.splice(to, 0, slide); });
    const entry = studio.past[studio.past.length - 1];
    if (entry) studio.said(entry).moved = { from, to };
    select(to);
  }

  function duplicateSlide(index) {
    if (chosenSlides().length > 1 && chosenSlides().includes(index)) { duplicateSlides(chosenSlides()); return; }
    studio.change((d) => { d.slides.splice(index + 1, 0, copyOf(d.slides[index])); });
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
    studio.change((d) => { d.slides.splice(last + 1, 0, ...indices.map((index) => copyOf(d.slides[index]))); });
    select(last + 1);
    state.picked = indices.map((_, n) => last + 1 + n);
    renderRail();
  }
  // `done` names it in the note: "deleted", or "cut" for ⌘X.
  function deleteSlides(indices, done = "deleted") {
    if (indices.length === 1) { deleteSlide(indices[0], done); return; }
    const noted = noteDeleted(indices);
    studio.change((d) => { for (const index of [...indices].sort((a, b) => b - a)) d.slides.splice(index, 1); },
      done === "cut" ? { label: `Cut ${indices.length} Slides` } : {});
    noted.entry(studio.past[studio.past.length - 1]);
    select(Math.min(indices[0], slides().length - 1));
    undoNote(`${indices.length} slides ${done}`, { icon: done === "cut" ? "cut" : "trash" });
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
  const newSlideLike = (index) => addSlide(layoutAfter(index), index + 1);
  // The layout of a new slide after the one at `index`, as Keynote's New Slide follows the
  // slide it is made after: its own, or Content after one that is not a content slide (a
  // title, agenda, section, statement or blank).
  const layoutAfter = (index) => (["title", "agenda", "section", "statement", "blank"].includes(layoutOf(slides()[index])) ? "content" : layoutOf(slides()[index]));

  // Slides deleted here lately, by layout and title, and the step in the history that
  // deleted them (see followChange).
  let deletedHere = [];
  const noteDeleted = (indices) => {
    const noted = indices.map((index) => slides()[index]).filter(Boolean).map((slide) => ({ slide: structuredClone(slide), at: Date.now(), entry: null }));
    deletedHere = [...deletedHere.filter((gone) => Date.now() - gone.at < 60000), ...noted];
    return { entry: (entry) => { for (const gone of noted) gone.entry = entry; } };
  };
  // Likewise objects deleted here lately: each with its name and the step that deleted it.
  let objectsDeleted = [];
  function deleteSlide(index, done = "deleted") {
    const noted = noteDeleted([index]);
    studio.change((d) => { d.slides.splice(index, 1); }, done === "cut" ? { label: "Cut Slide" } : {});
    noted.entry(studio.past[studio.past.length - 1]);
    select(Math.min(index, slides().length - 1));
    undoNote(`Slide ${done}`, { icon: done === "cut" ? "cut" : "trash" });
  }

  function slideMenu(anchor, index) {
    const count = slides().length;
    // A thumbnail's menu is about its slide -- or the slides chosen with it -- which a
    // right-click chooses, as in Keynote.
    const together = chosenSlides().length > 1 && chosenSlides().includes(index) ? chosenSlides() : null;
    if (!together && (index !== state.slide || state.focus || state.field)) select(index);
    railList.focus({ preventScroll: true });
    // Named and keyed as the slide's own menu and the palette name them.
    const many = together ? `${together.length} Slides` : "Slide";
    menu(anchor, [
      { icon: "plus", label: "New Slide", keys: "⇧⌘N", run: () => newSlideLike(together ? Math.max(...together) : index) },
      "-",
      ...clipItems(),
      { icon: "duplicate", label: `Duplicate ${many}`, keys: "⌘D", run: () => (together ? duplicateSlides(together) : duplicateSlide(index)) },
      "-",
      // Greyed where it cannot go, as a Mac menu's items are, rather than left out.
      ...(!together ? [{ icon: "up", label: "Move Up", disabled: index === 0, run: () => moveSlide(index, index - 1) },
        { icon: "down", label: "Move Down", disabled: index >= count - 1, run: () => moveSlide(index, index + 1) }] : []),
      "-",
      { icon: "trash", label: `Delete ${many}`, keys: "⌫", danger: true, run: () => deleteSlides(together || [index]) },
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
    // Its thumbnail whole in view, ring and all (a new slide's, at the foot of the list) --
    // again once the list is laid out, as a new thumbnail's size is known only then.
    const inView = () => {
      const thumb = railList.querySelector(".thumb.on");
      if (!thumb) return;
      // (WebKit's and Chromium's "nearest" take a thumbnail its ring short of the edge as shown.)
      const box = thumb.getBoundingClientRect(), port = railList.getBoundingClientRect();
      if (box.bottom + 8 > port.bottom) thumb.scrollIntoView({ block: "end" });
      else if (box.top - 8 < port.top) thumb.scrollIntoView({ block: "start" });
    };
    inView();
    requestAnimationFrame(inView);
    if (pages[state.slide]?.stale) studio.requestDraw(0);
    reportFocus();
    readSlideAhead();
  }

  function reportFocus() {
    const slide = slideAt();
    if (!slide) { studio.focus(null); return; }
    const block = state.focus && blocksAt(slide, state.focus.region)[state.focus.index];
    const part = block ? ` · ${blockName(block)}` : "";
    // Typed in -- on the slide (a figure's shape's words too), or in the panel's fields -- it is
    // shown the others as being edited.
    const keys = document.activeElement;
    const editing = Boolean(inline) || Boolean(figure?.parts.inline) || Boolean(inspectorBody.contains(keys) && keys.matches("input, textarea, [contenteditable=true]"));
    studio.focus({ page: state.slide + 1, label: `Slide ${state.slide + 1}${part}`, block: state.focus ? `${state.focus.region}[${state.focus.index}]` : null,
      field: !state.focus && state.field ? state.field.field : null, part: block ? partWithin(block) : null, editing });
  }
  // The part of the object chosen that is chosen or typed in, as the others are shown it: a
  // figure's shape (its id), a table's cell ("row.column"), by its id in the drawing after the
  // object's own -- null for the object as a whole.
  function partWithin(block) {
    if (kindOf(block) === "figure" && figureBlock() === block) {
      const parts = figure.parts, chosen = parts.inline?.id ?? parts.selected?.[parts.selected.length - 1];
      return chosen ? String(chosen) : null;
    }
    if (kindOf(block) !== "table") return null;
    const own = blockId(state.focus);
    const typed = inline?.cell ? inline.idOf() : null;
    if (typed?.startsWith(`${own}.`)) return typed.slice(own.length + 1);
    const key = document.activeElement?.dataset?.key || "";
    return inspectorBody.contains(document.activeElement) && /^cell\.\d+\.\d+$/.test(key) ? key.slice(5) : null;
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
      // Kept as it is, unless it has lost its picture (one taken for a drawing elsewhere).
      if (railKeys[index] === key && old[index] && (!page?.svg || old[index].querySelector(".picture"))) return old[index];
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
    // Another's ring outside the frame, never in place of this person's own (the chosen
    // slide's blue): an outline, beyond the box-shadow that rings it.
    h("div.frame", { style: here.length ? { outline: `2px solid ${colourOf(here[0].who)}`, outlineOffset: "3px" } : {} },
      page?.svg ? picture(page.svg, page.hash) : h("div.placeholder", {}, slideTitle(slide)),
      worst ? h(`div.badge.${worst}`, { title: own.map((m) => m.text).join("\n") }, icon(worst === "error" ? "close" : "warning", { weight: "2" })) : null,
      page?.steps > 1 ? h("div.steps", { title: "Items appear one at a time" }, `${page.steps} steps`) : null,
      // Two at most, and how many more there are.
      here.length ? h("div.here", { title: here.map((entry) => nameOf(entry.who)).join(", ") }, here.slice(0, 2).map((entry) => avatar(entry.who, { size: 18 })),
        here.length > 2 ? h("span.avatar.more", { style: { width: "18px", height: "18px", background: "var(--muted, #868e96)" } }, `+${here.length - 2}`) : null) : null,
      slideMoreButton(index)),
    h("button.insert-after", { type: "button", tabindex: -1, title: "Add a slide here", onclick: (event) => { event.stopPropagation(); newSlidePopover(event.currentTarget, index + 1); } }, icon("plus")));
    return node;
  }

  function slideMoreButton(index) {
    const button = ui.button("", (event) => { event.stopPropagation(); slideMenu(event.currentTarget, index); }, { kind: "ghost", icon: "more", small: true, title: "Slide actions" });
    button.classList.add("more");
    // The slide list is one stop for Tab, its slides chosen with the arrows: its buttons are for the pointer.
    button.tabIndex = -1;
    return button;
  }

  railList.addEventListener("keydown", (event) => {
    if (event.target !== railList || state.focus || state.field) return;
    if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); if (slides().length) deleteSlides(chosenSlides()); }
    // Return adds a slide after the one chosen, as in Keynote's slide navigator.
    else if (event.key === "Enter" && !event.metaKey && !event.ctrlKey && !event.altKey) { event.preventDefault(); event.stopPropagation(); newSlideLike(state.slide); }
    // ⌘A chooses every slide, as in Keynote's slide navigator (on the slide, its objects).
    else if ((event.metaKey || event.ctrlKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "a") {
      event.preventDefault();
      event.stopPropagation();
      state.picked = slides().map((_, n) => n);
      renderRail();
    }
    // ⇧↓ and ⇧↑ choose a run of slides from the one first chosen, as a Mac list does.
    else if (event.shiftKey && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      event.stopPropagation();
      const from = state.picked.length > 1 && runFrom !== null ? runFrom : state.slide;
      const to = Math.max(0, Math.min(slides().length - 1, state.slide + (event.key === "ArrowDown" ? 1 : -1)));
      select(to);
      const low = Math.min(from, to), high = Math.max(from, to);
      state.picked = Array.from({ length: high - low + 1 }, (_, n) => low + n);
      runFrom = from;
      renderRail();
    }
  });
  let runFrom = null;  // where a run of slides chosen with ⇧↓ began
  // Keys go to what was chosen last: once something on the slide is chosen, not the slides.
  const offRail = () => { if (railList.contains(document.activeElement)) document.activeElement.blur(); };

  // -- the stage --
  const hover = h("div.hit.hover", { hidden: true }, h("span.hit-label"));
  const chosen = h("div.hit.selected", { hidden: true }, h("span.hit-label"));
  const target = h("div.hit.target", { hidden: true }, h("span.hit-label"));  // what a menu item would act on
  let pageNode = null;
  const stageMeta = h("div.slide-meta");
  const stageMessages = h("div.slide-messages.messages", { hidden: true });
  const stageWrap = h("div.slide-wrap", {}, stageMeta, stageMessages);
  // A figure's shape's words typed in (in a box beside the page): shown the others as editing.
  for (const type of ["focusin", "focusout"]) stageWrap.addEventListener(type, () => setTimeout(() => { if (figure) reportFocus(); }));

  let notesFor = null;
  let wasOffline = false;
  studio.on("status", () => { const now = studio.state === "offline"; if (now !== wasOffline) { wasOffline = now; renderStage(); } });
  function renderStage() {
    const list = slides();
    const slide = slideAt();
    // The notes shown are the slide's shown: kept as typed only while the same slide's.
    if (document.activeElement !== notesArea || notesFor !== state.slide) {
      notesFor = state.slide;
      notesArea.value = slide?.notes || "";
      requestAnimationFrame(() => { notesArea.style.height = "auto"; notesArea.style.height = `${Math.max(notesArea.scrollHeight + 2, 60)}px`; });
    }
    notesPreview.textContent = slide?.notes ? plain(slide.notes) : "Click to add speaker notes";
    // (Not .empty: that is the studio's "nothing here" panel, padded and centred.)
    notesPreview.classList.toggle("unwritten", !slide?.notes);
    notes.hidden = !list.length;
    if (!list.length) {
      clear(stage, h("div.stage-empty", {}, h("h2", {}, "No slides"), h("div", {}, "Choose a layout for the first slide:"),
        tinted(h("div.layout-grid.big", {}, layouts.map((layout) => h("button.layout-card", { type: "button", onclick: () => addSlide(layout.name, 0) },
          glyph(layout.name), h("span.name", {}, LAYOUT_NAMES[layout.name]), h("span.note", {}, layout.note)))), studio.info?.palette)));
      return;
    }
    const page = pages[state.slide];
    // The slide's drawing is put in the page again only when it changed: parsing
    // and laying out an SVG is the costliest thing the stage does.
    // Not drawn, with the studio away: the slide's title, calmly, not a spinner that never ends.
    const away = !page?.svg && studio.state === "offline";
    const shows = page?.svg ? `${state.slide}:${page.hash}` : away ? `away:${state.slide}` : "";
    let before = null, moved = null;
    if (!pageNode || pageNode.dataset.shows !== shows) {
      // A figure's parts just moved on this slide: they land from where they were.
      before = figureBlock() ? figure.parts.landing() : null;
      // So do the slide's own parts, just moved or swapped.
      moved = blockLanding();
      landing = null;
      if (carry) dropCarry();
      pageNode = h("div.slide-page", { dataset: { shows } });
      if (page?.svg) { pageNode.innerHTML = page.svg.replace(/^<\?xml[^>]*>\s*/, ""); ownResources(pageNode.querySelector("svg")); }
      else pageNode.append(away ? h("div.placeholder.away", {}, h("span.away-title")) : h("div.placeholder", {}, h("div.spinner")));
      const svg = pageNode.querySelector("svg");
      if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); svg.setAttribute("preserveAspectRatio", "xMidYMid meet"); }
      if (svg) widenLines(svg);
      // A link drawn on the slide is words, chosen and edited as any: never a place for the
      // keys, nor followed by any click (a middle-click's new tab included).
      for (const link of pageNode.querySelectorAll("a")) { link.removeAttribute("href"); link.removeAttributeNS("http://www.w3.org/1999/xlink", "href"); }
      // The page under the drawing is the slide's own colour: a dark slide shows no light
      // edge where the drawing falls a fraction short of it.
      const paper = svg?.querySelector('[id="canvas.background"]')?.getAttribute("fill");
      if (paper && paper !== "none") pageNode.style.background = paper;
      // What the pointer was over has moved, or gone: shown again when it moves.
      hover.hidden = true;
      pageNode.append(hover, chosen, target);
      pageNode.addEventListener("mousemove", onHover);
      pageNode.addEventListener("mouseleave", () => { hover.hidden = true; });
      pageNode.addEventListener("click", onPick);
      pageNode.addEventListener("dblclick", onEdit);
      // A link's words are chosen and edited as any words: a click never goes to its page.
      pageNode.addEventListener("click", (event) => { if (event.target.closest?.("a")) event.preventDefault(); });
      pageNode.addEventListener("contextmenu", onContext);
      pageNode.addEventListener("pointerdown", onPress);
    }
    pageNode.querySelector(".away-title")?.replaceChildren(slideTitle(slide));
    pageNode.classList.toggle("error", Boolean(page?.error));
    pageNode.classList.toggle("pending", Boolean(pending || page?.stale));
    const own = messages.filter((m) => m.page === `slide${state.slide + 1}`);
    const here = studio.others().filter((entry) => entry.where?.page === state.slide + 1);
    if (stageWrap.parentNode !== stage) clear(stage, stageWrap);
    // The page alone is put in again: what else is beside it (a part's words being typed) stays.
    if (stageWrap.firstChild !== pageNode) {
      if (stageWrap.firstChild?.classList?.contains("slide-page")) stageWrap.firstChild.replaceWith(pageNode);
      else stageWrap.prepend(pageNode);
    }
    clear(stageMeta,
      h("span.slide-count", {}, `${state.slide + 1} / ${list.length}`),
      page?.steps > 1 ? h("span.chip", {}, icon("reveal"), `${page.steps} steps`) : null,
      here.map((entry) => h("span.here-chip", { style: { borderColor: colourOf(entry.who) } }, avatar(entry.who, { size: 16 }), nameOf(entry.who),
        entry.doing || entry.where?.editing ? h("span.muted", {}, ` · ${entry.doing || "editing"}`) : null)),
      h("span.spacer", { style: { flex: 1 } }),
      // With the studio away nothing is drawn: said so, not a spinner that never ends.
      pending ? (studio.state === "offline" ? h("span.stage-hint", {}, "Drawn again when the studio is back")
        : h("span.row.drawing", {}, h("span.spinner"), "Updating…")) : learning ? h("span.stage-hint", {}, "Click to select · Drag to move · Double-click to edit text") : null);
    clear(stageMessages, own.map((message) => messageView(message, true)));
    stageMessages.hidden = !own.length;
    fitStage();
    placeChosen();
    placeOthers(here);
    if (inline) positionInline();
    if (figureMarks.parentNode !== pageNode) pageNode.append(figureMarks, figureBar);
    placeFigure();
    figure?.parts.placeInline();
    if (before && figureBlock()) figure.parts.land(before);
    if (moved) landBlocks(moved);
    placeStandIns();
  }

  // Words typed with the studio away stay on the slide as typed once the typing ends -- in
  // their place and look (the editor's, without its frame) -- until the slide is drawn again
  // with them: never its old words meanwhile, as if the typing were lost. (Each goes once its
  // slide is drawn again, or its words are no longer the ones typed: an undo, another's change.)
  let standIns = [];
  function standIn() {
    if (!inline?.area.rich || inline.under || studio.state !== "offline") return;
    const node = inline.node.cloneNode(true);
    node.classList.add("standin");
    node.inert = true;
    for (const each of node.querySelectorAll("[contenteditable]")) each.removeAttribute("contenteditable");
    standIns.push({ node, id: inline.id, slide: state.slide, hash: pages[state.slide]?.hash, read: inline.read, value: inline.area.value });
    queueMicrotask(() => placeStandIns());
  }
  function placeStandIns(drop = null) {
    standIns = standIns.filter((each) => {
      const here = each.slide === state.slide;
      const keep = pages[each.slide]?.hash === each.hash && (!here || each.read() === each.value) && !(here && each.id === drop);
      if (!keep) { each.node.remove(); if (here) pageNode?.querySelector(`[id="${CSS.escape(each.id)}"]`)?.style.removeProperty("visibility"); }
      return keep;
    });
    for (const each of standIns) {
      if (each.slide !== state.slide) { each.node.remove(); continue; }
      if (each.node.parentNode !== center) center.append(each.node);
      pageNode?.querySelector(`[id="${CSS.escape(each.id)}"]`)?.style.setProperty("visibility", "hidden");
    }
  }
  studio.on("change", () => placeStandIns());

  // Under its slide a message need not name the slide: what on it, if anything, follows
  // its words.
  function messageView(message, onSlide = false) {
    const where = placeOf(message.where);
    const link = where && where.region !== null;
    const place = onSlide ? String(message.place || "").replace(/^Slide \d+(?: · )?/, "") : message.where && (message.place || message.where);
    return h(`div.message.${message.severity}${link ? ".link" : ""}`, { onclick: () => { if (link) focusBlock(where.region, where.index); } },
      icon(message.severity === "error" ? "error" : message.severity === "note" ? "info" : "warning"),
      h("div", {}, message.text, place ? (onSlide ? h("span.where", {}, ` · ${place}`) : h("div.where", {}, place)) : null));
  }

  function fitStage() {
    const room = stage.getBoundingClientRect();
    const width = Math.max(320, Math.min(room.width - 80, (room.height - 110) * 16 / 9));
    stage.style.setProperty("--slide-max", `${width}px`);
  }
  new ResizeObserver(() => { fitStage(); placeChosen(); placeOthers(); if (inline) positionInline(); placeFigure(); figure?.parts.placeInline(); }).observe(stage);

  // What the others on this slide have chosen -- an object, a line of the slide's words --
  // framed in their colour and named, as Keynote shows the people editing with you.
  const othersFrames = h("div.others-frames");
  function placeOthers(here = studio.others().filter((entry) => entry.where?.page === state.slide + 1)) {
    if (!pageNode) return;
    // Under this person's own frames, and a little outside them: what is chosen here shows
    // whole on an object another has chosen too.
    if (othersFrames.parentNode !== pageNode) { if (hover.parentNode === pageNode) pageNode.insertBefore(othersFrames, hover); else pageNode.append(othersFrames); }
    clear(othersFrames);
    for (const entry of here) {
      const at = /^(.+)\[(\d+)\]$/.exec(entry.where?.block || "");
      const field = entry.where?.field;
      const id = at ? blockId({ region: at[1], index: Number(at[2]) }) : null;
      // Round the shape or the cell they are at, where they are at one; else the object.
      const part = id && entry.where?.part ? boxOf(`${id}.${entry.where.part}`) : null;
      const box = part || (at ? frameOf({ kind: "block", region: at[1], index: Number(at[2]), id })
        : field ? frameOf({ kind: "field", id: fieldId(field) }) : null);
      if (!box) continue;
      const frame = h(`div.hit.other${entry.where.editing ? ".editing" : ""}`, {}, h("span.hit-label", {}, nameOf(entry.who)));
      frame.style.setProperty("--other", colourOf(entry.who));
      othersFrames.append(frame);
      const framed = { left: box.left - 3, top: box.top - 3, width: box.width + 6, height: box.height + 6 };
      place(frame, framed);
      tagClear(frame.firstChild, framed, part && at ? frameOf({ kind: "block", region: at[1], index: Number(at[2]), id }) : null);
    }
  }
  // Another's name tag where it hides no words, as Keynote's and Google Docs' do: over its
  // frame's top edge; else under it; else, for a shape or a cell, above the whole object they
  // are in; else beside the frame; else only their initial, on the frame's corner.
  function tagClear(tag, framed, object) {
    const words = [...pageNode.querySelectorAll("text")].map((text) => text.getBoundingClientRect()).filter((one) => one.width && one.height);
    const onWords = () => {
      const at = tag.getBoundingClientRect();
      return words.some((one) => one.left < at.right && one.right > at.left && one.top < at.bottom && one.bottom > at.top);
    };
    const tries = [
      () => true,
      () => { tag.classList.add("below"); return true; },
      () => {
        tag.classList.remove("below");
        if (!object || object.top >= framed.top - 1) return false;
        tag.style.top = `${object.top - framed.top - 21}px`;
        return true;
      },
      () => { tag.style.top = "0px"; tag.style.left = "calc(100% + 4px)"; tag.style.right = "auto"; tag.style.borderRadius = "4px"; return true; },
    ];
    for (const attempt of tries) if (attempt() && !onWords()) return;
    tag.removeAttribute("style");
    tag.title = tag.textContent;
    tag.textContent = tag.textContent.trim().charAt(0).toUpperCase();
    Object.assign(tag.style, { top: "-10px", right: "-10px", padding: "0", width: "19px", textAlign: "center", borderRadius: "50%" });
  }

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
    const outer = pageNode.getBoundingClientRect();
    for (const node of pageNode.querySelectorAll("[id]")) {
      if (!BLOCK_ID.test(node.id)) continue;
      let box = node.getBoundingClientRect();
      // Words are pressed anywhere in their frame, as wide as it is shown (wordsRoom).
      const part = partOf(node), block = part && blocksAt(slideAt() || {}, part.region)[part.index];
      const room = block && WIDE.has(kindOf(block)) ? frameOf(part) : null;
      if (room) box = { left: outer.left + room.left, right: outer.left + room.left + room.width, top: box.top, bottom: box.bottom, width: room.width, height: box.height };
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

  // A line of words' frame, chosen or pointed at: round its letters as they are inked, the
  // same room on every side -- not its box, as tall as its face's ascent and descent, which
  // its last letter may reach past.
  const inkPen = document.createElement("canvas").getContext("2d");
  function wordsFrame(id) {
    const ink = inkOf(id);
    if (!ink) return boxOf(id);
    const outer = pageNode.getBoundingClientRect(), room = 8;
    return { left: ink.left - outer.left - room, top: ink.top - outer.top - room, width: ink.right - ink.left + 2 * room, height: ink.bottom - ink.top + 2 * room };
  }
  // Where a line of words' letters are inked, on the page.
  function inkOf(id) {
    const element = pageNode?.querySelector(`[id="${CSS.escape(id)}"]`);
    if (!element) return null;
    let ink = null;
    for (const text of wordsIn(element)) {
      const style = getComputedStyle(text);
      inkPen.font = `${style.fontStyle} ${style.fontWeight} ${parseFloat(style.fontSize) * (text.getScreenCTM()?.a || 1)}px ${style.fontFamily}`;
      const lines = [...text.children].filter((span) => span.matches("tspan") && span.textContent.trim());
      for (const line of lines.length ? lines : [text]) {
        const box = line.getBoundingClientRect(), metrics = inkPen.measureText(line.textContent);
        const face = metrics.fontBoundingBoxAscent + metrics.fontBoundingBoxDescent;
        if (!box.width || !face) continue;
        const baseline = box.top + box.height * (metrics.fontBoundingBoxAscent / face);
        const each = { left: box.left - Math.max(0, metrics.actualBoundingBoxLeft), right: Math.max(box.right, box.left + metrics.actualBoundingBoxRight),
          top: baseline - metrics.actualBoundingBoxAscent, bottom: baseline + metrics.actualBoundingBoxDescent };
        ink = ink ? { left: Math.min(ink.left, each.left), right: Math.max(ink.right, each.right), top: Math.min(ink.top, each.top), bottom: Math.max(ink.bottom, each.bottom) } : each;
      }
    }
    return ink;
  }

  function place(node, box, label) {
    node.hidden = !box;
    if (!box) return;
    Object.assign(node.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` });
    if (label !== undefined) node.firstChild.textContent = label;
    clearOfWords(node.firstChild);
  }
  // A tag names what it frames from above it -- or, with words there (a list's last line
  // over a figure), from under it, else from inside its top right corner: never on words.
  function clearOfWords(tag) {
    tag.classList.remove("below", "inside");
    if (tag.parentNode.hidden || !tag.textContent || !pageNode) return;
    const words = [...pageNode.querySelectorAll("text")].map((text) => text.getBoundingClientRect()).filter((box) => box.width && box.height);
    const onWords = () => {
      const at = tag.getBoundingClientRect();
      return words.some((box) => box.left < at.right && box.right > at.left && box.top < at.bottom && box.bottom > at.top);
    };
    if (!onWords()) return;
    tag.classList.add("below");
    if (onWords()) tag.classList.replace("below", "inside");
  }

  function labelOf(part) {
    if (part.kind === "field") return { title: "Title", subtitle: "Subtitle", byline: "Byline" }[part.field] || "Text";
    const block = blocksAt(slideAt() || {}, part.region)[part.index];
    return block ? blockName(block) : "";
  }

  function onHover(event) {
    if (figure?.parts.inline) hover.hidden = true;
    if (figure?.parts.dragging || carry?.started || inline || figure?.parts.inline) return;
    if (inFigure(event)) {
      const id = figure.parts.idAt(event);
      // A shape's own words name it: its frame needs no tag over the words above it. One
      // chosen has its frame already: no second one inside it.
      const box = id && figure.parts.model && !figure.parts.selected.includes(id) ? boxOf(figurePrefix() + id) : null;
      place(hover, box, "");
      return;
    }
    const part = partAt(event);
    // A figure's parts are shown one by one, as they will be chosen: by the first click.
    const inner = part && figurePartAt(event, part);
    if (inner) { place(hover, boxOf(inner.element.id), ""); return; }
    // What is chosen has its own frame: no second one, nor a tag over the words above it.
    const chosenNow = part && (part.kind === "block" ? state.focus && state.focus.region === part.region && state.focus.index === part.index
      : state.field && state.field.field === fieldOf(part.field));
    if (chosenNow) { hover.hidden = true; return; }
    place(hover, part && frameOf(part), part ? labelOf(part) : "");
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
    const part = partAt(event);
    // A shape of a figure not yet chosen is dragged as the shape, the figure chosen first.
    if (part && figurePartAt(event, part)) { focusBlock(part.region, part.index, () => figure.parts.pointerdown(event)); return; }
    pressBlock(event, part);
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
        return { index, label: blockName(block), element, box: drawnBox(element) };
      }),
    }));
  }

  function pressBlock(event, part) {
    if (event.button !== 0 || event.shiftKey || event.metaKey || event.ctrlKey || event.altKey) return;
    if (!part || part.kind !== "block" || carry || figure?.parts.dragging) return;
    const element = blockElement(part.region, part.index);
    if (!element) return;
    // One of several chosen: they are carried together (`all`, in the slide's order).
    const chosenNow = allOn() ? allBlocks().map(({ region, index }) => ({ region: region.key, index })) : [];
    const all = chosenNow.length > 1 && chosenNow.some((each) => samePlace(each, part)) ? chosenNow : null;
    carry = { from: { region: part.region, index: part.index }, start: { x: event.clientX, y: event.clientY }, started: false, element, frame: 0, at: null, all };
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
    // The others chosen with it are lifted with it, and follow it.
    const group = (carry.all || []).filter((each) => !samePlace(each, carry.from)).map((each) => blockElement(each.region, each.index)).filter(Boolean).map(mover);
    for (const wrap of group) wrap.classList.add("block-lifted");
    const zone = h("div.block-drop-zone", {}, h("span.hit-label"));
    const line = h("div.block-drop-line");
    pageNode.append(zone, line);
    pageNode.classList.add("block-dragging");
    document.body.classList.add("block-grabbing");
    Object.assign(carry, { started: true, regions, home, lifted, group, scale: scaleOf(lifted), zone, line, shifted: [] });
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
    for (const wrap of carry.group) wrap.style.transform = `translate(${dx * scaleOf(wrap)}px, ${dy * scaleOf(wrap)}px)`;
    const at = dropAt(carry.pointer);
    if (JSON.stringify(at) !== JSON.stringify(carry.at)) { carry.at = at; showDrop(at); }
  }

  const dropAt = (point) => (carry.all ? groupDrop(carry.regions, carry.from, carry.all, point) : blockDrop(carry.regions, carry.from, point));

  function showDrop(at) {
    for (const wrap of carry.shifted) wrap.style.transform = "";
    carry.shifted = [];
    carry.zone.classList.remove("on");
    carry.line.classList.remove("on");
    carry.lifted.classList.toggle("block-astray", !at);
    for (const wrap of carry.group) wrap.classList.toggle("block-astray", !at);
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
      const isFrom = (block) => (carry.all || [carry.from]).some((each) => region.key === each.region && block.index === each.index);
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
    for (const wrap of was.group) wrap.classList.remove("block-lifted", "block-astray");
    // The drag ends in a click on whatever is under the pointer: that click is not one.
    swallowClick = true;
    setTimeout(() => { swallowClick = false; }, 0);
    return was;
  }
  // Its drawing is going (drawn again under it): let go of it where it is.
  function dropCarry() { finishCarry(); }
  function sendHome(was) {
    for (const wrap of [...was.shifted, ...was.group]) wrap.style.transform = "";
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
    // Several: they land together where the one grabbed lands, in their order, still chosen.
    if (was.all) {
      const slide = slideAt();
      const plan = gatherPlan(Object.fromEntries(regionsOf(slide).map((region) => [region.key, blocksAt(slide, region.key).length])), was.all, at);
      moving = { slide: state.slide, at: Date.now(), plan, wraps: [was.lifted, ...was.group, ...was.shifted] };
      const mine = moving;
      setTimeout(() => { if (moving === mine) { moving = null; for (const wrap of mine.wraps) wrap.style.transform = ""; placeChosen(); } }, 6000);
      const keys = [...new Set([...was.all.map((each) => each.region), at.region])];
      keepAll = true;
      editSlide((s) => gather(Object.fromEntries(keys.map((key) => [key, blocksAt(s, key, true)])), was.all, at), { label: `Move ${was.all.length} Objects` });
      keepAll = false;
      chooseMany(plan.filter(([old]) => was.all.some((each) => samePlace(each, old))).map(([, now]) => now));
      markMany(was.all, allChosen?.picks || null);
      placeChosen(); renderInspector(); reportFocus();
      return;
    }
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
    // What is chosen shows as chosen at once: the name tag of what the pointer was over goes.
    hover.hidden = true;
    if (event.shiftKey && part?.kind === "block" && (state.focus || allOn())) { pickAlso(part); return; }
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
  // What a drawn line of words is written as: a statement's are its words and, under them,
  // who said it.
  const fieldOf = (drawn) => {
    const statement = layoutOf(slideAt()) === "statement";
    return drawn === "byline" ? (statement ? "by" : "author") : statement ? "words" : drawn;
  };

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
      // Its own line double-clicked (a quote's attribution): that line.
      const own = Object.keys(OWN_LINES[kindOf(block)] || {}).find((name) => event.target.closest?.(`[id="${CSS.escape(`${part.id}.${name}`)}"]`));
      if (block && own) openInline({ kind: "block", region: part.region, index: part.index, part: own }, { at: point });
      else if (block && INLINE.has(kindOf(block))) openInline({ kind: "block", region: part.region, index: part.index }, { at: point });
      else if (block && kindOf(block) === "table") {
        const cell = cellAt(part.id, event);
        // The word double-clicked chosen, as in any words.
        if (cell) openInline({ kind: "cell", region: part.region, index: part.index, ...cell }, { at: point });
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
    // One of several chosen: they stay chosen, and its menu acts on them all.
    if (inChoice(part)) {
      const count = allBlocks().length;
      menu(point, [...clipItems(), { icon: "duplicate", label: `Duplicate ${count} Objects`, keys: "⌘D", run: () => duplicateChosen() }, "-", ...chosenCommands()]);
      return;
    }
    if (part?.kind !== "block") {
      leaveFigure(false);
      state.focus = null;
      if (part?.kind === "field") { offRail(); state.field = { field: fieldOf(part.field), id: part.id }; }
      else { state.field = null; railList.focus({ preventScroll: true }); }
      placeChosen();
      renderInspector();
      menu(point, slideItems(part));
      return;
    }
    const block = blocksAt(slideAt(), part.region)[part.index];
    if (block && kindOf(block) === "figure" && editable(block)) {
      // Into the figure: the part under the pointer is chosen, with its own menu.
      const show = () => {
        const id = figure?.parts.model ? figure.parts.idAt(event) : null;
        if (id && id !== figure.parts.model.root) {
          // In the object menu's order: what is its own, then Cut, Copy, Paste and Duplicate, then Delete.
          const own = figure.parts.menuOf(id, point), last = (label) => own.filter((item) => item?.label === label);
          const first = own.filter((item) => !["Duplicate", "Delete"].includes(item?.label));
          menu(point, [...first, "-", ...clipItems(), ...last("Duplicate"), "-", ...last("Delete")]);
          return;
        }
        figure?.parts.select([]);
        blockMenu(point, part);
      };
      if (figureBlock() && figure.region === part.region && figure.index === part.index && figure.parts.model) show();
      else focusBlock(part.region, part.index, show);
      return;
    }
    focusBlock(part.region, part.index);
    blockMenu(point, part, block && kindOf(block) === "table" ? cellAt(part.id, event) : null);
  }
  // Greyed out, as a Mac menu's are, when there is nothing to cut, copy or paste.
  const clipItems = () => [
    { icon: "cut", label: "Cut", keys: "⌘X", disabled: !clipOf(), run: () => clipChosen(true) },
    { icon: "copy", label: "Copy", keys: "⌘C", disabled: !clipOf(), run: () => clipChosen(false) },
    { icon: "paste", label: "Paste", keys: "⌘V", disabled: !clipboard, run: () => clipboard && pasteClip(clipboard) },
  ];
  function clipChosen(cut) {
    const clip = clipOf();
    if (!clip) return;
    clipboard = clip;
    navigator.clipboard?.writeText(plainOf(clip)).catch(() => {});
    if (cut) cutAway(clip); else copied(clip);
  }
  // What is copied, by name, for a command: "Table", "2 Shapes", "Slide".
  const clipName = (clip) => (clip.what === "block" ? blockLabel(clip.block) : clip.label.replace(/(^|\s)\p{L}/gu, (first) => first.toUpperCase()));
  function blockMenu(point, at, cell = null) {
    const slide = slideAt(), block = blocksAt(slide, at.region)[at.index];
    if (!block) return;
    const kind = kindOf(block), count = blocksAt(slide, at.region).length;
    const items = [];
    if (INLINE.has(kind)) items.push({ icon: "pencil", label: kind === "math" ? "Edit Equation" : kind === "code" ? "Edit Code" : "Edit Text", run: () => openInline({ kind: "block", ...at }) });
    if (kind === "text") items.push({ icon: "list", label: "Convert to List", run: () => restyle(at, "bulleted") });
    if (kind === "bullets") items.push({ icon: "text", label: "Convert to Text", run: () => restyle(at, "text") });
    if (cell) items.push({ icon: "pencil", label: "Edit Cell", run: () => openInline({ kind: "cell", ...at, ...cell }, { selectAll: true }) }, "-", ...tableItems(at, cell));
    if (kind === "figure" && editable(block)) items.push({ icon: "plus", label: "Add Shape…", keys: "A", run: () => whenFigure(() => figure.parts.addPalette(point)) });
    if (SIZED.has(kind) && block.width != null) items.push({ icon: "refresh", label: "Reset Size", run: () => sizeFit() });
    if (kind === "figure") items.push({ icon: "export", label: "Export Figure…", run: () => menu(point, exportItems(at)) });
    if (items.length) items.push("-");
    items.push(...clipItems(), { icon: "duplicate", label: "Duplicate", keys: "⌘D", run: () => insertBlock(kind, copyOf(block), at, `Duplicate ${blockLabel(block)}`) });
    items.push({ icon: "up", label: "Move Up", keys: "⌥↑", disabled: at.index === 0, run: () => moveBlock(at, { region: at.region, index: at.index - 1 }) },
      { icon: "down", label: "Move Down", keys: "⌥↓", disabled: at.index >= count - 1, run: () => moveBlock(at, { region: at.region, index: at.index + 2 }) });
    for (const other of regionsOf(slide)) {
      if (other.key !== at.region) items.push({ icon: "right", label: `Move to ${other.name}`, run: () => moveBlock(at, { region: other.key, index: blocksAt(slide, other.key).length }) });
    }
    items.push("-", { icon: "trash", label: "Delete", keys: "⌫", danger: true, run: () => deleteBlock(at) });
    menu(point, items);
  }
  // A table's rows and columns, from the cell under the pointer, as in Keynote. Each
  // column's alignment goes with it.
  function tableItems(at, { row, col }) {
    const rows = tableRows(blocksAt(slideAt(), at.region)[at.index]), columns = rows[0].length;
    const reshape = (mutate) => {
      editBlock(at, (b) => {
        const grid = tableRows(b), align = alignList(b.align, columns);
        mutate(grid, align);
        b.table = grid;
        if (align) b.align = align;
      });
      renderInspector();
    };
    const blank = () => Array(columns).fill("");
    // The row or column an item acts on, outlined on the slide while the item is pointed at.
    const table = blockId(at);
    const outline = (cells, on) => {
      if (!on) { target.hidden = true; return; }
      const boxes = cells.map(([r, c]) => cellBox(`${table}.${r}.${c}`)).filter(Boolean);
      if (!boxes.length) return;
      const left = Math.min(...boxes.map((b) => b.left)), top = Math.min(...boxes.map((b) => b.top));
      place(target, { left, top, width: Math.max(...boxes.map((b) => b.left + b.width)) - left, height: Math.max(...boxes.map((b) => b.top + b.height)) - top });
    };
    const theRow = (on) => outline(rows[row].map((_, c) => [row, c]), on), theColumn = (on) => outline(rows.map((_, r) => [r, col]), on);
    return [
      { icon: "plus", label: "Add Row Above", show: theRow, run: () => reshape((grid) => grid.splice(row, 0, blank())) },
      { icon: "plus", label: "Add Row Below", show: theRow, run: () => reshape((grid) => grid.splice(row + 1, 0, blank())) },
      { icon: "plus", label: "Add Column Before", show: theColumn, run: () => reshape((grid, align) => { grid.forEach((line) => line.splice(col, 0, "")); align?.splice(col, 0, align[col]); }) },
      { icon: "plus", label: "Add Column After", show: theColumn, run: () => reshape((grid, align) => { grid.forEach((line) => line.splice(col + 1, 0, "")); align?.splice(col + 1, 0, align[col]); }) },
      { icon: "trash", label: "Delete Row", disabled: rows.length < 2, show: theRow, run: () => reshape((grid) => grid.splice(row, 1)) },
      { icon: "trash", label: "Delete Column", disabled: columns < 2, show: theColumn, run: () => reshape((grid, align) => { grid.forEach((line) => line.splice(col, 1)); align?.splice(col, 1); }) },
    ];
  }
  // A figure's exports, as the menu that Export Figure… opens.
  const exportItems = (at) => [{ title: "Export Figure As" },
    ...FIGURE_EXPORTS.map(({ label, formats, hint }) => ({ icon: "export", label: `${label}…`, hint, run: () => exportFigure(at, formats) }))];

  // The slide's own: its words, what may be added to it, and the slide.
  function slideItems(part) {
    const index = state.slide, room = regionsOf(slideAt()).length > 0;
    const field = part?.kind === "field" ? part.field : null;
    return [
      field ? { icon: "pencil", label: `Edit ${{ title: "Title", subtitle: "Subtitle", author: "Byline", words: "Text", by: "Attribution" }[fieldOf(field)] || "Text"}`, run: () => openInline({ kind: "field", field: fieldOf(field) }) } : null,
      // What the toolbar adds, in its order.
      ...MAIN_BLOCKS.map((kind) => ({ icon: BLOCKS[kind].icon, label: `Add ${BLOCKS[kind].label}${CHOOSE.has(kind) ? "…" : ""}`, disabled: !room, run: () => insertBlock(kind) })),
      // Then the slide's, as its thumbnail's menu has them. On the slide itself its list has
      // the keys (a right-click on it gives them): ⌘C copies it and ⌫ deletes it. On a
      // title, they are the title's.
      "-",
      { icon: "plus", label: "New Slide", keys: "⇧⌘N", run: () => newSlideLike(index) },
      "-",
      ...(field ? [{ icon: "paste", label: "Paste", keys: "⌘V", disabled: !clipboard, run: () => clipboard && pasteClip(clipboard) }] : clipItems()),
      { icon: "duplicate", label: "Duplicate Slide", keys: "⌘D", run: () => duplicateSlide(index) },
      "-",
      { icon: "trash", label: "Delete Slide", keys: field ? undefined : "⌫", danger: true, run: () => deleteSlide(index) },
    ].filter(Boolean);
  }

  function placeChosen() {
    const focus = state.focus;
    placeAll();
    if (sizing) return;  // its frame follows it as it is sized
    if (!focus && state.field && pageNode && !inline && !moving && !landing) {
      place(chosen, frameOf({ kind: "field", id: state.field.id }), { title: "Title", subtitle: "Subtitle", author: "Byline", words: "Text", date: "Date", by: "Attribution" }[state.field.field] || "Text");
      chosen.classList.remove("sizable", "holder");
      return;
    }
    if (!focus || !pageNode || moving || landing || carry?.started || inline) { chosen.hidden = true; return; }
    const region = regionsOf(slideAt()).find((r) => r.key === focus.region);
    const block = blocksAt(slideAt() || {}, focus.region)[focus.index];
    const box = region && frameOf({ kind: "block", ...focus, id: `slide${state.slide + 1}.${region.svg}.${focus.index}` });
    place(chosen, box, block ? blockName(block) : "");
    chosen.classList.toggle("sizable", Boolean(block && SIZED.has(kindOf(block))));
    holding();
  }
  // ⌘A chooses all the slide's objects, as Keynote's Select All, and ⇧-click one more (or
  // one less): each framed, and deleted, copied, cut or duplicated together. Anything else
  // chosen (a press on the slide, Esc, another slide) ends it. (`picks`: those chosen;
  // `seen`: the document they were chosen in, to follow them through changes from.)
  let allChosen = null;
  const chooseMany = (picks, slide = state.slide) => { allChosen = picks.length ? { slide, picks: picks.map(({ region, index }) => ({ region, index })), seen: doc() } : null; };
  // A change of several chosen, in the history: undone or redone, they are chosen again
  // (`before`, `after`: where they were, and are; chooseChanged).
  const markMany = (before, after) => { const entry = studio.past[studio.past.length - 1]; if (entry) studio.said(entry).many = { slide: state.slide, before, after }; };
  const picksNow = () => allBlocks().map(({ region, index }) => ({ region: region.key, index }));
  const allFrames = h("div.all-frames");
  const allOn = () => Boolean(allChosen && allChosen.slide === state.slide && !state.focus && !state.field && !inline && slideAt());
  const allBlocks = () => regionsOf(slideAt() || {}).flatMap((region) => blocksAt(slideAt(), region.key).map((block, index) => ({ region, index, block })))
    .filter(({ region, index }) => !allChosen?.picks || allChosen.picks.some((pick) => pick.region === region.key && pick.index === index));
  function pickAlso(part) {
    const picks = allOn() ? allBlocks().map(({ region, index }) => ({ region: region.key, index })) : [{ region: state.focus.region, index: state.focus.index }];
    const at = picks.findIndex((pick) => pick.region === part.region && pick.index === part.index);
    if (at >= 0) picks.splice(at, 1); else picks.push({ region: part.region, index: part.index });
    allChosen = null;
    // One left is simply chosen; none, nothing is.
    if (picks.length === 1) { focusBlock(picks[0].region, picks[0].index); return; }
    closeInline();
    leaveFigure(false);
    state.focus = null; state.field = null;
    chooseMany(picks);
    placeChosen(); renderInspector(); reportFocus();
  }
  function placeAll() {
    if (allChosen && !allOn()) allChosen = null;
    // (Not while they are carried, or glide to where they were let go.)
    const each = allChosen && pageNode && !moving && !landing && !carry?.started ? allBlocks() : [];
    while (allFrames.children.length > each.length) allFrames.lastChild.remove();
    while (allFrames.children.length < each.length) allFrames.append(h("div.hit.selected", {}, h("span.hit-label")));
    each.forEach(({ region, index }, n) => place(allFrames.children[n], frameOf({ kind: "block", region: region.key, index, id: `slide${state.slide + 1}.${region.svg}.${index}` }), ""));
    if (each.length && allFrames.parentNode !== pageNode) pageNode.append(allFrames);
  }
  function chooseAll() {
    if (!allBlocks().length) return;
    closeInline();
    leaveFigure(false);
    state.focus = null; state.field = null;
    allChosen = null;
    chooseMany(picksNow());
    placeChosen(); renderInspector(); reportFocus();
  }
  // Several chosen moved together, as Keynote moves them (⌥↑ ⌥↓, Arrange › Move Up and Move
  // Down): each up or down its column past the next one not chosen, in order; ⌥← ⌥→, each
  // to the end of the column beside its own. One step, and they stay chosen. Whether any
  // would move (`dry`), else false.
  function moveAll(arrow, dry = false) {
    const keys = regionsOf(slideAt() || {}).map((region) => region.key);
    const chosenNow = allBlocks();
    const lists = Object.fromEntries(keys.map((key) => [key, blocksAt(slideAt(), key).map((_, index) => ({ region: key, index,
      chosen: chosenNow.some((each) => each.region.key === key && each.index === index) }))]));
    let moved = false;
    if (arrow === "ArrowUp" || arrow === "ArrowDown") {
      const step = arrow === "ArrowUp" ? -1 : 1;
      for (const list of Object.values(lists)) {
        for (let n = 0; n < list.length; n += 1) {
          const i = step < 0 ? n : list.length - 1 - n, j = i + step;
          if (list[i].chosen && list[j] && !list[j].chosen) { [list[i], list[j]] = [list[j], list[i]]; moved = true; }
        }
      }
    } else {
      const side = arrow === "ArrowRight" ? 1 : -1;
      const going = keys.map((key, column) => (keys[column + side] ? lists[key].filter((item) => item.chosen) : []));
      keys.forEach((key, column) => {
        if (!going[column].length) return;
        lists[key] = lists[key].filter((item) => !item.chosen);
        moved = true;
      });
      keys.forEach((key, column) => lists[keys[column + side]]?.push(...going[column]));
    }
    if (!moved || dry) return moved;
    const before = picksNow();
    keepAll = true;
    editSlide((slide) => {
      const was = Object.fromEntries(keys.map((key) => [key, [...blocksAt(slide, key)]]));
      for (const key of keys) {
        const list = blocksAt(slide, key, true);
        list.splice(0, list.length, ...lists[key].map((item) => was[item.region][item.index]));
      }
    }, { label: `Move ${chosenNow.length} Objects` });
    keepAll = false;
    chooseMany(keys.flatMap((key) => lists[key].map((item, index) => (item.chosen ? { region: key, index } : null)).filter(Boolean)));
    markMany(before, allChosen?.picks || null);
    placeChosen(); renderInspector();
    return true;
  }
  // Changed any other way (another's edit, an agent's, an undo), they stay chosen where they
  // now are -- followed by what they hold, as the one object chosen is (followChange) --
  // and those deleted are chosen no more, said when another deleted them. (An undo or a redo
  // of what was done to them chooses them again: chooseChanged.)
  let keepAll = false;
  studio.on("change", (event) => {
    if (!allChosen || keepAll || (event?.source === "history" && event.entry?.many)) return;
    const before = allChosen.seen?.slides || [], after = slides();
    const to = before.length ? follows(before, after)[allChosen.slide] ?? -1 : -1;
    const old = partsOf(before[allChosen.slide] || {}), now = to >= 0 ? partsOf(after[to] || {}) : [];
    const map = follows(old.map((part) => part.block), now.map((part) => part.block));
    const kept = allChosen.picks.map((pick) => old.findIndex((part) => part.region === pick.region && part.index === pick.index)).filter((k) => k >= 0 && map[k] >= 0);
    const picks = kept.map((k) => ({ region: now[map[k]].region, index: now[map[k]].index }));
    const gone = allChosen.picks.length - picks.length;
    if (gone && event?.source === "remote" && picks.length) {
      toast(`${nameOf(event.who)} deleted ${gone === 1 ? "one" : gone} of the objects you chose`, { icon: "info", seconds: 5 });
    }
    chooseMany(picks, to);
    // One left is the one chosen (where it was, for followChange to follow it from, after
    // another's change or an undo; else where it is).
    if (picks.length === 1 && to >= 0) {
      allChosen = null;
      const followed = event?.source === "remote" || event?.source === "history";
      state.focus = followed ? { region: old[kept[0]].region, index: old[kept[0]].index } : { ...picks[0] };
    }
    placeChosen(); renderInspector();
  });
  // The objects chosen, by column, the last first.
  const picked = () => allBlocks().map(({ region, index }) => ({ key: region.key, index })).sort((a, b) => b.index - a.index);
  // Those chosen deleted (or cut) at once, one step.
  function deleteAll(done = "deleted") {
    const gone = picked(), before = picksNow();
    allChosen = null;
    editSlide((s) => { for (const { key, index } of gone) blocksAt(s, key).splice(index, 1); }, { label: `${done === "cut" ? "Cut" : "Delete"} ${gone.length} Objects` });
    markMany(before, null);
    placeChosen(); renderInspector(); reportFocus();
    undoNote(`${gone.length} objects ${done}`, { icon: done === "cut" ? "cut" : "trash" });
  }
  // A press on the slide chooses afresh -- unless on one of them, which carries them all
  // when dragged (pressBlock); let go without a drag, that one is chosen alone (onPick).
  const inChoice = (part) => part?.kind === "block" && allOn() && allBlocks().some((each) => each.region.key === part.region && each.index === part.index);
  stage.addEventListener("mousedown", (event) => {
    // (A right-click on one of them keeps them: its menu is theirs.)
    if (!allChosen || event.shiftKey || carry?.all || ((event.button === 2 || event.ctrlKey) && inChoice(partAt(event)))) return;
    allChosen = null;
    placeChosen(); renderInspector(); reportFocus();
  }, true);

  // A figure whose part is chosen is only outlined round it: the part is what is chosen.
  const holding = () => chosen.classList.toggle("holder", Boolean(figureBlock() && figure.parts.selected.length));

  // A figure chosen is edited at once: `then` (a click, a double-click on one of its
  // parts) is done to it as soon as its parts are known.
  function focusBlock(region, index, then = null) {
    closeInline();
    offRail();
    state.tab = "slide";
    state.focus = { region, index };
    chosenLast = { slide: state.slide, region };
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
  // The figures holding edits for the studio while it is away, the latest last: ⌘Z and Undo
  // take back the last edit held first.
  const heldBy = new Set();
  // (Taken back, made again by ⇧⌘Z and Redo, by the figure that took it back.)
  const tookBack = [];
  studio.takeBack = () => {
    const by = [...heldBy].pop();
    if (!by?.parts.takeBackWaiting()) return false;
    tookBack.push(by);
    studio.emit("status");
    return true;
  };
  studio.takeBackLabel = () => [...heldBy].pop()?.parts.waitingLabel() || null;
  studio.putBack = () => {
    while (tookBack.length && !tookBack[tookBack.length - 1].parts.takenLabel()) tookBack.pop();
    return Boolean(tookBack.pop()?.parts.putBackWaiting());
  };
  studio.putBackLabel = () => [...tookBack].reverse().map((by) => by.parts.takenLabel()).find(Boolean) || null;
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
    const own = figure;
    figure.parts = figureParts({
      catalog: catalog.figure_editor,
      get overlay() { return pageNode; },
      // A slide's page keeps its size: what is added to the figure stays on it.
      fixedPage: true,
      // The box a part's words are typed in stays beside the page as the slide is drawn again.
      typing: stageWrap,
      element: (id) => { const prefix = figurePrefix(); return prefix && pageNode ? pageNode.querySelector(`[id="${CSS.escape(prefix + id)}"]`) : null; },
      idOf: (id) => { const prefix = figurePrefix(); return prefix && id.startsWith(prefix) ? id.slice(prefix.length) : null; },
      box: (id) => { const prefix = figurePrefix(); return prefix ? boxOf(prefix + id) : null; },
      // (What is chosen has its frame: the pointer's dashed one goes from it, till it moves.)
      changed: () => { hover.hidden = true; renderInspector(); placeFigure(); },
      settled: () => placeFigure(),
      chooseFile: async (options) => relativeTo(figureFolder(), await chooseFile(options)),
      tones: () => studio.info?.tones,
      palette: () => studio.info?.palette,
      // Edits held while the studio is away: the deck is not saved meanwhile.
      // (Counted: each figure's edits held tell it, a figure left meanwhile included; ⌘Z and
      // Undo take back the last of them first.)
      waiting: (on) => {
        studio.waiting = Math.max(0, (studio.waiting || 0) + (on ? 1 : -1));
        if (on) heldBy.add(own); else heldBy.delete(own);
        studio.emit("status");
      },
      // Another edit held while it is away: Undo names it.
      held: () => studio.emit("status"),
      // (A label's ⌘Z, once someone else's words came into it, is the deck's undo: false when
      // that undo left the figure.)
      undo: () => { studio.undo(); return figure === own; },
      redo: () => { studio.redo(); return figure === own; },
      addAnchor: () => figureBar.querySelector(".add") || figureBar,
      groupAnchor: () => figureBar.querySelector(".group") || figureBar,
      crumbs: () => h("button.crumb", { type: "button", onclick: () => { state.focus = null; renderInspector(); placeChosen(); reportFocus(); } }, `Slide ${state.slide + 1}`),
      // The shape chosen in it is shown the others, as the object is.
      focus: () => reportFocus(),
      nothing: () => [...blockPanel(slideAt(), figureBlock()), figure.parts.howTo()],
      // Its edits are made on it wherever the page has gone since (one held while the
      // studio was away, sent once it is back).
      run: (action, options) => runFigure(action, options, own),
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
    // Its line chosen is marked along its path, in the drawing: unmarked as it is left.
    for (const twin of pageNode?.querySelectorAll(".hit-line.chosen") || []) twin.classList.remove("chosen");
    figureBar.hidden = true;
    root.classList.remove("wide");
    if (render) renderInspector();
  }

  // The server makes the edit where the figure is written; if the deck changed while
  // it did, the edit is made again on the deck as it is now.
  let figureCut = false;  // the figure's next delete is a cut (⌘X), and said so
  // Whether a shape is in the figure on the slide as the deck now has it (a figure kept in
  // a file of its own: taken to be).
  const shapeIn = (id) => {
    const value = figureBlock()?.figure;
    return typeof value !== "object" || JSON.stringify(value).includes(`"id":${JSON.stringify(id)}`);
  };
  // A shape typed in that another has deleted (`was`, the deck before) is kept, as an object
  // typed in is (keepTyped): put back as it was here, with its lines and its place in its
  // group, and said -- the one who deleted it is told it is back (shapesBack). A figure kept
  // in a file of its own cannot be: there the typing ends, said once, rather than failing at
  // every key. (Not a shape just added, not in the deck yet.)
  function shapeGone(was) {
    const typing = figure?.parts.inline;
    const id = typing?.id;
    if (!typing || typing.kind !== "node" || shapeIn(id) || !JSON.stringify(was ?? null).includes(`"id":${JSON.stringify(id)}`)) return false;
    const old = blocksAt((was?.slides || [])[figure.slide], figure.region)[figure.index]?.figure;
    const node = typeof old === "object" ? (old.nodes || []).find((item) => item.id === id) : null;
    if (!node || typeof figureBlock()?.figure !== "object") {
      figure.parts.closeInline(false);
      toast(`${nameOf(lastWho)} deleted the shape you were editing`, { icon: "info", seconds: 5 });
      return true;
    }
    const at = { slide: figure.slide, region: figure.region, index: figure.index };
    const ends = (ref) => String(ref) === id || String(ref).startsWith(`${id}.`);
    studio.change((d) => {
      const now = blocksAt(d.slides?.[at.slide], at.region)[at.index]?.figure;
      if (!now || typeof now !== "object") return;
      now.nodes = [...(now.nodes || [])];
      now.nodes.splice(Math.min(old.nodes.indexOf(node), now.nodes.length), 0, structuredClone(node));
      const here = JSON.stringify(now);
      const there = (ref) => ends(ref) || here.includes(`"id":${JSON.stringify(String(ref).split(".")[0])}`);
      for (const edge of old.edges || []) {
        if ((ends(edge.from) || ends(edge.to)) && there(edge.from) && there(edge.to) && !(now.edges || []).some((other) => same(other, edge))) now.edges = [...(now.edges || []), structuredClone(edge)];
      }
      for (const group of old.groups || []) {
        const kept = (now.groups || []).find((other) => other.id === group.id);
        if (kept && group.children?.includes(id) && !kept.children?.includes(id)) kept.children = [...(kept.children || [])].toSpliced(group.children.indexOf(id), 0, id);
      }
    }, { quiet: true, merge: studio.lastMerge?.key ?? null, hold: true });
    toast(`${nameOf(lastWho)} deleted the shape you're editing. It stays.`, { icon: "info", seconds: 6 });
    return true;
  }
  // A figure a shape of which is typed in here, deleted by another meanwhile: kept, as it was
  // here, and said -- as an object typed in is (keepTyped); the one who deleted it is told it
  // is back (followChange).
  function figureKept(was, who) {
    if (!figure?.parts.inline || !Array.isArray(was?.slides)) return false;
    const old = blocksAt(was.slides[figure.slide], figure.region)[figure.index];
    const to = follow(was.slides, slides())[figure.slide];
    if (!old || kindOf(old) !== "figure" || to === undefined || to < 0) return false;
    const now = blocksAt(slides()[to], figure.region);
    if (follows([old], now)[0] >= 0) return false;
    const index = Math.min(figure.index, now.length), region = figure.region;
    studio.change((d) => { blocksAt(d.slides[to], region, true).splice(index, 0, structuredClone(old)); }, { quiet: true, merge: studio.lastMerge?.key ?? null, hold: true });
    Object.assign(figure, { slide: to, index });
    toast(`${nameOf(who)} deleted ${editedHere("the figure")}. It stays.`, { icon: "info", seconds: 6 });
    return true;
  }
  // Shapes deleted here lately, with the step that deleted them: back because another was still
  // typing in one, said so, and the deleting leaves the history (as an object's does).
  let shapesDeleted = [];
  function shapesBack(was, who) {
    shapesDeleted = shapesDeleted.filter((gone) => Date.now() - gone.at < 60000);
    if (!shapesDeleted.length) return;
    const before = JSON.stringify(was?.slides ?? null), after = JSON.stringify(slides());
    const has = (text, id) => text.includes(`"id":${JSON.stringify(id)}`);
    for (const gone of [...shapesDeleted]) {
      if (!gone.ids.some((id) => has(after, id) && !has(before, id))) continue;
      toast(`${gone.name ? `${gone.name} is` : "A shape deleted here is"} back: ${nameOf(who)} was still editing it.`, { icon: "info", seconds: 6 });
      const at = studio.past.indexOf(gone.entry);
      if (at >= 0) { studio.past.splice(at, 1); studio.emit("status"); }
      shapesDeleted = shapesDeleted.filter((item) => item !== gone);
    }
  }
  async function runFigure(action, { merge, hold = false, label: told = null }, own = figure) {
    if (!own) return null;
    // (Its words, still on their way, go with it.)
    if (own === figure && action.do === "update" && [action.target, ...(action.targets || [])].some((part) => part?.type === "node" && !shapeIn(part.id))) return null;
    const at = { slide: own.slide, region: own.region, index: own.index };
    // What changed is read from the figure before and after, but for a part moved: a swap
    // read from the figure alone could be either part's, so it is said as the parts say it.
    // A duplicate or a paste is said as such, not as the shapes it adds; a cut, as a cut; a
    // shape put into a line, as put between the two it joins.
    // (So is a part moved in a figure drawn turned, its groups written as drawn first.)
    let label = ["move", "step", "duplicate", "paste", "add"].includes(action.do) || merge?.startsWith("as-drawn:") ? told : null;
    if (action.do === "delete" && figureCut) { figureCut = false; label = told?.replace(/^Delete\b/, "Cut") || null; }
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const sent = studio.doc;
      const result = await studio.api("/api/act", { file: studio.file, document: sent, action: { do: "figure", at, edit: action } }).catch((error) => {
        // The studio out of reach: said so, for the edit to wait for it (figure parts hold it).
        if (error instanceof TypeError || same(studio.doc, sent)) throw error;
        return null;  // the deck changed meanwhile: made again on it as it is now
      });
      if (!same(studio.doc, sent)) {
        if (action.do === "update" && [action.target, ...(action.targets || [])].some((part) => part?.type === "node" && !shapeIn(part.id))) return null;
        continue;
      }
      // A figure's look changed at once (an arrowhead, a colour -- not words being typed) is
      // drawn in the layout that suits it best straight away, not kept as it was a moment
      // and then moved.
      const settles = action.do === "update" && !hold;
      // (Its parts glide there, should it be drawn another way.)
      if (settles) own.parts?.settles?.();
      if (result.file) {
        if (action.do !== "read") { if (settles) settling = true; studio.requestDraw(0); }
        if (result.was !== undefined) recordFile(result, at, label, merge, hold);
      }
      else if (!same(result.document, sent)) {
        studio.change(() => result.document, { merge, hold, quiet: true, label });
        if (settles) settling = true;
        if (action.do === "delete") {
          const name = action.ids?.length === 1 ? /“.*”/.exec(told || "")?.[0] || null : null;
          shapesDeleted.push({ ids: [...(action.ids || [])], name, at: Date.now(), entry: studio.past[studio.past.length - 1] });
        }
      }
      return result;
    }
    return null;
  }

  // An edit to a figure kept in its own file is written there, not in the deck: the
  // deck's history keeps it all the same, undone by putting the file back as it was
  // (if no one has changed it since).
  function recordFile(result, at, label, merge, hold = false) {
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
    }, { merge, hold });
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
      ui.button("", (event) => menu(event.currentTarget, exportItems(figure)),
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
  function openInline(target, { selectAll = false, at: point = null, replaceWith = null, tabbed = false, run = null } = {}) {
    closeInline();
    const slide = slideAt();
    if (!slide) return;
    // What is typed from opening to closing is one step in the history, however long its
    // pauses, and a step of its own: another time in the same words is another step. (`run`:
    // the typing going on from another editor, its step's.)
    const session = run ?? Date.now();
    // The slide shown and the block's place follow edits from elsewhere (followChange).
    const slideNow = (d = doc()) => (d?.slides || [])[state.slide];
    // Words are typed as the slide shows them: bold as bold, a list as a list.
    const rich = (value, options, onInput) => {
      // Its format bar kept on the stage, never over the slides or the inspector beside it.
      const field = richText({ value, palette: studio.info?.palette || {}, room: () => stage.getBoundingClientRect(), ...options });
      onRich(field, onInput);
      return field;
    };
    let editor, idOf, at = null, bullets = false, read = () => undefined, mirror = null;
    if (target.kind === "field") {
      const key = target.field;
      if (!catalog.slide_keys[layoutOf(slide)].includes(key)) return;
      read = (d) => slideNow(d)?.[key] ?? "";
      mirror = `slide.${key}`;
      // What is typed in is the one thing chosen, and the panel shows it (Tab come from an object).
      state.field = { field: key, id: fieldId(key) };
      if (state.focus) { state.focus = null; leaveFigure(false); renderInspector(); reportFocus(); }
      // A field the slide has none of (a title slide's subtitle) is put there empty as it
      // is opened, so the slide draws it, as its placeholder, where its words will go; its
      // words typed are the same step in the history. Left empty, it is taken back.
      const merge = `${state.slide}-${key}-${session}`;
      if (slide[key] === undefined) {
        editSlide((s) => { s[key] = ""; }, { quiet: true, merge, hold: true });
        placed = { key, slide: state.slide, entry: studio.past[studio.past.length - 1], merge };
      }
      // Emptied, it stays, as its placeholder, until it is closed.
      editor = rich(slide[key] ?? "", { single: key !== "words", placeholder: { title: "Title", subtitle: "Subtitle", words: "Text", author: "Author", date: "Date", by: "Who said it" }[key] },
        (text) => {
          if (placed?.key === key && studio.past[studio.past.length - 1] === placed.entry) studio.lastMerge = { key: merge, at: Date.now() };
          editSlide((s) => { s[key] = text; }, { quiet: true, merge, hold: true });
        });
      idOf = () => fieldId(key);
    } else if (target.kind === "cell") {
      const block = blocksAt(slide, target.region)[target.index];
      const rows = tableRows(block);
      if (!rows[target.row] || target.col >= rows[target.row].length) return;
      at = { region: target.region, index: target.index };
      read = (d) => { const now = blocksAt(slideNow(d) || {}, at.region)[at.index]; return now && kindOf(now) === "table" ? tableRows(now)[target.row]?.[target.col] : undefined; };
      // The format bar stands over the table, not over the rows above the cell.
      const table = () => pageNode?.querySelector(`[id="${CSS.escape(blockId(at))}"]`)?.getBoundingClientRect();
      // An empty header cell hints its column, as the slide does ("Column 1").
      const hint = block.header !== false && target.row === 0 ? `Column ${target.col + 1}` : "";
      editor = rich(rows[target.row][target.col], { single: true, frame: table, placeholder: hint, onCells: (cells) => pasteCells(at, target.row, target.col, cells) },
        (text) => editBlock(at, (b) => { const cells = tableRows(b); cells[target.row][target.col] = text; b.table = cells; },
          { merge: `${state.slide}-${at.region}-${at.index}-cell-${target.row}-${target.col}-${session}`, hold: true }));
      idOf = () => `${blockId(at)}.${target.row}.${target.col}`;
      // What is typed in is the one thing chosen: no title chosen before it is still.
      state.field = null;
      state.focus = at;
      renderInspector();
      reportFocus();
    } else {
      const block = blocksAt(slide, target.region)[target.index];
      if (!block) return;
      const kind = kindOf(block);
      at = { region: target.region, index: target.index };
      const merge = `${state.slide}-${at.region}-${at.index}-inline-${session}`;
      read = (d) => {
        const now = blocksAt(slideNow(d) || {}, at.region)[at.index];
        if (!now || kindOf(now) !== kind) return undefined;
        return kind === "bullets" ? bulletsText(now.bullets) : now[kind] ?? "";
      };
      mirror = `block.${kind}`;
      bullets = kind === "bullets";
      // A spreadsheet's cells pasted in the words are a table after them.
      const onCells = (cells) => { closeInline(); insertBlock("table", { table: cells }, at, "Paste Table"); };
      // And an outline or a list pasted in them, a list (listAfter).
      const onList = (items) => { const was = fresh; fresh = null; closeInline(); fresh = was; listAfter(at, items); };
      // Return on its empty last item ends the list: a paragraph after it, typed in at once.
      const onEnd = (kept) => paragraphAfter(at, kept);
      // "1. ", "- " or "• " typed at the start of its words (of a list's item) makes a list of
      // that kind, as in Pages and Keynote: the marks go, one step ⌘Z takes back to them.
      const onListStart = kind === "text" || kind === "bullets" ? (style, unmark) => {
        const now = blocksAt(slideAt() || {}, at.region)[at.index];
        if (!now || listStyle(now) === style || !inline?.at || inline.at.region !== at.region || inline.at.index !== at.index) return;
        unmark();
        restyle(at, style, { words: inline.area.value });
      } : null;
      // Written only as the kind it was opened as: an object made another kind meanwhile (a
      // paragraph made a list) is never written its old kind's words beside the new's -- the
      // editor follows it, as that kind, at once (refreshInline).
      const write = (put) => (text) => editBlock(at, (b) => { if (kindOf(b) === kind) put(b, text); }, { merge, hold: true });
      // An object's own line of words besides its words (a quote's attribution, a callout's
      // heading), typed on the slide where it is drawn -- or, not written yet, where it will be.
      const part = OWN_LINES[kind]?.[target.part] ? target.part : null;
      if (part) {
        read = (d) => { const now = blocksAt(slideNow(d) || {}, at.region)[at.index]; return now && kindOf(now) === kind ? String(now[part] ?? "") : undefined; };
        mirror = `block.${part}`;
        editor = rich(String(block[part] ?? ""), { single: true, placeholder: OWN_LINES[kind][part] }, write((b, text) => setOption(b, part, text)));
      } else if (bullets) editor = rich(bulletsText(block.bullets), { list: true, numbered: Boolean(block.numbered), plain: Boolean(block.plain), placeholder: "Text", onCells, onEnd, onListStart }, write((b, text) => { b.bullets = bulletsFrom(text, true); }));
      else if (kind === "code") editor = ui.textarea({ value: block.code, rows: 1, mono: true, indent: true, placeholder: "Code", onInput: write((b, text) => { b.code = codeOf(text); }) });
      else if (kind === "math") editor = ui.textarea({ value: block.math, rows: 2, mono: true, spelling: false, placeholder: "E = mc^2", onInput: write((b, text) => { b.math = text; }) });
      else editor = rich(block[kind] ?? "", { placeholder: { text: "Text", quote: "Quote", callout: "Text" }[kind] || "", onCells, onListStart, onList }, write((b, text) => { b[kind] = text; }));
      idOf = () => (part ? `${blockId(at)}.${part}` : blockId(at));
      state.field = null;
      state.focus = at;
      renderInspector();
      placeChosen();
      reportFocus();
    }
    const area = editor.area || editor;
    const cell = target.kind === "cell";
    const node = h(`div.inline-editor.in-place${cell ? ".cell" : ""}`, { onmousedown: (event) => event.stopPropagation(),
      title: cell ? "Tab: next cell · Return: cell below · ⌘B: bold · ⌘I: italic · Esc: done"
        : `${bullets ? "Tab: indent · Shift-Tab: outdent" : "Tab: next object"} · ⌘B: bold · ⌘I: italic · ⌘K: link · ⌃Tab: format bar · ${target.kind === "field" && target.field !== "words" ? "Return or Esc: done" : "Esc: done"}` }, editor);
    area.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); closeInline({ escaped: true }); }
      // Return ends a line of the slide's words (a statement's takes it as a line break, as
      // Keynote's does); it stays chosen, the next keys going on at its end, not over it.
      if (event.key === "Enter" && !event.shiftKey && target.kind === "field" && target.field !== "words") {
        event.preventDefault();
        closeInline();
        if (state.field) state.field.ended = true;
      }
      // Tab goes on to the slide's next line of words (title, subtitle, byline) or object, and
      // ⇧Tab back, not to the inspector; a list's Tab sets its levels (and ⌃Tab goes to the
      // format bar).
      if (event.key === "Tab" && !event.ctrlKey && !event.metaKey && !event.altKey && (target.kind === "field" || (target.kind === "block" && area.rich && !bullets))) {
        event.preventDefault();
        tabOn(target, event.shiftKey);
      }
      // The key is the cell's: Return past the last row ends the typing, and does not go on
      // to the table it leaves chosen (whose Return opens its first cell).
      if (target.kind === "cell" && (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey))) { event.preventDefault(); event.stopPropagation(); nextCell(target, event.key, event.shiftKey); }
    });
    // A list Tab came to, all of it chosen, is passed on by the next Tab (⇧Tab back), as
    // Tab goes round the slide: its levels change only once the caret is put in it or
    // items are chosen there.
    let passing = tabbed && bullets;
    if (passing) {
      node.addEventListener("keydown", (event) => {
        if (!passing || ["Shift", "Meta", "Control", "Alt", "CapsLock"].includes(event.key)) return;
        if (event.key === "Tab" && !event.ctrlKey && !event.metaKey && !event.altKey) { event.preventDefault(); event.stopPropagation(); tabOn(target, event.shiftKey); return; }
        passing = false;
      }, true);
      area.addEventListener("mousedown", () => { passing = false; });
    }
    // An equation's LaTeX looks nothing like it: it is typed under the equation, which
    // stays in view and is drawn again as it changes.
    const under = target.kind === "block" && kindOf(blocksAt(slide, target.region)[target.index]) === "math";
    if (under) node.classList.add("under");
    const code = target.kind === "block" && kindOf(blocksAt(slide, target.region)[target.index]) === "code";
    const id = idOf();
    // (Typed in again, its words are the editor's, not a stand-in's.)
    placeStandIns(id);
    inline = { node, id, idOf, at, area, bullets, cell, under, code, read, session, field: target.kind === "field" ? target.field : null,
      opened: target.kind === "field" ? slide[target.field] : undefined, target, part: target.kind === "block" && OWN_LINES[kindOf(blocksAt(slide, target.region)[target.index])]?.[target.part] ? target.part : null };
    reportFocus();
    // Where the caret was left by the last letters typed here (refreshInline: a caret right
    // after its own typing keeps to it).
    area.addEventListener("input", () => { if (inline?.area === area) inline.typedAt = area.rich ? area.caretAt()?.[1] : area.selectionEnd; });
    // Code is as wide as its longest line: the box widens as a line grows.
    if (code) { area.wrap = "off"; area.addEventListener("input", () => positionInline()); }
    // The inspector shows what is typed, as it is typed.
    area.addEventListener("input", () => requestAnimationFrame(clearUnder));
    if (mirror) area.addEventListener("input", () => {
      const twin = inspectorBody.querySelector(`[data-key="${CSS.escape(mirror)}"]`);
      if (twin && twin !== document.activeElement && twin.value !== area.value) twin.value = area.value;
    });
    center.append(node);
    positionInline();
    area.focus();
    if (area.rich) {
      if (replaceWith !== null) { area.value = replaceWith; area.dispatchEvent(new Event("input")); area.caretToEnd(); }
      // Opened from the keys on purpose (Return on what is chosen, Tab onto it), all its words
      // are chosen; a double-click chooses the word under it, as a Mac text view does.
      else if (selectAll) area.selectAll();
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

  // From the words being typed (`from`: a field or an object) on to the slide's next words
  // or object (`back`: the one before), as Tab goes on the slide: title, subtitle and
  // byline, then its objects, and round again. Words open all chosen, to be typed over.
  function tabOn(from, back) {
    const slide = slideAt();
    const stops = [
      // Each line of words the slide draws, its placeholder when empty (a blank slide draws
      // no title or subtitle).
      ...["title", "words", "subtitle", "author", "date", "by"].filter((key) => catalog.slide_keys[layoutOf(slide)].includes(key)
        && !(layoutOf(slide) === "blank" && (key === "title" || key === "subtitle"))).map((field) => ({ field })),
      // Each object, its own lines in their places among its words (a callout's heading
      // before them, a quote's attribution after them).
      ...regionsOf(slide).flatMap((region) => blocksAt(slide, region.key).flatMap((block, index) => {
        const own = Object.keys(OWN_LINES[kindOf(block)] || {}).map((part) => ({ region: region.key, index, part }));
        return kindOf(block) === "callout" ? [...own, { region: region.key, index }] : [{ region: region.key, index }, ...own];
      })),
    ];
    const now = stops.findIndex((stop) => (stop.field ? stop.field === from.field
      : from.kind === "block" && stop.region === from.region && stop.index === from.index && (stop.part || null) === (from.part || null)));
    const next = stops[(now + (back ? -1 : 1) + stops.length) % stops.length];
    if (!next || next === stops[now]) return;
    if (next.field) { openInline({ kind: "field", field: next.field }, { selectAll: true }); return; }
    // Within one object (its words to its own line, or back) it is the same one being
    // written: not taken back as left empty on the way.
    const within = from.kind === "block" && next.region === from.region && next.index === from.index, was = fresh;
    if (within) fresh = null;
    closeInline();
    if (within) fresh = was;
    if (next.part) openInline({ kind: "block", ...next }, { selectAll: true });
    else if (WORDY.has(kindOf(blocksAt(slide, next.region)[next.index]))) openInline({ kind: "block", ...next }, { selectAll: true, tabbed: true });
    else { focusBlock(next.region, next.index); toured = { slide: state.slide, ...next }; }
  }
  // An object Tab came to with no words to open (a picture, code): the next Tab goes on
  // round as Tab went, opening words (see the keys), not only choosing them.
  let toured = null;

  // A new text after an object, typed in at once (a list ended by Return), as Pages goes on
  // after a list; left empty, it goes again (see closeInline).
  // (`kept`: a list ended amid its items, how many stay -- those after them a list of their
  // own after the paragraph, set as this one is.)
  function paragraphAfter(at, kept = undefined) {
    closeInline();
    let index = 0;
    editSlide((s) => {
      const list = blocksAt(s, at.region, true);
      index = Math.min(at.index + 1, list.length);
      const was = list[at.index], lines = kept !== undefined && was?.bullets ? bulletsText(was.bullets).split("\n") : [];
      let after = [];
      if (lines.length > kept) {
        const { bullets: _, ...look } = was;
        was.bullets = bulletsFrom(lines.slice(0, kept).join("\n"));
        after = [{ bullets: bulletsFrom(lines.slice(kept).join("\n")), ...structuredClone(look) }];
      }
      list.splice(index, 0, NEW_BLOCKS.text(), ...after);
    }, { label: kept !== undefined ? "Split List" : "Add Text" });
    fresh = { entry: studio.past[studio.past.length - 1], slide: state.slide, region: at.region, index };
    openInline({ kind: "block", region: at.region, index });
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
    // (Its words, or the whole cell where the editor's drawing marks it: `.cell`.)
    const cells = [...pageNode.querySelectorAll("[id]")].map((node) => ({ node, match: node.id.startsWith(`${tableId}.`) && /^(\d+)\.(\d+)(?:\.cell)?$/.exec(node.id.slice(tableId.length + 1)) }))
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
    // The cell itself, just its size, as the slide marks it for an editor (an empty one is
    // drawn as its frame), else as near as its words and its row's and column's tell.
    const frame = pageNode.querySelector(`[id="${CSS.escape(`${id}.cell`)}"]`) || pageNode.querySelector(`rect[id="${CSS.escape(id)}"]`);
    if (frame) {
      const outer = pageNode.getBoundingClientRect(), inner = frame.getBoundingClientRect();
      return { left: inner.left - outer.left, top: inner.top - outer.top, width: inner.width, height: inner.height, exact: true };
    }
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

  // The words of a cell's row (where the row's line is), but its own.
  function rowWordsOf(id) {
    const [, tableId, row, col] = /^(.*)\.(\d+)\.(\d+)$/.exec(id) || [];
    if (!tableId) return [];
    return [...pageNode.querySelectorAll("[id]")].filter((node) => node.id.startsWith(`${tableId}.${row}.`) && /^\d+$/.test(node.id.slice(`${tableId}.${row}.`.length)) && node.id !== `${tableId}.${row}.${col}`);
  }
  // Where a drawn line of words sits, on the screen: its first text's baseline.
  function baselineOf(node) {
    const text = node.matches("text") ? node : node.querySelector("text");
    const ctm = text?.getScreenCTM(), x = parseFloat(text?.getAttribute("x")) || 0, y = parseFloat(text?.getAttribute("y"));
    return ctm && Number.isFinite(y) ? ctm.b * x + ctm.d * y + ctm.f : null;
  }
  // While a cell is typed in, its table stays where it was when the typing began: words
  // that widen their column push the columns after it right, rather than move the whole
  // table about its middle at each key. It is set as the slide sets it once the cell is left.
  function holdTable() {
    const table = pageNode?.querySelector(`[id="${CSS.escape(blockId(inline.at))}"]`);
    if (!table?.getBBox) return;
    const left = table.getBBox().x;
    inline.tableLeft ??= left;
    if (Math.abs(inline.tableLeft - left) > 0.01) table.setAttribute("transform", `translate(${inline.tableLeft - left} 0)`);
    else table.removeAttribute("transform");
  }

  // An empty cell, drawn with no words, is typed in as the cells about it are set.
  function cellLook(id) {
    const [, tableId, row, col] = /^(.*)\.(\d+)\.(\d+)$/.exec(id) || [];
    // An empty header cell is typed as its hint is set ("Column 2"), else as the header's
    // other cells are; a body cell as the body's (not the header's, set bold).
    const hint = wordsLook(pageNode.querySelector(`[id="${CSS.escape(`${id}.hint`)}"]`));
    if (hint) return hint;
    for (const [r, c] of [[+row - 1, +col], [+row + 1, +col], [+row, +col - 1], [+row, +col + 1], [+row - 1, +col - 1]]) {
      const look = (+row === 0 ? r === 0 : r > 0) && wordsLook(pageNode.querySelector(`[id="${CSS.escape(`${tableId}.${r}.${c}`)}"]`));
      // Another column's cell lends its face, not its alignment (a new column beside numbers).
      if (look) return c === +col ? look : { ...look, anchor: "start" };
    }
    // Else the table's face and size, from any of its words or hints, as the body sets them.
    const any = [...pageNode.querySelectorAll(`[id^="${CSS.escape(`${tableId}.`)}"]`)].find((node) => node.matches("text") && wordsLook(node));
    return any ? { ...wordsLook(any), weight: "400", anchor: "start" } : null;
  }

  // A range of a spreadsheet's cells pasted in a cell fills the cells from that one on, the
  // table growing to take them, as in Numbers (and the inspector's table); each column keeps
  // its alignment.
  // An outline or a list pasted in words (`items`: each its depth, markup and whether it was
  // numbered): a list after them, its levels kept -- or, in an empty text, the text made it.
  function listAfter(at, items) {
    const least = Math.min(...items.map((item) => item.depth || 0));
    const list = { bullets: bulletsFrom(items.map((item) => "  ".repeat((item.depth || 0) - least) + item.markup.trim()).join("\n")) };
    if (items.filter((item) => (item.depth || 0) === least).every((item) => item.ordered)) list.numbered = true;
    const here = blocksAt(slideAt() || {}, at.region)[at.index];
    if (here && kindOf(here) === "text" && blank(here)) {
      if (fresh && fresh.region === at.region && fresh.index === at.index) fresh = null;
      editBlock(at, (b) => { for (const key of Object.keys(b)) delete b[key]; Object.assign(b, list); }, { label: "Paste List" });
      focusBlock(at.region, at.index);
    } else insertBlock("bullets", list, at, "Paste List");
  }
  function pasteCells(at, row, col, cells) {
    closeInline();
    editBlock(at, (b) => {
      // Into a table with nothing in it yet (a new one), the cells pasted set its size: no
      // empty row or column of the new table's left over.
      const empty = !tableRows(b).some((line) => line.some((value) => String(value ?? "").trim()));
      let grid = tableRows(b);
      if (empty) grid = Array.from({ length: row + cells.length }, () => Array(col + Math.max(...cells.map((line) => line.length))).fill(""));
      const align = empty ? null : alignList(b.align, grid[0].length);
      if (empty) delete b.align;
      cells.forEach((line, i) => line.forEach((value, j) => {
        while (grid.length <= row + i) grid.push(Array(grid[0].length).fill(""));
        grid.forEach((cellsOfRow) => { while (cellsOfRow.length <= col + j) cellsOfRow.push(""); });
        grid[row + i][col + j] = value;
      }));
      b.table = grid;
      if (align) { const auto = autoAlign(grid, b.header !== false); b.align = grid[0].map((_, c) => align[c] ?? auto[c]); }
    }, { label: "Paste Cells" });
    renderInspector();
    toast(`${cells.length} × ${cells[0].length} cells pasted`, { icon: "table", seconds: 2 });
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
  const fieldId = (key) => `slide${state.slide + 1}.${key === "author" || key === "date" || key === "by" ? "byline" : key === "words" ? "title" : key}`;
  const blockId = (at) => `slide${state.slide + 1}.${regionsOf(slideAt()).find((r) => r.key === at.region)?.svg}.${at.index}`;

  // Where each of `before`'s items is in `after` (-1 if it is gone): the items that are
  // the same, in the same order, first; then an item changed in place is the changed
  // one between the same neighbours -- the one that looks like it (`like`), else the
  // one in its turn.
  // Where each of `before` is in `after`, by what it holds: kept, moved, or changed (and
  // moved and changed at once, as a paragraph another person moved while it was typed in).
  function follow(before, after) {
    return follows(before, after);
  }


  // After an edit from elsewhere (another person, an agent, the file on disk) or an undo,
  // the slide shown, the object selected and the text being typed are found where they
  // now are, by what they hold -- not left at a place that now holds something else.
  // What the editor open here is typing in, taken away by another's change (`remote`), is
  // kept, as their presence on it says it is being edited: put back as it is typed here (one
  // with the typing), and said -- the one who deleted it is told it is back -- or, made
  // another kind meanwhile (a paragraph a list), typed on in that. Answers whether it was.
  function keepTyped(before, after, from, to) {
    const at = inline.at, typed = blocksAt(before[from], at.region)[at.index];
    if (!typed || to < 0) return false;
    const now = blocksAt(after[to], at.region), kind = "text" in typed ? "text" : "bullets" in typed ? "bullets" : null;
    const into = kind && linesOf(typed) ? [at.index, at.index - 1, at.index + 1].find((n) => now[n] && !(kind in now[n]) && linesOf(now[n]) && alikeLines(linesOf(now[n]), linesOf(typed)) >= 0.5) : undefined;
    if (into !== undefined) {
      // Its typing goes on, one step with what was typed before (one row in the history).
      const caret = inline.area.rich ? inline.area.caretAt()?.[1] : null, run = inline.session, going = studio.lastMerge;
      closeInline({ going: true });
      openInline({ kind: "block", region: at.region, index: into }, { run });
      if (going) studio.lastMerge = { key: `${state.slide}-${at.region}-${into}-inline-${run}`, at: Date.now() };
      if (inline?.area.rich && caret !== null && caret !== undefined) inline.area.caretTo(Math.min(caret, inline.area.letters().length));
      return true;
    }
    // Moved meanwhile, not taken away (to another column of the slide): typed on where it went.
    for (const region of regionsOf(after[to])) {
      if (region.key === at.region) continue;
      const found = follows([typed], blocksAt(after[to], region.key))[0];
      if (found >= 0) { at.region = region.key; at.index = found; return true; }
    }
    const index = Math.min(at.index, now.length);
    studio.change((d) => { blocksAt(d.slides[to], at.region, true).splice(index, 0, structuredClone(typed)); }, { quiet: true, merge: studio.lastMerge?.key ?? null, hold: true });
    at.index = index;
    return named(typed, { the: true });
  }

  function followChange(was, who, remote = false) {
    const before = Array.isArray(was?.slides) ? was.slides : [], after = slides();
    if (before === after || !before.length) return;
    // A deleting undone here is no longer one that someone else's typing could bring back.
    if (!remote) {
      deletedHere = deletedHere.filter((gone) => studio.past.includes(gone.entry));
      objectsDeleted = objectsDeleted.filter((gone) => studio.past.includes(gone.entry));
    }
    // A slide deleted here a moment ago, back because someone was still editing it: said,
    // so it does not seem to have come back of itself.
    if (remote && after.length > before.length && deletedHere.length) {
      // Known by what it holds, as it was deleted -- changed since, by whoever kept typing in it.
      const come = after.filter((slide) => !before.some((other) => same(other, slide)));
      for (const gone of deletedHere.filter((item) => Date.now() - item.at < 60000)) {
        const back = come[follows([gone.slide], come)[0]];
        if (!back) continue;
        toast(`Slide ${after.indexOf(back) + 1} is back: ${nameOf(who)} was still editing it.`, { icon: "info", seconds: 6 });
        // Its deleting came to nothing, so it leaves the history: undone, it would bring
        // back a second copy beside the one that came back.
        const at = studio.past.indexOf(gone.entry);
        if (at >= 0) { studio.past.splice(at, 1); studio.emit("status"); }
        deletedHere = deletedHere.filter((item) => item !== gone);
        come.splice(come.indexOf(back), 1);
      }
    }
    // So too an object deleted here a moment ago, on whichever slide it comes back.
    objectsDeleted = objectsDeleted.filter((item) => Date.now() - item.at < 60000);
    if (remote && objectsDeleted.length) {
      // The objects come that no object of the slide before became (not one edited).
      const slideFrom = follow(before, after);
      const come = after.flatMap((slide, index) => {
        const was = before[slideFrom.indexOf(index)];
        const old = was ? partsOf(was).map((item) => item.block) : [], now = partsOf(slide).map((item) => item.block);
        const became = new Set(follows(old, now));
        return now.filter((_, k) => !became.has(k));
      });
      for (const gone of [...objectsDeleted]) {
        const back = come[follows([gone.block], come)[0]];
        if (!back) continue;
        // (Named by its words as they now are, not as they were when it was deleted.)
        toast(`${named(back)} is back: ${nameOf(who)} was still editing it.`, { icon: "info", seconds: 6 });
        const at = studio.past.indexOf(gone.entry);
        if (at >= 0) { studio.past.splice(at, 1); studio.emit("status"); }
        objectsDeleted = objectsDeleted.filter((item) => item !== gone);
        come.splice(come.indexOf(back), 1);
      }
    }
    const from = state.slide;
    // (Known first as the very slide it was, which the merge keeps as it is here when no one
    // else changed it: two slides alike -- one added here, one by another at the same place at
    // once -- are not taken one for the other.)
    const own = from < before.length ? after.indexOf(before[from]) : -1;
    const to = own >= 0 ? own : from < before.length ? follow(before, after)[from] : from;
    // (An undo or a redo here takes it away without a word: no one else deleted it.)
    const gone = () => { closeInline(); if (remote) toast(`${nameOf(who)} deleted the text you were editing`, { icon: "info", seconds: 5 }); };
    const kept = (what) => toast(`${nameOf(who)} deleted ${editedHere(what)}. It stays.`, { icon: "info", seconds: 6 });
    if (to < 0 && inline && remote && before[from]) {
      // The slide typed in, deleted by another: kept, as it is here, and said.
      studio.change((d) => { (d.slides ||= []).splice(Math.min(from, d.slides.length), 0, structuredClone(before[from])); }, { quiet: true, merge: studio.lastMerge?.key ?? null, hold: true });
      state.slide = Math.min(from, slides().length - 1);
      kept("the slide");
      return;
    }
    if (to < 0) {
      if (inline) gone();
      // The slide shown, deleted by another: said, not left to seem a jump of its own.
      else if (remote) toast(`${nameOf(who)} deleted slide ${from + 1}, which you were viewing.`, { icon: "info", seconds: 5 });
      state.focus = null; state.field = null;
      state.slide = Math.min(from, Math.max(0, after.length - 1));
      return;
    }
    state.slide = to;
    const place = (at) => {
      const map = follow(blocksAt(before[from], at.region), blocksAt(after[to], at.region));
      return map[at.index] ?? -1;
    };
    // The selection and the editor's block may be one object: each is placed from where it was.
    const focusTo = state.focus ? place(state.focus) : -1, inlineTo = inline?.at ? place(inline.at) : -1;
    const shared = inline?.at && inline.at === state.focus;
    let typedTo = inlineTo, retype = null;
    if (inline?.at && inlineTo < 0) {
      // Put on another slide meanwhile, with the words typed here (an agent moving it there,
      // the merges following it): the typing here ends, and that is said -- no copy kept here.
      const went = remote ? wentTo(before, after, from, to, inline.at) : null;
      const label = !went && remote && keepTyped(before, after, from, to);
      // Undone or redone here, the words typed in made another kind where they were (a list
      // back to the "- " that made it): typed on in, as that kind, from their end.
      const there = !remote && !inline.cell && blocksAt(before[from], inline.at.region).length === blocksAt(after[to], inline.at.region).length
        ? blocksAt(after[to], inline.at.region)[inline.at.index] : null;
      if (went) { closeInline(); toast(`${nameOf(who)} moved ${editedHere(went.what)} to slide ${went.slide + 1}.`, { icon: "info", seconds: 6 }); }
      else if (typeof label === "string") { kept(label); typedTo = inline.at.index; }
      else if (!label && there && INLINE.has(kindOf(there))) { retype = { ...inline.at }; typedTo = inline.at.index; }
      else if (!label) gone();
      else typedTo = inline?.at?.index ?? -1;
    } else if (inline?.at) inline.at.index = inlineTo;
    if (state.focus && !shared) { if (focusTo < 0) state.focus = null; else state.focus.index = focusTo; }
    else if (shared && typedTo < 0) state.focus = null;
    else if (shared && inline?.at) state.focus = inline.at;
    if (state.field) state.field.id = fieldId(state.field.field);
    if (inline) inline.id = inline.idOf();
    if (retype) { closeInline(); openInline({ kind: "block", ...retype }); }
  }

  // The slide (of `after`, other than `to`, where the slide `from` went) another's change put
  // the object at `at` on, with what it is named: null if it went to none. (Of objects new on
  // a slide, the one it became, as merges know it.)
  function wentTo(before, after, from, to, at) {
    const typed = blocksAt(before[from], at.region)[at.index];
    if (!typed) return null;
    const back = follow(before, after);
    const come = after.flatMap((slide, n) => {
      if (n === to) return [];
      const was = before[back.indexOf(n)], olds = was ? partsOf(was).map((part) => part.block) : [];
      return partsOf(slide).filter((part) => !olds.some((old) => same(old, part.block))).map((part) => ({ slide: n, block: part.block }));
    });
    const found = come[follows([typed], come.map((part) => part.block))[0]];
    return found ? { slide: found.slide, what: named(found.block, { the: true }) } : null;
  }

  // After an undo or a redo, the object it changed is chosen, as Keynote does: the first
  // on the slide shown that is not as it was.
  function chooseChanged(was, entry) {
    // Several chosen together and changed so (deleted, moved, pasted): undone or redone, they
    // are chosen again where they now are -- none when they are gone.
    if (entry?.many) {
      const undone = studio.future[studio.future.length - 1]?.said === entry;
      const picks = (undone ? entry.many.before : entry.many.after) || [];
      if (entry.many.slide !== state.slide && entry.many.slide < slides().length) select(entry.many.slide);
      state.focus = null; state.field = null;
      allChosen = null;
      if (picks.length === 1) focusBlock(picks[0].region, picks[0].index);
      else chooseMany(picks.filter((pick) => blocksAt(slideAt() || {}, pick.region)[pick.index]));
      return;
    }
    const before = was?.slides || [], after = slides();
    if (before.length !== after.length) { state.focus = null; return; }
    // A move undone or redone: what moved is chosen, where it now is.
    if (entry?.moved) {
      const undone = studio.future[studio.future.length - 1]?.said === entry;
      const { slide, from, to } = entry.moved;
      if (slide === undefined) { select(undone ? from : to); state.focus = null; return; }
      if (slide !== state.slide) select(slide);
      const at = undone ? from : to;
      if (blocksAt(slideAt(), at.region)[at.index]) { focusBlock(at.region, at.index); return; }
    }
    // A slide moved: the slide that moved is shown.
    const movedSlide = movedIn(before, after);
    if (movedSlide >= 0) { if (movedSlide !== state.slide) select(movedSlide); state.focus = null; return; }
    const old = partsOf(before[state.slide] || {}), now = partsOf(after[state.slide] || {});
    // An object moved: the one that moved; else the first changed.
    const moved = old.length === now.length ? movedIn(old.map((item) => item.block), now.map((item) => item.block)) : -1;
    const changed = moved >= 0 ? now[moved] : now.find((item, k) => !old[k] || item.region !== old[k].region || !same(item.block, old[k].block));
    if (!changed) {
      // Words of the slide's own (its title, its author): that field.
      const field = SLIDE_WORDS.map(([key]) => key).find((key) => !same(before[state.slide]?.[key], after[state.slide]?.[key]));
      if (field) { state.focus = null; state.field = { field, id: fieldId(field) }; placeChosen(); return; }
      if (state.focus && !blocksAt(slideAt(), state.focus.region)[state.focus.index]) state.focus = null;
      return;
    }
    // A figure's shapes come back (or change): those shapes are chosen in it.
    const shapes = (block) => (block && typeof block.figure === "object" ? block.figure.nodes || [] : []);
    const prior = old.find((item) => item.region === changed.region && item.index === changed.index)?.block;
    const back = shapes(changed.block).filter((node) => !shapes(prior).some((other) => same(other, node))).map((node) => node.id).filter(Boolean);
    const chosen = state.focus?.region === changed.region && state.focus?.index === changed.index;
    if (back.length && kindOf(changed.block) === "figure") focusBlock(changed.region, changed.index, () => figure?.parts.select(back));
    else if (!chosen) focusBlock(changed.region, changed.index);
  }
  // Where the one item that moved now is, when `after` is `before` with one item moved
  // (else -1).
  function movedIn(before, after) {
    const differ = after.map((_, k) => k).filter((k) => !same(before[k], after[k]));
    if (differ.length < 2) return -1;
    const low = differ[0], high = differ[differ.length - 1];
    const up = same(after[low], before[high]) && after.slice(low + 1, high + 1).every((item, k) => same(item, before[low + k]));
    if (up) return low;
    const down = same(after[high], before[low]) && after.slice(low, high).every((item, k) => same(item, before[low + 1 + k]));
    return down ? high : -1;
  }

  // Others' words merged with words typed here (not yet sent, or sent and answered with
  // theirs): the caret goes through the same merge (`change`'s `base` and `incoming`), as a
  // mark at the end of the letters typed here, so it stays after them wherever the merge put
  // them -- never in among another's. A space typed here that the merge took for another's
  // (both started a word at one place) is put back, so the two words stay apart. Answers
  // whether it was so.
  const CARET = "\ue07f";
  function caretMerged(value, { merged = false, base = null, incoming = null } = {}) {
    const area = inline.area;
    const was = merged && base && incoming ? [inline.read(base), inline.read(incoming)] : [];
    const chosen = getSelection();
    if (typeof was[0] !== "string" || typeof was[1] !== "string" || !chosen.rangeCount || !area.contains(chosen.anchorNode)) return false;
    const mark = document.createTextNode(CARET);
    chosen.getRangeAt(0).insertNode(mark);
    const local = area.value;
    mark.remove();
    area.normalize();
    // The caret, typing on where another's words came in at the same place, stays by the
    // letters typed here, before theirs -- as merged with this page's words first there, when
    // the words come out the same.
    const first = merge3(was[0], local, was[1]), plainFirst = first.replace(CARET, "");
    const out = plainFirst === value ? first : merge3(was[0], was[1], local), plain = out.replace(CARET, "");
    const putBack = plain !== value && plain.replace(/\s+/g, "") === value.replace(/\s+/g, "");
    if (out.split(CARET).length !== 2 || (plain !== value && !putBack)) return false;
    area.value = out;
    const walker = document.createTreeWalker(area, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const at = node.data.indexOf(CARET);
      if (at < 0) continue;
      node.deleteData(at, 1);
      const range = document.createRange();
      range.setStart(node, at);
      chosen.removeAllRanges();
      chosen.addRange(range);
      break;
    }
    if (putBack) area.dispatchEvent(new CustomEvent("input", { bubbles: true, detail: { tidy: true } }));
    return true;
  }

  // After an undo or an edit from elsewhere, the editor open on the slide shows the words
  // as they now are -- typing on from what was undone would bring it back.
  // Undone or redone (`history`), the caret goes to the end of what changed -- after the
  // words put back -- as in TextEdit.
  function refreshInline(history = false, change = {}) {
    if (!inline?.read) return;
    const value = inline.read();
    if (value === undefined) { closeInline(); return; }
    // Words changed under the caret (another person's, the file's, an undo): the caret
    // stays by the words it was by -- after the letters typed here, when it was left by them.
    const area = inline.area, rich = area.rich, focused = document.activeElement === area;
    const caret = rich ? area.caretAt() : [area.selectionStart, area.selectionEnd];
    const own = Boolean(caret) && caret[0] === caret[1] && caret[1] === inline.typedAt;
    // (Unchanged here, a merge may still have taken a space typed here for another's: put back.)
    if (value === area.value && !(change.merged && !history && focused && own && rich)) return;
    if (!history && focused && own && rich && caretMerged(value, change)) {
      inline.typedAt = area.caretAt()?.[1];
      positionInline();
      return;
    }
    const was = rich ? area.letters() : area.value;
    area.value = value;
    const now = rich ? area.letters() : value;
    if (!rich) { area.style.height = "auto"; area.style.height = `${area.scrollHeight + 2}px`; }
    if (focused && caret) {
      // (A change of look alone -- bold undone -- leaves the letters and the words chosen as they were.)
      // Undone or redone, words put back are chosen, as TextEdit chooses them; else the caret
      // is where words were taken away.
      const [ahead, behind] = changeIn(was, now), [from, to] = [ahead, was.length - behind];
      let [start, end] = history && was !== now ? [ahead, now.length - behind] : caret.map((at) => caretThrough(was, now, at, !own));
      // Words chosen here that another replaced -- and typed on in, a letter at a time, as
      // they replace them -- are chosen as they now are, not a stale length of them.
      const following = inline.chose?.[0] === caret[0] && inline.chose?.[1] === caret[1];
      inline.chose = null;
      if (!history && caret[0] !== caret[1] && ((from === caret[0] && to === caret[1]) || (following && from >= caret[0] && to <= caret[1]))) {
        [start, end] = [caret[0], caret[1] + now.length - was.length];
        inline.chose = [start, end];
      }
      if (rich) area.caretTo(start, end); else area.setSelectionRange(start, end);
      if (own) inline.typedAt = end;
    // (Its format bar or link field has the keys: the words they act on stay theirs.)
    } else if (rich && !area.holding?.()) area.caretToEnd();
    positionInline();
  }
  // Where words changed from `was` to `now`: how many letters are alike before the change,
  // and how many after it.
  function changeIn(was, now) {
    let start = 0;
    while (start < was.length && start < now.length && was[start] === now[start]) start++;
    let end = 0;
    while (end < was.length - start && end < now.length - start && was[was.length - 1 - end] === now[now.length - 1 - end]) end++;
    return [start, end];
  }
  // Where a caret at `at` goes when words change from `was` to `now`: before the change,
  // it stays; after it, it moves with the words; inside it, to the change's end. Letters put
  // in where they could be on either side of it (alike letters about it) go before a caret
  // with no typing of its own there (`fresh`), after one typing on there.
  function caretThrough(was, now, at, fresh = false) {
    const [start, end] = changeIn(was, now);
    if (fresh && now.length > was.length && start + end === was.length) {
      let tail = 0;
      while (tail < was.length && was[was.length - 1 - tail] === now[now.length - 1 - tail]) tail += 1;
      if (at >= was.length - tail && at <= start) return at + now.length - was.length;
    }
    if (at <= start) return at;
    if (at >= was.length - end) return at + now.length - was.length;
    return now.length - end;
  }

  // Words are typed where they are on the slide, as they look there: the editor lies
  // over them in their face, size and colour, and the drawn words step aside while it
  // is open. It stays put (keeping its caret) when the slide is drawn again under it.
  // A list's own numbers (its marks, drawn as words in their own colour) are not its words.
  const wordsIn = (element) => (element.matches("text") ? [element] : [...element.querySelectorAll("text")].filter((text) => !text.id.endsWith(".mark")));
  function wordsLook(element) {
    const text = element ? wordsIn(element)[0] : null;
    if (!text) return null;
    const style = getComputedStyle(text);
    const scale = text.getScreenCTM()?.a || 1;
    const first = text.getBoundingClientRect();
    // Words all in a face of their own (code, in the monospace) are typed in it.
    const spans = [...text.querySelectorAll("tspan")].filter((span) => [...span.childNodes].some((node) => node.nodeType === Node.TEXT_NODE && node.data.trim()));
    const faces = new Set(spans.map((span) => getComputedStyle(span).fontFamily));
    return { size: parseFloat(style.fontSize) * scale, family: faces.size === 1 ? [...faces][0] : style.fontFamily, weight: style.fontWeight,
      colour: style.fill && style.fill !== "none" ? style.fill : "", anchor: text.getAttribute("text-anchor") || style.textAnchor || "start", left: first.left };
  }
  function positionInline() {
    if (!inline || !pageNode?.isConnected) return;
    const outer = center.getBoundingClientRect();
    const slide = pageNode.getBoundingClientRect();
    const element = pageNode.querySelector(`[id="${CSS.escape(inline.id)}"]`);
    // A line of words not drawn yet (a subtitle just put there, before the slide is drawn
    // again with its placeholder) is typed where it will be: under the words above it.
    const guess = element ? null : inline.field ? belowField(inline.field) : inline.part ? ownLine(inline.at, inline.part) : inline.at && !inline.cell ? belowBlock(inline.at) : null;
    const box = boxOf(inline.id) || guess?.box || null;
    const look = wordsLook(element) || inline.look || guess?.look || (inline.cell ? cellLook(inline.id) : null);
    if (look && !guess) inline.look = look;
    if (inline.under) {
      chosen.hidden = true;
      hover.hidden = true;
      // On the slide's own paper and ink, as the slide's other in-place editors are (not the
      // window's, a dark panel on a white slide in dark mode).
      const paper = pageNode?.querySelector('[id="canvas.background"]')?.getAttribute("fill");
      if (paper) inline.node.style.setProperty("--under-paper", paper);
      // The ink the slide draws the equation in: light on a dark background colour.
      const ink = element?.getAttribute("fill") || studio.info?.palette?.ink;
      if (ink) inline.node.style.setProperty("--under-ink", ink);
      // An equation not yet written: its hint is in the field (its placeholder), not drawn
      // faintly over it as well.
      const hint = element?.hasAttribute("data-flexo-placeholder") ? element : null;
      if (inline.hidden !== hint) { inline.hidden?.style.removeProperty("visibility"); if (hint) hint.style.visibility = "hidden"; inline.hidden = hint; }
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
      holdTable();
      // The hint drawn in an empty header cell is the field's own placeholder while it is typed in.
      const hint = pageNode.querySelector(`[id="${CSS.escape(`${inline.id}.hint`)}"]`);
      if (inline.hint !== hint) { inline.hint?.style.removeProperty("visibility"); if (hint) hint.style.visibility = "hidden"; inline.hint = hint; }
      const box = cellBox(inline.id);
      if (!box) return;
      const right = look?.anchor === "end";
      // Typed in a frame just the cell's size, its words where the slide sets them (its
      // padding, its row's line); words outgrowing it grow it to the right, as the column
      // will grow when the slide is drawn again.
      const pad = box.exact ? size * 0.6 : 5;
      // Its letters on the drawn ones' baseline: the row's line as the slide sets it, less the
      // room the editor's line gives over its letters (its half-leading and the face's ascent).
      const words = [element, hint, ...rowWordsOf(inline.id)].find((node) => node?.matches?.("text, g") && node.getBoundingClientRect().height);
      const baseline = words && baselineOf(words);
      inkPen.font = `${look?.weight || 400} ${size}px ${look?.family || "sans-serif"}`;
      const face = inkPen.measureText("Hg"), ascent = face.fontBoundingBoxAscent, line = size * 1.22;
      const inset = !box.exact ? 0 : baseline != null
        ? baseline - (pageNode.getBoundingClientRect().top + box.top) - (line - ascent - face.fontBoundingBoxDescent) / 2 - ascent
        : (box.height - line) / 2;
      Object.assign(inline.node.style, { left: `${slide.left - outer.left + box.left}px`, top: `${slide.top - outer.top + box.top}px`, width: "",
        minWidth: `${box.width}px`, maxWidth: `${Math.max(box.width, slide.width - box.left - 8)}px`, minHeight: `${box.height}px` });
      Object.assign(inline.area.style, { fontSize: `${size}px`, fontFamily: look?.family || "", fontWeight: look?.weight || "", color: look?.colour || "",
        textAlign: right ? "right" : look?.anchor === "middle" ? "center" : "left", padding: `${Math.max(0, inset)}px ${pad}px 0` });
      return;
    }
    const centred = look?.anchor === "middle";
    const room = wordsRoom(element, box, look, Boolean(inline.area.rich));
    const width = room.width, left = slide.left - outer.left + room.left;
    let top = slide.top - outer.top + (box ? box.top : 60);
    const rich = inline.area.rich;
    const indent = inline.bullets && look && box && !rich ? Math.max(0, look.left - slide.left - box.left - 5) : 0;
    // The rich editor's lines lie on the drawn lines: the same line spacing, the first
    // line's letters where the drawn ones are, and a list's bullets where they are drawn.
    const metrics = rich && element ? textMetrics(element, size) : null;
    // Lines evened out on the slide are evened out here (CSS's balance is flexo's: the
    // narrowest width that takes no more lines).
    inline.area.style.textWrap = room.wrapping.includes("balance") ? "balance" : "";
    if (metrics) {
      top = metrics.top - outer.top - (metrics.line - metrics.height) / 2 - 5;
      inline.area.style.setProperty("--rt-line", `${metrics.line}px`);
      if (inline.bullets) for (const [name, value] of Object.entries(listLook(element, metrics, slide.left + box.left + 5))) inline.area.style.setProperty(name, value);
    }
    // A line of words typed under another (a subtitle under its title) keeps its frame clear
    // of the letters over it, their descenders: the room over its words is taken in.
    let over = 5;
    for (const name of { subtitle: ["title"], author: ["subtitle", "title"], date: ["subtitle", "title"], by: ["words"] }[inline.field] || []) {
      const ink = inkOf(fieldId(name));
      if (!ink) continue;
      over = Math.max(0, Math.min(5, 5 - (ink.bottom + 3.5 - (outer.top + top))));
      break;
    }
    top += 5 - over;
    Object.assign(inline.node.style, { left: `${left}px`, top: `${Math.max(8, top)}px`, width: `${width}px`, minHeight: box ? `${Math.max(0, box.height - (5 - over))}px` : "" });
    Object.assign(inline.area.style, { fontSize: `${size}px`, fontFamily: look?.family || "", fontWeight: look?.weight || "",
      color: look?.colour || "", textAlign: centred ? "center" : "left", paddingLeft: rich ? "" : `${5 + indent}px`, paddingTop: over < 5 ? `${over}px` : "" });
    // Words set bold (a title, a statement) show their own bold words as the slide draws
    // them: in the accent (the ink, words in the accent), not bolder.
    const strong = element?.getAttribute("data-flexo-strong") || (Number(look?.weight) >= 600 ? studio.info?.palette?.accent : "");
    inline.area.classList.toggle("rt-heavy", Boolean(strong));
    if (strong) { inline.area.style.setProperty("--rt-strong", strong); inline.area.style.setProperty("--rt-plain", look?.colour || "inherit"); }
    bylinePart(look, size, centred);
    codeOnLines(element, box, slide);
    clearUnder();
  }
  // Code is typed on its lines as the slide draws them: on its panel (left in view), its
  // letters where the drawn ones are, line for line, so nothing moves when it is done.
  function codeOnLines(element, box, slide) {
    if (!inline.code || !element || !box) return;
    const panel = element.querySelector('[id$=".panel"]');
    if (panel) panel.style.visibility = "visible";
    const texts = wordsIn(element).filter((text) => text.getBoundingClientRect().height);
    if (!texts.length) return;
    const first = texts[0].getBoundingClientRect(), ctm = texts[0].getScreenCTM();
    const x = ctm ? parseFloat(texts[0].getAttribute("x")) * ctm.a + ctm.e : first.left;
    const pitch = texts.length > 1 ? texts[1].getBoundingClientRect().top - first.top : first.height * 1.2;
    const area = inline.area;
    // Never narrower than it was while it is typed in: a panel drawn round fewer letters (an
    // empty one's, as wide as its place, typed into) leaves the frame where it was.
    inline.codeWidth = Math.max(inline.codeWidth || 0, box.width);
    inline.node.style.width = `${inline.codeWidth}px`;
    const holder = inline.node.getBoundingClientRect();
    Object.assign(area.style, { lineHeight: `${pitch}px`, paddingLeft: `${x - holder.left}px`, paddingTop: `${first.top - (pitch - first.height) / 2 - holder.top}px` });
    // A line longer than the panel widens the box, to the slide's edge at most.
    if (area.scrollWidth > area.clientWidth) inline.node.style.width = `${Math.min(area.scrollWidth + 6, slide.right - holder.left - 12)}px`;
  }
  // A title slide's author and date are drawn as one line, its byline: the one not being
  // typed stays in view beside the one that is, where the slide draws it. (A statement's
  // attribution is drawn after a dash, which stays too.)
  function bylinePart(look, size, centred) {
    const key = inline.field;
    const node = inline.node;
    if (key !== "author" && key !== "date" && key !== "by") return;
    const slide = slideAt() || {};
    const other = key === "by" ? "" : plain(slide[key === "author" ? "date" : "author"] ?? "").trim();
    // A dash, not a middle dot, in a right-to-left byline (deck.py's title).
    const between = /[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]/.test(`${slide.author ?? ""}${slide.date ?? ""}`) ? " \u2013 " : " \u00b7 ";
    node.classList.add("byline-part");
    node.dataset.before = key === "by" ? "\u2014 " : key === "date" && other ? `${other}${between}` : "";
    node.dataset.after = key === "author" && other ? `${between}${other}` : "";
    // Empty, as wide as its placeholder ("Date"), which it shows.
    inkPen.font = `${look?.weight || 400} ${size}px ${look?.family || "sans-serif"}`;
    inline.area.style.minWidth = `${Math.ceil(inkPen.measureText(inline.area.dataset.placeholder || "").width) + 10}px`;
    Object.assign(node.style, { fontSize: `${size}px`, fontFamily: look?.family || "", fontWeight: look?.weight || "", color: look?.colour || "",
      justifyContent: centred ? "center" : look?.anchor === "end" ? "flex-end" : "flex-start" });
  }
  // Where an object not yet drawn (a text just added) will be: under the one before it, in
  // its words' look.
  function belowBlock(at) {
    if (!at.index) return null;
    const id = blockId({ region: at.region, index: at.index - 1 });
    const box = boxOf(id), look = wordsLook(pageNode?.querySelector(`[id="${CSS.escape(id)}"]`));
    if (!box || !look) return null;
    return { box: { left: box.left, top: box.top + box.height - 5 + look.size * 0.5, width: box.width, height: look.size * 1.25 + 10 }, look: { ...look, weight: "400" } };
  }
  // Where an object's own line not yet written will be, and its look: a quote's attribution
  // under its words, smaller; a callout's heading where its words start.
  function ownLine(at, part) {
    const id = `${blockId(at)}.words`;
    const box = boxOf(id), look = wordsLook(pageNode?.querySelector(`[id="${CSS.escape(id)}"]`));
    if (!box || !look) return null;
    if (part === "by") {
      const size = look.size * 0.62;
      return { box: { left: box.left, top: box.top + box.height + look.size * 0.2, width: box.width, height: size * 1.25 + 10 }, look: { ...look, size, weight: "400" } };
    }
    return { box: { left: box.left, top: box.top, width: box.width, height: look.size * 1.25 + 10 }, look: { ...look, weight: "600" } };
  }
  // Where a line of words not yet drawn will be, and its look: under the line above it
  // (a subtitle under the title, a byline under the subtitle), a little smaller.
  function belowField(key) {
    const above = { subtitle: ["title"], author: ["subtitle", "title"], date: ["subtitle", "title"], by: ["words"] }[key] || [];
    for (const name of above) {
      const id = fieldId(name);
      const look = wordsLook(pageNode?.querySelector(`[id="${CSS.escape(id)}"]`));
      const box = boxOf(id);
      if (!look || !box) continue;
      const titles = Number(deckStyle("title_size")) || 32, subtitles = Number(deckStyle("subtitle_size")) || 18;
      const size = look.size * (name === "subtitle" ? 0.9 : subtitles / titles);
      return { box: { left: box.left, top: box.top + box.height - 2, width: box.width, height: size * 1.25 + 10 },
        look: { ...look, size, weight: "400" } };
    }
    return null;
  }
  // Words typed that grow past their place (a title onto a second line) would lie over
  // what is drawn under them until the slide is drawn again round them: what they cover
  // steps aside meanwhile, as the words being edited do.
  let underneath = [];
  function clearUnder() {
    for (const node of underneath) node.style.removeProperty("visibility");
    underneath = [];
    if (!inline || !pageNode) return;
    const editing = inline.node.getBoundingClientRect();
    for (const node of pageNode.querySelectorAll("[id]")) {
      if (node.id === inline.id || !(WORDS.test(node.id) || BLOCK_ID.test(node.id))) continue;
      const box = node.getBoundingClientRect();
      if (!box.width || box.right <= editing.left || box.left >= editing.right) continue;
      // Covered, not grazed by the editor's margin.
      if (Math.min(box.bottom, editing.bottom) - Math.max(box.top, editing.top) < box.height * 0.3) continue;
      node.style.visibility = "hidden";
      underneath.push(node);
    }
  }

  // The room words have on the slide, left to right (in page pixels, as boxOf gives boxes):
  // as wide as the slide lets them run before they wrap (their data-flexo-wrap), give or
  // take a little for letters set a hair wider, centred words about their middle -- else to
  // the slide's margin, both sides for centred words, and not past the column beside them.
  // Words are framed this wide however they are shown -- pointed at, chosen, typed in, or
  // chosen by another -- so their frame is not tight round them in one and wide in the next.
  function wordsRoom(element, box, look = wordsLook(element), rich = true) {
    const slide = pageNode.getBoundingClientRect();
    const centred = look?.anchor === "middle", size = look?.size || 16;
    const wrapping = (box && element?.getAttribute("data-flexo-wrap")) || "";
    const wraps = (parseFloat(wrapping) || 0) * (element?.getScreenCTM?.()?.a || 0);
    if (wraps) {
      const width = wraps + 10 + size * 0.3;
      return { width, wrapping, left: centred ? box.left + box.width / 2 - width / 2 : look?.anchor === "end" ? box.left + box.width - width + 10 : box.left };
    }
    const margin = box ? Math.max(12, centred ? Math.min(box.left, slide.width - box.left - box.width) : box.left) : 40;
    let width = box ? (centred ? slide.width - 2 * margin : Math.max(box.width, slide.width - box.left - margin)) : 420;
    const beside = box && !centred ? columnBeside(box) : null;
    if (beside !== null) width = Math.max(box.width, Math.min(width, beside - box.left - 8));
    // Words the slide wrapped wrap where it wrapped them: at their longest line, give or take a letter.
    if (rich && box && !centred && element && textMetrics(element, size)?.wrapped) width = Math.min(width, box.width + size * 0.6);
    return { width, wrapping, left: box ? (centred ? margin : box.left) : 40 };
  }
  // The frame round a part of the slide -- a line of its words, or an object -- pointed at,
  // chosen, or chosen by another.
  function frameOf(part) {
    if (part.kind === "field") return roomy(part.id, wordsFrame(part.id));
    const block = blocksAt(slideAt() || {}, part.region)[part.index];
    const kind = block ? kindOf(block) : "", framed = roomy(part.id, boxOf(part.id), kind);
    // Words, or drawn to its edges (an equation's glyphs, a table's rules), it has the room
    // round it a line of the slide's words has (wordsFrame): its frame never touches them.
    return framed && (INKED.has(kind) || WIDE.has(kind)) ? { left: framed.left - 3, top: framed.top - 3, width: framed.width + 6, height: framed.height + 6 } : framed;
  }
  const INKED = new Set(["math", "table", "stats"]);
  // A frame round words (a line of the slide's, a text, a list, a quote) as wide as their
  // room; round anything else, as it is.
  const WIDE = new Set(["text", "bullets", "quote"]);
  function roomy(id, frame, kind = "words") {
    const element = pageNode?.querySelector(`[id="${CSS.escape(id)}"]`);
    if (!frame || !element || !(kind === "words" || WIDE.has(kind))) return frame;
    const room = wordsRoom(element, boxOf(id) || frame);
    return { ...frame, left: room.left, width: room.width };
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
    const texts = wordsIn(element);
    if (!texts.length) return null;
    const first = (texts[0].querySelector("tspan") || texts[0]).getBoundingClientRect();
    let line = 0, wrapped = false;
    for (const text of texts) {
      const tops = lineTops(text, first.height || size);
      if (tops.length > 1) { line ||= tops[1] - tops[0]; wrapped = true; }
    }
    return { top: first.top, height: first.height, line: line || first.height * 1.05 || size * 1.22, wrapped, texts };
  }
  // The tops of a text's lines: its runs' tops, those within half a line of each other one
  // line (code, in its own face, or a bold word sits a hair higher or lower on the same line).
  function lineTops(text, height) {
    const tops = [...text.querySelectorAll("tspan")].map((span) => span.getBoundingClientRect()).filter((box) => box.width).map((box) => box.top).sort((a, b) => a - b);
    return tops.filter((top, k) => !k || top - tops[k - 1] > height / 2);
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
    // Numbers stand where the slide sets them (deck.py's ListLayout): the first level's at
    // the list's edge, the second's where the first's words start, each deeper one an indent
    // on; and each item's words after the room its level's numbers take.
    if (marked.some((item) => item.mark.matches("text"))) {
      const leftOf = (item) => item.mark.getBoundingClientRect().left;
      const places = [];
      for (const at of marked.map(leftOf).sort((a, b) => a - b)) if (!places.length || at - places[places.length - 1] > 1.5) places.push(at);
      const [zero, one, two] = [0, 1, 2].map((level) => marked.find((item) => Math.abs(leftOf(item) - places[level]) <= 1.5));
      Object.assign(look, { "--rt-num-x": `${leftOf(zero) - origin}px`, "--rt-num-right": "auto", "--rt-text": `${zero.box.left - origin}px`, "--rt-mark": zero.mark.getAttribute("fill") || "currentColor" });
      if (one) Object.assign(look, { "--rt-num1-x": `${leftOf(one) - origin}px`, "--rt-text1": `${one.box.left - origin}px`, "--rt-mark2": one.mark.getAttribute("fill") || "currentColor" });
      if (one && two) look["--rt-step"] = `${leftOf(two) - leftOf(one)}px`;
    } else look["--rt-text"] = `${top.box.left - origin}px`;
    // A plain list's levels, by its words alone: an item a level in starts an indent on.
    if (!marked.length) {
      const levels = [...(inline?.area?.querySelectorAll(".rt-line") || [])].map((line) => Number(line.dataset.level) || 0);
      const deep = items.findIndex((item, n) => levels[n] > 0 && item.box.left - items[0].box.left > 3);
      if (deep >= 0) look["--rt-step"] = `${(items[deep].box.left - items[0].box.left) / levels[deep]}px`;
    }
    if (top.mark && !top.mark.matches("text")) {
      const mark = top.mark.getBoundingClientRect();
      look["--rt-mark-x"] = `${centre(top.mark) - origin}px`;
      look["--rt-r"] = `${mark.width / 2}px`;
      look["--rt-mark-y"] = `${(metrics.line - metrics.height) / 2 + (mark.top + mark.height / 2 - top.box.top)}px`;
      look["--rt-mark"] = top.mark.getAttribute("fill") || "currentColor";
    }
    if (deeper && !deeper.mark.matches("text")) {
      look["--rt-step"] = `${centre(deeper.mark) - outerMost}px`;
      look["--rt-r2"] = `${deeper.mark.getBoundingClientRect().width / 2}px`;
      look["--rt-mark2"] = deeper.mark.getAttribute("fill") || "currentColor";
    }
    // From one item to the next, less its own lines: the space between items.
    const lines = (item) => lineTops(item.text, metrics.height || 10).length || 1;
    // Measured baseline to baseline (an item's box grows with a taller face in it, as code's).
    const baseline = (item) => { const y = parseFloat(item.text.getAttribute("y")); const ctm = item.text.getScreenCTM(); return Number.isFinite(y) && ctm ? y * ctm.d + ctm.f : item.box.top; };
    const gaps = items.slice(1).map((item, n) => baseline(item) - baseline(items[n]) - lines(items[n]) * metrics.line);
    if (gaps.length) look["--rt-gap"] = `${Math.max(0, Math.min(...gaps))}px`;
    return look;
  }
  stage.addEventListener("scroll", () => { if (inline) positionInline(); });
  // A click on the desk round the slide chooses nothing, as on Keynote's canvas.
  stage.addEventListener("click", (event) => {
    if (event.target !== stage && !event.target.classList?.contains("slide-wrap")) return;
    if (!state.focus && !state.field && !allChosen) return;
    allChosen = null;
    state.focus = null; state.field = null;
    leaveFigure(false);
    placeChosen(); renderInspector(); reportFocus();
  });
  // A right-click there has the slide's menu, as Keynote's canvas has.
  stage.addEventListener("contextmenu", (event) => {
    if (pageNode && (event.target === stage || event.target.classList?.contains("slide-wrap"))) onContext(event);
  });

  // A press anywhere else ends the typing. On a control outside the slide (the inspector's
  // Subtitle field, a Layout tile, a colour) the press still reaches it, as in Keynote: the
  // inspector is drawn again only once the click is done, never under the pointer -- drawn
  // at once, the control pressed would be gone, the keys left on the page and the title
  // still chosen, to be typed over.
  function closeOnOutside(event) {
    if (!inline || inline.node.contains(event.target) || event.target.closest?.(".rt-bar, [data-keeps-typing]")) return;
    // A button, tile or swatch of the inspector (not one of its fields) leaves the insertion
    // point where it was, as Keynote's does: the words are typed in again from there once
    // the click is done, the next letter going on from it, never over them all (takeUp).
    const back = inspector.contains(event.target) && !event.target.closest("input, select, textarea, [contenteditable=true]") ? {
      slide: state.slide, target: inline.field ? { kind: "field", field: inline.field } : { ...inline.target, ...inline.at }, words: inline.read(),
      caret: inline.area.rich ? inline.area.caretAt() : [inline.area.selectionStart, inline.area.selectionEnd] } : null;
    closeInline({ later: !stage.contains(event.target), back });
  }
  // Typed in again where it was left (`back`), when the same words are chosen on the same
  // slide (an object moved meanwhile, Move Up, the one chosen still, its words the same)
  // and nothing else -- a menu, a dialog, a field -- has the keys; else, added and left
  // empty, it goes, as when the typing ends (dropFresh).
  function takeUp({ slide, target, caret, words }) {
    const there = target.kind !== "field" && state.focus ? { ...target, region: state.focus.region, index: state.focus.index } : null;
    const block = there && blocksAt(slideAt() || {}, there.region)[there.index];
    const still = target.kind === "field" ? state.field?.field === target.field
      : Boolean(there) && ((there.region === target.region && there.index === target.index)
        || (target.kind === "block" && Boolean(block) && (kindOf(block) === "bullets" ? bulletsText(block.bullets) : block[kindOf(block)]) === words));
    if (inline || !studio.active || state.slide !== slide || !still || typingNow() || document.querySelector(".menu")) {
      if (target.kind === "block" && dropFresh(target)) { renderInspector(); placeChosen(); reportFocus(); }
      return;
    }
    openInline(there || target);
    if (!inline || !caret) return;
    if (inline.area.rich) inline.area.caretTo(...caret);
    else inline.area.setSelectionRange(...caret);
  }

  // The spaces typed last, at the end of a line, waited for a word that never came: they go
  // as the editor closes, the same step as the typing.
  function trimTyped() {
    const area = inline.area;
    if (!area.rich) return;
    // (Made here, not typed: one with the typing, no turn of its own -- see typingSteps.)
    const tidied = () => area.dispatchEvent(new CustomEvent("input", { bubbles: true, detail: { tidy: true } }));
    const letters = area.letters(), at = inline.typedAt;
    const lineEnd = typeof at === "number" ? (letters.indexOf("\n", at) < 0 ? letters.length : letters.indexOf("\n", at)) : -1;
    if (at === lineEnd && /\s$/.test(letters.slice(0, at))) {
      const lines = area.value.split("\n"), line = letters.slice(0, at).split("\n").length - 1;
      if (lines[line] && /\s$/.test(lines[line])) {
        lines[line] = lines[line].replace(/\s+$/, "");
        area.value = lines.join("\n");
        tidied();
      }
    }
    // A list's items left empty go (the document keeps none), one with the typing.
    if (inline.bullets && area.value.split("\n").some((line) => !line.trim()) && area.value.trim()) {
      area.value = area.value.split("\n").filter((line) => line.trim()).join("\n");
      tidied();
    }
  }

  // The words a slide keeps empty, as placeholders holding their places: its title, a
  // statement's words, a title slide's subtitle (as a new one has them).
  const keptEmpty = (key) => key === "title" || key === "words" || (key === "subtitle" && layoutOf(slideAt()) === "title");
  function closeInline({ later = false, back = null, going = false, escaped = false } = {}) {
    if (!inline) return;
    // (Typed in again in a moment, `back`, its spaces wait on.)
    if (!back) trimTyped();
    // The typing done: what it left to say is said now.
    typedAt = 0;
    setTimeout(sayHeld);
    if (placed) {
      const { key, slide, entry } = placed;
      placed = null;
      // Put there to be typed into, and left empty: taken back, as if never put there.
      if (slide === state.slide && slideAt()?.[key] === "") {
        if (studio.past[studio.past.length - 1] === entry && same(studio.document, entry.after)) { studio.undo(); studio.future.pop(); }
        else editSlide((s) => { delete s[key]; }, { quiet: true });
      }
    } else if (inline.field && inline.opened && slideAt()?.[inline.field] === "" && !keptEmpty(inline.field)) {
      // A line of words emptied goes from the document, as before it was written (as the
      // panel's field does) -- with the typing that emptied it, one step to undo. (One empty
      // already, passed through, is left as it was.)
      const key = inline.field;
      editSlide((s) => { delete s[key]; }, { quiet: true, merge: `${state.slide}-${key}-${inline.session}`, hold: true });
      if (state.field?.field === key) state.field = null;
    }
    inline.area.dispose?.();
    standIn();
    inline.node.remove();
    pageNode?.querySelector(`[id="${CSS.escape(inline.id)}"]`)?.style.removeProperty("visibility");
    inline.hidden?.style.removeProperty("visibility");
    inline.hint?.style.removeProperty("visibility");
    if (inline.cell) pageNode?.querySelector(`[id="${CSS.escape(blockId(inline.at))}"]`)?.removeAttribute("transform");
    // (A cell left by Esc leaves its table: a new one still empty goes, as a text does.)
    const left = inline.at && (!inline.cell || escaped) ? inline.at : null;
    inline = null;
    // Its run of typing ends with it: typed in again, however soon, another step -- unless it
    // goes on in the same words made another kind (`going`).
    if (!going) studio.step();
    reportFocus();
    clearUnder();
    if (!back) dropFresh(left);
    document.removeEventListener("mousedown", closeOnOutside, true);
    // What was typed is shown in the panel too: after the click that ended the typing, when
    // one did (closeOnOutside), the control it was on kept the while.
    if (later) afterClick(renderInspector);
    else renderInspector();
    if (back) afterClick(() => takeUp(back));
    placeChosen();
  }
  // Added and left empty (`left`, where it was typed in): taken back as if it had never been
  // added, when nothing came after it; else deleted.
  function dropFresh(left) {
    if (!fresh || !left || fresh.slide !== state.slide || fresh.region !== left.region || fresh.index !== left.index) return false;
    const block = blocksAt(slideAt() || {}, left.region)[left.index];
    const { entry } = fresh;
    fresh = null;
    if (!block || !blank(block)) return false;
    if (studio.past[studio.past.length - 1] === entry && same(studio.document, entry.after)) { studio.undo(); studio.future.pop(); }
    else editSlide((s) => { blocksAt(s, left.region).splice(left.index, 1); });
    state.focus = null;
    return true;
  }
  // Once the press under way has been let go and its click has run (or at once, should no
  // click come of it).
  function afterClick(run) {
    let done = false;
    const once = () => { if (!done) { done = true; run(); } };
    document.addEventListener("pointerup", () => setTimeout(once, 0), { once: true, capture: true });
    setTimeout(() => { if (!document.querySelector(":active")) once(); }, 1500);
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
      else await insertBlock("structure", structureFigure(sources, await structureNames(sources)));
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
    if (block) return { what: "block", block: structuredClone(block), label: blockName(block).toLowerCase() };
    if (allOn()) { const blocks = allBlocks().map((each) => structuredClone(each.block)); return { what: "blocks", blocks, label: `${blocks.length} objects` }; }
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
    if (clip.what === "blocks") return clip.blocks.map((block) => plainOf({ what: "block", block })).join("\n");
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
    if (clip.what === "parts") { figureCut = true; figure.parts.remove(); }
    else if (clip.what === "block") deleteBlock(state.focus, "cut");
    else if (clip.what === "blocks") deleteAll("cut");
    else if (clip.what === "slides") deleteSlides(clip.indices, "cut");
    else deleteSlide(state.slide, "cut");
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
    // (Words typed in, or a field that took the paste itself, are not the slide's.)
    if (!studio.active || typingNow() || event.defaultPrevented) return;
    const data = event.clipboardData;
    let clip = null;
    try { clip = JSON.parse(data?.getData(CLIP) || "null"); } catch { clip = null; }
    // A clipboard that keeps only words: what was copied here, if they are its words.
    if (!clip && clipboard && data?.getData("text/plain") === plainOf(clipboard)) clip = clipboard;
    if (clip) { event.preventDefault(); pasteClip(clip); return; }
    const files = [...(data?.files || [])];
    if (files.length) { event.preventDefault(); await addFiles(files, state.focus ? { kind: "block", ...state.focus } : null); return; }
    const text = (data?.getData("text/plain") || "").replace(/\r/g, "").trim();
    // Another app's formatted words keep their bold, italic, code, links and levels, as
    // they do pasted in an editor.
    const html = data?.getData("text/html");
    const read = html ? itemsOfHtml(html) : [];
    const items = read.filter((item) => item.markup.trim());
    if (!text && !items.length) return;
    if (!regionsOf(slideAt()).length) { toast("This layout has no room for text. Choose a different layout first.", { icon: "info" }); return; }
    event.preventDefault();
    // A spreadsheet's cells are a table, its first row the header, as in Keynote.
    const cells = cellsOf(html, data?.getData("text/plain") || "");
    if (cells) { insertBlock("table", { table: cells }, null, "Paste Table"); return; }
    // One address is a link, its words the address (unless it came as a link of its own).
    const linked = !/<a[\s>]/i.test(html || "") && linkOfWords(text);
    if (linked) { insertBlock("text", { text: linked }, null, "Paste Text"); return; }
    if (items.length === 1) { insertBlock("text", { text: items[0].markup.trim() }, null, "Paste Text"); return; }
    if (items.length) { const blocks = pastedBlocks(read); insertBlock("text", blocks, null, pasteLabel(blocks)); return; }
    // Words pasted are words: a * or $ in them is that mark, not markup. A line that starts
    // with a bullet or a number ("- ", "3. ", "a) ") is a list's item, without them, its
    // indent (a tab or two spaces) its level; so is a line indented under another (an outline
    // from Notes or TextEdit), the line it is under the item over it. Other lines are
    // paragraphs, a blank line between two.
    const lines = text.split("\n");
    if (lines.filter((line) => line.trim()).length < 2) { insertBlock("text", { text: markupOfWords(text) }, null, "Paste Text"); return; }
    const marker = /^(?:[-*+•◦▪‣·–]|\(?\d{1,3}[.)]|\(?[a-z][.)])\s+/i;
    let paragraph = 0;
    const plainItems = lines.map((line) => {
      if (!line.trim()) { paragraph += 1; return { markup: "" }; }
      const mark = marker.exec(line.trim());
      const depth = Math.floor(/^[ \t]*/.exec(line)[0].replace(/\t/g, "  ").length / 2);
      return { depth, markup: markupOfWords(line.trim().slice(mark ? mark[0].length : 0)), listed: Boolean(mark) || depth > 0, ordered: Boolean(mark && /\d/.test(mark[0])), block: paragraph, outline: !mark && depth === 0 };
    });
    plainItems.forEach((item, n) => { if (item.listed && item.depth > 0 && plainItems[n - 1]?.markup && !plainItems[n - 1].listed) plainItems[n - 1].listed = true; });
    // An outline's lines at its top, after the lines under one of them, are its items too.
    plainItems.forEach((item, n) => {
      if (item.markup && !item.listed && plainItems[n - 1]?.listed && plainItems.some((other) => other.block === item.block && other.listed && other.outline)) item.listed = true;
    });
    const blocks = pastedBlocks(plainItems);
    insertBlock("text", blocks, null, pasteLabel(blocks));
  });
  // Words pasted named in the history by what they were made: a list, a text -- or, made
  // into several objects, words.
  const pasteLabel = (blocks) => (blocks.length === 1 ? `Paste ${blockLabel(blocks[0])}` : "Paste Text");
  // Pasted words as the slide's objects, as Keynote pastes them: each paragraph a text (its
  // lines kept), and a list's items -- only a list's (an <ol> or <ul>, Word's, lines with
  // bullets or numbers, an outline's indented lines) -- a list, numbered if its numbers were.
  function pastedBlocks(items) {
    const blocks = [];
    let last = null;
    for (const item of items) {
      // (A blank line ends a paragraph; a list goes on past it.)
      if (!item.markup.trim()) { if (!last?.listed) last = null; continue; }
      if (item.listed) {
        if (!last?.listed) blocks.push(last = { listed: true, items: [] });
        last.items.push(item);
      } else {
        if (!last || last.listed || last.block !== item.block) blocks.push(last = { listed: false, block: item.block, lines: [] });
        last.lines.push(item.markup.trim());
      }
    }
    return blocks.map((block) => {
      if (!block.listed) return { text: block.lines.join("\n") };
      const least = Math.min(...block.items.map((item) => item.depth || 0));
      const outer = block.items.filter((item) => (item.depth || 0) === least);
      return { bullets: bulletsFrom(block.items.map((item) => "  ".repeat((item.depth || 0) - least) + item.markup.trim()).join("\n")), ...(outer.every((item) => item.ordered) ? { numbered: true } : {}) };
    });
  }
  function pasteClip(clip) {
    if (clip.what === "slides") {
      const at = Math.min(Math.max(...chosenSlides()) + 1, slides().length);
      studio.change((d) => { d.slides ||= []; d.slides.splice(at, 0, ...clip.slides.map((slide) => copyOf(slide))); },
        { label: clip.slides.length === 1 ? "Paste Slide" : `Paste ${clip.slides.length} Slides` });
      select(at);
      state.picked = clip.slides.map((_, n) => at + n);
      renderRail();
    } else if (clip.what === "slide") {
      const at = Math.min(state.slide + 1, slides().length);
      studio.change((d) => { d.slides ||= []; d.slides.splice(at, 0, copyOf(clip.slide)); }, { label: "Paste Slide" });
      select(at);
    } else if (clip.what === "block") {
      if (!regionsOf(slideAt()).length) { toast("This layout has no room for objects. Choose a different layout first.", { icon: "info" }); return; }
      insertBlock(kindOf(clip.block), copyOf(clip.block), null, `Paste ${blockLabel(clip.block)}`);
    } else if (clip.what === "blocks" && Array.isArray(clip.blocks) && clip.blocks.length) {
      if (!regionsOf(slideAt()).length) { toast("This layout has no room for objects. Choose a different layout first.", { icon: "info" }); return; }
      insertBlock(kindOf(clip.blocks[0]), clip.blocks.map((block) => copyOf(block)), null, `Paste ${clip.blocks.length} Objects`);
    } else if (clip.what === "parts") {
      if (figure && figureBlock() && editable(figureBlock())) figure.parts.paste(clip.parts);
      else insertBlock("figure", { figure: figureOfParts(clip.parts) }, null, "Paste Figure");
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
  // `label` names it in the history when it is not a new object: "Paste Text", "Duplicate Figure".
  // (`given` may be several objects, one after another: words pasted as paragraphs and lists.)
  async function insertBlock(kind, given = null, where = null, label = null) {
    // Typing ends first: a new object just put there and left empty goes as it is left, not
    // after this one is put in its place (or this one taken for it).
    closeInline();
    const slide = slideAt();
    const regions = regionsOf(slide);
    if (!regions.length) { toast("This layout has no room for objects. Choose a different layout first.", { icon: "info" }); return; }
    const more = Array.isArray(given) ? given.slice(1) : [];
    if (Array.isArray(given)) given = given[0];
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
      block = structureFigure([path], await structureNames([path]));
    }
    // After what is chosen (the last of several); else in the first empty column, as a new
    // object fills the room there is.
    const last = allOn() ? allBlocks().at(-1) : null;
    const anchor = where || state.focus || (last ? { region: last.region.key, index: last.index } : null);
    const empty = regions.find((r) => !blocksAt(slide, r.key).length);
    // Nothing chosen now: the column last chosen on this slide (its placeholder clicked, then
    // Esc), where the person was working.
    const lastHere = chosenLast?.slide === state.slide && regions.some((r) => r.key === chosenLast.region) ? chosenLast.region : null;
    const region = anchor && regions.some((r) => r.key === anchor.region) ? anchor.region : lastHere || (empty || regions[0]).key;
    let index = 0;
    editSlide((s) => {
      const list = blocksAt(s, region, true);
      // Where there is only the layout's placeholder (an empty text or list, a Figure slide's
      // empty figure), the new object takes its place. Objects put there are kept, empty or
      // not: an empty table, numbers.
      const own = (other) => blank(other) && (["text", "bullets"].includes(kindOf(other)) || (kindOf(other) === "figure" && layoutOf(s) === "figure"));
      if (list.length && list.every(own)) { list.splice(0, list.length, block, ...more); index = 0; return; }
      index = anchor?.region === region ? Math.min(anchor.index + 1, list.length) : list.length;
      list.splice(index, 0, block, ...more);
    }, label ? { label } : {});
    // The last of several is the one chosen: what is pasted next goes after it.
    index += more.length;
    // A new text or list left empty goes again when it is left, as Keynote's does.
    fresh = !given && blank(block) ? { entry: studio.past[studio.past.length - 1], slide: state.slide, region, index } : null;
    focusBlock(region, index);
    // Several put in (pasted): all of them chosen, as Keynote chooses what it pastes.
    if (more.length) {
      chooseMany(Array.from({ length: more.length + 1 }, (_, n) => ({ region, index: index - more.length + n })));
      markMany(null, allChosen?.picks || null);
      state.focus = null;
      leaveFigure(false);
      placeChosen(); renderInspector(); reportFocus();
    }
    if (INLINE.has(kind) && !given) openSoon({ kind: "block", region, index });
    // A new table is typed into at once, from its first cell, as Keynote's is.
    else if (kind === "table" && !given) openSoon({ kind: "cell", region, index, row: 0, col: 0 });
    // New numbers, from their first number's value, in the panel (where numbers are typed).
    else if (kind === "stats" && !given) inspectorBody.querySelector('[data-key="stat.0.value"]')?.focus();
    // So is a new figure or flow chart, on its one shape, once the figure is read: the keys
    // typed meanwhile are its words, never its commands (A, C, G).
    else if ((kind === "figure" || kind === "flow") && !given) {
      const open = openSoon({ kind: "shape", region, index }, null);
      whenFigure(open);
      // (Should the figure not be read in a while, the keys are the page's again.)
      setTimeout(open, 4000);
    }
  }
  let fresh = null;
  // The column of the object chosen last, and on which slide: where a new one goes when
  // nothing is chosen.
  let chosenLast = null;
  // The slide's field put there empty to be typed into (openInline), and its step in the history.
  let placed = null;
  // An object with nothing of its person's in it yet -- a text or list with no words, an
  // empty table or equation, a new figure's one empty shape, a sample: a placeholder.
  function blank(block) {
    const kind = kindOf(block);
    if (kind === "text" || kind === "code") return !String(block[kind] ?? "").trim();
    if (kind === "quote") return !String(block.quote ?? "").trim() && !String(block.by ?? "").trim();
    if (kind === "callout") return !String(block.callout ?? "").trim() && !String(block.title ?? "").trim();
    if (kind === "stats") return (block.stats || []).every((item) => !String(item?.value ?? "").trim() && !String(item?.label ?? "").trim());
    if (kind === "bullets") return !JSON.stringify(block.bullets ?? "").replace(/[\[\]",\s]/g, "");
    if (kind === "math") return !String(block.math ?? "").trim();
    if (kind === "table") return Array.isArray(block.table) && block.table.every((row) => (Array.isArray(row) ? row : [row]).every((cell) => !String(cell ?? "").trim()));
    // A figure that is one shape with no words (as a new one starts: document.py's _lone_shape).
    if (kind === "figure") {
      const nodes = block.figure?.nodes;
      return Boolean(block.figure && typeof block.figure === "object" && !block.figure.edges?.length && nodes?.length === 1
        && Object.keys(nodes[0]).every((key) => ["id", "kind", "label"].includes(key)) && !String(nodes[0].label ?? "").trim()
        && [undefined, "block", "terminal", "decision"].includes(nodes[0].kind));
    }
    return Boolean(block.placeholder);
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
    // Which object moved, and where to: undone or redone, it is the one chosen.
    const entry = studio.past[studio.past.length - 1];
    if (entry && state.focus) studio.said(entry).moved = { slide: state.slide, from: { ...from }, to: { ...state.focus } };
    renderInspector();
    placeChosen();
  }

  function deleteBlock(at, done = "deleted") {
    const block = blocksAt(slideAt(), at.region)[at.index];
    const label = block ? blockName(block) : "Object";
    editSlide((s) => { blocksAt(s, at.region).splice(at.index, 1); }, { label: done === "cut" ? `Cut ${label}` : null });
    if (block) {
      const gone = { block: structuredClone(block), label: named(block), at: Date.now(), entry: studio.past[studio.past.length - 1] };
      objectsDeleted = [...objectsDeleted.filter((item) => Date.now() - item.at < 60000), gone];
    }
    state.focus = null;
    renderInspector();
    placeChosen();
    reportFocus();
    undoNote(`${label} ${done}`, { icon: done === "cut" ? "cut" : "trash" });
  }

  // -- the inspector --
  // Drawn again for an undo or a redo, a field typed in has its caret after what changed.
  let undoing = false;
  // Who made the last change from elsewhere: who deleted what was being edited here.
  let lastWho = null;
  function renderInspector() {
    remember(placeKey, JSON.stringify({ slide: state.slide, tab: state.tab }));
    // A figure is edited while it is the part chosen on the slide shown.
    const focus = state.focus;
    if (figure && !(focus && figure.slide === state.slide && focus.region === figure.region && focus.index === figure.index)) leaveFigure(false);
    keepFocus(inspectorBody, () => {
      const slide = slideAt();
      const block = slide && state.focus && blocksAt(slide, state.focus.region)[state.focus.index];
      if (state.focus && !block) state.focus = null;
      // Format and Design: one segmented control, one stop for Tab, the arrows going from one
      // to the other and Space or Return choosing -- the keys staying on it as it is drawn again.
      const choose = (tab) => {
        const keys = inspectorHead.contains(document.activeElement);
        state.tab = tab;
        renderInspector();
        if (keys) inspectorHead.querySelector(".insp-tab.on")?.focus();
      };
      const tabs = [["slide", "Format", "slide"], ["design", "Design", "palette"]].map(([tab, label, glyph]) =>
        h(`button.insp-tab${state.tab === tab ? ".on" : ""}`, { type: "button", role: "tab", "aria-selected": String(state.tab === tab), onclick: () => choose(tab) }, icon(glyph), label));
      const tabBar = h("div.insp-tabs", { role: "tablist", "aria-label": "Inspector" }, tabs);
      ui.roving(tabBar, () => tabs, "inspector.tab");
      clear(inspectorHead, tabBar);
      if (state.tab === "design") clear(inspectorBody, designForm());
      else if (!slide) clear(inspectorBody, h("div.empty", {}, "No slides"));
      else if (block && figure && figureBlock() === block && figure.parts.model) clear(inspectorBody, figure.parts.panel());
      else if (block) clear(inspectorBody, blockPanel(slide, block));
      else if (allOn()) clear(inspectorBody, manyPanel(slide));
      else clear(inspectorBody, slidePanel(slide));
      markBlockErrors();
    }, { undone: undoing });
  }

  function crumbs(slide, block) {
    return h("div.crumbs", {},
      h(`button.crumb${block ? "" : ".here"}`, { type: "button", onclick: () => { state.focus = null; renderInspector(); placeChosen(); reportFocus(); } }, glyph(layoutOf(slide)), `Slide ${state.slide + 1}`),
      block ? [icon("chevron"), h("span.crumb.here", {}, icon(blockIcon(block)), blockName(block))] : null);
  }

  function blockPanel(slide, block) {
    const kind = kindOf(block);
    const at = state.focus;
    const regions = regionsOf(slide);
    const count = blocksAt(slide, at.region).length;
    return [
      h("div.section.block-top", {}, crumbs(slide, block),
        // In the order they are drawn, for Tab: the icons beside the name, then Edit Text under them.
        h("div.block-actions", {},
          ui.button("", () => moveBlock(at, { region: at.region, index: at.index - 1 }), { kind: "ghost", small: true, icon: "up", title: "Move Up", disabled: at.index === 0 }),
          ui.button("", () => moveBlock(at, { region: at.region, index: at.index + 2 }), { kind: "ghost", small: true, icon: "down", title: "Move Down", disabled: at.index >= count - 1 }),
          ui.button("", () => { editSlide((s) => { const list = blocksAt(s, at.region); list.splice(at.index + 1, 0, structuredClone(list[at.index])); }); focusBlock(at.region, at.index + 1); }, { kind: "ghost", small: true, icon: "duplicate", title: "Duplicate (⌘D)" }),
          ui.button("", () => deleteBlock(at), { kind: "ghost", small: true, icon: "trash", title: "Delete (⌫)" }),
          INLINE.has(kind) ? ui.button(kind === "math" ? "Edit Equation" : kind === "code" ? "Edit Code" : "Edit Text", () => openInline({ kind: "block", ...at }), { small: true, icon: "pencil", title: "Edit on the slide (↩), or double-click it" }) : null),
        // A placeholder says so, at the top: it looks like an object, but no one sees it yet --
        // until something is typed in it, here or on the slide (the note goes as it is).
        h("div.hint-line.placeholder-note", { hidden: !blank(block) }, icon("info"), placeholderWords(block, true)),
        regions.length > 1 ? ui.field("Column", ui.segmented({ value: at.region, options: regions.map((r) => ({ value: r.key, label: r.label })),
          onChange: (value) => moveBlock(at, { region: value, index: blocksAt(slideAt(), value).length }) })) : null),
      h("div.section.block-form", { dataset: { region: at.region, index: at.index } }, blockForm(block, kind, at)),
    ];
  }

  // Several objects chosen (⌘A, ⇧-click): said so, with what applies to them all -- the
  // settings every one of them has (one value shown when they share it), Arrange,
  // Duplicate and Delete -- and the slide's objects, those chosen marked, as a figure's
  // shapes chosen together are shown.
  const SIZED_WORDS = new Set(["text", "bullets", "quote", "callout", "code", "table", "math", "stats", "gallery"]);
  function manyPanel(slide) {
    const chosenNow = allBlocks(), count = chosenNow.length;
    const kinds = new Set(chosenNow.map(({ block }) => kindOf(block)));
    const all = (set) => [...kinds].every((kind) => set.has(kind));
    const shared = (name) => { const values = chosenNow.map(({ block }) => block[name]); return values.every((value) => value === values[0]) ? values[0] : undefined; };
    const mixed = (name) => shared(name) === undefined && chosenNow.some(({ block }) => block[name] !== undefined);
    // One edit for them all; a size stepped, or colours tried one after another, one run.
    const setAll = (name, fallback) => (value) => {
      keepAll = true;
      editSlide((s) => {
        for (const { region, index } of chosenNow) {
          const b = blocksAt(s, region.key)[index];
          if (b) { setOption(b, name, value, fallback); delete b.placeholder; }
        }
      }, { quiet: true, merge: `${state.slide}-many-${name}`, label: `Format ${count} Objects` });
      keepAll = false;
      markMany(picksNow(), picksNow());
    };
    const palette = studio.info?.palette || {};
    const seen = new Set(palette.ink ? [String(palette.ink).toLowerCase()] : []);
    const colours = [...TONES.map((tone, i) => ({ value: tone, colour: palette[tone] || "#888", title: i === 0 ? "Accent" : `Accent ${i + 1}` })),
      { value: "muted", colour: palette.muted || "#999", title: "Muted" }]
      .filter((item) => item.value === shared("colour") || (!seen.has(String(item.colour).toLowerCase()) && seen.add(String(item.colour).toLowerCase())));
    const leave = () => { allChosen = null; renderInspector(); placeChosen(); reportFocus(); };
    return [
      h("div.section.block-top", {},
        h("div.crumbs", {}, h("button.crumb", { type: "button", onclick: leave }, glyph(layoutOf(slide)), `Slide ${state.slide + 1}`),
          icon("chevron"), h("span.crumb.here", {}, icon("layout"), `${count} Objects`)),
        h("div.insp-title", {}, icon("layout"), h("div.insp-words", {}, h("div.insp-name", {}, `${count} Objects Selected`),
          h("div.insp-hint", {}, chosenNow.map(({ block }) => blockName(block)).join(", ")))),
        h("div.row", {},
          ui.button("Move Up", () => moveAll("ArrowUp"), { small: true, icon: "up", disabled: !moveAll("ArrowUp", true), title: "Move Up (⌥↑)" }),
          ui.button("Move Down", () => moveAll("ArrowDown"), { small: true, icon: "down", disabled: !moveAll("ArrowDown", true), title: "Move Down (⌥↓)" })),
        h("div.row", {},
          ui.button("Duplicate", () => duplicateChosen(), { small: true, icon: "duplicate", title: "Duplicate (⌘D)" }),
          ui.button("Delete", () => deleteAll(), { small: true, icon: "trash", kind: "danger", title: "Delete (⌫)" }))),
      all(new Set(["text"])) || all(new Set(["text", "bullets"])) || all(SIZED_WORDS) ? h("div.section", {},
        all(new Set(["text"])) ? ui.field("Align", ui.segmented({ value: mixed("align") ? null : shared("align") || "start", options: [
          { value: "start", label: "Left" }, { value: "middle", label: "Centre" }, { value: "end", label: "Right" }], onChange: setAll("align", "start") })) : null,
        all(new Set(["text", "bullets"])) ? ui.field("Colour", ui.swatches({ value: shared("colour") ?? null, colours, none: true, custom: true, onChange: setAll("colour") })) : null,
        all(SIZED_WORDS) ? ui.field("Font Size", ui.number({ value: shared("size"), placeholder: mixed("size") ? "Mixed" : "Auto", min: 4, max: 400, step: 1, unit: "pt", start: 18,
          key: "many.size", onChange: setAll("size") })) : null) : null,
      h("div.section", {}, h("div.section-title", {}, "Objects"), regionsOf(slide).map((region) => regionView(slide, region))),
    ];
  }

  function slidePanel(slide) {
    const layout = layoutOf(slide);
    const allowed = new Set(catalog.slide_keys[layout]);
    // A blank slide draws no title: its title and subtitle are offered only once they are set.
    if (layout === "blank") for (const key of ["title", "subtitle"]) if (!slide[key]) allowed.delete(key);
    const text = (key, label, { placeholder = "", markup = true, rows = 1 } = {}) => {
      if (!allowed.has(key)) return null;
      const onInput = (value) => editSlide((s) => setOption(s, key, value), { quiet: true, merge: `${state.slide}-${key}`, hold: true });
      return ui.field(label, markup ? richField({ value: slide[key] ?? "", single: rows === 1, placeholder, key: `slide.${key}`, onInput })
        : ui.input({ value: slide[key] ?? "", placeholder, key: `slide.${key}`, onInput }));
    };
    const parts = [
      h("div.section", {}, crumbs(slide, null),
        layout === "statement" ? text("words", "Text", { rows: 2, placeholder: "A short statement" }) : text("title", layout === "agenda" ? "Heading" : "Title", { placeholder: layout === "agenda" ? "Outline" : "Title" }),
        text("subtitle", "Subtitle", { placeholder: "Subtitle" }),
        // Each a whole row wide: an author's name and affiliation read without being cut off.
        layout === "title" ? [text("author", "Author", { markup: false, placeholder: "Your name" }),
          // An example, not a default: an empty date draws nothing.
          text("date", "Date", { markup: false, placeholder: `e.g. ${new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}` })] : null,
        text("by", "Attribution", { markup: false, placeholder: "Who said it" }),
        layout === "agenda" ? h("div.hint-line", {}, "Lists the titles of the deck's section slides automatically.") : null,
        layout === "blank" && (slide.title || slide.subtitle) ? h("div.hint-line", {}, "A blank slide doesn't show its title.") : null),
    ];
    const regions = regionsOf(slide);
    if (regions.length) parts.push(h("div.section", {}, h("div.section-title", {}, "Objects"), regions.map((region) => regionView(slide, region))));
    parts.push(h("div.section", {}, h("div.section-title", {}, "Layout"), layoutGrid(layout, (name) => changeLayout(name), layouts, studio.info?.palette),
      layout === "two-columns" ? splitControl(slide) : null,
      layout === "columns" ? columnsControls(slide) : null,
      // Unset, the slide follows the deck's Design: said, so it is not taken for one of the
      // others -- and the Design's own choice is offered only as that, not twice by one name
      // (unless the slide already sets it).
      allowed.has("align") ? ui.field(styleName("align"), ui.select({ value: slide.align ?? "", key: "slide.align", options: [
        { value: "", label: `As in Design (${choiceName("align", deckStyle("align") || "auto")})` },
        ...["auto", "top", "middle"].filter((value) => value !== (deckStyle("align") || "auto") || value === slide.align)
          .map((value) => ({ value, label: choiceName("align", value) }))],
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
    // Placeholders (an empty list a new slide starts with) simply go: they are nothing lost.
    const real = blocks.flat().filter((block) => !blank(block));
    const lost = WORDLESS.has(layout) && real.length;
    // A layout without room for objects (Statement, Title, Section, Agenda) never takes them
    // away: they go on a new slide after this one, set out and titled as they were -- its
    // title a placeholder to click if it had none -- in the same step (one Undo puts them back).
    const ownOnly = (list) => (Array.isArray(list) ? structuredClone(list.filter((block) => !blank(block))) : list);
    const kept = lost ? {
      ...(layoutOf(before) === "content" ? {} : { layout: layoutOf(before) }),
      title: before.title ?? before.words ?? "",
      ...Object.fromEntries(["body", "left", "right", "split", "widths", "align"].filter((key) => key in before).map((key) => [key, ownOnly(before[key])])),
      ...(Array.isArray(before.columns) ? { columns: before.columns.map(ownOnly) } : {}),
    } : null;
    editSlide((slide, d) => {
      for (const [key, value] of Object.entries(before)) if (!(key in slide) && !["layout", "body", "left", "right", "columns"].includes(key)) slide[key] = structuredClone(value);
      const all = blocks.flat();
      const words = layoutOf(slide) === "statement" ? slide.words : slide.title;
      for (const key of ["body", "left", "right", "columns", "split", "widths"]) delete slide[key];
      if (layout === "content") delete slide.layout; else slide.layout = layout;
      if (layout === "statement") { if (words) slide.words = words; delete slide.title; }
      else if (words) { slide.title = words; delete slide.words; }
      // One body made two columns, its objects kept in their order: words on the left and
      // what is drawn on the right where the words come first, as a slide with both is set
      // out; else the first half on the left and the rest on the right.
      const drawn = (block) => VISUAL.has(kindOf(block));
      const first = all.findIndex(drawn);
      if (layout === "two-columns" && blocks.length === 1 && first > 0 && all.slice(first).every(drawn)) {
        slide.left = all.slice(0, first);
        slide.right = all.slice(first);
      } else if (layout === "two-columns" && blocks.length === 1 && all.length > 1) {
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
      if (kept) d.slides.splice(state.slide + 1, 0, kept);
    }, kept ? { label: "Change Layout" } : {});
    // Objects kept on the next slide are there, not set aside to come back here too.
    if (!kept) layoutStash.set(JSON.stringify(slideAt()), current);
    state.focus = null;
    renderRail();
    renderInspector();
    renderBar();
    if (lost) {
      const count = real.length, what = count === 1 ? blockLabel(real[0]) : `${count} objects`;
      undoNote(`${LAYOUT_NAMES[layout]} has no room for objects: ${count === 1 ? `the ${what.toLowerCase()} is` : `${what} are`} on a new slide after this one`, { icon: "info", seconds: 7 });
    }
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

  // A slide's colour is one of its theme's, by name (accent, accent2, ink, muted), so a
  // change of theme repaints it; or any colour, from the system's picker.
  const THEME_COLOURS = [["accent", "Accent"], ["accent2", "Accent 2"], ["accent3", "Accent 3"], ["accent4", "Accent 4"], ["accent5", "Accent 5"], ["ink", "Text"], ["muted", "Muted"]];
  function backgroundControls(slide, allowed) {
    const background = slide.background;
    const named = THEME_COLOURS.some(([name]) => name === background);
    const mode = !background ? "" : named || String(background).startsWith("#") ? "colour" : "picture";
    const parts = [ui.segmented({ value: mode, options: [{ value: "", label: "Default" }, { value: "colour", label: "Colour" }, { value: "picture", label: "Picture" }],
      onChange: async (value) => {
        if (value === "") editSlide((s) => { delete s.background; delete s.shade; delete s.dark; });
        else if (value === "colour") editSlide((s) => { s.background = "accent"; delete s.shade; });
        else {
          const path = await chooseFile({ title: "Choose a Background Picture", types: ["image"] });
          if (path) editSlide((s) => { s.background = path; s.shade = s.shade ?? 0.35; });
        }
        renderInspector();
      } })];
    if (mode === "colour") {
      // Chosen as every colour is: the theme's, as chips, and any other from the system's
      // picker in the well after them.
      const palette = studio.info?.palette || {};
      const seen = new Set();
      // Each colour once (a palette of three fills five accents by going round), the one in use kept.
      // An accent as it fills a slide: the theme's own colour (deck.py's theme_colour), not
      // the stroke words and lines take from it.
      const order = studio.info?.order || [];
      const filled = (name) => (name.startsWith("accent") && order.length ? order[(Number(name.slice(6) || 1) - 1) % order.length] : palette[name]);
      const colours = THEME_COLOURS.map(([name, title]) => ({ value: name, colour: filled(name), title }))
        .filter((item) => /^#[0-9a-f]{6}$/i.test(item.colour || "") && (item.value === background || !seen.has(item.colour.toLowerCase()) && seen.add(item.colour.toLowerCase())));
      parts.push(ui.swatches({ value: named ? background : String(background).toLowerCase(), colours, none: false, custom: true, key: "slide.background",
        onChange: (value) => editSlide((s) => { s.background = value; }, { quiet: true, merge: `${state.slide}-bg` }) }));
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
    // Apart as the inspector's fields are: the chips' rings clear of the label under them.
    return h("div", { style: { display: "grid", gap: "12px" } }, parts);
  }

  // A slide's footnotes, as a list. Each change is made to them as they are when it is made,
  // not as the panel was drawn: typed into since (quietly, the panel not drawn again), the
  // list drawn would put back what was typed over.
  const notesOf = (slide) => (Array.isArray(slide.footnotes) ? [...slide.footnotes] : slide.footnotes ? [slide.footnotes] : []);
  function footnotesControls(slide) {
    const list = notesOf(slide);
    // Each as the slide sets it (emphasis, links), as the inspector's other words are.
    const rows = list.map((note, i) => h("div.list-row", {},
      richField({ value: note, key: `footnote.${i}`, placeholder: "Reference or note", single: true, onInput: (value) => editSlide((s) => { const notes = notesOf(s); notes[i] = value; s.footnotes = notes; }, { quiet: true, merge: `${state.slide}-fn-${i}`, hold: true }) }),
      ui.button("", () => { editSlide((s) => { const next = notesOf(s).filter((_, j) => j !== i); if (next.length) s.footnotes = next; else delete s.footnotes; }); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, title: "Delete" })));
    rows.forEach((row) => { row.firstChild.style.flex = "1"; });
    return h("div.list-rows", {}, rows,
      // Added empty, to be typed in at once: "Footnote" shows faintly on the slide until it is.
      h("div.list-add", {}, ui.button("Add Footnote", () => {
        let added = 0;
        editSlide((s) => { const notes = notesOf(s); added = notes.length; s.footnotes = [...notes, ""]; });
        renderInspector();
        focusAdded(`footnote.${added}`);
      }, { kind: "ghost", icon: "plus", small: true })));
  }
  // A row just added is typed in at once: its field focused, and in view with what follows
  // it (its format bar, the Add button) -- not flush to the panel's foot, cut off.
  function focusAdded(key) {
    requestAnimationFrame(() => {
      const field = inspectorBody.querySelector(`[data-key="${key}"]`);
      if (!field) return;
      field.focus({ preventScroll: true });
      // (Once its format bar, shown as the caret comes, is under it.)
      setTimeout(() => (field.closest(".list-rows")?.parentNode.querySelector(".list-add") || field).scrollIntoView({ block: "nearest" }), 80);
    });
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
      // In the order of the bar's buttons and its More menu, as the Mac's Insert menu has them.
      h("button.add-row", { type: "button", onclick: (event) => menu(event.currentTarget, [...MAIN_BLOCKS, "-", ...MORE_BLOCKS].map((kind) => (kind === "-" ? "-" : {
        icon: BLOCKS[kind].icon, label: `${BLOCKS[kind].label}${CHOOSE.has(kind) ? "…" : ""}`, hint: BLOCKS[kind].hint, run: () => insertBlock(kind, null, { region: region.key, index: blocks.length - 1 }),
      }))) }, icon("plus"), "Add Object")));
    return node;
  }

  // What a placeholder is, said where it would be taken for an object: an empty one, or a
  // sample (a new mechanism), neither presented nor exported until its person changes it.
  const placeholderWords = (block, long = false) => `${block.placeholder ? "Sample" : "Empty"} — ${long ? "not presented or exported until edited" : "not shown until edited"}`;
  const rowWords = (block) => (blank(block) ? placeholderWords(block) : summary(block));
  function blockRow(block, region, index) {
    const kind = kindOf(block);
    const at = { region: region.key, index };
    // A row Tab reaches, Return or Space choosing its object, as a Mac list's row.
    // (⇧-click adds it to what is chosen, or takes it out, as on the slide.)
    const inChoice = allOn() && allBlocks().some((each) => each.region.key === region.key && each.index === index);
    const node = h(`div.block-row${inChoice ? ".chosen" : ""}`, { dataset: { region: region.key, index }, "aria-selected": inChoice ? "true" : undefined,
      onclick: (event) => { if (event.shiftKey && (state.focus || allOn())) pickAlso(at); else focusBlock(region.key, index); }, draggable: true,
      tabindex: 0, role: "button", "aria-label": `${blockName(block)}: ${rowWords(block)}`,
      onkeydown: (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); focusBlock(region.key, index); } },
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
      onmouseenter: () => place(hover, frameOf({ kind: "block", region: region.key, index, id: `slide${state.slide + 1}.${region.svg}.${index}` }), blockName(block)),
      onmouseleave: () => { hover.hidden = true; } },
    h("span.kind", {}, icon(blockIcon(block))),
    h("span.summary", {}, h("span.what", {}, blockName(block)), h(`span.words${blank(block) ? ".placeholder-words" : ""}`, {}, rowWords(block))),
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
  // Rich words' changes, for the history: typing runs together into one step; a change
  // of look or a paste is a step of its own, as in Keynote.
  function onRich(area, onInput) {
    area.addEventListener("input", (event) => {
      const step = Boolean(event.detail?.step) || /^format/.test(event.inputType || "");
      if (step) studio.step?.();
      const top = studio.past[studio.past.length - 1];
      onInput(area.value);
      // A step of its own named as what it did (a paste), not as what changed (an item added).
      const made = studio.past[studio.past.length - 1];
      if (step && event.detail?.label && made && made !== top) { made.label = event.detail.label; made.said = null; }
      if (step) studio.step?.();
    });
  }
  // (`onCells`: a spreadsheet's cells pasted in it, as on the slide.)
  function richField({ value, key, placeholder = "", list = false, single = false, numbered = false, plain = false, onInput, onCells = null, onList = null }) {
    // Its format bar under it: over it are the panel's own controls (Edit Text).
    const area = richText({ value, list, single, numbered, plain, placeholder, palette: studio.info?.palette || {}, leaveOnTab: true, docked: true, onCells, onList });
    area.dataset.key = key;
    // Esc leaves the field (a list's Tab sets its levels), and nothing else.
    area.addEventListener("keydown", (event) => { if (event.key === "Escape") { event.stopPropagation(); area.blur(); } });
    onRich(area, onInput);
    if (single) area.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) area.blur(); });
    return h(`div.rich-field${single ? ".single" : ""}`, {}, area);
  }

  // What the slide draws of an object, in the slide's points: the size of its words (as
  // drawn, shrunk to fit or not), its width and its height. A number field left to "Auto"
  // steps from these.
  function drawnOf(at) {
    const element = blockElement(at.region, at.index);
    const scale = element?.ownerSVGElement?.getScreenCTM?.()?.a;
    const box = element?.getBoundingClientRect();
    if (!scale || !box?.width) return {};
    const words = [...element.querySelectorAll("text")].find((text) => text.textContent.trim().length > 1);
    const size = words ? parseFloat(getComputedStyle(words).fontSize) * ((words.getScreenCTM()?.a || scale) / scale) : null;
    return { size: Number.isFinite(size) ? size : null, width: box.width / scale, height: box.height / scale };
  }

  // -- the form for each kind of part --
  function blockForm(block, kind, at) {
    const merge = (name) => `${state.slide}-${at.region}-${at.index}-${name}`;
    const key = (name) => `block.${name}`;
    const set = (name, fallback) => (value) => editBlock(at, (b) => setOption(b, name, value, fallback), { merge: merge(name) });
    // Words typed in a field: one run from focusing it to leaving it (leftField, typingSteps).
    const edit = (mutate, name) => editBlock(at, mutate, { merge: merge(name), hold: true });
    // In points, said in the field ("18 pt"); ↑ from "Auto" goes from the size the slide draws.
    const size = () => ui.field("Font Size", ui.number({ value: block.size, placeholder: "Auto", min: 4, max: 400, step: 1, unit: "pt", start: 18, key: key("size"),
      current: () => drawnOf(at).size, onChange: set("size") }));
    const toneSwatches = (name, { none = true, extra = [], fallback } = {}) => {
      const palette = studio.info?.palette || {};
      // A palette of five fills more tones by going round again: each colour is offered once
      // -- and none that is the words' own colour, the default (Swiss's black accent).
      const seen = new Set(none && palette.ink ? [String(palette.ink).toLowerCase()] : []);
      const colours = [...TONES.map((tone, i) => ({ value: tone, colour: palette[tone] || "#888", title: i === 0 ? "Accent" : `Accent ${i + 1}` })), ...extra]
        .filter((item) => item.value === block[name] || !seen.has(String(item.colour).toLowerCase()) && seen.add(String(item.colour).toLowerCase()));
      return ui.swatches({ value: block[name] ?? fallback ?? null, colours, none, custom: true,
        onChange: (value) => editBlock(at, (b) => setOption(b, name, value, fallback), { merge: merge(name) }) });
    };
    // A spreadsheet's cells pasted in its words are a table after it, as on the slide.
    const onCells = (cells) => { document.activeElement?.blur(); insertBlock("table", { table: cells }, at, "Paste Table"); };
    const onList = (items) => { document.activeElement?.blur(); listAfter(at, items); };
    switch (kind) {
      case "bullets":
        return [richField({ value: bulletsText(block.bullets), list: true, numbered: Boolean(block.numbered), plain: Boolean(block.plain), key: key("bullets"), placeholder: "Text",
          onInput: (text) => edit((b) => { b.bullets = bulletsFrom(text); }, "items"), onCells }),
        h("div.hint-line", {}, "Return starts the next item; ", h("kbd", {}, "Tab"), " and ", h("kbd", {}, "⇧Tab"), " change its level; ", h("kbd", {}, "Esc"), " then ", h("kbd", {}, "Tab"), " goes on."),
        listField(at, block),
        ui.toggle({ value: block.reveal, label: "Reveal items one at a time", onChange: set("reveal", false) }),
        // Its words' colour, as a text's: the bullets and numbers keep the theme's.
        ui.field("Colour", toneSwatches("colour", { extra: [{ value: "muted", colour: studio.info?.palette?.muted || "#999", title: "Muted" }] })),
        size()];
      case "text":
        return [richField({ value: block.text ?? "", key: key("text"), placeholder: "Text", onInput: (text) => edit((b) => { b.text = text; }, "text"), onCells, onList }),
          listField(at, block),
          ui.field("Align", ui.segmented({ value: block.align || "start", options: [
            { value: "start", label: "Left" }, { value: "middle", label: "Centre" }, { value: "end", label: "Right" }],
          onChange: (value) => editBlock(at, (b) => setOption(b, "align", value, "start")) })),
          ui.field("Colour", toneSwatches("colour", { extra: [{ value: "muted", colour: studio.info?.palette?.muted || "#999", title: "Muted" }] })),
          size()];
      case "quote":
        return [richField({ value: block.quote ?? "", key: key("quote"), placeholder: "Quote", onInput: (text) => edit((b) => { b.quote = text; }, "quote"), onCells, onList }),
          ui.field("Attribution", ui.input({ value: block.by, placeholder: "Name", key: key("by"), onInput: (text) => edit((b) => setOption(b, "by", text), "by") })), size()];
      case "callout":
        return [ui.field("Heading", ui.input({ value: block.title, placeholder: "Optional", key: key("title"), onInput: (text) => edit((b) => setOption(b, "title", text), "title") })),
          ui.field("Text", richField({ value: block.callout ?? "", key: key("callout"), placeholder: "Text", onInput: (text) => edit((b) => { b.callout = text; }, "words"), onCells, onList })),
          ui.field("Colour", toneSwatches("colour", { none: false, fallback: "accent" })), size()];
      case "code": {
        // Its lines as typed, never wrapped back to the left edge: a long one scrolls sideways.
        const code = ui.textarea({ value: block.code, rows: 5, mono: true, indent: true, placeholder: "Code", key: key("code"), onInput: (text) => edit((b) => { b.code = codeOf(text); }, "code") });
        code.setAttribute("wrap", "off");
        // In a box with room at its right: a textarea's own padding is not kept at the end
        // of a line scrolled to, which would run into its edge.
        return [h("div.markup.code-box", {}, code), h("div.hint-line", {}, "Shown exactly as typed. Whole-line comments are dimmed."), size()];
      }
      case "stats": return statsForm(block, at, edit, toneSwatches, size);
      case "table": return tableForm(block, at, edit, size);
      case "image": return imageForm(block, at);
      case "gallery": return galleryForm(block, at, edit, size);
      case "figure": return figureForm(block, at, edit);
      case "plot":
        return [ui.field("Function", functionInput(block.plot, (value) => edit((b) => { b.plot = value; }, "plot")), { hint: "file.py:function" }),
          h("div.hint-line", {}, "A function that returns a matplotlib figure. It runs inside ", h("code", {}, "deck.plotting()"), " and receives the deck if it takes an argument."),
          ui.field("Aspect Ratio", ui.number({ value: block.aspect, placeholder: "Auto", min: 0.2, step: 0.1, start: 1.5, key: key("aspect"),
            current: () => { const drawn = drawnOf(at); return drawn.width && drawn.height ? drawn.width / drawn.height : null; }, onChange: set("aspect") }), { hint: "Width ÷ height" })];
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
    // Put in by the pointer (the LaTeX keeping the keys), or by Space or Return on the chip
    // with the keys; the chips one stop for Tab, the arrow keys going along them.
    const chips = MATH_SNIPPETS.map(([label, title, snippet]) => h("button.math-chip", { type: "button", title,
      onmousedown: (event) => { event.preventDefault(); insert(snippet); },
      onclick: (event) => { if (event.detail === 0) insert(snippet); } }, label));
    const chipRow = h("div.math-chips", { role: "toolbar", "aria-label": "Insert" }, chips);
    ui.roving(chipRow, () => chips, "math.chips");
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
    return [area, chipRow, notes,
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
        ownResources(drawing.querySelector("svg"));
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
      // Added empty, its hint drawn faintly on the slide (as its fields here hint it) and never
      // presented, rather than a sample number that would be.
      h("div.list-add", {}, ui.button("Add Number", () => {
        editBlock(at, (b) => { b.stats = [...items, { value: "", label: "" }]; });
        renderInspector();
        // Typed in at once, as a footnote added is.
        focusAdded(`stat.${items.length}.value`);
      }, { kind: "ghost", icon: "plus", small: true })),
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
    // Rows or columns added (or pasted), the alignments set stay with their columns; a new
    // column's is automatic.
    const restructure = (mutate) => {
      // From the cells as they are now: one just typed in on the slide (the panel drawn
      // again only after this click) is kept, not written back as it was.
      const current = blocksAt(slideAt() || {}, at.region)[at.index]?.table;
      if (Array.isArray(current)) current.forEach((row, r) => (Array.isArray(row) ? row : [row]).forEach((cell, c) => { if (rows[r] && c < rows[r].length) rows[r][c] = String(cell ?? ""); }));
      mutate();
      const now = Math.max(1, ...rows.map((row) => row.length));
      const fresh = autoAlign(rows, header);
      const align = given ? Array.from({ length: now }, (_, c) => given[c] ?? fresh[c]) : null;
      editBlock(at, (b) => {
        b.table = rows.map((row) => [...row]);
        if (align && align.some((value, c) => value !== fresh[c])) b.align = align; else delete b.align;
      });
      renderInspector();
    };
    // Each column's cells set as the slide sets them: as its alignment says, else as its words do.
    const aligned = given || auto;
    const input = (r, c) => {
      const cell = ui.cell({ value: rows[r][c], dataset: { key: `cell.${r}.${c}` },
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
    // Over each column, its pop-up as Numbers has one: the alignment it is set in, shown by
    // its icon and named in its menu -- never cut to "Aut…" -- and the column's commands
    // under it, as the slide's menu names them; each row's number opens the row's.
    // A row or column added is brought into view, the caret in its first cell to type in:
    // empty, it shows nowhere else (the slide draws nothing of it).
    const typeIn = (r, c) => requestAnimationFrame(() => {
      const cell = inspectorBody.querySelector(`[data-key="cell.${r}.${c}"]`);
      if (!cell) return;
      cell.focus({ preventScroll: true });
      cell.closest("td")?.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
    const ALIGN_ICONS = { start: "align-left", middle: "align-centre", end: "align-right" };
    // While a column's or a row's menu is open, what it acts on is marked in the grid and
    // outlined on the slide (as its items' `show` would, one by one).
    const lineItems = (cell, which) => tableItems(at, cell).filter((item) => which.test(item.label));
    const acting = (items, cells) => (on) => {
      items[0]?.show?.(on);
      for (const node of cells()) node.classList.toggle("acting", on);
    };
    const quiet = (items) => items.map(({ show, ...item }) => item);
    const columnCells = (c) => () => [...table.rows].map((tr) => tr.cells[c + 1]).filter(Boolean);
    const rowCells = (r) => () => [...(table.rows[r + 1]?.cells || [])].slice(1);
    const alignRow = h("tr", {}, h("th.corner"), Array.from({ length: columns }, (_, c) => h("th", {},
      ui.select({ value: given ? given[c] : "", icons: true, title: `Column ${c + 1}`, key: `table.column.${c}`,
        acting: acting(lineItems({ row: 0, col: c }, / Column/), columnCells(c)),
        options: [{ value: "", label: `Align Automatically (${auto[c] === "end" ? "Right" : "Left"})`, icon: ALIGN_ICONS[auto[c]] || "align-left" },
          { value: "start", label: "Align Left", icon: "align-left" }, { value: "middle", label: "Align Centre", icon: "align-centre" }, { value: "end", label: "Align Right", icon: "align-right" }],
        actions: quiet(lineItems({ row: 0, col: c }, / Column/)),
        onChange: (value) => {
          editBlock(at, (b) => {
            const next = given ? [...given] : [...auto];
            next[c] = value || auto[c];
            if (next.every((v, i) => v === auto[i])) delete b.align; else b.align = next;
          });
          // The cells below it set as it now says.
          renderInspector();
        } }))));
    const table = h("table", {}, alignRow, rows.map((row, r) => h(`tr${header && r === 0 ? ".header" : ""}`, {},
      h("td.corner", {}, h("button.row-pick", { type: "button", title: `Row ${r + 1}`, "aria-haspopup": "menu",
        onclick: (event) => {
          const items = lineItems({ row: r, col: 0 }, / Row/), shown = acting(items, rowCells(r));
          const opened = menu(event.currentTarget, quiet(items));
          shown(true);
          new MutationObserver((_, watch) => { if (!opened.isConnected) { shown(false); watch.disconnect(); } }).observe(document.body, { childList: true });
        } }, String(r + 1))),
      // A number with its unit ("40 ms") is kept on one line, as the slide sets it.
      // A few words (a name, "2 Na+ and glucose") on one line, the grid scrolling sideways if
      // it must: words are never broken, nor a short cell stacked a word a line.
      row.map((cell, c) => h(`td${numeric(cell) ? ".number" : ""}${cell.length <= 24 && !cell.includes("\n") ? ".short" : ""}`, { style: { textAlign: { start: "left", middle: "center", end: "right" }[aligned[c]] || "left" } }, input(r, c))))));
    // Wider than the panel, it scrolls sideways, and says so: its right edge fades while
    // there is more beyond it, as a menu's foot does while there is more below.
    const grid = h("div.table-edit.scroll-thin", {}, table);
    const frame = h("div.table-frame", {}, grid);
    const more = () => frame.classList.toggle("more-right", grid.scrollLeft + grid.clientWidth < grid.scrollWidth - 2);
    grid.addEventListener("scroll", more, { passive: true });
    new ResizeObserver(more).observe(grid);
    return [frame,
      h("div.row", {},
        ui.button("Add Row", () => { restructure(() => rows.push(Array(columns).fill(""))); typeIn(rows.length - 1, 0); }, { kind: "ghost", icon: "plus", small: true }),
        ui.button("Add Column", () => { restructure(() => rows.forEach((row) => row.push(""))); typeIn(0, columns); }, { kind: "ghost", icon: "plus", small: true }),
        h("span.spacer", { style: { flex: 1 } })),
      h("div.hint-line", {}, "Paste cells from a spreadsheet into any cell."),
      ui.toggle({ value: header, label: "Header row", onChange: (value) => editBlock(at, (b) => setOption(b, "header", value ? null : false)) }),
      size()];
  }

  function imageForm(block, at) {
    // A picture put back by Redo may be asked for a moment before its file is: it is asked
    // for again, a few times, rather than left blank.
    let tries = 0;
    const preview = h("img.preview-pic", { src: block.image ? studio.raw(block.image) : "", alt: "", hidden: !block.image,
      onload: () => { tries = 0; },
      onerror: () => { if (preview.getAttribute("src") && tries < 4) { tries += 1; const src = preview.src.replace(/&again=\d+$/, ""); setTimeout(() => { preview.src = `${src}&again=${tries}`; }, 400 * tries); } } });
    return [preview,
      fileRow(block.image, ["image"], (path) => { editBlock(at, (b) => { b.image = path; }, {}); preview.src = studio.raw(path); preview.hidden = false; }, "picture.png"),
      /\.svg$/i.test(block.image || "") ? h("div.hint-line", {}, "An SVG picture stays as vectors: editable shapes and text in PowerPoint.") : null,
      widthField(block, at),
      // As Keynote's Description: read out for whoever cannot see the picture, its lines
      // growing to hold it; Return is done, as it is one paragraph.
      ui.field("Description", described(ui.textarea({ value: block.description || "", rows: 1, placeholder: "What the picture shows", key: "block.description",
        onInput: (text) => editBlock(at, (b) => setOption(b, "description", text.replace(/\n+/g, " ")), { merge: `${state.slide}-${at.region}-${at.index}-description`, hold: true }) })),
      { hint: "Alt text for screen readers" })];
  }

  function described(area) {
    area.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); area.blur(); } });
    return area;
  }

  // A figure's or picture's width, in points: as its place sets it, or as its corners were
  // dragged to; ↑ from "Auto" goes from the width it is drawn at.
  function widthField(block, at) {
    return ui.field("Width", h("div.row", {},
      ui.number({ value: block.width, placeholder: "Auto", min: 10, step: 10, unit: "pt", start: 300, key: "block.width",
        current: () => drawnOf(at).width, onChange: (value) => editBlock(at, (b) => setOption(b, "width", value)) }),
      block.width != null ? ui.button("Reset Size", () => { editBlock(at, (b) => setOption(b, "width", null)); renderInspector(); }, { small: true, kind: "ghost" }) : null),
    { hint: "Or drag a corner on the slide" });
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
        ui.field("Columns", ui.number({ value: block.columns, placeholder: "Auto", min: 1, step: 1, start: Math.min(4, Math.max(1, items.length)), key: "gallery.columns", onChange: (value) => editBlock(at, (b) => setOption(b, "columns", value)) })),
        ui.field("Height", ui.number({ value: block.height, placeholder: "Auto", min: 10, step: 5, unit: "pt", start: 80, key: "gallery.height", onChange: (value) => editBlock(at, (b) => setOption(b, "height", value)) }))),
      ui.field("Crop", ui.segmented({ value: block.crop || "", options: [{ value: "", label: "None" }, { value: "circle", label: "Circle" }, { value: "square", label: "Square" }],
        onChange: (value) => { editBlock(at, (b) => setOption(b, "crop", value)); renderInspector(); } })),
      size()];
  }

  // Whether a figure's parts were arranged by hand -- a column of parts in a row beside
  // others, or a row in a column -- as the drawing judges it (compose.py's _arranged).
  function arranged(spec) {
    const groups = new Map((spec?.groups || []).map((group) => [group.id, group]));
    const kind = (group) => (typeof group?.layout === "string" ? group.layout : group?.layout?.kind);
    const lined = (group) => ["row", "column"].includes(kind(group)) && (group.children || []).length > 1;
    return [...groups.values()].some((holder) => lined(holder)
      && holder.children.some((child) => lined(groups.get(child)) && kind(groups.get(child)) !== kind(holder)));
  }

  function figureForm(block, at, edit) {
    const value = block.figure;
    const mode = typeof value === "string" ? (value.includes(".py:") ? "python" : "file") : "inline";
    // A figure of one shape (a structure by itself) has no rows and columns to swap.
    const shapes = mode === "inline" ? (value?.nodes || []).length : figure && figureBlock() === block ? figure.parts.model?.nodes?.length : undefined;
    // A figure arranged by hand is kept as arranged unless the switch is turned on for it.
    const byHand = arranged(mode === "inline" ? value : figure && figureBlock() === block ? figure.parts.model : null);
    const turn = shapes !== undefined && shapes < 2 ? null
      : ui.toggle({ value: block.turn ?? !byHand, label: "Swap rows and columns to fit", onChange: (on) => {
        if (on && byHand) swapAsked = `slide${state.slide + 1}`;
        editBlock(at, (b) => setOption(b, "turn", on && !byHand ? null : on));
      } });
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
    // One button for the figure's exports, as its right-click menu has one item.
    const exports = ui.field("Export", ui.button("Export Figure…", (event) => menu(event.currentTarget, exportItems(at)), { small: true, icon: "export", title: "SVG, PDF, PNG or a Flexo figure file" }));
    if (mode === "inline") {
      parts.push(h("div.figure-card", {},
        h("div", {}, h("b", {}, `${count((value?.nodes || []).length, "shape")}, ${count((value?.edges || []).length, "line")}`), h("div.hint-line", {}, "Stored in the deck, using the deck's theme"))));
      const area = ui.textarea({ value: JSON.stringify(value, null, 2), rows: 8, mono: true, indent: true, key: "figure.json", onInput: (text) => {
        try { const parsed = JSON.parse(text); area.style.borderColor = ""; edit((b) => { b.figure = parsed; }, "figure"); }
        catch { area.style.borderColor = "var(--error)"; }
      } });
      area.classList.remove("grow"); area.style.maxHeight = "300px"; area.style.overflow = "auto";
      parts.push(h("details.more", {}, h("summary", {}, icon("chevron"), "JSON"), h("div.inner", {}, area)));
      // Written in the deck, it is edited where it is drawn: where it is kept is put by, under
      // Advanced, as a figure's shape keeps its name in the file.
      return [exports, widthField(block, at), turn, figureDescription(block, at), h("details.more", {}, h("summary", {}, icon("chevron"), "Advanced"), h("div.inner", {}, parts))];
    } else if (mode === "file") {
      parts.push(fileRow(value, ["figure"], (path) => { editBlock(at, (b) => { b.figure = path; }); }, "figure.yaml"),
        h("div.hint-line", {}, "Edit the figure on the slide. Your changes are saved to the file, and changes made to the file appear here."));
    } else {
      parts.push(functionInput(value, (text) => edit((b) => { b.figure = text; }, "figure")),
        h("div.hint-line", {}, "A function that returns a ", h("code", {}, "flexo.Figure"), ". It runs again when its file changes."));
    }
    parts.push(widthField(block, at), turn, figureDescription(block, at));
    return [exports, ...parts];
  }

  // As a picture's Description: what the figure shows, read out in place of what is made
  // up from its shapes' words.
  function figureDescription(block, at) {
    return ui.field("Description", described(ui.textarea({ value: block.description || "", rows: 1, placeholder: "What the figure shows", key: "block.description",
      onInput: (text) => editBlock(at, (b) => setOption(b, "description", text.replace(/\n+/g, " ")), { merge: `${state.slide}-${at.region}-${at.index}-description`, hold: true }) })),
    { hint: "Alt text for screen readers" });
  }

  // The figure on the slide written out by itself, in the deck's look, laid out as written.
  function exportFigure(at, formats) {
    return studio.exportFiles(formats, { slide: state.slide, region: at.region, index: at.index });
  }

  // -- files --
  function fileRow(value, types, onChoose, placeholder) {
    const input = ui.input({ value: value || "", placeholder, mono: true, onChange: (text) => text && onChoose(text) });
    return h("div.list-row", {}, input,
      ui.button("Choose…", async () => { const path = await chooseFile({ title: "Choose a File", types }); if (path) { input.value = path; onChoose(path); } }, { icon: "folder", small: true, title: "Choose a file" }));
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

  // What the folder holds of each kind, as it was last listed (by `types`).
  const listed = new Map();
  const listFiles = (types) => studio.files(types).then((files) => {
    const shown = files.filter((file) => file !== studio.file.split("/").pop());
    listed.set(types.join(), shown);
    return shown;
  });
  listFiles(["image"]).catch(() => {});
  function chooseFile({ title, types, create }) {
    const accept = types.includes("image") ? "image/*,.svg,.pdf,.ai" : types.includes("structure") ? ".pdb,.cif,.mmcif,.ent" : ".yaml,.yml,.json";
    // A picture asked for in a folder known to have none: the Mac's file panel at once, as
    // Keynote's Choose… is, and no sheet. It is opened in the click that asked: a web view
    // opens none after the folder has been listed, the click long done.
    if (types.includes("image") && listed.get(types.join())?.length === 0) {
      return new Promise((resolve) => {
        const upload = h("input", { type: "file", accept, hidden: true });
        upload.addEventListener("change", async () => {
          upload.remove();
          const file = upload.files[0];
          try { resolve(file ? await studio.upload(file) : null); }
          catch (error) { toast(`Couldn't add “${file.name}”: ${error.message}`, { kind: "error", icon: "error", seconds: 6 }); resolve(null); }
        });
        upload.addEventListener("cancel", () => { upload.remove(); resolve(null); });
        document.body.append(upload);
        upload.click();
        listFiles(types).catch(() => {});
      });
    }
    return new Promise((resolve) => {
      let done = false;
      const finish = (value) => { if (!done) { done = true; resolve(value); box.close(); } };
      const list = h("div.list-rows", {}, h("div.empty", {}, h("div.spinner")));
      const upload = h("input", { type: "file", accept, hidden: true,
        onchange: async () => { const file = upload.files[0]; if (file) finish(await studio.upload(file)); } });
      const actions = [];
      if (types.some((type) => ["image", "figure", "structure"].includes(type))) actions.push({ label: "Upload…", aside: true, run: () => { upload.click(); return false; } });
      if (types.includes("structure")) actions.push({ label: "PDB ID…", aside: true, run: () => {
        askEntry().then((id) => { if (id) finish(id); });
        return false;
      } });
      if (create === "figure") actions.push({ label: "New Figure File…", aside: true, run: () => {
        ask("New Figure File", "figures/figure.yaml", "Create").then(async (name) => {
          if (!name) return;
          try { finish(await createFile(name, "figure")); }
          // Said in the sheet it was asked from, not in a note under it.
          catch (error) { problem.hidden = false; clear(problem, icon("error"), h("span", {}, error.message)); }
        });
        return false;
      } });
      actions.push({ label: "Cancel", run: () => finish(null) });
      const problem = h("div.field-problem", { hidden: true });
      const box = dialog({ title, body: [problem, list, upload], actions, onClose: () => finish(null) });
      listFiles(types).then((shown) => {
        // No picture to choose from in the folder (not known when it was asked for): the
        // Mac's file panel as soon as that is known (the sheet stays, should it be cancelled).
        if (!shown.length && types.includes("image") && !done) upload.click();
        clear(list, shown.length ? shown.map((file) => h("button.menu-item", { type: "button", onclick: () => finish(file) },
          types.includes("image") ? h("img.pic", { src: studio.raw(file), alt: "" }) : icon(types.includes("python") ? "code" : types.includes("structure") ? "structure" : "figure"),
          // Its name, and its folder only when it is in one.
          h("span.menu-text", {}, h("span", {}, file.split("/").pop()), file.includes("/") ? h("span.menu-hint", {}, file.slice(0, file.lastIndexOf("/") + 1)) : null)))
          : h("div.empty", {}, types.includes("structure") ? "No structure files in the deck's folder. Upload a PDB or mmCIF file, or enter a PDB ID." : "No matching files in the deck's folder"));
      });
    });
  }

  function chooseFunction(title = "Choose a Python Function") {
    return new Promise((resolve) => {
      let value = "";
      const input = functionInput("", (text) => { value = text; });
      // Named as any field is; its form is what the empty field shows.
      input.placeholder = "file.py:function";
      dialog({ title, body: [ui.field("Function", input), h("div.hint-line", {}, "The file must be in the deck's folder. The function runs each time the slide is drawn.")],
        actions: [{ label: "Cancel", run: () => resolve(null) }, { label: "Choose", kind: "primary", run: () => {
          if (!/\.py:\w+$/.test(value.trim())) { input.classList.add("invalid"); return false; }
          resolve(value.trim());
        } }], onClose: () => resolve(null) });
      setTimeout(() => input.focus(), 30);
    });
  }

  // What structure files say they hold, to name the parts made of them (none: named for
  // their files).
  const structureNames = (sources) => studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "structure-name", sources } })
    .then((found) => found?.names || []).catch(() => []);

  // A PDB entry, downloaded before it is added: if it can't be, the dialog says why and
  // nothing is added (as in the figure editor).
  function askEntry() {
    return new Promise((resolve) => {
      let done = false;
      const input = ui.input({ placeholder: "1UBQ", mono: true });
      const note = h("div.field-problem", { hidden: true });
      // While it downloads its button says so, and is not pressed twice.
      const download = ui.button("Download", () => fetchIt(), { kind: "primary" });
      const busy = (on) => { download.disabled = on; download.querySelector(".btn-label").textContent = on ? "Downloading…" : "Download"; };
      const fetchIt = async () => {
        const id = input.value.trim().toUpperCase();
        if (!id || download.disabled) { input.focus(); return; }
        clear(note, h("span.spinner"), h("span", {}, `Downloading ${id}…`));
        note.hidden = false;
        busy(true);
        try {
          const found = await studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "structure-fetch", id } });
          if (!done) { done = true; resolve(found.id); box.close(); }
        } catch (error) {
          clear(note, icon("warning"), h("span", {}, error.message));
          input.focus();
        }
        busy(false);
      };
      input.addEventListener("input", () => { note.hidden = true; });
      input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); fetchIt(); } });
      const box = dialog({ title: "Add a Structure from the PDB", body: [ui.field("PDB ID", input, { hint: "Four characters, like 1UBQ" }), note],
        actions: [{ label: "Cancel", run: () => { done = true; resolve(null); } }, download],
        onClose: () => { if (!done) { done = true; resolve(null); } } });
      setTimeout(() => input.focus(), 20);
    });
  }

  // A file's name asked for, as a Mac's save panel asks: its name chosen, not its folder or
  // its extension, the button saying what it does -- and, with `about`, a line saying what
  // the file will be for.
  function ask(title, placeholder, action = "Save", about = "") {
    return new Promise((resolve) => {
      const input = ui.input({ value: placeholder });
      input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); resolve(input.value.trim() || null); box.close(); } });
      const box = dialog({ title, body: [about ? h("p.export-hint", {}, about) : null, input], actions: [{ label: "Cancel", run: () => resolve(null) }, { label: action, kind: "primary", run: () => resolve(input.value.trim() || null) }], onClose: () => resolve(null) });
      setTimeout(() => {
        input.focus();
        const from = placeholder.lastIndexOf("/") + 1, dot = placeholder.indexOf(".", from);
        input.setSelectionRange(from, dot > from ? dot : placeholder.length);
      }, 30);
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
    // Words typed in a field: one run from focusing it to leaving it (leftField).
    const typeDeck = (name) => (value) => editDeck((d) => setOption(d, name, value), { quiet: true, merge: `deck-${name}`, hold: true });
    const look = deck.look || "classic";
    const looks = tinted(h("div.looks", {}, catalog.looks.map((item) => h(`button.look${item.name === look ? ".on" : ""}`, { type: "button",
      onclick: () => { editDeck((d) => setOption(d, "look", item.name, "classic")); renderInspector(); } },
    lookArt(item.name), h("span.name", {}, lookName(item)), h("span.note", {}, item.note)))), studio.info?.palette);
    const themeIsFile = typeof deck.theme === "string" && /\.(ya?ml|json)$/i.test(deck.theme);
    const current = Array.isArray(deck.palette) ? "" : deck.palette || "default";
    const accents = () => Object.entries(studio.info?.palette || {}).filter(([k]) => k.startsWith("accent")).slice(0, 5).map(([, c]) => h("span", { style: { background: c } }));
    // The palette as a pop-up button, like the theme above it: every palette is in its menu,
    // not in a box scrolling inside the inspector.
    const strip = (colours) => h("span.palette-strip", {}, colours ? colours.map((c) => h("span", { style: { background: c } })) : accents());
    const choosePalette = (name) => { closeMenu(); editDeck((d) => { if (name === "default") delete d.palette; else d.palette = name; }); renderInspector(); };
    // With no palette of its own the deck has its theme's colours: shown as they are, and
    // named as the palette they are if they are one ("Okabe-Ito", after Customise…), else
    // as the theme's own.
    const own = studio.info?.own?.length ? studio.info.own : null;
    const colourSet = (colours) => [...colours].map((colour) => String(colour).toLowerCase()).sort().join();
    const ownName = own && Object.keys(catalog.palettes).find((name) => colourSet(catalog.palettes[name]) === colourSet(own));
    const paletteName = (name) => (name === "default" ? ownName || "Theme's Own" : name);
    // The palette in use in the order its colours are used (the deck's tones take them so),
    // the order Customise… writes them in and the theme then lists them in: one order.
    const inUse = (name, colours) => (name === current && name !== "default" && studio.info?.order?.length ? studio.info.order : colours);
    const paletteList = h("button.palette-pick", { type: "button", title: "Choose the deck's palette", onclick: (event) => popover(event.currentTarget,
      h("div.palette-choices", {}, [["default", own], ...Object.entries(catalog.palettes).filter(([name]) => name !== ownName)].map(([name, colours]) => h(`button.palette-choice${current === name ? ".on" : ""}`,
        { type: "button", onclick: () => choosePalette(name) }, strip(inUse(name, colours)), h("span", {}, paletteName(name))))), { className: "palette-menu" }) },
    strip(current === "default" ? own : inUse(current, catalog.palettes[current])), h("span", {}, current ? paletteName(current) : "Custom"), icon("chevron"));
    const fonts = (name, label, note) => ui.field(label, ui.font({ value: deck[name] || "", options: catalog.fonts, placeholder: note, key: `deck.${name}`, onChange: setDeck(name) }));
    const lookStyle = catalog.looks.find((item) => item.name === look)?.style || {};
    const changes = deck.style || {};
    const styleRows = catalog.style.map((field) => {
      const fallback = lookStyle[field.name] ?? field.default;
      const setStyle = (value) => editDeck((d) => { d.style ||= {}; setOption(d.style, field.name, value, undefined); if (!Object.keys(d.style).length) delete d.style; }, { quiet: true, merge: `style-${field.name}` });
      const choiceLabel = (choice) => choiceName(field.name, choice);
      let control;
      if (field.kind === "bool") control = ui.select({ value: changes[field.name] === undefined ? "" : String(changes[field.name]), options: [{ value: "", label: `Default (${fallback ? "On" : "Off"})` }, { value: "true", label: "On" }, { value: "false", label: "Off" }], onChange: (v) => setStyle(v === "" ? null : v === "true") });
      else if (field.kind === "choice") control = ui.select({ value: changes[field.name] ?? "", options: [{ value: "", label: `Default (${choiceLabel(fallback)})` }, ...field.choices.map((choice) => ({ value: choice, label: choiceLabel(choice) }))], onChange: (v) => setStyle(v || null) });
      // A length's unit is said in its field ("28 pt"), as every number's is, not in its note.
      const points = /,? in points$/i.test(field.note || "");
      if (!control) control = ui.number({ value: changes[field.name], placeholder: String(fallback ?? "Auto"), step: "any", unit: points ? "pt" : undefined, key: `style.${field.name}`, onChange: setStyle });
      const set = changes[field.name] !== undefined;
      return h("div.style-row", {}, h("span.name", {}, h(`span${set ? ".changed" : ""}`, {}, styleName(field.name)), h("span.note", {}, String(field.note || "").replace(/,? in points$/i, ""))), control,
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
        ui.field("Footer", ui.markup({ value: deck.footer || "", placeholder: "Group meeting · 2026", colours: false, key: "deck.footer", onInput: typeDeck("footer") })),
        ui.field("Export File Name", ui.input({ value: deck.id || "", placeholder: "talk", key: "deck.id", onInput: typeDeck("id") }), { hint: "name.pptx, name.pdf" })),
      h("div.section", {}, h("details.more", { open: changed > 0 }, h("summary", {}, icon("chevron"), `Proportions${changed ? ` (${changed} changed)` : ""}`),
        h("div.inner", {}, styleRows))),
    ];
  }

  async function customiseTheme(deck) {
    const base = deck.theme && !/\.(ya?ml|json)$/i.test(deck.theme) ? deck.theme : "paper";
    // Asked for by its name alone, as a Mac app asks: the file's extension is the studio's.
    // Named for the deck, and not as it is: two tabs of one name would not say which is which.
    const deckName = String(studio.file || deck.id || "talk").split("/").pop().replace(/\.(ya?ml|json)$/i, "");
    const given = await ask("Save Theme As", `${deckName} Theme`, "Save",
      "Saves this deck's look as a theme file you can edit: its colours, fonts and lines. Other decks can use it too.");
    if (!given) return;
    const name = /\.(ya?ml|json)$/i.test(given) ? given : `${given.replace(/\.theme$/i, "")}.theme.yaml`;
    const stem = name.split("/").pop().replace(/\.(ya?ml|json)$/i, "").replace(/\.theme$/i, "");
    // The deck's palette goes into the theme, where its colours can be changed: left on the
    // deck it would stand over every colour changed there. Its colours are written in the
    // order the deck's tones took them, so every colour stays where it was.
    const colours = deck.palette ? (studio.info?.order?.length ? studio.info.order : Array.isArray(deck.palette) ? deck.palette : catalog.palettes?.[deck.palette]) : null;
    try {
      const made = await createFile(name, "theme", { theme: { name: stem, base, description: `The look of ${deck.id || "this deck"}.`, ...(colours ? { palette: [...colours] } : {}) } });
      studio.change((d) => { d.deck ||= {}; d.deck.theme = made; if (colours) delete d.deck.palette; });
      renderInspector();
      studio.workspace.open(studio.folder() + made);
      toast("Edit the theme here. The deck updates as you make changes.", { icon: "theme", seconds: 4 });
    } catch (error) { toast(error.message, { kind: "error", icon: "error" }); }
  }

  // -- presenting (present.js) --
  // From this slide, or from the first with ⌥ (⌥⌘↩, an ⌥-click on Present).
  function present(fromStart = Boolean(window.event?.altKey)) {
    if (!slides().length) { toast("This deck has no slides to present.", { icon: "play" }); return; }
    presentSlides({ pages: () => pages, slides, start: fromStart ? 0 : state.slide, done: (index) => select(index) });
  }

  // ⌘B and ⌘I with words chosen, not being typed in (a text, a list, a title): all their
  // words bold (italic), or none when all are already, as Keynote does to a text box chosen.
  function emphasiseChosen(look) {
    const label = look === "bold" ? "Bold" : "Italic";
    // Several chosen: the words of all those that have words, as one -- all bold, or none.
    if (allOn()) {
      const worded = allBlocks().filter(({ block }) => WORDY.has(kindOf(block)));
      if (!worded.length) return false;
      const linesOf = (block) => (kindOf(block) === "bullets" ? bulletsText(block.bullets).split("\n") : [String(block[kindOf(block)] ?? "")]);
      const all = worded.flatMap(({ block }) => linesOf(block).map((line) => line.trim()));
      const made = emphasised(all, look);
      const picks = picksNow();
      keepAll = true;
      editSlide((s) => {
        let n = 0;
        for (const { region, index, block } of worded) {
          const b = blocksAt(s, region.key)[index], kind = kindOf(block);
          const lines = linesOf(block), mine = made.slice(n, n + lines.length);
          n += lines.length;
          if (!b || kindOf(b) !== kind) continue;
          if (kind === "bullets") b.bullets = bulletsFrom(lines.map((line, k) => /^\s*/.exec(line)[0] + mine[k]).join("\n"), true);
          else b[kind] = mine[0];
          delete b.placeholder;
        }
      }, { label });
      keepAll = false;
      markMany(picks, picks);
      return true;
    }
    const block = state.focus && blocksAt(slideAt() || {}, state.focus.region)[state.focus.index];
    if (block) {
      const kind = kindOf(block);
      if (!WORDY.has(kind) || !bulletsText(kind === "bullets" ? block.bullets : block[kind] ?? "").trim()) return false;
      editBlock(state.focus, (b) => {
        if (kindOf(b) !== kind) return;
        if (kind !== "bullets") { b[kind] = emphasised([String(b[kind] ?? "")], look)[0]; return; }
        const lines = bulletsText(b.bullets).split("\n");
        const made = emphasised(lines.map((line) => line.trim()), look);
        b.bullets = bulletsFrom(lines.map((line, n) => /^\s*/.exec(line)[0] + made[n]).join("\n"), true);
      }, { label });
      return true;
    }
    const key = state.field?.field;
    if (!key || typeof slideAt()?.[key] !== "string" || !slideAt()[key].trim()) return false;
    editSlide((s) => { s[key] = emphasised([s[key]], look)[0]; }, { label });
    return true;
  }

  // ⌘D (and Edit › Duplicate) duplicates what is chosen: a figure's shapes, the object on
  // the slide, else the slide.
  function duplicateChosen() {
    if (figure && figureBlock() && figure.parts.selected.length) { figure.parts.duplicate(); return; }
    // Several chosen (⌘A, ⇧-click): each copied after the last of them in its column, one step.
    if (allOn()) {
      const copies = picked();
      const columns = [...new Set(copies.map((copy) => copy.key))].map((key) => [key, copies.filter((copy) => copy.key === key).map((copy) => copy.index).sort((a, b) => a - b)]);
      allChosen = null;
      editSlide((s) => {
        for (const [key, mine] of columns) { const list = blocksAt(s, key); list.splice(mine.at(-1) + 1, 0, ...mine.map((index) => copyOf(list[index]))); }
      }, { label: `Duplicate ${copies.length} Objects` });
      const made = columns.flatMap(([key, mine]) => mine.map((_, n) => ({ region: key, index: mine.at(-1) + 1 + n })));
      // The copies are what is chosen, as Keynote chooses them.
      chooseMany(made);
      markMany(columns.flatMap(([key, mine]) => mine.map((index) => ({ region: key, index }))), made);
      placeChosen(); renderInspector(); reportFocus();
      return;
    }
    const block = state.focus && blocksAt(slideAt(), state.focus.region)[state.focus.index];
    if (block) insertBlock(kindOf(block), copyOf(block), { ...state.focus }, `Duplicate ${blockLabel(block)}`);
    else if (chosenSlides().length > 1) duplicateSlides(chosenSlides());
    else if (slides().length) duplicateSlide(state.slide);
  }

  // -- keys --
  document.addEventListener("keydown", (event) => {
    // A key something has taken already (Return that ended a title's typing, or ran the
    // palette's command) is done with: the slide does not take it again.
    if (!studio.active || event.defaultPrevented) return;
    const typing = typingNow() || document.querySelector(".scrim, .present, .menu");
    const mod = event.metaKey || event.ctrlKey;
    if (mod && event.key === "Enter") { event.preventDefault(); present(); return; }
    // Esc in a field of the inspector leaves it (what it takes back first, a number's typing,
    // it has taken): the next Esc is the slide's.
    if (event.key === "Escape" && !document.querySelector(".scrim, .present, .menu") && typingNow() && inspector.contains(document.activeElement)) {
      event.preventDefault();
      document.activeElement.blur();
      return;
    }
    if (typing) return;
    const key = event.key;
    // ⌥⌘I goes to the inspector, as Keynote's shows it; Esc there comes back to the slide.
    if (mod && event.altKey && key.toLowerCase() === "i") {
      event.preventDefault();
      const first = [...inspector.querySelectorAll("button:not(:disabled), input, select, textarea, [contenteditable=true], [tabindex='0']")].find((node) => node.offsetParent && node.tabIndex >= 0);
      // Ringed, as the keys brought it there (a web view rings nothing focused by a shortcut).
      if (first) {
        first.focus({ focusVisible: true });
        first.dataset.keyed = "";
        first.addEventListener("blur", () => { delete first.dataset.keyed; }, { once: true });
      }
      return;
    }
    // Keys in the inspector or the toolbar are theirs: a swatch focused is no slide's object to move.
    if (!mod && document.activeElement && document.activeElement !== document.body && !stage.contains(document.activeElement) && !railList.contains(document.activeElement)) {
      if (key === "Escape" && inspector.contains(document.activeElement)) { event.preventDefault(); document.activeElement.blur(); }
      return;
    }
    if (figure && figureBlock() && figure.parts.key(event)) return;
    if (mod && event.shiftKey && key.toLowerCase() === "n") { event.preventDefault(); newSlideLike(state.slide); }
    else if (mod && key.toLowerCase() === "d") { event.preventDefault(); duplicateChosen(); }
    // ⌘A outside a text field selects nothing on the page's own words.
    else if (mod && key.toLowerCase() === "a") { event.preventDefault(); chooseAll(); }
    else if (mod && !event.altKey && !event.shiftKey && ["b", "i"].includes(key.toLowerCase()) && emphasiseChosen(key.toLowerCase() === "b" ? "bold" : "italic")) event.preventDefault();
    else if (mod) return;
    // With a part of the slide chosen, ↑ and ↓ choose the one before or after it, ← and → the
    // one in the column beside: nothing changes. With ⌥ they move it (Arrange › Move Up and
    // Move Down): up and down its column, across to the next. A figure's part chosen, they
    // leave the slide alone. Else they turn slides.
    // Several chosen: with ⌥ the arrows move them all (moveAll); without, ↑ chooses the one
    // before the first of them and ↓ the one after the last, ← and → the one beside the first
    // or the last, as a Mac list's arrows go on from a choice of several.
    else if (key.startsWith("Arrow") && allOn()) {
      event.preventDefault();
      if (event.altKey) { moveAll(key); return; }
      const chosenNow = allBlocks(), regions = regionsOf(slideAt());
      const from = key === "ArrowUp" || key === "ArrowLeft" ? chosenNow[0] : chosenNow[chosenNow.length - 1];
      const all = regions.flatMap((region) => blocksAt(slideAt(), region.key).map((_, index) => ({ region: region.key, index })));
      const at = all.findIndex((stop) => stop.region === from.region.key && stop.index === from.index);
      const column = regions.findIndex((region) => region.key === from.region.key), beside = regions[column + (key === "ArrowRight" ? 1 : -1)];
      const next = key === "ArrowUp" ? all[at - 1] : key === "ArrowDown" ? all[at + 1]
        : beside && blocksAt(slideAt(), beside.key).length ? { region: beside.key, index: Math.min(from.index, blocksAt(slideAt(), beside.key).length - 1) } : null;
      const to = next || all[at];
      focusBlock(to.region, to.index);
    }
    else if (key.startsWith("Arrow") && state.focus) {
      event.preventDefault();
      if (figure && figureBlock() && figure.parts.selected.length) return;
      const at = state.focus, regions = regionsOf(slideAt()), count = blocksAt(slideAt(), at.region).length;
      const column = regions.findIndex((region) => region.key === at.region);
      const side = column + (key === "ArrowRight" ? 1 : key === "ArrowLeft" ? -1 : 0);
      if (!event.altKey) {
        if (key === "ArrowUp" || key === "ArrowDown") {
          const all = regions.flatMap((region) => blocksAt(slideAt(), region.key).map((_, index) => ({ region: region.key, index })));
          const next = all[all.findIndex((stop) => stop.region === at.region && stop.index === at.index) + (key === "ArrowUp" ? -1 : 1)];
          if (next) focusBlock(next.region, next.index);
        } else if (regions[side] && side !== column && blocksAt(slideAt(), regions[side].key).length) {
          focusBlock(regions[side].key, Math.min(at.index, blocksAt(slideAt(), regions[side].key).length - 1));
        }
        return;
      }
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
      if (toured && !state.field && toured.slide === state.slide && toured.region === state.focus?.region && toured.index === state.focus?.index) {
        tabOn({ kind: "block", ...state.focus }, event.shiftKey);
        return;
      }
      toured = null;
      const slide = slideAt();
      const stops = [
        // Its words, placeholders too (an empty title is written, and holds its place).
        ...["title", "words", "subtitle", "author", "date", "by"].filter((name) => (slide[name] || name in slide) && catalog.slide_keys[layoutOf(slide)].includes(name)).map((name) => ({ field: name })),
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
    // Return opens what is chosen with all its words chosen, as Keynote's does.
    else if (state.field && key === "Enter") { event.preventDefault(); openInline({ kind: "field", field: state.field.field }, { selectAll: true }); }
    // Just ended with Return, its words go on from where they were left: typed on at their
    // end, never over them.
    else if (state.field?.ended && (key === "Backspace" || (key.length === 1 && !event.altKey))) {
      event.preventDefault();
      openInline({ kind: "field", field: state.field.field });
      if (inline) { if (key === "Backspace") document.execCommand("delete"); else document.execCommand("insertText", false, key); }
    }
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
    // Esc leaves what is chosen -- and an object just added and still empty goes, whatever it is.
    else if (key === "Escape" && state.focus) { const at = state.focus; state.focus = null; leaveFigure(false); dropFresh(at); renderInspector(); placeChosen(); reportFocus(); }
    else if (key === "Enter" && state.focus) {
      event.preventDefault();
      const block = blocksAt(slideAt(), state.focus.region)[state.focus.index];
      // Return goes into what is chosen: its words, a table's first cell, a figure's first shape.
      if (block && INLINE.has(kindOf(block))) openInline({ kind: "block", ...state.focus }, { selectAll: true });
      else if (block && kindOf(block) === "table") openInline({ kind: "cell", ...state.focus, row: 0, col: 0 }, { selectAll: true });
      else if (block && kindOf(block) === "figure" && figure && figureBlock() === block) {
        const first = figure.parts.model?.nodes?.[0]?.id;
        if (first) figure.parts.select([first]);
      }
    } else if ((key === "Delete" || key === "Backspace") && state.focus) { event.preventDefault(); deleteBlock(state.focus); }
    else if ((key === "Delete" || key === "Backspace") && allOn()) { event.preventDefault(); deleteAll(); }
    else if (key === "Escape" && allChosen) { allChosen = null; placeChosen(); renderInspector(); reportFocus(); }
  });

  // -- the palette's commands, and following --
  // A page for each stage of a build is offered only where the deck has one: a list that
  // reveals its items a click at a time.
  const builds = () => pages.some((page) => page?.steps > 1) || slides().some((slide) => regionsOf(slide).some(({ key }) =>
    blocksAt(slide, key).some((block) => kindOf(block) === "bullets" && block.reveal)));
  studio.exports = [
    { format: "pdf", label: "PDF…", hint: "One page per slide, with embedded fonts",
      // Each stage of builds as the person last chose it for this deck.
      get options() {
        const key = `steps-${studio.file}`;
        return builds() ? [{ name: "steps", label: "Include each stage of builds", value: remembered(key, "0") === "1", onChange: (value) => remember(key, value ? "1" : "0") }] : [];
      } },
    { format: "pptx", label: "PowerPoint…", hint: "Editable shapes and text" },
    { format: "png", label: "Images…", icon: "image", hint: "A PNG or SVG image of each slide", choose: [{ format: "png", label: "PNG" }, { format: "svg", label: "SVG" }] },
  ];
  studio.present = () => present();
  studio.commands = () => [
    // The slides to go to: places, listed after every command (`later`).
    ...slides().map((slide, index) => ({ icon: "slide", label: `Slide ${index + 1}: ${slideTitle(slide)}`, later: true, run: () => select(index) })),
    // What the keys do (⇧⌘N, ⌘D, ⌫ in the slide list, the arrows), by name for the Mac
    // app's Slide and Edit menus. ⌘D in a field is the field's.
    { icon: "plus", label: "New Slide", keys: "⇧⌘N", run: () => newSlideLike(state.slide) },
    // The object chosen, by name: what its right-click menu does; then the slide's.
    ...clipCommands(),
    ...chosenCommands(),
    ...(slides().length ? slideCommands() : []),
    // Words being typed: the Mac app's Format menu's Bold, Italic, Code and Inline Equation,
    // and Link… (⌘B, ⌘I, ⌘E, ⌥⌘E and ⌘K are the field's own). Link… wants words chosen, or
    // the caret in a link.
    ...(inline?.area?.rich ? [["bold", "Bold", "b"], ["italic", "Italic", "i"], ["code", "Code", "e"], ["math", "Inline Equation", "e", true], ["link", "Link…", "k"]].map(([name, label, key, alt = false]) => ({
      icon: name, label, keys: `${alt ? "⌥" : ""}⌘${key.toUpperCase()}`,
      ...(name === "link" && !linkable() ? { disabled: true, hint: "Choose the words to link" } : {}),
      // As if its keys were pressed in the field, which knows what bold means there (a bold title).
      run: () => {
        const mac = /Mac|iP/.test(navigator.platform);
        inline?.area.focus();
        inline?.area.dispatchEvent(new KeyboardEvent("keydown", { key, code: `Key${key.toUpperCase()}`, metaKey: mac, ctrlKey: !mac, altKey: alt, bubbles: true, cancelable: true }));
      } })) : []),
    ...(state.slide < slides().length - 1 ? [{ icon: "down", label: "Go to Next Slide", run: () => select(state.slide + 1) }] : []),
    ...(state.slide > 0 ? [{ icon: "up", label: "Go to Previous Slide", run: () => select(state.slide - 1) }] : []),
    ...layouts.map((layout) => ({ icon: "plus", label: `New ${LAYOUT_NAMES[layout.name]} Slide`, hint: layout.note, run: () => addSlide(layout.name, state.slide + 1) })),
    // Only what can be done here: no layout the slide already has, nothing added where there is no room.
    ...(slides().length ? layouts.filter((layout) => layout.name !== layoutOf(slideAt())).map((layout) => ({ icon: "layout", label: `Layout: ${LAYOUT_NAMES[layout.name]}`, run: () => changeLayout(layout.name) })) : []),
    ...(regionsOf(slideAt()).length ? Object.entries(BLOCKS).filter(([, info]) => !info.hidden).map(([kind, info]) => ({ icon: info.icon, label: `Add ${info.label}${CHOOSE.has(kind) ? "…" : ""}`, hint: info.hint, run: () => insertBlock(kind) })) : []),
    ...catalog.looks.map((look) => ({ icon: "palette", label: `Look: ${lookName(look)}`, hint: look.note, run: () => { studio.change((d) => { d.deck ||= {}; setOption(d.deck, "look", look.name, "classic"); }); renderInspector(); } })),
    { icon: "theme", label: "Customise Theme…", run: () => customiseTheme(doc().deck || {}) },
    ...(figureBlock() ? FIGURE_EXPORTS.map(({ label, formats, hint }) => ({ icon: "export", label: `Export Figure as ${label}…`, hint, run: () => exportFigure(figure, formats) })) : []),
    { icon: "notes", label: state.notes ? "Hide Speaker Notes" : "Show Speaker Notes", run: () => showNotes(!state.notes) },
    { icon: "play", label: "Present", keys: "⌘↩", hint: "Full screen; X for the presenter view, with notes", run: () => present() },
    // In the toolbar's Export menu's order.
    { icon: "export", label: "Export as PDF…", hint: "One page per slide", run: () => studio.exportFiles(["pdf"]) },
    { icon: "export", label: "Export as PowerPoint…", hint: "A .pptx file of editable shapes and text", run: () => studio.exportFiles(["pptx"]) },
    { icon: "export", label: "Export as Images…", hint: "A PNG or SVG image of each slide", run: () => studio.exportFiles(["png"]) },
  ];
  // The slide's commands, named and keyed as its menus have them: ⌘D duplicates the object
  // chosen (named for it) or else the slides chosen; ⌫ deletes the slides while their list
  // has the keys. Each named for what it acts on is also the Mac menu's plain one (`also`).
  function slideCommands() {
    const typing = typingNow(), shapes = !typing && figure && figureBlock() && figure.parts.selected.length;
    const block = !typing && state.focus && blocksAt(slideAt(), state.focus.region)[state.focus.index];
    const picked = chosenSlides(), many = picked.length > 1 ? `${picked.length} Slides` : "Slide", own = Boolean(shapes || block);
    return [
      ...(own ? [{ icon: "duplicate", label: `Duplicate ${shapes ? (shapes > 1 ? `${shapes} Shapes` : "Shape") : blockLabel(block)}`, also: ["Duplicate"], keys: "⌘D", run: () => duplicateChosen() }] : []),
      { icon: "duplicate", label: `Duplicate ${many}`, also: [...(own || typing ? [] : ["Duplicate"]), "Duplicate Slide"], keys: own || typing ? undefined : "⌘D", run: () => duplicateSlide(state.slide) },
      { icon: "trash", label: `Delete ${many}`, also: ["Delete Slide"], keys: railList.contains(document.activeElement) ? "⌫" : undefined, run: () => deleteSlides(picked) },
    ];
  }
  // Cut and Copy of what is chosen, as ⌘X and ⌘C do them, named for it; Paste of what was.
  function clipCommands() {
    if (typingNow()) return [];
    const clip = clipOf();
    return [
      ...(clip ? [{ icon: "cut", label: `Cut ${clipName(clip)}`, keys: "⌘X", run: () => clipChosen(true) },
        { icon: "copy", label: `Copy ${clipName(clip)}`, keys: "⌘C", run: () => clipChosen(false) }] : []),
      // What was copied here, else what the clipboard holds (words, a picture's file name),
      // as ⌘V pastes it onto the slide.
      { icon: "paste", label: "Paste", keys: "⌘V", hint: clipboard ? clipName(clipboard) : "", run: () => (clipboard ? pasteClip(clipboard) : pasteFromClipboard()) },
    ];
  }
  function pasteFromClipboard() {
    navigator.clipboard?.readText().then((text) => {
      if (!text) return;
      const data = new DataTransfer();
      data.setData("text/plain", text);
      document.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
    }).catch(() => toast("Paste with ⌘V: the studio may not read the clipboard here.", { icon: "paste", seconds: 3 }));
  }
  // Words chosen in what is typed, or the caret in a link: what Link… acts on.
  function linkable() {
    const chosenWords = window.getSelection();
    if (!inline?.area || !chosenWords?.rangeCount || !inline.area.contains(chosenWords.anchorNode)) return false;
    return !chosenWords.isCollapsed || Boolean(chosenWords.anchorNode.parentElement?.closest("a"));
  }
  function chosenCommands() {
    // Several chosen: Arrange moves them all, where any can go.
    if (allOn() && !typingNow()) {
      const count = allBlocks().length;
      return [
        ...(moveAll("ArrowUp", true) ? [{ icon: "up", label: "Move Up", keys: "⌥↑", hint: `${count} objects`, run: () => moveAll("ArrowUp") }] : []),
        ...(moveAll("ArrowDown", true) ? [{ icon: "down", label: "Move Down", keys: "⌥↓", hint: `${count} objects`, run: () => moveAll("ArrowDown") }] : []),
        { icon: "trash", label: `Delete ${count} Objects`, keys: "⌫", run: () => deleteAll() },
      ];
    }
    const at = state.focus, block = at && !typingNow() ? blocksAt(slideAt(), at.region)[at.index] : null;
    if (!block) return [];
    const kind = kindOf(block), name = blockLabel(block), count = blocksAt(slideAt(), at.region).length;
    return [
      ...(kind === "text" ? [{ icon: "list", label: "Convert to List", run: () => restyle(at, "bulleted") }] : []),
      ...(kind === "bullets" ? [{ icon: "text", label: "Convert to Text", run: () => restyle(at, "text") }] : []),
      // As the Mac app's Arrange menu names them; the hint says what they move.
      ...(at.index > 0 ? [{ icon: "up", label: "Move Up", keys: "⌥↑", hint: name, run: () => moveBlock(at, { region: at.region, index: at.index - 1 }) }] : []),
      ...(at.index < count - 1 ? [{ icon: "down", label: "Move Down", keys: "⌥↓", hint: name, run: () => moveBlock(at, { region: at.region, index: at.index + 2 }) }] : []),
      { icon: "trash", label: `Delete ${name}`, keys: "⌫", run: () => deleteBlock(at) },
    ];
  }
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
  // Words typed, named by the words they are in ("Typing in “Second paragraph…”"), as every
  // typing is, wherever it is -- a title, a cell, code, a field; null where it is not words.
  const typing = (now, was = "") => {
    if (typeof now !== "string" && typeof was !== "string") return null;
    const first = plain(typeof now === "string" && now.trim() ? now : typeof was === "string" ? was : "").trim();
    return first ? `Typing in ${quoted(first)}` : "Typing";
  };
  // Of the fields an object is set by, those typed in (not chosen): their changes are typing.
  const TYPED_FIELDS = new Set(["description", "by", "title", "caption", "alt", "label", "footer"]);
  const blockLabel = (block) => blockName(block);
  // In the history, a figure by what it was added as: a Flow Chart (steps and decisions), a
  // Structure (structures alone).
  const objectName = (block) => {
    const nodes = kindOf(block) === "figure" && typeof block.figure === "object" ? block.figure?.nodes || [] : [];
    if (nodes.length && nodes.every((node) => node?.kind === "structure")) return "Structure";
    if (nodes.some((node) => ["terminal", "decision"].includes(node?.kind))) return "Flow Chart";
    return blockLabel(block);
  };
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
    // Customise…: the theme made a file of its own, the deck's palette taken into it.
    if (keys.includes("theme") && keys.every((key) => key === "theme" || key === "palette")) return typeof b.theme === "string" && /\.(ya?ml|json)$/i.test(b.theme) ? "Customise Theme" : "Change Theme";
    if (keys.length === 1 && TYPED_FIELDS.has(keys[0])) return typing(b[keys[0]], a[keys[0]]);
    return keys.length === 1 ? `Change ${DECK_NAMES[keys[0]] || keyTitle(keys[0])}` : "Change Design";
  }
  const SLIDE_WORDS = [["title", "Title"], ["subtitle", "Subtitle"], ["words", "Text"], ["author", "Author"], ["date", "Date"]];
  const SLIDE_NAMES = { widths: "Column Widths", split: "Column Widths", align: styleName("align"), dark: "Text Colour", shade: "Background", background: "Background", by: "Attribution" };
  function slideChange(a, b) {
    if (layoutOf(a) !== layoutOf(b)) return "Change Layout";
    for (const [key, name] of SLIDE_WORDS) if (!same(a[key], b[key])) return typing(b[key], a[key]) || `Edit ${name}`;
    if (!same(a.notes, b.notes)) return typing(b.notes, a.notes) || "Edit Notes";
    if (!same(a.footnotes, b.footnotes)) {
      const before = [a.footnotes ?? []].flat(), after = [b.footnotes ?? []].flat();
      if (before.length === after.length) { const n = after.findIndex((note, i) => !same(note, before[i])); return typing(after[n], before[n]) || "Edit Footnotes"; }
      return after.length > before.length ? "Add Footnote" : "Delete Footnote";
    }
    const old = partsOf(a), next = partsOf(b);
    const found = (list, item) => list.some((other) => same(other.block, item.block));
    // The objects of one not in the other, counted: of two alike, the one more is the one added.
    const beyond = (list, other) => {
      const pool = [...other];
      return list.filter((item) => { const at = pool.findIndex((one) => same(one.block, item.block)); if (at < 0) return true; pool.splice(at, 1); return false; });
    };
    if (next.length > old.length) {
      const added = beyond(next, old)[0] || next[next.length - 1];
      return `${found(old, added) ? "Duplicate" : "Add"} ${objectName(added.block)}`;
    }
    if (next.length < old.length) { const gone = beyond(old, next)[0] || old[old.length - 1]; return `Delete ${objectName(gone.block)}`; }
    const pairs = next.map((item, k) => [old[k], item]).filter(([was, now]) => !same(was.block, now.block) || was.region !== now.region);
    if (pairs.length && pairs.every(([, now]) => found(old, now))) return `Move ${blockLabel(pairs[0][1].block)}`;
    if (pairs.length === 1) return blockChange(pairs[0][0].block, pairs[0][1].block);
    if (pairs.length > 1) return `Edit ${pairs.length} Objects`;
    const keys = differing(a, b).filter((key) => key !== "body" && key !== "left" && key !== "right" && key !== "columns");
    if (keys.length && keys.every((key) => ["background", "shade", "dark"].includes(key)) && keys.some((key) => key !== "dark")) return "Change Background";
    return keys.length === 1 ? `Change ${SLIDE_NAMES[keys[0]] || keyTitle(keys[0])}` : "Edit Slide";
  }
  const BLOCK_NAMES = { description: "Description", align: "Alignment", size: "Font Size", turn: "Rotation", colour: "Colour", muted: "Colour", numbered: "Numbering", plain: "Bullets",
    reveal: "Build", header: "Header Row", by: "Attribution", title: "Heading", aspect: "Aspect Ratio", arrow_colour: "Arrow Colour" };
  function blockChange(a, b) {
    const kind = kindOf(b), name = blockLabel(b), keys = differing(a, b).filter((key) => key !== "placeholder");
    if (!keys.length) return `Edit ${name}`;
    // A placeholder (an empty text or list) a new object took the place of: that object added.
    if (kind !== kindOf(a) && blank(a)) return `Add ${objectName(b)}`;
    if (keys.length === 1 && keys[0] === "width") return b.width == null ? `Reset ${name} Size` : `Resize ${name}`;
    if (keys.includes(kind)) {
      if (kind === "figure" && typeof a.figure === "object" && typeof b.figure === "object") return figureChange(a.figure, b.figure);
      if (kind === "image") return "Change Picture";
      if (kind === "figure" && typeof b.figure === "string") return "Change Figure Source";
      if (kind === "table") return tableChange(a.table, b.table);
      const items = (block) => (Array.isArray(block.bullets) ? block.bullets.flat(Infinity) : [block.bullets]);
      if (kind === "bullets") {
        if (items(b).length > items(a).length) return "Add Item";
        if (items(b).length < items(a).length) return "Delete Item";
      }
      // The same words in another look (bold, a colour, a link): their format changed.
      const words = (block) => readable(JSON.stringify(block[kind] ?? ""));
      if (["text", "bullets", "quote", "callout"].includes(kind) && words(a) === words(b)) return `Format ${name}`;
      // Words typed: named by the words they are in -- a list's, by the item typed in.
      if (kind === "bullets") { const n = items(b).findIndex((item, i) => !same(item, items(a)[i])); return typing(items(b)[n], items(a)[n]) || `Edit ${name}`; }
      if (["text", "quote", "callout", "code", "math"].includes(kind)) return typing(b[kind], a[kind]) || `Edit ${name}`;
      return `Edit ${name}`;
    }
    if (keys.length === 1 && TYPED_FIELDS.has(keys[0]) && (typeof a[keys[0]] === "string" || typeof b[keys[0]] === "string")) return typing(b[keys[0]], a[keys[0]]);
    // A figure's swapping to fit, as its switch says.
    if (keys.length === 1 && keys[0] === "turn") return b.turn === false ? "Don’t Swap Rows and Columns to Fit" : "Swap Rows and Columns to Fit";
    return `Change ${BLOCK_NAMES[keys[0]] || keyTitle(keys[0])}`;
  }
  // A table's change by what it did: a row or column more or fewer, else a cell typed in.
  function tableChange(a, b) {
    const rows = (table) => (Array.isArray(table) ? table : []), columns = (table) => Math.max(0, ...rows(table).map((row) => (Array.isArray(row) ? row.length : 1)));
    if (rows(b).length !== rows(a).length) return rows(b).length > rows(a).length ? "Add Row" : "Delete Row";
    if (columns(b) !== columns(a)) return columns(b) > columns(a) ? "Add Column" : "Delete Column";
    for (const [r, row] of rows(b).entries()) for (const [c, cell] of (Array.isArray(row) ? row : [row]).entries()) {
      const was = rows(a)[r]?.[c];
      if (!same(cell, was)) return typing(String(cell ?? ""), String(was ?? "")) || "Edit Cell";
    }
    return "Edit Cell";
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
    let added = [...nodesB.keys()].filter((id) => !nodesA.has(id)), removed = [...nodesA.keys()].filter((id) => !nodesB.has(id));
    // A shape named for its new words (its id made from them) is the same shape, renamed.
    if (added.length === 1 && removed.length === 1 && same(nodesA.get(removed[0]).kind, nodesB.get(added[0]).kind)) {
      nodesB.set(removed[0], nodesB.get(added[0]));
      nodesB.delete(added[0]);
      added = [];
      removed = [];
    }
    if (added.length === 1 && !removed.length) return "Add Shape";
    if (removed.length === 1 && !added.length) return `Delete ${call(removed[0])}`;
    if (added.length > 1 && !removed.length) return `Add ${added.length} Shapes`;
    if (removed.length > 1 && !added.length) return `Delete ${removed.length} Shapes`;
    if (added.length || removed.length) return "Edit Shapes";
    const changed = [...nodesB.keys()].filter((id) => !same(nodesA.get(id), nodesB.get(id)));
    if (changed.length === 1) {
      const id = changed[0], was = nodesA.get(id), now = nodesB.get(id);
      if (!same(was.label, now.label)) {
        // The same words in another look (a colour, code) are the label's format changed.
        if (was.label && named(was, id) === named(now, id)) return `Format ${named(now, id)}`;
        return `Typing in ${named(now.label ? now : was, id)}`;
      }
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
    // (Those typed while it was on its way too, typed again once it is open: shell.js's create.)
    studio.takesKeys = true;
    let started = false;
    // (What is typed before it is drawn is kept for it.)
    const open = openSoon(() => ({ kind: "field", field: layoutOf(slides()[0]) === "statement" ? "words" : "title" }), null);
    studio.on("drawn", () => {
      if (started || !slides().length) return;
      started = true;
      setTimeout(open, 60);
    });
  }
  // An undo waits for a figure's edits still on their way (shell.js).
  studio.settled = () => figure?.parts.idle?.() ?? Promise.resolve();
  // Drawings (and what they say) are kept by slide, not by place: when slides are added,
  // removed or moved, each keeps its own until the next drawing comes, and a new slide
  // shows as not drawn yet -- never another slide's drawing.
  function followSlides(before, after) {
    if (before === after || !pages.length) return;
    let start = 0, end = 0;
    while (start < before.length && start < after.length && same(before[start], after[start])) start += 1;
    while (end < before.length - start && end < after.length - start
      && same(before[before.length - 1 - end], after[after.length - 1 - end])) end += 1;
    const was = before.length - start - end, now = after.length - start - end;
    if (!was && !now) return;
    const used = new Set();
    const found = after.slice(start, start + now).map((slide) => {
      const at = before.slice(start, start + was).findIndex((old, k) => !used.has(k) && same(old, slide));
      if (at >= 0) used.add(at);
      return at >= 0 ? start + at : -1;
    });
    if (was === now && found.some((at) => at < 0)) return;  // edited in place: as now
    const from = (index) => (index < start ? index : index >= start + now ? index - now + was : found[index - start]);
    const old = pages;
    pages = after.map((_, index) => (from(index) >= 0 ? old[from(index)] : undefined));
    messages = messages.filter((m) => { const n = Number(/^slide(\d+)$/.exec(m.page || "")?.[1]); return !n || from(n - 1) === n - 1; });
  }
  studio.on("change", ({ quiet, source, who, before, entry, base, incoming, merged }) => {
    clearTimeout(settleTimer);
    undoing = source === "history";
    const was = lastDoc;
    lastDoc = doc();
    followSlides(was?.slides || [], slides());
    if (source === "remote") figureKept(was, who);
    if (source === "history" || source === "remote") followChange(was, who, source === "remote");
    // Undone or redone, the deck goes to the slide the change was made on.
    if (source === "history" && Number.isInteger(entry?.where) && entry.where !== state.slide && entry.where < slides().length) {
      closeInline();
      leaveFigure(false);
      state.slide = entry.where;
      state.focus = null;
    }
    settling = false;
    if (state.slide >= slides().length) state.slide = Math.max(0, slides().length - 1);
    if (source === "history" && !inline) chooseChanged(was, entry);
    pending = true;
    if (source === "remote" && before) flash(before, who);
    if (!quiet) { renderRail(); renderInspector(); renderStage(); renderBar(); }
    // A slide not drawn yet (made with the studio away) shows its words as they are typed.
    else if (!pages[state.slide]?.svg) { renderRail(); renderStage(); }
    if (source === "history" || source === "remote") {
      refreshInline(source === "history", { base, incoming, merged });
      if (document.activeElement === notesArea) notesChanged(source === "history");
      if (source === "history") figure?.parts.closeInline(false);
    }
    if (source === "remote") { lastWho = who; shapesBack(was, who); }
    if (figure && source !== "edit") {
      if (source === "remote") shapeGone(was);
      // (Its words as they now are shown in the field being typed in, too.)
      if (figureBlock() && editable(figureBlock())) figure.parts.act({ do: "read" }, { select: false, fresh: true });
      else leaveFigure();
    }
    pageNode?.classList.add("pending");
    undoing = false;
  });
  // What a merge kept of what is being edited here (session.js's "merged"): another's
  // deleting it, or their words written over the words typed, came to nothing here, so
  // without a word the change would seem never to have been made.
  const whose = (who) => {
    const name = nameOf(who);
    return `${["Someone", "Another app", "An agent"].includes(name) ? name[0].toLowerCase() + name.slice(1) : name}'s`;
  };
  studio.on("merged", ({ notes }) => {
    const slide = slideAt();
    // (A figure's shape typed in on the slide is the figure being edited.)
    const shaping = Boolean(figure?.parts.inline) && figure.slide === state.slide;
    const editing = inline || shaping || inspectorBody.contains(document.activeElement);
    if (!slide || !editing) return;
    const at = inline?.at || state.focus || (shaping ? { region: figure.region, index: figure.index } : null);
    const block = at && partsOf(slide).find((item) => item.region === at.region && item.index === at.index)?.block;
    const typed = [inline?.area, document.activeElement].map((field) => (typeof field?.value === "string" ? field.value : "")).join("\n");
    for (const note of notes) {
      if (note.kept !== undefined && block && follows([note.kept], [block])[0] === 0) {
        toast(`${nameOf(note.by)} deleted ${editedHere(named(block, { the: true }))}. It stays.`, { icon: "info", seconds: 6 });
      } else if (note.kept !== undefined && follows([note.kept], [slide])[0] === 0) {
        toast(`${nameOf(note.by)} deleted the slide you're editing. It stays.`, { icon: "info", seconds: 6 });
      } else if (note.rewritten !== undefined && note.typed && typed.includes(note.typed)) {
        toast(`Your words and ${whose(note.by)} were both kept.`, { icon: "info", seconds: 6 });
      } else continue;
      return;
    }
  });
  // Words typed here that another typed too, at the same place (a space both typed to start
  // a word), taken as one by the merge: the editor puts its own back (caretMerged).
  studio.on("absorbed", ({ base, incoming }) => refreshInline(false, { base, incoming, merged: true }));
  studio.on("drawing", () => { pending = true; });
  studio.on("drawn", (result) => {
    pending = !result.latest || Boolean(result.unfinished);
    if (result.latest && !result.unfinished) {
      settling = false;
      clearTimeout(settleTimer);
      // A figure being edited, drawn in the layout that suits it best once the edits stop,
      // lands there: its parts glide, never jump.
      if (result.info?.unsettled) settleTimer = setTimeout(() => { settling = true; if (figureBlock()) figure.parts.settles(); studio.requestDraw(0); }, 1200);
    }
    pages = result.pages;
    drawnMessages = result.messages || [];
    // Swapping asked for a figure arranged by hand, and nothing to gain by it: said, as the
    // drawing does not change.
    if (swapAsked && result.latest && !result.unfinished && !result.info?.unsettled) {
      const page = swapAsked;
      swapAsked = null;
      if (!drawnMessages.some((m) => m.page === page && /rows and columns (were )?swapped|had their rows and columns swapped/.test(m.text))) {
        toast("Already drawn as large as it can be: swapping its rows and columns would not make it larger.", { icon: "info", seconds: 5 });
      }
    }
    sayMessages();
    renderRail();
    renderStage();
    readSlideAhead();
    if (mathNotes && document.contains(inspectorBody.querySelector(".math-notes"))) mathNotes();
    if (figure && typeof figureBlock()?.figure === "string") figure.parts.act({ do: "read" }, { select: false });
    // The panel's colours drawn again when the theme's change (its palette edited in its own
    // tab): the named colours, the tones and the palette's own order, as the swatches show them.
    const key = JSON.stringify([studio.info?.palette || {}, studio.info?.tones, studio.info?.order, studio.info?.own]);
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

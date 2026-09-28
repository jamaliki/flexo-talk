// The deck editor: slides on the left, the slide drawn in the middle, its parts on
// the right. Everything edits the deck document (see flexo_talk.document); the
// server draws each changed slide and the page shows it as it comes back.

import { h, clear, icon, ui, menu, dialog, toast } from "/static/studio/studio.js";

const BLOCKS = {
  bullets: { icon: "list", label: "List", hint: "Bullets or numbers, nested" },
  text: { icon: "text", label: "Text", hint: "A paragraph" },
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

const LAYOUT_ICONS = {
  content: "slide", "two-columns": "twocol", columns: "columns", figure: "figure", title: "title",
  section: "section", statement: "statement", agenda: "agenda", blank: "blank",
};
const LAYOUT_NAMES = {
  content: "Content", "two-columns": "Two columns", columns: "Columns", figure: "Figure", title: "Title",
  section: "Section", statement: "Statement", agenda: "Agenda", blank: "Blank",
};
const WORDLESS = new Set(["title", "section", "statement", "agenda"]);
const TONES = ["accent", "accent2", "accent3", "accent4", "accent5", "accent6"];

let serial = 0;

const NEW_SLIDES = {
  content: () => ({ title: "A new slide", body: [{ bullets: ["The first point", "The second point"] }] }),
  "two-columns": () => ({ layout: "two-columns", title: "Two sides", left: [{ bullets: ["On the left"] }], right: [{ text: "On the right." }] }),
  columns: () => ({ layout: "columns", title: "Three things", columns: [[{ text: "**One**" }], [{ text: "**Two**" }], [{ text: "**Three**" }]] }),
  figure: () => ({ layout: "figure", title: "The model", body: [NEW_BLOCKS.figure()] }),
  title: () => ({ layout: "title", title: "A talk worth giving", subtitle: "What we found", author: "", date: "" }),
  section: () => ({ layout: "section", title: "Part two" }),
  statement: () => ({ layout: "statement", words: "One sentence that [matters]{accent}." }),
  agenda: () => ({ layout: "agenda" }),
  blank: () => ({ layout: "blank", body: [{ text: "Anything at all." }] }),
};

const NEW_BLOCKS = {
  bullets: () => ({ bullets: ["The first point", "The second point"] }),
  text: () => ({ text: "A paragraph of words, with *emphasis* and $\\mathrm{maths}$." }),
  figure: () => ({ figure: { figure: { id: `figure-${Date.now().toString(36)}${serial++}` }, nodes: [
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
  if (WORDLESS.has(layout)) return [];
  if (layout === "two-columns") return [{ key: "left", label: "Left", svg: "left" }, { key: "right", label: "Right", svg: "right" }];
  if (layout === "columns") return (slide.columns || []).map((_, i) => ({ key: `columns.${i}`, label: `Column ${i + 1}`, svg: `column${i + 1}` }));
  return [{ key: "body", label: layout === "figure" ? "Figure" : "Body", svg: "body" }];
}

function blocksAt(slide, key, create = false) {
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
    case "table": return Array.isArray(value) ? `${value.length} rows × ${Math.max(0, ...value.map((row) => row.length))} columns` : "";
    case "stats": return Array.isArray(value) ? value.map((item) => item?.value ?? item?.[0] ?? item).join("  ·  ") : "";
    case "gallery": { const n = Array.isArray(value) ? value.length : 0; return `${n} picture${n === 1 ? "" : "s"}`; }
    case "figure": return typeof value === "string" ? value : `Inline · ${(value?.nodes || []).length} parts`;
    case "image": case "plot": return value || "Not chosen yet";
    case "callout": return plain(block.title) || plain(value);
    default: return plain(value);
  }
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
    if (level === stack.length) {
      const nested = [];
      stack[level - 1].push(nested);
      stack.push(nested);
    }
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

// Where a message points: slides[3].left[1] -> {slide: 3, region: "left", index: 1}.
function placeOf(where) {
  const match = /slides\[(\d+)\](?:\.(body|left|right|columns\[(\d+)\])\[(\d+)\])?/.exec(where || "");
  if (!match) return null;
  const region = match[2] ? (match[3] !== undefined ? `columns.${match[3]}` : match[2]) : null;
  return { slide: Number(match[1]), region, index: match[4] !== undefined ? Number(match[4]) : null };
}

// -- glyphs ---------------------------------------------------------------------------

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

// -- the editor -----------------------------------------------------------------------

export function mount(studio, main) {
  document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/editor.css" }));
  const catalog = studio.catalog;
  const state = { slide: 0, focus: null, tab: "slide", notes: remembered("notes", "1") === "1" };
  let pages = [];
  let messages = [];
  let drawnVersion = 0;
  let pending = false;
  let seconds = 0;
  const thumbs = new Map();   // hash -> object URL

  studio.hints = () => ({ focus: state.slide });
  const doc = () => studio.doc;
  const slides = () => doc().slides || [];
  const slideAt = (d = doc()) => (d.slides || [])[state.slide];

  // Changes to the current slide, and to one of its blocks.
  const editSlide = (mutate, options = {}) => studio.change((d) => { const slide = (d.slides || [])[state.slide]; if (slide) mutate(slide, d); }, options);
  const editBlock = (place, mutate, options = {}) => editSlide((slide) => {
    const block = blocksAt(slide, place.region)[place.index];
    if (block) mutate(block, slide);
  }, { quiet: true, ...options });

  // -- the frame --
  const railList = h("div.rail-list.scroll-thin");
  const railCount = h("span.count");
  const rail = h("aside.panel.rail", {},
    h("div.panel-head", {}, h("span.panel-title", {}, "Slides "), railCount, h("div.spacer"),
      ui.button("", (event) => addSlideMenu(event.currentTarget, state.slide + 1), { kind: "ghost", icon: "plus", small: true, title: "Add a slide" })),
    h("div.panel-body.scroll-thin", {}, railList));

  const stage = h("div.stage.deck-stage.scroll-thin");
  const notesArea = ui.textarea({ rows: 3, placeholder: "What to say on this slide — kept as the speaker notes", onInput: (text) =>
    editSlide((slide) => setOption(slide, "notes", text), { quiet: true, merge: `notes-${state.slide}` }) });
  const notes = h(`div.notes${state.notes ? ".open" : ""}`, {},
    h("div.notes-head", { onclick: () => { state.notes = !state.notes; remember("notes", state.notes ? "1" : "0"); notes.classList.toggle("open", state.notes); } },
      icon("chevron", { class: "caret" }), icon("notes"), "Speaker notes"),
    h("div.notes-body", {}, notesArea));
  const center = h("section.deck-center", {}, stage, notes);

  const inspectorTabs = h("div.insp-tabs");
  const inspectorBody = h("div.panel-body.scroll-thin");
  const inspector = h("aside.panel.inspector", {}, h("div.panel-head", {}, inspectorTabs), inspectorBody);
  const root = h("div.deck", {}, rail, center, inspector);
  clear(main, root);

  // -- the bar --
  studio.tools.append(
    ui.button("Present", () => present(), { kind: "ghost", icon: "play", title: "Present from this slide (⌘⏎)" }),
    ui.button("Export", (event) => menu(event.currentTarget, [
      { icon: "export", label: "PowerPoint", hint: "Native, editable shapes and text", run: () => studio.exportFiles(["pptx"]) },
      { icon: "export", label: "PDF", hint: "A page per slide, fonts embedded", run: () => studio.exportFiles(["pdf"]) },
      { icon: "image", label: "PNG per slide", run: () => studio.exportFiles(["png"]) },
      { icon: "image", label: "SVG per slide", run: () => studio.exportFiles(["svg"]) },
      "-",
      { icon: "export", label: "Everything", hint: "PPTX, PDF, SVG and PNG", run: () => studio.exportFiles(["pptx", "pdf", "svg", "png"]) },
    ], { align: "end" }), { kind: "ghost", icon: "export" }),
  );

  // -- slides: add, move, remove --
  function addSlideMenu(anchor, at) {
    menu(anchor, [{ title: "New slide" }, ...catalog.layouts.map((layout) => ({
      icon: LAYOUT_ICONS[layout.name], label: LAYOUT_NAMES[layout.name], hint: layout.note,
      run: () => addSlide(layout.name, at),
    }))]);
  }

  function addSlide(layout, at = slides().length) {
    studio.change((d) => { d.slides ||= []; d.slides.splice(at, 0, NEW_SLIDES[layout]()); });
    select(at);
  }

  function moveSlide(from, to) {
    if (from === to || to < 0 || to >= slides().length) return;
    studio.change((d) => { const [slide] = d.slides.splice(from, 1); d.slides.splice(to, 0, slide); });
    select(to);
  }

  function slideMenu(anchor, index) {
    const count = slides().length;
    menu(anchor, [
      { icon: "plus", label: "New slide after", run: () => addSlideMenu(anchor, index + 1) },
      { icon: "copy", label: "Duplicate", run: () => { studio.change((d) => { d.slides.splice(index + 1, 0, structuredClone(d.slides[index])); }); select(index + 1); } },
      "-",
      { icon: "up", label: "Move up", run: () => moveSlide(index, index - 1), disabled: index === 0 },
      { icon: "down", label: "Move down", run: () => moveSlide(index, index + 1), disabled: index === count - 1 },
      "-",
      { icon: "trash", label: "Delete", danger: true, run: () => { studio.change((d) => { d.slides.splice(index, 1); }); select(Math.min(index, count - 2)); } },
    ].filter((item) => item === "-" || !item.disabled));
  }

  function select(index, focus = null) {
    state.slide = Math.max(0, Math.min(index, slides().length - 1));
    state.focus = focus;
    renderRail();
    renderStage();
    renderInspector();
    railList.querySelector(".thumb.on")?.scrollIntoView({ block: "nearest" });
    if (pages[state.slide]?.stale) studio.requestDraw(0);
  }

  // -- the rail --
  let dragFrom = null;

  function thumbUrl(page) {
    if (!page?.svg) return null;
    if (!thumbs.has(page.hash)) thumbs.set(page.hash, URL.createObjectURL(new Blob([page.svg], { type: "image/svg+xml" })));
    return thumbs.get(page.hash);
  }

  function moreButton(index) {
    const button = ui.button("", (event) => { event.stopPropagation(); slideMenu(event.currentTarget, index); }, { kind: "ghost", icon: "more", small: true, title: "Slide actions" });
    button.classList.add("more");
    return button;
  }

  function renderRail() {
    const list = slides();
    railCount.textContent = list.length ? `· ${list.length}` : "";
    railCount.className = "count panel-title";
    clear(railList, list.map((slide, index) => {
      const page = pages[index];
      const url = thumbUrl(page);
      const own = messages.filter((m) => m.page === `slide${index + 1}` && m.severity !== "note");
      const worst = own.some((m) => m.severity === "error") ? "error" : own.length ? "warning" : null;
      const node = h(`div.thumb${index === state.slide ? ".on" : ""}${page?.stale ? ".stale" : ""}`, {
        draggable: true, title: plain(slide.title || slide.words) || LAYOUT_NAMES[layoutOf(slide)],
        onclick: () => select(index),
        oncontextmenu: (event) => { event.preventDefault(); slideMenu({ x: event.clientX, y: event.clientY }, index); },
        ondragstart: (event) => { dragFrom = index; node.classList.add("dragging"); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(index)); },
        ondragend: () => { dragFrom = null; node.classList.remove("dragging"); railList.querySelectorAll(".drop-before,.drop-after").forEach((el) => el.classList.remove("drop-before", "drop-after")); },
        ondragover: (event) => {
          if (dragFrom === null) return;
          event.preventDefault();
          const box = node.getBoundingClientRect();
          const after = event.clientY > box.top + box.height / 2;
          railList.querySelectorAll(".drop-before,.drop-after").forEach((el) => el.classList.remove("drop-before", "drop-after"));
          node.classList.add(after ? "drop-after" : "drop-before");
        },
        ondrop: (event) => {
          if (dragFrom === null) return;
          event.preventDefault();
          const after = node.classList.contains("drop-after");
          let to = index + (after ? 1 : 0);
          if (dragFrom < to) to -= 1;
          moveSlide(dragFrom, to);
        },
      },
      h("div.num", {}, index + 1),
      h("div.frame", {},
        url ? h("img", { src: url, alt: "", draggable: false }) : h("div.placeholder", {}, plain(slide.title || slide.words) || LAYOUT_NAMES[layoutOf(slide)]),
        worst ? h(`div.badge.${worst}`, { title: own.map((m) => m.text).join("\n") }, icon(worst === "error" ? "close" : "warning", { weight: "2" })) : null,
        page?.steps > 1 ? h("div.steps", { title: "Revealed one item at a time" }, `${page.steps} steps`) : null,
        moreButton(index)));
      return node;
    }), h("div.rail-add", {}, ui.button("Add slide", (event) => addSlideMenu(event.currentTarget, slides().length), { kind: "ghost", icon: "plus", small: true })));
  }

  // -- the stage --
  const hover = h("div.hit.hover", { hidden: true });
  const chosen = h("div.hit.selected", { hidden: true }, h("span.hit-label"));
  let pageNode = null;

  function renderStage() {
    const list = slides();
    notesArea.value = slideAt()?.notes || "";
    requestAnimationFrame(() => { notesArea.style.height = "auto"; notesArea.style.height = `${notesArea.scrollHeight + 2}px`; });
    if (!list.length) {
      notes.hidden = true;
      clear(stage, h("div.stage-empty", {}, h("h2", {}, "An empty deck"), h("div", {}, "Start with a slide:"),
        h("div.layout-grid", {}, catalog.layouts.map((layout) => h("button.layout-card", { type: "button", onclick: () => addSlide(layout.name, 0) },
          glyph(layout.name), h("span.name", {}, LAYOUT_NAMES[layout.name]), h("span.note", {}, layout.note))))));
      return;
    }
    notes.hidden = false;
    const page = pages[state.slide];
    pageNode = h(`div.slide-page${page?.error ? ".error" : ""}${pending || page?.stale ? ".pending" : ""}`);
    if (page?.svg) pageNode.innerHTML = page.svg.replace(/^<\?xml[^>]*>\s*/, "");
    else pageNode.append(h("div.placeholder", { style: { display: "grid", placeItems: "center", height: "100%", color: "var(--ink-3)", lineHeight: 1.4 } }, h("div.spinner")));
    const svg = pageNode.querySelector("svg");
    if (svg) { svg.removeAttribute("width"); svg.removeAttribute("height"); svg.setAttribute("preserveAspectRatio", "xMidYMid meet"); }
    pageNode.append(hover, chosen);
    pageNode.addEventListener("mousemove", onHover);
    pageNode.addEventListener("mouseleave", () => { hover.hidden = true; });
    pageNode.addEventListener("click", onPick);
    const own = messages.filter((m) => m.page === `slide${state.slide + 1}`);
    const slide = slideAt();
    clear(stage, h("div.slide-wrap", {}, pageNode,
      h("div.slide-meta", {},
        glyph(layoutOf(slide)), h("span", {}, `Slide ${state.slide + 1} of ${list.length} · ${LAYOUT_NAMES[layoutOf(slide)]}`),
        page?.steps > 1 ? h("span.chip", {}, icon("reveal"), `${page.steps} steps`) : null,
        h("span.timing", {}, pending ? h("span.row", {}, h("span.spinner"), "Drawing…") : seconds ? `drawn in ${(seconds * 1000).toFixed(0)} ms` : "")),
      own.length ? h("div.slide-messages.messages", {}, own.map(messageView)) : null));
    fitStage();
    placeChosen();
  }

  function messageView(message) {
    const place = placeOf(message.where);
    const link = place && place.region !== null;
    return h(`div.message.${message.severity}${link ? ".link" : ""}`, {
      onclick: () => { if (link) focusBlock(place.region, place.index); } },
    icon(message.severity === "error" ? "error" : message.severity === "note" ? "info" : "warning"),
    h("div", {}, message.text, message.where ? h("div.where", {}, message.where) : null));
  }

  function fitStage() {
    const room = stage.getBoundingClientRect();
    const width = Math.max(320, Math.min(room.width - 80, (room.height - 150) * 16 / 9));
    stage.style.setProperty("--slide-max", `${width}px`);
  }
  new ResizeObserver(() => { fitStage(); placeChosen(); }).observe(stage);

  const PART = /^slide(\d+)\.(body|left|right|column(\d+))\.(\d+)(?:\.|$)/;
  const WORDS = /^slide(\d+)\.(title|subtitle|byline|footnote\d+|footer)$/;

  // What was pointed at: the block (or words) an element belongs to, or failing that
  // the smallest block whose extent holds the point (the space inside a figure).
  function partAt(event) {
    const direct = partOf(event.target);
    if (direct || !pageNode) return direct;
    let best = null;
    for (const node of pageNode.querySelectorAll("[id]")) {
      if (!/^slide\d+\.(body|left|right|column\d+)\.\d+$/.test(node.id)) continue;
      const box = node.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) continue;
      const area = box.width * box.height;
      if (!best || area < best.area) best = { node, area };
    }
    return best ? partOf(best.node) : null;
  }

  function partOf(target) {
    for (let node = target; node && node !== pageNode; node = node.parentNode) {
      const id = node.id || "";
      const part = PART.exec(id);
      if (part) {
        const region = part[3] ? `columns.${Number(part[3]) - 1}` : part[2];
        const prefix = `slide${part[1]}.${part[2]}.${part[4]}`;
        return { kind: "block", region, index: Number(part[4]), id: prefix };
      }
      const words = WORDS.exec(id);
      if (words) return { kind: "words", field: words[2], id };
    }
    return null;
  }

  function boxOf(id) {
    const target = pageNode && [...pageNode.querySelectorAll("[id]")].find((el) => el.id === id);
    if (!target) return null;
    const outer = pageNode.getBoundingClientRect(), inner = target.getBoundingClientRect();
    if (!inner.width && !inner.height) return null;
    return { left: inner.left - outer.left - 4, top: inner.top - outer.top - 4, width: inner.width + 8, height: inner.height + 8 };
  }

  function place(node, box) {
    node.hidden = !box;
    if (box) Object.assign(node.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` });
  }

  function onHover(event) {
    const part = partAt(event);
    place(hover, part && boxOf(part.id));
  }

  function onPick(event) {
    const part = partAt(event);
    if (!part) { state.focus = null; placeChosen(); renderInspector(); return; }
    if (part.kind === "block") focusBlock(part.region, part.index);
    else {
      state.tab = "slide";
      renderInspector();
      const field = part.field.startsWith("footnote") ? "footnotes" : part.field === "byline" ? "author" : part.field === "footer" ? null : part.field;
      if (part.field === "footer") { state.tab = "deck"; renderInspector(); inspectorBody.querySelector("[data-field=footer] textarea")?.focus(); return; }
      const input = inspectorBody.querySelector(`[data-field="${field}"] textarea, [data-field="${field}"] input`) ||
        inspectorBody.querySelector('[data-field="words"] textarea');
      input?.focus();
    }
  }

  function placeChosen() {
    const focus = state.focus;
    if (!focus || !pageNode) { chosen.hidden = true; return; }
    const region = regionsOf(slideAt()).find((r) => r.key === focus.region);
    const box = region && boxOf(`slide${state.slide + 1}.${region.svg}.${focus.index}`);
    place(chosen, box);
    const block = blocksAt(slideAt() || {}, focus.region)[focus.index];
    chosen.firstChild.textContent = block ? BLOCKS[kindOf(block)].label : "";
  }

  function focusBlock(region, index) {
    state.tab = "slide";
    state.focus = { region, index };
    renderInspector();
    placeChosen();
    const card = inspectorBody.querySelector(`.block[data-region="${region}"][data-index="${index}"]`);
    card?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  // Pictures dropped on the slide become picture blocks.
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
    const region = state.focus?.region || regionsOf(slideAt())[0]?.key;
    if (!region) return;
    for (const file of files) {
      const path = await studio.upload(file);
      editSlide((slide) => { blocksAt(slide, region, true).push({ image: path }); });
    }
    toast(`Added ${files.length} picture${files.length > 1 ? "s" : ""}`, { icon: "image" });
  });

  // -- the inspector --
  function renderInspector() {
    clear(inspectorTabs,
      h(`button.insp-tab${state.tab === "slide" ? ".on" : ""}`, { onclick: () => { state.tab = "slide"; renderInspector(); } }, icon("slide"), "Slide"),
      h(`button.insp-tab${state.tab === "deck" ? ".on" : ""}`, { onclick: () => { state.tab = "deck"; renderInspector(); } }, icon("palette"), "Deck"));
    const scroll = inspectorBody.scrollTop;
    if (state.tab === "deck") clear(inspectorBody, deckForm());
    else if (!slideAt()) clear(inspectorBody, h("div.empty", {}, "No slide chosen."));
    else clear(inspectorBody, slideForm(slideAt()), regionsOf(slideAt()).map((region) => regionView(slideAt(), region)));
    inspectorBody.scrollTop = scroll;
    markBlockErrors();
  }

  function slideForm(slide) {
    const layout = layoutOf(slide);
    const allowed = new Set(catalog.slide_keys[layout]);
    const text = (key, label, { placeholder = "", markup = true, rows = 1 } = {}) => allowed.has(key)
      ? h("div", { dataset: { field: key } }, ui.field(label, (markup ? ui.markup : ui.input)({ value: slide[key] ?? "", rows, placeholder,
        onInput: (value) => editSlide((s) => setOption(s, key, value), { quiet: true, merge: `${state.slide}-${key}` }) })))
      : null;
    const pick = h("button.layout-pick", { type: "button", onclick: (event) => layoutMenu(event.currentTarget) },
      glyph(layout), h("span.name", {}, LAYOUT_NAMES[layout]), h("span.note", {}, catalog.layouts.find((l) => l.name === layout)?.note || ""), icon("chevron-down"));
    const parts = [
      h("div.section-title", {}, `Slide ${state.slide + 1}`, h("span.spacer", { style: { flex: 1 } }),
        ui.button("", (event) => slideMenu(event.currentTarget, state.slide), { kind: "ghost", icon: "more", small: true, title: "Slide actions" })),
      pick,
      layout === "statement" ? text("words", "Words", { rows: 2, placeholder: "One sentence, large" }) : text("title", layout === "agenda" ? "Heading" : "Title", { placeholder: layout === "agenda" ? "Outline" : "" }),
      text("subtitle", "Subtitle"),
      layout === "title" ? h("div.grid2", {}, text("author", "Author", { markup: false }), text("date", "Date", { markup: false })) : null,
      text("by", "Said by", { markup: false }),
    ];
    if (layout === "agenda") parts.push(h("div.hint-line", {}, "Lists the deck's section slides, wherever they are."));
    if (layout === "two-columns") {
      const split = slide.split ?? 0.5;
      const value = h("span.value", {}, `${Math.round(split * 100)}%`);
      const range = h("input", { type: "range", min: 0.15, max: 0.85, step: 0.01, value: split, oninput: () => {
        value.textContent = `${Math.round(range.value * 100)}%`;
        editSlide((s) => setOption(s, "split", Number(range.value), 0.5), { quiet: true, merge: `${state.slide}-split` });
      } });
      parts.push(ui.field("Left column's share", h("div.slider", {}, range, value)));
    }
    if (layout === "columns") parts.push(columnsControls(slide));
    if (allowed.has("align")) {
      parts.push(ui.field("Content sits", ui.segmented({ value: slide.align ?? "", options: [
        { value: "", label: "Deck's" }, { value: "auto", label: "Auto" }, { value: "top", label: "Top" }, { value: "middle", label: "Middle" }],
        onChange: (value) => editSlide((s) => setOption(s, "align", value), { quiet: true }) })));
    }
    parts.push(backgroundControls(slide, allowed));
    parts.push(footnotesControls(slide));
    return h("div.section", {}, parts);
  }

  function layoutMenu(anchor) {
    menu(anchor, [{ title: "Layout" }, ...catalog.layouts.map((layout) => ({
      icon: LAYOUT_ICONS[layout.name], label: LAYOUT_NAMES[layout.name], hint: layout.note, run: () => changeLayout(layout.name),
    }))]);
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
      else if (layout === "columns") { slide.columns = blocks.length > 1 ? blocks : [all, [], []]; }
      else if (!WORDLESS.has(layout)) slide.body = all;
      const allowed = new Set(catalog.slide_keys[layout]);
      for (const key of Object.keys(slide)) if (!allowed.has(key)) delete slide[key];
    });
    state.focus = null;
    renderInspector();
    if (lost) toast(h("span", {}, `A ${LAYOUT_NAMES[layout].toLowerCase()} slide has no blocks: they were set aside. `, h("a", { href: "#", onclick: (event) => { event.preventDefault(); studio.undo(); } }, "Undo")), { icon: "info", seconds: 6 });
  }

  function columnsControls(slide) {
    const count = (slide.columns || []).length;
    const widths = slide.widths;
    const setCount = (n) => editSlide((s) => {
      s.columns ||= [];
      while (s.columns.length < n) s.columns.push([]);
      if (s.columns.length > n) { const extra = s.columns.splice(n).flat(); s.columns[n - 1].push(...extra); }
      if (s.widths) s.widths = Array.from({ length: n }, (_, i) => s.widths[i] ?? 1);
    });
    const stepper = h("div.row", {},
      ui.button("", () => count > 1 && setCount(count - 1), { icon: "minus", small: true, disabled: count <= 1, title: "One column fewer" }),
      h("span", { style: { textAlign: "center", fontWeight: 600 } }, `${count} columns`),
      ui.button("", () => count < 6 && setCount(count + 1), { icon: "plus", small: true, disabled: count >= 6, title: "One column more" }));
    stepper.firstChild.classList.add("fixed"); stepper.lastChild.classList.add("fixed");
    const shares = h("div.row", {}, Array.from({ length: count }, (_, i) => ui.number({ value: widths?.[i] ?? "", placeholder: "1", min: 0.1, step: 0.5,
      onChange: (value) => editSlide((s) => {
        const next = Array.from({ length: count }, (_, j) => (j === i ? value : s.widths?.[j]) ?? 1);
        if (next.every((v) => v === 1)) delete s.widths; else s.widths = next;
      }, { quiet: true, merge: `${state.slide}-widths-${i}` }) })));
    return h("div.field", {}, ui.field("Columns", stepper), ui.field("Widths", shares, { hint: "relative, e.g. 2 1 1" }));
  }

  function backgroundControls(slide, allowed) {
    const background = slide.background;
    const mode = !background ? "" : String(background).startsWith("#") ? "colour" : "picture";
    const body = h("div.field");
    const segments = ui.segmented({ value: mode, options: [{ value: "", label: "Page" }, { value: "colour", label: "Colour" }, { value: "picture", label: "Picture" }],
      onChange: async (value) => {
        if (value === "") editSlide((s) => { delete s.background; delete s.shade; delete s.dark; });
        else if (value === "colour") editSlide((s) => { s.background = "#1b2a41"; delete s.shade; });
        else {
          const path = await chooseFile({ title: "A picture to fill the slide", types: ["image"] });
          if (path) editSlide((s) => { s.background = path; s.shade = s.shade ?? 0.35; });
          else renderInspector();
        }
        renderInspector();
      } });
    const parts = [segments];
    if (mode === "colour") {
      const swatch = h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(background) ? background : "#1b2a41", style: { width: "44px", height: "30px", border: 0, background: "none", padding: 0 },
        oninput: () => { hex.value = swatch.value; editSlide((s) => { s.background = swatch.value; }, { quiet: true, merge: `${state.slide}-bg` }); } });
      const hex = ui.input({ value: background, mono: true, onInput: (value) => { if (/^#[0-9a-f]{3,8}$/i.test(value)) { swatch.value = value.length === 7 ? value : swatch.value; editSlide((s) => { s.background = value; }, { quiet: true, merge: `${state.slide}-bg` }); } } });
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
    body.append(ui.field("Background", h("div", { style: { display: "grid", gap: "8px" } }, parts)));
    return body;
  }

  function footnotesControls(slide) {
    const list = Array.isArray(slide.footnotes) ? slide.footnotes : slide.footnotes ? [slide.footnotes] : [];
    const rows = list.map((note, i) => h("div.list-row", {},
      ui.markup({ value: note, placeholder: "A reference, small at the foot", onInput: (value) => editSlide((s) => { s.footnotes = [...list]; s.footnotes[i] = value; }, { quiet: true, merge: `${state.slide}-fn-${i}` }) }),
      ui.button("", () => editSlide((s) => { const next = list.filter((_, j) => j !== i); if (next.length) s.footnotes = next; else delete s.footnotes; }), { kind: "ghost", icon: "trash", small: true, title: "Remove" })));
    rows.forEach((row) => { row.firstChild.style.flex = "1"; });
    return ui.field("Footnotes", h("div.list-rows", {}, rows,
      h("div", {}, ui.button("Footnote", () => editSlide((s) => { s.footnotes = [...list, "[1] Author et al., *Venue* (2026)"]; }), { kind: "ghost", icon: "plus", small: true }))));
  }

  // -- regions and blocks --
  let dragBlock = null;

  function regionView(slide, region) {
    const blocks = blocksAt(slide, region.key);
    const list = h("div.blocks", {}, blocks.map((block, index) => blockView(block, region, index)));
    const node = h("div.region", { dataset: { region: region.key },
      ondragover: (event) => { if (dragBlock) { event.preventDefault(); node.classList.add("drop-target"); } },
      ondragleave: (event) => { if (!node.contains(event.relatedTarget)) node.classList.remove("drop-target"); },
      ondrop: (event) => {
        node.classList.remove("drop-target");
        if (!dragBlock || event.defaultPrevented) return;
        event.preventDefault();
        moveBlock(dragBlock, { region: region.key, index: blocks.length });
      } },
    h("div.region-head", {}, region.label, h("span.count", {}, blocks.length ? `· ${blocks.length}` : ""), h("span.spacer"),
      ui.button("Add", (event) => addBlockMenu(event.currentTarget, region.key), { kind: "ghost", icon: "plus", small: true })),
    blocks.length ? list : h("div.region-empty", {}, "Nothing here yet — ", h("a", { href: "#", onclick: (event) => { event.preventDefault(); addBlockMenu(event.currentTarget, region.key); } }, "add a block"), " or drop pictures on the slide."));
    return h("div.section", {}, node);
  }

  function addBlockMenu(anchor, region) {
    menu(anchor, [{ title: "Add" }, ...Object.entries(BLOCKS).map(([kind, info]) => ({
      icon: info.icon, label: info.label, hint: info.hint, run: () => addBlock(region, kind),
    }))]);
  }

  async function addBlock(region, kind) {
    let block = NEW_BLOCKS[kind]();
    if (kind === "image") {
      const path = await chooseFile({ title: "Choose a picture", types: ["image"] });
      if (!path) return;
      block = { image: path };
    } else if (kind === "plot") {
      const target = await chooseFunction();
      if (!target) return;
      block = { plot: target };
    } else if (kind === "gallery") {
      const path = await chooseFile({ title: "The first picture of the gallery", types: ["image"] });
      if (!path) return;
      block = { gallery: [path] };
    }
    let index = 0;
    editSlide((slide) => { const list = blocksAt(slide, region, true); list.push(block); index = list.length - 1; });
    state.focus = { region, index };
    renderInspector();
    placeChosen();
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
  }

  function blockMenu(anchor, region, index) {
    const slide = slideAt();
    const others = regionsOf(slide).filter((r) => r.key !== region.key);
    const count = blocksAt(slide, region.key).length;
    menu(anchor, [
      { icon: "copy", label: "Duplicate", run: () => { editSlide((s) => { const list = blocksAt(s, region.key); list.splice(index + 1, 0, structuredClone(list[index])); }); state.focus = { region: region.key, index: index + 1 }; renderInspector(); } },
      ...(index > 0 ? [{ icon: "up", label: "Move up", run: () => moveBlock({ region: region.key, index }, { region: region.key, index: index - 1 }) }] : []),
      ...(index < count - 1 ? [{ icon: "down", label: "Move down", run: () => moveBlock({ region: region.key, index }, { region: region.key, index: index + 2 }) }] : []),
      ...others.map((other) => ({ icon: "right", label: `Move to ${other.label.toLowerCase()}`, run: () => moveBlock({ region: region.key, index }, { region: other.key, index: blocksAt(slide, other.key).length }) })),
      "-",
      { icon: "trash", label: "Delete", danger: true, run: () => { editSlide((s) => { blocksAt(s, region.key).splice(index, 1); }); state.focus = null; renderInspector(); placeChosen(); } },
    ]);
  }

  function blockView(block, region, index) {
    const kind = kindOf(block);
    const info = BLOCKS[kind];
    const open = state.focus && state.focus.region === region.key && state.focus.index === index;
    const place = { region: region.key, index };
    const words = h("span.words", {}, summary(block));
    const node = h(`div.block${open ? ".on" : ""}`, { dataset: { region: region.key, index },
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
      } },
    h("div.block-head", { onclick: () => { state.focus = open ? null : place; renderInspector(); placeChosen(); } },
      h("span.grip", { draggable: true, title: "Drag to move",
        ondragstart: (event) => { dragBlock = place; node.classList.add("dragging"); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", kind); event.dataTransfer.setDragImage(node, 20, 18); },
        ondragend: () => { dragBlock = null; node.classList.remove("dragging"); } }, icon("grip", { weight: "2.4" })),
      h("span.kind", {}, icon(info.icon)),
      h("span.summary", {}, h("span.what", {}, info.label), words),
      h("span.actions", {}, ui.button("", (event) => { event.stopPropagation(); blockMenu(event.currentTarget, region, index); }, { kind: "ghost", icon: "more", small: true, title: "Block actions" }))),
    open ? h("div.block-body", {}, blockForm(block, kind, place, words)) : null);
    return node;
  }

  function markBlockErrors() {
    for (const card of inspectorBody.querySelectorAll(".block")) { card.classList.remove("error"); card.querySelector(".block-error")?.remove(); }
    for (const message of messages) {
      const place = placeOf(message.where);
      if (!place || place.slide !== state.slide || place.region === null || message.severity !== "error") continue;
      const card = inspectorBody.querySelector(`.block[data-region="${place.region}"][data-index="${place.index}"]`);
      if (!card) continue;
      card.classList.add("error");
      const body = card.querySelector(".block-body") || card;
      body.prepend(h("div.block-error", {}, icon("error"), message.text));
    }
  }

  // -- block forms --
  function blockForm(block, kind, place, words) {
    const merge = (key) => `${state.slide}-${place.region}-${place.index}-${key}`;
    const set = (key, fallback) => (value) => editBlock(place, (b) => setOption(b, key, value, fallback), { merge: merge(key) });
    const refresh = () => { const current = blocksAt(slideAt(), place.region)[place.index]; if (current) words.textContent = summary(current); };
    const edit = (mutate, key) => { editBlock(place, mutate, { merge: merge(key) }); refresh(); };
    const size = () => ui.field("Size", ui.number({ value: block.size, placeholder: "auto", min: 4, step: 1, onChange: set("size") }), { hint: "pt" });
    const toneSwatches = (key, { none = true, extra = [], fallback } = {}) => {
      const palette = studio.info?.palette || {};
      const colours = [...TONES.map((tone, i) => ({ value: tone, colour: palette[tone] || "#888", title: i === 0 ? "Accent" : `Accent ${i + 1}` })), ...extra];
      return ui.swatches({ value: block[key] ?? fallback ?? null, colours, none, onChange: (value) => editBlock(place, (b) => setOption(b, key, value, fallback)) });
    };

    switch (kind) {
      case "bullets": {
        const area = ui.markup({ value: bulletsText(block.bullets), rows: 3, tabs: true, placeholder: "One item per line",
          onInput: (text) => edit((b) => { b.bullets = bulletsFrom(text); }, "items") });
        return [area,
          h("div.hint-line", {}, "One item per line. ", h("kbd", {}, "Tab"), " sets a line a level below, ", h("kbd", {}, "⇧Tab"), " brings it back."),
          h("div.row", {}, ui.toggle({ value: block.numbered, label: "Numbered", onChange: set("numbered", false) }),
            ui.toggle({ value: block.reveal, label: "One at a time", onChange: set("reveal", false) })),
          size()];
      }
      case "text":
        return [ui.markup({ value: block.text, rows: 2, onInput: (text) => edit((b) => { b.text = text; }, "text") }),
          ui.field("Align", ui.segmented({ value: block.align || "start", options: [
            { value: "start", icon: "text", title: "Flush left" }, { value: "middle", icon: "title", title: "Centred" }, { value: "end", icon: "right", title: "Flush right" }],
            onChange: (value) => editBlock(place, (b) => setOption(b, "align", value, "start")) })),
          ui.field("Colour", toneSwatches("colour", { extra: [{ value: "muted", colour: studio.info?.palette?.muted || "#999", title: "Muted" }] })),
          h("div.row", {}, ui.toggle({ value: block.muted, label: "Muted", onChange: set("muted", false) })),
          size()];
      case "quote":
        return [ui.markup({ value: block.quote, rows: 2, onInput: (text) => edit((b) => { b.quote = text; }, "quote") }),
          ui.field("Said by", ui.input({ value: block.by, placeholder: "Who", onInput: set("by") })), size()];
      case "callout":
        return [ui.field("Heading", ui.input({ value: block.title, placeholder: "Optional", onInput: (text) => edit((b) => setOption(b, "title", text), "title") })),
          ui.field("Words", ui.markup({ value: block.callout, rows: 2, onInput: (text) => edit((b) => { b.callout = text; }, "words") })),
          ui.field("Tone", toneSwatches("colour", { none: false, fallback: "accent" })), size()];
      case "code":
        return [ui.textarea({ value: block.code, rows: 5, mono: true, onInput: (text) => edit((b) => { b.code = text; }, "code") }),
          h("div.hint-line", {}, "Kept as written; whole-line comments are set muted."), size()];
      case "stats": return statsForm(block, place, edit, toneSwatches, size);
      case "table": return tableForm(block, place, edit, size);
      case "image": return imageForm(block, place, refresh);
      case "gallery": return galleryForm(block, place, edit, size);
      case "figure": return figureForm(block, place, edit, refresh);
      case "plot":
        return [ui.field("Made by", functionInput(block.plot, (value) => edit((b) => { b.plot = value; }, "plot")), { hint: "file.py:function" }),
          h("div.hint-line", {}, "A function returning a matplotlib figure; it runs inside ", h("code", {}, "deck.plotting()"), " and is given the deck if it takes an argument."),
          ui.field("Shape", ui.number({ value: block.aspect, placeholder: "fill the room", min: 0.2, step: 0.1, onChange: set("aspect") }), { hint: "width ÷ height" })];
      default:
        return [h("div.hint-line", {}, "This block has no form yet.")];
    }
  }

  function statsForm(block, place, edit, toneSwatches, size) {
    const items = (Array.isArray(block.stats) ? block.stats : []).map((item) => (Array.isArray(item) ? { value: item[0], label: item[1] } : typeof item === "object" && item ? { ...item } : { value: item, label: "" }));
    const write = (next) => edit((b) => { b.stats = next; }, "stats");
    const rows = items.map((item, i) => h("div.list-row", {},
      ui.input({ value: String(item.value ?? ""), placeholder: "93%", width: "90px", onInput: (value) => { items[i].value = value; write(items); } }),
      ui.input({ value: item.label ?? "", placeholder: "what it counts", onInput: (value) => { items[i].label = value; write(items); } }),
      ui.button("", () => { items.splice(i, 1); editBlock(place, (b) => { b.stats = items; }); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, disabled: items.length <= 1 })));
    rows.forEach((row) => { row.firstChild.style.flex = "0 0 96px"; });
    return [h("div.list-rows", {}, rows),
      h("div", {}, ui.button("Number", () => { editBlock(place, (b) => { b.stats = [...items, { value: "1", label: "more" }]; }); renderInspector(); }, { kind: "ghost", icon: "plus", small: true })),
      ui.field("Colour", toneSwatches("colour")), size()];
  }

  function tableForm(block, place, edit, size) {
    const source = Array.isArray(block.table) && block.table.length ? block.table : [[typeof block.table === "string" ? block.table : ""]];
    const rows = source.map((row) => (Array.isArray(row) ? row : [row]).map((cell) => String(cell ?? "")));
    const columns = Math.max(1, ...rows.map((row) => row.length));
    rows.forEach((row) => { while (row.length < columns) row.push(""); });
    const header = block.header !== false;
    const given = alignList(block.align, columns);
    const auto = autoAlign(rows, header);
    const write = () => edit((b) => { b.table = rows.map((row) => [...row]); }, "cells");
    const restructure = (mutate) => { mutate(); editBlock(place, (b) => { b.table = rows.map((row) => [...row]); if (b.align) delete b.align; }); renderInspector(); };
    const input = (r, c) => {
      const cell = h("input", { value: rows[r][c], spellcheck: false,
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
        onChange: (value) => editBlock(place, (b) => {
          const next = given ? [...given] : [...auto];
          next[c] = value || auto[c];
          if (next.every((v, i) => v === auto[i])) delete b.align; else b.align = next;
        }) }))),
    h("th.corner", {}, ""));
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
      h("div.hint-line", {}, "Paste cells from a spreadsheet into any cell. Numbers are set flush right unless you choose."),
      h("div.row", {}, ui.toggle({ value: header, label: "First row is the header", onChange: (value) => editBlock(place, (b) => setOption(b, "header", value ? null : false)) })),
      size()];
  }

  function imageForm(block, place, refresh) {
    const preview = h("img.preview-pic", { src: block.image ? studio.raw(block.image) : "", alt: "", hidden: !block.image });
    return [preview,
      fileRow(block.image, ["image"], (path) => { editBlock(place, (b) => { b.image = path; }, {}); preview.src = studio.raw(path); preview.hidden = false; refresh(); }, "picture.png"),
      h("div.hint-line", {}, "An SVG is drawn as vectors — native shapes and text in the PowerPoint."),
      ui.field("Width", ui.number({ value: block.width, placeholder: "as wide as fits", min: 10, step: 10, onChange: (value) => editBlock(place, (b) => setOption(b, "width", value)) }), { hint: "pt" })];
  }

  function galleryForm(block, place, edit, size) {
    const items = (Array.isArray(block.gallery) ? block.gallery : []).map((item) => (typeof item === "string" ? { picture: item, caption: "" } : { picture: item?.picture || "", caption: item?.caption || "" }));
    const write = () => edit((b) => { b.gallery = items.map((item) => (item.caption ? { ...item } : item.picture)); }, "gallery");
    const round = block.crop === "circle";
    const rows = items.map((item, i) => h("div.list-row", {},
      h(`img.pic${round ? ".round" : ""}`, { src: studio.raw(item.picture), alt: "" }),
      h("div", { style: { flex: 1, display: "grid", gap: "4px" } },
        ui.input({ value: item.caption, placeholder: "**Name**\\nInstitute (optional)", onInput: (value) => { items[i].caption = value.replace(/\\n/g, "\n"); write(); } }),
        h("span.hint-line", {}, item.picture)),
      ui.button("", () => { items.splice(i, 1); write(); renderInspector(); }, { kind: "ghost", icon: "trash", small: true, title: "Remove" })));
    return [h("div.list-rows", {}, rows),
      h("div", {}, ui.button("Picture", async () => {
        const path = await chooseFile({ title: "Add a picture", types: ["image"] });
        if (path) { items.push({ picture: path, caption: "" }); write(); renderInspector(); }
      }, { kind: "ghost", icon: "plus", small: true })),
      h("div.grid2", {},
        ui.field("Columns", ui.number({ value: block.columns, placeholder: "auto", min: 1, step: 1, onChange: (value) => editBlock(place, (b) => setOption(b, "columns", value)) })),
        ui.field("Height", ui.number({ value: block.height, placeholder: "auto", min: 10, step: 5, onChange: (value) => editBlock(place, (b) => setOption(b, "height", value)) }), { hint: "pt" })),
      ui.field("Crop", ui.segmented({ value: block.crop || "", options: [{ value: "", label: "None" }, { value: "circle", label: "Circle" }, { value: "square", label: "Square" }],
        onChange: (value) => { editBlock(place, (b) => setOption(b, "crop", value)); renderInspector(); } })),
      ui.field("A single column", ui.segmented({ value: block.align || "", options: [{ value: "", label: "Auto" }, { value: "start", label: "Flush" }, { value: "middle", label: "Centred" }],
        onChange: (value) => editBlock(place, (b) => setOption(b, "align", value)) })),
      size()];
  }

  function figureForm(block, place, edit, refresh) {
    const value = block.figure;
    const mode = typeof value === "string" ? (value.includes(".py:") ? "python" : "file") : "inline";
    const parts = [ui.field("Made from", ui.segmented({ value: mode, options: [
      { value: "inline", label: "Here" }, { value: "file", label: "A figure file" }, { value: "python", label: "Python" }],
      onChange: async (next) => {
        if (next === mode) return;
        if (next === "inline") editBlock(place, (b) => { b.figure = NEW_BLOCKS.figure().figure; });
        else if (next === "file") {
          const path = await chooseFile({ title: "A flexo figure file", types: ["figure"], create: "figure" });
          if (path) editBlock(place, (b) => { b.figure = path; });
        } else {
          const target = await chooseFunction("A function returning a flexo figure");
          if (target) editBlock(place, (b) => { b.figure = target; });
        }
        renderInspector();
      } }))];
    if (mode === "inline") {
      const area = ui.textarea({ value: JSON.stringify(value, null, 2), rows: 10, mono: true, onInput: (text) => {
        try { const parsed = JSON.parse(text); area.classList.remove("invalid"); area.style.borderColor = ""; edit((b) => { b.figure = parsed; }, "figure"); }
        catch { area.style.borderColor = "var(--error)"; }
      } });
      area.style.maxHeight = "360px"; area.style.overflow = "auto"; area.classList.remove("grow");
      parts.push(area, h("div.hint-line", {}, "A flexo figure document (nodes, edges, groups), written here as JSON."),
        h("div", {}, ui.button("Move to its own file", async () => {
          const name = await ask("Save the figure as", "figures/figure.yaml");
          if (!name) return;
          try {
            const made = await createFile(name, "figure", value);
            editBlock(place, (b) => { b.figure = made; });
            renderInspector();
            toast(h("span", {}, "Saved as ", h("b", {}, made), ". ", h("a", { href: figureLink(made), target: "_blank" }, "Open in the figure editor")), { icon: "check", seconds: 6 });
          } catch (error) { toast(error.message, { kind: "error", icon: "error" }); }
        }, { kind: "ghost", icon: "external", small: true })));
    } else if (mode === "file") {
      parts.push(fileRow(value, ["figure"], (path) => { editBlock(place, (b) => { b.figure = path; }); refresh(); }, "figure.yaml"),
        h("div", {}, h("a.btn.ghost.small", { href: figureLink(value), target: "_blank" }, icon("external"), "Open in the figure editor")),
        h("div.hint-line", {}, "Changes saved there are drawn here as you work."));
    } else {
      parts.push(functionInput(value, (text) => edit((b) => { b.figure = text; }, "figure")),
        h("div.hint-line", {}, "A function returning a ", h("code", {}, "flexo.Figure"), "; it runs again when its file changes."));
    }
    parts.push(h("div.row", {}, ui.toggle({ value: block.turn !== false, label: "May turn to fit the slide", onChange: (on) => editBlock(place, (b) => setOption(b, "turn", on ? null : false)) })));
    return parts;
  }

  function figureLink(path) {
    const folder = studio.file.includes("/") ? studio.file.slice(0, studio.file.lastIndexOf("/") + 1) : "";
    return `/?file=${encodeURIComponent(folder + path)}`;
  }

  // -- files --
  function fileRow(value, types, onChoose, placeholder) {
    const input = ui.input({ value: value || "", placeholder, mono: true, onChange: (text) => text && onChoose(text) });
    const row = h("div.list-row", {}, input,
      ui.button("", async () => { const path = await chooseFile({ title: "Choose a file", types }); if (path) { input.value = path; onChoose(path); } }, { icon: "folder", small: true, title: "Choose…" }));
    return row;
  }

  function functionInput(value, onInput) {
    const input = ui.input({ value: value || "", placeholder: "plots.py:loss", mono: true, onInput });
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
      const upload = h("input", { type: "file", accept: types.includes("image") ? "image/*,.svg" : ".yaml,.yml,.json", hidden: true,
        onchange: async () => { const file = upload.files[0]; if (file) finish(await studio.upload(file)); } });
      const body = [list, upload];
      const actions = [];
      if (types.includes("image") || types.includes("figure")) actions.push({ label: "Upload…", run: () => { upload.click(); return false; } });
      if (create === "figure") actions.push({ label: "New figure file…", run: () => {
        ask("Name the new figure file", "figures/figure.yaml").then(async (name) => {
          if (!name) return;
          try { const made = await createFile(name, "figure"); finish(made); open(figureLink(made), "_blank"); }
          catch (error) { toast(error.message, { kind: "error", icon: "error" }); }
        });
        return false;
      } });
      actions.push({ label: "Cancel", run: () => finish(null) });
      const box = dialog({ title, body, actions, onClose: () => finish(null) });
      studio.files(types).then((files) => {
        const shown = files.filter((file) => file !== studio.file.split("/").pop());
        clear(list, shown.length ? shown.map((file) => h("button.menu-item", { type: "button", onclick: () => finish(file) },
          types.includes("image") ? h("img.pic", { src: studio.raw(file), alt: "", style: { width: "36px", height: "36px", objectFit: "cover", borderRadius: "5px", border: "1px solid var(--line)" } }) : icon(types.includes("python") ? "code" : "figure"),
          h("span.menu-text", {}, h("span", {}, file.split("/").pop()), h("span.menu-hint", {}, file))))
          : h("div.empty", {}, "No files of this kind beside the deck yet."));
      });
    });
  }

  function chooseFunction(title = "A Python function") {
    return new Promise((resolve) => {
      let value = "";
      const input = functionInput("", (text) => { value = text; });
      const box = dialog({ title, body: [ui.field("file.py:function", input), h("div.hint-line", {}, "The file sits beside the deck; the function is called when the slide is drawn.")],
        actions: [{ label: "Cancel", run: () => resolve(null) }, { label: "Use it", kind: "primary", run: () => {
          if (!/\.py:\w+$/.test(value.trim())) { input.classList.add("invalid"); return false; }
          resolve(value.trim());
        } }], onClose: () => resolve(null) });
      setTimeout(() => input.focus(), 30);
      void box;
    });
  }

  function ask(title, placeholder) {
    return new Promise((resolve) => {
      const input = ui.input({ value: placeholder, mono: true });
      dialog({ title, body: [input], actions: [{ label: "Cancel", run: () => resolve(null) }, { label: "OK", kind: "primary", run: () => resolve(input.value.trim() || null) }], onClose: () => resolve(null) });
      setTimeout(() => { input.focus(); input.select(); }, 30);
    });
  }

  async function createFile(name, kind, data) {
    const folder = studio.file.includes("/") ? studio.file.slice(0, studio.file.lastIndexOf("/") + 1) : "";
    const result = await studio.api("/api/new", { file: folder + name, kind, data });
    return result.file.slice(folder.length);
  }

  // -- the deck --
  function deckForm() {
    const deck = doc().deck || {};
    const editDeck = (mutate, options = {}) => studio.change((d) => { d.deck ||= {}; mutate(d.deck); }, options);
    const setDeck = (key, fallback) => (value) => editDeck((d) => setOption(d, key, value, fallback), { quiet: true, merge: `deck-${key}` });
    const look = deck.look || "classic";
    const looks = h("div.looks", {}, catalog.looks.map((item) => h(`button.look${item.name === look ? ".on" : ""}`, { type: "button",
      onclick: () => { editDeck((d) => setOption(d, "look", item.name, "classic")); renderInspector(); } },
    lookArt(item.name), h("span.name", {}, item.name), h("span.note", {}, item.note))));
    const palettes = Object.entries(catalog.palettes);
    const current = Array.isArray(deck.palette) ? "" : deck.palette || "default";
    const paletteList = h("div.palette-list.scroll-thin", {},
      h(`button.palette-item${current === "default" ? ".on" : ""}`, { type: "button", onclick: () => { editDeck((d) => { delete d.palette; }); renderInspector(); } },
        h("span.palette-row", {}, Object.entries(studio.info?.palette || {}).filter(([k]) => k.startsWith("accent")).slice(0, 5).map(([, c]) => h("span", { style: { background: c } }))),
        h("span.name", {}, "The theme's own")),
      palettes.map(([name, colours]) => h(`button.palette-item${current === name ? ".on" : ""}`, { type: "button", onclick: () => { editDeck((d) => { d.palette = name; }); renderInspector(); } },
        h("span.palette-row", {}, colours.map((c) => h("span", { style: { background: c } }))), h("span.name", {}, name))));
    const custom = ui.input({ value: Array.isArray(deck.palette) ? deck.palette.join(", ") : "", placeholder: "#1f77b4, #ff7f0e, …", mono: true,
      onChange: (text) => { const colours = text.split(/[\s,]+/).filter((c) => /^#[0-9a-f]{3,8}$/i.test(c)); editDeck((d) => setOption(d, "palette", colours.length ? colours : null)); renderInspector(); } });
    const fonts = (key, label, note) => ui.field(label, ui.combo({ value: deck[key] || "", options: catalog.fonts, placeholder: note, onChange: setDeck(key) }));
    const lookStyle = catalog.looks.find((item) => item.name === look)?.style || {};
    const changes = deck.style || {};
    const styleRows = catalog.style.map((field) => {
      const fallback = lookStyle[field.name] ?? field.default;
      const setStyle = (value) => { editDeck((d) => { d.style ||= {}; setOption(d.style, field.name, value, undefined); if (!Object.keys(d.style).length) delete d.style; }, { quiet: true, merge: `style-${field.name}` }); mark(); };
      let control;
      if (field.kind === "bool") control = ui.select({ value: changes[field.name] === undefined ? "" : String(changes[field.name]), options: [{ value: "", label: `look (${fallback ? "on" : "off"})` }, { value: "true", label: "on" }, { value: "false", label: "off" }], onChange: (v) => setStyle(v === "" ? null : v === "true") });
      else if (field.kind === "choice") control = ui.select({ value: changes[field.name] ?? "", options: [{ value: "", label: `look (${fallback})` }, ...field.choices], onChange: (v) => setStyle(v || null) });
      else control = ui.number({ value: changes[field.name], placeholder: String(fallback ?? "theme"), step: "any", onChange: setStyle });
      const nameNode = h("span.name", {}, h("span", {}, field.name.replace(/_/g, " ")), h("span.note", {}, field.note));
      const reset = ui.button("", () => { setStyle(null); renderInspector(); }, { kind: "ghost", icon: "undo", small: true, title: "Back to the look's" });
      const mark = () => { const set = (doc().deck?.style || {})[field.name] !== undefined; nameNode.firstChild.classList.toggle("changed", set); reset.style.visibility = set ? "visible" : "hidden"; };
      mark();
      return h("div.style-row", {}, nameNode, control, reset);
    });
    const changed = Object.keys(changes).length;
    return [
      h("div.section", {},
        h("div.section-title", {}, "Look"), looks),
      h("div.section", {},
        h("div.section-title", {}, "Theme"),
        ui.field("Theme", ui.combo({ value: deck.theme || "paper", options: catalog.themes, onChange: (value) => { if (value) editDeck((d) => setOption(d, "theme", value, "paper"), { quiet: true, merge: "deck-theme" }); } }), { hint: "or a theme file" }),
        ui.field("Palette", paletteList),
        ui.field("Your own colours", custom, { hint: "overrides the palette" })),
      h("div.section", {},
        h("div.section-title", {}, "Type"),
        fonts("font", "Words", "the theme's"), fonts("title_font", "Titles and headings", "as the words"), fonts("figure_font", "Figures", "as the words")),
      h("div.section", {},
        h("div.section-title", {}, "Deck"),
        h("div", { dataset: { field: "footer" } }, ui.field("Footer", ui.markup({ value: deck.footer || "", placeholder: "Group meeting · 2026", colours: false, onInput: setDeck("footer") }))),
        ui.field("Name of the outputs", ui.input({ value: deck.id || "", placeholder: "talk", mono: true, onInput: setDeck("id") }), { hint: "name.pptx, name.pdf" })),
      h("div.section", {},
        h("details.more", { open: changed > 0 }, h("summary", {}, icon("chevron"), `Proportions${changed ? ` · ${changed} changed` : ""}`),
          h("div.inner", {}, styleRows))),
    ];
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
    const svgAt = (page, at) => {
      if (!page?.svg || page.steps <= 1 || at >= page.steps) return page?.svg || "";
      const parsed = new DOMParser().parseFromString(page.svg, "image/svg+xml");
      parsed.querySelectorAll("[data-flexo-step]").forEach((el) => { if (Number(el.getAttribute("data-flexo-step")) > at) el.remove(); });
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
    addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && node.isConnected) show(); });
    setTimeout(() => { hint.style.opacity = "0"; }, 2500);
    show();
  }

  // -- keys --
  document.addEventListener("keydown", (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "") || document.querySelector(".scrim, .present");
    const mod = event.metaKey || event.ctrlKey;
    if (mod && event.key === "Enter") { event.preventDefault(); present(); return; }
    if (typing) return;
    if (["ArrowDown", "PageDown"].includes(event.key) && state.slide < slides().length - 1) { event.preventDefault(); select(state.slide + 1); }
    else if (["ArrowUp", "PageUp"].includes(event.key) && state.slide > 0) { event.preventDefault(); select(state.slide - 1); }
    else if (event.key === "Escape" && state.focus) { state.focus = null; renderInspector(); placeChosen(); }
    else if ((event.key === "Delete" || event.key === "Backspace") && state.focus) {
      const { region, index } = state.focus;
      editSlide((s) => { blocksAt(s, region).splice(index, 1); });
      state.focus = null; renderInspector(); placeChosen();
    }
  });

  // -- the studio's news --
  studio.on("change", ({ quiet, source }) => {
    if (state.slide >= slides().length) state.slide = Math.max(0, slides().length - 1);
    pending = true;
    if (!quiet) { renderRail(); renderInspector(); renderStage(); }
    else if (source === "save-failed") renderRail();
    pageNode?.classList.add("pending");
  });
  studio.on("drawing", () => { pending = true; });
  studio.on("drawn", (result) => {
    if (result.version < drawnVersion) return;
    drawnVersion = result.version;
    pending = !result.latest || Boolean(result.unfinished);
    seconds = result.seconds || 0;
    pages = result.pages;
    messages = result.messages || [];
    const live = new Set(pages.map((page) => page.hash));
    for (const [hash, url] of thumbs) if (!live.has(hash)) { URL.revokeObjectURL(url); thumbs.delete(hash); }
    const deckError = messages.find((m) => m.severity === "error" && !m.page && !placeOf(m.where));
    renderRail();
    const active = document.activeElement;
    renderStage();
    markBlockErrors();
    if (deckError) stage.prepend(h("div.messages", { style: { position: "absolute", top: "12px", left: "40px", right: "40px", zIndex: 3 } }, messageView(deckError)));
    if (active && active.isConnected && document.activeElement !== active) active.focus({ preventScroll: true });
    if (state.tab === "deck") {
      // Palettes shown in the deck's tab follow the theme the server resolved.
      inspectorBody.querySelectorAll(".palette-item:first-child .palette-row").forEach((row) => clear(row,
        Object.entries(studio.info?.palette || {}).filter(([k]) => k.startsWith("accent")).slice(0, 5).map(([, c]) => h("span", { style: { background: c } }))));
    }
  });

  renderRail();
  renderStage();
  renderInspector();
}

function remembered(key, fallback) {
  try { return localStorage.getItem(`flexo-deck-${key}`) ?? fallback; } catch { return fallback; }
}

function remember(key, value) {
  try { localStorage.setItem(`flexo-deck-${key}`, value); } catch { /* private window */ }
}

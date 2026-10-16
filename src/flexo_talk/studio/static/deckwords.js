// A deck's words, where each is: every line of words typed on its slides -- titles,
// subtitles and bylines; texts, lists, quotes, callouts and tables; numbers, captions,
// footnotes and rows' labels; the words of its shapes; its figures' labels, whether the
// figure is in the deck or in a figure file; its equations and code -- and each slide's
// speaker notes, for finding them (finddeck.js, and the top bar's search). Read in Node as
// it is in the studio: it takes nothing from the page.
//
// Each is a field of finding.js's: { kind, value } and, of a deck's own, `slide` (its
// index), `path` (where it is in the deck: ["slides", 3, "body", 0, "bullets", 1]), `element`
// (the id it is drawn under, "slide4.body.0.1", to find it again on the slide), `name` (what
// it is, "List", "Notes"), and `edit` (what opens it on the slide to type in: a field, an
// object, a cell). A figure file's has `file`, `at` (the figure's place) and `target` in
// place of `path`: it is changed by an edit of the figure.

const REGIONS = [["body", "body"], ["left", "left"], ["right", "right"]];

// The fields of `deck`. `files` are the figure files its slides show, read (finddeck.js reads
// them): { "figures/pipeline.yaml": model }. `figure(figure, { prefix, name })` gives a
// figure's own fields (finding.js's figureFields).
export function deckFields(deck, { files = {}, figure = () => [] } = {}) {
  const fields = [];
  const slides = Array.isArray(deck?.slides) ? deck.slides : [];
  const add = (slide, path, value, { kind = "markup", element = null, name = "Text", edit = null, ...rest } = {}) => {
    if (typeof value === "number") value = String(value);
    // (A figure's label written as runs, [{ text, weight }...], is words too.)
    if (kind === "runs" ? !Array.isArray(value) || !value.length : typeof value !== "string" || !value) return;
    fields.push({ kind, value, slide, path, element, name, edit, ...rest });
  };
  // The deck's own figures, shown by name on slides (`figure: "#pipeline"`): found once, on
  // the first slide that shows each.
  const shared = new Set();
  // (So too a figure file, however many slides show it.)
  const filed = new Set();
  // The deck's footer, the same on every slide: found once, on the first slide it is on.
  const footed = Math.max(0, slides.findIndex((slide) => slide && typeof slide === "object" && !["title", "section", "statement"].includes(slide.layout)));
  slides.forEach((slide, n) => {
    if (!slide || typeof slide !== "object") return;
    const id = `slide${n + 1}`, at = ["slides", n];
    const layout = slide.layout || "content";
    if (layout === "statement") {
      add(n, [...at, "words"], slide.words, { element: `${id}.title`, name: "Statement", edit: { kind: "field", field: "words" } });
      add(n, [...at, "by"], slide.by, { element: `${id}.byline`, name: "Attribution", edit: { kind: "field", field: "by" } });
    }
    add(n, [...at, "title"], slide.title, { element: `${id}.title`, name: "Title", edit: { kind: "field", field: "title" } });
    add(n, [...at, "subtitle"], slide.subtitle, { element: `${id}.subtitle`, name: "Subtitle", edit: { kind: "field", field: "subtitle" } });
    add(n, [...at, "author"], slide.author, { element: `${id}.byline`, name: "Author", edit: { kind: "field", field: "author" } });
    add(n, [...at, "date"], slide.date, { element: `${id}.byline`, name: "Date", edit: { kind: "field", field: "date" } });
    if (Array.isArray(slide.rows)) slide.rows.forEach((label, k) => add(n, [...at, "rows", k], label, { element: `${id}.row${k}`, name: "Row Label", edit: { kind: "field", field: `row${k}` } }));
    const regions = [
      ...REGIONS.filter(([key]) => Array.isArray(slide[key])).map(([key, drawn]) => ({ key, drawn, blocks: slide[key], path: [...at, key] })),
      ...(Array.isArray(slide.columns) ? slide.columns.map((blocks, c) => ({ key: `columns.${c}`, drawn: `column${c + 1}`, blocks: Array.isArray(blocks) ? blocks : [], path: [...at, "columns", c] })) : []),
    ];
    for (const region of regions) {
      region.blocks.forEach((block, index) => {
        if (!block || typeof block !== "object") { if (typeof block === "string") add(n, [...region.path, index], block, { element: `${id}.${region.drawn}.${index}`, name: "Text" }); return; }
        const place = [...region.path, index], drawn = `${id}.${region.drawn}.${index}`, object = { region: region.key, index };
        blockFields(block, { slide: n, place, drawn, object, add, figure, files, deck, shared, filed });
      });
    }
    const footnotes = Array.isArray(slide.footnotes) ? slide.footnotes : typeof slide.footnotes === "string" ? [slide.footnotes] : [];
    footnotes.forEach((note, k) => add(n, Array.isArray(slide.footnotes) ? [...at, "footnotes", k] : [...at, "footnotes"], note, { element: `${id}.footnote${k}`, name: "Footnote", edit: { kind: "field", field: `footnote${k}` } }));
    const shapes = (list, path, drawn) => (Array.isArray(list) ? list : []).forEach((shape, k) => {
      if (!shape || typeof shape !== "object") return;
      if (Array.isArray(shape.shapes)) shapes(shape.shapes, [...path, k, "shapes"], `${drawn}.${k}`);
      add(n, [...path, k, "text"], shape.text, { element: `${drawn}.${k}.text`, name: "Shape" });
    });
    shapes(slide.shapes, [...at, "shapes"], `${id}.shapes`);
    if (n === footed) add(n, ["deck", "footer"], deck?.deck?.footer, { element: `${id}.footer`, name: "Footer", edit: { kind: "field", field: "footer" } });
    add(n, [...at, "notes"], slide.notes, { kind: "plain", name: "Notes", notes: true });
  });
  return fields;
}

// An object's fields, in the order it shows them.
function blockFields(block, { slide, place, drawn, object, add, figure, files, deck, shared, filed }) {
  const own = (key, value, element, name, edit = { kind: "block", ...object }, kind = "markup") => add(slide, [...place, key], value, { element, name, edit, kind, object });
  if (typeof block.text === "string") own("text", block.text, drawn, "Text");
  if ("bullets" in block) {
    // Its items a line each, depth first, as the slide draws them (`drawn.k`).
    let k = 0;
    const items = (list, path) => (Array.isArray(list) ? list : [list]).forEach((item, i) => {
      if (Array.isArray(item)) { items(item, [...path, i]); return; }
      const line = k++;
      add(slide, Array.isArray(list) ? [...path, i] : path, item, { element: `${drawn}.${line}`, name: "List", edit: { kind: "block", ...object }, object, item: line });
    });
    items(block.bullets, [...place, "bullets"]);
  }
  if ("quote" in block) {
    own("quote", block.quote, `${drawn}.words`, "Quote");
    own("by", block.by, `${drawn}.by`, "Quote", { kind: "block", ...object, part: "by" });
  }
  if ("callout" in block) {
    own("title", block.title, `${drawn}.title`, "Callout", { kind: "block", ...object, part: "title" });
    own("callout", block.callout, `${drawn}.words`, "Callout");
  }
  if (Array.isArray(block.table)) {
    block.table.forEach((row, r) => (Array.isArray(row) ? row : [row]).forEach((cell, c) => add(slide, Array.isArray(row) ? [...place, "table", r, c] : [...place, "table", r], cell,
      { element: `${drawn}.${r}.${c}`, name: "Table", edit: { kind: "cell", ...object, row: r, col: c }, object })));
  }
  if (Array.isArray(block.stats)) {
    block.stats.forEach((item, k) => {
      const pair = Array.isArray(item);
      const value = pair ? item[0] : item && typeof item === "object" ? item.value : item, label = pair ? item[1] : item && typeof item === "object" ? item.label : undefined;
      const path = [...place, "stats", k];
      add(slide, pair ? [...path, 0] : item && typeof item === "object" ? [...path, "value"] : path, value, { element: `${drawn}.${k}`, name: "Numbers", edit: { kind: "stat", ...object, item: k, label: false }, object });
      add(slide, pair ? [...path, 1] : [...path, "label"], label, { element: `${drawn}.${k}.label`, name: "Numbers", edit: { kind: "stat", ...object, item: k, label: true }, object });
    });
  }
  if (typeof block.code === "string") own("code", block.code, drawn, "Code", { kind: "block", ...object }, "plain");
  if (typeof block.math === "string") own("math", block.math, drawn, "Equation", { kind: "block", ...object }, "plain");
  if ("mechanism" in block) {
    const steps = Array.isArray(block.mechanism) ? block.mechanism : [block.mechanism];
    steps.forEach((step, k) => {
      if (!step || typeof step !== "object") return;
      const path = Array.isArray(block.mechanism) ? [...place, "mechanism", k] : [...place, "mechanism"];
      for (const key of ["label", "reagents", "conditions"]) add(slide, [...path, key], step[key], { kind: "plain", element: drawn, name: "Mechanism", object });
    });
  }
  if (Array.isArray(block.gallery)) {
    block.gallery.forEach((item, k) => {
      if (item && typeof item === "object") add(slide, [...place, "gallery", k, "caption"], item.caption, { element: `${drawn}.${k}.caption`, name: "Gallery", edit: { kind: "picture", ...object, item: k }, object });
    });
  }
  if ("figure" in block) {
    const value = block.figure;
    const prefix = `${drawn}.`;
    // (Each a figure's field, put where the deck has it: `path` from the deck, or -- a figure
    // file's -- none, its file and place in its stead.)
    const put = (field, path, more = {}) => add(slide, path, field.value,
      { kind: field.kind, element: field.element, name: "Figure", part: field.part, target: field.target, object, ...more });
    if (value && typeof value === "object") {
      for (const field of figure(value, { prefix })) put(field, [...place, "figure", ...field.path]);
    } else if (typeof value === "string" && value.startsWith("#")) {
      const key = value.slice(1), own = deck?.figures?.[key];
      if (own && typeof own === "object" && !shared.has(key)) {
        shared.add(key);
        for (const field of figure(own, { prefix })) put(field, ["figures", key, ...field.path]);
      }
    } else if (typeof value === "string" && value && !value.includes(".py:") && files[value] && !filed.has(value)) {
      filed.add(value);
      for (const field of figure(files[value], { prefix })) put(field, null, { file: value, at: { slide, ...object } });
    }
  }
  // A picture's, a table's and a figure's caption, under it.
  if (typeof block.caption === "string") own("caption", block.caption, `${drawn}.caption`, "Caption", { kind: "block", ...object, part: "caption" });
}

// A field's value set in a deck being changed (`deck`, a copy): where its path says.
export function setField(deck, path, value) {
  let into = deck;
  for (const key of path.slice(0, -1)) {
    if (into == null || typeof into !== "object") return false;
    into = into[key];
  }
  const last = path[path.length - 1];
  if (into == null || typeof into !== "object" || !(last in into)) return false;
  into[last] = value;
  return true;
}

// What is in a deck at `path` now (undefined once it is gone).
export function fieldAt(deck, path) {
  let into = deck;
  for (const key of path) {
    if (into == null || typeof into !== "object") return undefined;
    into = into[key];
  }
  return into;
}

// How anything on a slide is shown -- Shown, Highlighted, Dimmed or Hidden (flexo_talk.showing)
// -- as the deck writes it, read and written without the page: run in Node too.
//
// An object says it with `hide`, `dim` and `highlight`, each `true` (the whole object) or a list
// of its parts: a list's items by number (an item under another as "2.1"), a table's rows (its
// header row 1), a gallery's pictures, numbers' figures and code's lines by theirs; a figure's
// parts by id. A shape says `hide: true`, `dim: true` or `highlight: true` (and `hidden: true`, as
// decks said it before, is `hide: true`).

export const WAYS = ["shown", "highlighted", "dimmed", "hidden"];
export const KEYS = { hidden: "hide", dimmed: "dim", highlighted: "highlight" };
// What each is called where it is done (the history, the palette: "Dim List Item 2"), where it
// is chosen in a menu, and where it is set in the inspector -- as a figure's parts have them.
export const VERBS = { shown: "Show", highlighted: "Highlight", dimmed: "Dim", hidden: "Hide" };
export const NAMES = { shown: "Shown", highlighted: "Highlight", dimmed: "Dimmed", hidden: "Hidden" };
// The Mac app's Format › Show As runs the page's commands by these names.
export const AS = { shown: "Show As Shown", highlighted: "Show As Highlighted", dimmed: "Show As Dimmed", hidden: "Show As Hidden" };
const STRENGTH = { highlighted: 1, dimmed: 2, hidden: 3 };

// The kinds whose parts are shown apart, and what a part of each is called.
export const PARTS = { bullets: ["Item", "List Item"], table: ["Row", "Table Row"], gallery: ["Picture", "Gallery Picture"], stats: ["Number", "Number"], code: ["Line", "Code Line"] };

const kindOf = (block) => (typeof block === "string" ? "text" : Object.keys(PARTS).find((key) => block && typeof block === "object" && key in block)
  || (block && typeof block === "object" && "figure" in block ? "figure" : "other"));

// How an object or a shape (`shape`) is shown as a whole: the strongest it says.
export function wholeOf(spec, { shape = false } = {}) {
  if (!spec || typeof spec !== "object") return "shown";
  let found = "shown";
  for (const [how, key] of Object.entries(KEYS)) if (spec[key] === true && (STRENGTH[how] || 0) > (STRENGTH[found] || 0)) found = how;
  if (shape && spec.hidden === true) found = "hidden";
  return found;
}

// `spec` (an object or a shape) shown `how` as a whole: what it said as a whole gone, the parts
// it names kept -- but where a part list holds the key it now takes (a figure dimmed whole that
// dimmed some of its parts), the whole is said instead.
export function setWhole(spec, how, { shape = false } = {}) {
  for (const key of Object.values(KEYS)) if (spec[key] === true || spec[key] === false) delete spec[key];
  if (shape) delete spec.hidden;
  if (how !== "shown" && KEYS[how]) spec[KEYS[how]] = true;
  return spec;
}

const named = (value) => (Array.isArray(value) ? value.map((item) => String(item).trim()) : []);
// A part's name as a document writes it: a number as a number, "2.1" as words.
export const written = (name) => (/^\d+$/.test(String(name)) ? Number(name) : String(name));

// How the part `name` of `block` is shown, as it says of it ("shown" where it says nothing).
export function partOf(block, name) {
  let found = "shown";
  for (const [how, key] of Object.entries(KEYS)) {
    if (named(block?.[key]).includes(String(name)) && (STRENGTH[how] || 0) > (STRENGTH[found] || 0)) found = how;
  }
  return found;
}

// The parts `names` of `block` shown `how`: taken out of every list, put in that one. A key the
// whole object takes (`dim: true`) is the part's list instead.
export function setPart(block, names, how) {
  const wanted = names.map(String);
  for (const key of Object.values(KEYS)) {
    if (!Array.isArray(block[key])) continue;
    const kept = block[key].filter((item) => !wanted.includes(String(item).trim()));
    if (kept.length) block[key] = kept; else delete block[key];
  }
  if (how === "shown" || !KEYS[how]) return block;
  const key = KEYS[how];
  block[key] = [...(Array.isArray(block[key]) ? block[key] : []), ...wanted.map(written)];
  return block;
}

const plain = (text) => String(text ?? "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/\[([^\]]*)\]\{[^}]*\}/g, "$1").replace(/[*`$]/g, "").replace(/\s+/g, " ").trim();
const fileName = (value) => String(value ?? "").split("/").pop();

// Each part of `block` that is shown apart, in order: { name, label, drawn } -- `drawn`, its
// place among what the slide draws of it (a list's items as drawn: an empty one is not).
export function partsOf(block) {
  const kind = kindOf(block);
  if (kind === "bullets") {
    const found = [];
    let counts = [];
    const walk = (items, level) => {
      for (const item of Array.isArray(items) ? items : [items]) {
        if (Array.isArray(item)) { walk(item, level + 1); continue; }
        if (!String(item ?? "").trim()) continue;
        counts = [...counts, ...Array(Math.max(0, level + 1 - counts.length)).fill(0)].slice(0, level + 1);
        counts[level] += 1;
        found.push({ name: counts.join("."), label: plain(item), level, drawn: found.length });
      }
    };
    walk(block.bullets, 0);
    return found;
  }
  if (kind === "table") {
    const rows = Array.isArray(block.table) ? block.table : [];
    return rows.map((row, index) => ({ name: String(index + 1), label: (Array.isArray(row) ? row : [row]).map(plain).filter(Boolean).join(" · "),
      header: block.header !== false && index === 0, drawn: index }));
  }
  if (kind === "gallery") {
    const items = Array.isArray(block.gallery) ? block.gallery : [];
    return items.map((item, index) => ({ name: String(index + 1), label: item && typeof item === "object" ? plain(item.caption) || fileName(item.picture) : fileName(item), drawn: index }));
  }
  if (kind === "stats") {
    const items = Array.isArray(block.stats) ? block.stats : [];
    return items.map((item, index) => {
      const [value, label] = Array.isArray(item) ? item : [item?.value, item?.label];
      return { name: String(index + 1), label: [plain(value), plain(label)].filter(Boolean).join(" "), drawn: index };
    });
  }
  if (kind === "code") {
    // (As the slide keeps them: its blank lines at its start and end left off.)
    const lines = String(block.code ?? "").replace(/\t/g, "    ").replace(/^\n+|\n+$/g, "").split(/\r\n|\r|\n/);
    return lines.map((line, index) => ({ name: String(index + 1), label: line.trim(), drawn: index }));
  }
  return [];
}

// What a part of a block is called, by kind and name: "List Item 2", "Table Row 3".
export const partName = (block, name) => `${PARTS[kindOf(block)]?.[1] || "Part"} ${name}`;

// Whether anything on `slide` is shown apart: an object, a part, a shape, a figure's own parts.
export function anyApart(slide) {
  const says = (spec) => spec && typeof spec === "object" && Object.values(KEYS).some((key) => spec[key] !== undefined);
  const figure = (block) => block && typeof block === "object" && block.figure && typeof block.figure === "object" ? block.figure.figure : null;
  return objectsOf(slide).some((block) => says(block) || says(figure(block)))
    || (Array.isArray(slide?.shapes) ? slide.shapes : []).some((shape) => says(shape) || shape?.hidden === true);
}

// Everything on `slide` shown plainly again: its objects, their parts, a figure written in it
// (its own parts), its shapes. What changed, counted.
export function showAll(slide) {
  let count = 0;
  const clear = (spec) => {
    if (!spec || typeof spec !== "object") return;
    for (const key of Object.values(KEYS)) if (key in spec) { delete spec[key]; count += 1; }
  };
  for (const block of objectsOf(slide)) {
    clear(block);
    if (block && typeof block === "object" && block.figure && typeof block.figure === "object") clear(block.figure.figure);
  }
  for (const shape of Array.isArray(slide?.shapes) ? slide.shapes : []) {
    clear(shape);
    if (shape && typeof shape === "object" && "hidden" in shape) { delete shape.hidden; count += 1; }
  }
  return count;
}

function objectsOf(slide) {
  if (!slide || typeof slide !== "object") return [];
  const lists = [slide.body, slide.left, slide.right, ...(Array.isArray(slide.columns) ? slide.columns : [])];
  return lists.filter(Array.isArray).flat();
}

// The part of `block` drawn as `rest` of its id (what follows the object's own: "3", "3.mark", a
// table's "1.2.cell") -- by its name, else null. `of`: a code line's line, where it was wrapped.
export function partAt(block, rest, of = null) {
  const kind = kindOf(block), first = /^(\d+)(?:\.(\d+))?/.exec(String(rest ?? ""));
  if (!first || !PARTS[kind]) return null;
  const parts = partsOf(block), index = Number(first[1]);
  if (kind === "bullets") return parts.find((part) => part.drawn === index)?.name ?? null;
  if (kind === "code" && of !== null && of !== undefined && of !== "") return String(Number(of) + 1);
  return parts[index]?.name ?? null;
}

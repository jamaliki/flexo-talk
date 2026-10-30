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

// Whether anything on `slide` is shown apart: an object, a part, a shape, a figure's own parts --
// at `click`, as its last click up to it says.
export function anyApart(slide, click = 0) {
  const says = (spec) => spec && typeof spec === "object" && Object.values(KEYS).some((key) => spec[key] !== undefined && spec[key] !== false
    && !(Array.isArray(spec[key]) && !spec[key].length));
  const figure = (block) => block && typeof block === "object" && block.figure && typeof block.figure === "object" ? block.figure.figure : null;
  const at = (spec) => (spec && typeof spec === "object" ? saidAt(spec, click) : spec);
  return objectsOf(slide).some((block) => says(at(block)) || says(figure(block)))
    || (Array.isArray(slide?.shapes) ? slide.shapes : []).some((shape) => says(at(shape)) || (at(shape) === shape && shape?.hidden === true));
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

// -- from a click on (flexo_talk.onclick) --
// An object or a shape says how it is shown from a click on with `click N`: a mapping of hide,
// dim and highlight, all of how it is shown from that click on, held until a later click of its
// own. What a figure's click does not say of its parts is as the figure says it (its own lists).

const CLICK = /^click ([1-9][0-9]*)$/;
export const clickKey = (click) => `click ${click}`;
// The clicks `spec` says how it is shown from, in order.
export function clicksOf(spec) {
  if (!spec || typeof spec !== "object") return [];
  return Object.keys(spec).map((key) => CLICK.exec(key)).filter(Boolean).map((found) => Number(found[1])).sort((a, b) => a - b);
}
// The last click anything on `slide` is shown anew on (0 for none).
export function lastClick(slide) {
  const all = [...objectsOf(slide), ...(Array.isArray(slide?.shapes) ? slide.shapes : [])];
  return Math.max(0, ...all.flatMap((spec) => clicksOf(spec)));
}
// What says how `spec` is shown at `click`: its last click up to it, else itself.
export function saidAt(spec, click = 0) {
  const named = clicksOf(spec).filter((number) => number <= click);
  if (!named.length) return spec;
  const said = spec[clickKey(named[named.length - 1])];
  return said && typeof said === "object" ? said : {};
}
const copied = (value) => (Array.isArray(value) ? value.map((item) => item) : value);
// The mapping that says how `spec` is shown from `click` on, made -- as it is shown then -- if it
// has none: `spec` itself at 0.
export function entryAt(spec, click, { shape = false } = {}) {
  if (!click) return spec;
  const key = clickKey(click);
  if (!spec[key] || typeof spec[key] !== "object") {
    const said = saidAt(spec, click), made = {};
    for (const name of Object.values(KEYS)) if (said[name] !== undefined && said[name] !== false) made[name] = copied(said[name]);
    if (shape && said === spec && spec.hidden === true) made.hide = true;
    spec[key] = made;
  }
  return spec[key];
}
// How what says it (`said`) shows it, to be compared: each key's, the figure's own (`own`: its
// lists) for those it does not say.
const showOf = (said, own = {}) => Object.fromEntries(Object.values(KEYS).map((name) => {
  const value = said?.[name] !== undefined ? said[name] : own[name];
  return [name, value === true ? true : Array.isArray(value) && value.length ? value.map(String).sort().join("\n") : ""];
}));
// `spec`'s clicks that say what the click before says taken away: what changes nothing is not said.
export function tidyClicks(spec, { shape = false, own = {} } = {}) {
  for (const click of clicksOf(spec)) {
    const before = saidAt(spec, click - 1);
    const was = shape && before === spec && spec.hidden === true ? { ...spec, hide: true } : before;
    if (JSON.stringify(showOf(spec[clickKey(click)], own)) === JSON.stringify(showOf(was, own))) delete spec[clickKey(click)];
  }
  return spec;
}
// How a figure's part `id` is shown at `click` -- by `block` (a figure's), `own` its figure's own
// lists: as its click says, the figure's own where that says nothing; null where it says nothing.
export function figurePartAt(block, id, click, own = {}) {
  const said = saidAt(block, click);
  let found = null;
  for (const [how, key] of Object.entries(KEYS)) {
    const list = Array.isArray(said[key]) ? said[key] : said[key] === undefined && Array.isArray(own[key]) ? own[key] : [];
    if (list.map(String).includes(String(id)) && (STRENGTH[how] || 0) > (STRENGTH[found] || 0)) found = how;
  }
  return found;
}
// A figure's parts `ids` shown `how` from `click` on (`block`, a figure's; `own`, its figure's
// lists): every list of the click said, the figure's own copied where it said nothing, each id
// taken out of all and put in `how`'s.
export function setFigurePart(block, ids, how, click, own = {}) {
  const entry = entryAt(block, click), wanted = ids.map(String);
  for (const key of Object.values(KEYS)) {
    if (entry[key] === true) continue;
    const list = Array.isArray(entry[key]) ? entry[key] : Array.isArray(own[key]) ? own[key] : [];
    const kept = list.filter((item) => !wanted.includes(String(item)));
    if (KEYS[how] === key) kept.push(...wanted);
    if (kept.length || (Array.isArray(own[key]) && own[key].length)) entry[key] = kept;
    else delete entry[key];
  }
  tidyClicks(block, { own });
  return block;
}
// `click` taken off `slide`: what each object and shape says of it gone, and what they say of
// the clicks after it said of the click before. What was changed, counted.
export function removeClick(slide, click) {
  let count = 0;
  for (const spec of [...objectsOf(slide), ...(Array.isArray(slide?.shapes) ? slide.shapes : [])]) {
    if (!spec || typeof spec !== "object") continue;
    const later = clicksOf(spec).filter((number) => number >= click);
    if (!later.length) continue;
    count += 1;
    const moved = later.map((number) => [number, spec[clickKey(number)]]);
    for (const [number] of moved) delete spec[clickKey(number)];
    for (const [number, said] of moved) if (number > click) spec[clickKey(number - 1)] = said;
  }
  return count;
}
// Everything on `slide` shown plainly from `click` on: each object and shape saying so then.
export function showAllAt(slide, click) {
  let count = 0;
  for (const spec of [...objectsOf(slide), ...(Array.isArray(slide?.shapes) ? slide.shapes : [])]) {
    if (!spec || typeof spec !== "object") continue;
    spec[clickKey(click)] = {};
    count += 1;
    tidyClicks(spec, { shape: (slide.shapes || []).includes(spec) });
  }
  return count;
}

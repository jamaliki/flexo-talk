// A slide drawn again, put in the page where it changed alone: the drawing it shows is patched
// -- each part of it the change touched read and put in anew, the rest left as it is -- rather
// than the whole of it read and laid out again (a slide with a large figure is thousands of
// shapes, and an edit to one of its parts changes a few).
//
// The studio writes a slide's SVG an element to a line (some lines holding a run of words'
// own elements, start and end): what changed is found line by line. A run of changed lines
// that is start tags alone has those elements' attributes made anew, what they hold kept;
// any other is put in as the run of elements side by side that holds it, each read anew whole
// from the drawing that came (in place of those that were there: as many, more or fewer, in
// the order it has them). Anything else (its markers or gradients changed, a run whose
// elements the drawing that came does not close where this one does, more changed than is
// worth patching) and the slide is put in whole, as ever.

const RESOURCES = "marker, linearGradient, radialGradient, clipPath, mask, pattern, filter, symbol";
const RESOURCE_TAGS = new Set(["marker", "lineargradient", "radialgradient", "clippath", "mask", "pattern", "filter", "symbol"]);
// (Words: the spaces between what they hold are theirs, drawn.)
const WORDS = new Set(["text", "tspan", "textpath"]);
const MOST_CHANGED = 600;  // lines changed past which the slide is put in whole
const TAG = /<(\/?)([A-Za-z][\w:.-]*)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>/g;
const START_TAG = /^\s*(<([A-Za-z][\w:.-]*)(?:[^>"']|"[^"]*"|'[^']*')*>)\s*$/;

// The drawing's elements as its words write them, in order: each one's tag, id, the lines its
// start and end are on, the element it is in (`parent`, -1 for none) and its last descendant
// (`last`) -- or null for words this does not read (a comment, CDATA, tags that do not close).
export function elementsOf(lines) {
  const found = [], open = [];
  for (let at = 0; at < lines.length; at += 1) {
    const line = lines[at];
    if (line.includes("<!") || (line.includes("<?") && !(at === 0 && line.startsWith("<?")))) return null;
    if (at === 0 && line.startsWith("<?")) continue;
    TAG.lastIndex = 0;
    for (let match = TAG.exec(line); match; match = TAG.exec(line)) {
      const [, closing, tag, attributes, empty] = match;
      if (closing) {
        const element = open.pop();
        if (!element || element.tag !== tag) return null;
        element.end = at;
        element.last = found.length - 1;
        continue;
      }
      const parent = open.length ? open[open.length - 1].index : -1;
      const element = { tag, id: /\sid="([^"]*)"/.exec(attributes)?.[1] ?? null, start: at, end: at, index: found.length, parent, last: found.length };
      found.push(element);
      if (!empty) open.push(element);
    }
  }
  return open.length ? null : found;
}

// The runs of changed lines between two drawings: [from, to) in the first, [into, upto) in the
// second -- or null, past MOST_CHANGED (Myers's diff, on the lines between those alike at
// either end).
function changedRuns(a, b) {
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head += 1;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) tail += 1;
  const ids = new Map();
  const code = (line) => { let id = ids.get(line); if (id === undefined) ids.set(line, id = ids.size); return id; };
  const x = a.slice(head, a.length - tail).map(code), y = b.slice(head, b.length - tail).map(code);
  const n = x.length, m = y.length, most = Math.min(n + m, MOST_CHANGED);
  const offset = most + 1, trace = [];
  const v = new Int32Array(2 * most + 3);
  let done = false;
  for (let d = 0; d <= most && !done; d += 1) {
    trace.push(v.slice());
    for (let k = -d; k <= d; k += 2) {
      let i = k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1]) ? v[offset + k + 1] : v[offset + k - 1] + 1;
      let j = i - k;
      while (i < n && j < m && x[i] === y[j]) { i += 1; j += 1; }
      v[offset + k] = i;
      if (i >= n && j >= m) { done = true; break; }
    }
  }
  if (!done) return null;
  // Back through the trace: the lines kept, then the runs between them.
  const kept = [];
  let i = n, j = m;
  for (let d = trace.length - 1; d > 0 && (i > 0 || j > 0); d -= 1) {
    const w = trace[d], k = i - j;
    const down = k === -d || (k !== d && w[offset + k - 1] < w[offset + k + 1]);
    const previous = down ? k + 1 : k - 1;
    const pi = w[offset + previous], pj = pi - previous;
    while (i > pi && j > pj) { i -= 1; j -= 1; kept.push([i, j]); }
    i = pi;
    j = pj;
  }
  while (i > 0 && j > 0) { i -= 1; j -= 1; kept.push([i, j]); }
  kept.reverse();
  const runs = [];
  let ai = 0, bj = 0;
  for (const [ki, kj] of [...kept, [n, m]]) {
    if (ki > ai || kj > bj) runs.push({ from: head + ai, to: head + ki, into: head + bj, upto: head + kj });
    ai = ki + 1;
    bj = kj + 1;
  }
  return runs;
}

// How the drawing written `before` is made the one written `after`: the runs of elements side
// by side read anew (`ranges`: of the element `parent`'s children, `kids` -- its lines `from` to
// `to`; none, for elements put in before its child `first` -- made the lines `start` to `end` of
// `after`), and the
// elements whose start tag alone is made anew (`retagged`, with its line in `after`). Null
// where it cannot be (see the module).
export function patchPlan(before, after, elements = elementsOf(before)) {
  const runs = changedRuns(before, after);
  if (!runs || !elements) return null;
  // (The element a line starts, where that line holds its start tag and nothing else.)
  const tagged = new Map(), crowded = new Set();
  for (const element of elements) {
    if (tagged.has(element.start) || element.end === element.start) crowded.add(element.start);
    tagged.set(element.start, element);
    if (element.end !== element.start) crowded.add(element.end);
  }
  const opens = (line) => (crowded.has(line) ? null : tagged.get(line));
  // Runs of start tags alone: their elements' attributes made anew. Their lines are known in
  // the drawing that came as much as those unchanged, for the runs about them.
  const retagged = [], others = [];
  for (const run of runs) {
    const lines = run.to - run.from;
    const tags = lines && lines === run.upto - run.into ? Array.from({ length: lines }, (_, k) => opens(run.from + k)) : [];
    // (Not the drawing's own element: the page sizes it as it puts it in.)
    if (tags.length && tags.every((element) => element && element.index > 0 && !RESOURCE_TAGS.has(element.tag.toLowerCase()))) {
      tags.forEach((element, k) => retagged.push({ element, line: after[run.into + k], from: run.from + k, into: run.into + k }));
    } else others.push(run);
  }
  const lineAt = (line) => {
    let shift = 0;
    for (const run of runs) {
      if (line < run.from) break;
      if (line < run.to) return retagged.find((tag) => tag.from === line)?.into ?? -1;
      shift += (run.upto - run.into) - (run.to - run.from);
    }
    return line < before.length ? line + shift : -1;
  };
  const kids = new Map();
  for (const element of elements) {
    if (!kids.has(element.parent)) kids.set(element.parent, []);
    kids.get(element.parent).push(element);
  }
  const ranges = [];
  for (const run of others) {
    // The smallest element round the run: its start before it, its end at or after its last line.
    let parent = null;
    for (const element of elements) {
      if (element.start < run.from && element.end >= run.to && element.end > element.start && (!parent || element.end - element.start < parent.end - parent.start)) parent = element;
    }
    // Its children the run touches, widened until the lines either side are known in both
    // drawings -- else the parent itself, among its own side by side.
    let range = null, from = run.from, to = run.to;
    while (parent && !range) {
      const own = kids.get(parent.index) || [];
      let first = own.findIndex((kid) => kid.end >= from && kid.start < to);
      let last = own.findLastIndex((kid) => kid.end >= from && kid.start < to);
      if (first < 0) { first = own.findIndex((kid) => kid.start >= from); if (first < 0) first = own.length; last = first - 1; }
      for (;;) {
        const lineBefore = first > 0 ? own[first - 1].end : parent.start;
        const lineAfter = last + 1 < own.length ? own[last + 1].start : parent.end;
        if (lineBefore >= from || lineAfter < to) break;
        const at = lineAt(lineBefore), upto = lineAt(lineAfter);
        // (The lines between read as whole elements -- else the lines alike either side were
        // matched one for another, as a "</g>" may be: wider.)
        const whole = at >= 0 && upto > at && (upto === at + 1 || elementsOf(after.slice(at + 1, upto)));
        if (whole) { range = { parent, first, last, start: at + 1, end: upto - 1, from: lineBefore + 1, to: lineAfter - 1 }; break; }
        if ((at < 0 || upto >= 0) && first > 0) { first -= 1; continue; }
        if (last + 1 < own.length) { last += 1; continue; }
        break;
      }
      if (range) break;
      if (parent.parent < 0) return null;
      from = parent.start;
      to = parent.end + 1;
      parent = elements[parent.parent];
    }
    if (!range) return null;
    ranges.push(range);
  }
  // Runs side by side in one parent made one; one inside another's, the other's alone.
  ranges.sort((one, other) => one.from - other.from || other.to - one.to);
  const merged = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last && range.from >= last.from && range.to <= last.to) continue;
    if (last && last.parent === range.parent && range.first <= last.last + 1) {
      Object.assign(last, { last: Math.max(last.last, range.last), end: Math.max(last.end, range.end), to: Math.max(last.to, range.to) });
      continue;
    }
    if (last && range.from <= last.to) return null;
    merged.push(range);
  }
  return {
    runs,
    ranges: merged.map(({ parent, first, last, start, end, from, to }) => ({
      parent, first, start, end, from, to, kids: (kids.get(parent.index) || []).slice(first, last + 1), next: (kids.get(parent.index) || [])[last + 1] || null,
    })),
    retagged: retagged.filter(({ element }) => !merged.some((range) => element.start >= range.from && element.start <= range.to)),
  };
}

// The drawing `svg` put in the page from `text`: its elements kept in the order its words write
// them, for the next drawing to be patched into it (before anything is added to it in the page).
const drawn = new WeakMap();
export function indexDrawing(svg, text) {
  if (!svg) return;
  drawn.set(svg, { text, elements: [svg, ...svg.querySelectorAll("*")] });
}

// The drawing `svg` (put in from the words indexDrawing was given) made the drawing `text`
// where they differ: true if it was, false if it is to be put in whole. `prepare(holder)` makes
// what is read anew ready for the page (as the slide put in whole is), before it goes in.
// Why the last drawing was put in whole, not patched (null: it was patched).
export let refused = null;
const refuse = (why) => { refused = why; return false; };

export function patchDrawing(svg, text, prepare) {
  const known = svg && drawn.get(svg);
  if (!known || !svg.isConnected) return refuse("not put in from words");
  if (known.text === text) return true;
  const before = known.text.split("\n"), after = text.split("\n");
  const elements = elementsOf(before);
  if (!elements || elements.length !== known.elements.length) return refuse("its words do not read as its elements");
  // (Nothing the page put over the drawing -- a part lifted as it is carried, a copy left where
  // it was let go -- for a part drawn anew to be drawn twice.)
  const indexed = new Set(known.elements);
  if ([...svg.children].some((child) => !indexed.has(child))) return refuse("something put over it");
  const plan = patchPlan(before, after, elements);
  if (!plan) return refuse("no runs of elements hold what changed");
  const live = (element) => known.elements[element.index];
  // Each read, and checked, before any is put in.
  const made = [];
  for (const range of plan.ranges) {
    const parent = live(range.parent);
    if (!parent?.isConnected || !svg.contains(parent) || WORDS.has(parent.localName.toLowerCase()) || RESOURCE_TAGS.has(parent.localName.toLowerCase())) return refuse(`in ${range.parent.id || range.parent.tag}`);
    const old = range.kids.map(live);
    if (old.some((element, k) => element?.parentNode !== parent || (element.getAttribute("id") ?? null) !== range.kids[k].id
      || RESOURCE_TAGS.has(element.localName.toLowerCase()) || element.querySelector(RESOURCES))) return refuse(`elements of ${range.parent.id || range.parent.tag} moved or named anew, or its markers`);
    // (Each of their own where it was drawn: none carried off elsewhere.)
    if (range.kids.some((kid, k) => known.elements.slice(kid.index, kid.last + 1).some((own) => !old[k].contains(own)))) return refuse("a part carried off");
    const lines = range.end >= range.start ? after.slice(range.start, range.end + 1) : [];
    const inner = elementsOf(lines);
    const holder = document.createElement("div");
    holder.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg">${lines.join("\n")}</svg>`;
    const read = holder.firstElementChild;
    const fresh = [...read.querySelectorAll("*")];
    if (!inner || inner.length !== fresh.length || inner.filter((element) => element.parent < 0).length !== read.childElementCount || read.querySelector(RESOURCES)) return refuse(`what came for ${range.parent.id || range.parent.tag} does not read as elements`);
    const next = old.length ? old[old.length - 1].nextSibling : range.next ? live(range.next) : null;
    if (next && next.parentNode !== parent) return refuse("its place moved");
    const at = range.kids.length ? range.kids[0].index : range.next ? range.next.index : range.parent.last + 1;
    const count = range.kids.length ? range.kids[range.kids.length - 1].last + 1 - range.kids[0].index : 0;
    made.push({ parent, old, read, fresh, next, at, count });
  }
  const tags = [];
  for (const { element, line } of plan.retagged) {
    const own = live(element);
    const tag = START_TAG.exec(line);
    if (!own?.isConnected || !svg.contains(own) || !tag || tag[1].endsWith("/>") || tag[2] !== element.tag) return refuse(`${element.id || element.tag} retagged as another`);
    const holder = document.createElement("div");
    holder.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg">${tag[1]}</${tag[2]}></svg>`;
    const read = holder.firstElementChild, fresh = read?.firstElementChild;
    if (!fresh || fresh.localName !== own.localName || (fresh.getAttribute("id") ?? null) !== element.id || (own.getAttribute("id") ?? null) !== element.id) return refuse(`${element.id || element.tag} renamed`);
    tags.push({ own, fresh, read });
  }
  // All read: put in.
  const owned = ownedIn(svg);
  for (const { parent, old, read, next } of made) {
    owned(read);
    prepare(read);
    // (The spaces between the old go with them; those either side stay.)
    for (let node = old[0]; node; ) {
      const following = node.nextSibling;
      node.remove();
      if (node === old[old.length - 1]) break;
      node = following;
    }
    for (const node of trimmed([...read.childNodes])) parent.insertBefore(node, next);
  }
  for (const { own, fresh, read } of tags) {
    owned(read);
    for (const name of own.getAttributeNames()) if (!fresh.hasAttribute(name)) own.removeAttribute(name);
    for (const name of fresh.getAttributeNames()) if (own.getAttribute(name) !== fresh.getAttribute(name)) own.setAttribute(name, fresh.getAttribute(name));
  }
  const list = [...known.elements];
  for (const { at, count, fresh } of [...made].sort((one, other) => other.at - one.at)) list.splice(at, count, ...fresh);
  drawn.set(svg, { text, elements: list });
  refused = null;
  return true;
}

// Nodes read, without the spaces at either end (those about the old stay where they are).
function trimmed(nodes) {
  while (nodes.length && nodes[0].nodeType === 3 && !nodes[0].textContent.trim()) nodes.shift();
  while (nodes.length && nodes[nodes.length - 1].nodeType === 3 && !nodes[nodes.length - 1].textContent.trim()) nodes.pop();
  return nodes;
}

// What the drawing's markers, gradients and clips are named in the page (drawings.js
// ownResources renamed them, ~ and a tag after their names): what is read anew names them so.
function ownedIn(svg) {
  const renamed = new Map();
  for (const node of svg.querySelectorAll(RESOURCES)) {
    const id = node.id, at = id.lastIndexOf("~");
    if (at > 0) renamed.set(id.slice(0, at), id);
  }
  const swap = (value) => value.replace(/url\(\s*(['"]?)#([^)'"]+)\1\s*\)/g, (whole, quote, id) => (renamed.has(id) ? `url(#${renamed.get(id)})` : whole));
  return (root) => {
    if (!renamed.size) return;
    for (const node of root.querySelectorAll("*")) {
      for (const attr of [...node.attributes]) {
        if (attr.value.includes("url(")) attr.value = swap(attr.value);
        else if (attr.localName === "href" && attr.value.startsWith("#") && renamed.has(attr.value.slice(1))) attr.value = `#${renamed.get(attr.value.slice(1))}`;
      }
      if (node.localName === "style" && node.textContent.includes("url(")) node.textContent = swap(node.textContent);
    }
  };
}

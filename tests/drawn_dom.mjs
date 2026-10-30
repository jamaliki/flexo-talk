// A drawing read into elements enough like a page's for stepping.js to change them in Node: their
// attributes, their children, querySelectorAll by a tag or an attribute, cloneNode and after --
// and what each element with an id is drawn as, to compare with what Python draws.
export class El {
  constructor(tag, attrs, parent) { this.localName = tag; this.attrs = new Map(attrs); this.children = []; this.parentNode = parent; }
  getAttribute(name) { return this.attrs.has(name) ? this.attrs.get(name) : null; }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  removeAttribute(name) { this.attrs.delete(name); }
  hasAttribute(name) { return this.attrs.has(name); }
  get attributes() { return [...this.attrs].map(([name, value]) => ({ name, value })); }
  get id() { return this.getAttribute("id") || ""; }
  set id(value) { this.setAttribute("id", value); }
  *walk() { for (const child of this.children) { yield child; yield* child.walk(); } }
  querySelectorAll(selector) {
    const has = /^\[([\w-]+)\]$/.exec(selector);
    const test = selector === "*" ? () => true : has ? (one) => one.hasAttribute(has[1]) : (one) => one.localName === selector;
    return [...this.walk()].filter(test);
  }
  cloneNode() { const copy = new El(this.localName, this.attrs, null); copy.children = this.children.map((child) => { const one = child.cloneNode(); one.parentNode = copy; return one; }); return copy; }
  after(node) { const list = this.parentNode.children; node.parentNode = this.parentNode; list.splice(list.indexOf(this) + 1, 0, node); }
}
const unescape = (text) => text.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n))).replace(/&amp;/g, "&");
export function read(text) {
  const root = new El("#root", [], null);
  let at = root;
  for (const [, closing, tag, body, empty] of text.matchAll(/<(\/?)([\w:.-]+)((?:[^>"']|"[^"]*"|'[^']*')*?)(\/?)>/g)) {
    if (closing) { at = at.parentNode; continue; }
    const attrs = [...body.matchAll(/([\w:.-]+)="([^"]*)"/g)].map(([, name, value]) => [name, unescape(value)]);
    const made = new El(tag.replace(/^\w+:/, ""), attrs, at);
    at.children.push(made);
    if (!empty) at = made;
  }
  return root.children.find((one) => one.localName === "svg");
}
export function drawnAs(svg) {
  const found = {};
  for (const one of [svg, ...svg.walk()]) {
    const id = one.getAttribute("id");
    if (!id || id.includes(".arrow.") || id.endsWith(".dimmed")) continue;
    const ends = ["marker-start", "marker-end"].map((end) => (one.getAttribute(end) || "").replace(".dimmed", ""));
    found[id] = [...["fill", "stroke", "visibility", "opacity", "data-flexo-show"].map((key) => one.getAttribute(key)), ...ends];
  }
  return found;
}

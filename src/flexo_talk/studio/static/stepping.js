// A slide's drawing shown as it is at a step of its builds: what builds in later marked so
// (data-flexo-later: left out when presenting, a ghost while edited), and what a click shows
// anew (flexo_talk.onclick) shown as it is then -- hidden, faint, or plainly again -- by changing
// those elements' own attributes in place. The drawing is kept as it is: a click reads nothing
// again, whatever step it goes to, forward, back or a jump.
//
// The drawing comes as the slide is before its first click. What a click shows anew is marked
// with how it is shown at each step (data-flexo-shows, a word a step: shown, dimmed, hidden);
// what is faint keeps its paints as they are plainly (data-flexo-was-fill...), as the slide's
// drawing has them for what is faint at its first step and as this keeps them for what it
// draws faint. Faint is the figure's faint (flexo.showing.faint): every colour most of the way
// to the page's (data-flexo-page), a picture see-through -- what a PDF of the step draws.

const DIM = 0.28;
const MARK = "data-flexo-show";
const SHOWS = "data-flexo-shows";
const WAS = "data-flexo-was-";
const LATER = "data-flexo-later";
const PAINTS = ["fill", "stroke", "stop-color", "flood-color"];
const ENDS = ["marker-start", "marker-mid", "marker-end"];
const HEX = /^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/;
const HEXES = /#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b/g;
const HAS_HEX = /#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b/;

// `colour` (#rgb or #rrggbb) as it is drawn faint on a page of `page`: DIM of it, the rest the
// page's (flexo.showing.faint).
export function faint(colour, page) {
  const parts = (value) => {
    let hex = String(value).replace(/^#/, "");
    if (hex.length === 3) hex = [...hex].map((letter) => letter + letter).join("");
    return /^[0-9a-fA-F]{6}$/.test(hex) ? [0, 2, 4].map((at) => parseInt(hex.slice(at, at + 2), 16)) : null;
  };
  const own = parts(colour), ground = parts(page) || [255, 255, 255];
  if (!own) return colour;
  return `#${own.map((value, at) => Math.round(DIM * value + (1 - DIM) * ground[at]).toString(16).padStart(2, "0")).join("")}`;
}

// How what is marked `seq` (data-flexo-shows) is shown at `step` (from 1): its last word holds.
export function stepOf(seq, step) {
  const words = String(seq || "").trim().split(/\s+/).filter(Boolean);
  return words.length ? words[Math.max(0, Math.min(step, words.length) - 1)] : "shown";
}

// `svg` (a slide's drawing, in the page) shown as the slide is at `step` (from 1). `builds`:
// whether what builds in later is marked so -- not, to show the slide as it is edited, all of
// it there and each thing as it is before the first click.
export function showStep(svg, step, { builds = true } = {}) {
  if (!svg?.querySelectorAll) return;
  for (const item of svg.querySelectorAll("[data-flexo-step]")) {
    const later = builds && Number(item.getAttribute("data-flexo-step")) > step;
    if (later !== item.hasAttribute(LATER)) {
      if (later) item.setAttribute(LATER, "");
      else item.removeAttribute(LATER);
    }
  }
  const marked = [...svg.querySelectorAll(`[${SHOWS}]`)];
  if (!marked.length) return;
  const page = svg.getAttribute("data-flexo-page") || "#ffffff";
  const wanted = marked.map((item) => [item, stepOf(item.getAttribute(SHOWS), step)]);
  // What is shown otherwise now shown plainly first, then each as it is at this step: at any
  // step, what is faint is apart from all else faint.
  for (const [item, want] of wanted) if ((item.getAttribute(MARK) || "shown") !== want) plainly(item);
  for (const [item, want] of wanted) {
    if ((item.getAttribute(MARK) || "shown") === want) continue;
    if (want === "hidden") {
      item.setAttribute(MARK, "hidden");
      item.setAttribute("visibility", "hidden");
    } else if (want === "dimmed") fade(item, page, svg);
  }
}

// `item` shown plainly again: shown where it was hidden, its paints as they are plainly where
// it was faint.
export function plainly(item) {
  const how = item.getAttribute(MARK);
  item.removeAttribute(MARK);
  if (how === "hidden") item.removeAttribute("visibility");
  else if (how === "dimmed") {
    for (const one of [item, ...item.querySelectorAll("*")]) {
      for (const attr of [...one.attributes]) {
        if (!attr.name.startsWith(WAS)) continue;
        const name = attr.name.slice(WAS.length), value = attr.value;
        one.removeAttribute(attr.name);
        if (value) one.setAttribute(name, value);
        else one.removeAttribute(name);
      }
    }
  }
}

// `item` and all in it drawn faint -- but what is faint already (marked so), faint once: as
// flexo.showing.mark draws it, each paint kept as it was (WAS) to be shown plainly again.
function fade(item, page, svg) {
  const keep = (one, name) => { if (!one.hasAttribute(WAS + name)) one.setAttribute(WAS + name, one.getAttribute(name) ?? ""); };
  const walk = (one) => {
    for (const name of PAINTS) {
      const value = one.getAttribute(name)?.trim();
      if (value && HEX.test(value)) { keep(one, name); one.setAttribute(name, faint(value, page)); }
    }
    const style = one.getAttribute("style");
    if (style && HAS_HEX.test(style)) { keep(one, "style"); one.setAttribute("style", style.replace(HEXES, (found) => faint(found, page))); }
    if (one.localName === "image") {
      const was = Number(one.getAttribute("opacity") ?? 1);
      keep(one, "opacity");
      one.setAttribute("opacity", String(Number((DIM * Math.min(1, Math.max(0, Number.isFinite(was) ? was : 1))).toPrecision(4))));
    }
    for (const name of ENDS) {
      const found = /^url\(#(.+)\)$/.exec(one.getAttribute(name) || "");
      const copy = found ? fainted(svg, found[1], page) : null;
      if (copy) { keep(one, name); one.setAttribute(name, `url(#${copy})`); }
    }
    for (const child of one.children) if (child.getAttribute(MARK) !== "dimmed") walk(child);
  };
  walk(item);
  item.setAttribute(MARK, "dimmed");
}

// The faint copy of the arrowhead `name` (a marker other lines share), made once: its id.
function fainted(svg, name, page) {
  const markers = [...svg.querySelectorAll("marker")];
  const marker = markers.find((one) => one.id === name);
  if (!marker) return null;
  const id = `${name}.dimmed`;
  if (markers.some((one) => one.id === id)) return id;
  const copy = marker.cloneNode(true);
  copy.id = id;
  for (const one of [copy, ...copy.querySelectorAll("*")]) {
    for (const key of PAINTS) {
      const value = one.getAttribute(key)?.trim();
      if (value && HEX.test(value)) one.setAttribute(key, faint(value, page));
    }
  }
  marker.after(copy);
  return id;
}

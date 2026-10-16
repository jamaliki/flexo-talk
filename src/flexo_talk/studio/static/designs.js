// A deck's design as the Design bar shows it and changes it (designbar.js): what slide its
// theme gallery shows, its slide sizes, backgrounds and font pairs, and a design's variants --
// the deck's settings with one changed -- as the studio draws them (previews.py). Nothing here
// touches the page, so it is read in Node as it is in the studio.

// A slide's size by name, as PowerPoint's Slide Size offers them: points, the height a slide
// keeps (every size in a deck is of a slide 540 high), its width as wide as its proportions say.
export const SLIDE_SIZES = [
  { value: "16:9", label: "Widescreen", width: 960, height: 540 },
  { value: "4:3", label: "Standard", width: 720, height: 540 },
  { value: "16:10", label: "16:10", width: 864, height: 540 },
  { value: "1:1", label: "Square", width: 540, height: 540 },
];
export const DEFAULT_SIZE = SLIDE_SIZES[0];
// A slide's width or height, in points, as a deck may set them (deck.py's _STYLE_NUMBERS).
export const SIZE_RANGE = [72, 4032];

// The deck's slides' size: its width and height, its name if it has one ("custom" else), and
// its proportions.
export function slideSize(deck) {
  const style = deck?.style && typeof deck.style === "object" ? deck.style : {};
  const width = number(style.width) ?? DEFAULT_SIZE.width, height = number(style.height) ?? DEFAULT_SIZE.height;
  const named = SLIDE_SIZES.find((size) => size.width === width && size.height === height);
  return { width, height, value: named?.value ?? "custom", ratio: width / height };
}
const number = (value) => (typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null);

// The deck's settings with its slides of `size` ({width, height}, or a size's name): the
// default written as nothing, a style left empty taken away.
export function sized(deck, size) {
  const made = structuredClone(deck || {});
  const wanted = typeof size === "string" ? SLIDE_SIZES.find((each) => each.value === size) : size;
  if (!wanted) return made;
  const [least, most] = SIZE_RANGE;
  const clamp = (value) => Math.round(Math.min(most, Math.max(least, Number(value))) * 100) / 100;
  const style = { ...(made.style && typeof made.style === "object" ? made.style : {}) };
  for (const key of ["width", "height"]) {
    const value = clamp(wanted[key]);
    if (value === DEFAULT_SIZE[key]) delete style[key]; else style[key] = value;
  }
  if (Object.keys(style).length) made.style = style; else delete made.style;
  return made;
}

// The slide a theme gallery shows: the deck's title slide, else its first; -1 with none.
export function gallerySlide(slides) {
  const list = Array.isArray(slides) ? slides : [];
  const titled = list.findIndex((slide) => slide && typeof slide === "object" && slide.layout === "title" && slide.skip !== true);
  return titled >= 0 ? titled : list.length ? 0 : -1;
}

// What a variant may change, as the studio draws it (previews.py's DESIGN).
export const DESIGN = ["theme", "palette", "font", "title_font", "figure_font", "look", "background", "style"];

// The deck's settings with a variant's put over them: `null` takes one away (the default).
export function withVariant(deck, variant) {
  const made = { ...(deck || {}) };
  for (const [key, value] of Object.entries(variant || {})) {
    if (!DESIGN.includes(key)) continue;
    if (value === null || value === undefined) delete made[key]; else made[key] = value;
  }
  return made;
}

// A variant put in the document, as one change: the deck's settings it names set, or taken
// away where it says null (the default, written as nothing).
export function applyVariant(deck, variant) {
  for (const [key, value] of Object.entries(variant || {})) {
    if (!DESIGN.includes(key)) continue;
    if (value === null || value === undefined) delete deck[key]; else deck[key] = value;
  }
  return deck;
}

// Whether the deck is as a variant would make it: the one in use, marked.
export function hasVariant(deck, variant) {
  return Object.entries(variant || {}).every(([key, value]) => same(deck?.[key] ?? null, value ?? null));
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// A short name for what a drawing was made from: equal for equal designs and slides.
export function keyOf(...parts) {
  const text = JSON.stringify(parts);
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return `${(hash >>> 0).toString(36)}${text.length.toString(36)}`;
}

// The deck's background: the theme's page, none, a colour, or a picture.
export function backgroundOf(deck) {
  const value = deck?.background;
  if (value === undefined || value === null || value === true) return { kind: "theme", value: null };
  if (value === false) return { kind: "none", value: false };
  if (typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value)) return { kind: "colour", value: value.toLowerCase() };
  return { kind: "picture", value: String(value) };
}
// Backgrounds a click away: light ones, as the theme's words are drawn on any (a dark page is a
// theme's own: Dark), the theme's page first, and any colour can be picked besides.
export const BACKGROUNDS = [
  ["#ffffff", "White"], ["#f7f4ee", "Paper"], ["#fdf6e3", "Cream"],
  ["#f3efe6", "Sand"], ["#eef1f5", "Mist"], ["#edf5f9", "Sky"],
];

// The fonts a deck may be set in, a click away: the theme's own, two faces that go together
// (titles in one, words in the other), and one face for every word. Only those this Mac has.
export const FONT_PAIRS = [
  ["Georgia", "Helvetica Neue"], ["Baskerville", "Gill Sans"], ["Palatino", "Avenir Next"],
  ["Futura", "Avenir Next"], ["Charter", "Inter"], ["Iowan Old Style", "Source Sans 3"],
];
export function fontChoices(available, single) {
  const there = new Set((available || []).map((name) => String(name).toLowerCase()));
  const has = (name) => there.has(name.toLowerCase()) || name.toLowerCase() === "helvetica";
  const pairs = FONT_PAIRS.filter(([title, body]) => has(title) && has(body))
    .map(([title, body]) => ({ value: `${title} / ${body}`, title, body, variant: { font: body, title_font: title, figure_font: null } }));
  const singles = (single || []).filter(has).map((name) => ({ value: name, title: name, body: name, variant: { font: name, title_font: null, figure_font: null } }));
  return [{ value: "", title: null, body: null, variant: { font: null, title_font: null, figure_font: null } }, ...pairs, ...singles];
}

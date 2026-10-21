// Slides and objects copied in one deck and pasted in another: what the deck's editor
// (editor.js) needs.
//
// A copy says where its deck is (`deckFolder`: the folder on the computer its files are named
// from) and carries the figures of the deck's own it shows (`figures`: those a block names
// '#name', kept once in the deck for several slides). Pasted in a deck of another folder --
// another window of the Mac app, another studio in a browser -- the files its slides, objects
// and shapes name (pictures, GIFs, portraits, figure files and theirs, plots' Python, and the
// files of those figures) are copied into this deck's folder first, each renamed where a file
// of its name is another here (flexo_talk.pasting), and the copy names them so. The figures
// it carries are put in this deck's own, each by its name -- or, where this deck has another
// figure of that name, numbered ('#pipeline-2'), the blocks naming it named so; one this deck
// has already, the very same, is used as it is. Pasted in the deck it came from, or another
// of the same folder, its files are where they were.

import { toast, same } from "/static/studio/studio.js";
import { clipsOf } from "/static/studio/mixing.js";

// The folder the deck is in, on the computer: the studio's own, and the deck's place in it.
export function deckFolder(studio) {
  const root = String(studio.workspace?.info?.folder || "").replace(/\/+$/, "");
  return root ? `${root}/${studio.folder()}`.replace(/\/+$/, "") : "";
}

// What of a copy names files, as slides (a slide's objects in its body, its shapes as its
// shapes): [slides, back], `back(slides)` the copy again with those in their places. (A
// figure's shapes are the figure's: they are not looked through.)
function asSlides(clip) {
  const pieces = clipsOf(clip);
  const slides = [];
  const at = pieces.map((piece) => {
    const from = slides.length;
    if (piece.what === "slides" && Array.isArray(piece.slides)) slides.push(...piece.slides);
    else if (piece.what === "slide" && piece.slide) slides.push(piece.slide);
    else if (piece.what === "block" && piece.block) slides.push({ body: [piece.block] });
    else if (piece.what === "blocks" && Array.isArray(piece.blocks)) slides.push({ body: piece.blocks });
    else if (piece.what === "shapes" && Array.isArray(piece.shapes)) slides.push({ shapes: piece.shapes });
    return [from, slides.length];
  });
  const back = (made) => {
    const each = pieces.map((piece, n) => {
      const [from, to] = at[n];
      if (from === to) return piece;
      const mine = made.slice(from, to);
      if (piece.what === "slides") return { ...piece, slides: mine };
      if (piece.what === "slide") return { ...piece, slide: mine[0] };
      if (piece.what === "block") return { ...piece, block: mine[0].body[0] };
      if (piece.what === "blocks") return { ...piece, blocks: mine[0].body };
      return { ...piece, shapes: mine[0].shapes };
    });
    return clip?.what === "mixed" ? { ...clip, clips: each } : { ...each[0], from: clip.from, figures: clip.figures };
  };
  return [slides, back];
}

// The figures of the deck's own (`figures`, its `figures`) that what is copied names: { name:
// figure }, none if it names none.
export function figuresNamed(clip, figures) {
  const found = {};
  if (!figures || typeof figures !== "object") return found;
  const look = (value) => {
    if (Array.isArray(value)) { value.forEach(look); return; }
    if (!value || typeof value !== "object") return;
    for (const [key, item] of Object.entries(value)) {
      if (key === "figure" && typeof item === "string" && item.startsWith("#")) {
        const name = item.slice(1);
        if (figures[name] && !(name in found)) found[name] = structuredClone(figures[name]);
      } else look(item);
    }
  };
  look(asSlides(clip)[0]);
  return found;
}

// A copy (`clip`) as it is pasted in this deck: from a deck of another folder, the files it
// and the figures it carries name copied here first and named so. A promise of it. Should
// its files not come, it comes as it is, and that is said.
export async function broughtClip(studio, clip) {
  const here = deckFolder(studio);
  if (!clip?.from || !here || clip.from === here) return clip;
  const [slides, back] = asSlides(clip);
  const figures = clip.figures && Object.keys(clip.figures).length ? clip.figures : null;
  if (!slides.length && !figures) return clip;
  try {
    const result = await studio.api("/api/act", { file: studio.file, action: { do: "bring-slides", from: clip.from, slides, ...(figures ? { figures } : {}) } });
    if (result?.missing?.length) {
      const named = result.missing.slice(0, 3).map((name) => `“${name}”`).join(", ");
      toast(`${result.missing.length === 1 ? "A file it names isn’t" : `${result.missing.length} files it names aren’t`} where it was copied from: ${named}${result.missing.length > 3 ? "…" : ""}`, { icon: "info", seconds: 6 });
    }
    if (!Array.isArray(result?.slides) || result.slides.length !== slides.length) return clip;
    const made = back(result.slides);
    return figures && result.figures ? { ...made, figures: result.figures } : made;
  } catch (error) {
    toast(`Pasted, but not the files it names: ${error.message}`, { icon: "info", seconds: 6 });
    return clip;
  }
}

// The figures a copy carries (`clip.figures`) put among this deck's (`have`): each by its
// name, the very same one here used as it is, another of its name here numbered ('-2', '-3'…)
// and the blocks naming it named so. { clip, add }: the copy naming them as they are here,
// and the figures for the deck to have besides.
export function placedFigures(clip, have) {
  const given = clip?.figures && typeof clip.figures === "object" ? clip.figures : {};
  const mine = have && typeof have === "object" ? have : {};
  const add = {}, renamed = {};
  for (const [name, figure] of Object.entries(given)) {
    let own = name, count = 1;
    while ((own in mine && !same(mine[own], figure)) || (own in add && !same(add[own], figure))) own = `${name}-${++count}`;
    if (!(own in mine)) add[own] = figure;
    if (own !== name) renamed[name] = own;
  }
  if (!Object.keys(renamed).length) return { clip, add };
  const rename = (value) => {
    if (Array.isArray(value)) return value.map(rename);
    if (!value || typeof value !== "object") return value;
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key,
      key === "figure" && typeof item === "string" && item.startsWith("#") && renamed[item.slice(1)] ? `#${renamed[item.slice(1)]}` : rename(item)]));
  };
  const [slides, back] = asSlides(clip);
  return { clip: back(slides.map(rename)), add };
}

// Convert to Figure Parts on a slide: the slide's shapes chosen, drawn as a diagram, made a
// figure on it (convert.py) -- in the column they were drawn over, among its objects by where
// they were drawn, or in place of its empty placeholders. One step in the history.

import { toast } from "/static/studio/studio.js";
import * as F from "/static/studio/freeform.js";
import { CONVERT } from "/static/studio/toparts.js";

// Where the figure goes: the region whose room holds the drawing's middle (else the nearest),
// after its objects drawn above that middle -- or in place of the layout's placeholders.
// `regions`: the editor's regionsDrawn(); `middle`: the drawing's, in the page's pixels.
export function placeFor(regions, middle, placeholder) {
  if (!regions.length) return null;
  const gap = (room) => (room ? Math.hypot(Math.max(room.left - middle.x, 0, middle.x - room.right), Math.max(room.top - middle.y, 0, middle.y - room.bottom)) : Infinity);
  const region = regions.reduce((best, each) => (gap(each.room) < gap(best.room) ? each : best), regions[0]);
  const blocks = region.blocks || [];
  const replace = blocks.length > 0 && blocks.every((block) => placeholder(region.key, block.index));
  const index = replace ? 0 : blocks.filter((block) => block.box && (block.box.top + block.box.bottom) / 2 < middle.y).length;
  return { region: region.key, index, replace };
}

// The shapes chosen made a figure on the slide. `toScreen`: a point in the shapes' units, in
// the page's pixels; `apply(document, label)`: the deck made the one the studio answers with,
// as one step (its glue kept as the studio wrote it).
export async function slideToParts({ studio, slide, picks, shapes, regions, toScreen, placeholder, apply, chosen }) {
  const specs = picks.map((index) => shapes[index]).filter(Boolean);
  if (!specs.length) return;
  const boxes = specs.map((spec) => { try { return F.bounds(spec); } catch { return null; } }).filter(Boolean);
  const left = Math.min(...boxes.map((box) => box[0])), top = Math.min(...boxes.map((box) => box[1]));
  const right = Math.max(...boxes.map((box) => box[2])), bottom = Math.max(...boxes.map((box) => box[3]));
  const [x, y] = toScreen([(left + right) / 2, (top + bottom) / 2]);
  const where = placeFor(regions, { x, y }, placeholder) || {};
  try {
    const result = await studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "convert", slide, shapes: picks, ...where } });
    apply(result.document, CONVERT);
    chosen?.(result.select);
    if (result.said) toast(`${result.said}.`, { icon: "figure", seconds: 4 });
  } catch (error) {
    toast(error.message, { kind: "error", icon: "error", seconds: 6 });
  }
}

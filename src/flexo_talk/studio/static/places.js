// Where a slide's object stands when it is placed where it is put (a block's `at`, its `width`
// its width there, in the units the slide's shapes are placed in: flexo_talk.document) -- the
// sums alone, for placing.js (where the person meets them), read in Node as in the studio.
//
// - Taken out of line, an object stands at its frame as the slide drew it (compose.py's
//   data-flexo-frame: [x, y, width, height]), that wide -- rounded, its width never a hair
//   narrower than it was drawn, else its words would wrap -- so nothing about it moves or
//   changes: a plot keeps its proportions as its aspect, a gallery its pictures' height.
// - Moved, its top left moves.
// - Put back in line, it is in its place's flow again, where it is in its list: the width it
//   was given dropped where it would fill its place anyway, else kept (in the place's points).

export const round = (value) => Math.round(value * 100) / 100;
// (A width written never a hair narrower than it is drawn.)
export const roundUp = (value) => Math.ceil(value * 100 - 1e-6) / 100;

// Whether a block stands where it says on the slide, out of its place's flow.
export const placed = (block) => Array.isArray(block?.at) && block.at.length === 2 && block.at.every((value) => Number.isFinite(Number(value)));

// `block` (of `kind`) made to stand at `frame`, as wide: `pictures`, a gallery's pictures'
// height as drawn (compose.py's data-flexo-cells), kept as its own.
export function stand(block, frame, kind, { pictures = null } = {}) {
  block.at = [round(frame[0]), round(frame[1])];
  block.width = roundUp(frame[2]);
  if (kind === "plot" && !block.aspect && frame[3] > 0) block.aspect = Math.round((frame[2] / frame[3]) * 1000) / 1000;
  if (kind === "gallery" && !block.height && Number.isFinite(pictures) && pictures > 0) block.height = round(pictures);
  delete block.placeholder;
  return block;
}

// `block` placed moved by `dx`, `dy`.
export function movedBy(block, dx, dy) {
  block.at = [round(Number(block.at[0]) + dx), round(Number(block.at[1]) + dy)];
  delete block.placeholder;
  return block;
}

// `block` put back in its place's flow: its width, in the shapes' units, made the place's
// points (`scale` of them in one), dropped where it would fill its place (`room` points wide).
export function inLine(block, scale = 1, room = null) {
  delete block.at;
  if (block.width != null) {
    const width = Number(block.width) * scale;
    if (room && width >= room - 1) delete block.width;
    else block.width = Math.round(width);
  }
  return block;
}

// Where several stand, as X and Y say it: the top left of what they reach.
export const reach = (boxes) => {
  const all = boxes.filter(Boolean);
  return all.length ? [Math.min(...all.map((box) => box[0])), Math.min(...all.map((box) => box[1]))] : null;
};

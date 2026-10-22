// What a slide's object sized by the editor's own handles catches at -- a picture, a plot, a
// gallery or a table in line by a corner, words in line by a side -- as a placed object's and a
// shape's moving edges do (placing.js, aligning.js's sizeCatch): where an edge that moves as it
// is sized comes within reach of a guide (the slide's edges and middles, the shapes' and the
// other objects' edges and middles, the grid's lines), the size that puts it on that guide.
//
// Sized so, it is not where the pointer puts it but where its place stands it at that size:
// in proportion, from its top, about its middle, no wider than its place. So the size is found
// that puts the edge there, as the slide will stand it -- not the pointer moved.
//
// No page is needed: it is read in Node as it is in the studio.

// The edges of `box` ({ left, top, width, height }) one way: "x" its left and right, "y" its
// top and bottom.
const edgesOf = (box, axis) => (axis === "x" ? [box.left, box.left + box.width] : [box.top, box.top + box.height]);

// `place(size)`: where it stands at `size` (a scale or a width: whatever grows it), as
// { left, top, width, height } in any one unit; `size` the one the pointer gives;
// `catches(axis, values)`: the nearest guide to any of `values` ("x": across, "y": down) within
// reach, as { gap, at } (snapping.js's `nearest`), or null; `least`, `most`: the sizes it may
// be. Of the edges that move as it is sized, the one nearest a guide: { size (that puts it on
// the guide), gap (how far it was from it), axis, at } -- or null: none within reach, none
// that moves, or none that any size it may be puts there.
export function sizeCaught(place, size, catches, { least = 0, most = Infinity } = {}) {
  const now = place(size);
  if (!now) return null;
  // (How fast an edge moves as it grows, near `at`: none, it stays where it is.)
  const step = Math.max(Math.abs(size) * 1e-4, 1e-9);
  const rate = (at, axis, index) => {
    const ahead = place(Math.min(at + step, most)), behind = place(Math.max(at - step, least));
    const span = Math.min(at + step, most) - Math.max(at - step, least);
    return ahead && behind && span > 0 ? (edgesOf(ahead, axis)[index] - edgesOf(behind, axis)[index]) / span : 0;
  };
  // (Close enough: a thousandth of how large it is, whatever the unit.)
  const close = Math.max(Math.abs(now.width), Math.abs(now.height), 1) * 1e-3;
  let best = null;
  for (const axis of ["x", "y"]) {
    edgesOf(now, axis).forEach((value, index) => {
      if (Math.abs(rate(size, axis, index)) < 1e-9) return;
      const hit = catches(axis, [value]);
      if (!hit || (best && Math.abs(hit.gap) >= Math.abs(best.gap))) return;
      // The size that puts it there: straight on from here, then again from where that is
      // (past an end of its place the edge moves another way, or stops).
      let grown = size;
      for (let tries = 0; tries < 6; tries += 1) {
        const off = hit.at - edgesOf(place(grown), axis)[index];
        if (Math.abs(off) <= close / 10) break;
        const speed = rate(grown, axis, index);
        if (Math.abs(speed) < 1e-9) break;
        grown = Math.min(Math.max(grown + off / speed, least), most);
      }
      if (Math.abs(edgesOf(place(grown), axis)[index] - hit.at) > close) return;
      best = { size: grown, gap: hit.gap, axis, at: hit.at };
    });
  }
  return best;
}

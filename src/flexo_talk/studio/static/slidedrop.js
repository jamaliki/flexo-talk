// Where a part of a slide dragged on it would go if let go, and what letting it go there
// does to the slide's regions: worked out from where the parts are drawn, with no page,
// so it can be tried without one.
//
//   regions  the slide's regions, as drawn: [{ key, room, blocks: [{ index, box }] }], each
//            box { left, top, right, bottom } in the page's pixels (room the region's,
//            from the box its drawing gives it; a block's box null if it is not drawn)
//   from     the part dragged, { region, index }
//   point    the pointer, { x, y }
//
// The answer is null away from every region (let go there, the part goes home), or
// { kind: "home" } where it already is, or { kind, region, index }: "swap" with the part
// at index, "between" (index as before the part goes in: the place it takes, counting
// the part itself where it was), or "into" an empty region.

const EDGE = 0.25;
const REACH = 28;

export function blockDrop(regions, from, point) {
  const within = (box) => box && point.x >= box.left && point.x <= box.right && point.y >= box.top && point.y <= box.bottom;
  // A line of words is taken to be a little taller than it is, so it can be hit.
  const reach = (box) => {
    const grow = Math.max(0, (REACH - (box.bottom - box.top)) / 2);
    return { left: box.left, right: box.right, top: box.top - grow, bottom: box.bottom + grow };
  };
  const isFrom = (region, block) => region.key === from.region && block.index === from.index;
  const between = (region, index) => (region.key === from.region && (index === from.index || index === from.index + 1)
    ? { kind: "home" } : { kind: "between", region: region.key, index });
  // Over a part: its middle swaps with it, its top or bottom edge goes before or after it.
  for (const region of regions) {
    for (const block of region.blocks) {
      const box = block.box && reach(block.box);
      if (!box || isFrom(region, block) || !within(box)) continue;
      const share = (point.y - box.top) / Math.max(box.bottom - box.top, 1);
      if (share > EDGE && share < 1 - EDGE) return { kind: "swap", region: region.key, index: block.index };
      return between(region, block.index + (share >= 1 - EDGE ? 1 : 0));
    }
  }
  // Elsewhere in a region: into it, if it is empty; a column holding one part swaps with
  // it wherever it is let go; else between the parts either side of the pointer.
  for (const region of regions) {
    if (!within(region.room)) continue;
    const others = region.blocks.filter((block) => block.box && !isFrom(region, block));
    if (!others.length) return region.key === from.region ? { kind: "home" } : { kind: "into", region: region.key, index: 0 };
    if (others.length === 1 && region.key !== from.region) return { kind: "swap", region: region.key, index: others[0].index };
    const above = region.blocks.filter((block) => block.box && (block.box.top + block.box.bottom) / 2 < point.y).length;
    return between(region, above);
  }
  return null;
}

// Letting it go at ``at``: the regions' lists (a key's list of parts, the slide's own
// lists or stand-ins for them) changed in place -- the two parts swapped, or the one
// taken out and put in where it goes.
export function rearrange(lists, from, at) {
  if (at.kind === "swap") {
    const first = lists[from.region], second = lists[at.region];
    [first[from.index], second[at.index]] = [second[at.index], first[from.index]];
    return;
  }
  const [part] = lists[from.region].splice(from.index, 1);
  const target = lists[at.region];
  const index = from.region === at.region && from.index < at.index ? at.index - 1 : at.index;
  target.splice(Math.min(index, target.length), 0, part);
}

// Where every part goes, as [where it was, where it goes], given how many parts each
// region holds: for each part to glide from where it was drawn when the slide is drawn
// again.
export function blockPlan(counts, from, at) {
  const lists = Object.fromEntries(Object.entries(counts).map(([region, count]) =>
    [region, Array.from({ length: count }, (_, index) => ({ region, index }))]));
  rearrange(lists, from, at);
  return Object.entries(lists).flatMap(([region, list]) => list.map((old, index) => [old, { region, index }]));
}

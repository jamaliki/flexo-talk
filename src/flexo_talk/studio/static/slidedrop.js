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
  // Elsewhere in a region: into it, if it is empty; else between the parts either side of
  // the pointer (a column holding one part too: only its middle swaps with it).
  for (const region of regions) {
    if (!within(region.room)) continue;
    const others = region.blocks.filter((block) => block.box && !isFrom(region, block));
    if (!others.length) return region.key === from.region ? { kind: "home" } : { kind: "into", region: region.key, index: 0 };
    const above = region.blocks.filter((block) => block.box && (block.box.top + block.box.bottom) / 2 < point.y).length;
    return between(region, above);
  }
  // Past a region's room, over or under it (under its last part, at the slide's foot): at its
  // end, or its start.
  const column = beside(regions, point);
  if (!column) return null;
  if (!column.blocks.some((block) => block.box && !isFrom(column, block))) return column.key === from.region ? { kind: "home" } : { kind: "into", region: column.key, index: 0 };
  return between(column, point.y > column.room.bottom ? column.blocks.length : 0);
}

// The region whose room the pointer is over or under (across, within its edges), if any.
function beside(regions, point) {
  return regions.find((region) => region.room && point.x >= region.room.left && point.x <= region.room.right && (point.y > region.room.bottom || point.y < region.room.top)) || null;
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

// Several parts dragged together (`all`, every one of them, in the slide's order): where
// they would go, among the parts not dragged (those dragged out of the way: their boxes as
// the parts left behind now show, closed up), as `at` for gather -- over a part, before or
// after it as the pointer is over its upper or lower half (several are never swapped with
// one); elsewhere in a region, between the parts either side of the pointer, or into it
// when no part is left there. (`at.index` counts the parts dragged where they were.)
export function groupDrop(regions, all, point) {
  const within = (box) => box && point.x >= box.left && point.x <= box.right && point.y >= box.top && point.y <= box.bottom;
  const reach = (box) => {
    const grow = Math.max(0, (REACH - (box.bottom - box.top)) / 2);
    return { left: box.left, right: box.right, top: box.top - grow, bottom: box.bottom + grow };
  };
  const dragged = (region, block) => all.some((part) => part.region === region.key && part.index === block.index);
  const left = regions.map((region) => ({ ...region, blocks: region.blocks.filter((block) => block.box && !dragged(region, block)) }));
  for (const region of left) {
    for (const block of region.blocks) {
      const box = reach(block.box);
      if (within(box)) return { kind: "between", region: region.key, index: block.index + (point.y > (box.top + box.bottom) / 2 ? 1 : 0) };
    }
  }
  for (const region of left) {
    if (!within(region.room)) continue;
    if (!region.blocks.length) return { kind: "into", region: region.key, index: 0 };
    const below = region.blocks.find((block) => (block.box.top + block.box.bottom) / 2 >= point.y);
    return { kind: "between", region: region.key, index: below ? below.index : region.blocks[region.blocks.length - 1].index + 1 };
  }
  // Past a region's room, over or under it: at its end (counting every part it holds), or
  // its start.
  const column = beside(regions, point);
  if (!column) return null;
  if (!column.blocks.some((block) => block.box && !dragged(column, block))) return { kind: "into", region: column.key, index: 0 };
  return { kind: "between", region: column.key, index: point.y > column.room.bottom ? column.blocks.length : 0 };
}

// Letting them go at `at`: each taken out of its list, and all put in together where they
// go, in their order (`at.index` counting them where they were, as for one).
export function gather(lists, all, at) {
  const parts = all.map((part) => lists[part.region][part.index]);
  const before = all.filter((part) => part.region === at.region && part.index < at.index).length;
  for (const part of [...all].sort((a, b) => b.index - a.index)) lists[part.region].splice(part.index, 1);
  const target = lists[at.region];
  target.splice(Math.min(at.index - before, target.length), 0, ...parts);
}

// Where every part goes when several are let go together, as blockPlan.
export function gatherPlan(counts, all, at) {
  const lists = Object.fromEntries(Object.entries(counts).map(([region, count]) =>
    [region, Array.from({ length: count }, (_, index) => ({ region, index }))]));
  gather(lists, all, at);
  return Object.entries(lists).flatMap(([region, list]) => list.map((old, index) => [old, { region, index }]));
}

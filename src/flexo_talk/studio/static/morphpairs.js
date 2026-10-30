// What a morph pairs, and how a slide says it morphs: the part of morph.js that needs no page
// (its tests run it in Node). `paired` pairs as flexo_talk.morphing's `paired` does, for a
// PowerPoint; `matchGlyphs` matches two equations' glyphs.
//
// Adapted from DeckWerk (src/shared/morph.ts and src/shared/glyphMatch.ts), MIT licence,
// Copyright (c) 2026 Vincent Sitzmann.

export const DURATION = 1;
export const SHORTEST = 0.1;
export const LONGEST = 10;
const NEAR = 8;

// -- what a slide says --

// A slide's `transition` as written ("morph", { kind: "morph", duration: 2 }): { kind, duration }
// in seconds, or null.
export function transitionOf(value) {
  if (value === "morph") return { kind: "morph", duration: DURATION };
  if (!value || typeof value !== "object" || Array.isArray(value) || (value.kind ?? "morph") !== "morph") return null;
  const seconds = Number(value.duration ?? DURATION);
  return { kind: "morph", duration: Number.isFinite(seconds) ? Math.min(LONGEST, Math.max(SHORTEST, seconds)) : DURATION };
}

// A transition as a deck writes it: "morph", taking the time it takes unless told, or with its
// duration; none, nothing.
export function transitionWritten(transition) {
  if (!transition) return null;
  const seconds = Math.round(Number(transition.duration ?? DURATION) * 100) / 100;
  return Math.abs(seconds - DURATION) < 1e-9 ? "morph" : { kind: "morph", duration: seconds };
}

// -- pairing (as flexo_talk.morphing.paired) --

export const centre = (unit) => [unit.box[0] + unit.box[2] / 2, unit.box[1] + unit.box[3] / 2];

function near(old, now) {
  const [ox, oy, ow, oh] = old.box, [nx, ny, nw, nh] = now.box;
  if (old.texty || now.texty) {
    // Words: their first line where it was, from the side they are set from, whatever it says.
    const across = Math.min(Math.abs(ox - nx), Math.abs(ox + ow / 2 - nx - nw / 2), Math.abs(ox + ow - nx - nw));
    return Math.abs(oy - ny) <= NEAR && across <= NEAR;
  }
  return Math.abs(ox - nx) <= NEAR && Math.abs(oy - ny) <= NEAR && Math.abs(ow - nw) <= NEAR && Math.abs(oh - nh) <= NEAR;
}

export const TIERS = [
  ["named", (unit) => unit.morph || ""],
  ["framed", (unit) => unit.framed || ""],
  ["same", (unit) => unit.same || ""],
  ["placed", (unit) => (unit.region ? `${unit.kind}|${unit.region}` : "")],
];

// Which of `old` (the slide before's units: { key, kind, box: [x, y, w, h], region, morph,
// framed, same, owner, texty }) goes with which of `now`: [old, now] index pairs in `now`'s
// order. Each step pairs what the steps before left, each of `now` in turn with the nearest of
// `old` it may go with; then a part drawn apart (`owner`: a caption) with the same part of what
// its object went with.
export function paired(old, now, tiers = TIERS) {
  const pairs = new Map(), taken = new Set();
  for (const [tier, keyOf] of tiers) {
    now.forEach((unit, j) => {
      if (pairs.has(j) || unit.owner) return;
      const key = keyOf(unit);
      if (!key) return;
      const [cx, cy] = centre(unit);
      let best = null;
      old.forEach((other, i) => {
        if (taken.has(i) || other.owner || keyOf(other) !== key) return;
        if (tier === "placed" && !near(other, unit)) return;
        const [ox, oy] = centre(other), distance = Math.hypot(ox - cx, oy - cy);
        if (!best || distance < best[0] - 1e-9) best = [distance, i];
      });
      if (best) { pairs.set(j, best[1]); taken.add(best[1]); }
    });
  }
  const went = new Map([...pairs].map(([j, i]) => [now[j].key, old[i].key]));
  const olds = new Map(old.map((unit, i) => [unit.key, i]));
  now.forEach((unit, j) => {
    if (!unit.owner || pairs.has(j) || !went.has(unit.owner)) return;
    const i = olds.get(went.get(unit.owner) + unit.key.slice(unit.owner.length));
    if (i !== undefined && !taken.has(i)) { pairs.set(j, i); taken.add(i); }
  });
  return [...pairs].map(([j, i]) => [i, j]).sort((a, b) => a[1] - b[1]);
}

// Each part drawn apart from its object (`right.0.caption`) said to be that object's.
export function owned(units) {
  const blocks = new Set(units.filter((unit) => unit.region && unit.region !== "shapes").map((unit) => unit.key));
  for (const unit of units) {
    if (unit.region) continue;
    const head = unit.key.split(".").slice(0, 2).join(".");
    if (head !== unit.key && blocks.has(head)) { unit.owner = head; unit.same = ""; }
  }
}

// Which glyphs of one equation are the same glyphs in another (each { key, box }): a longest
// common subsequence of their keys in reading order, the least travel (in the equation's own
// height, from its own corner) deciding between equally long ones; then those of one key the
// order could not keep, nearest first, so a term that commutes (a + b → b + a) travels across.
// [source, target] index pairs, in the target's order. (DeckWerk's glyphMatch.ts.)
export function matchGlyphs(source, target) {
  const n = source.length, m = target.length;
  if (!n || !m) return [];
  const from = normalised(source), to = normalised(target);
  const distance = (i, j) => Math.hypot(from[i].x - to[j].x, from[i].y - to[j].y);
  const width = m + 1;
  const count = new Int32Array((n + 1) * width), cost = new Float64Array((n + 1) * width);
  const better = (c1, d1, c2, d2) => c1 > c2 || (c1 === c2 && d1 < d2 - 1e-9);
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      const at = i * width + j;
      let bestCount = count[at - width], bestCost = cost[at - width];
      if (better(count[at - 1], cost[at - 1], bestCount, bestCost)) { bestCount = count[at - 1]; bestCost = cost[at - 1]; }
      if (source[i - 1].key === target[j - 1].key) {
        const diagonal = at - width - 1;
        const pairedCount = count[diagonal] + 1, pairedCost = cost[diagonal] + distance(i - 1, j - 1);
        if (better(pairedCount, pairedCost, bestCount, bestCost)) { bestCount = pairedCount; bestCost = pairedCost; }
      }
      count[at] = bestCount;
      cost[at] = bestCost;
    }
  }
  const pairs = [];
  let i = n, j = m;
  while (i > 0 && j > 0) {
    const at = i * width + j;
    if (source[i - 1].key === target[j - 1].key) {
      const diagonal = at - width - 1;
      if (count[diagonal] + 1 === count[at] && Math.abs(cost[diagonal] + distance(i - 1, j - 1) - cost[at]) < 1e-6) {
        pairs.push([i - 1, j - 1]);
        i--; j--;
        continue;
      }
    }
    if (count[at - width] === count[at] && Math.abs(cost[at - width] - cost[at]) < 1e-6) i--;
    else j--;
  }
  pairs.reverse();
  const usedSource = new Set(pairs.map(([s]) => s)), usedTarget = new Set(pairs.map(([, t]) => t));
  const leftovers = [];
  for (let s = 0; s < n; s++) {
    if (usedSource.has(s)) continue;
    for (let t = 0; t < m; t++) if (!usedTarget.has(t) && source[s].key === target[t].key) leftovers.push({ s, t, d: distance(s, t) });
  }
  leftovers.sort((a, b) => a.d - b.d || a.t - b.t || a.s - b.s);
  for (const { s, t } of leftovers) {
    if (usedSource.has(s) || usedTarget.has(t)) continue;
    usedSource.add(s);
    usedTarget.add(t);
    pairs.push([s, t]);
  }
  return pairs.sort((a, b) => a[1] - b[1]);
}

function normalised(glyphs) {
  let left = Infinity, top = Infinity, bottom = -Infinity;
  for (const { box: [x, y, , h] } of glyphs) { left = Math.min(left, x); top = Math.min(top, y); bottom = Math.max(bottom, y + h); }
  const unit = bottom - top > 0 ? bottom - top : 1;
  return glyphs.map(({ box: [x, y, w, h] }) => ({ x: (x + w / 2 - left) / unit, y: (y + h / 2 - top) / unit }));
}

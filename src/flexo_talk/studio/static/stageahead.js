// The slides beside the one on the stage, read ahead once the window has been left alone a
// moment (no key, click or scroll for `quiet` ms): each one's drawing read into the page's own
// elements (`read(text)`, as the stage reads one it puts in), and kept until the stage puts
// that slide in -- ↓, ↑ or a click on its thumbnail then shows it without reading its words
// there and then, a large slide's thousands of shapes. One slide at a time, so a key pressed
// meanwhile waits on one at most; each kept only while it is beside the one shown, as drawn.

// `read(text)`: a holder of the drawing `text` read. `want([[shows, text], ...])` names the
// slides to have ready, nearest first (`shows`: the stage's name for a slide as drawn, its
// place and its drawing's hash), letting any other go; `take(shows)` answers that one's holder,
// read, once (null if it is not).
export function stageAhead(read, { quiet = 250 } = {}) {
  const kept = new Map();
  let wanted = [], timer = 0, touched = 0;
  const now = () => globalThis.performance?.now?.() ?? Date.now();
  for (const type of ["keydown", "pointerdown", "wheel"]) globalThis.document?.addEventListener?.(type, () => { touched = now(); }, { capture: true, passive: true });
  const step = () => {
    timer = 0;
    const wait = touched + quiet - now();
    if (wait > 0) { timer = setTimeout(step, wait); return; }
    const next = wanted.find(([shows]) => !kept.has(shows));
    if (!next) return;
    kept.set(next[0], read(next[1]));
    if (wanted.some(([shows]) => !kept.has(shows))) timer = setTimeout(step, 0);
  };
  return {
    want(list) {
      wanted = list;
      const near = new Set(list.map(([shows]) => shows));
      for (const shows of [...kept.keys()]) if (!near.has(shows)) kept.delete(shows);
      if (!timer && wanted.some(([shows]) => !kept.has(shows))) timer = setTimeout(step, quiet);
    },
    take(shows) {
      const holder = kept.get(shows) ?? null;
      kept.delete(shows);
      return holder;
    },
  };
}

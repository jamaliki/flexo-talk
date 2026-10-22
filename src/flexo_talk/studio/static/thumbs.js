// The slide list's thumbnails, each drawn as it comes near enough to be seen and let go once it
// is far out of sight: every slide of a long deck drawn small at once -- some sixteen thousand
// elements for a talk of fifty slides of molecules and figures -- is work the page does as it
// opens, and does again whenever the whole window is styled anew, WebKit (the Mac app's)
// styling every one of them, seen or not. Let go, a drawing is kept (studio.js's picture, by
// its hash), so one scrolled back to is not read again.

// `root`: the list that scrolls; `make(svg, hash)`: a picture of a drawing. A slot for a
// drawing in the list (`.picture-slot`), at a place in it (`at`), holding its picture while
// the thumbnail it is in (`watch(thumbnail)`) is within `margin` of the list's view -- at once
// where one was seen, so a thumbnail made again never shows blank for a moment. (The thumbnail
// is watched, not the slot: a frame out of sight is not laid out -- content-visibility -- and
// what is in it is never seen to come near.)
export function lazyPictures(root, make, { margin = "600px 0px" } = {}) {
  const Observer = globalThis.IntersectionObserver;
  const near = new Set();
  const sight = Observer ? new Observer((entries) => {
    for (const entry of entries) {
      const slot = entry.target.pictureSlot;
      // (One taken out of the list, its place another's now: it says nothing of that place.)
      if (!slot || !entry.target.isConnected) continue;
      if (entry.isIntersecting) near.add(slot.at); else near.delete(slot.at);
      slot.near(entry.isIntersecting);
    }
  }, { root, rootMargin: margin }) : null;
  return function slot(svg, hash, at) {
    const node = document.createElement("div");
    node.className = "picture-slot";
    node.at = at;
    let shown = null, watched = null;
    node.near = (seen) => {
      if (seen && !shown) { shown = make(svg, hash); node.replaceChildren(shown); }
      else if (!seen && shown) { shown = null; node.replaceChildren(); }
    };
    node.watch = (thumbnail) => {
      watched = thumbnail;
      thumbnail.pictureSlot = node;
      sight?.observe(thumbnail);
    };
    // Whole: its picture shown where it is, or none wanted -- not one taken for a drawing
    // elsewhere (a copy of a slide carried, a preview), which it would show again.
    node.whole = () => !shown || shown.parentNode === node;
    node.drop = () => { if (watched) sight?.unobserve(watched); };
    if (!sight || near.has(at)) node.near(true);
    return node;
  };
}

// The slide list kept about the slide chosen: its thumbnail whole in view, ring and all, as
// scrollIntoView puts it (its scroll margin clear of the list's edge).

// `item` brought into `list`'s view, if it is within `slack` of an edge (WebKit's and
// Chromium's "nearest" take a thumbnail its ring short of the edge as shown). Whether it was
// scrolled. (Asked while the window is laid out as it is shown -- before a slide gone to is
// drawn anew -- it costs no layout of its own: asked after, WebKit laid the window out, and
// every layer's place, once more for it.)
export function intoView(list, item, { slack = 8 } = {}) {
  const box = item.getBoundingClientRect(), port = list.getBoundingClientRect();
  if (box.bottom + slack > port.bottom) item.scrollIntoView({ block: "end" });
  else if (box.top - slack < port.top) item.scrollIntoView({ block: "start" });
  else return false;
  return true;
}


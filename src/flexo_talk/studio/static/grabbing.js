// The closed hand shown while something is dragged on a slide (a placed object, the People, a
// logo, an object carried to another place: the <body>'s block-grabbing class says so --
// editor.js, placing.js, portraits.js), wherever the pointer goes. It is shown on what is under
// the pointer alone, moved along as the pointer moves: a rule over every element in the window
// styles each of them again as a drag starts and as it ends -- every slide's thumbnail too,
// which in WebKit (the Mac app's) is some fifty milliseconds, twice a drag.

const CLASS = "grab-here";

// Watched once a page.
export function grabbingHand(doc = globalThis.document) {
  if (!doc?.body || doc.grabbingHand) return;
  doc.grabbingHand = true;
  let under = null, marked = null;
  const mark = (element) => {
    if (element === marked) return;
    marked?.classList?.remove(CLASS);
    marked = element?.classList ? element : null;
    marked?.classList.add(CLASS);
  };
  const grabbing = () => doc.body.classList.contains("block-grabbing");
  const follow = (event) => { under = event.target; if (grabbing()) mark(under); };
  for (const type of ["pointerdown", "pointermove", "pointerover"]) doc.addEventListener(type, follow, { capture: true, passive: true });
  new MutationObserver(() => mark(grabbing() ? under : null)).observe(doc.body, { attributes: true, attributeFilter: ["class"] });
}

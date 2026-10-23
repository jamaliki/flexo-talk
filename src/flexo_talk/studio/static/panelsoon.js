// The panel beside the slide drawn a frame after the slide gone to by ↓ or ↑, or by a click on
// its thumbnail: that frame shows the slide and its thumbnail alone. (The panel made anew, every
// field and button of it painted again, was about half of the frame after each key in the Mac
// app.) Held -- the keys repeating, or pressed again within a moment -- the panel waits until
// they stop a moment, as the slides passed over are not drawn whole on the way (editor.js's
// goTo). Anything else pressed or clicked meanwhile finds it drawn first (`flush`), never a
// panel of a slide no longer shown to type in.

// `draw`: the panel drawn now. `soon(wait)`: drawn once the frame now coming is drawn, and
// `wait` ms more; asked again before then, it is drawn once, for the last. `cancel`: drawn
// meanwhile by other means, it is not drawn again. `flush`: if it is waiting, drawn now.
export function afterFrame(draw) {
  let frame = 0, timer = 0;
  const pending = () => Boolean(frame || timer);
  const cancel = () => {
    if (frame) cancelAnimationFrame(frame);
    if (timer) clearTimeout(timer);
    frame = timer = 0;
  };
  return {
    soon(wait = 0) {
      cancel();
      frame = requestAnimationFrame(() => {
        frame = 0;
        timer = setTimeout(() => { timer = 0; draw(); }, wait);
      });
    },
    cancel,
    pending,
    flush() { if (pending()) { cancel(); draw(); } },
  };
}

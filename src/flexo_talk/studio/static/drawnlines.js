// Where a line of a slide's drawn words is on the page. Flexo draws each line of a text as a
// tspan of its own; WebKit as the Mac app has it gives every tspan of a text the box of the
// whole text, all its lines -- a title wrapped to two lines read as one line twice as tall, and
// the words typed over it set on lines twice as far apart as the drawn ones. A tspan's box
// taller than its first letter's cell (the face's ascent to descent, where the line is set) is
// that: its top and height are then its first letter's cell's, its left and width its own.
// (Elsewhere a tspan's box is its line's, and is taken as it is.)
export function lineBox(span) {
  const box = span.getBoundingClientRect();
  if (!box.height || !span.getNumberOfChars?.()) return box;
  let cell, ctm;
  try {
    cell = span.getExtentOfChar(0);
    ctm = span.getScreenCTM();
  } catch {
    return box;
  }
  if (!cell || !ctm) return box;
  const top = ctm.b * cell.x + ctm.d * cell.y + ctm.f, height = cell.height * Math.hypot(ctm.c, ctm.d);
  if (!(height > 0) || box.height <= height * 1.5) return box;
  return { left: box.left, right: box.right, width: box.width, x: box.left, top, y: top, height, bottom: top + height };
}

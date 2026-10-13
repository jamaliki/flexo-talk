// A slide of columns set in rows (`rows`, in the deck's document): its rows' labels, one a
// row -- "" for a row without one -- block i of every column in row i. What the editor does
// to them, worked out from the slide alone, with no page, so it can be tried without one.

// The layouts whose columns may be set in rows (deck.py's ROWED).
const ROWED = new Set(["two-columns", "columns"]);

export const canRow = (slide) => ROWED.has(slide?.layout);
// Whether a slide is set in rows: it says so, labelled or not (`rows: []` only lines them up).
export const rowed = (slide) => canRow(slide) && Array.isArray(slide.rows);

// How many rows its columns make: as many as its longest column holds objects.
export function rowCount(slide) {
  const columns = slide?.layout === "two-columns" ? [slide.left, slide.right] : slide?.layout === "columns" ? slide.columns : [];
  return Math.max(0, ...(Array.isArray(columns) ? columns : []).map((column) => (Array.isArray(column) ? column.length : 0)));
}

// Its labels as they are written, each as words ("" where nothing is written for a row).
export const labelsOf = (slide) => (rowed(slide) ? slide.rows.map((label) => (label == null ? "" : String(label))) : []);

// Row Labels switched on -- an empty label for each row there is, to be written -- or off:
// its labels gone, each column stacked on its own again.
export function setRows(slide, on) {
  if (!canRow(slide)) return;
  if (on) slide.rows = Array.from({ length: rowCount(slide) }, (_, row) => labelsOf(slide)[row] ?? "");
  else delete slide.rows;
}

// A row's label written: those before it it has none of are empty ones.
export function setLabel(slide, row, text) {
  if (!rowed(slide) || row < 0) return;
  const labels = labelsOf(slide);
  while (labels.length < row) labels.push("");
  labels[row] = text;
  slide.rows = labels;
}

// A slide's labels kept in step with its rows, after a change to it (`was`: the slide before
// it): a row more than it had has an empty label of its own; rows fewer, the labels past the
// last go with them while they are empty (one written is kept, should its row come back).
export function keepRows(was, slide) {
  if (!rowed(slide) || !rowed(was)) return;
  const before = rowCount(was), after = rowCount(slide);
  if (after === before) return;
  const labels = labelsOf(slide);
  while (after > before && labels.length < after) labels.push("");
  while (after < before && labels.length > after && !labels[labels.length - 1].trim()) labels.pop();
  if (labels.length !== slide.rows.length) slide.rows = labels;
}

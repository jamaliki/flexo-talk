// Find and replace in a deck (⌘F, Edit › Find in the Mac app), and what the top bar's search
// finds in it: every slide's words, its notes, its figures' labels -- a figure file's too
// (deckwords.js) -- found by the studio's one engine (finding.js, findbar.js). A match is
// gone to on its slide and marked there, every match on the slide faint and the one gone to
// strong; one in the notes opens them and is marked in them. Replaced, each change is one
// step in the deck's history, a figure file's changes with the deck's.

import { h } from "/static/studio/studio.js";
import { finder, markDrawing, unmarkDrawing } from "/static/studio/findbar.js";
import { figureFields, replaced, wordsOf } from "/static/studio/finding.js";
import { joinSteps } from "/static/studio/mixing.js";
import { deckFields, setField, fieldAt } from "/static/kinds/deck/deckwords.js";

// `deck`, the editor's: { center, notesArea, showNotes(on, { focus }), pageNode(), slide(),
// select(index), slideTitle(index), openWords(edit, start, end), choose(object) }.
export function deckFinder(studio, deck) {
  // The figure files the deck's slides show, read: { file: model }.
  const files = {};
  let reading = null;
  const figureFiles = () => {
    const found = new Map();
    (studio.doc?.slides || []).forEach((slide, n) => {
      if (!slide || typeof slide !== "object") return;
      const regions = [["body", slide.body], ["left", slide.left], ["right", slide.right],
        ...(Array.isArray(slide.columns) ? slide.columns.map((blocks, c) => [`columns.${c}`, blocks]) : [])];
      for (const [region, blocks] of regions) (Array.isArray(blocks) ? blocks : []).forEach((block, index) => {
        const value = block && typeof block === "object" ? block.figure : null;
        if (typeof value === "string" && value && !value.startsWith("#") && !value.includes(".py:") && !found.has(value)) found.set(value, { slide: n, region, index });
      });
    });
    return found;
  };
  // Read again: every figure file shown, as its slide shows it (an edit of nothing: "read").
  const readFiles = () => {
    reading ||= (async () => {
      const wanted = figureFiles();
      let changed = false;
      for (const file of Object.keys(files)) if (!wanted.has(file)) { delete files[file]; changed = true; }
      for (const [file, at] of wanted) {
        try {
          const result = await studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "figure", at, edit: { do: "read" } } });
          if (result?.model && JSON.stringify(result.model) !== JSON.stringify(files[file])) { files[file] = result.model; changed = true; }
        } catch { /* a file that does not read: its words are not found */ }
      }
      reading = null;
      if (changed) found.refresh();
    })();
    return reading;
  };

  // -- the notes' marks: over the notes' words, which stay where they are --
  const notesMarks = h("div.find-notes", { hidden: true, "aria-hidden": "true" });
  const area = deck.notesArea;
  const placeNotes = () => {
    if (notesMarks.hidden || !area.isConnected) return;
    if (notesMarks.parentNode !== area.parentNode) area.after(notesMarks);
    if (getComputedStyle(area.parentNode).position === "static") area.parentNode.style.position = "relative";
    const look = getComputedStyle(area);
    Object.assign(notesMarks.style, {
      left: `${area.offsetLeft}px`, top: `${area.offsetTop}px`, width: `${area.offsetWidth}px`, height: `${area.offsetHeight}px`,
      font: look.font, lineHeight: look.lineHeight, letterSpacing: look.letterSpacing, padding: look.padding,
      borderStyle: "solid", borderColor: "transparent", borderWidth: look.borderWidth, boxSizing: look.boxSizing, tabSize: look.tabSize,
    });
    notesMarks.scrollTop = area.scrollTop;
  };
  area.addEventListener("scroll", () => { notesMarks.scrollTop = area.scrollTop; });
  new ResizeObserver(placeNotes).observe(area);
  const markNotes = (matches, current) => {
    const text = area.value;
    const here = matches.filter((match) => match.field.notes && match.field.slide === deck.slide() && match.field.value === text);
    if (!here.length) { notesMarks.hidden = true; notesMarks.replaceChildren(); return null; }
    notesMarks.hidden = false;
    const parts = [];
    let at = 0, mine = null;
    for (const match of here) {
      parts.push(text.slice(at, match.start));
      const mark = h(`mark${match === current ? ".current" : ""}`, {}, text.slice(match.start, match.end));
      if (match === current) mine = mark;
      parts.push(mark);
      at = match.end;
    }
    parts.push(`${text.slice(at)}​`);
    notesMarks.replaceChildren(...parts);
    placeNotes();
    return mine;
  };
  // A match in the notes in view in them.
  const notesInView = (mark) => {
    if (!mark) return;
    const top = mark.offsetTop, bottom = top + mark.offsetHeight;
    if (top < area.scrollTop || bottom > area.scrollTop + area.clientHeight) area.scrollTop = Math.max(0, top - area.clientHeight / 3);
    notesMarks.scrollTop = area.scrollTop;
  };
  area.addEventListener("input", () => found.shown());

  // -- the slide's --
  const svgShown = () => deck.pageNode()?.querySelector(":scope > svg") || null;
  const darkPaper = (svg) => {
    const fill = svg?.querySelector('[id="canvas.background"]')?.getAttribute("fill") || "";
    const hex = /^#([0-9a-f]{6})$/i.exec(fill.trim())?.[1];
    if (!hex) return false;
    const [r, g, b] = [0, 2, 4].map((k) => parseInt(hex.slice(k, k + 2), 16) / 255);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.45;
  };
  const show = (matches, current, query, options, fields) => {
    const slide = deck.slide();
    const svg = svgShown();
    const here = matches.filter((match) => match.field.slide === slide && !match.field.notes);
    const own = fields.filter((field) => field.slide === slide && !field.notes);
    const mark = svg ? markDrawing(svg, own, here, current, query, options, { dark: darkPaper(svg) }) : null;
    // The one gone to in view, on a slide zoomed past the stage.
    if (mark && current && !current.field.notes) mark.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    const noted = markNotes(matches, current);
    if (current?.field.notes) notesInView(noted);
  };
  const hide = () => { unmarkDrawing(svgShown()); notesMarks.hidden = true; notesMarks.replaceChildren(); };

  // -- putting words in their place --
  // The object a field is in, in the deck: its path up to it.
  const blockPath = (field) => (field.object ? field.path.slice(0, field.object.region.startsWith("columns.") ? 5 : 4) : null);
  async function replace(changes, words, label) {
    const from = studio.past.length;
    const own = changes.filter(({ field }) => field.path), filed = changes.filter(({ field }) => field.file);
    if (own.length) {
      studio.change((d) => {
        for (const { field, ranges } of own) {
          // (Changed since it was found -- by another, meanwhile: left as it is.)
          if (JSON.stringify(fieldAt(d, field.path)) !== JSON.stringify(field.value)) continue;
          setField(d, field.path, replaced(field.value, field.kind, ranges, words));
          // A placeholder changed is its person's own: presented and exported.
          const block = blockPath(field) && fieldAt(d, blockPath(field));
          if (block && typeof block === "object") delete block.placeholder;
        }
      }, { label });
    }
    // A figure file's words, changed where the file is: each file one edit of its figure.
    const byFile = new Map();
    for (const change of filed) {
      if (!byFile.has(change.field.file)) byFile.set(change.field.file, []);
      byFile.get(change.field.file).push(change);
    }
    for (const [file, list] of byFile) {
      const at = list[0].field.at, model = files[file];
      const targets = [], shapes = model?.shapes ? structuredClone(model.shapes) : null;
      let reshaped = false;
      for (const { field, ranges } of list) {
        const value = replaced(field.value, field.kind, ranges, words), target = field.target;
        if (target.type === "shape") {
          let into = shapes;
          for (const key of target.path.slice(0, -1)) into = into?.[key];
          const shape = into?.[target.path[target.path.length - 1]];
          if (shape) { shape.text = value; reshaped = true; }
        } else if (target.key === "cofactors") {
          const edge = (model.edges || []).find((one) => one.id === target.id);
          const both = [...(edge?.cofactors || [])];
          both[target.item] = value;
          targets.push({ type: "edge", id: target.id, values: { cofactors: both } });
        } else targets.push({ type: target.type, id: target.id, values: { [target.key]: value } });
      }
      const edits = [...(targets.length ? [{ do: "update", targets }] : []), ...(reshaped ? [{ do: "shapes", shapes }] : [])];
      for (const edit of edits) {
        const result = await studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "figure", at, edit } });
        if (result?.file && result.was !== undefined) {
          const restore = (text, expect) => studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "figure-file", file, text, expect } });
          studio.record({ label, place: `Slide ${at.slide + 1}`, where: at.slide, was: result.was, now: result.now,
            apply(target) { return (target === "before" ? restore(this.was, this.now) : restore(this.now, this.was)).then(() => { studio.requestDraw(0); readFiles(); }); } });
        }
      }
      if (edits.length) studio.requestDraw(0);
    }
    // One step, however many places it changed.
    if (studio.past.length - from > 1) joinSteps(studio, from, label);
    if (byFile.size) await readFiles();
  }

  // -- going, and leaving --
  const go = (match) => {
    const field = match.field;
    if (field.slide !== deck.slide()) deck.select(field.slide);
    if (field.notes) deck.showNotes(true, { focus: false });
  };
  // Closed, what is chosen is the last match: its words chosen where they are typed (the notes,
  // a title, a list on the slide), else the object it is in.
  const leave = (match) => {
    const field = match.field;
    if (field.slide !== deck.slide()) return;
    if (field.notes) {
      deck.showNotes(true, { focus: false });
      area.focus({ preventScroll: true });
      area.setSelectionRange(match.start, match.end);
      return;
    }
    if (field.edit) {
      let before = 0;
      // A list's items are its lines, typed in as one: the letters of those before it, and
      // their line breaks.
      if (field.edit.kind === "block" && field.item !== undefined) {
        const block = fieldAt(studio.doc, blockPath(field));
        const items = [];
        const walk = (list) => (Array.isArray(list) ? list : [list]).forEach((item) => (Array.isArray(item) ? walk(item) : items.push(String(item ?? ""))));
        walk(block?.bullets);
        before = items.slice(0, field.item).reduce((sum, item) => sum + wordsOf(item).text.length + 1, 0);
      }
      deck.openWords(field.edit, before + match.start, before + match.end);
      return;
    }
    // (A figure's label: its shape chosen in it.)
    if (field.object) deck.choose(field.object, field.target && field.target.type !== "shape" ? field.target.id : null);
  };

  const found = finder(studio, {
    fields: () => deckFields(studio.doc, { files, figure: figureFields }),
    place: (bar) => { deck.center.prepend(bar); readFiles(); },
    unplace: (bar) => bar.remove(),
    from: () => deck.slide(),
    group: (match) => ({ key: `slide-${match.field.slide}`, label: `Slide ${match.field.slide + 1}`, title: deck.slideTitle(match.field.slide) }),
    go, show, hide, replace, leave,
  });
  // The words of figure files: read a moment after the deck is first drawn (for the top bar's
  // search), and again as it is drawn (a figure edited on its slide) while finding.
  let drawnSoon = 0, first = true;
  studio.on("drawn", () => {
    if (!first && !found.isOpen) return;
    clearTimeout(drawnSoon);
    drawnSoon = setTimeout(readFiles, first ? 1500 : 400);
    first = false;
  });
  return {
    // The slide drawn again (or another shown): its marks put on it.
    drawn: () => found.shown(),
    finder: found,
  };
}

// A deck's TODOs: the word TODO, in capitals, as a word of its own ("TODO", "TODO:", "TODO —"),
// anywhere in a slide's words -- its titles, texts, lists, quotes, tables, shapes' words,
// figures' labels (in the deck, or in a figure file it shows), equations -- or in its speaker
// notes (deckwords.js's fields, found by flexo's todos.js, as the find bar finds words). Work
// left, said so where it is, in the studio only:
//   - in the slide list, the slide's thumbnail glows amber, with how many under its number
//     when there are several, and the list's foot says how many in all ("3 TODOs");
//   - on the slide, each is marked amber behind its words, with markers at the stage's edges
//     pointing to those out of sight while it is zoomed in (todomarks.js);
//   - one in the notes: a TODO chip on the notes' bar, which opens them at it, and marked in them;
//   - Next TODO (⌘') and Previous TODO (⇧⌘') go from one to the next, slide after slide -- in
//     the palette, and the Mac app's View menu;
//   - as the show starts and as the deck is exported, a quiet word that slides have them.
// None of it is in what is presented or exported: the marks are the studio's, over its drawing,
// and the words stay as the author wrote them.
//
// Read again a moment after the deck changes (never at each key typed), each field's words
// read once for each value it has had (todos.js): what typing changes is all that is looked at.

import { h, toast } from "/static/studio/studio.js";
import { figureFields } from "/static/studio/finding.js";
import { todoIndex, todosIn, stepFrom, todosSaid } from "/static/studio/todos.js";
import { markTodos, todoMarks, edgeMarkers, todoButton, todoKeys, darkPaper } from "/static/studio/todomarks.js";
import { deckFields } from "/static/kinds/deck/deckwords.js";
import { slidesWithTodos, slidesSaid } from "/static/kinds/deck/todocount.js";

// `deck`, the editor's: { finding (finddeck.js's), rail, railList, stage, center, notes,
// notesArea, showNotes(on, { focus }), pageNode(), slide(), select(index) }.
export function deckTodos(studio, deck) {
  if (!document.querySelector('link[href="/static/kinds/deck/todos.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/todos.css" }));
  }
  const index = todoIndex();
  let found = { fields: [], matches: [] };
  let bySlide = new Map();
  // The TODO gone to last (Next TODO), kept as the deck changes about it; and whether its mark
  // is to be brought into sight once its slide is drawn.
  let current = null, sight = false;
  const keyOf = (match) => JSON.stringify([match.field.path ?? [match.field.file, match.field.target], match.start]);

  // -- reading --
  function read() {
    found = index.find(deckFields(studio.doc, { files: deck.finding.files(), figure: figureFields }));
    bySlide = new Map();
    for (const match of found.matches) {
      const n = match.field.slide;
      if (!bySlide.has(n)) bySlide.set(n, []);
      bySlide.get(n).push(match);
    }
    if (current) current = found.matches.find((match) => keyOf(match) === keyOf(current)) || null;
    foot.set(found.matches.length);
    footing.hidden = !found.matches.length;
    rail();
    noted();
    show();
  }
  let soon = 0;
  const readSoon = () => { clearTimeout(soon); soon = setTimeout(read, 150); };
  studio.on("change", readSoon);
  deck.finding.onFiles(readSoon);

  // -- the slide list --
  // Each thumbnail as many as are on its slide: glowing with any, its count under its number
  // with several. (Called as the list is drawn again: a thumbnail made anew is told again.)
  function rail() {
    for (const thumb of deck.railList.querySelectorAll(":scope > .thumb[data-index]")) {
      const count = bySlide.get(Number(thumb.dataset.index))?.length || 0;
      if (thumb.todos === count) continue;
      thumb.todos = count;
      thumb.classList.toggle("todo", count > 0);
      let badge = thumb.querySelector(":scope > .num > .todo-badge");
      if (count > 1) {
        if (!badge) { badge = h("span.todo-badge"); thumb.querySelector(":scope > .num")?.append(badge); }
        badge.textContent = String(count);
        badge.title = todosSaid(count);
      } else badge?.remove();
    }
  }
  const foot = todoButton(() => step(1));
  const footing = h("div.rail-todos", { hidden: true }, foot.node);
  deck.rail.append(footing);

  // -- the slide --
  const svgShown = () => deck.pageNode()?.querySelector(":scope > svg") || null;
  const edges = edgeMarkers(deck.stage, { host: deck.center, marks: () => todoMarks(svgShown()) });
  let watched = null, shown = "", mark = null;
  const sized = new ResizeObserver(() => edges.place());
  // The slide's TODOs marked on its drawing, again only once they (or the drawing) are not as
  // they were. (On a drawing of the slide before the latest change, those it does not draw yet
  // are marked once it does.) The current one's mark answered.
  function show() {
    const svg = svgShown();
    if (!svg) { edges.clear(); mark = null; shown = ""; return null; }
    const n = deck.slide();
    const here = (bySlide.get(n) || []).filter((match) => !match.field.notes);
    const now = current && here.includes(current) ? current : null;
    const key = JSON.stringify([n, here.map((match) => [match.field.element, match.field.value, match.start]), now && keyOf(now)]);
    if (svg === shownOn && key === shown) return mark;
    shownOn = svg;
    shown = key;
    const own = found.fields.filter((field) => field.slide === n && !field.notes);
    mark = markTodos(svg, own, here, now, { dark: darkPaper(svg) });
    const page = deck.pageNode();
    if (page !== watched) { if (watched) sized.unobserve(watched); watched = page; sized.observe(page); }
    edges.place();
    return mark;
  }
  let shownOn = null;
  // The slide shown drawn (again, or another shown).
  function drawn() {
    const mark = show();
    if (sight && mark) { sight = false; mark.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }
    noted();
  }
  // The figure files the slides show, read again once a slide showing one is drawn anew (the file
  // edited on the slide, or in its own tab): their labels' TODOs as they are now. (Typed in
  // elsewhere, the deck's drawing of those slides is as it was: nothing is read.)
  const showsFile = (slide) => slide && typeof slide === "object"
    && [slide.body, slide.left, slide.right, ...(Array.isArray(slide.columns) ? slide.columns : [])].filter(Array.isArray).flat()
      .some((block) => typeof block?.figure === "string" && block.figure && !block.figure.startsWith("#") && !block.figure.includes(".py:"));
  let filed = "", filesSoon = 0;
  studio.on("drawn", (result) => {
    const pages = result?.pages || [];
    const now = (studio.doc?.slides || []).map((slide, n) => (showsFile(slide) && pages[n]?.svg ? `${n}:${pages[n].hash}` : "")).filter(Boolean).join();
    if (now === filed) return;
    filed = now;
    clearTimeout(filesSoon);
    if (now) filesSoon = setTimeout(() => deck.finding.readFiles(), 300);
  });

  // -- the notes --
  const area = deck.notesArea, head = deck.notes.querySelector(".notes-head");
  const chip = h("span.todo-chip", { hidden: true, onmousedown: (event) => event.preventDefault(),
    onclick: (event) => { event.preventDefault(); event.stopPropagation(); toNotes(); } }, "TODO");
  head.querySelector(".notes-label")?.after(chip);
  // Marked over the notes' own words, which stay where they are (as finddeck.js marks a match).
  const marks = h("div.todo-notes", { hidden: true, "aria-hidden": "true" });
  let marked = null;
  const placeMarks = () => {
    if (marks.hidden || !area.isConnected) return;
    if (marks.parentNode !== area.parentNode) area.after(marks);
    if (getComputedStyle(area.parentNode).position === "static") area.parentNode.style.position = "relative";
    const look = getComputedStyle(area);
    Object.assign(marks.style, {
      left: `${area.offsetLeft}px`, top: `${area.offsetTop}px`, width: `${area.offsetWidth}px`, height: `${area.offsetHeight}px`,
      font: look.font, lineHeight: look.lineHeight, letterSpacing: look.letterSpacing, padding: look.padding,
      borderStyle: "solid", borderColor: "transparent", borderWidth: look.borderWidth, boxSizing: look.boxSizing, tabSize: look.tabSize,
    });
    marks.scrollTop = area.scrollTop;
  };
  area.addEventListener("scroll", () => { marks.scrollTop = area.scrollTop; });
  new ResizeObserver(placeMarks).observe(area);
  // The notes' TODOs as typed (the field's own words: at once, as they are typed), marked; the
  // chip on their bar while there are any.
  let notedOn = -1;
  function noted() {
    if (notedOn !== deck.slide()) { notedOn = deck.slide(); marked = null; }
    const text = area.value, places = todosIn(text);
    chip.hidden = !places.length;
    chip.textContent = places.length > 1 ? todosSaid(places.length) : "TODO";
    chip.title = places.length > 1 ? "Next TODO in the Notes" : "TODO in the Notes";
    const key = `${text}\u0000${marked?.start ?? -1}`;
    if (!places.length) { marks.hidden = true; marks.replaceChildren(); marks.key = ""; return; }
    if (marks.key === key && !marks.hidden) return;
    marks.key = key;
    marks.hidden = false;
    const parts = [];
    let at = 0;
    for (const [start, end] of places) {
      parts.push(text.slice(at, start), h(`mark${marked?.start === start ? ".current" : ""}`, {}, text.slice(start, end)));
      at = end;
    }
    parts.push(`${text.slice(at)}​`);
    marks.replaceChildren(...parts);
    placeMarks();
  }
  area.addEventListener("input", () => { marked = null; noted(); });
  // The notes opened at a TODO in them -- the one at `start`; else, while they have the keys,
  // the next after what is chosen in them; else their first -- its word chosen and in sight.
  function toNotes(start = null) {
    const places = todosIn(area.value);
    if (!places.length) return;
    const typing = area === document.activeElement, after = area.selectionEnd;
    const [from, to] = (start !== null ? places.find(([at]) => at === start)
      : typing ? places.find(([at]) => at >= after) : null) || places[0];
    deck.showNotes(true, { focus: false });
    area.focus({ preventScroll: true });
    area.setSelectionRange(from, to);
    marked = { start: from };
    noted();
    const mark = marks.querySelector("mark.current");
    if (mark && (mark.offsetTop < area.scrollTop || mark.offsetTop + mark.offsetHeight > area.scrollTop + area.clientHeight)) area.scrollTop = Math.max(0, mark.offsetTop - area.clientHeight / 3);
    marks.scrollTop = area.scrollTop;
  }

  // -- going from one to the next --
  // From the one gone to last, while its slide is shown; else from the slide shown -- its first
  // (going on), or its last (going back) -- round from the end of the deck to its start.
  function step(way = 1) {
    const list = found.matches;
    if (!list.length) return;
    const n = deck.slide();
    const next = current && current.field.slide === n ? stepFrom(list, current, way)
      : way > 0 ? list.find((match) => match.field.slide >= n) || list[0]
        : [...list].reverse().find((match) => match.field.slide <= n) || list[list.length - 1];
    go(next);
  }
  function go(match) {
    current = match;
    const field = match.field;
    sight = !field.notes;
    if (field.slide !== deck.slide()) deck.select(field.slide);
    if (field.notes) { toNotes(match.start); show(); return; }
    // (From one in the notes: the keys back with the slide.)
    if (document.activeElement === area) area.blur();
    const gone = show();
    if (gone) { sight = false; gone.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }
  }

  // -- said as the show starts, and as the deck is exported --
  const said = () => slidesSaid(slidesWithTodos(studio.doc, found.matches).length);
  // (Once for the document, however often its editor is made again: what it says is read as it
  // exports.)
  if (!studio.exportFiles.saysTodos) {
    const exportFiles = studio.exportFiles.bind(studio);
    const saying = async (formats, part = null) => {
      const made = await exportFiles(formats, part);
      const words = !part && made?.length ? studio.todos?.said?.() : "";
      if (words) toast(words, { icon: "tag", seconds: 4 });
      return made;
    };
    saying.saysTodos = true;
    studio.exportFiles = saying;
  }

  // -- the palette, the menus, the keys --
  const own = studio.commands;
  studio.commands = () => [...own(), ...(found.matches.length ? [
    { icon: "tag", label: "Next TODO", keys: "⌘'", hint: todosSaid(found.matches.length), run: () => step(1) },
    { icon: "tag", label: "Previous TODO", keys: "⇧⌘'", run: () => step(-1) }] : [])];
  studio.todos = { count: () => found.matches.length, step, said };
  todoKeys();

  read();
  return {
    // The slide list drawn again; the slide shown drawn again (or another shown).
    rail, drawn,
    // What the show starts by saying: "2 slides have TODOs", or nothing.
    said,
  };
}

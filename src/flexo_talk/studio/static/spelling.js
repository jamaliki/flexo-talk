// Check Spelling… (the palette, Edit › Spelling and Grammar in the Mac app): the deck's words
// gone through for those the Mac's dictionary does not know -- every slide's, its notes, its
// figures' labels -- each in turn, in a bar where Find's is (finddeck.js, whose ways of going
// to words, marking and changing them it takes): the word, where it is, the dictionary's
// guesses, one click each to put it in its place; Ignore, for as long as the bar is open, and
// Add to Deck, kept with the deck (`deck.spelling`) so it is never said misspelt in it again.
// What is not prose is left alone (spellwords.js). The dictionary is the Mac app's: in a
// browser the command is not offered -- the browser underlines words as they are typed.

import { h, clear, ui, toast, icon } from "/static/studio/studio.js";
import { wordsOf } from "/static/studio/finding.js";
import { spellingTexts, misspellings } from "/static/kinds/deck/spellwords.js";

// `find`: deckFinder's parts. `closeFind()` closes the find bar, should it be open.
export function deckSpeller(studio, { find, closeFind }) {
  const app = () => (window.pywebview?.api?.misspelled ? window.pywebview.api : null);
  let open = false, fields = [], list = [], current = -1, busy = false;
  const ignored = new Set();
  const keyOf = (field) => JSON.stringify(field.path ?? [field.file, field.target]);

  // -- the bar --
  const word = h("span.spell-word");
  const where = h("span.find-count", { "aria-live": "polite" });
  const guesses = h("span.spell-guesses");
  const step = (glyph, title, way) => {
    const button = ui.button("", () => go(way), { kind: "ghost", small: true, icon: glyph, title });
    button.addEventListener("mousedown", (event) => event.preventDefault());
    return button;
  };
  const previousButton = step("up", "Previous Misspelling", -1), nextButton = step("down", "Next Misspelling", 1);
  const ignoreButton = ui.button("Ignore", () => ignore(), { small: true, title: "Pass over this word while the bar is open" });
  const learnButton = ui.button("Add to Deck", () => learn(), { small: true, title: "Never say this word is misspelt in this deck" });
  const done = ui.button("Done", () => close(), { small: true });
  const bar = h("div.find-bar.spell-bar", { role: "region", "aria-label": "Spelling" },
    h("div.find-row", {}, h("span.spell-title", {}, icon("check"), "Spelling"), word, guesses,
      ignoreButton, learnButton, where, previousButton, nextButton, h("span.find-gap"), done));
  bar.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
  });

  // -- the words --
  async function check() {
    fields = find.fields();
    const texts = spellingTexts(fields, wordsOf);
    const answers = texts.length ? await app().misspelled(texts.map((entry) => entry.text)) : [];
    list = misspellings(texts, Array.isArray(answers) ? answers : [], { known: studio.doc?.deck?.spelling || [], ignored: [...ignored] });
  }
  // The one to show: the first from `after` (a field and a place in it), else from the slide shown.
  function choose(after = null, from = 0) {
    if (!list.length) { current = -1; return; }
    if (after) {
      const own = list.findIndex((match) => keyOf(match.field) === after.key && match.start >= after.start);
      current = own >= 0 ? own : list.findIndex((match) => match.index > after.index);
    } else current = list.findIndex((match) => (match.field.slide ?? 0) >= from);
    if (current < 0) current = 0;
  }
  function showCurrent() {
    const match = list[current];
    if (!match) { finish(); return; }
    word.textContent = `“${match.word}”`;
    where.textContent = `${current + 1} of ${list.length} · Slide ${(match.field.slide ?? 0) + 1}${match.field.name ? `, ${match.field.name}` : ""}`;
    clear(guesses);
    const offered = match.guesses.slice(0, 4);
    if (offered.length) for (const guess of offered) guesses.append(ui.button(guess, () => change(guess), { small: true, kind: "primary", title: `Change to “${guess}”` }));
    else guesses.append(h("span.muted", {}, "No guesses"));
    for (const button of [previousButton, nextButton]) button.disabled = list.length < 2;
    find.go(match);
    mark();
  }
  function mark() {
    const match = list[current];
    if (!open || !match) { find.hide(); return; }
    find.show(list.filter((one) => one.word === match.word), match, match.word, { matchCase: true }, fields);
  }
  function go(way) {
    if (!list.length) return;
    current = (current + way + list.length) % list.length;
    showCurrent();
  }
  // None left: said, and the bar closed.
  function finish() {
    toast("No misspelt words in the deck", { icon: "check", seconds: 2.5 });
    close({ leave: false });
  }

  // -- putting right --
  async function change(guess) {
    const match = list[current];
    if (!match || busy) return;
    busy = true;
    try {
      await find.replace([{ field: match.field, ranges: [[match.start, match.end]] }], guess, "Correct Spelling");
      await check();
      choose({ key: keyOf(match.field), start: match.start + guess.length, index: match.index });
      showCurrent();
    } catch (error) {
      toast(`Couldn’t change it: ${error?.message || error}`, { kind: "error", icon: "error", seconds: 5 });
    } finally { busy = false; }
  }
  function passOver(text) {
    const at = list[current];
    list = list.filter((match) => match.word.toLowerCase() !== text.toLowerCase());
    choose(at ? { key: keyOf(at.field), start: at.start, index: at.index } : null);
    showCurrent();
  }
  function ignore() {
    const match = list[current];
    if (!match) return;
    ignored.add(match.word.toLowerCase());
    passOver(match.word);
  }
  function learn() {
    const match = list[current];
    if (!match) return;
    studio.change((d) => {
      d.deck = d.deck && typeof d.deck === "object" ? d.deck : {};
      const known = new Set(Array.isArray(d.deck.spelling) ? d.deck.spelling : []);
      known.add(match.word);
      d.deck.spelling = [...known].sort((a, b) => a.localeCompare(b));
    }, { label: `Add “${match.word}” to the Deck’s Words` });
    passOver(match.word);
  }

  // -- opening and closing --
  async function start(from = 0) {
    if (!app()) { toast("Check Spelling… is the Mac app’s: in a browser, misspelt words are underlined as they are typed.", { icon: "info", seconds: 6 }); return; }
    if (busy) return;
    busy = true;
    try {
      await check();
    } catch (error) {
      toast(`Couldn’t check the spelling: ${error?.message || error}`, { kind: "error", icon: "error", seconds: 6 });
      return;
    } finally { busy = false; }
    if (!list.length) { toast("No misspelt words in the deck", { icon: "check", seconds: 2.5 }); return; }
    closeFind?.();
    if (!open) { open = true; find.place(bar); }
    choose(null, from);
    showCurrent();
  }
  function close({ leave = true } = {}) {
    if (!open) return;
    open = false;
    const match = list[current];
    find.hide();
    bar.remove();
    if (leave && match) find.leave(match);
  }
  return {
    available: () => Boolean(app()),
    start, close,
    get isOpen() { return open; },
    // The slide drawn again: its marks put back.
    drawn: () => { if (open) mark(); },
  };
}

// The people beside a slide's title, in the editor (peoplelist.js says what each change does
// to the slide): the slide's People in its inspector -- each person's portrait, their Name, and
// Remove; dragged up or down (⌥↑ ⌥↓ with its row's keys) to stand elsewhere in the row -- Add
// Person…, which chooses or uploads a picture as Add Logo… does; Size, how wide every portrait
// on the slide is (as a corner of one chosen on the slide sizes them: portraits.js); the
// palette's "Add Person to Title…", "Reset People Size" and "Put People Back in Line" (once
// they are placed freely, dragged on the slide: portraits.js); and pictures dropped on the
// slide's title, each a person added. Each change is one step, named for what it does.

import { h, ui, icon, toast } from "/static/studio/studio.js";
import { canHavePeople, peopleOf, addPeople, removePerson, movePerson, renamePerson, peopleSize, setPeopleSize, peopleAt, setPeopleAt } from "/static/kinds/deck/peoplelist.js";

// `deck`, the editor's: { editSlide(mutate, options), slideAt(), slide() (its index),
// chooseFile({ title, types, action }), awayFrom(what), renderInspector(), undoNote(text,
// options), pageNode(), types (the files a portrait may be) }.
export function slidePeople(studio, deck) {
  if (!document.querySelector('link[href="/static/kinds/deck/people.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/people.css" }));
  }
  const types = deck.types || [".png", ".jpg", ".jpeg", ".svg", ".pdf", ".ai"];
  const portraitFile = (path) => types.some((suffix) => String(path).toLowerCase().endsWith(suffix));
  const fileName = (path) => String(path ?? "").split("/").pop();
  const notPortrait = (path) => toast(`A portrait is a PNG, JPEG, SVG or PDF picture: ${fileName(path)} is none of these.`, { icon: "info", seconds: 5 });

  // Those whose file is not there, as the last drawing said (`slides[3].people[1]`): their
  // rows drawn again when that changes.
  let gone = new Set();
  studio.on("drawn", (result) => {
    const now = new Set((result?.messages || []).map((message) => /^slides\[(\d+)\]\.people\[(\d+)\]$/.exec(message.where || ""))
      .filter(Boolean).map((found) => `${found[1]}:${found[2]}`));
    const same = now.size === gone.size && [...now].every((key) => gone.has(key));
    gone = now;
    if (!same && document.querySelector(".people-rows")) setTimeout(deck.renderInspector, 0);
  });

  function edit(mutate, label, { merge } = {}) {
    deck.editSlide(mutate, merge ? { label, quiet: true, merge, hold: true } : { label });
    if (!merge) deck.renderInspector();
  }

  // Pictures added as people (`paths`; else one chosen), at `at` in the row (else at its end).
  async function add(paths = null, at = null) {
    const slide = deck.slideAt();
    if (!canHavePeople(slide) || deck.awayFrom("add people")) return;
    if (!paths) {
      const path = await deck.chooseFile({ title: "Add Person", types: ["image"], action: "Add" });
      if (!path) return;
      paths = [path];
    }
    const wrong = paths.filter((path) => !portraitFile(path));
    if (wrong.length) notPortrait(wrong[0]);
    paths = paths.filter(portraitFile);
    if (!paths.length) return;
    edit((s) => { addPeople(s, paths, at); }, paths.length === 1 ? "Add Person" : `Add ${paths.length} People`);
    // The last added, its name to be typed.
    const last = (at ?? peopleOf(deck.slideAt()).length - paths.length) + paths.length - 1;
    setTimeout(() => document.querySelector(`input[data-key="people.${last}.name"]`)?.focus({ preventScroll: true }), 0);
  }
  function remove(index) {
    if (deck.awayFrom("remove people")) return;
    edit((s) => removePerson(s, index), "Remove Person");
    deck.undoNote("Person removed");
  }
  function move(index, to) {
    if (to < 0 || to >= peopleOf(deck.slideAt()).length || to === index || deck.awayFrom("move people")) return;
    const typing = document.activeElement?.matches?.("input[data-key^='people.']");
    edit((s) => movePerson(s, index, to), "Move Person");
    // The keys go with the person moved, in their name's field.
    if (typing) setTimeout(() => document.querySelector(`input[data-key="people.${to}.name"]`)?.focus({ preventScroll: true }), 0);
  }

  // How wide its portraits are when the slide says nothing, as the slide was last drawn (the
  // drawing says, on each portrait); null, not drawn yet.
  const sizes = deck.sizes || [24, 160];
  function defaultSize() {
    const drawn = deck.pageNode()?.querySelector(`[id^="slide${deck.slide() + 1}.person"][data-flexo-default]`);
    const value = Number(drawn?.getAttribute("data-flexo-default"));
    return value > 0 ? value : null;
  }
  // Every portrait on the slide `size` points across (null: as the title sets them), one step.
  // Whether that changed it.
  function resize(size, label = "Resize People") {
    const slide = deck.slideAt();
    if (!canHavePeople(slide) || deck.awayFrom("size people")) return false;
    if (!setPeopleSize(structuredClone(slide), size, sizes)) return false;
    edit((s) => { setPeopleSize(s, size, sizes); }, size === null || size === undefined ? "Reset People Size" : label);
    return true;
  }
  const resetSize = () => peopleSize(deck.slideAt()) !== null && resize(null);
  // Placed freely, the row's top left at `at` (the shapes' units: portraits.js drags and
  // nudges them), one step -- the presses of a run of nudges one (`merge`); null, Put People
  // Back in Line. Whether that changed it.
  function placeAt(at, { merge = null } = {}) {
    const slide = deck.slideAt();
    if (!canHavePeople(slide) || !peopleOf(slide).length || deck.awayFrom("move people")) return false;
    if (!setPeopleAt(structuredClone(slide), at)) return false;
    const label = at ? "Move People" : "Put People Back in Line";
    deck.editSlide((s) => { setPeopleAt(s, at); }, merge ? { label, merge, hold: true } : { label });
    deck.renderInspector();
    return true;
  }
  const putBack = () => peopleAt(deck.slideAt()) !== null && placeAt(null);

  // The one chosen on the slide, marked in its row (portraits.js says which: `choosing`).
  let chosen = () => null;
  let dragged = null;
  // The slide's People: a row for each, then Add Person…, then how wide they are.
  function controls(slide) {
    const people = peopleOf(slide), at = deck.slide();
    const rows = people.map((person, index) => {
      const missing = gone.has(`${at}:${index}`);
      const row = h(`div.list-row.person-row${chosen() === index ? ".chosen" : ""}`, {
        dataset: { index, key: `person:${index}:${person.image}` }, draggable: true,
        "aria-label": `Person ${index + 1} of ${people.length}: ${person.name || fileName(person.image)}`,
        title: "Drag to reorder",
        onkeydown: (event) => {
          if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
            event.preventDefault();
            event.stopPropagation();
            move(index, index + (event.key === "ArrowUp" ? -1 : 1));
          }
        },
        ondragstart: (event) => {
          if (event.target.closest?.("input")) { event.preventDefault(); return; }
          dragged = index; row.classList.add("dragging"); event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", person.name || fileName(person.image));
        },
        ondragend: () => { dragged = null; row.classList.remove("dragging"); },
        ondragover: (event) => {
          if (dragged === null) return;
          event.preventDefault();
          const box = row.getBoundingClientRect();
          row.classList.remove("drop-before", "drop-after");
          row.classList.add(event.clientY > box.top + box.height / 2 ? "drop-after" : "drop-before");
        },
        ondragleave: () => row.classList.remove("drop-before", "drop-after"),
        ondrop: (event) => {
          if (dragged === null) return;
          event.preventDefault();
          const after = row.classList.contains("drop-after");
          row.classList.remove("drop-before", "drop-after");
          const from = dragged, place = index + (after ? 1 : 0);
          move(from, place > from ? place - 1 : place);
        },
      },
      missing ? h("span.pic.person-pic.gone", { title: "Not in the deck’s folder" }, icon("warning"))
        : h("img.pic.person-pic", { src: studio.raw(person.image), alt: "", draggable: false,
          onerror: (event) => event.currentTarget.replaceWith(h("span.pic.person-pic.gone", { title: "Not in the deck’s folder" }, icon("warning"))) }),
      h("div.person-name", {}, ui.input({ value: person.name, placeholder: "Name", key: `people.${index}.name`,
        onInput: (value) => edit((s) => renamePerson(s, index, value), "Rename Person", { merge: `${at}-person-${index}-name` }) })),
      ui.button("", () => remove(index), { kind: "ghost", icon: "trash", small: true, title: "Remove" }));
      return row;
    });
    const adder = ui.button("Add Person…", () => add(), { kind: "ghost", icon: "plus", small: true });
    adder.dataset.key = "people.add";
    const size = peopleSize(slide), fallback = defaultSize();
    const sized = people.length ? ui.field("Size", h("div.row", {},
      ui.number({ value: size, placeholder: fallback ? String(Math.round(fallback)) : "", min: sizes[0], max: sizes[1], step: 2, unit: "pt", key: "people_size",
        onChange: (value) => resize(value) }),
      size !== null ? ui.button("Reset Size", () => resetSize(), { small: true, kind: "ghost" }) : null)) : null;
    return [people.length ? h("div.list-rows.people-rows", {}, rows) : null, h("div", {}, adder), sized];
  }

  // The palette's: named as the Mac app's Insert menu would name it.
  const commands = () => (canHavePeople(deck.slideAt()) ? [{ icon: "image", label: "Add Person to Title…", run: () => add() },
    ...(peopleSize(deck.slideAt()) !== null ? [{ icon: "undo", label: "Reset People Size", run: () => resetSize() }] : []),
    ...(peopleAt(deck.slideAt()) !== null ? [{ icon: "layout", label: "Put People Back in Line", run: () => putBack() }] : [])] : []);

  // Whether `event` (a drag of files) is over the slide's title -- its words, its band, the
  // people beside it -- on a slide that may have people: there, pictures are people.
  function overTitle(event) {
    const slide = deck.slideAt(), page = deck.pageNode();
    if (!page || !canHavePeople(slide) || event?.clientY === undefined) return false;
    const id = `slide${deck.slide() + 1}`;
    const boxes = [...page.querySelectorAll(`[id="${id}.title"], [id="${id}.subtitle"], [id="${id}.band"], [id^="${id}.person"]`)]
      .map((node) => node.getBoundingClientRect()).filter((box) => box.width || box.height);
    if (!boxes.length) return false;
    const bottom = Math.max(...boxes.map((box) => box.bottom)), top = Math.min(...boxes.map((box) => box.top));
    return event.clientY >= Math.min(top, page.getBoundingClientRect().top) && event.clientY <= bottom + 6;
  }
  // Pictures dropped on the title: each a person, in the row where they are let go.
  async function dropped(files, event) {
    if (!overTitle(event)) return false;
    const pictures = files.filter((file) => /\.(png|jpe?g|svg|gif|webp|tiff?|bmp|hei[cf]|avif|pdf|ai)$/i.test(file.name));
    if (!pictures.length || pictures.length < files.length) return false;
    const fit = pictures.filter((file) => portraitFile(file.name));
    if (fit.length < pictures.length) notPortrait(pictures.find((file) => !portraitFile(file.name)).name);
    if (!fit.length) return true;
    const page = deck.pageNode(), id = `slide${deck.slide() + 1}`;
    const drawn = peopleOf(deck.slideAt()).map((_, index) => page?.querySelector(`[id="${id}.person${index}"]`)?.getBoundingClientRect()).filter(Boolean);
    // Let go among the people, where it is let go; on the title's words, after them all.
    const among = drawn.length && event.clientX >= Math.min(...drawn.map((box) => box.left)) - 12;
    const at = among ? drawn.filter((box) => (box.left + box.right) / 2 < event.clientX).length : null;
    const paths = [];
    for (const file of fit) paths.push(await studio.upload(file));
    await add(paths, at);
    return true;
  }

  return { controls, commands, add, overTitle, dropped, room: canHavePeople, remove, move, resize, resetSize, defaultSize, sizes, placeAt, putBack,
    placed: () => peopleAt(deck.slideAt()),
    choosing: (which) => { chosen = which; } };
}

// A deck's comments in the editor (flexo_talk/studio/comments.py says how they are written):
// review notes left on a slide, an object on it, or a part of its figure, each a thread of
// comments and replies, open or resolved. In the studio only -- never presented or exported
// as part of a slide:
//   - on the slide, a small marker at the corner of what each open thread is about (the slide's
//     own at its top right); clicked, its threads: each comment, who and when, a reply field,
//     Resolve and Delete;
//   - in the slide list, how many open threads a slide has, at its thumbnail's corner;
//   - Add Comment (⇧⌘K, Keynote's key; the palette; Insert › Comment; an object's, a figure
//     part's and the slide's menus) on what is chosen: the part of a figure, else the object,
//     else the slide;
//   - the side panel's Comments (studio's commentlist.js), every thread in the deck, gone to
//     from there (`studio.comments`).
// Each comment, reply, resolve and delete is one step of its person's, undone with ⌘Z. A
// change to comments draws nothing again: the slide is drawn without them.

import { h, clear, icon, ui, popover, closeMenu, toast, avatar } from "/static/studio/studio.js";

const REGIONS = ["body", "left", "right"];

// -- the threads --

// Each thread written on a slide -- its own, its objects' -- as { region, index, part, at,
// thread }: region and index null for the slide's own; `at`, its place in its holder's list.
// Read once for each slide as it is (a slide is replaced as it changes, never changed).
const read = new WeakMap();
function ownThreads(slide) {
  if (!slide || typeof slide !== "object") return [];
  let found = read.get(slide);
  if (found) return found;
  found = [];
  const add = (held, region, index) => {
    if (!Array.isArray(held)) return;
    held.forEach((thread, at) => {
      if (thread && typeof thread === "object" && ["string", "number"].includes(typeof thread.text)) {
        found.push({ region, index, part: region !== null && thread.part != null && thread.part !== "" ? String(thread.part) : null, at, thread });
      }
    });
  };
  add(slide.comments, null, null);
  for (const region of REGIONS) (Array.isArray(slide[region]) ? slide[region] : []).forEach((block, index) => add(block?.comments, region, index));
  (Array.isArray(slide.columns) ? slide.columns : []).forEach((column, c) => (Array.isArray(column) ? column : [])
    .forEach((block, index) => add(block?.comments, `columns.${c}`, index)));
  read.set(slide, found);
  return found;
}

// Every thread in the deck `doc`, each with its slide's index, its id and whether it is open.
export function deckThreads(doc) {
  const slides = Array.isArray(doc?.slides) ? doc.slides : [];
  return slides.flatMap((slide, n) => ownThreads(slide).map((one) => ({ ...one, slide: n, id: String(one.thread.id ?? ""), open: one.thread.resolved !== true })));
}

// How many open threads each slide has.
export function openCounts(doc) {
  const slides = Array.isArray(doc?.slides) ? doc.slides : [];
  return slides.map((slide) => ownThreads(slide).filter((one) => one.thread.resolved !== true).length);
}

// The mapping on `slide` that holds the threads of `region`, `index` (null, null: the slide).
function holderIn(slide, region, index) {
  if (region === null || region === undefined) return slide;
  const blocks = region.startsWith("columns.") ? slide?.columns?.[Number(region.split(".")[1])] : slide?.[region];
  const block = Array.isArray(blocks) ? blocks[index] : null;
  return block && typeof block === "object" ? block : null;
}

// A new thread's id, none of the deck's.
function newId(doc) {
  const taken = new Set(deckThreads(doc).map((one) => one.id));
  for (;;) {
    const id = `c${Math.floor(Math.random() * 0x1000000).toString(16).padStart(6, "0")}`;
    if (!taken.has(id)) return id;
  }
}

// Now, as a comment's time is written: UTC, to the second.
const now = () => new Date().toISOString().replace(/\.\d+Z$/, "Z");

// When, as a Mac's lists say it: Just now, 5 min ago, 14:03, Yesterday 14:03, 29 Oct (2025).
export function when(time) {
  const at = new Date(String(time ?? ""));
  if (Number.isNaN(at.getTime())) return "";
  const seconds = (Date.now() - at.getTime()) / 1000;
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  const clock = at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const day = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const days = Math.round((day(new Date()) - day(at)) / 86400000);
  if (days === 0) return clock;
  if (days === 1) return `Yesterday ${clock}`;
  return at.toLocaleDateString("en-GB", { day: "numeric", month: "short", ...(at.getFullYear() === new Date().getFullYear() ? {} : { year: "numeric" }) });
}

// Who wrote a comment, as the studio's avatars take someone: known by their name. One of the
// agents the studio has seen is shown as an agent.
function writer(workspace, name) {
  const author = String(name || "Someone");
  const agent = [...(workspace?.activity || []), ...(workspace?.presence || [])]
    .some((entry) => entry?.who?.kind === "agent" && entry.who.name === author);
  return { id: `author:${author}`, name: author, kind: agent ? "agent" : "person" };
}

// -- in the editor --

// `deck`, the editor's: { rail, railList, pageNode(), slide(), select(index), choose(at, part),
// blockId(at), frameOf(part), boxOf(id), where() (what is chosen, as studio.focus says it) }.
export function deckComments(studio, deck) {
  if (!document.querySelector('link[href="/static/kinds/deck/comments.css"]')) {
    document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/comments.css" }));
  }
  const workspace = studio.workspace;
  const doc = () => studio.doc || {};

  // -- changes: each one step, its person's --
  // The thread `id` changed by `change(thread)` (a copy, its own to change), in one step named `label`.
  function changeThread(id, label, change) {
    const found = deckThreads(doc()).find((one) => one.id === id);
    if (!found) return false;
    studio.change((d) => {
      const holder = holderIn(d.slides?.[found.slide], found.region, found.index);
      if (!holder || !Array.isArray(holder.comments)) return;
      const at = holder.comments.findIndex((thread) => String(thread?.id ?? "") === id);
      if (at < 0) return;
      const thread = { ...holder.comments[at] };
      if (change(thread) === false) holder.comments.splice(at, 1);
      else holder.comments[at] = thread;
      if (!holder.comments.length) delete holder.comments;
    }, { label, within: ["slides", found.slide] });
    return true;
  }
  const myName = () => String(workspace?.me?.name || "").trim();
  function add(target, text) {
    const id = newId(doc());
    const thread = { id, author: myName() || "Someone", time: now(), text, ...(target.part ? { part: String(target.part) } : {}) };
    studio.change((d) => {
      const holder = holderIn(d.slides?.[target.slide], target.region ?? null, target.index ?? null);
      if (!holder) return;
      holder.comments = [...(Array.isArray(holder.comments) ? holder.comments : []), thread];
    }, { label: "Add Comment", within: ["slides", target.slide] });
    return id;
  }
  const reply = (id, text) => changeThread(id, "Reply to Comment", (thread) => {
    thread.replies = [...(Array.isArray(thread.replies) ? thread.replies : []), { author: myName() || "Someone", time: now(), text }];
  });
  const resolve = (id, on = true) => changeThread(id, on ? "Resolve Comment" : "Reopen Comment", (thread) => {
    if (on) thread.resolved = true; else delete thread.resolved;
  });
  const remove = (id) => changeThread(id, "Delete Comment", () => false);

  // -- the markers on the slide --
  const layer = h("div.comment-markers");
  let shownKey = "", shownOn = null;
  // Where an anchor is on the slide shown, in the page's pixels: its top right corner.
  function cornerOf(one) {
    const page = deck.pageNode();
    if (!page) return null;
    if (one.region === null) return { left: page.clientWidth - 30, top: 10 };
    const id = deck.blockId({ region: one.region, index: one.index });
    const part = one.part ? deck.boxOf(`${id}.${one.part}`) : null;
    const box = part || deck.frameOf({ kind: "block", region: one.region, index: one.index, id });
    if (!box) return null;
    // (Just right of its top right corner: on none of its words, nor on the handle there that
    // sizes it -- nor, a figure's part's, on the words over the figure.)
    return { left: Math.min(page.clientWidth - 24, box.left + box.width + (part ? 2 : 6)), top: Math.max(2, box.top - (part ? 4 : 0)) };
  }
  const anchorKey = (one) => (one.region === null ? "slide" : `${one.region}:${one.index}:${one.part ?? ""}`);
  // Placed again only when what they mark, or the drawing under them, is not as it was: a
  // key typed on a slide with comments measures nothing for them.
  function place(force = false) {
    const page = deck.pageNode();
    if (!page) return;
    const n = deck.slide();
    const here = ownThreads(doc().slides?.[n]).filter((one) => one.thread.resolved !== true);
    if (!here.length) { if (layer.childElementCount) clear(layer); shownKey = ""; return; }
    const drawn = page.querySelector(":scope > svg");
    const key = `${n}|${here.map((one) => `${anchorKey(one)}:${one.thread.id}:${one.thread.author}`).join()}|${page.clientWidth}x${page.clientHeight}|${opened?.key ?? ""}`;
    if (!force && key === shownKey && drawn === shownOn && layer.parentNode === page) return;
    shownOn = drawn;
    if (layer.parentNode !== page) page.append(layer);
    if (!watched.has(page)) { watched.add(page); sized.observe(page); }
    const groups = new Map();
    for (const one of here) {
      const key = anchorKey(one);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(one);
    }
    const markers = [];
    const taken = [];
    for (const [key, ones] of groups) {
      const corner = cornerOf(ones[0]);
      if (!corner) continue;
      // (Two at one corner -- an object and a part of it -- side by side, never one over the other.)
      while (taken.some((other) => Math.abs(other.left - corner.left) < 20 && Math.abs(other.top - corner.top) < 20)) corner.left -= 22;
      taken.push(corner);
      const first = writer(workspace, ones[0].thread.author);
      const marker = h(`button.comment-marker${opened?.key === key && opened.slide === n ? ".open" : ""}`, {
        type: "button", dataset: { anchor: key },
        title: ones.length > 1 ? `${ones.length} comments` : `${first.name}: ${String(ones[0].thread.text).slice(0, 80)}`,
        onpointerdown: (event) => event.stopPropagation(),
        onclick: (event) => {
          event.stopPropagation();
          event.preventDefault();
          // (Its own popover open, the press that closed it closes it: it is not opened again.)
          if (closedLast?.key === key && performance.now() - closedLast.at < 400) return;
          show(n, key, event.currentTarget);
        },
      }, ones.length > 1 ? h("span.comment-count", {}, String(ones.length)) : icon("comment"));
      Object.assign(marker.style, { left: `${corner.left}px`, top: `${corner.top}px` });
      markers.push(marker);
    }
    clear(layer, ...markers);
    shownKey = key;
  }
  const watched = new WeakSet();
  const sized = new ResizeObserver(() => requestAnimationFrame(() => place(true)));

  // -- the slide list --
  // (Looked through only when the counts, or the list's thumbnails, are not as they were.)
  let railSaid = "";
  function rail() {
    const counts = openCounts(doc());
    const said = `${counts.join()}|${deck.railList.childElementCount}|${deck.railList.firstElementChild?.comments === undefined}`;
    if (said === railSaid && !counts.some(Boolean)) return;
    railSaid = said;
    for (const thumb of deck.railList.querySelectorAll(":scope > .thumb[data-index]")) {
      const count = counts[Number(thumb.dataset.index)] || 0;
      if (thumb.comments === count) continue;
      thumb.comments = count;
      let badge = thumb.querySelector(":scope > .comment-badge");
      if (count) {
        if (!badge) { badge = h("span.comment-badge", { "aria-hidden": "true" }); thumb.append(badge); }
        clear(badge, icon("comment"), count > 1 ? h("span", {}, String(count)) : null);
      } else badge?.remove();
    }
  }

  // -- a thread, read and answered --
  let opened = null;   // { slide, key, node, anchor }
  let closedLast = null;
  function show(n, key, anchor) {
    const ones = ownThreads(doc().slides?.[n]).filter((one) => anchorKey(one) === key && one.thread.resolved !== true);
    if (!ones.length) { closeMenu(); return; }
    const node = popover(anchor, threadsView(ones.map((one) => String(one.thread.id ?? ""))), { className: "comment-pop" });
    opened = { slide: n, key, node, anchor };
    anchor.classList?.add("open");
    watchClosed(node);
  }
  function watchClosed(node) {
    const watch = new MutationObserver(() => {
      if (node.isConnected) return;
      watch.disconnect();
      if (opened?.node === node) { opened.anchor?.classList?.remove("open"); closedLast = { key: opened.key, at: performance.now() }; opened = null; }
      pending?.remove();
      pending = null;
    });
    watch.observe(document.body, { childList: true });
  }
  // The threads `ids` in a popover: each comment and its replies, then a field to reply.
  function threadsView(ids) {
    const all = deckThreads(doc());
    return h("div.comment-threads", {}, ids.map((id) => all.find((one) => one.id === id)).filter(Boolean).map((one) => threadView(one)));
  }
  function threadView(one) {
    const { thread, id } = one;
    const comments = [thread, ...(Array.isArray(thread.replies) ? thread.replies : []).filter((item) => item && typeof item === "object")];
    const field = composer({ placeholder: "Reply", label: "Reply", send: (text) => { reply(id, text); refresh(); } });
    const head = (item, first) => h("div.comment-head", {},
      avatar(writer(workspace, item.author), { size: 20 }),
      h("span.comment-author", {}, String(item.author || "Someone")),
      h("span.comment-time", { title: String(item.time ?? "") }, when(item.time)),
      first ? h("span.comment-actions", {},
        ui.button("", () => { resolve(id, thread.resolved !== true); refresh(); }, { kind: "ghost", small: true, icon: "check", title: thread.resolved === true ? "Reopen" : "Resolve" }),
        ui.button("", () => { remove(id); refresh(); }, { kind: "ghost", small: true, icon: "trash", title: "Delete" })) : null);
    const node = h(`div.comment-thread${thread.resolved === true ? ".resolved" : ""}`, { dataset: { thread: id } },
      comments.map((item, index) => h(`div.comment${index ? ".reply" : ""}`, {}, head(item, !index), h("div.comment-text", {}, String(item.text ?? "")))),
      thread.resolved === true ? null : field);
    node.thread = thread;
    return node;
  }
  // A field to write a comment in: Return sends, ⇧Return starts a line, Esc goes back. With no
  // name yet (a browser's studio), the person's name is asked once, beside it.
  function composer({ placeholder, label, send, cancel = null }) {
    const area = h("textarea.comment-field", { rows: 1, placeholder, "aria-label": label });
    const name = myName() ? null : h("input.comment-name", { type: "text", placeholder: "Your Name", "aria-label": "Your Name" });
    const grow = () => { area.style.height = "auto"; area.style.height = `${Math.min(area.scrollHeight, 120)}px`; };
    const go = () => {
      const text = area.value.trim();
      if (!text) return;
      if (name) {
        if (!name.value.trim()) { name.focus(); return; }
        workspace.setName?.(name.value.trim());
      }
      area.value = "";
      grow();
      send(text);
    };
    area.addEventListener("input", grow);
    area.addEventListener("keydown", (event) => {
      // (Its own lines for the arrows, not the popover's buttons.)
      if (event.key === "ArrowUp" || event.key === "ArrowDown") event.stopPropagation();
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); go(); }
      if (event.key === "Escape" && cancel) { event.preventDefault(); event.stopPropagation(); cancel(); }
    });
    const sendButton = ui.button("", go, { kind: "ghost", small: true, icon: "send", title: label === "Comment" ? "Comment" : "Reply" });
    return h("div.comment-compose", {}, name, h("div.comment-row", {}, area, sendButton));
  }
  // The popover open, drawn again as the threads in it are now (a reply, another's too); closed
  // once none of them is open.
  function refresh() {
    if (!opened?.node?.isConnected) return;
    const ones = ownThreads(doc().slides?.[opened.slide]).filter((one) => anchorKey(one) === opened.key && one.thread.resolved !== true);
    if (!ones.length) { closeMenu(); return; }
    const list = opened.node.querySelector(".comment-threads");
    const ids = ones.map((one) => String(one.thread.id ?? ""));
    const shown = [...list.querySelectorAll(":scope > .comment-thread")].map((node) => node.dataset.thread);
    // (A reply being written stays as it is: only the threads that changed are drawn again.)
    if (ids.join() !== shown.join()) {
      const drafts = new Map([...list.querySelectorAll(".comment-thread")].map((node) => [node.dataset.thread, node.querySelector("textarea")?.value || ""]));
      clear(list, ...threadsView(ids).childNodes);
      for (const node of list.querySelectorAll(".comment-thread")) { const area = node.querySelector("textarea"); if (area) area.value = drafts.get(node.dataset.thread) || ""; }
      return;
    }
    const all = deckThreads(doc());
    for (const node of [...list.children]) {
      const one = all.find((item) => item.id === node.dataset.thread);
      if (!one || node.thread === one.thread) continue;
      const area = node.querySelector("textarea"), draft = area?.value || "", focused = document.activeElement === area;
      const fresh = threadView(one);
      node.replaceWith(fresh);
      const again = fresh.querySelector("textarea");
      if (again) { again.value = draft; if (focused) again.focus({ preventScroll: true }); }
    }
  }

  // -- a new comment --
  let pending = null;
  // What a new comment is on: the part of a figure chosen, else the object, else the slide.
  function target() {
    const where = deck.where?.() || studio.where || {};
    const n = deck.slide();
    const found = /^(body|left|right|columns\.\d+)\[(\d+)\]$/.exec(String(where.block || ""));
    if (!found || (where.page && where.page - 1 !== n)) return { slide: n, region: null, index: null, part: null };
    const block = holderIn(doc().slides?.[n], found[1], Number(found[2]));
    if (!block) return { slide: n, region: null, index: null, part: null };
    const part = where.part && block.figure && typeof block.figure === "object" ? String(where.part) : null;
    return { slide: n, region: found[1], index: Number(found[2]), part };
  }
  function addComment(at = target()) {
    if (!doc().slides?.[at.slide]) return;
    if (at.slide !== deck.slide()) deck.select(at.slide);
    const page = deck.pageNode();
    if (!page) return;
    const corner = cornerOf(at) || { left: page.clientWidth - 30, top: 10 };
    pending?.remove();
    pending = h("button.comment-marker.open.pending", { type: "button", tabIndex: -1 }, icon("comment"));
    Object.assign(pending.style, { left: `${corner.left}px`, top: `${corner.top}px` });
    if (layer.parentNode !== page) page.append(layer);
    layer.append(pending);
    const field = composer({ placeholder: "Comment", label: "Comment", cancel: () => closeMenu(), send: (text) => {
      add(at, text);
      closeMenu();
      requestAnimationFrame(() => {
        place();
        const key = at.region === null ? "slide" : `${at.region}:${at.index}:${at.part ?? ""}`;
        const marker = layer.querySelector(`.comment-marker[data-anchor="${CSS.escape(key)}"]`);
        if (marker) marker.classList.add("fresh");
      });
    } });
    const me = { ...(workspace?.me || {}), name: myName() || "You" };
    const node = popover(pending, h("div.comment-threads", {}, h("div.comment-thread.new", {},
      h("div.comment-head", {}, avatar(me, { size: 20 }), h("span.comment-author", {}, myName() || "New Comment")), field)), { className: "comment-pop" });
    watchClosed(node);
  }

  // -- going to one (the side panel's list) --
  function open(id) {
    const one = deckThreads(doc()).find((item) => item.id === id);
    if (!one) return;
    if (one.slide !== deck.slide()) deck.select(one.slide);
    if (one.region !== null) deck.choose?.({ region: one.region, index: one.index }, one.part);
    // Once the slide is drawn there, its marker opened (a resolved one: in the list alone).
    const key = anchorKey(one);
    let tries = 0;
    const look = () => {
      place();
      const marker = layer.querySelector(`.comment-marker[data-anchor="${CSS.escape(key)}"]`);
      if (marker) { show(one.slide, key, marker); return; }
      if (++tries < 30) setTimeout(look, 100);
    };
    setTimeout(look, 0);
  }

  // -- kept up --
  let soon = 0;
  studio.on("change", () => {
    cancelAnimationFrame(soon);
    soon = requestAnimationFrame(() => { place(); rail(); refresh(); workspace.emit?.("comments", studio); });
  });
  // The list: what is said of each thread, for the side panel (commentlist.js).
  studio.comments = {
    list: () => deckThreads(doc()).map((one) => ({ id: one.id, open: one.open, thread: one.thread, place: placeOf(one), where: { page: one.slide + 1 } })),
    open,
    resolve: (id, on) => resolve(id, on),
    writer: (name) => writer(workspace, name),
    when,
    add: () => addComment(),
  };
  function placeOf(one) {
    const slide = doc().slides?.[one.slide];
    if (one.region === null) return `Slide ${one.slide + 1}`;
    const block = holderIn(slide, one.region, one.index);
    const kind = block ? Object.keys(block).find((key) => KINDS[key]) : null;
    return `Slide ${one.slide + 1} · ${KINDS[kind] || "Object"}${one.part ? ` · ${partName(block, one.part)}` : ""}`;
  }

  // -- commands --
  const command = () => ({ icon: "comment", label: "Add Comment", keys: "⇧⌘K", run: () => addComment() });
  const own = studio.commands;
  studio.commands = () => [...own(), command(),
    { icon: "comment", label: workspace.side?.open === "comments" ? "Hide Comments" : "Show Comments", run: () => workspace.side?.toggle("comments") }];
  // ⇧⌘K, before the frame's ⌘K (the palette) sees it -- not while words are typed, where the
  // Mac app's menu has it all the same.
  window.addEventListener("keydown", (event) => {
    if (!studio.active || !(event.metaKey || event.ctrlKey) || !event.shiftKey || event.altKey || event.code !== "KeyK") return;
    if (document.querySelector(".scrim:not(.palette-scrim), .present")) return;
    event.preventDefault();
    addComment();
  }, true);

  return {
    rail,
    // The slide drawn (again): its markers placed on the drawing as it is now.
    place: () => place(true),
    // The menus' item: on an object (or a part of its figure, or the slide).
    menuItem: (at = null) => ({ icon: "comment", label: "Add Comment", keys: "⇧⌘K", run: () => addComment(at ? { slide: deck.slide(), part: null, ...at } : target()) }),
    add: addComment, open,
  };
}

const KINDS = { bullets: "List", text: "Text", figure: "Figure", image: "Picture", table: "Table", math: "Equation", code: "Code", quote: "Quote",
  callout: "Callout", stats: "Numbers", gallery: "Gallery", plot: "Plot", mechanism: "Mechanism" };

// A figure's part by its name in the figure (its label), else its id.
function partName(block, part) {
  const figure = block?.figure && typeof block.figure === "object" ? block.figure : null;
  const node = [...(figure?.nodes || []), ...(figure?.groups || [])].find((item) => String(item?.id) === String(part));
  const label = node?.label ?? node?.title;
  return typeof label === "string" && label.trim() ? `“${label.trim().split("\n")[0]}”` : String(part);
}

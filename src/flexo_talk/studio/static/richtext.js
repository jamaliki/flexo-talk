// Words typed on a slide as the slide shows them: flexo markup (**bold**, *italic*,
// `code`, $maths$, [links](url), [colours]{accent}) shown bold, italic, in the
// monospace and in its colour rather than as marks, and a list as a list -- a bullet
// to each item, items indented by level -- rather than lines of spaces.
//
// richText() makes the field: a contenteditable element whose `value` is the markup
// (for a list, one item a line, two spaces a level, as bulletsText writes it), and
// which says "input" whenever it changes, as a textarea does.

import { icon } from "/static/studio/studio.js";

// -- markup to runs --------------------------------------------------------------------

const INLINE = /(\[[^\]\n]+\]\([^)\s]+\)|\[[^\]\n]+\]\{[^}\s]+\}|`[^`]*`|\*\*|\*)/;
const ASTERISK = "";
// Escaped marks, and where each waits while markup is read (deck.py's _HELD): a mark typed
// is written escaped, so it reads back as itself. An escaped $ is a dollar sign.
const HELD = [["\\*", ASTERISK], ["\\`", "\ue001"], ["\\]", "\ue002"], ["\\$", "$"]];
const held = (words) => HELD.reduce((text, [mark, wait]) => text.replaceAll(mark, wait), words);
const freed = (text) => HELD.reduce((out, [mark, wait]) => (wait.length === 1 && wait !== "$" ? out.replaceAll(wait, mark[1]) : out), text);

// Where maths is, delimiters and all, as flexo reads it (flexo.markup.math_spans): $...$
// (not a price: no space inside its ends, no digit after it, unless plainly TeX),
// $$...$$, \(...\) and \[...\]; not an escaped \$, not inside backticks.
function mathSpans(text) {
  const spans = [];
  let index = 0;
  while (index < text.length) {
    const character = text[index];
    if (character === "\\" && "$`".includes(text[index + 1] || " ")) { index += 2; continue; }
    if (character === "`") {
      const end = text.indexOf("`", index + 1);
      if (end > index) { index = end + 1; continue; }
    }
    if (text.startsWith("$$", index) || text.startsWith("\\[", index)) {
      const end = text.indexOf(character === "$" ? "$$" : "\\]", index + 2);
      if (end > index + 2) { spans.push([index, end + 2]); index = end + 2; continue; }
    }
    if (text.startsWith("\\(", index)) {
      const end = text.indexOf("\\)", index + 2);
      if (end > index + 2) { spans.push([index, end + 2]); index = end + 2; continue; }
    }
    if (character === "$") {
      const end = closingDollar(text, index + 1);
      if (end !== null) { spans.push([index, end + 1]); index = end + 1; continue; }
    }
    index += 1;
  }
  return spans;
}

function closingDollar(text, start) {
  for (let index = start; index < text.length; index += 1) {
    if (text[index] === "\\") { index += 1; continue; }
    if (text[index] !== "$") continue;
    const inside = text.slice(start, index);
    if (!inside) return null;
    const tex = /[\\^_{]/.test(inside.replace(/\\\$/g, ""));
    if (/\d/.test(text[index + 1] || "") && !tex) return null;
    if ((/\s/.test(inside[0]) || /\s/.test(inside[inside.length - 1])) && !tex) return null;
    return index;
  }
  return null;
}

function tokensOf(words) {
  const tokens = [];
  const split = (part) => tokens.push(...held(part).split(INLINE).filter(Boolean));
  let at = 0;
  for (const [start, end] of mathSpans(words)) {
    split(words.slice(at, start));
    tokens.push({ maths: words.slice(start, end) });
    at = end;
  }
  split(words.slice(at));
  return tokens;
}

// The * and ** that open or close emphasis, paired as Markdown pairs them (deck.py's
// _emphasis): an opener touches the word after it, a closer the word before.
function emphasis(tokens) {
  const paired = new Set();
  const open = [];
  const edge = (token, end) => (typeof token === "string" ? (end ? token.slice(-1) : token.slice(0, 1)) : token ? "x" : "");
  tokens.forEach((token, index) => {
    if (token !== "*" && token !== "**") return;
    const before = edge(tokens[index - 1], true), after = edge(tokens[index + 1], false);
    const canClose = Boolean(before) && !/\s/.test(before), canOpen = Boolean(after) && !/\s/.test(after);
    const same = open.filter((at) => tokens[at] === token);
    if (canClose && same.length) {
      const at = same[same.length - 1];
      open.splice(open.indexOf(at), 1);
      paired.add(at).add(index);
    } else if (canOpen) open.push(index);
  });
  return paired;
}

// A line pasted into a list as an item: how deep it was indented (two spaces or a tab a
// level) and its words without the bullet or number it came with.
function listed(line) {
  const indent = /^[ \t]*/.exec(line)[0].replace(/\t/g, "  ").length;
  return { depth: Math.floor(indent / 2), words: line.trim().replace(/^(?:[-*+•◦▪‣·–]|\(?\d{1,3}[.)]|\(?[a-z][.)])\s+/i, "") };
}

// Another app's formatted words (text/html) as items: each block -- a paragraph, a
// list's item, a heading, a table's row -- its depth in lists and its words as markup,
// keeping bold, italic, code and links; nothing else of their look.
const BLOCKS_HTML = "address, article, aside, blockquote, center, dd, div, dl, dt, figcaption, figure, footer, h1, h2, h3, h4, h5, h6, header, hr, li, main, nav, ol, p, pre, section, table, tbody, tfoot, thead, tr, ul";
function itemsOfHtml(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  // Word's own bullets and numbers are words in its HTML; the list's levels say them.
  doc.querySelectorAll("script, style, meta, link, img, svg, title, template, [style*='mso-list:ignore' i], [style*='mso-list: ignore' i]").forEach((node) => node.remove());
  doc.querySelectorAll("a[href]").forEach((link) => { link.dataset.href = link.getAttribute("href"); });
  // Headings bold, the way a slide marks them.
  doc.querySelectorAll("h1, h2, h3, h4, h5, h6, th").forEach((node) => { node.style.fontWeight = "700"; });
  doc.querySelectorAll("td + td, td + th, th + td, th + th").forEach((cell) => cell.prepend(" "));
  // Spaces and line ends in the source are one space, as a browser shows them, except
  // in code set out as typed.
  const texts = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  for (let text = texts.nextNode(); text; text = texts.nextNode()) if (!text.parentElement.closest("pre")) text.data = text.data.replace(/[ \t\r\n\f]+/g, " ");
  // The words between one block's edge and the next are an item; an inline wrapper
  // round blocks (Google Docs wraps all it copies in one) is passed through.
  const items = [];
  let run = null, depth = 0;
  const flush = () => {
    if (!run) return;
    const markup = serialise(run).replace(/\u00a0/g, " ").replace(/\n$/, "");
    for (const part of markup.split("\n")) items.push({ depth, markup: part.trim() });
    run = null;
  };
  const walk = (node, lists) => {
    for (const child of [...node.childNodes]) {
      const element = child.nodeType === Node.ELEMENT_NODE;
      if (element && (child.matches(BLOCKS_HTML) || child.querySelector(BLOCKS_HTML))) {
        flush();
        walk(child, lists + (child.matches("ul, ol") ? 1 : 0));
        flush();
        continue;
      }
      if (!run) {
        if (!child.textContent.trim() && !(element && (child.nodeName === "BR" || child.querySelector("br")))) continue;
        run = doc.createElement("span");
        depth = Math.max(0, lists - 1);
      }
      run.append(child);
    }
  };
  walk(doc.body, 0);
  flush();
  // Blank lines one at a time, and none at either end.
  const kept = items.filter((item, n) => item.markup || (n && items[n - 1].markup));
  while (kept.length && !kept[kept.length - 1].markup) kept.pop();
  while (kept.length && !kept[0].markup) kept.shift();
  return kept;
}

// -- markup to the page and back -------------------------------------------------------

function wrapped(node, { bold, italic }) {
  let out = node;
  if (italic) { const i = document.createElement("i"); i.append(out); out = i; }
  if (bold) { const b = document.createElement("b"); b.append(out); out = b; }
  return out;
}

// The nodes markup stands for: `colours` gives a colour's name its look.
function inlineNodes(words, colours, outer = { bold: false, italic: false }) {
  const tokens = tokensOf(words);
  const paired = emphasis(tokens);
  const nodes = [];
  let bold = outer.bold, italic = outer.italic;
  tokens.forEach((token, index) => {
    if (token === "**" && paired.has(index)) { bold = !bold; return; }
    if (token === "*" && paired.has(index)) { italic = !italic; return; }
    const style = { bold, italic };
    if (typeof token !== "string") {
      const maths = document.createElement("span");
      maths.className = "rt-maths";
      maths.textContent = token.maths;
      nodes.push(wrapped(maths, style));
      return;
    }
    const link = /^\[([^\]\n]+)\]\(([^)\s]+)\)$/.exec(token);
    const coloured = /^\[([^\]\n]+)\]\{([^}\s]+)\}$/.exec(token);
    const code = /^`([^`]*)`$/.exec(token);
    if (link || coloured) {
      const node = document.createElement(link ? "a" : "span");
      if (link) { node.dataset.href = link[2]; node.title = link[2]; }
      else { node.dataset.colour = coloured[2]; node.style.color = colours(coloured[2]); }
      node.append(...inlineNodes((link || coloured)[1], colours, style));
      nodes.push(node);
    } else if (code) {
      const node = document.createElement("code");
      node.textContent = freed(code[1]);
      nodes.push(wrapped(node, style));
    } else {
      // Lines in the words are lines on the page.
      freed(token).split("\n").forEach((line, n) => {
        if (n) nodes.push(document.createElement("br"));
        if (line) nodes.push(wrapped(document.createTextNode(line), style));
      });
    }
  });
  return nodes;
}

// The runs a node holds: words with their emphasis, or markup kept as written (maths,
// code, a link, a colour).
function runsOf(node, style, runs, names) {
  for (const child of node.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) { runs.push({ text: child.data.replace(/ /g, " "), ...style }); continue; }
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    const tag = child.nodeName;
    if (tag === "BR") { runs.push({ text: "\n", ...style }); continue; }
    if (child.classList.contains("rt-maths")) { runs.push({ raw: child.textContent }); continue; }
    const css = child.style || {};
    // A weight or slant set in its style is its own, even on a <b> (Google Docs wraps
    // all it copies in a <b> of normal weight).
    const next = {
      bold: css.fontWeight ? /^bold/.test(css.fontWeight) || Number(css.fontWeight) >= 600 : style.bold || tag === "B" || tag === "STRONG",
      italic: css.fontStyle ? css.fontStyle !== "normal" : style.italic || tag === "I" || tag === "EM",
    };
    if (tag === "CODE") { runs.push({ raw: `\`${child.textContent.replace(/`/g, "")}\``, ...next, wrap: true }); continue; }
    const colour = child.dataset?.colour || (tag === "FONT" && child.getAttribute("color") ? names(child.getAttribute("color")) : null);
    if (tag === "A" && child.dataset.href) { runs.push({ raw: `[${serialise(child, next, names)}](${address(child.dataset.href)})` }); continue; }
    // The ink is the words' own colour: no colour of their own.
    if (colour && colour !== "ink") { runs.push({ raw: `[${serialise(child, next, names)}]{${colour}}` }); continue; }
    // A line the browser made a block of its own (a pasted or split paragraph) is a line.
    if ((tag === "DIV" || tag === "P") && runs.length && !String(runs[runs.length - 1].text ?? "").endsWith("\n")) runs.push({ text: "\n" });
    runsOf(child, next, runs, names);
  }
  return runs;
}

const escaped = (text) => text.replace(/[*`$]/g, "\\$&").replace(/\](?=[({])/g, "\\]");
// A link's address as markup reads it: no space, no bracket to end it early.
const address = (href) => href.replace(/[\s()]/g, (mark) => `%${mark.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")}`);

// Runs as markup: emphasis opened and closed only where it changes, each mark against
// a word (spaces kept outside it), so ** and * pair as written.
function markupOf(runs) {
  // Marks open now, the innermost last ("**" bold, "*" italic): kept nested, so that
  // Markdown reads them as we do -- one that ends inside another closes what was opened
  // after it and opens it again, never crossing it.
  let out = "", pending = "";
  const stack = [];
  const closeAll = () => { let marks = ""; while (stack.length) marks += stack.pop(); return marks; };
  const lasts = (from, mark) => {
    let count = 0;
    for (let k = from; k < runs.length; k += 1) {
      const run = runs[k];
      if (run.raw !== undefined && !run.wrap) break;
      if (!(mark === "**" ? run.bold : run.italic)) break;
      count += 1;
    }
    return count;
  };
  runs.forEach((run, index) => {
    if (run.raw !== undefined && !run.wrap) { out += closeAll() + pending + run.raw; pending = ""; return; }
    const text = run.raw ?? escaped(run.text);
    const [, lead, core, trail] = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
    if (!core) { pending += text; return; }
    const want = { "**": Boolean(run.bold), "*": Boolean(run.italic) };
    let marks = "";
    const reopen = [];
    const lowest = stack.findIndex((mark) => !want[mark]);
    if (lowest >= 0) {
      while (stack.length > lowest) {
        const mark = stack.pop();
        marks += mark;
        if (want[mark]) reopen.unshift(mark);
      }
    }
    out += marks + pending + lead;
    // What opens here opens longest-lasting first, so it is the outer one.
    const opening = ["**", "*"].filter((mark) => want[mark] && !stack.includes(mark) && !reopen.includes(mark))
      .sort((a, b) => lasts(index, b) - lasts(index, a));
    for (const mark of [...reopen, ...opening]) { out += mark; stack.push(mark); }
    out += core;
    pending = trail;
  });
  return out + closeAll() + pending;
}

function serialise(node, style = { bold: false, italic: false }, names = (colour) => colour) {
  return markupOf(runsOf(node, style, [], names));
}

// -- the field -------------------------------------------------------------------------

// `list` makes it a list (Tab and Shift-Tab change an item's level, Return starts the
// next item, Return on an empty item moves it out a level); `single` a line of its own
// (Return is left to whoever holds it); else words in lines. `palette` gives the
// theme's colours by name, for [words]{accent}.
export function richText({ value = "", list = false, single = false, numbered = false, palette = {}, placeholder = "", spelling = true, leaveOnTab = false, frame = null } = {}) {
  const area = document.createElement("div");
  area.className = `rich${list ? " rt-list" : ""}${numbered ? " rt-numbered" : ""}`;
  area.contentEditable = "true";
  area.spellcheck = spelling;
  area.dataset.placeholder = placeholder;
  area.setAttribute("role", "textbox");
  if (!single) area.setAttribute("aria-multiline", "true");
  const colours = (name) => palette[name] || palette[`tone-${/\d+/.exec(name)?.[0] || 1}`] || (name.startsWith("#") ? name : "");
  const names = (hex) => Object.entries(palette).find(([, colour]) => String(colour).toLowerCase() === String(hex).toLowerCase())?.[0] || hex;

  const lineNode = (level, words) => {
    const line = document.createElement("div");
    line.className = "rt-line";
    line.dataset.level = String(level);
    line.append(...inlineNodes(words, colours));
    if (!line.childNodes.length) line.append(document.createElement("br"));
    return line;
  };
  const lines = () => [...area.children].filter((child) => child.classList.contains("rt-line"));
  // Words left in the list itself (all of it deleted and typed anew) go in a line.
  const tidy = () => {
    if (!list) return;
    const loose = [...area.childNodes].filter((node) => !(node.nodeType === Node.ELEMENT_NODE && node.classList.contains("rt-line")));
    if (!loose.length) return;
    const selection = getSelection();
    const caret = selection.rangeCount ? selection.getRangeAt(0) : null;
    let line = null;
    for (const node of loose) {
      if (node.nodeType === Node.ELEMENT_NODE && node.nodeName === "DIV") { node.classList.add("rt-line"); node.dataset.level ||= "0"; line = null; continue; }
      if (!line) { line = document.createElement("div"); line.className = "rt-line"; line.dataset.level = "0"; node.before(line); }
      line.append(node);
    }
    if (caret) { selection.removeAllRanges(); selection.addRange(caret); }
  };
  const read = () => {
    tidy();
    const strip = (text) => text.replace(/\n$/, "");
    if (list) return lines().map((line) => "  ".repeat(Number(line.dataset.level) || 0) + strip(serialise(line, undefined, names)).replace(/\n/g, " ")).join("\n");
    const text = strip(serialise(area, undefined, names));
    return single ? text.replace(/\n/g, " ") : text;
  };
  const write = (text) => {
    area.replaceChildren();
    if (list) {
      for (const raw of String(text ?? "").split("\n")) {
        const indent = /^[ \t]*/.exec(raw)[0].replace(/\t/g, "  ").length;
        area.append(lineNode(Math.floor(indent / 2), raw.trim()));
      }
      if (!area.children.length) area.append(lineNode(0, ""));
    } else area.append(...inlineNodes(String(text ?? ""), colours));
    area.classList.toggle("empty", !String(text ?? "").trim());
  };
  write(value);
  Object.defineProperty(area, "value", { get: read, set: write });
  area.rich = true;
  // A change of look (bold, a colour, a link) or a paste says it is a step of its own, for
  // the history: typing runs together, these do not (a native ⌘B says so by its inputType).
  const changed = (step = false) => area.dispatchEvent(new CustomEvent("input", { bubbles: true, detail: { step } }));
  area.addEventListener("input", () => area.classList.toggle("empty", !area.textContent.trim() && !area.querySelector(".rt-line + .rt-line")));

  // -- the caret --
  const selection = () => getSelection();
  const place = (range) => { const s = selection(); s.removeAllRanges(); s.addRange(range); };
  area.selectAll = () => { const range = document.createRange(); range.selectNodeContents(area); place(range); };
  area.caretToEnd = () => { const range = document.createRange(); range.selectNodeContents(area); range.collapse(false); place(range); };
  // The words as letters, and where the caret is as a count of the letters before it (a
  // new line counts one): so the caret stays where it was when the words change under it.
  const lettersIn = (root) => {
    let text = "", lines = 0;
    const go = (node) => {
      for (const child of node.childNodes) {
        if (child.nodeType === Node.TEXT_NODE) text += child.data;
        else if (child.nodeType !== Node.ELEMENT_NODE) continue;
        else if (child.classList.contains("rt-line")) { if (lines++) text += "\n"; go(child); }
        else if (child.nodeName === "BR") { if (!list) text += "\n"; }
        else go(child);
      }
    };
    go(root);
    return text;
  };
  area.letters = () => lettersIn(area);
  area.caretAt = () => {
    const s = selection();
    if (!s.rangeCount || !area.contains(s.anchorNode) || !area.contains(s.focusNode)) return null;
    const range = s.getRangeAt(0);
    const upTo = (container, offset) => { const r = document.createRange(); r.setStart(area, 0); r.setEnd(container, offset); return lettersIn(r.cloneContents()).length; };
    return [upTo(range.startContainer, range.startOffset), upTo(range.endContainer, range.endOffset)];
  };
  const pointAt = (count) => {
    let left = count, lines = 0, previous = null, found = null;
    const go = (node) => {
      for (const [index, child] of [...node.childNodes].entries()) {
        if (found) return;
        if (child.nodeType === Node.TEXT_NODE) {
          if (left <= child.data.length) { found = [child, left]; return; }
          left -= child.data.length;
        } else if (child.nodeType !== Node.ELEMENT_NODE) continue;
        else if (child.classList.contains("rt-line")) {
          if (lines++) {
            if (left === 0) { found = [previous, previous.textContent ? previous.childNodes.length : 0]; return; }
            left -= 1;
          }
          previous = child;
          go(child);
          if (!found && left === 0) found = [child, child.textContent ? child.childNodes.length : 0];
        } else if (child.nodeName === "BR") {
          if (list) continue;
          if (left === 0) { found = [node, index]; return; }
          left -= 1;
        } else go(child);
      }
    };
    go(area);
    return found;
  };
  area.caretTo = (start, end = start) => {
    const from = pointAt(start), to = pointAt(end);
    if (!from || !to) { area.caretToEnd(); return; }
    const range = document.createRange();
    range.setStart(...from);
    range.setEnd(...to);
    place(range);
  };
  // The word under a point (a double-click on the slide), as a Mac text view selects it.
  area.selectWordAt = (point) => {
    const range = document.caretRangeFromPoint?.(point.x, point.y);
    if (!range || !area.contains(range.startContainer)) return false;
    place(range);
    const s = selection();
    const text = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.data : "";
    const at = range.startOffset;
    if (!/[\p{L}\p{N}]/u.test(text[at] || "") && !/[\p{L}\p{N}]/u.test(text[at - 1] || "")) return true;
    s.modify?.("move", "backward", "word");
    s.modify?.("extend", "forward", "word");
    // A word and not the space after it.
    const chosen = s.toString();
    const trail = chosen.length - chosen.trimEnd().length;
    for (let n = 0; n < trail; n += 1) s.modify?.("extend", "backward", "character");
    return true;
  };
  const lineAt = (node) => {
    let at = node;
    while (at && at !== area) { if (at.classList?.contains("rt-line")) return at; at = at.parentNode; }
    return null;
  };
  const chosenLines = () => {
    const s = selection();
    if (!s.rangeCount) return [];
    const range = s.getRangeAt(0);
    const first = lineAt(range.startContainer), last = lineAt(range.endContainer);
    const all = lines();
    if (!first) return [];
    return all.slice(all.indexOf(first), all.indexOf(last || first) + 1);
  };
  const atStart = (line) => {
    const s = selection();
    if (!s.rangeCount || !s.isCollapsed) return false;
    const before = document.createRange();
    before.setStart(line, 0);
    before.setEnd(s.anchorNode, s.anchorOffset);
    return !before.toString().length;
  };
  // An item's level: one deeper than the item before it at most.
  const setLevel = (line, level) => {
    const previous = line.previousElementSibling;
    const most = previous ? Number(previous.dataset.level) + 1 : 0;
    line.dataset.level = String(Math.max(0, Math.min(level, most)));
  };

  // Words drawn bold (a title) are bold already: the markup has no "not bold" to give them.
  const boldAlready = () => Number(getComputedStyle(area).fontWeight) >= 600;
  area.addEventListener("keydown", (event) => {
    const mod = event.metaKey || event.ctrlKey;
    if (mod && !event.altKey && ["b", "i"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      if (event.key.toLowerCase() === "b" && boldAlready()) return;
      document.execCommand(event.key.toLowerCase() === "b" ? "bold" : "italic");
      return;
    }
    if (event.key === "Tab" && list) {
      event.preventDefault();
      for (const line of chosenLines()) setLevel(line, Number(line.dataset.level) + (event.shiftKey ? -1 : 1));
      changed();
      return;
    }
    // Tab is no character here: in a panel's field it goes on to the next control.
    if (event.key === "Tab" && !single) { if (!leaveOnTab) event.preventDefault(); return; }
    // ⌘K links the words chosen, as in Keynote and Pages.
    if (mod && !event.altKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      event.stopPropagation();
      if (!selection().isCollapsed) askLink();
      return;
    }
    if (event.key === "Backspace" && list) {
      const [line] = chosenLines();
      if (line && atStart(line) && Number(line.dataset.level) > 0) { event.preventDefault(); line.dataset.level = String(Number(line.dataset.level) - 1); changed(); }
      return;
    }
    if (event.key !== "Enter" || event.isComposing) return;
    if (single) { event.preventDefault(); if (event.shiftKey) { document.execCommand("insertLineBreak"); } return; }
    event.preventDefault();
    if (!list || event.shiftKey) { document.execCommand("insertLineBreak"); return; }
    // Return ends an item and starts the next at its level; on an empty item, it moves out a level.
    const s = selection();
    if (!s.rangeCount) return;
    if (!s.isCollapsed) s.deleteFromDocument();
    const line = lineAt(s.anchorNode);
    if (!line) return;
    const level = Number(line.dataset.level) || 0;
    if (!line.textContent.trim() && level > 0) { line.dataset.level = String(level - 1); changed(); return; }
    const tail = document.createRange();
    tail.setStart(s.anchorNode, s.anchorOffset);
    tail.setEnd(line, line.childNodes.length);
    const rest = tail.extractContents();
    const next = lineNode(level, "");
    if (rest.textContent.length) next.replaceChildren(rest);
    if (!line.childNodes.length || !line.textContent.length && !line.querySelector("br")) line.replaceChildren(document.createElement("br"));
    line.after(next);
    const caret = document.createRange();
    caret.setStart(next, 0);
    caret.collapse(true);
    place(caret);
    changed();
  });

  // -- the format bar: over the words chosen, as a Mac text view's touch bar offers them --
  const swatches = [["accent", "Accent"], ["accent2", "Accent 2"], ["muted", "Muted"]].filter(([name]) => palette[name]);
  const bar = document.createElement("div");
  bar.className = "rt-bar";
  bar.hidden = true;
  const tool = (label, title, run, style = {}) => {
    const button = document.createElement("button");
    button.type = "button";
    button.title = title;
    if (label instanceof Node) button.append(label); else button.innerHTML = label;
    Object.assign(button.style, style);
    // The words stay chosen: the button never takes the caret.
    button.addEventListener("mousedown", (event) => { event.preventDefault(); run(); changed(true); showBar(); });
    return button;
  };
  const wrapChosen = (make) => {
    const s = selection();
    if (!s.rangeCount || s.isCollapsed) return;
    const range = s.getRangeAt(0);
    const node = make(range.toString());
    range.deleteContents();
    range.insertNode(node);
    const after = document.createRange();
    after.selectNodeContents(node);
    place(after);
  };
  const plainNode = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; node.textContent = text; return node; };
  const linkInput = document.createElement("input");
  linkInput.className = "rt-link";
  linkInput.placeholder = "https://";
  linkInput.hidden = true;
  let linkRange = null;
  linkInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const url = linkInput.value.trim();
      if (url && linkRange) {
        place(linkRange);
        wrapChosen((text) => { const a = plainNode("a", "", text); a.dataset.href = url; a.title = url; return a; });
        changed(true);
      }
      linkInput.hidden = true;
      area.focus();
    } else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); linkInput.hidden = true; if (linkRange) place(linkRange); area.focus(); }
  });
  const boldTool = tool("<b>B</b>", "Bold (⌘B)", () => document.execCommand("bold"));
  const italicTool = tool("<i>I</i>", "Italic (⌘I)", () => document.execCommand("italic"));
  function askLink() {
    const s = selection();
    linkRange = s.rangeCount ? s.getRangeAt(0).cloneRange() : null;
    linkInput.value = "";
    showBar();
    linkInput.hidden = false;
    setTimeout(() => linkInput.focus(), 0);
  }
  bar.append(
    boldTool,
    italicTool,
    tool("<span style=\"font-family: var(--mono); font-size: 11px\">&lt;/&gt;</span>", "Code", () => wrapChosen((text) => plainNode("code", "", text))),
    tool("<span style=\"font-family: Georgia, serif\">∑</span>", "Equation: the words chosen as LaTeX", () => wrapChosen((text) => plainNode("span", "rt-maths", `$${text}$`))),
    tool(icon("link"), "Link (⌘K)", () => askLink()),
    ...swatches.map(([name, title]) => tool(`<span class="rt-swatch" style="background:${palette[name]}"></span>`, title, () => document.execCommand("foreColor", false, palette[name]))),
    palette.ink ? tool(`<span class="rt-swatch" style="background:${palette.ink}"></span>`, "Default colour", () => document.execCommand("foreColor", false, palette.ink)) : "",
    linkInput);
  let seen = false;
  const showBar = () => {
    // A field gone from the page (the panel drawn again) takes its bar and listener with it.
    if (!area.isConnected) { if (seen) area.dispose(); return; }
    seen = true;
    const s = selection();
    const inside = s.rangeCount && area.contains(s.anchorNode) && area.contains(s.focusNode);
    if (!inside || s.isCollapsed) { if (document.activeElement !== linkInput) bar.hidden = true; return; }
    if (!bar.isConnected) document.body.append(bar);
    boldTool.hidden = boldAlready();
    // Pressed where the words chosen are bold or italic, as a Mac format bar shows.
    boldTool.classList.toggle("on", document.queryCommandState("bold"));
    italicTool.classList.toggle("on", document.queryCommandState("italic"));
    bar.hidden = false;
    // Over the thing being edited, never on it (`frame`: a table for its cell), else under it.
    const chosen = s.getRangeAt(0).getBoundingClientRect(), own = bar.getBoundingClientRect();
    const around = frame?.() || (area.closest(".inline-editor, .rich-field") || area).getBoundingClientRect();
    const above = Math.min(chosen.top, around.top) - own.height - 8;
    const top = above > 8 ? above : Math.max(chosen.bottom, around.bottom) + 8;
    const left = Math.min(Math.max(8, chosen.left + chosen.width / 2 - own.width / 2), innerWidth - own.width - 8);
    Object.assign(bar.style, { top: `${top}px`, left: `${left}px` });
  };
  document.addEventListener("selectionchange", showBar);
  // Whoever closes the field takes its bar with it.
  area.dispose = () => { bar.remove(); document.removeEventListener("selectionchange", showBar); };

  // Pasted words come in the look of where they go, keeping what Keynote keeps of another
  // app's: bold, italic, code and links, and a list's items and levels (⌥⇧⌘V, Paste and
  // Match Style, keeps the words alone). Lines pasted in a list are items.
  let matchStyle = false;
  area.addEventListener("keydown", (event) => {
    matchStyle = (event.metaKey || event.ctrlKey) && event.altKey && event.shiftKey && event.key.toLowerCase() === "v";
  });
  // Lines of markup in at the caret, in place of what is chosen.
  const insertMarkup = (...lines) => {
    const s = selection();
    if (!s.rangeCount) return;
    const range = s.getRangeAt(0);
    range.deleteContents();
    const nodes = lines.flatMap((markup, n) => [...(n ? [document.createElement("br")] : []), ...inlineNodes(markup, colours)]);
    if (!nodes.length) return;
    const fragment = document.createDocumentFragment();
    fragment.append(...nodes);
    const last = nodes[nodes.length - 1];
    range.insertNode(fragment);
    const caret = document.createRange();
    caret.setStartAfter(last);
    caret.collapse(true);
    place(caret);
  };
  area.addEventListener("paste", (event) => {
    const text = event.clipboardData?.getData("text/plain");
    const html = matchStyle ? "" : event.clipboardData?.getData("text/html") || "";
    matchStyle = false;
    if (text === undefined && !html) return;
    event.preventDefault();
    changed(true);
    // What was pasted, as items: each its depth in a list and its words as markup.
    const formatted = html ? itemsOfHtml(html).filter((item) => !list || item.markup) : null;
    const plainParts = String(text ?? "").replace(/\r\n?/g, "\n").split("\n");
    const items = formatted?.length ? formatted
      : plainParts.length > 1 && list ? plainParts.map(listed).map((item) => ({ depth: item.depth, markup: escaped(item.words) }))
        : plainParts.map((part) => ({ depth: 0, markup: escaped(part) }));
    if (single) { insertMarkup(items.map((item) => item.markup).join(" ")); changed(true); return; }
    if (!list) { insertMarkup(...items.map((item) => item.markup)); changed(true); return; }
    // In a list, items: their indents kept as levels under the item pasted into, and the
    // words after the caret moved to the end of the last one. The first goes on with the
    // item pasted into as it was, unless that is empty.
    let line = lineAt(selection().anchorNode);
    if (!formatted?.length && line?.textContent.trim() && plainParts.length > 1) items[0] = { depth: items[0].depth, markup: escaped(plainParts[0]) };
    const level = Number(line?.dataset.level) || 0;
    let rest = null;
    if (line && items.length > 1) {
      const after = document.createRange();
      const s = selection();
      after.setStart(s.getRangeAt(0).endContainer, s.getRangeAt(0).endOffset);
      after.setEnd(line, line.childNodes.length);
      if (!s.isCollapsed) document.execCommand("delete");  // what was chosen goes, as a paste replaces it
      rest = after.extractContents();
    }
    insertMarkup(items[0].markup);
    line = lineAt(selection().anchorNode);
    const first = items[0].depth;
    for (const item of items.slice(1)) {
      if (!line) break;
      const next = lineNode(Math.max(0, Math.min(4, level + item.depth - first)), item.markup);
      line.after(next);
      line = next;
    }
    if (line) {
      const caret = document.createRange();
      caret.selectNodeContents(line);
      caret.collapse(false);
      if (rest?.textContent) {
        if (!line.textContent) line.replaceChildren();
        line.append(rest);
      }
      place(caret);
    }
    changed(true);
  });
  return area;
}

export { serialise as markupFromNodes, inlineNodes as nodesFromMarkup, escaped as markupOfWords, itemsOfHtml };

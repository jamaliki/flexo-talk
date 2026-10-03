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

// A link's or a colour's words (deck.py's _WORDS_IN): no bracket in them but those of
// another link or colour (a link's words coloured, a colour's words linked) or one alone
// that starts none.
const WORDS_IN = String.raw`(?:[^\[\]\n]|\[[^\[\]\n]+\](?:\([^)\s]+\)|\{[^}\s]+\})|\[(?![^\[\]\n]+\](?:\([^)\s]+\)|\{[^}\s]+\})))+`;
const LINK = new RegExp(String.raw`^\[(${WORDS_IN})\]\(([^)\s]+)\)$`);
const COLOURED = new RegExp(String.raw`^\[(${WORDS_IN})\]\{([^}\s]+)\}$`);
const INLINE = new RegExp(String.raw`(\[${WORDS_IN}\]\([^)\s]+\)|\[${WORDS_IN}\]\{[^}\s]+\}|` + "`[^`]*`" + String.raw`|\*\*|\*)`);
const ASTERISK = "";
// Escaped marks, and where each waits while markup is read (deck.py's _HELD): a mark typed
// is written escaped, so it reads back as itself. An escaped $ is a dollar sign, and \\(
// and \\[ a backslash before a bracket (a typed \( is written so), not maths.
const HELD = [["\\*", ASTERISK], ["\\`", "\ue001"], ["\\]", "\ue002"]];
const held = (words) => HELD.reduce((text, [mark, wait]) => text.replaceAll(mark, wait), words);
const freed = (text) => HELD.reduce((out, [mark, wait]) => out.replaceAll(wait, mark[1]), text).replaceAll("\\$", "$").replaceAll("\ue003", "\\");

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

// Markup as tokens (deck.py's inline): words, maths ({ maths }), links, colours, code, *
// and **. Maths stands aside, as a letter that is no mark, while the rest is split, so
// maths in a link's or a colour's words stays in them.
function tokensOf(words) {
  const masked = words.replace(/(\\`|`[^`]*`)|\\\\(?=[([])/g, (found, kept) => kept ?? "\ue003\ue003");
  const maths = [];
  let text = "", at = 0;
  for (const [start, end] of mathSpans(masked)) {
    text += `${masked.slice(at, start)}\ue010${maths.length}\ue011`;
    maths.push(words.slice(start, end));
    at = end;
  }
  text += masked.slice(at);
  const back = (part) => part.replace(/\ue010(\d+)\ue011/g, (_, n) => maths[n]);
  const tokens = [];
  for (const token of held(text.replaceAll("\ue003\ue003", "\ue003")).split(INLINE).filter(Boolean)) {
    if (LINK.test(token) || COLOURED.test(token)) { tokens.push(back(token)); continue; }
    for (const part of token.split(/(\ue010\d+\ue011)/).filter(Boolean)) tokens.push(/^\ue010\d+\ue011$/.test(part) ? { maths: back(part) } : part);
  }
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
        // Word's list items are paragraphs, each saying its level ("mso-list:l0 level2 lfo1").
        const word = /mso-list:\s*l\d+\s+level(\d+)/i.exec(child.getAttribute("style") || "");
        walk(child, word ? Number(word[1]) : lists + (child.matches("ul, ol") ? 1 : 0));
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
    const link = LINK.exec(token);
    const coloured = !link && COLOURED.exec(token);
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
function runsOf(node, style, runs, names, inside = false) {
  for (const child of node.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) { runs.push({ text: child.data.replace(/ /g, " "), ...style, inside }); continue; }
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    const tag = child.nodeName;
    if (tag === "BR") { runs.push({ text: "\n", ...style }); continue; }
    // Maths keeps the emphasis it is in, as the slide reads it.
    if (child.classList.contains("rt-maths")) { runs.push({ raw: child.textContent, ...style, wrap: true }); continue; }
    const css = child.style || {};
    // A weight or slant set in its style is its own, even on a <b> (Google Docs wraps
    // all it copies in a <b> of normal weight).
    const next = {
      bold: css.fontWeight ? /^bold/.test(css.fontWeight) || Number(css.fontWeight) >= 600 : style.bold || tag === "B" || tag === "STRONG",
      italic: css.fontStyle ? css.fontStyle !== "normal" : style.italic || tag === "I" || tag === "EM",
    };
    if (tag === "CODE") { runs.push({ raw: `\`${child.textContent.replace(/`/g, "")}\``, ...next, wrap: true }); continue; }
    const colour = child.dataset?.colour || (tag === "FONT" && child.getAttribute("color") ? names(child.getAttribute("color")) : null);
    // The ink is the words' own colour: no colour of their own. A link or a colour over a
    // line's end is one on each line, as markup has no line in one.
    if ((tag === "A" && child.dataset.href) || (colour && colour !== "ink")) {
      for (const part of byLine(child)) {
        if (part === "\n") runs.push({ text: "\n", ...next });
        else if (part.textContent) runs.push({ raw: tag === "A" && child.dataset.href ? `[${serialise(part, next, names, true)}](${address(child.dataset.href)})` : `[${serialise(part, next, names, true)}]{${colour}}` });
      }
      continue;
    }
    // A line the browser made a block of its own (a pasted or split paragraph) is a line.
    if ((tag === "DIV" || tag === "P") && runs.length && !String(runs[runs.length - 1].text ?? "").endsWith("\n")) runs.push({ text: "\n" });
    runsOf(child, next, runs, names, inside);
  }
  return runs;
}

// Words as markup that reads back as them: each mark escaped, a ] that would end a link's
// words (in a link's or a colour's words, any), and a backslash that would make what
// follows maths (\( or \[) or an escape (\]).
const escaped = (text, inside = false) => text.replace(/\\(?=[([])/g, "\\\\").replace(/[*`$]/g, "\\$&")
  .replace(inside ? /\\?\]/g : /\\?\](?=[({])|\\\]/g, (found) => (found.length > 1 ? "\\\\]" : "\\]"));
// A link's address as markup reads it: no space, no bracket to end it early.
const address = (href) => href.replace(/[\s()]/g, (mark) => `%${mark.charCodeAt(0).toString(16).toUpperCase().padStart(2, "0")}`);

// Runs as markup: emphasis opened and closed only where it changes, each mark against
// a word (spaces kept outside it), so ** and * pair as written.
function markupOf(runs) {
  // Marks open now, the innermost last ("**" bold, "*" italic): kept nested, so that
  // Markdown reads them as we do -- one that ends inside another closes what was opened
  // after it and opens it again past the space between them. Between two letters there is
  // no space to part them, and the marks run together (*, ** and * would read as ** and
  // **): there a mark closes alone, never closed and opened again in one run of marks,
  // and the readers (here and deck.py's _emphasis) pair each kind with its own.
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
    const text = run.raw ?? escaped(run.text, run.inside);
    const [, lead, core, trail] = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
    if (!core) { pending += text; return; }
    const want = { "**": Boolean(run.bold), "*": Boolean(run.italic) };
    let marks = "";
    const reopen = [];
    const lowest = stack.findIndex((mark) => !want[mark]);
    const between = !(pending + lead);
    if (lowest >= 0 && between) {
      for (const mark of stack.filter((open) => !want[open]).reverse()) { marks += mark; stack.splice(stack.lastIndexOf(mark), 1); }
    } else if (lowest >= 0) {
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

// An element as copies of it a line each, and the line ends ("\n") between them.
function byLine(element) {
  if (!element.querySelector("br")) return [element];
  const parts = [];
  const rest = element.cloneNode(true);
  for (let end = rest.querySelector("br"); end; end = rest.querySelector("br")) {
    const before = document.createRange();
    before.setStart(rest, 0);
    before.setEndBefore(end);
    const line = element.cloneNode(false);
    line.append(before.extractContents());
    end.remove();
    parts.push(line, "\n");
  }
  parts.push(rest);
  return parts;
}

function serialise(node, style = { bold: false, italic: false }, names = (colour) => colour, inside = false) {
  return markupOf(runsOf(node, style, [], names, inside));
}

// -- the field -------------------------------------------------------------------------

// `list` makes it a list (Tab and Shift-Tab change an item's level, Return starts the
// next item, Return on an empty item moves it out a level); `single` a line of its own
// (Return is left to whoever holds it); else words in lines. `palette` gives the
// theme's colours by name, for [words]{accent}.
export function richText({ value = "", list = false, single = false, numbered = false, palette = {}, placeholder = "", spelling = true, leaveOnTab = false, frame = null, room = null } = {}) {
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
  // Only the look the slide keeps is offered: bold and italic, not underline and the like
  // (a menu's or the system's), which saving would drop.
  area.addEventListener("beforeinput", (event) => { if (/^format/.test(event.inputType) && !["formatBold", "formatItalic"].includes(event.inputType)) event.preventDefault(); });

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
    // All the items chosen (Return or Tab onto the list) are chosen from the list itself.
    const first = lineAt(range.startContainer) || (range.startContainer === area ? area.children[range.startOffset] : null);
    const last = lineAt(range.endContainer) || (range.endContainer === area ? area.children[range.endOffset - 1] : null);
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
    // ⌃Tab: to the format bar, to format from the keys.
    if (event.key === "Tab" && event.ctrlKey && !event.metaKey && !event.altKey) { event.preventDefault(); event.stopPropagation(); toBar(); return; }
    // ⌘E makes the words chosen code, ⌥⌘E an equation (⌃E stays a Mac's end of the line).
    const command = /Mac|iP/.test(navigator.platform) ? event.metaKey : event.ctrlKey;
    if (command && !event.shiftKey && (event.code === "KeyE" || event.key.toLowerCase() === "e")) {
      event.preventDefault();
      event.stopPropagation();
      if ((event.altKey ? asMaths() : asCode()) !== false) changed(true);
      return;
    }
    // No underline: the slide has none to keep.
    if (mod && !event.altKey && (event.code === "KeyU" || event.key.toLowerCase() === "u")) { event.preventDefault(); return; }
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
      askLink();
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
  // From the keys: ⌃Tab goes to it from the words (as ⌃Tab leaves a Mac text view for the
  // next control), ← and → go along it, Space or Return presses a button, and Esc or Tab
  // goes back to the words; ⌘E makes the words code and ⌥⌘E an equation (as Pages inserts one).
  const swatches = [["accent", "Accent"], ["accent2", "Accent 2"], ["muted", "Muted"]].filter(([name]) => palette[name]);
  const bar = document.createElement("div");
  bar.className = "rt-bar";
  bar.setAttribute("role", "toolbar");
  bar.setAttribute("aria-label", "Format");
  bar.hidden = true;
  // The words chosen while the bar has the keys, given back to the words to act on.
  let kept = null;
  const backToWords = () => {
    area.focus();
    if (kept && area.contains(kept.startContainer)) place(kept);
  };
  const keyed = () => bar.contains(document.activeElement);
  const tool = (label, title, run, { words = false } = {}) => {
    const button = document.createElement("button");
    button.type = "button";
    button.title = title;
    button.tabIndex = -1;
    if (words) button.dataset.words = "";
    if (label instanceof Node) button.append(label); else button.innerHTML = label;
    // The words stay chosen: the button never takes the caret.
    button.addEventListener("mousedown", (event) => { event.preventDefault(); if (run() !== false) changed(true); showBar(); });
    // Pressed from the keys (Space or Return on it): on the words, and the keys stay on it.
    button.addEventListener("click", (event) => {
      if (event.detail || !keyed()) return;
      backToWords();
      const done = run();
      if (done !== false) changed(true);
      if (done === "words") return;
      const s = selection();
      kept = s.rangeCount && area.contains(s.anchorNode) ? s.getRangeAt(0).cloneRange() : kept;
      showBar({ caret: true });
      if (button.isConnected && !button.hidden && !button.disabled) button.focus();
    });
    return button;
  };
  const isLink = (node) => node.nodeName === "A";
  const isColour = (node) => Boolean(node.dataset?.colour || (node.nodeName === "FONT" && node.getAttribute("color")) || node.style?.color);
  // The range made all of one piece of the outermost element round it that `strip` takes
  // (a colour, a link), by cutting that element at the range's ends, and then out of it.
  const splitOut = (range, strip) => {
    let outer = null;
    for (let at = range.commonAncestorContainer; at && at !== area; at = at.parentNode) if (at.nodeType === Node.ELEMENT_NODE && strip(at)) outer = at;
    if (!outer) return;
    const piece = (start, end) => {
      const part = document.createRange();
      part.setStart(...start);
      part.setEnd(...end);
      const words = part.extractContents();
      if (!words.textContent) return null;
      const copy = outer.cloneNode(false);
      copy.append(words);
      return copy;
    };
    const head = piece([outer, 0], [range.startContainer, range.startOffset]);
    const tail = piece([range.endContainer, range.endOffset], [outer, outer.childNodes.length]);
    if (head) outer.before(head);
    if (tail) outer.after(tail);
    const kids = [...outer.childNodes];
    outer.replaceWith(...kids);
    if (kids.length) { range.setStartBefore(kids[0]); range.setEndAfter(kids[kids.length - 1]); }
  };
  // The words chosen (or `given`) taken out of what `strip` takes, round them and in them,
  // and put in what `make` makes of them (nothing: as they are), keeping their look --
  // bold, italic, a colour, a link -- as they had it. Chosen after, unless `choose` is false.
  const wrapChosen = (make, { strip = null, given = null, choose = true } = {}) => {
    const s = selection();
    const range = given || (s.rangeCount && !s.isCollapsed && area.contains(s.anchorNode) ? s.getRangeAt(0) : null);
    if (!range || range.collapsed) return false;
    // A line at a time (a list's items, a paragraph's lines), the last first, so each is
    // where it was when its turn comes: markup has no link, colour or code over a line's end.
    let start = null, end = null;
    for (const piece of linesOf(range).reverse()) {
      if (strip) splitOut(piece, strip);
      const words = piece.extractContents();
      if (strip) for (const node of [...words.querySelectorAll("*")].filter(strip)) node.replaceWith(...node.childNodes);
      if (!words.textContent) { piece.insertNode(words); continue; }
      const node = make ? make(words) : words;
      const first = node.nodeType === Node.DOCUMENT_FRAGMENT_NODE ? node.firstChild : node, last = node.nodeType === Node.DOCUMENT_FRAGMENT_NODE ? node.lastChild : node;
      piece.insertNode(node);
      end ||= [last, make ? last.childNodes.length : null];
      start = [first, 0];
    }
    if (!start) return false;
    const after = document.createRange();
    if (make) after.setStart(...start); else after.setStartBefore(start[0]);
    if (end[1] !== null) after.setEnd(...end); else after.setEndAfter(end[0]);
    if (choose) place(after);
    return after;
  };
  // A range a line each: cut at a list's items and at the line ends in words.
  const linesOf = (range) => {
    const items = [...area.querySelectorAll(".rt-line")].filter((line) => range.intersectsNode(line));
    const spans = items.length > 1 ? items.map((line, k) => {
      const piece = document.createRange();
      piece.selectNodeContents(line);
      if (k === 0) piece.setStart(range.startContainer, range.startOffset);
      if (k === items.length - 1) piece.setEnd(range.endContainer, range.endOffset);
      return piece;
    }) : [range.cloneRange()];
    return spans.flatMap((span) => {
      const pieces = [];
      let from = [span.startContainer, span.startOffset];
      for (const end of [...area.querySelectorAll("br")]) {
        const at = [end.parentNode, [...end.parentNode.childNodes].indexOf(end)];
        if (span.comparePoint(...at) !== 0 || span.comparePoint(at[0], at[1] + 1) !== 0) continue;
        const piece = document.createRange();
        piece.setStart(...from);
        piece.setEnd(...at);
        pieces.push(piece);
        from = [at[0], at[1] + 1];
      }
      const piece = document.createRange();
      piece.setStart(...from);
      piece.setEnd(span.endContainer, span.endOffset);
      pieces.push(piece);
      return pieces.filter((part) => part.toString().length);
    });
  };
  // What holds words as one (code, an equation) has no look inside it: it takes the look
  // all the words chosen had.
  const inTheirLook = (words, node) => {
    const texts = [];
    const walker = document.createTreeWalker(words, NodeFilter.SHOW_TEXT);
    for (let text = walker.nextNode(); text; text = walker.nextNode()) if (text.data.trim()) texts.push(text);
    // What every word chosen has (`find` says it of an element round one, or null).
    const all = (find) => {
      const found = texts.map((text) => { for (let at = text.parentNode; at && at !== words; at = at.parentNode) { const it = find(at); if (it !== null) return it; } return null; });
      return found.length && found.every((it) => it !== null && it === found[0]) ? found[0] : null;
    };
    const weight = (at) => at.style?.fontWeight;
    const bold = all((at) => (weight(at) ? /^bold/.test(weight(at)) || Number(weight(at)) >= 600 : at.nodeName === "B" || at.nodeName === "STRONG" ? true : null)) === true;
    const italic = all((at) => (at.style?.fontStyle ? at.style.fontStyle !== "normal" : at.nodeName === "I" || at.nodeName === "EM" ? true : null)) === true;
    const colour = all((at) => at.dataset?.colour || (at.nodeName === "FONT" && at.getAttribute("color") ? names(at.getAttribute("color")) : null));
    const href = all((at) => (at.nodeName === "A" && at.dataset.href) || null);
    let out = node;
    if (italic) { const i = document.createElement("i"); i.append(out); out = i; }
    if (bold) { const b = document.createElement("b"); b.append(out); out = b; }
    if (colour && colour !== "ink") { const span = colourNode(colour); span.append(out); out = span; }
    if (href) { const a = linkNode(href); a.append(out); out = a; }
    return out;
  };
  const plainNode = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; node.textContent = text; return node; };
  const colourNode = (name) => { const span = document.createElement("span"); span.dataset.colour = name; span.style.color = colours(name); return span; };
  const linkNode = (href) => { const a = document.createElement("a"); a.dataset.href = href; a.title = href; return a; };
  // Words in one of the theme's colours, or (none) in the words' own, as they are drawn.
  const recolour = (name) => wrapChosen(name ? (words) => { const span = colourNode(name); span.append(words); return span; } : null, { strip: isColour });
  const asCode = () => wrapChosen((words) => inTheirLook(words, plainNode("code", "", words.textContent)));
  const asMaths = () => wrapChosen((words) => inTheirLook(words, plainNode("span", "rt-maths", `$${words.textContent}$`)));

  // -- links: ⌘K, or the bar's link button, on words; on a link, its address to change or remove --
  // An address as typed, as a link goes: "example.com/page" a web page's (https://), and
  // "name@example.com" an email's (mailto:); one with its scheme, or a place, as it is.
  const addressOf = (typed) => {
    const text = typed.trim();
    if (!text) return "";
    if (text.startsWith("//")) return `https:${text}`;
    if (/^[a-z][a-z0-9+.-]*:(?!\d)/i.test(text) || /^[#/.?]/.test(text)) return text;
    if (/^[^\s@/]+@[^\s@/]+\.[^\s@/]+$/.test(text)) return `mailto:${text}`;
    return `https://${text}`;
  };
  const linkInput = document.createElement("input");
  linkInput.className = "rt-link";
  linkInput.placeholder = "example.com";
  linkInput.setAttribute("aria-label", "Link address");
  linkInput.spellcheck = false;
  linkInput.hidden = true;
  // The words to link, and the link they are in (to change or remove), if any.
  let linkRange = null, editing = null;
  const outerLink = (node) => { let found = null; for (let at = node; at && at !== area; at = at.parentNode) if (at.nodeName === "A") found = at; return found; };
  // The address typed is applied (or, emptied, the link removed) or set aside; and the
  // keys go back to the words, unless they have gone elsewhere (`back` false).
  const finishLink = (apply, back = true) => {
    if (linkInput.hidden) return;
    linkInput.hidden = true;
    unlinkTool.hidden = true;
    const url = apply ? addressOf(linkInput.value) : "";
    const link = editing?.isConnected ? editing : null, range = linkRange;
    editing = null;
    linkRange = null;
    if (back) { area.focus(); if (range) place(range); }
    if (apply && link) {
      if (url) {
        // One link, never one in another.
        for (const inner of [...link.querySelectorAll("a")]) inner.replaceWith(...inner.childNodes);
        Object.assign(link.dataset, { href: url });
        link.title = url;
      } else unlink(link, back);
      changed(true);
    } else if (apply && url && range && !range.collapsed) {
      if (wrapChosen((words) => { const a = linkNode(url); a.append(words); return a; }, { strip: isLink, given: range, choose: back })) changed(true);
    }
    showBar();
  };
  const unlink = (link, choose = true) => {
    const kids = [...link.childNodes];
    link.replaceWith(...kids);
    if (choose && kids.length) { const range = document.createRange(); range.setStartBefore(kids[0]); range.setEndAfter(kids[kids.length - 1]); place(range); }
  };
  linkInput.addEventListener("keydown", (event) => {
    // Its keys are its own: none reaches the words or the slide.
    event.stopPropagation();
    if (event.key === "Enter" || event.key === "Tab") { event.preventDefault(); finishLink(true); }
    else if (event.key === "Escape") { event.preventDefault(); finishLink(false); }
  });
  // Clicked away from, it applies what was typed, as a Mac link field does.
  linkInput.addEventListener("blur", () => setTimeout(() => { if (!linkInput.hidden && area.isConnected && document.activeElement !== linkInput) finishLink(true, false); }, 0));
  const unlinkTool = tool("Remove", "Remove Link", () => {
    const link = editing?.isConnected ? editing : null;
    linkInput.hidden = true;
    unlinkTool.hidden = true;
    editing = null;
    area.focus();
    if (linkRange) place(linkRange);
    linkRange = null;
    if (!link) return false;
    unlink(link);
    return "words";
  });
  unlinkTool.classList.add("rt-unlink");
  unlinkTool.hidden = true;
  const boldTool = tool("<b>B</b>", "Bold (⌘B)", () => document.execCommand("bold"));
  const italicTool = tool("<i>I</i>", "Italic (⌘I)", () => document.execCommand("italic"));
  function askLink() {
    const s = selection();
    if (!s.rangeCount || !area.contains(s.anchorNode)) return false;
    const range = s.getRangeAt(0);
    // Words in a link, or the caret: that link, its address shown to change or remove.
    const start = outerLink(range.startContainer), end = outerLink(range.endContainer);
    editing = start && start === end ? start : null;
    if (!editing && range.collapsed) return false;
    linkRange = range.cloneRange();
    linkInput.value = editing?.dataset.href || "";
    unlinkTool.hidden = !editing;
    linkInput.hidden = false;
    showBar({ caret: true });
    setTimeout(() => { linkInput.focus(); linkInput.select(); }, 0);
    return false;
  }
  // The words' own colour, as they are drawn here (light on a dark slide), not the ink's.
  const plainTool = palette.ink ? tool(`<span class="rt-swatch" style="background:${palette.ink}"></span>`, "Default colour", () => recolour(null), { words: true }) : "";
  bar.append(
    boldTool,
    italicTool,
    tool("<span style=\"font-family: var(--mono); font-size: 11px\">&lt;/&gt;</span>", "Code (⌘E)", asCode, { words: true }),
    tool("<span style=\"font-family: Georgia, serif\">∑</span>", "Equation: the words chosen as LaTeX (⌥⌘E)", asMaths, { words: true }),
    tool(icon("link"), "Link (⌘K)", () => askLink()),
    ...swatches.map(([name, title]) => tool(`<span class="rt-swatch" style="background:${palette[name]}"></span>`, title, () => recolour(name), { words: true })),
    plainTool,
    linkInput,
    unlinkTool);
  // Along the bar from the keys, as along a Mac toolbar; Esc and Tab go back to the words.
  bar.addEventListener("keydown", (event) => {
    if (event.target === linkInput) return;
    const buttons = [...bar.querySelectorAll("button")].filter((button) => !button.hidden && !button.disabled);
    const at = buttons.indexOf(document.activeElement);
    const go = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: buttons.length - 1 }[event.key];
    if (go !== undefined) { event.preventDefault(); event.stopPropagation(); buttons[Math.max(0, Math.min(buttons.length - 1, go))]?.focus(); return; }
    if (event.key === "Escape" || event.key === "Tab") { event.preventDefault(); event.stopPropagation(); backToWords(); }
    // Space and Return press the button; nothing else of the slide's is done from here.
    else if (event.key === "Enter" || event.key === " ") event.stopPropagation();
  });
  // ⌃Tab from the words: the bar, at the words chosen (at the caret, what needs no words).
  const toBar = () => {
    const s = selection();
    if (!s.rangeCount || !area.contains(s.anchorNode)) return;
    kept = s.getRangeAt(0).cloneRange();
    showBar({ caret: true });
    [...bar.querySelectorAll("button")].find((button) => !button.hidden && !button.disabled)?.focus();
  };
  let seen = false;
  const showBar = ({ caret = false } = {}) => {
    // A field gone from the page (the panel drawn again) takes its bar and listener with it.
    if (!area.isConnected) { if (seen) area.dispose(); return; }
    seen = true;
    const s = selection();
    const inside = s.rangeCount && area.contains(s.anchorNode) && area.contains(s.focusNode);
    // It stays while it has the keys (its buttons) or a link's address is asked for.
    if (!keyed() && linkInput.hidden && !caret && (!inside || s.isCollapsed)) { bar.hidden = true; return; }
    if (!inside) return;
    if (!bar.isConnected) document.body.append(bar);
    boldTool.hidden = boldAlready();
    // Pressed where the words chosen are bold or italic, as a Mac format bar shows.
    boldTool.classList.toggle("on", document.queryCommandState("bold"));
    italicTool.classList.toggle("on", document.queryCommandState("italic"));
    for (const button of bar.querySelectorAll("[data-words]")) button.disabled = s.isCollapsed;
    if (plainTool) plainTool.firstElementChild.style.background = getComputedStyle(area).color || palette.ink;
    bar.hidden = false;
    // Over the thing being edited, never on it (`frame`: a table for its cell), else under
    // it; and in its `room` (the slide's stage), never over the panels beside it.
    const range = s.getRangeAt(0);
    const chosen = range.getClientRects().length ? range.getBoundingClientRect() : (area.closest(".inline-editor, .rich-field") || area).getBoundingClientRect();
    const own = bar.getBoundingClientRect();
    const around = frame?.() || (area.closest(".inline-editor, .rich-field") || area).getBoundingClientRect();
    const bounds = room?.() || { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
    const above = Math.min(chosen.top, around.top) - own.height - 8;
    const top = above > bounds.top + 8 ? above : Math.max(chosen.bottom, around.bottom) + 8;
    const left = Math.max(bounds.left + 8, Math.min(chosen.left + chosen.width / 2 - own.width / 2, bounds.right - own.width - 8));
    Object.assign(bar.style, { top: `${top}px`, left: `${left}px` });
  };
  document.addEventListener("selectionchange", showBar);
  // Whoever closes the field takes its bar with it, and the address being typed is applied.
  // (A field the page has dropped writes nothing more.)
  area.dispose = () => {
    if (area.isConnected) finishLink(true, false); else linkInput.hidden = true;
    bar.remove();
    document.removeEventListener("selectionchange", showBar);
  };

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

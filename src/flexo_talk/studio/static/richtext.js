// Words typed on a slide as the slide shows them: flexo markup (**bold**, *italic*,
// `code`, $maths$, [links](url), [colours]{accent}) shown bold, italic, in the
// monospace and in its colour rather than as marks, and a list as a list -- a bullet
// to each item, items indented by level -- rather than lines of spaces.
//
// richText() makes the field: a contenteditable element whose `value` is the markup
// (for a list, one item a line, two spaces a level, as bulletsText writes it), and
// which says "input" whenever it changes, as a textarea does.

import { icon, toast } from "/static/studio/studio.js";

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
const LIST_MARK = /^(?:[-*+•◦▪‣·–]|\(?\d{1,3}[.)]|\(?[a-z][.)])\s+/i;
function listed(line) {
  const indent = /^[ \t]*/.exec(line)[0].replace(/\t/g, "  ").length;
  return { depth: Math.floor(indent / 2), words: line.trim().replace(LIST_MARK, "") };
}

// Another app's formatted words (text/html) as items: each block -- a paragraph, a
// list's item, a heading, a table's row -- its depth in lists and its words as markup,
// keeping bold, italic, code and links; nothing else of their look.
const BLOCKS_HTML = "address, article, aside, blockquote, center, dd, div, dl, dt, figcaption, figure, footer, h1, h2, h3, h4, h5, h6, header, hr, li, main, nav, ol, p, pre, section, table, tbody, tfoot, thead, tr, ul";
function itemsOfHtml(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  // Word's own bullets and numbers are words in its HTML; the list's levels say them, and
  // its numbers ("1.", "a.", "iv)") that it is numbered, as an <ol> says it.
  const marks = [...doc.querySelectorAll("[style*='mso-list:ignore' i], [style*='mso-list: ignore' i]")].map((node) => {
    const mark = node.textContent.replace(/[\s ]+/g, "");
    const counted = /^\(?(?:\d{1,3}|[a-z]{1,4})[.)]$/i.test(mark);
    const item = node.closest("[style*='mso-list' i]:not([style*='ignore' i])");
    if (item) item.dataset.counted = counted ? "1" : "";
    return counted;
  });
  const numbered = marks.length ? marks.every(Boolean) : Boolean(doc.querySelector("ol")) && !doc.querySelector("ul");
  doc.querySelectorAll("script, style, meta, link, img, svg, title, template, [style*='mso-list:ignore' i], [style*='mso-list: ignore' i]").forEach((node) => node.remove());
  // (A link to a place in the page it came from -- a citation's, "#cite_note-1" -- goes
  // nowhere from a slide: its words come alone.)
  doc.querySelectorAll("a[href]").forEach((link) => { if (!link.getAttribute("href").startsWith("#")) link.dataset.href = link.getAttribute("href"); });
  raised(doc);
  // Headings bold, the way a slide marks them.
  doc.querySelectorAll("h1, h2, h3, h4, h5, h6, th").forEach((node) => { node.style.fontWeight = "700"; });
  doc.querySelectorAll("td + td, td + th, th + td, th + th").forEach((cell) => cell.prepend(" "));
  // Spaces and line ends in the source are one space, as a browser shows them, except
  // in code set out as typed.
  const texts = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  for (let text = texts.nextNode(); text; text = texts.nextNode()) if (!text.parentElement.closest("pre")) text.data = text.data.replace(/[ \t\r\n\f]+/g, " ");
  // The words between one block's edge and the next are an item; an inline wrapper
  // round blocks (Google Docs wraps all it copies in one) is passed through. Each item says
  // whether it is a list's (and an ordered one's), and which block it is a line of.
  const items = [];
  let run = null, depth = 0, inList = false, ordered = false, block = 0, afterBlock = false, inBlock = false;
  // A block's words lose the spaces at its edges; words copied out of the middle of a line
  // (no block round them) keep theirs, as they go in among other words.
  const flush = (atBlock = true) => {
    if (!run) return;
    let markup = serialise(run, lookOf(run, { bold: false, italic: false })).replace(/ /g, " ").replace(/\n$/, "");
    const lone = !markup.trim() && !run.querySelector("br");
    if (inBlock || afterBlock) markup = markup.replace(/^\s+/, "");
    if (inBlock || atBlock) markup = markup.replace(/\s+$/, "");
    run = null;
    if (lone) return;
    block += 1;
    // Its lines lose the spaces about their line ends.
    const parts = markup.split("\n");
    parts.forEach((part, n) => {
      const line = n ? part.trimStart() : part;
      items.push({ depth, markup: n < parts.length - 1 ? line.trimEnd() : line, listed: inList, ordered, block });
    });
  };
  // (`look`: the bold and italic of the blocks it is in -- a heading's -- which its words,
  // taken out of it into an item, keep; `list`, the kind of list round it.)
  const walk = (node, lists, look, list = null) => {
    for (const child of [...node.childNodes]) {
      const element = child.nodeType === Node.ELEMENT_NODE;
      if (element && (child.matches(BLOCKS_HTML) || child.querySelector(BLOCKS_HTML))) {
        flush();
        if (child.matches(BLOCKS_HTML)) afterBlock = true;
        // Word's list items are paragraphs, each saying its level ("mso-list:l0 level2 lfo1").
        const word = /mso-list:\s*l\d+\s+level(\d+)/i.exec(child.getAttribute("style") || "");
        const kind = word ? (child.dataset.counted ? "ol" : "ul") : child.matches("ol, ul") ? child.nodeName.toLowerCase() : list;
        walk(child, word ? Number(word[1]) : lists + (child.matches("ul, ol") ? 1 : 0), lookOf(child, look), kind);
        flush();
        continue;
      }
      if (!run) {
        if (!child.textContent && !(element && (child.nodeName === "BR" || child.querySelector("br")))) continue;
        run = doc.createElement("span");
        if (look.bold) run.style.fontWeight = "700";
        if (look.italic) run.style.fontStyle = "italic";
        depth = Math.max(0, lists - 1);
        inList = lists > 0;
        ordered = list === "ol";
        inBlock = node !== doc.body && node.matches(BLOCKS_HTML);
      }
      run.append(child);
    }
  };
  walk(doc.body, 0, { bold: false, italic: false });
  flush(false);
  // Blank lines one at a time, and none at either end.
  const kept = items.filter((item, n) => item.markup.trim() || (n && items[n - 1].markup.trim()));
  while (kept.length && !kept[kept.length - 1].markup.trim()) kept.pop();
  while (kept.length && !kept[0].markup.trim()) kept.shift();
  kept.numbered = numbered;
  return kept;
}

// Raised and lowered words in another app's HTML (x², 10⁻³, H₂O, a citation's [1]) in the
// letters Unicode raises and lowers, where it has one for each of theirs -- as the slide has
// no superscript of its own -- rather than set on the line.
const RAISED = Object.fromEntries([..."0123456789+-−=()[]abcdefghijklmnoprstuvwxyz"].map((letter, n) => [letter, [..."⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ"][n]]));
const LOWERED = Object.fromEntries([..."0123456789+-−=()[]aehijklmnoprstuvx"].map((letter, n) => [letter, [..."₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"][n]]));
function raised(doc) {
  for (const node of doc.querySelectorAll("sup, sub")) {
    const table = node.nodeName === "SUP" ? RAISED : LOWERED, words = node.textContent.trim();
    if (words && [...words].every((letter) => table[letter])) node.replaceWith([...words].map((letter) => table[letter]).join(""));
  }
}

// A range of cells copied from a spreadsheet (Numbers, Excel and Google Sheets put a
// <table> and its rows as lines of tab-separated cells on the clipboard): its rows of
// cells as markup, each row as long as the longest; else null. Words with a tab in them
// alone are a range only over two lines or more.
function cellsOf(html, text) {
  let rows = null;
  if (html && /<table[\s>]/i.test(html)) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    doc.querySelectorAll("script, style, meta, link, title, template").forEach((node) => node.remove());
    doc.querySelectorAll("a[href]").forEach((link) => { link.dataset.href = link.getAttribute("href"); });
    const table = doc.querySelector("table");
    rows = [...table.rows].map((row) => [...row.cells].map((cell) => {
      const texts = doc.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
      for (let node = texts.nextNode(); node; node = texts.nextNode()) node.data = node.data.replace(/[ \t\r\n\f]+/g, " ");
      return serialise(cell, { bold: false, italic: false }).replace(/\u00a0/g, " ").replace(/\s*\n\s*/g, " ").trim();
    }));
  } else if (text && text.includes("\t")) {
    const lines = text.replace(/\r\n?/g, "\n").replace(/\n$/, "").split("\n");
    // (Tabs only at the lines' starts are an outline's indents, not cells.)
    if (lines.length > 1 && lines.every((line) => line.includes("\t")) && lines.some((line) => /[^\t]\t/.test(line))) rows = lines.map((line) => line.split("\t").map((cell) => escaped(cell.trim())));
  }
  if (!rows?.length) return null;
  const columns = Math.max(...rows.map((row) => row.length));
  if (rows.length * columns < 2) return null;
  return rows.map((row) => [...row, ...Array(columns - row.length).fill("")]);
}

// Words that are one web address (or an email's), as pasted: the link they make, its
// words the address as it was, as Pages and Keynote make one; else null.
function linkOfWords(text) {
  const words = String(text ?? "").trim();
  // A bare e-mail address too, as a mailto: link.
  const mail = /^[^\s@<>()[\]:;,"]+@[^\s@<>()[\]:;,"]+\.[a-z]{2,}$/i.test(words);
  if (!mail && !/^(?:https?:\/\/|ftp:\/\/|mailto:|www\.)[^\s<>"]+$/i.test(words)) return null;
  const href = mail ? `mailto:${words}` : /^www\./i.test(words) ? `https://${words}` : words;
  return `[${escaped(words, true)}](${address(href)})`;
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
      else { node.dataset.colour = coloured[2]; node.style.color = colours(coloured[2]); node.style.setProperty("--rt-colour", node.style.color); }
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

// A node's own look: bold or italic as its tag or its style says (a weight or slant set
// in its style is its own, even on a <b>: Google Docs wraps all it copies in a <b> of
// normal weight), else as `style`, the look it is in.
function lookOf(node, style) {
  const tag = node.nodeName, css = node.style || {};
  return {
    bold: css.fontWeight ? /^bold/.test(css.fontWeight) || Number(css.fontWeight) >= 600 : style.bold || tag === "B" || tag === "STRONG",
    italic: css.fontStyle ? css.fontStyle !== "normal" : style.italic || tag === "I" || tag === "EM",
  };
}
const colourOf = (node, names) => node.dataset?.colour || (node.nodeName === "FONT" && node.getAttribute("color") ? names(node.getAttribute("color")) : null);

// Code or an equation: words held as one, with no look of their own inside.
const isAtom = (node) => node?.nodeType === Node.ELEMENT_NODE && (node.nodeName === "CODE" || node.classList.contains("rt-maths"));

// Code as markup: in backticks, a backtick in it escaped (deck.py reads \` in code as one).
const codeMarkup = (text) => `\`${text.replace(/\u00a0/g, " ").replace(/`/g, "\\`")}\``;

// The look of the words in code or an equation, a format applied after it was made having
// gone inside it: what all of them have, which the slide gives the whole -- bold, italic,
// a colour, a link.
function atomLook(node, style, names) {
  const texts = [];
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
  for (let text = walker.nextNode(); text; text = walker.nextNode()) if (text.data.trim()) texts.push(text);
  const each = (find) => texts.map((text) => { for (let at = text.parentNode; at && at !== node; at = at.parentNode) { const it = find(at); if (it) return it; } return null; });
  const all = (find) => { const found = each(find); return found.length && found.every((it) => it && it === found[0]) ? found[0] : null; };
  const plain = { bold: false, italic: false };
  return {
    bold: style.bold || Boolean(all((at) => (lookOf(at, plain).bold ? "yes" : null))),
    italic: style.italic || Boolean(all((at) => (lookOf(at, plain).italic ? "yes" : null))),
    colour: all((at) => colourOf(at, names)),
    href: all((at) => (at.nodeName === "A" && at.dataset.href) || null),
  };
}

// The runs a node holds: words with their emphasis, or markup kept as written (maths,
// code, a link, a colour).
function runsOf(node, style, runs, names, inside = false) {
  for (const child of node.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) { runs.push({ text: child.data.replace(/\u00a0/g, " "), ...style, inside }); continue; }
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    const tag = child.nodeName;
    if (tag === "BR") { runs.push({ text: "\n", ...style }); continue; }
    // Maths keeps the emphasis it is in, as the slide reads it; so does code.
    if (isAtom(child)) {
      const look = atomLook(child, tag === "CODE" ? lookOf(child, style) : style, names);
      let raw = tag === "CODE" ? codeMarkup(child.textContent) : child.textContent;
      if (look.colour && look.colour !== "ink") raw = `[${raw}]{${look.colour}}`;
      if (look.href) raw = `[${raw}](${address(look.href)})`;
      runs.push({ raw, bold: look.bold, italic: look.italic, wrap: true });
      continue;
    }
    const next = lookOf(child, style);
    const colour = colourOf(child, names);
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

// An element as copies of it a line each, and the line ends ("\n") between them: its line
// breaks, and the "\n" a field that keeps its spaces types for one (a Return at a colour's
// or a link's edge, typed in it).
function byLine(element) {
  const own = element.cloneNode(true);
  const typed = [];
  const walker = document.createTreeWalker(own, NodeFilter.SHOW_TEXT);
  for (let text = walker.nextNode(); text; text = walker.nextNode()) if (text.data.includes("\n")) typed.push(text);
  for (const text of typed) text.replaceWith(...text.data.split("\n").flatMap((part, n) => [...(n ? [document.createElement("br")] : []), ...(part ? [document.createTextNode(part)] : [])]));
  if (!own.querySelector("br")) return [element];
  const parts = [];
  const rest = own;
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

// Lines of markup all made bold (`look` "bold") or italic -- or, every word so already,
// none: ⌘B on a text chosen whole, as Keynote's does to a text box chosen.
function emphasised(lines, look) {
  const tags = look === "bold" ? /^(B|STRONG)$/ : /^(I|EM)$/;
  const holders = lines.map((markup) => { const holder = document.createElement("div"); holder.append(...inlineNodes(markup, () => "")); return holder; });
  const inLook = (text, holder) => { for (let at = text.parentNode; at && at !== holder; at = at.parentNode) if (tags.test(at.nodeName)) return true; return false; };
  const all = holders.every((holder) => {
    const walker = document.createTreeWalker(holder, NodeFilter.SHOW_TEXT);
    for (let text = walker.nextNode(); text; text = walker.nextNode()) if (text.data.trim() && !inLook(text, holder)) return false;
    return true;
  });
  return holders.map((holder) => {
    for (const node of [...holder.querySelectorAll("*")].filter((node) => tags.test(node.nodeName))) node.replaceWith(...node.childNodes);
    if (!all && holder.textContent.trim()) { const wrap = document.createElement(look === "bold" ? "b" : "i"); wrap.append(...holder.childNodes); holder.append(wrap); }
    return serialise(holder);
  });
}

// -- the field -------------------------------------------------------------------------

// A line break within a list's item, in the list's words (one item a line): the Unicode
// line separator, which no one types.
export const ITEM_BREAK = "\u2028";

// Whether two colours, however written ("#1a5d9b", "rgb(26, 93, 155)"), are one.
const pen = document.createElement("canvas").getContext("2d");
const colourAs = (colour) => { pen.fillStyle = "#010203"; pen.fillStyle = String(colour ?? ""); return pen.fillStyle; };
const sameColour = (a, b) => Boolean(a && b) && colourAs(a) === colourAs(b) && colourAs(a) !== "#010203";

// `list` makes it a list (Tab and ⇧Tab change an item's level, Return starts the next
// item, ⇧Return a new line in the item, Return on an empty item moves it out a level;
// `numbered` numbers it, and `plain` has no marks, its levels kept); `single` a line of its
// own (Return is left to whoever holds it); else words in lines, Return starting a new one,
// as in Keynote -- or, `breakWith` "shift" (a table's cell), ⇧Return or ⌥Return, Return
// left to whoever holds it. ⌘Return is always theirs: it ends the typing. `palette` gives the
// theme's colours by name, for [words]{accent}. `onCells` takes a spreadsheet's cells
// pasted in it; `docked` keeps its format bar under it (a panel's field); `onEnd(kept)` goes on
// after a list ended by Return on an empty item (`kept`: how many items stay before the
// ones after it, if any); `onListStart(style, unmark)` is
// asked for a list ("numbered", "bulleted") by the marks typed at the words' start;
// `onList(items, split)` takes an outline or a list pasted in words (each item's depth, markup
// and whether it was numbered; `split`: the words before the caret and after it, as markup --
// so too `onCells(cells, split)`, but for a list's or one line's).
// A list's `value` holds a line break within an item as ITEM_BREAK, its items being its lines.
// `clear(rect)`: how much of what the slide shows round the words a rect over it would cover,
// as an area (its format bar is put where it covers least: see `overlap`).
// How much of `one` (a box: left, top, right, bottom) `other` covers, as an area.
export function overlap(one, other) {
  return Math.max(0, Math.min(one.right, other.right) - Math.max(one.left, other.left)) * Math.max(0, Math.min(one.bottom, other.bottom) - Math.max(one.top, other.top));
}

export function richText({ value = "", list = false, single = false, breakWith = "return", numbered = false, plain = false, palette = {}, placeholder = "", spelling = true, leaveOnTab = false, frame = null, room = null, clear = null, onCells = null, docked = false, onEnd = null, onListStart = null, onList = null } = {}) {
  const area = document.createElement("div");
  area.className = `rich${list ? " rt-list" : ""}${numbered ? " rt-numbered" : ""}${plain ? " rt-plain" : ""}`;
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
    line.append(...inlineNodes(words.replaceAll(ITEM_BREAK, "\n"), colours));
    // A line break in an item is the "\n" ⇧Return types in it, as the field keeps its
    // spaces: its letters counted as typed ones are (a <br> in an item only holds its place).
    for (const end of line.querySelectorAll("br")) end.replaceWith("\n");
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
    if (list) return lines().map((line) => "  ".repeat(Number(line.dataset.level) || 0) + strip(serialise(line, undefined, names)).replace(/\n/g, ITEM_BREAK)).join("\n");
    const text = strip(serialise(area, undefined, names));
    return single ? text.replace(/\n/g, " ") : text;
  };
  const write = (text) => {
    area.replaceChildren();
    if (list) {
      for (const raw of String(text ?? "").split("\n")) {
        const indent = /^[ \t]*/.exec(raw)[0].replace(/\t/g, "  ").length;
        // Only the indent goes: a space just typed at an item's end stays (a list written
        // again under the typing, as another's change comes in).
        area.append(lineNode(Math.floor(indent / 2), raw.replace(/^[ \t]*/, "")));
      }
      if (!area.children.length) area.append(lineNode(0, ""));
    } else area.append(...inlineNodes(String(text ?? ""), colours));
    area.classList.toggle("rt-empty", !String(text ?? "").trim());
  };
  write(value);
  Object.defineProperty(area, "value", { get: read, set: (text) => rewrite(text) });
  area.rich = true;
  // A change of look (bold, a colour, a link) or a paste says it is a step of its own, for
  // the history: typing runs together, these do not (a native ⌘B says so by its inputType).
  // (`label` names it in the history, when it is a step of its own: "Paste Text".)
  const changed = (step = false, label = null) => area.dispatchEvent(new CustomEvent("input", { bubbles: true, detail: { step, label } }));
  // (Its own name for it: a page's .empty is a panel's note that it has nothing, centred.)
  area.addEventListener("input", () => area.classList.toggle("rt-empty", !area.textContent.trim() && !area.querySelector(".rt-line + .rt-line")));
  // The look the browser keeps of words it deleted, for what is typed next (code's face and
  // tint: <font face>, a span's size and background), is no look the slide has: it goes,
  // the words typed staying words.
  const scrub = () => {
    const strays = [...area.querySelectorAll("font, span:not([data-colour]):not(.rt-maths)")];
    if (!strays.length) return;
    const caret = document.activeElement === area ? area.caretAt() : null;
    for (const node of strays) {
      node.removeAttribute("face");
      node.removeAttribute("size");
      for (const name of ["font-family", "font-size", "background", "background-color"]) node.style?.removeProperty(name);
      if (node.nodeName === "SPAN" ? !node.getAttribute("style") : !node.attributes.length) node.replaceWith(...node.childNodes);
    }
    if (caret) area.caretTo(...caret);
  };
  area.addEventListener("input", scrub);
  // "1. ", "- " or "• " typed at the start of a list's item (of the words, in a text) asks for
  // a list of that kind, as Pages and Keynote make one; whoever holds the field takes the
  // marks away (`unmark`) as it makes it.
  area.addEventListener("input", (event) => {
    if (!onListStart || event.inputType !== "insertText" || event.data !== " ") return;
    const s = getSelection();
    if (!s.rangeCount || !s.isCollapsed || !area.contains(s.anchorNode) || atomAt(s.anchorNode)) return;
    const caret = area.caretAt()?.[0], letters = area.letters();
    if (caret === undefined) return;
    const start = list ? letters.lastIndexOf("\n", caret - 1) + 1 : 0;
    const typed = letters.slice(start, caret);
    const style = /^1[.)] $/.test(typed) ? "numbered" : /^[-*•–] $/.test(typed) ? "bulleted" : null;
    if (!style) return;
    setTimeout(() => {
      if (area.letters().slice(start, start + typed.length) !== typed) return;
      onListStart(style, () => {
        const from = pointAt(start), to = pointAt(start + typed.length);
        if (!from || !to) return;
        const marks = document.createRange();
        marks.setStart(...from);
        marks.setEnd(...to);
        marks.deleteContents();
        area.caretTo(start);
      });
    }, 0);
  });
  // Maths typed as it is written, between $ signs, becomes an equation as its closing $ is
  // typed (as Pages makes one of it): a step of its own after the typing, so ⌘Z gives the
  // dollars back. What flexo reads as no maths -- a price, "$5 and $10" -- stays words.
  area.addEventListener("input", (event) => {
    if (event.inputType !== "insertText" || event.data !== "$") return;
    // (Its words one run of letters, however they were typed: the $ of a $$ before it is seen.)
    area.normalize();
    const s = getSelection();
    const text = s.rangeCount && s.isCollapsed ? s.anchorNode : null;
    if (text?.nodeType !== Node.TEXT_NODE || !area.contains(text) || atomAt(text)) return;
    const end = s.anchorOffset;
    // (Read as flexo reads it, the letter after it no digit: none is typed yet.)
    const span = mathSpans(`${text.data.slice(0, end)} `).find(([, close]) => close === end);
    // (Not the inner pair of $$...$$ as its first closing $ is typed.)
    if (!span || text.data[span[0] - 1] === "$") return;
    const source = text.data.slice(span[0], end);
    setTimeout(() => {
      if (!text.isConnected || text.data.slice(span[0], end) !== source) return;
      // (Its letters are the same: the caret stays by them, wherever typing has taken it.)
      const caret = document.activeElement === area ? area.caretAt() : null;
      const range = document.createRange();
      range.setStart(text, span[0]);
      range.setEnd(text, end);
      range.deleteContents();
      range.insertNode(plainNode("span", "rt-maths", source));
      if (caret) area.caretTo(...caret);
      changed(true);
    }, 0);
  });
  // Only the look the slide keeps is offered: bold and italic, not underline and the like
  // (a menu's or the system's), which saving would drop.
  area.addEventListener("beforeinput", (event) => {
    if (/^format/.test(event.inputType) && !["formatBold", "formatItalic"].includes(event.inputType)) event.preventDefault();
    // A line of its own takes no second line, however asked for (⌃O, a menu); a list's item
    // one only as ⇧Return makes it (lineBreak), not as the browser would.
    if (single && /^insert(LineBreak|Paragraph)$/.test(event.inputType)) event.preventDefault();
    if (list && event.inputType === "insertLineBreak" && !breaking) event.preventDefault();
    if (overAtoms(event)) return;
    // Typing at a link's end goes on after it, as in Pages and Keynote: a link ends where it
    // ends (the caret in its last letters or just past it, where the browser would type in it);
    // so does code's, and an equation's, words held as one.
    const s = getSelection();
    if (event.inputType !== "insertText" || !event.data || !s.rangeCount || !s.isCollapsed || !area.contains(s.anchorNode)) return;
    let leaf = s.anchorNode;
    if (leaf.nodeType === Node.TEXT_NODE) { if (s.anchorOffset < leaf.data.length) return; }
    else { leaf = leaf.childNodes[s.anchorOffset - 1] || null; while (leaf?.lastChild) leaf = leaf.lastChild; }
    const link = leaf ? outerLink(leaf) || atomAt(leaf) : null;
    if (!link) return;
    const rest = document.createRange();
    rest.setStartAfter(leaf);
    rest.setEnd(link, link.childNodes.length);
    if (rest.toString()) return;
    event.preventDefault();
    let after = link.nextSibling;
    if (after?.nodeType !== Node.TEXT_NODE) { after = document.createTextNode(""); link.after(after); }
    after.insertData(0, event.data);
    const caret = document.createRange();
    caret.setStart(after, event.data.length);
    place(caret);
    area.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: event.data }));
  });

  // Words chosen over code or an equation (all of one, or across its edge), typed over or
  // deleted: what is typed is words of its own, never in the emptied equation, and the
  // browser keeps no look of what went (see scrub). Whether it was done here.
  const overAtoms = (event) => {
    const typing = event.inputType === "insertText" && event.data;
    if (!typing && !/^delete(Content|Word|SoftLine|HardLine)/.test(event.inputType)) return false;
    const s = getSelection();
    if (!s.rangeCount || !area.contains(s.anchorNode)) return false;
    const range = s.getRangeAt(0);
    const head = atomAt(range.startContainer), tail = atomAt(range.endContainer);
    const atoms = [...area.querySelectorAll("code, .rt-maths")].filter((atom) => range.intersectsNode(atom));
    const emptied = range.collapsed && head && !head.textContent;
    if (!emptied && (range.collapsed || !atoms.length || (head && head === tail && range.toString() !== head.textContent))) return false;
    if (!typing && range.collapsed) return false;
    event.preventDefault();
    // Deleted as the browser deletes (lines joined as it joins them), then what it emptied goes.
    if (!range.collapsed) document.execCommand("delete");
    for (const atom of [...area.querySelectorAll("code, .rt-maths")]) if (!atom.textContent) atom.remove();
    if (typing) {
      const at = getSelection().getRangeAt(0);
      let text = at.startContainer;
      const offset = at.startOffset;
      if (text.nodeType === Node.TEXT_NODE) text.insertData(offset, event.data);
      else { text = document.createTextNode(event.data); at.insertNode(text); }
      // (The break an emptied line held its place with is no longer needed.)
      if (text.nextSibling?.nodeName === "BR" && !text.nextSibling.nextSibling) text.nextSibling.remove();
      const caret = document.createRange();
      caret.setStart(text, text === at.startContainer ? offset + event.data.length : event.data.length);
      place(caret);
      area.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: event.inputType, data: event.data }));
    } else scrub();
    return true;
  };

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

  // Words drawn bold (a title, a statement) are bold already: the markup has no "not bold"
  // to give them, and their own bold words are drawn in the accent (compose.py), not bolder.
  const boldAlready = () => Number(getComputedStyle(area).fontWeight) >= 600;
  // So in them Bold is made and unmade as the markup's (<b>), not by the browser, which sees
  // all of them bold already and would make them light. Pressed where all the words chosen are.
  const inBold = (node) => { for (let at = node; at && at !== area; at = at.parentNode) if (at.nodeName === "B" || at.nodeName === "STRONG") return true; return false; };
  const allBold = () => {
    const s = selection();
    if (!s.rangeCount || !area.contains(s.anchorNode)) return false;
    const range = s.getRangeAt(0);
    if (range.collapsed) return inBold(range.startContainer);
    const walker = document.createTreeWalker(range.commonAncestorContainer, NodeFilter.SHOW_TEXT);
    const texts = [];
    for (let text = walker.currentNode.nodeType === Node.TEXT_NODE ? walker.currentNode : walker.nextNode(); text; text = walker.nextNode()) if (range.intersectsNode(text) && text.data.trim()) texts.push(text);
    return texts.length > 0 && texts.every(inBold);
  };
  const boldInBold = () => {
    const strong = (words) => { const b = document.createElement("b"); b.append(words); return b; };
    if (wrapChosen(allBold() ? null : strong, { strip: (node) => node.nodeName === "B" || node.nodeName === "STRONG" })) changed(true);
    showBar();
  };
  // A panel's list come to by Tab is passed by Tab (⇧Tab back), as any field is: its levels
  // change once the caret is put in an item -- clicked, or moved by the keys. Esc, then
  // Tab, goes on from anywhere in it (a second Esc leaves it).
  let passing = false, pointed = false;
  if (leaveOnTab && list) {
    area.addEventListener("mousedown", () => { pointed = true; passing = false; });
    area.addEventListener("focus", () => { passing = !pointed; pointed = false; });
  }
  area.addEventListener("keydown", (event) => {
    const mod = event.metaKey || event.ctrlKey;
    if (leaveOnTab && list) {
      if (event.key === "Escape" && !passing) { passing = true; event.preventDefault(); event.stopImmediatePropagation(); return; }
      if (event.key === "Tab" && passing && !event.ctrlKey) return;
      if (!["Tab", "Escape", "Shift", "Meta", "Control", "Alt", "CapsLock"].includes(event.key)) passing = false;
    }
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
    // No underline: the slide has none to keep -- said, not swallowed without a word.
    if (mod && !event.altKey && (event.code === "KeyU" || event.key.toLowerCase() === "u")) {
      event.preventDefault();
      toast("Slides have no underline: use bold, italic or a colour to make words stand out.", { icon: "info", seconds: 3 });
      return;
    }
    if (mod && !event.altKey && ["b", "i"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      format(event.key.toLowerCase() === "b" ? "bold" : "italic");
      return;
    }
    // (A step of its own, named as what it did, as Pages names one: not typing.)
    if (event.key === "Tab" && list) {
      event.preventDefault();
      const was = read();
      for (const line of chosenLines()) setLevel(line, Number(line.dataset.level) + (event.shiftKey ? -1 : 1));
      if (read() !== was) changed(true, event.shiftKey ? "Outdent" : "Indent");
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
    // ⌘Return ends the typing, wherever it is: whoever holds the field ends it.
    if (mod) { event.preventDefault(); return; }
    // One line (a number): no line break, which it would not keep.
    if (single) { event.preventDefault(); return; }
    // ⇧Return (or ⌥Return) is a new line in a list's item, or a table's cell, whose Return
    // is another's: the next item, the cell below.
    const within = event.shiftKey || event.altKey;
    if (breakWith === "shift" && !within) return;
    event.preventDefault();
    if (!list || within) { lineBreak(); return; }
    // Return ends an item and starts the next at its level; on an empty item, it moves out a level.
    const s = selection();
    if (!s.rangeCount) return;
    if (!s.isCollapsed) s.deleteFromDocument();
    const line = lineAt(s.anchorNode);
    if (!line) return;
    const level = Number(line.dataset.level) || 0;
    if (!line.textContent.trim() && level > 0) { line.dataset.level = String(level - 1); changed(); return; }
    // On an empty last item, the list ends, as in Pages: the item goes, and whoever holds the
    // field goes on after it (`onEnd`: a paragraph after the list).
    if (!line.textContent.trim() && !line.nextElementSibling && line.previousElementSibling && onEnd) { line.remove(); changed(); onEnd(); return; }
    // Amid others, it ends there too: the item goes, and the items after it are a list of
    // their own after the paragraph that follows (`onEnd(kept)`: how many items stay).
    if (!line.textContent.trim() && line.nextElementSibling && line.previousElementSibling && onEnd) {
      const kept = lines().indexOf(line);
      line.remove();
      changed();
      onEnd(kept);
      return;
    }
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

  // A new line where the caret is: never in code or an equation, held as one (after it), nor
  // inside a link or a colour at its edge -- before or after it, so its markup stays whole.
  let breaking = false;
  const lineBreak = () => {
    const s = selection();
    if (!s.rangeCount || !area.contains(s.anchorNode)) return;
    const out = s.isCollapsed ? outOfEdge(s.getRangeAt(0)) : null;
    if (out) {
      // Beside it, the new line is put there by hand, as typing at a link's end is: the
      // browser's would go back into it (and its placeholder with it), and the first letter
      // typed after would be the link's. At the words' end, a second stands for the empty
      // line the caret goes to, as the browser's does (the typing's end takes it away).
      const node = document.createTextNode("\n");
      out.insertNode(node);
      const rest = document.createRange();
      rest.setStartAfter(node);
      rest.setEnd(area, area.childNodes.length);
      if (!rest.toString()) node.appendData("\n");
      const caret = document.createRange();
      caret.setStart(node, 1);
      place(caret);
      area.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertLineBreak" }));
      return;
    }
    breaking = true;
    try { document.execCommand("insertLineBreak"); } finally { breaking = false; }
  };
  // Where a caret at the edge of a link (or, `colours`, a colour) it is in goes to be beside it
  // rather than in it, or out of code or an equation it is in; null if it stays.
  const outOfEdge = (range, { colours = true } = {}) => {
    let outer = null;
    for (let at = range.startContainer; at && at !== area; at = at.parentNode) if (at.nodeType === Node.ELEMENT_NODE && (isLink(at) || (colours && isColour(at)))) outer = at;
    for (const holder of [atomAt(range.startContainer), outer]) {
      if (!holder) continue;
      const side = (from, to) => { const part = document.createRange(); part.setStart(...from); part.setEnd(...to); return part.toString(); };
      const here = [range.startContainer, range.startOffset];
      const out = document.createRange();
      if (!side([holder, 0], here)) out.setStartBefore(holder);
      else if (!side(here, [holder, holder.childNodes.length]) || isAtom(holder)) out.setStartAfter(holder);
      else continue;
      out.collapse(true);
      return out;
    }
    return null;
  };

  // -- the format bar: over the words chosen, as a Mac text view's touch bar offers them --
  // From the keys: ⌃Tab goes to it from the words (as ⌃Tab leaves a Mac text view for the
  // next control), ← and → go along it, Space or Return presses a button, and Esc or Tab
  // goes back to the words; ⌘E makes the words code and ⌥⌘E an equation (as Pages inserts one).
  // Each colour offered once: one that looks as another does (a theme's accent its ink, as
  // Swiss's is) is left to that one -- the default's dot, or the first of that colour.
  const offered = new Set([String(palette.ink || "").toLowerCase()]);
  const swatches = [["accent", "Accent"], ["accent2", "Accent 2"], ["muted", "Muted"]].filter(([name]) => {
    const colour = String(palette[name] || "").toLowerCase();
    if (!colour || offered.has(colour)) return false;
    offered.add(colour);
    return true;
  });
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
    const chosen = given || (s.rangeCount && !s.isCollapsed && area.contains(s.anchorNode) ? s.getRangeAt(0) : null);
    if (!chosen || chosen.collapsed) return false;
    const range = settled(chosen);
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
  const colourNode = (name) => { const span = document.createElement("span"); span.dataset.colour = name; span.style.color = colours(name); span.style.setProperty("--rt-colour", span.style.color); return span; };
  const linkNode = (href) => { const a = document.createElement("a"); a.dataset.href = href; a.title = href; return a; };
  // Words in one of the theme's colours, or (none) in the words' own, as they are drawn.
  const recolour = (name) => wrapChosen(name ? (words) => { const span = colourNode(name); span.append(words); return span; } : null, { strip: isColour });
  // -- code and equations: words held as one --
  // The code or equation round a point in the words, if any.
  const atomAt = (node) => { for (let at = node; at && at !== area; at = at.parentNode) if (isAtom(at)) return at; return null; };
  // A range as a look is given to it: its ends on the words chosen, not before an element
  // round them (so a link the words start is not cut in two), and code or an equation
  // it is in taken whole -- its look is the whole one's, given round it, not inside.
  const onWords = (range) => {
    const out = range.cloneRange();
    let first = null, last = null;
    const walker = document.createTreeWalker(area, NodeFilter.SHOW_TEXT);
    for (let text = walker.nextNode(); text; text = walker.nextNode()) {
      if (!range.intersectsNode(text)) continue;
      const from = text === range.startContainer ? range.startOffset : 0, to = text === range.endContainer ? range.endOffset : text.data.length;
      if (to <= from) continue;
      first ||= [text, from];
      last = [text, to];
    }
    if (first) { out.setStart(...first); out.setEnd(...last); }
    return out;
  };
  const settled = (range) => {
    const out = onWords(range);
    const head = atomAt(out.startContainer), tail = atomAt(out.endContainer);
    if (head) out.setStartBefore(head);
    if (tail) out.setEndAfter(tail);
    return out;
  };
  // Bold or italic (⌘B, ⌘I) on words that are code or an equation: on the whole of it.
  const format = (command) => {
    if (command === "bold" && boldAlready()) { boldInBold(); return; }
    const s = selection();
    const range = s.rangeCount && !s.isCollapsed && area.contains(s.anchorNode) ? s.getRangeAt(0) : null;
    if (range && (atomAt(range.startContainer) || atomAt(range.endContainer))) place(settled(range));
    document.execCommand(command);
  };
  // An equation's LaTeX without its marks ($...$, $$...$$, \(...\), \[...\]).
  const unmarked = (source) => (/^\$\$([\s\S]*)\$\$$/.exec(source) || /^\\\(([\s\S]*)\\\)$/.exec(source) || /^\\\[([\s\S]*)\\\]$/.exec(source) || /^\$([\s\S]*)\$$/.exec(source))?.[1] ?? source;
  // The words chosen as letters, each equation in them its LaTeX alone (one equation of all).
  const textOfWords = (words, unmark) => {
    const copy = words.cloneNode(true);
    if (unmark) for (const maths of copy.querySelectorAll(".rt-maths")) maths.textContent = unmarked(maths.textContent);
    return copy.textContent;
  };
  // ⌘E makes the words chosen code, ⌥⌘E an equation; again, as ⌘B, words once more: code
  // chosen in part, those words. Code made an equation is that equation, and an equation
  // made code, that code; part of an equation is none of its own.
  const toggleAtom = (kind) => {
    const s = selection();
    if (!s.rangeCount || s.isCollapsed || !area.contains(s.anchorNode)) return false;
    // (The words chosen, wherever the ends of the choice are: round code just made bold.)
    const range = onWords(s.getRangeAt(0));
    const head = atomAt(range.startContainer), atom = head && head === atomAt(range.endContainer) ? head : null;
    if (!atom && kind === "code") return wrapChosen((words) => inTheirLook(words, plainNode("code", "", textOfWords(words, false))));
    // Words chosen with the marks typed round them ($...$, \(...\)) are that equation; the
    // spaces at their ends stay words, outside it.
    if (!atom) {
      const made = [];
      const after = wrapChosen((words) => {
        const all = textOfWords(words, true), source = all.trim();
        if (!source) return words;
        const maths = plainNode("span", "rt-maths", `$${unmarked(source)}$`);
        made.push(maths);
        const out = document.createDocumentFragment();
        out.append(...[/^\s*/.exec(all)[0], inTheirLook(words, maths), /\s*$/.exec(all)[0]].filter((part) => part !== ""));
        return out;
      });
      // The equation chosen, not the spaces beside it: pressed again, it is words once more.
      if (!after || made.length !== 1) return after;
      const chosen = document.createRange();
      chosen.selectNodeContents(made[0]);
      place(chosen);
      return chosen;
    }
    const code = atom.nodeName === "CODE", whole = range.toString() === atom.textContent;
    const source = code ? atom.textContent : unmarked(atom.textContent);
    if (!code && !whole) return false;
    let made = null, parts = [];
    if (kind === (code ? "code" : "maths")) {
      // Words again: all of them, or (in code) those chosen, the rest code either side
      // (the spaces between them words too).
      const side = (start, end) => { const piece = document.createRange(); piece.setStart(...start); piece.setEnd(...end); return piece.toString(); };
      const before = whole ? "" : side([atom, 0], [range.startContainer, range.startOffset]), after = whole ? "" : side([range.endContainer, range.endOffset], [atom, atom.childNodes.length]);
      made = document.createTextNode(whole ? source : range.toString());
      const lead = before.slice(before.trimEnd().length), trail = after.slice(0, after.length - after.trimStart().length);
      parts = [before.trim() && plainNode("code", "", before.trimEnd()), lead, made, trail, after.trim() && plainNode("code", "", after.trimStart())].filter(Boolean);
    } else {
      made = kind === "code" ? plainNode("code", "", source) : plainNode("span", "rt-maths", `$${source}$`);
      parts = [made];
    }
    // The look given inside it (bold, a colour) stays the words'.
    const look = atomLook(atom, { bold: false, italic: false }, names);
    parts = parts.map((part) => (typeof part === "string" ? document.createTextNode(part) : part)).map((part) => {
      let out = wrapped(part, look);
      if (look.colour && look.colour !== "ink") { const span = colourNode(look.colour); span.append(out); out = span; }
      if (look.href) { const a = linkNode(look.href); a.append(out); out = a; }
      return out;
    });
    atom.replaceWith(...parts);
    const after = document.createRange();
    after.selectNodeContents(made);
    place(after);
    return after;
  };
  const asCode = () => toggleAtom("code");
  const asMaths = () => toggleAtom("maths");

  // -- links: ⌘K, or the bar's link button, on words; on a link, its address to change or remove --
  // A scheme known as one, though a number follows it (doi:10.1000/182, tel:+44...), where
  // "example.com:8080" is a web page's address.
  const SCHEMES = /^(?:https?|ftps?|mailto|tel|sms|doi|urn|isbn|geo|file|news|webcal|facetime|maps|zotero|obsidian|slack|zoommtg):/i;
  // An address as typed, as a link goes: "example.com/page" a web page's (https://), and
  // "name@example.com" an email's (mailto:); one with its scheme, or a place, as it is. Not
  // an address (null): words with a space in them, or a script to run (javascript:), which
  // a slide never links to.
  const addressOf = (typed) => {
    let text = typed.trim();
    if (!text) return "";
    if (/^(?:javascript|vbscript|data):/i.test(text.replace(/[\s\u0000-\u001f]+/g, ""))) return null;
    // A telephone number is written with spaces, and linked without them.
    if (/^(?:tel|sms):/i.test(text)) text = text.replace(/\s+/g, "");
    if (/\s/.test(text)) return null;
    if (text.startsWith("//")) return `https:${text}`;
    if (SCHEMES.test(text) || /^[a-z][a-z0-9+.-]*:(?!\d)/i.test(text) || /^[#/.?]/.test(text)) return text;
    if (/^[^\s@/]+@[^\s@/]+\.[^\s@/]+$/.test(text)) return `mailto:${text}`;
    return `https://${text}`;
  };
  const linkInput = document.createElement("input");
  linkInput.className = "rt-link";
  linkInput.placeholder = "example.com";
  linkInput.setAttribute("aria-label", "Link address");
  linkInput.spellcheck = false;
  linkInput.hidden = true;
  // The words to link, and the link they are in (to change or remove), if any; `ofCaret`:
  // the word the caret was in, linked with the caret after it, as Pages leaves it.
  let linkRange = null, editing = null, ofCaret = false;
  const outerLink = (node) => { let found = null; for (let at = node; at && at !== area; at = at.parentNode) if (at.nodeName === "A") found = at; return found; };
  // The address typed is applied (or, emptied, the link removed) or set aside; and the
  // keys go back to the words, unless they have gone elsewhere (`back` false).
  const finishLink = (apply, back = true) => {
    if (linkInput.hidden) return;
    const typed = linkInput.value.trim();
    let url = apply ? addressOf(typed) : "";
    // Not an address: said, and the field kept to put right (clicked away from, set aside).
    if (url === null && back) { linkNote.hidden = false; linkInput.setAttribute("aria-invalid", "true"); linkInput.focus(); return; }
    if (url === null) { url = ""; apply = false; }
    linkInput.hidden = true;
    linkNote.hidden = true;
    linkInput.removeAttribute("aria-invalid");
    unlinkTool.hidden = true;
    markChosen(null);
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
      const linked = wrapChosen((words) => { const a = linkNode(url); a.append(words); return a; }, { strip: isLink, given: range, choose: back && !ofCaret });
      if (linked && back && ofCaret) { const caret = document.createRange(); caret.setStartAfter(outerLink(linked.endContainer) || linked.endContainer); caret.collapse(true); place(caret); }
      if (linked) changed(true);
    } else if (apply && url && range && area.contains(range.startContainer)) {
      // No words chosen: the address typed is the link's words, as in Pages.
      const a = linkNode(url);
      a.textContent = typed;
      range.insertNode(a);
      if (back) { const caret = document.createRange(); caret.setStartAfter(a); caret.collapse(true); place(caret); }
      changed(true);
    }
    showBar();
  };
  const unlink = (link, choose = true) => {
    const kids = [...link.childNodes];
    link.replaceWith(...kids);
    if (choose && kids.length) { const range = document.createRange(); range.setStartBefore(kids[0]); range.setEndAfter(kids[kids.length - 1]); place(range); }
  };
  // The words a link is made of stay marked as chosen while its address is typed (the
  // keys, and with them the page's selection, are in the address field).
  const marking = typeof Highlight === "function" && Boolean(CSS.highlights);
  const markChosen = (range) => {
    if (!marking) return;
    if (range && !range.collapsed && area.contains(range.startContainer)) CSS.highlights.set("rt-chosen", new Highlight(range));
    else CSS.highlights.delete("rt-chosen");
  };
  const linkNote = document.createElement("span");
  linkNote.className = "rt-link-note";
  linkNote.textContent = "Not a link address";
  linkNote.hidden = true;
  linkInput.addEventListener("input", () => { linkNote.hidden = true; linkInput.removeAttribute("aria-invalid"); });
  linkInput.addEventListener("keydown", (event) => {
    // Its keys are its own: none reaches the words or the slide.
    event.stopPropagation();
    // Tab goes on to Remove, when the link has one; from there, back to the words.
    if (event.key === "Tab" && !event.shiftKey && !unlinkTool.hidden) { event.preventDefault(); unlinkTool.focus(); }
    else if (event.key === "Enter" || event.key === "Tab") { event.preventDefault(); finishLink(true); }
    else if (event.key === "Escape") { event.preventDefault(); finishLink(false); }
  });
  // Not being typed in, it shows an address from its start, as a Mac's field does.
  linkInput.addEventListener("blur", () => { linkInput.scrollLeft = 0; });
  // Clicked away from, it applies what was typed, as a Mac link field does.
  linkInput.addEventListener("blur", () => setTimeout(() => { if (!linkInput.hidden && area.isConnected && document.activeElement !== linkInput && document.activeElement !== unlinkTool) finishLink(true, false); }, 0));
  const unlinkTool = tool("Remove", "Remove Link", () => {
    const link = editing?.isConnected ? editing : null;
    linkInput.hidden = true;
    linkNote.hidden = true;
    unlinkTool.hidden = true;
    markChosen(null);
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
  const boldTool = tool("<b>B</b>", "Bold (⌘B)", () => format("bold"));
  const italicTool = tool("<i>I</i>", "Italic (⌘I)", () => format("italic"));
  function askLink() {
    const s = selection();
    if (!s.rangeCount || !area.contains(s.anchorNode)) return false;
    const range = s.getRangeAt(0);
    // Words in a link, or the caret: that link, its address shown to change or remove.
    const start = outerLink(range.startContainer), end = outerLink(range.endContainer);
    editing = start && start === end ? start : null;
    // The caret in a word, no link: that word is linked, as in Pages.
    const text = range.startContainer;
    ofCaret = false;
    if (!editing && range.collapsed && text.nodeType === Node.TEXT_NODE && !atomAt(text)) {
      const letter = /[\p{L}\p{N}'’_-]/u;
      let from = range.startOffset, to = range.startOffset;
      while (from > 0 && letter.test(text.data[from - 1])) from -= 1;
      while (to < text.data.length && letter.test(text.data[to])) to += 1;
      if (to > from) { range.setStart(text, from); range.setEnd(text, to); place(range); ofCaret = true; }
    }
    linkRange = range.cloneRange();
    linkInput.value = editing?.dataset.href || "";
    unlinkTool.hidden = !editing;
    linkInput.hidden = false;
    showBar({ caret: true });
    markChosen(linkRange);
    // All of it chosen, with its start in view (the scheme and the host), not its end.
    setTimeout(() => { linkInput.focus(); linkInput.setSelectionRange(0, linkInput.value.length, "backward"); linkInput.scrollLeft = 0; }, 0);
    return false;
  }
  // The words' own colour, as they are drawn here (light on a dark slide), not the ink's.
  const plainTool = palette.ink ? tool(`<span class="rt-swatch" style="background:${palette.ink}"></span>`, "Default", () => recolour(null), { words: true }) : "";
  const codeTool = tool("<span style=\"font-family: var(--mono); font-size: 11px\">&lt;/&gt;</span>", "Code (⌘E)", asCode, { words: true });
  const mathsTool = tool("<span style=\"font-family: Georgia, serif\">∑</span>", "Equation: the words chosen as LaTeX (⌥⌘E)", asMaths, { words: true });
  const swatchTools = swatches.map(([name, title]) => [tool(`<span class="rt-swatch" style="background:${palette[name]}"></span>`, title, () => recolour(name), { words: true }), name]);
  bar.append(
    boldTool,
    italicTool,
    codeTool,
    mathsTool,
    tool(icon("link"), "Link (⌘K)", () => askLink()),
    ...swatchTools.map(([button]) => button),
    plainTool,
    linkInput,
    linkNote,
    unlinkTool);
  // Along the bar from the keys, as along a Mac toolbar; Esc and Tab go back to the words.
  bar.addEventListener("keydown", (event) => {
    if (event.target === linkInput) return;
    const buttons = [...bar.querySelectorAll("button")].filter((button) => !button.hidden && !button.disabled);
    const at = buttons.indexOf(document.activeElement);
    const go = { ArrowRight: at + 1, ArrowLeft: at - 1, Home: 0, End: buttons.length - 1 }[event.key];
    if (go !== undefined) { event.preventDefault(); event.stopPropagation(); buttons[Math.max(0, Math.min(buttons.length - 1, go))]?.focus(); return; }
    // From Remove with the address still open: Tab applies what was typed, Esc puts it back.
    if (event.key === "Escape" || event.key === "Tab") { event.preventDefault(); event.stopPropagation(); if (!linkInput.hidden) finishLink(event.key === "Tab"); else backToWords(); }
    // Space and Return press the button; nothing else of the slide's is done from here.
    else if (event.key === "Enter" || event.key === " ") event.stopPropagation();
  });
  // ⌃Tab from the words: the bar, at the words chosen (at the caret, what needs no words).
  const toBar = () => {
    const s = selection();
    if (!s.rangeCount || !area.contains(s.anchorNode)) return;
    kept = s.getRangeAt(0).cloneRange();
    showBar({ caret: true });
    // Ringed, as the keys brought it there (a web view rings nothing for ⌃Tab).
    const first = [...bar.querySelectorAll("button")].find((button) => !button.hidden && !button.disabled);
    if (!first) return;
    first.focus({ focusVisible: true });
    first.dataset.keyed = "";
    first.addEventListener("blur", () => { delete first.dataset.keyed; }, { once: true });
  };
  let seen = false;
  const showBar = ({ caret = false } = {}) => {
    // A field gone from the page (the panel drawn again) takes its bar and listener with it.
    if (!area.isConnected) { if (seen) area.dispose(); return; }
    seen = true;
    const s = selection();
    // (A panel's field left keeps its words chosen, but not the keys.)
    const inside = s.rangeCount && area.contains(s.anchorNode) && area.contains(s.focusNode) && (!docked || document.activeElement === area);
    // It stays while it has the keys (its buttons) or a link's address is asked for; a
    // panel's, while its field has the keys.
    // (Nothing chosen is no words chosen: an empty field opened all chosen shows no bar.)
    const none = s.isCollapsed || !s.toString();
    if (!keyed() && linkInput.hidden && !caret && (!inside || (none && !docked))) { bar.hidden = true; return; }
    if (!inside) return;
    // A panel's field has it in the panel under the field, the controls under that moved down
    // to make room for it while it is there: it covers none of them.
    if (docked && bar.previousElementSibling !== area) { bar.classList.add("rt-docked"); area.after(bar); }
    else if (!bar.isConnected) document.body.append(bar);
    // Pressed where the words chosen are bold or italic, as a Mac format bar shows.
    boldTool.classList.toggle("on", boldAlready() ? allBold() : document.queryCommandState("bold"));
    italicTool.classList.toggle("on", document.queryCommandState("italic"));
    // And where they are code or an equation: pressed again, they are words once more.
    const atom = s.rangeCount ? atomAt(s.getRangeAt(0).startContainer) : null;
    codeTool.classList.toggle("on", atom?.nodeName === "CODE");
    mathsTool.classList.toggle("on", Boolean(atom && atom.nodeName !== "CODE"));
    for (const button of bar.querySelectorAll("[data-words]")) button.disabled = none;
    if (plainTool) {
      const own = getComputedStyle(area).color || palette.ink;
      plainTool.firstElementChild.style.background = own;
      // Words drawn in a colour of the theme's already (a number, in the accent): that
      // colour is their Default, offered once, not as two dots alike.
      for (const [button, name] of swatchTools) button.hidden = sameColour(palette[name], own);
    }
    bar.hidden = false;
    if (docked) return;
    // Just over the words chosen, clear of them, as Pages' and Keynote's bar is, and under
    // them when there is no room over them in its `room` (the slide's stage: never over the
    // panels beside it). A cell's is over its table (`frame`), clear of the cells.
    const range = s.getRangeAt(0);
    const at = range.startContainer.nodeType === Node.ELEMENT_NODE ? range.startContainer : range.startContainer.parentElement;
    const chosen = [...range.getClientRects()].some((rect) => rect.width || rect.height) ? range.getBoundingClientRect() : (area.contains(at) ? at : area).getBoundingClientRect();
    const own = bar.getBoundingClientRect();
    const bounds = room?.() || { left: 0, top: 0, right: innerWidth, bottom: innerHeight };
    const over = frame?.() || chosen;
    // A link's address asked for widens it to the right: it stays where it was, by the words.
    const keep = !linkInput.hidden && barLeft !== null;
    let left = keep ? barLeft : chosen.left + chosen.width / 2 - own.width / 2;
    left = Math.max(bounds.left + 8, Math.min(left, bounds.right - own.width - 8));
    // Over them where there is room and it covers none of the words about them -- the field's
    // own other lines, or (`clear`) another object's, a heading's -- else over or under all
    // the field's words, else where it covers least.
    const within = (top) => Math.max(bounds.top + 4, Math.min(top, bounds.bottom - own.height - 4));
    const whole = frame ? over : area.getBoundingClientRect();
    const places = [over.top - own.height - 6, whole.top - own.height - 6, whole.bottom + 6].filter((top) => top >= bounds.top + 4 && top + own.height <= bounds.bottom - 4);
    const all = document.createRange();
    all.selectNodeContents(area);
    const ownLines = [...all.getClientRects()].filter((rect) => rect.width && rect.height);
    // (How much of them: a bar over a title's line and one grazing a byline cover one line
    // each, and it goes where it hides least of the words.)
    const covered = (top) => {
      const rect = { left, top, right: left + own.width, bottom: top + own.height };
      return ownLines.reduce((sum, line) => sum + overlap(line, rect), 0) + (clear ? clear(rect) : 0);
    };
    let best = places.map((top) => ({ top, covers: covered(top) })).reduce((one, other) => (other.covers < one.covers ? other : one), { top: places[0] ?? over.bottom + 6, covers: Infinity });
    // Covering some either way (a title over the subtitle chosen, a byline under it): the
    // nearest place clear of them all, over the field's words or under them, if it is near
    // enough to be theirs.
    for (let step = 4; best.covers > 0 && step <= own.height * 3; step += 4) {
      const near = [whole.top - own.height - 6 - step, whole.bottom + 6 + step].find((top) => top >= bounds.top + 4 && top + own.height <= bounds.bottom - 4 && !covered(top));
      if (near !== undefined) best = { top: near, covers: 0 };
    }
    const top = keep && barTop !== null ? barTop : within(best.top);
    if (!keep) { barLeft = left; barTop = top; }
    Object.assign(bar.style, { top: `${top}px`, left: `${left}px` });
  };
  let barLeft = null, barTop = null;
  document.addEventListener("selectionchange", showBar);
  // A panel's field shows its bar while it has the keys, chosen words or not.
  if (docked) for (const name of ["focus", "blur"]) area.addEventListener(name, () => setTimeout(() => showBar(), 0));

  // The words written again under the field (another's change come in, an undo) while the
  // bar or the link field has the keys: what they act on is the same letters, moved as the
  // words before them moved, and a link being changed is still that link.
  area.holding = () => !linkInput.hidden || keyed();
  const lettersOf = (range) => [[range.startContainer, range.startOffset], [range.endContainer, range.endOffset]].map(([container, offset]) => {
    const upTo = document.createRange();
    upTo.setStart(area, 0);
    upTo.setEnd(container, offset);
    return lettersIn(upTo.cloneContents()).length;
  });
  const rangeOf = ([start, end]) => {
    const from = pointAt(start), to = pointAt(end);
    if (!from || !to) return null;
    const range = document.createRange();
    range.setStart(...from);
    range.setEnd(...to);
    return range;
  };
  // Where the letter at `at` in `was` is in `now`: before the change, where it was; after
  // it, moved with the words; inside it, at its end.
  const through = (was, now, at) => {
    let start = 0, end = 0;
    while (start < was.length && start < now.length && was[start] === now[start]) start += 1;
    while (end < was.length - start && end < now.length - start && was[was.length - 1 - end] === now[now.length - 1 - end]) end += 1;
    return at <= start ? at : at >= was.length - end ? at + now.length - was.length : now.length - end;
  };
  const rewrite = (text) => {
    if (!area.holding()) { write(text); return; }
    const whole = editing?.isConnected ? document.createRange() : null;
    whole?.selectNodeContents(editing);
    const held = [linkRange, kept, whole].map((range) => (range && area.contains(range.startContainer) ? lettersOf(range) : null));
    const was = area.letters();
    write(text);
    const now = area.letters();
    const moved = held.map((at) => at && at.map((n) => through(was, now, n)));
    [linkRange, kept] = moved.slice(0, 2).map((at) => at && rangeOf(at));
    // The link being changed, found by a letter inside it.
    const inside = moved[2] && moved[2][1] > moved[2][0] ? pointAt(moved[2][0] + 1) : null;
    if (editing) editing = inside ? outerLink(inside[0]) : null;
  };
  // Whoever closes the field takes its bar with it, and the address being typed is applied.
  // (A field the page has dropped writes nothing more.)
  area.dispose = () => {
    if (area.isConnected) finishLink(true, false); else { linkInput.hidden = true; markChosen(null); }
    bar.remove();
    document.removeEventListener("selectionchange", showBar);
  };

  // Words copied or cut go as the slide has them, as their markup makes them -- bold,
  // italic, links, code, maths, the theme's colours, a list's items and levels -- and as
  // words alone: never the editor's own face, size and paper, which another app would keep.
  const htmlOf = (markup) => {
    const holder = document.createElement("div");
    holder.append(...inlineNodes(markup, colours));
    for (const link of holder.querySelectorAll("a[data-href]")) { link.setAttribute("href", link.dataset.href); link.removeAttribute("title"); }
    return holder.innerHTML;
  };
  const toClipboard = (event) => {
    const s = selection();
    if (!event.clipboardData || !s.rangeCount || s.isCollapsed || !area.contains(s.anchorNode)) return false;
    const holder = document.createElement("div");
    holder.append(onWords(s.getRangeAt(0)).cloneContents());
    const items = list && holder.querySelector(".rt-line")
      // (A line break in an item kept in its HTML; in plain words, one item a line, a space.)
      ? [...holder.children].filter((line) => line.classList?.contains("rt-line")).map((line) => ({ level: Number(line.dataset.level) || 0, markup: serialise(line, undefined, names).replace(/\n$/, ""), text: line.textContent.replace(/\n/g, " ") }))
      : null;
    let html, text;
    if (items) {
      let depth = -1;
      html = "";
      for (const item of items) {
        while (depth < item.level) { html += "<ul>"; depth += 1; }
        while (depth > item.level) { html += "</ul>"; depth -= 1; }
        html += `<li>${htmlOf(item.markup)}</li>`;
      }
      while (depth-- >= 0) html += "</ul>";
      text = items.map((item) => "\t".repeat(item.level) + item.text).join("\n");
    } else {
      const markup = serialise(holder, undefined, names).replace(/\n$/, "");
      html = markup.split("\n").map(htmlOf).join("<br>");
      text = s.toString();
    }
    event.preventDefault();
    event.clipboardData.setData("text/html", html);
    event.clipboardData.setData("text/plain", text);
    return true;
  };
  // A word cut or deleted takes a space beside it with it, as on a Mac: no two spaces left
  // between words, nor one before a stop.
  const smartJoin = () => {
    const s = selection();
    const text = s.rangeCount && s.isCollapsed ? s.anchorNode : null;
    if (text?.nodeType !== Node.TEXT_NODE || !area.contains(text)) return;
    const at = s.anchorOffset, before = text.data[at - 1], after = text.data[at];
    if (before === " " && (after === " " || /^[.,;:!?)]$/.test(after || ""))) {
      text.deleteData(at - 1, 1);
      const caret = document.createRange();
      caret.setStart(text, at - 1);
      place(caret);
    } else if (before === undefined && after === " " && !text.previousSibling) text.deleteData(0, 1);
  };
  // What is done here in parts (the words chosen deleted, then the space beside them) is
  // heard as one change once done (`changed`), one step in the history, not each part.
  const quietly = (run) => {
    const hush = (event) => { if (area.contains(event.target)) event.stopImmediatePropagation(); };
    window.addEventListener("input", hush, true);
    try { run(); } finally { window.removeEventListener("input", hush, true); }
  };
  area.addEventListener("copy", toClipboard);
  area.addEventListener("cut", (event) => {
    if (!toClipboard(event)) return;
    quietly(() => { document.execCommand("delete"); smartJoin(); });
    changed(true, "Cut");
  });
  let deletingChosen = false;
  area.addEventListener("beforeinput", (event) => { deletingChosen = /^delete/.test(event.inputType) && !getSelection().isCollapsed; });
  area.addEventListener("input", (event) => { if (deletingChosen && /^delete/.test(event.inputType || "")) { deletingChosen = false; smartJoin(); } });

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
    // At a link's edge it goes beside the link, as typing there does, not into it; in a
    // link, a link pasted is its words: one link, never one in another.
    const beside = range.collapsed ? outOfEdge(range, { colours: false }) : null;
    if (beside) { range.setStart(beside.startContainer, beside.startOffset); range.collapse(true); }
    const nodes = lines.flatMap((markup, n) => [...(n ? [document.createElement("br")] : []), ...inlineNodes(markup, colours)]);
    if (!nodes.length) return;
    const fragment = document.createDocumentFragment();
    fragment.append(...nodes);
    if (outerLink(range.startContainer)) for (const link of [...fragment.querySelectorAll("a")]) link.replaceWith(...link.childNodes);
    const last = fragment.lastChild;
    range.insertNode(fragment);
    const caret = document.createRange();
    caret.setStartAfter(last);
    caret.collapse(true);
    place(caret);
  };
  // The words before the caret and after it (what is chosen gone), as markup: where words
  // pasted that are not words (a list, a table) split them.
  const splitAtCaret = () => {
    const s = selection();
    if (!s.rangeCount || !area.contains(s.anchorNode)) return { before: read(), after: "" };
    const range = s.getRangeAt(0);
    const part = (from, to) => {
      const piece = document.createRange();
      piece.selectNodeContents(area);
      if (from) piece.setStart(from[0], from[1]);
      if (to) piece.setEnd(to[0], to[1]);
      const holder = document.createElement("div");
      holder.append(piece.cloneContents());
      return serialise(holder, undefined, names).replace(/\n$/, "");
    };
    return { before: part(null, [range.startContainer, range.startOffset]), after: part([range.endContainer, range.endOffset], null) };
  };
  area.addEventListener("paste", (event) => {
    const text = event.clipboardData?.getData("text/plain");
    const html = matchStyle ? "" : event.clipboardData?.getData("text/html") || "";
    matchStyle = false;
    if (text === undefined && !html) return;
    event.preventDefault();
    // A range of a spreadsheet's cells is given to whoever holds the field (`onCells`): a
    // table's cell fills the cells from it on, words have a table made after them.
    const cells = onCells ? cellsOf(html, text) : null;
    if (cells) { event.stopPropagation(); onCells(cells, list || single ? null : splitAtCaret()); return; }
    changed(true);
    // One address pasted is a link (unless it came as formatted words of their own).
    const linked = linkOfWords(text);
    if (linked && (!html || itemsOfHtml(html).map((item) => item.markup).join("").trim() === String(text).trim())) {
      // Over words chosen, it links them, as in Pages, the caret after them.
      const s = selection();
      if (!s.isCollapsed && s.toString().trim() && area.contains(s.anchorNode)) {
        const words = String(text).trim();
        const href = /\]\(([^)]*)\)$/.exec(linked)?.[1] || words;
        const made = wrapChosen((chosen) => { const a = linkNode(href); a.append(chosen); return a; }, { strip: isLink, choose: false });
        if (made) {
          const caret = document.createRange();
          caret.setStartAfter(outerLink(made.endContainer) || made.endContainer);
          caret.collapse(true);
          place(caret);
          changed(true, "Paste Link");
          return;
        }
      }
      // A space pasted at either end stays a word's space beside it: not doubled with one by
      // the caret, nor put at a line's start or before a stop -- but kept at its end, so the
      // next word typed is not run into the address.
      const caret = area.caretAt(), letters = area.letters();
      const before = caret ? letters[caret[0] - 1] : undefined, after = caret ? letters[caret[1]] : undefined;
      const lead = /^\s/.test(text) && before !== undefined && !/\s/.test(before) ? " " : "";
      const trail = /\s$/.test(text) && !(after !== undefined && /[\s.,;:!?)\]}]/.test(after)) ? " " : "";
      insertMarkup(`${lead}${linked}${trail}`);
      changed(true, "Paste Text");
      return;
    }
    // What was pasted, as items: each its depth in a list and its words as markup.
    const formatted = html ? itemsOfHtml(html).filter((item) => !list || item.markup.trim()) : null;
    const plainParts = String(text ?? "").replace(/\r\n?/g, "\n").split("\n");
    const items = (formatted?.length ? formatted
      : plainParts.length > 1 && list ? plainParts.map(listed).map((item) => ({ depth: item.depth, markup: escaped(item.words) }))
        : plainParts.map((part) => ({ depth: 0, markup: escaped(part) }))).map((item) => ({ ...item, markup: item.markup.replace(/^\t+/, "").replace(/\t+/g, " ") }));
    // A space at either end of what is pasted stays, as a Mac's smart paste leaves it: not
    // doubled with one beside the caret, at a line's edge, or before punctuation.
    const caret = area.caretAt(), letters = area.letters();
    const before = caret ? letters[caret[0] - 1] : undefined, after = caret ? letters[caret[1]] : undefined;
    if (items.length && (before === undefined || /\s/.test(before))) items[0].markup = items[0].markup.replace(/^\s+/, "");
    // (At a line's end it stays: the next word typed is not run into the last pasted.)
    if (items.length && after !== undefined && /[\s.,;:!?)\]}]/.test(after)) items[items.length - 1].markup = items[items.length - 1].markup.replace(/\s+$/, "");
    // On one line, the lines pasted are words a space apart (a blank line, or a tab, is no
    // more); the spaces at their own two ends stay, as words go in among others.
    if (single) {
      const lines = items.map((item) => item.markup.replace(/\t/g, " "));
      const words = lines.map((line) => line.trim()).filter(Boolean).join(" ");
      insertMarkup(words && `${/^\s/.test(lines[0]) ? " " : ""}${words}${/\s$/.test(lines[lines.length - 1]) ? " " : ""}`);
      changed(true, "Paste Text");
      return;
    }
    // An outline or a list pasted in words (a paragraph's) is a list, given to whoever holds
    // them (`onList`, each item's depth and words): not lines with their levels lost.
    if (!list && onList) {
      const lines = plainParts.filter((part) => part.trim());
      const fromHtml = formatted?.filter((item) => item.markup.trim()) || [];
      const outline = !fromHtml.length && lines.length > 1 && (lines.some((line) => /^\t/.test(line)) || lines.every((line) => LIST_MARK.test(line.trim())));
      if (outline || (fromHtml.length > 1 && fromHtml.every((item) => item.listed))) {
        event.stopPropagation();
        onList(outline ? lines.map((line) => ({ ...listed(line), ordered: /^\(?\d{1,3}[.)]\s/.test(line.trim()) })).map((item) => ({ depth: item.depth, markup: escaped(item.words), ordered: item.ordered }))
          : fromHtml.map((item) => ({ depth: item.depth || 0, markup: item.markup.trim(), ordered: Boolean(item.ordered) })), splitAtCaret());
        return;
      }
    }
    if (!list) { insertMarkup(...items.map((item) => item.markup)); changed(true, "Paste Text"); return; }
    // In a list, items: their indents kept as levels under the item pasted into, and the
    // words after the caret moved to the end of the last one. The first goes on with the
    // item pasted into as it was, unless that is empty. (Items chosen go first, as typing
    // over them would take them; the caret is then in an item, however the list was chosen
    // -- a new list's one empty item chosen whole, from the list itself.)
    if (!selection().isCollapsed) quietly(() => document.execCommand("delete"));
    let line = lineAt(selection().anchorNode);
    if (!line) {
      tidy();
      line = lines()[0] || null;
      if (!line) { line = lineNode(0, ""); area.append(line); }
      const start = document.createRange();
      start.setStart(line, 0);
      place(start);
    }
    // (Its list mark taken off, as every other line's is: "- one" goes on the item as "one".)
    if (!formatted?.length && line?.textContent.trim() && plainParts.length > 1) items[0] = { depth: items[0].depth, markup: escaped(listed(plainParts[0]).words) };
    const level = Number(line?.dataset.level) || 0;
    let rest = null;
    if (line && items.length > 1) {
      const after = document.createRange();
      const s = selection();
      after.setStart(s.getRangeAt(0).endContainer, s.getRangeAt(0).endOffset);
      after.setEnd(line, line.childNodes.length);
      if (!s.isCollapsed) quietly(() => document.execCommand("delete"));  // what was chosen goes, as a paste replaces it
      rest = after.extractContents();
    }
    insertMarkup(items[0].markup);
    line = lineAt(selection().anchorNode);
    const first = items[0].depth;
    for (const item of items.slice(1)) {
      if (!line) break;
      const next = lineNode(Math.max(0, Math.min(4, level + item.depth - first)), item.markup.trimStart());
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
    changed(true, "Paste Text");
  });
  return area;
}

export { serialise as markupFromNodes, inlineNodes as nodesFromMarkup, escaped as markupOfWords, itemsOfHtml, cellsOf, linkOfWords, emphasised };

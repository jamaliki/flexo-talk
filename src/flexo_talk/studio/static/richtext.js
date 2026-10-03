// Words typed on a slide as the slide shows them: flexo markup (**bold**, *italic*,
// `code`, $maths$, [links](url), [colours]{accent}) shown bold, italic, in the
// monospace and in its colour rather than as marks, and a list as a list -- a bullet
// to each item, items indented by level -- rather than lines of spaces.
//
// richText() makes the field: a contenteditable element whose `value` is the markup
// (for a list, one item a line, two spaces a level, as bulletsText writes it), and
// which says "input" whenever it changes, as a textarea does.

// -- markup to runs --------------------------------------------------------------------

const INLINE = /(\[[^\]\n]+\]\([^)\s]+\)|\[[^\]\n]+\]\{[^}\s]+\}|`[^`]*`|\*\*|\*)/;
const ASTERISK = "";

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
  const split = (part) => tokens.push(...part.replace(/\\\*/g, ASTERISK).split(INLINE).filter(Boolean));
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
      node.textContent = code[1];
      nodes.push(wrapped(node, style));
    } else {
      // Lines in the words are lines on the page.
      token.replaceAll(ASTERISK, "*").split("\n").forEach((line, n) => {
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
    const next = {
      bold: style.bold || tag === "B" || tag === "STRONG" || css.fontWeight === "bold" || Number(css.fontWeight) >= 600,
      italic: style.italic || tag === "I" || tag === "EM" || css.fontStyle === "italic",
    };
    if (tag === "CODE") { runs.push({ raw: `\`${child.textContent.replace(/`/g, "")}\``, ...next, wrap: true }); continue; }
    const colour = child.dataset?.colour || (tag === "FONT" && child.getAttribute("color") ? names(child.getAttribute("color")) : null);
    if (tag === "A" && child.dataset.href) { runs.push({ raw: `[${serialise(child, next, names)}](${child.dataset.href})` }); continue; }
    // The ink is the words' own colour: no colour of their own.
    if (colour && colour !== "ink") { runs.push({ raw: `[${serialise(child, next, names)}]{${colour}}` }); continue; }
    // A line the browser made a block of its own (a pasted or split paragraph) is a line.
    if ((tag === "DIV" || tag === "P") && runs.length && !String(runs[runs.length - 1].text ?? "").endsWith("\n")) runs.push({ text: "\n" });
    runsOf(child, next, runs, names);
  }
  return runs;
}

const escaped = (text) => text.replace(/\*/g, "\\*");

// Runs as markup: emphasis opened and closed only where it changes, each mark against
// a word (spaces kept outside it), so ** and * pair as written.
function markupOf(runs) {
  let out = "", pending = "";
  const open = { bold: false, italic: false };
  const close = () => {
    let marks = "";
    if (open.italic) marks += "*";
    if (open.bold) marks += "**";
    open.bold = open.italic = false;
    return marks;
  };
  for (const run of runs) {
    if (run.raw !== undefined && !run.wrap) { out += close() + pending + run.raw; pending = ""; continue; }
    const text = run.raw ?? escaped(run.text);
    const [, lead, core, trail] = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
    if (!core) { pending += text; continue; }
    let marks = "";
    if (open.italic && !run.italic) { marks += "*"; open.italic = false; }
    if (open.bold && !run.bold) { marks += "**"; open.bold = false; }
    out += marks + pending + lead;
    if (!open.bold && run.bold) { out += "**"; open.bold = true; }
    if (!open.italic && run.italic) { out += "*"; open.italic = true; }
    out += core;
    pending = trail;
  }
  return out + close() + pending;
}

function serialise(node, style = { bold: false, italic: false }, names = (colour) => colour) {
  return markupOf(runsOf(node, style, [], names));
}

// -- the field -------------------------------------------------------------------------

// `list` makes it a list (Tab and Shift-Tab change an item's level, Return starts the
// next item, Return on an empty item moves it out a level); `single` a line of its own
// (Return is left to whoever holds it); else words in lines. `palette` gives the
// theme's colours by name, for [words]{accent}.
export function richText({ value = "", list = false, single = false, numbered = false, palette = {}, placeholder = "", spelling = true } = {}) {
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
  const changed = () => area.dispatchEvent(new Event("input", { bubbles: true }));
  area.addEventListener("input", () => area.classList.toggle("empty", !area.textContent.trim() && !area.querySelector(".rt-line + .rt-line")));

  // -- the caret --
  const selection = () => getSelection();
  const place = (range) => { const s = selection(); s.removeAllRanges(); s.addRange(range); };
  area.selectAll = () => { const range = document.createRange(); range.selectNodeContents(area); place(range); };
  area.caretToEnd = () => { const range = document.createRange(); range.selectNodeContents(area); range.collapse(false); place(range); };
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

  area.addEventListener("keydown", (event) => {
    const mod = event.metaKey || event.ctrlKey;
    if (mod && !event.altKey && ["b", "i"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      document.execCommand(event.key.toLowerCase() === "b" ? "bold" : "italic");
      return;
    }
    if (event.key === "Tab" && list) {
      event.preventDefault();
      for (const line of chosenLines()) setLevel(line, Number(line.dataset.level) + (event.shiftKey ? -1 : 1));
      changed();
      return;
    }
    if (event.key === "Tab" && !single) { event.preventDefault(); return; }
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
    button.innerHTML = label;
    Object.assign(button.style, style);
    // The words stay chosen: the button never takes the caret.
    button.addEventListener("mousedown", (event) => { event.preventDefault(); run(); changed(); showBar(); });
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
        changed();
      }
      linkInput.hidden = true;
      area.focus();
    } else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); linkInput.hidden = true; if (linkRange) place(linkRange); area.focus(); }
  });
  bar.append(
    tool("<b>B</b>", "Bold (⌘B)", () => document.execCommand("bold")),
    tool("<i>I</i>", "Italic (⌘I)", () => document.execCommand("italic")),
    tool("<span style=\"font-family: var(--mono); font-size: 11px\">&lt;/&gt;</span>", "Code", () => wrapChosen((text) => plainNode("code", "", text))),
    tool("<span style=\"font-family: Georgia, serif; font-style: italic\">x²</span>", "Equation: the words chosen as LaTeX", () => wrapChosen((text) => plainNode("span", "rt-maths", `$${text}$`))),
    tool("Link", "Link", () => { const s = selection(); linkRange = s.rangeCount ? s.getRangeAt(0).cloneRange() : null; linkInput.value = ""; linkInput.hidden = false; setTimeout(() => linkInput.focus(), 0); }),
    ...swatches.map(([name, title]) => tool(`<span class="rt-swatch" style="background:${palette[name]}"></span>`, title, () => document.execCommand("foreColor", false, palette[name]))),
    palette.ink ? tool("<span class=\"rt-swatch rt-plain\"></span>", "Default colour", () => document.execCommand("foreColor", false, palette.ink)) : "",
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
    bar.hidden = false;
    const chosen = s.getRangeAt(0).getBoundingClientRect(), own = bar.getBoundingClientRect();
    const above = chosen.top - own.height - 8;
    const top = above > 8 ? above : chosen.bottom + 8;
    const left = Math.min(Math.max(8, chosen.left + chosen.width / 2 - own.width / 2), innerWidth - own.width - 8);
    Object.assign(bar.style, { top: `${top}px`, left: `${left}px` });
  };
  document.addEventListener("selectionchange", showBar);
  // Whoever closes the field takes its bar with it.
  area.dispose = () => { bar.remove(); document.removeEventListener("selectionchange", showBar); };

  // Pasted words come as words, in the look of where they go; lines pasted in a list are items.
  area.addEventListener("paste", (event) => {
    const text = event.clipboardData?.getData("text/plain");
    if (text === undefined) return;
    event.preventDefault();
    const parts = text.replace(/\r\n?/g, "\n").split("\n");
    if (single) { document.execCommand("insertText", false, parts.join(" ")); return; }
    if (!list) {
      parts.forEach((part, n) => { if (n) document.execCommand("insertLineBreak"); if (part) document.execCommand("insertText", false, part); });
      return;
    }
    document.execCommand("insertText", false, parts[0]);
    let line = lineAt(selection().anchorNode);
    for (const part of parts.slice(1)) {
      if (!line) break;
      const next = lineNode(Number(line.dataset.level) || 0, "");
      next.replaceChildren(document.createTextNode(part.trim()) );
      if (!part.trim()) next.replaceChildren(document.createElement("br"));
      line.after(next);
      line = next;
    }
    if (line) { const caret = document.createRange(); caret.selectNodeContents(line); caret.collapse(false); place(caret); }
    changed();
  });
  return area;
}

export { serialise as markupFromNodes, inlineNodes as nodesFromMarkup };

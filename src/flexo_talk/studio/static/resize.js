// A slide's objects set again at another width as the slide will set them, while a side or
// a corner of one is dragged (editor.js's resizing): words wrapped where the slide wraps
// them -- measured as it measures them, each line filled (a list's, a panel's) or evened out
// (a paragraph's) -- a list's items one under another, a quote's words and who said it, a
// callout's panel round its words, numbers side by side, a listing's panel, an equation set
// smaller, and a table's columns sharing its width, their words wrapped in them.
//
// `sizer(element, kind, span)` reads the object as it is drawn (compose.py marks what it
// needs on it while it is edited: data-flexo-span, -wrap, -line, -breaks, -columns) and gives
// a function that sets it again `width` points wide with its left edge at `left`, returning
// how much taller (or shorter) it is -- or null where it cannot be set here (words with a
// drawn formula in them), for the caller to show its frame alone.

const SVG_NS = "http://www.w3.org/2000/svg";
const XML_NS = "http://www.w3.org/XML/1998/namespace";
// The looks a stretch of words carries, on its own tspan or the text it is in.
const LOOK = ["font-family", "font-size", "font-weight", "font-style", "fill", "data-flexo-fill", "text-decoration", "baseline-shift", "opacity"];
// (Measured large and scaled, unhinted, as the slide measures its words: set small, a
// browser's words come out a little narrower, and a line just too long for it would fit.)
const pen = typeof document !== "undefined" ? document.createElement("canvas").getContext("2d") : null;
if (pen && "textRendering" in pen) pen.textRendering = "geometricPrecision";
// Room for rounding, as the slide's measurer allows a line before it wraps it.
const ROUNDING = 1e-6;

const num = (element, name, fallback = 0) => {
  const value = parseFloat(element?.getAttribute?.(name) ?? "");
  return Number.isFinite(value) ? value : fallback;
};
const family = (value) => String(value || "sans-serif").split(",").map((name) => {
  const plain = name.trim();
  return /^["']/.test(plain) || !/\s/.test(plain) ? plain : `"${plain}"`;
}).join(", ");

// How wide a piece of words is drawn, in the slide's points.
function widthOf(text, look) {
  if (!pen || !text) return 0;
  const size = parseFloat(look["font-size"]) || 16;
  pen.font = `${look["font-style"] || "normal"} ${look["font-weight"] || "400"} 100px ${family(look["font-family"])}`;
  return pen.measureText(text).width * size / 100;
}

// A text's words as drawn: its lines, each the pieces of it in their looks (a run of bold,
// a link, a letter set raised) -- or, words with formulas drawn among them (a fraction), a
// group of stretches of words and formulas, each formula a piece no line breaks inside.
// Null for anything else (a letter stepped back over another, a line opened for a tall
// formula), which is not set again here.
function readWords(element) {
  if (element?.localName === "g") return readFormulaWords(element);
  if (element?.localName !== "text") return null;
  const base = lookOf(element);
  const lines = [];
  let plain = true;
  const visit = (node, look, top) => {
    for (const child of node.childNodes) {
      if (child.nodeType === 3) {
        if (child.textContent && (lines.length || child.textContent.trim())) {
          if (!lines.length) lines.push([]);
          lines[lines.length - 1].push({ text: child.textContent, look });
        }
        continue;
      }
      if (child.nodeType !== 1) continue;
      if (child.localName === "a") { visit(child, look, top); continue; }
      if (child.localName !== "tspan" || child.hasAttribute("dx")) { plain = false; continue; }
      if (top && child.hasAttribute("x")) lines.push([]);
      const own = { ...look };
      for (const name of LOOK) if (child.hasAttribute(name)) own[name] = child.getAttribute(name);
      visit(child, own, false);
    }
  };
  visit(element, base, true);
  if (!plain || !lines.length) return null;
  const steps = [...element.querySelectorAll("tspan[dy]")].map((span) => num(span, "dy")).filter((value) => value > 0);
  const size = parseFloat(base["font-size"]) || 16;
  return {
    ...settings(element, lines, base), drawn: "text", x: num(element, "x"), y: num(element, "y"),
    anchor: element.getAttribute("text-anchor") || "start",
    line: num(element, "data-flexo-line", 0) || steps[0] || size * 1.2,
  };
}
function lookOf(text) {
  const look = {};
  for (const name of LOOK) if (text.hasAttribute(name)) look[name] = text.getAttribute(name);
  look["font-weight"] ||= "400";
  return look;
}
// Its paragraphs (lines the slide wrapped joined again by the space they were wrapped at,
// and lines begun by hand kept apart), how many lines it has, whether they are evened out,
// and the width they were wrapped at.
function settings(element, lines, base) {
  const wrap = String(element.getAttribute("data-flexo-wrap") || "");
  const begun = new Set(String(element.getAttribute("data-flexo-breaks") || "").split(/\s+/).filter(Boolean).map(Number));
  const paragraphs = [];
  lines.forEach((line, index) => {
    if (!index || begun.has(index)) paragraphs.push([...line]);
    else {
      const last = paragraphs[paragraphs.length - 1];
      const look = [...last].reverse().find((piece) => piece.look)?.look || line.find((piece) => piece.look)?.look || base;
      last.push({ text: " ", look }, ...line);
    }
  });
  return { paragraphs, lines: lines.length, balance: / balance$/.test(wrap), wrap: parseFloat(wrap) || null, base };
}
function readFormulaWords(group) {
  const children = [...group.children];
  const texts = children.filter((child) => child.localName === "text");
  if (!texts.length || children.some((child) => child.localName !== "text" && !(child.localName === "g" && child.classList.contains("flexo-math")))) return null;
  const line = num(group, "data-flexo-line", 0) || parseFloat(texts[0].getAttribute("font-size")) * 1.2;
  const first = Math.min(...texts.map((text) => num(text, "y")));
  const at = (y) => Math.max(0, Math.round((y - first) / line));
  // Each stretch of words and each formula, in order, on the line it is on.
  const items = [];
  for (const child of children) {
    if (child.localName === "text") {
      const words = readWords(child);
      if (!words || words.lines !== 1) return null;
      items.push({ line: at(num(child, "y")), x: num(child, "x"), pieces: words.paragraphs[0] });
    } else {
      const found = /translate\(\s*([-\d.e]+)[ ,]+([-\d.e]+)\s*\)/.exec(child.getAttribute("transform") || "");
      if (!found) return null;
      const y = Number(found[2]), index = at(y);
      items.push({ line: index, x: Number(found[1]), formula: child, shift: first + index * line - y });
    }
  }
  // A formula's width: to what follows it on its line, else as wide as it is inked.
  items.forEach((item, index) => {
    if (!item.formula) return;
    const next = items[index + 1];
    let width = next && next.line === item.line ? next.x - item.x : null;
    if (width == null) { try { width = item.formula.getBBox().width; } catch { width = 0; } }
    item.pieces = [{ formula: item.formula, width, shift: item.shift }];
  });
  const lines = [];
  for (const item of items) (lines[item.line] ||= []).push(...item.pieces);
  const filled = lines.map((each) => each || []);
  const left = Math.min(...items.filter((item) => item.line === 0).map((item) => item.x));
  const widthOfLine = (pieces) => pieces.reduce((sum, piece) => sum + (piece.formula ? piece.width : widthOf(piece.text, piece.look)), 0);
  const anchor = group.getAttribute("data-flexo-anchor") || "start";
  const shown = widthOfLine(filled[0] || []);
  return {
    ...settings(group, filled, lookOf(texts[0])), drawn: "formulas", template: texts[0], line, y: first, anchor,
    x: anchor === "middle" ? left + shown / 2 : anchor === "end" ? left + shown : left,
  };
}

// A paragraph's words as the slide breaks them: units (a word, and the pieces touching it,
// a raised letter, a formula, a comma after it) between spaces, each line filled in turn --
// or, `balance`, at the narrowest width that needs no more lines than that, so its lines
// come out even.
function tokensOf(pieces) {
  const tokens = [];
  for (const piece of pieces) {
    if (piece.formula) { tokens.push({ ...piece, space: false }); continue; }
    for (const part of piece.text.split(/(\s+)/)) {
      if (!part) continue;
      tokens.push({ text: part, look: piece.look, space: /^\s+$/.test(part), width: widthOf(part, piece.look) });
    }
  }
  const units = [];
  for (const token of tokens) {
    const last = units[units.length - 1];
    if (!token.space && last && !last.space) { last.tokens.push(token); last.width += token.width; }
    else units.push({ space: token.space, tokens: [token], width: token.width });
  }
  return units;
}
function fill(units, room) {
  const lines = [];
  let line = [], width = 0;
  for (const unit of units) {
    if (unit.space) { if (line.length) { line.push(unit); width += unit.width; } continue; }
    if (line.length && width + unit.width > room + ROUNDING) {
      lines.push(line);
      line = [];
      width = 0;
    }
    line.push(unit);
    width += unit.width;
  }
  lines.push(line);
  // (A line ends at its last word: the space it was wrapped at is not part of it.)
  return lines.map((each) => { while (each.length && each[each.length - 1].space) each.pop(); return each; });
}
function wrapped(units, room, balance) {
  const lines = fill(units, room);
  if (!balance || lines.length < 2) return lines;
  const widest = Math.max(0, ...units.filter((unit) => !unit.space).map((unit) => unit.width));
  let low = Math.min(widest, room), high = room;
  for (let step = 0; step < 12; step += 1) {
    const middle = (low + high) / 2;
    if (fill(units, middle).length <= lines.length) high = middle; else low = middle;
  }
  return fill(units, high);
}

// How many lines words take wrapped at `room` points.
const linesIn = (words, room) => words.paragraphs.reduce((sum, pieces) => sum + wrapped(tokensOf(pieces), room, words.balance).length, 0);

// Pieces of words in one look, a tspan each: the first starting a line where `x` says.
function spansOf(tokens, words, x, dy) {
  const spans = [];
  for (const token of tokens) {
    const last = spans[spans.length - 1];
    if (last && last.look === token.look) last.text += token.text;
    else spans.push({ text: token.text, look: token.look });
  }
  if (!spans.length) spans.push({ text: "", look: words.base });
  return spans.map((piece, at) => {
    const span = document.createElementNS(SVG_NS, "tspan");
    for (const name of LOOK) if (piece.look[name] != null && piece.look[name] !== words.base[name]) span.setAttribute(name, piece.look[name]);
    if (!at && x != null) {
      span.setAttribute("x", String(x));
      if (dy) span.setAttribute("dy", String(dy));
    }
    if (piece.text !== piece.text.trim()) span.setAttributeNS(XML_NS, "xml:space", "preserve");
    span.textContent = piece.text;
    return span;
  });
}

// The words of `element` set again in `room` points, their lines where `x` says (as their
// anchor sets them) from the first baseline `y` down; returns how many lines they take.
function setWords(element, words, room, x, y = words.y) {
  const lines = words.paragraphs.flatMap((pieces) => wrapped(tokensOf(pieces), room, words.balance));
  if (words.drawn === "formulas") return setFormulaWords(element, words, lines, x, y);
  while (element.firstChild) element.firstChild.remove();
  element.setAttribute("x", String(x));
  element.setAttribute("y", String(y));
  lines.forEach((line, index) => element.append(...spansOf(line.flatMap((unit) => unit.tokens), words, x, index ? words.line : 0)));
  return lines.length;
}
// Words with formulas among them: each stretch of words a text of its own, each formula
// moved to where its line leaves room for it.
function setFormulaWords(group, words, lines, x, y) {
  for (const child of [...group.children]) if (child.localName === "text") child.remove();
  lines.forEach((line, index) => {
    const tokens = line.flatMap((unit) => unit.tokens);
    const width = tokens.reduce((sum, token) => sum + token.width, 0);
    const baseline = y + index * words.line;
    let at = words.anchor === "middle" ? x - width / 2 : words.anchor === "end" ? x - width : x;
    let stretch = [];
    const flush = () => {
      if (!stretch.length) return;
      const text = document.createElementNS(SVG_NS, "text");
      for (const attribute of words.template.attributes) if (!["id", "x", "y"].includes(attribute.name)) text.setAttribute(attribute.name, attribute.value);
      text.setAttribute("x", String(at));
      text.setAttribute("y", String(baseline));
      text.append(...spansOf(stretch, words, at, 0));
      group.append(text);
      at += stretch.reduce((sum, token) => sum + token.width, 0);
      stretch = [];
    };
    for (const token of tokens) {
      if (!token.formula) { stretch.push(token); continue; }
      flush();
      token.formula.setAttribute("transform", `translate(${at} ${baseline - token.shift})`);
      group.append(token.formula);
      at += token.width;
    }
    flush();
  });
  return lines.length;
}

// Where words anchored at `anchor` stand in a room from `left`, `width` wide.
const anchored = (anchor, left, width) => (anchor === "middle" ? left + width / 2 : anchor === "end" ? left + width : left);

// Words in an object, as they sit in it: how far their room starts in from its left edge and
// ends in from its right, so they keep that room as the object is made wider or narrower.
function inRoom(text, span) {
  const words = text && readWords(text);
  if (!words || !words.wrap) return null;
  const start = words.anchor === "middle" ? words.x - words.wrap / 2 : words.anchor === "end" ? words.x - words.wrap : words.x;
  const before = start - span.x, after = span.x + span.width - (start + words.wrap);
  return {
    words,
    // Set again in its room in an object from `x`, `width` wide, its first baseline at `y`;
    // how many lines it takes.
    set: (x, width, y = words.y) => {
      const room = Math.max(1, width - before - after);
      return setWords(text, words, room, anchored(words.anchor, x + before, room), y);
    },
  };
}

// -- each kind --

function textSizer(element, span) {
  const room = inRoom(element, span);
  if (!room) return null;
  const was = room.words.lines;
  return (left, width) => (room.set(left, width) - was) * room.words.line;
}

function listSizer(element, span) {
  const id = element.id, items = [];
  for (let n = 0; n < 500; n += 1) {
    const text = element.querySelector(`[id="${CSS.escape(`${id}.${n}`)}"]`);
    if (!text) break;
    const words = readWords(text);
    if (!words) return null;
    const rtl = words.anchor === "end";
    // (How far in from its start its words begin: its bullet, its level's indent.)
    const offset = rtl ? span.x + span.width - words.x : words.x - span.x;
    items.push({ text, words, rtl, offset, y: words.y, mark: element.querySelector(`[id="${CSS.escape(`${id}.${n}.mark`)}"]`), markAt: null });
  }
  if (!items.length) return null;
  for (const item of items) item.markAt = item.mark ? { x: num(item.mark, item.mark.hasAttribute("cx") ? "cx" : "x"), y: num(item.mark, item.mark.hasAttribute("cy") ? "cy" : "y") } : null;
  return (left, width) => {
    let down = 0;
    for (const item of items) {
      const edge = item.rtl ? left + width - (span.x + span.width) : left - span.x;
      const lines = setWords(item.text, item.words, Math.max(1, width - item.offset), item.rtl ? left + width - item.offset : left + item.offset, item.y + down);
      if (item.mark && item.markAt) {
        const [ax, ay] = item.mark.hasAttribute("cx") ? ["cx", "cy"] : ["x", "y"];
        item.mark.setAttribute(ax, String(item.markAt.x + edge));
        item.mark.setAttribute(ay, String(item.markAt.y + down));
        for (const tspan of item.mark.querySelectorAll?.("tspan[x]") || []) tspan.setAttribute("x", String(item.markAt.x + edge));
      }
      down += (lines - item.words.lines) * item.words.line;
    }
    return down;
  };
}

function quoteSizer(element, span) {
  const id = element.id;
  const words = inRoom(element.querySelector(`[id="${CSS.escape(`${id}.words`)}"]`), span);
  if (!words) return null;
  const byText = element.querySelector(`[id="${CSS.escape(`${id}.by`)}"]`);
  const by = byText ? inRoom(byText, span) : null;
  const mark = element.querySelector(`[id="${CSS.escape(`${id}.mark`)}"]`);
  const rtl = words.words.anchor === "end";
  const markX = num(mark, "x"), byY = by?.words.y;
  return (left, width) => {
    const edge = rtl ? left + width - (span.x + span.width) : left - span.x;
    if (mark) { mark.setAttribute("x", String(markX + edge)); for (const tspan of mark.querySelectorAll("tspan[x]")) tspan.setAttribute("x", String(markX + edge)); }
    let down = (words.set(left, width) - words.words.lines) * words.words.line;
    if (by) down += (by.set(left, width, byY + down) - by.words.lines) * by.words.line;
    return down;
  };
}

function calloutSizer(element, span) {
  const id = element.id;
  const find = (name) => element.querySelector(`[id="${CSS.escape(`${id}.${name}`)}"]`);
  const panel = find("panel"), bar = find("bar"), titleText = find("title"), wordsText = find("words");
  const words = inRoom(wordsText, span);
  if (!panel || !words) return null;
  const title = titleText ? inRoom(titleText, span) : null;
  if (titleText && !title) return null;
  const height = num(panel, "height"), wordsY = words.words.y;
  const barRight = bar && num(bar, "x") > span.x + 0.5;
  return (left, width) => {
    panel.setAttribute("x", String(left));
    panel.setAttribute("width", String(width));
    let down = 0;
    if (title) down += (title.set(left, width) - title.words.lines) * title.words.line;
    down += (words.set(left, width, wordsY + down) - words.words.lines) * words.words.line;
    panel.setAttribute("height", String(Math.max(1, height + down)));
    if (bar) {
      bar.setAttribute("x", String(barRight ? left + width - num(bar, "width") : left));
      bar.setAttribute("height", String(Math.max(1, height + down)));
    }
    return down;
  };
}

// Numbers side by side, each in a cell of an even share of the width: each value as large
// as its cell lets it be (`grow` times larger than it is drawn at most), its label wrapped in
// its cell.
function statsSizer(element, span, { grow = 1 } = {}) {
  const id = element.id, cells = [];
  for (let n = 0; n < 50; n += 1) {
    const value = element.querySelector(`[id="${CSS.escape(`${id}.${n}`)}"]`);
    if (!value) break;
    const label = element.querySelector(`[id="${CSS.escape(`${id}.${n}.label`)}"]`);
    cells.push({ value, label, words: label ? readWords(label) : null, valueWords: readWords(value) });
  }
  if (!cells.length || cells.some((cell) => !cell.valueWords || (cell.label && !cell.words))) return null;
  const count = cells.length;
  const cell = parseFloat(cells[0].valueWords.wrap) || span.width / count;
  const gap = count > 1 ? (span.width - cell * count) / (count - 1) : 0;
  const size = parseFloat(cells[0].value.getAttribute("font-size")) || 40;
  const most = size * grow;
  const widest = Math.max(...cells.map((each) => each.valueWords.paragraphs.flat().reduce((sum, piece) => sum + widthOf(piece.text, piece.look), 0)));
  for (const each of cells) {
    // (Which cell it is in, counted from the left: a right-to-left row reads from the right.)
    const start = each.valueWords.anchor === "middle" ? each.valueWords.x - cell / 2 : each.valueWords.anchor === "end" ? each.valueWords.x - cell : each.valueWords.x;
    each.slot = Math.round((start - span.x) / (cell + gap));
  }
  return (left, width) => {
    const room = Math.max(1, (width - gap * (count - 1)) / count);
    const at = Math.min(most, most * room / Math.max(widest * most / size, 1e-6));
    let down = 0;
    for (const each of cells) {
      const x = left + each.slot * (room + gap);
      each.value.setAttribute("font-size", String(at));
      setWords(each.value, each.valueWords, room, anchored(each.valueWords.anchor, x, room));
      if (each.label) {
        const lines = setWords(each.label, each.words, room, anchored(each.words.anchor, x, room));
        down = Math.max(down, (lines - each.words.lines) * each.words.line);
      }
    }
    return down;
  };
}

// A listing on its panel: as wide as it is given, its lines as they are -- or, narrower than
// they are, all of it set smaller (its size, its panel's padding and its lines' spacing go
// together), as the slide sets it.
function codeSizer(element, span, { natural, grow = 1 } = {}) {
  const panel = element.querySelector(`[id="${CSS.escape(`${element.id}.panel`)}"]`);
  if (!panel) return null;
  const top = num(panel, "y"), height = num(panel, "height");
  // (The width its lines take of themselves at its own size, and how much larger that size
  // is than the one it is drawn at, set smaller to fit.)
  const own = natural || span.width * grow;
  return (left, width) => {
    const scale = grow * Math.min(1, width / own);
    panel.setAttribute("width", String(width / scale));
    panel.setAttribute("x", String(span.x));
    element.setAttribute("transform", `translate(${left} ${top}) scale(${scale}) translate(${-span.x} ${-top})`);
    return height * (scale - 1);
  };
}

// An equation, set smaller where it is given less than its width (never wider than that),
// where its place's alignment puts it.
function mathSizer(element, span, { share = 0.5, grow = 1 } = {}) {
  const at = /translate\(\s*([-\d.e]+)[ ,]+([-\d.e]+)\s*\)/.exec(element.getAttribute("transform") || "");
  if (!at) return null;
  const x = Number(at[1]), y = Number(at[2]);
  const size = num(element, "data-flexo-size", 16);
  let box;
  try { box = element.getBBox(); } catch { return null; }
  // (Its top, a skip above its ink, which moves down as it is set smaller.)
  const top = y + box.y - size * 0.4, tall = box.height + size * 0.8;
  // (Its width at its own size: it may be drawn smaller now, set in less room.)
  const own = span.width * grow;
  return (left, width) => {
    const shown = Math.min(width, own), scale = shown / span.width;
    const nx = left + (width - shown) * share;
    element.setAttribute("transform", `translate(${nx + (x - span.x) * scale} ${top + (y - top) * scale}) scale(${scale})`);
    return tall * (scale - 1);
  };
}

// A table's columns sharing its width as the slide shares it: each as wide as its words make
// it and the rest shared in proportion, or, narrower than they are, each its longest word at
// least and what is left shared among those that want more; their words wrapped in them, the
// rows as tall as their lines, the rules as long as the table.
function shared(natural, least, width) {
  const total = (list) => list.reduce((sum, value) => sum + value, 0);
  if (total(natural) <= width) return natural.map((value) => value * width / total(natural));
  if (total(least) >= width) return total(least) ? least.map((value) => width * value / total(least)) : least;
  const widths = [...least];
  let left = width - total(least);
  for (let round = 0; round < widths.length; round += 1) {
    const wanting = widths.map((_, c) => c).filter((c) => natural[c] - widths[c] > 1e-6);
    const want = wanting.reduce((sum, c) => sum + natural[c] - widths[c], 0);
    if (!wanting.length || left <= 1e-6) break;
    const given = Math.min(left, want);
    const asked = wanting.map((c) => natural[c] - widths[c]);
    wanting.forEach((c, k) => { widths[c] += given * asked[k] / want; });
    left -= given;
  }
  return widths;
}
function tableSizer(element, span) {
  const id = element.id;
  const columns = String(element.getAttribute("data-flexo-columns") || "").split(/\s+/).filter(Boolean).map((pair) => pair.split(",").map(Number));
  if (!columns.length || columns.some((pair) => pair.length !== 2 || pair.some((value) => !Number.isFinite(value)))) return null;
  const natural = columns.map(([value]) => value), least = columns.map(([, value]) => value);
  const find = (name) => element.querySelector(`[id="${CSS.escape(`${id}.${name}`)}"]`);
  // Each cell: its words (or, empty, its frame standing in for them, and its column's name
  // in a header), and the frame it is typed in.
  const rows = [];
  for (let r = 0; r < 400; r += 1) {
    const row = [];
    for (let c = 0; c < columns.length; c += 1) {
      const own = find(`${r}.${c}`), empty = own?.localName === "rect" ? own : null;
      const text = own && !empty ? own : null, words = text ? readWords(text) : null;
      if (text && !words) return null;
      row.push({ text, words, frame: find(`${r}.${c}.cell`) || empty, hint: find(`${r}.${c}.hint`) });
    }
    if (row.every((cell) => !cell.text && !cell.frame)) break;
    rows.push(row);
  }
  if (!rows.length || rows.some((row) => row.some((cell) => !cell.frame))) return null;
  const sample = rows.flat().find((cell) => cell.text);
  const size = parseFloat(sample?.text.getAttribute("font-size")) || 16;
  const pad = size * 0.6, slack = 2 * pad + size * 0.2, vertical = size * 0.35;
  const line = num(element, "data-flexo-line", size * 1.2);
  const top = Math.min(...rows[0].map((cell) => num(cell.frame, "y")));
  const height = rows.reduce((sum, row) => sum + num(row[0].frame, "height"), 0);
  // (Where a row's first baseline is, below its top.)
  const baseline = sample ? num(sample.text, "y") - num(sample.frame, "y") : vertical + size;
  const rtl = rows[0].length > 1 && num(rows[0][0].frame, "x") > num(rows[0][1].frame, "x");
  // Its rules, by where they are: above it, under its header, below it.
  const rules = [0, 1, 2].map((n) => find(`rule${n}`)).filter(Boolean).map((rule) => {
    const level = Number(/M\s*[-\d.e]+\s+([-\d.e]+)/.exec(rule.getAttribute("d") || "")?.[1]);
    return { rule, at: Math.abs(level - top) < 0.5 ? "top" : Math.abs(level - top - height) < 0.5 ? "bottom" : "header" };
  });
  const caption = find("caption"), captionY = num(caption, "y");
  const anchor = (text, x, wide) => {
    const side = text.getAttribute("text-anchor") || "start";
    return side === "middle" ? x + wide / 2 : side === "end" ? x + wide - pad : x + pad;
  };
  const place = (text, x, y) => {
    text.setAttribute("x", String(x));
    for (const span of text.querySelectorAll("tspan[x]")) span.setAttribute("x", String(x));
    text.setAttribute("y", String(y));
  };
  return (left, width) => {
    const widths = shared(natural, least, width);
    const total = widths.reduce((sum, value) => sum + value, 0);
    const before = (c) => widths.slice(0, c).reduce((sum, value) => sum + value, 0);
    const xs = widths.map((wide, c) => (rtl ? left + total - before(c) - wide : left + before(c)));
    let y = top, header = top;
    rows.forEach((row, r) => {
      const lines = row.map((cell, c) => (cell.text ? setWords(cell.text, cell.words, Math.max(1, widths[c] - slack), anchor(cell.text, xs[c], widths[c]), y + baseline) : 1));
      const tall = line * Math.max(1, ...lines) + 2 * vertical;
      row.forEach((cell, c) => {
        for (const [name, value] of [["x", xs[c]], ["y", y], ["width", widths[c]], ["height", tall]]) cell.frame.setAttribute(name, String(value));
        if (cell.hint) place(cell.hint, anchor(cell.hint, xs[c], widths[c]), y + baseline);
      });
      y += tall;
      if (!r) header = y;
    });
    for (const { rule, at } of rules) rule.setAttribute("d", `M ${left} ${at === "top" ? top : at === "bottom" ? y : header} H ${left + total}`);
    // (Its caption centred under it, as far down as it now ends.)
    if (caption) place(caption, left + total / 2, captionY + y - top - height);
    return y - top - height;
  };
}

// Pictures in a grid, each in a cell of an even share of the width, as large as its cell (and
// its place's height, or the height it was given) lets it be, its caption wrapped under it.
function gallerySizer(element, span) {
  const [columns, gap, picture, most, under, top, centred] = String(element.getAttribute("data-flexo-cells") || "").split(" ").map(Number);
  if (![columns, gap, picture, most, under, top, centred].every(Number.isFinite) || columns < 1) return null;
  const id = element.id, items = [];
  for (let n = 0; n < 500; n += 1) {
    const image = element.querySelector(`[id="${CSS.escape(`${id}.${n}`)}"]`);
    if (!image) break;
    // (A picture drawn as shapes, an SVG, is not set again here: the gallery is shown scaled.)
    if (image.localName !== "image") return null;
    const text = element.querySelector(`[id="${CSS.escape(`${id}.${n}.caption`)}"]`);
    const words = text ? readWords(text) : null;
    if (text && !words) return null;
    items.push({ image, text, words, ratio: num(image, "width", 1) / Math.max(num(image, "height", 1), 1e-6), y: words?.y });
  }
  if (!items.length) return null;
  const middle = centred === 1;
  const rows = Math.ceil(items.length / columns);
  const lines = (list) => Math.max(0, ...list.map((item) => (item.words ? item.words.lines * item.words.line : 0)));
  const caption = lines(items), height = rows * (picture + under + caption) + (rows - 1) * gap;
  // (Where a caption's first baseline is below its picture's box.)
  const below = items.find((item) => item.text);
  const drop = below ? below.y - (top + Math.floor(items.indexOf(below) / columns) * (picture + under + caption + gap) + picture + under) : 0;
  return (left, width) => {
    const cell = Math.max(1, (width - gap * (columns - 1)) / columns);
    const tall = Math.min(cell, most || cell);
    const words = Math.max(0, ...items.filter((item) => item.text).map((item) => linesIn(item.words, cell) * item.words.line));
    const row = tall + under + words;
    items.forEach((item, n) => {
      const r = Math.floor(n / columns), c = n % columns, inRow = Math.min(columns, items.length - r * columns);
      const x = left + (middle ? (columns - inRow) * (cell + gap) / 2 : 0) + c * (cell + gap), y = top + r * (row + gap);
      const wide = Math.min(cell, tall * item.ratio), high = wide / item.ratio;
      for (const [name, value] of [["x", middle ? x + (cell - wide) / 2 : x], ["y", y + (tall - high) / 2], ["width", wide], ["height", high]]) item.image.setAttribute(name, String(value));
      if (item.text) setWords(item.text, item.words, cell, anchored(item.words.anchor, x, cell), y + tall + under + drop);
    });
    return rows * row + (rows - 1) * gap - height;
  };
}

// A drawn thing (a plot, a gallery of drawings) shown at another size, in proportion, about
// its top left -- its height with its width.
function scaledSizer(element, span) {
  let local;
  try { local = element.getBBox(); } catch { return null; }
  if (!local || !local.width) return null;
  // (Its box where it is drawn, through the transform it is placed by -- a plot's -- which it
  // keeps, under the one that sizes it.)
  const own = element.getAttribute("transform") || "";
  const matrix = element.transform?.baseVal?.consolidate?.()?.matrix;
  const box = matrix ? { x: local.x * matrix.a + matrix.e, y: local.y * matrix.d + matrix.f, height: local.height * matrix.d } : local;
  return (left, width) => {
    const scale = width / span.width;
    element.setAttribute("transform", `translate(${left + (box.x - span.x) * scale} ${box.y}) scale(${scale}) translate(${-box.x} ${-box.y}) ${own}`.trim());
    return box.height * (scale - 1);
  };
}

const SIZERS = { text: textSizer, bullets: listSizer, quote: quoteSizer, callout: calloutSizer, stats: statsSizer, code: codeSizer, math: mathSizer, table: tableSizer, plot: scaledSizer,
  gallery: (element, span) => gallerySizer(element, span) || scaledSizer(element, span) };

// How the object `element` (of `kind`) is set again at another width, as a function of its
// left edge and its width (points) returning how much taller it is; null where it is not.
// `span` is where it stands across now ({ x, width }); `options` what a kind needs besides.
export function sizer(element, kind, span, options = {}) {
  // (A text that is one equation displayed is drawn as an equation.)
  const make = SIZERS[element?.getAttribute?.("data-flexo-talk") === "math" ? "math" : kind];
  if (!make || !element) return null;
  try { return make(element, span, options); } catch { return null; }
}

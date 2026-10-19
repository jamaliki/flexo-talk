// A deck's words to check for spelling (spelling.js): each of its fields (deckwords.js) as its
// letters read, with what no dictionary knows blanked -- code and equations, words between
// backticks or dollars, links, and any word with a digit in it (5KKA, H2O, RFdiffusion2) --
// every letter kept where it was, so that a word found misspelt is where it is in the field.
// Read in Node as it is in the studio: it takes nothing from the page.

// Objects whose words are not prose.
const NOT_PROSE = new Set(["Code", "Equation"]);
// In what is written: code and maths.
const WRITTEN = [/`[^`\n]*`/g, /\$[^$\n]*\$/g];
// In the words as they read: links, addresses and words with digits.
const READ = [/https?:\/\/\S+/g, /\S+@\S+\.\S+/g, /[^\s]*\d[^\s]*/g];

const blank = (letters, from, to) => { for (let k = from; k < to; k += 1) if (letters[k] !== "\n") letters[k] = " "; };

// The fields worth checking, each `{ field, text }`: `text` its words as they read (wordsOf,
// finding.js's, given: as `words` already, read for find), blanked as said above.
export function spellingTexts(fields, wordsOf) {
  const texts = [];
  for (const field of fields) {
    if (NOT_PROSE.has(field.name)) continue;
    // (A mechanism's reagents and conditions are formulae: its labels are words.)
    if (field.name === "Mechanism" && field.path?.[field.path.length - 1] !== "label") continue;
    const words = field.words || wordsOf(field.value, field.kind);
    const letters = words.text.split("");
    if (field.kind === "markup" || field.kind === "label") {
      const source = String(field.value ?? "");
      const hidden = new Set();
      for (const pattern of WRITTEN) for (const found of source.matchAll(pattern)) for (let k = found.index; k < found.index + found[0].length; k += 1) hidden.add(k);
      if (hidden.size) letters.forEach((_, k) => { if (hidden.has(words.at[k])) letters[k] = " "; });
    }
    let text = letters.join("");
    for (const pattern of READ) for (const found of text.matchAll(pattern)) blank(letters, found.index, found.index + found[0].length);
    text = letters.join("");
    if (/\p{L}/u.test(text)) texts.push({ field, text });
  }
  return texts;
}

// The misspelt words, in the deck's order: `answers[k]` what the dictionary says of
// `texts[k].text` -- [{ start, end, guesses }] -- less those the deck knows (`known`, its
// `deck.spelling`) and those passed over (`ignored`), whatever their case. Each is a match as
// finding has them: { field, index, start, end, word, guesses }.
export function misspellings(texts, answers, { known = [], ignored = [] } = {}) {
  const skip = new Set([...known, ...ignored].map((word) => String(word).toLowerCase()));
  const found = [];
  texts.forEach((entry, index) => {
    for (const one of answers[index] || []) {
      const word = entry.text.slice(one.start, one.end);
      if (!word.trim() || skip.has(word.toLowerCase())) continue;
      found.push({ field: entry.field, index, start: one.start, end: one.end, word, guesses: one.guesses || [] });
    }
  });
  return found;
}

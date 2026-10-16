// How a deck's TODOs (todos.js) are counted and said: the slides they are on -- of those
// presented and exported, a slide skipped being in neither -- and "2 slides have TODOs", as the
// show starts and as the deck is exported. Read in Node as in the studio: it takes nothing from
// the page.

// The slides of `deck` with TODOs on them, from `matches` (each { field: { slide } }): their
// indices, in order, each once, those skipped left out.
export function slidesWithTodos(deck, matches) {
  const slides = Array.isArray(deck?.slides) ? deck.slides : [];
  return [...new Set(matches.map((match) => match.field.slide))].filter((n) => slides[n] && slides[n].skip !== true).sort((a, b) => a - b);
}

// "1 slide has TODOs", "2 slides have TODOs"; nothing, with none.
export const slidesSaid = (count) => (count ? `${count} ${count === 1 ? "slide has" : "slides have"} TODOs` : "");

// The slide shown at one of its clicks while it is edited, and what is shown anew on it said
// there (flexo_talk.onclick): the stage shows the slide as the audience sees it after that click
// -- what is hidden then a ghost, as what is hidden always is, and what builds in later too --
// and every Show (showing.js, a figure's parts' own) shows and says how the thing is shown from
// that click on.
//
// Under the slide, its clicks: the first click, the one before or after, a new one after the
// last, and the slide as it is edited again. In a Show section, From: Start, Click 1, Click 2,
// New Click -- the click it says how the thing is shown from.
//
// `ctx` is the editor's: slideAt(), slideIndex(), page() (the slide as drawn: its steps),
// editSlide(mutate, options), renderStage() (the stage drawn again: its drawing kept),
// render() (the inspector).

import { h, icon, ui } from "/static/studio/studio.js";
import { showStep } from "/static/kinds/deck/stepping.js";
import { lastClick, clicksOf, removeClick, figurePartAt, setFigurePart, VERBS } from "/static/kinds/deck/shown.js";

if (typeof document !== "undefined" && !document.querySelector('link[href="/static/kinds/deck/showsteps.css"]')) {
  document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/showsteps.css" }));
}

export function showSteps(ctx) {
  let at = null;  // { slide, click }: the click the stage shows; null, the slide as edited
  const stepped = new WeakSet();  // the drawings shown at a click, till they are as drawn again

  // (Another slide gone to, the slide is shown as edited again.)
  const here = () => {
    if (at && at.slide !== ctx.slideIndex()) at = null;
    return at && ctx.slideAt() ? at : null;
  };
  // The clicks the slide has: as many as its builds take, or its last click names.
  const count = () => Math.max(0, (ctx.page()?.steps || 1) - 1, lastClick(ctx.slideAt()));
  const click = () => here()?.click ?? 0;

  function go(next) {
    at = next === null ? null : { slide: ctx.slideIndex(), click: Math.max(0, Math.min(next, count() + 1)) };
    ctx.renderStage();
    ctx.render();
  }

  // The slide's drawing (`svg`, on the stage) shown at the click: as edited, all of it there --
  // as it comes, unless it was shown at a click (`stepped`): a large slide is not gone through
  // at each drawing of it for nothing.
  function apply(svg) {
    if (!svg) return;
    const shown = here();
    if (!shown) { reset(svg); return; }
    showStep(svg, shown.click + 1);
    stepped.add(svg);
  }

  // The slide's drawing as it was drawn: before its first click, all of it there.
  function reset(svg) {
    if (!svg || !stepped.has(svg)) return;
    showStep(svg, 1, { builds: false });
    stepped.delete(svg);
  }

  // Under the slide: its builds, as ever, a click on them showing it at its first; showing it at
  // one, which, and the way to the others.
  function bar(said) {
    const shown = here(), total = count();
    if (!shown) {
      if (!total) return null;
      return h("button.chip.steps-chip", { type: "button", title: said, onclick: () => go(0) }, icon("reveal"),
        `${total + 1} builds`);
    }
    const last = Math.max(total, shown.click);
    const button = (name, title, run, disabled = false) => h("button.steps-button", { type: "button", title, disabled, onclick: run }, icon(name));
    return h("span.steps-bar", {},
      button("left", "Previous Click", () => go(shown.click - 1), shown.click === 0),
      h("span.steps-at", { title: said }, shown.click ? `Click ${shown.click} of ${last}` : "Start"),
      button("right", "Next Click", () => go(shown.click + 1), shown.click >= last),
      button("plus", "New Click", () => go(total + 1), shown.click > total),
      shown.click && shown.click <= lastClick(ctx.slideAt()) ? button("trash", `Remove Click ${shown.click}`, () => remove(shown.click)) : null,
      button("close", "Show the Slide as Edited", () => go(null)));
  }

  // What each click shows anew is said nothing more of: the click taken off the slide, those
  // after it a click sooner.
  function remove(number) {
    ctx.editSlide((slide) => { removeClick(slide, number); }, { label: `Remove Click ${number}` });
    go(Math.min(number, count()));
  }

  // From: the click a Show section says how the thing is shown from.
  function from() {
    const total = count(), shown = here();
    const options = [{ value: "0", label: "Start" }, ...Array.from({ length: total }, (_, index) => ({ value: String(index + 1), label: `Click ${index + 1}` })),
      { value: String(total + 1), label: shown?.click === total + 1 ? `Click ${total + 1}` : "New Click" }];
    return ui.field("From", ui.select({ value: String(click()), key: "show.from", options, onChange: (value) => go(Number(value)) }));
  }

  // A figure's parts, at the click shown: how one is shown (undefined, the slide as edited --
  // the figure's own say), and shown so from it on (false, as edited: the figure's own do it).
  // `figure()`: { at: { region, index }, block, own: the figure's own lists, name(ids) }.
  function figureShownAt(figure, id) {
    if (!here() || !figure?.block) return undefined;
    return figurePartAt(figure.block, id, click(), figure.own || {});
  }
  function figureShowAt(figure, how, ids) {
    if (!here() || !figure?.at || !ids.length) return false;
    const number = click();
    ctx.editSlide((slide) => {
      const block = ctx.blockAt(slide, figure.at);
      if (block && typeof block === "object") setFigurePart(block, ids, how, number, figure.own || {});
    }, { label: `${VERBS[how]} ${figure.name(ids)}${number ? ` from Click ${number}` : ""}` });
    ctx.render();
    return true;
  }

  return { click, count, go, apply, reset, bar, from, previewing: () => Boolean(here()), figureShownAt, figureShowAt };
}

const listed = (numbers) => (numbers.length > 1 ? `${numbers.slice(0, -1).join(", ")} and ${numbers[numbers.length - 1]}` : String(numbers[0]));

// What each click shows anew on `slide`, said -- "Shown anew: the list from clicks 1, 2 and 3" --
// `names`: its objects, each with what it is called ("the list").
export function shownSaid(slide, names) {
  const found = [];
  for (const [block, name] of names) {
    const clicks = clicksOf(block);
    if (clicks.length) found.push(`${name} from ${clicks.length > 1 ? "clicks" : "click"} ${listed(clicks)}`);
  }
  for (const shape of Array.isArray(slide?.shapes) ? slide.shapes : []) {
    const clicks = clicksOf(shape);
    if (clicks.length) found.push(`a shape from ${clicks.length > 1 ? "clicks" : "click"} ${listed(clicks)}`);
  }
  return found.length ? `Shown anew: ${found.join("; ")}` : "";
}

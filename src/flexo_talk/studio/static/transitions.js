// How a slide arrives from the one shown before it: Morph, or nothing (morph.js plays it,
// flexo_talk.morphing writes it into a PowerPoint). The same everywhere:
// - the inspector's Transition, for the slide shown or the slides chosen: None or Morph, how long
//   it takes, and Preview, which plays it on the stage, from the slide before;
// - a mark under the number of each slide that morphs, in the slide list, as PowerPoint's: a
//   click on it plays it;
// - the palette's Morph from Previous Slide (Don't Morph) and Preview Transition.
// Each change is a step of its own ("Morph from Previous Slide", "Change Transition Duration").
//
// `ctx` is the editor's: slides(), pages(), current() (the slide shown), chosen() (the slides
// chosen), editChosen(mutate, options, name), select(index), pageNode(), toast(text).

import { h, ui, icon } from "/static/studio/studio.js";
import { DURATION, LONGEST, SHORTEST, preview, transitionOf, transitionWritten } from "/static/kinds/deck/morph.js";

export function slideTransitions(ctx) {
  dress();
  let playing = null;
  // The slide shown before `index` when presenting: the nearest before it not skipped.
  const shownBefore = (index) => {
    for (let at = index - 1; at >= 0; at -= 1) if (ctx.slides()[at]?.skip !== true) return at;
    return -1;
  };
  const of = (index) => transitionOf(ctx.slides()[index]?.transition);

  // The morph into slide `index` played on the stage, from the slide shown before it.
  function play(index = ctx.current()) {
    playing?.finish();
    const from = shownBefore(index), pages = ctx.pages();
    if (from < 0) { ctx.toast("No slide is shown before this one."); return; }
    if (!pages[from]?.svg || !pages[index]?.svg) return;
    const host = ctx.pageNode();
    if (!host) return;
    playing = preview(host, pages[from], pages[index], of(index) || { kind: "morph", duration: DURATION },
      { onEnd: () => { playing = null; } });
  }

  // The slides `indices` given `transition` (or none), one step named for it.
  function set(indices, transition, name) {
    const written = transitionWritten(transition);
    ctx.editChosen((slide) => {
      if (written === null) delete slide.transition;
      else slide.transition = structuredClone(written);
    }, { label: name }, name);
  }

  // The inspector's Transition, for the slides `indices` (the one shown, or those chosen).
  function section(indices) {
    const ways = indices.map(of);
    const kinds = new Set(ways.map((way) => way?.kind || ""));
    const kind = kinds.size === 1 ? [...kinds][0] : "";
    const seconds = new Set(ways.filter(Boolean).map((way) => way.duration));
    const first = indices.length === 1 && shownBefore(indices[0]) < 0;
    const choice = ui.select({
      value: kind, key: "slide.transition", options: [{ value: "", label: "None" }, { value: "morph", label: "Morph" }],
      title: first ? "No slide is shown before this one" : "",
      onChange: (next) => set(indices, next ? { kind: next, duration: seconds.size === 1 ? [...seconds][0] : DURATION } : null,
        next ? "Morph from Previous Slide" : "Remove Transition"),
    });
    if (first && !kind) choice.disabled = true;
    const rows = [ui.field("", choice)];
    if (kind) {
      const duration = seconds.size === 1 ? [...seconds][0] : null;
      rows.push(ui.field("Duration", ui.number({
        value: duration === DURATION ? null : duration, placeholder: `${DURATION}`, unit: "s", min: SHORTEST, max: LONGEST, step: 0.1,
        key: "slide.transition.duration", current: () => duration ?? DURATION,
        onChange: (next) => set(indices, { kind, duration: next ?? DURATION }, "Change Transition Duration"),
      })));
      if (indices.length === 1 && !first) rows.push(h("div.row", {}, ui.button("Preview", () => play(indices[0]), { small: true, icon: "play" })));
    }
    return h("div.section.transition-section", {}, h("div.section-title", {}, "Transition"), rows);
  }

  // The mark under a slide's number in the slide list, where it morphs from the slide before.
  function badge(slide, index) {
    const way = transitionOf(slide?.transition);
    if (!way) return null;
    return h("button.morph-tag", {
      type: "button", tabindex: -1, title: `Morph, ${way.duration} s`,
      onclick: (event) => { event.stopPropagation(); if (ctx.current() !== index) ctx.select(index); requestAnimationFrame(() => play(index)); },
    }, icon("sparkle"));
  }

  // The palette's, for the slides chosen.
  function commands() {
    const picked = ctx.chosen();
    if (!picked.length) return [];
    const on = picked.every((index) => of(index));
    const many = picked.length > 1 ? `${picked.length} Slides` : "";
    return [
      { icon: "sparkle", label: on ? "Don’t Morph from Previous Slide" : "Morph from Previous Slide", also: ["Morph", "Transition", ...(many ? [many] : [])],
        run: () => set(picked, on ? null : { kind: "morph", duration: DURATION }, on ? "Remove Transition" : "Morph from Previous Slide") },
      ...(of(ctx.current()) && shownBefore(ctx.current()) >= 0 ? [{ icon: "play", label: "Preview Transition", run: () => play() }] : []),
    ];
  }

  return { section, badge, commands, play, key: (slide) => JSON.stringify(transitionOf(slide?.transition)), stop: () => playing?.finish() };
}

function dress() {
  if (typeof document === "undefined" || document.getElementById("flexo-transitions")) return;
  const style = document.createElement("style");
  style.id = "flexo-transitions";
  style.textContent = `
.thumb > .morph-tag { position: absolute; left: 3px; top: 18px; width: 16px; height: 16px; padding: 0; border: 0; border-radius: 4px;
  display: grid; place-items: center; background: none; color: var(--ink-3); cursor: pointer; }
.thumb > .morph-tag:hover { color: var(--accent); background: var(--raised); }
.thumb.on > .morph-tag { color: var(--accent); }
.thumb > .morph-tag svg { width: 11px; height: 11px; }
`;
  document.head.append(style);
}

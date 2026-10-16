// Set Colour… (⇧⌘C) on a slide (the studio's colourkey.js): what is chosen, coloured by a code
// pasted. A slide's objects by their words' colour (a text's, a list's, numbers', a callout's,
// an equation's; a mechanism's arrows), its shapes by theirs (shapecolours.js) -- inside a
// group entered too -- both together, each its own main colour; a figure being edited, its
// shapes chosen (partcolours.js), with the slide's shapes over it too; and with nothing chosen,
// the slide's background.
//
// `ctx` is the slide editor's: studio, shapes (its shapes' editor), pageNode() (the slide's
// drawing), inspector (its panel), typing(), slide() (its number, from 0), slideAt(),
// objects() (those chosen: [{ region, index }]), blockAt(slide, pick), kindOf(block),
// blockName(block), element(region, index), figure() (the figure being edited: { parts },
// else null), partElement(id), chosenOther() (a title, a logo: something chosen that has no
// colour here), editSlide(mutate, options).

import { colourKey, boxAround } from "/static/studio/colourkey.js";
import { shapeColours, shapesBox } from "/static/studio/shapecolours.js";
import { partColours, partsBox } from "/static/kinds/figure/partcolours.js";

// The objects whose words take a colour, by the key it is written as.
export const COLOURED = { text: "colour", bullets: "colour", stats: "colour", callout: "colour", math: "colour", mechanism: "arrow_colour" };

export function deckColours(ctx) {
  // The objects chosen that take a colour, as a kind of colourKey's.
  function objectColours() {
    const slide = ctx.slideAt();
    if (!slide) return null;
    const picks = ctx.objects().filter((pick) => {
      const block = ctx.blockAt(slide, pick);
      return block && COLOURED[ctx.kindOf(block)];
    });
    if (!picks.length) return null;
    const blocks = picks.map((pick) => ctx.blockAt(slide, pick));
    const keys = blocks.map((block) => COLOURED[ctx.kindOf(block)]);
    const values = blocks.map((block, n) => block[keys[n]] ?? null);
    const arrows = keys.every((key) => key === "arrow_colour");
    return {
      noun: picks.length === 1 ? ctx.blockName(blocks[0]) : `${picks.length} Objects`,
      main: 0,
      colours: [{ name: arrows ? "Arrows" : "Text", value: values.every((value) => value === values[0]) ? values[0] : undefined,
        set: (hex) => ctx.editSlide((each) => {
          for (const pick of picks) {
            const block = ctx.blockAt(each, pick);
            const key = block && COLOURED[ctx.kindOf(block)];
            if (key) block[key] = hex;
          }
        }, { label: arrows ? "Change Arrow Colour" : "Change Text Colour" }) }],
    };
  }
  // Nothing chosen: the slide itself, its background.
  function backgroundColours() {
    const slide = ctx.slideAt();
    if (!slide) return null;
    return { noun: `Slide ${ctx.slide() + 1}`, main: 0, colours: [{ name: "Background", value: typeof slide.background === "string" ? slide.background : null,
      set: (hex) => ctx.editSlide((each) => { each.background = hex; }, { label: "Change Background" }) }] };
  }
  function kinds() {
    if (ctx.typing()) return [];
    const figure = ctx.figure();
    const parts = figure ? partColours(figure.parts, { word: "Figure Shape" }) : null;
    const shapes = ctx.shapes.any() ? shapeColours(ctx.shapes) : null;
    // (A figure being edited is the object chosen: its shapes are, not it.)
    const objects = figure ? null : objectColours();
    const found = [parts || objects, shapes].filter(Boolean);
    if (found.length) return found;
    const chosen = figure || ctx.shapes.any() || ctx.objects().length || ctx.chosenOther?.();
    return chosen ? [] : [backgroundColours()].filter(Boolean);
  }
  function anchor() {
    const figure = ctx.figure();
    const boxes = [
      ctx.shapes.any() ? shapesBox(ctx.shapes, ctx.pageNode) : null,
      figure ? partsBox(figure.parts, (id) => ctx.partElement(id)) : boxAround(ctx.objects().map((pick) => ctx.element(pick.region, pick.index))),
    ].filter(Boolean);
    if (!boxes.length) return null;
    return boxAround(boxes.map((box) => ({ getBoundingClientRect: () => box })));
  }
  return colourKey({ kinds, anchor, fallback: () => ctx.inspector, studio: ctx.studio, settled: () => ctx.figure()?.parts.idle?.() });
}

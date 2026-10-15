// A slide's zoom insets and its pictures masked by shapes, for the deck's editor (editor.js).
//
// Add Zoom Inset, with a picture, a figure or a plot chosen: a box beside it showing the middle
// of it magnified, joined to it -- a shape of the slide's (flexo.insets), chosen at once, its
// region's handles on what it magnifies (shapes.js draws it as it is dragged, insets.js).
// Mask with Shape, with a picture chosen and a closed shape over it -- or the shape chosen,
// over a picture -- as Keynote's: the picture shows only inside the shape, which is the
// picture's now (its crop and its mask, flexo.masks); it is moved, sized and cropped again as
// ever. Unmask shows the whole picture again. Each one step in the history, named for it.

import * as F from "/static/studio/freeform.js";
import * as Insets from "/static/studio/insets.js";
import * as Masks from "/static/studio/masks.js";

// The objects an inset magnifies: what the slide draws as a picture of something.
export const MAGNIFIED = new Set(["image", "figure", "plot"]);

// `editor`: what this needs of the deck's editor -- slideAt(), blocksAt(slide, region),
// kindOf(block), blockElement(region, index), pictureOf(element), glueKey(name) and
// glueName(place) (a slide's object by its name, body[0], and back), shapeScale() (the slide's
// points in a shape's unit), frame() (the slide in the shapes' units), editSlide(mutate, options),
// setOption(target, key, value), widthWithin(place, width), chooseShape(index).
export function slideTools(editor) {
  const numbers = (element, name) => {
    const values = (element?.getAttribute(name) || "").split(" ").map(Number);
    return values.length === 4 && values.every(Number.isFinite) ? values : null;
  };
  // What an object of the slide is drawn as -- a picture without its caption -- and its box.
  function drawnAt(place) {
    const element = editor.pictureOf(editor.blockElement(place.region, place.index));
    const box = numbers(element, "data-flexo-box");
    return element?.id && box ? { element, box } : null;
  }

  // -- zoom insets --

  // What an inset magnifies, for shapes.js: its box in the shapes' units, its drawing's id,
  // and the slide's points as the shapes' units.
  function insetSource(spec) {
    const place = editor.glueKey(spec?.of);
    const block = place && editor.blocksAt(editor.slideAt(), place.region)[place.index];
    if (!block || !MAGNIFIED.has(editor.kindOf(block))) return null;
    const found = drawnAt(place);
    if (!found) return null;
    const k = editor.shapeScale();
    return { box: found.box.map((value) => value / k), target: found.element.id, toShapes: { a: 1 / k, b: 0, c: 0, d: 1 / k, e: 0, f: 0 } };
  }
  const canInset = (place) => {
    const block = place && editor.blocksAt(editor.slideAt(), place.region)[place.index];
    return Boolean(block && MAGNIFIED.has(editor.kindOf(block)) && drawnAt(place));
  };
  // A new inset of the object at `place`, beside it, chosen: one step, Add Zoom Inset.
  function addInset(place) {
    if (!canInset(place)) return false;
    const of = editor.glueName(place);
    const source = insetSource({ of });
    if (!source) return false;
    const spec = Insets.fresh(source.box, editor.frame(), { of });
    const index = (editor.slideAt()?.shapes || []).length;
    editor.editSlide((slide) => { slide.shapes = [...(Array.isArray(slide.shapes) ? slide.shapes : []), spec]; }, { label: "Add Zoom Inset" });
    editor.chooseShape(index);
    return true;
  }

  // -- masks --

  // The pictures of the slide, each whole and as kept, in the shapes' units.
  function pictures() {
    const slide = editor.slideAt(), k = editor.shapeScale(), out = [];
    for (const region of editor.regionsOf(slide)) {
      editor.blocksAt(slide, region.key).forEach((block, index) => {
        if (editor.kindOf(block) !== "image") return;
        const place = { region: region.key, index };
        const element = editor.pictureOf(editor.blockElement(place.region, place.index));
        const whole = numbers(element, "data-flexo-whole"), kept = numbers(element, "data-flexo-box");
        if (whole && kept) out.push({ place, whole: whole.map((v) => v / k), kept: kept.map((v) => v / k) });
      });
    }
    return out;
  }
  const overlap = (box, [left, top, right, bottom]) => Math.max(0, Math.min(box[0] + box[2], right) - Math.max(box[0], left)) * Math.max(0, Math.min(box[1] + box[3], bottom) - Math.max(box[1], top));
  // A picture and the shape that would mask it: given the picture (`place`), the shape over it
  // the most -- the one in front, of those alike; given a shape (`shape`, its index), the
  // picture under the most of it. Null when there is none.
  function maskPair({ place = null, shape = null } = {}) {
    const shapes = editor.slideAt()?.shapes || [], all = pictures();
    const bounds = (spec) => F.bounds(spec, F.geometry(spec));
    if (shape !== null) {
      const spec = shapes[shape];
      if (!spec || spec.locked || !Masks.maskable(spec)) return null;
      const reach = bounds(spec);
      const best = all.map((one) => ({ one, area: overlap(one.kept, reach) })).filter((item) => item.area > 0).sort((a, b) => b.area - a.area)[0];
      return best ? { place: best.one.place, shape } : null;
    }
    const one = all.find((item) => item.place.region === place?.region && item.place.index === place?.index);
    if (!one) return null;
    let best = null;
    shapes.forEach((spec, index) => {
      if (!spec || spec.locked || !Masks.maskable(spec)) return;
      const area = overlap(one.kept, bounds(spec));
      if (area > 0 && (!best || area >= best.area)) best = { area, index };
    });
    return best ? { place, shape: best.index } : null;
  }
  // The picture masked by the shape: its crop the shape's box (as far as it is on it), its
  // mask the shape, drawn as large as it was -- and the shape gone. One step, Mask with Shape.
  function maskWith(pair) {
    if (!pair) return false;
    const spec = (editor.slideAt()?.shapes || [])[pair.shape];
    const one = pictures().find((item) => item.place.region === pair.place.region && item.place.index === pair.place.index);
    const made = spec && one ? Masks.fromShape(spec, one.whole) : null;
    if (!made) return false;
    const width = editor.widthWithin(pair.place, Math.round(made.crop[2] * one.whole[2] * editor.shapeScale()));
    editor.editSlide((slide) => {
      const block = editor.blocksAt(slide, pair.place.region)[pair.place.index];
      if (!block) return;
      editor.setOption(block, "crop", made.crop);
      editor.setOption(block, "mask", made.mask);
      editor.setOption(block, "width", width);
      delete block.placeholder;
      slide.shapes = (slide.shapes || []).filter((_, index) => index !== pair.shape);
      if (!slide.shapes.length) delete slide.shapes;
    }, { label: "Mask with Shape" });
    return true;
  }
  const masked = (place) => {
    const block = place && editor.blocksAt(editor.slideAt(), place.region)[place.index];
    return Boolean(block && editor.kindOf(block) === "image" && block.mask != null);
  };
  // The whole picture again, at the scale it was drawn: one step, Unmask.
  function unmask(place) {
    const block = place && editor.blocksAt(editor.slideAt(), place.region)[place.index];
    if (!masked(place)) return false;
    const kept = Array.isArray(block.crop) ? block.crop[2] : 1;
    const width = editor.widthWithin(place, block.width == null ? null : Math.round(block.width / (kept || 1)));
    editor.editSlide((slide) => {
      const b = editor.blocksAt(slide, place.region)[place.index];
      if (!b) return;
      editor.setOption(b, "crop", null);
      editor.setOption(b, "mask", null);
      editor.setOption(b, "width", width);
    }, { label: "Unmask" });
    return true;
  }

  return { insetSource, canInset, addInset, maskPair, maskWith, masked, unmask };
}

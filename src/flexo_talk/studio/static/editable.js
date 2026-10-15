// Make Editable on a slide: a drawing placed as a picture (an Inkscape SVG, a PDF's or an
// Illustrator file's page) made the slide's own shapes, one group where the picture was drawn,
// chosen -- its boxes, lines and words dragged and edited one by one. The studio makes it
// (editable.py); here it is offered and done in one step of the history. With the picture
// chosen: Make Editable (the palette, its right-click menu, the inspector's button and the Mac
// app's Format › Make Editable, which a path's Make Editable shares). For the whole deck: Make
// All Drawings Editable, in the palette, said in a toast with how many.

import { toast } from "/static/studio/studio.js";

// A picture's file that is a drawing, read as shapes (flexo.studio.editable.DRAWING).
const DRAWING = /\.(svg|pdf|ai)(#\d+)?$/i;
export const isDrawing = (block) => typeof block?.image === "string" && DRAWING.test(block.image.trim());

// `editor`: what this needs of the deck's editor -- studio, slideIndex() (the slide shown),
// regions(slide) (its regions' keys), blocksAt(slide, key), apply(document, label) (the deck the
// studio answers with, as one step, its glue as the studio wrote it), chooseShapes(slide,
// indexes) and away(what) (true, and said, while the deck can't be changed: being presented).
export function editableTools(editor) {
  const { studio } = editor;
  let busy = false;

  // How many pictures of drawings the deck has, and on how many slides.
  function count() {
    let pictures = 0;
    const slides = new Set();
    (studio.doc?.slides || []).forEach((slide, number) => {
      for (const key of editor.regions(slide)) {
        for (const block of editor.blocksAt(slide, key)) if (isDrawing(block)) { pictures += 1; slides.add(number); }
      }
    });
    return { pictures, slides: slides.size };
  }

  async function make(action, label) {
    if (busy || editor.away("make pictures editable")) return false;
    busy = true;
    const before = studio.doc;
    // (A large drawing, or all of them, takes a moment: said while it is made.)
    const waiting = setTimeout(() => toast(action.all ? "Making the drawings editable…" : "Making the drawing editable…", { icon: "shape", seconds: 3 }), 400);
    try {
      const result = await studio.api("/api/act", { file: studio.file, document: before, action });
      clearTimeout(waiting);
      // (Changed here meanwhile -- typed in, another's edit come: not put over it.)
      if (studio.doc !== before) { toast("The deck changed while the drawing was made editable: try again.", { icon: "info", seconds: 5 }); return false; }
      editor.apply(result.document, label);
      if (result.select && result.select.slide === editor.slideIndex()) editor.chooseShapes(result.select.slide, [result.select.shape]);
      toast(result.said || "Made editable", { icon: "shape", seconds: result.failed?.length ? 10 : 6 });
      return true;
    } catch (error) {
      clearTimeout(waiting);
      console.error("Make Editable:", error);
      toast(String(error?.message || error), { kind: "error", icon: "error", seconds: 8 });
      return false;
    } finally {
      busy = false;
    }
  }

  // The picture at `at` ({ region, index }) on the slide shown, made its shapes.
  const one = (at) => make({ do: "editable", at: { slide: editor.slideIndex(), region: at.region, index: at.index } }, "Make Editable");
  // Every picture of a drawing in the deck.
  const all = () => make({ do: "editable", all: true }, "Make All Drawings Editable");

  // The chosen picture's command (as the Mac app's Format menu names it), if it is a drawing's.
  const command = (block, at, name) => (isDrawing(block)
    ? { icon: "shape", label: "Make Editable", also: ["Make Drawing Editable", "Convert to Shapes"], hint: `${name}, as its own shapes, to drag and edit one by one`, run: () => one(at) }
    : null);
  // The deck's command, while it has pictures of drawings.
  function allCommand() {
    const { pictures, slides } = count();
    if (!pictures) return null;
    return { icon: "shape", label: "Make All Drawings Editable", also: ["Convert Pictures to Shapes"], hint: `${pictures} ${pictures === 1 ? "picture" : "pictures"} of drawings on ${slides} ${slides === 1 ? "slide" : "slides"}, as their own shapes`, run: () => all() };
  }

  return { one, all, command, allCommand, count };
}

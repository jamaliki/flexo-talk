// Slides copied in one deck and pasted in another: what the deck's editor (editor.js) needs.
//
// A slide copied says where its deck is (`deckFolder`: the folder on the computer its files are
// named from). Pasted in a deck of another folder -- another window of the Mac app, another
// studio in a browser -- the files its slides name (pictures, GIFs, portraits, figure files and
// theirs, plots' Python) are copied into this deck's folder first, each renamed where a file
// of its name is another here (flexo_talk.pasting), and the slides name them so. Pasted in the
// deck they came from, or in another of the same folder, they are what they were.

import { toast } from "/static/studio/studio.js";

// The folder the deck is in, on the computer: the studio's own, and the deck's place in it.
export function deckFolder(studio) {
  const root = String(studio.workspace?.info?.folder || "").replace(/\/+$/, "");
  return root ? `${root}/${studio.folder()}`.replace(/\/+$/, "") : "";
}

// `slides` copied in the deck in `from` (its folder), as they are pasted here: a promise of
// them, naming their files as this deck's folder has them. Should their files not come, the
// slides come as they are, and that is said.
export async function broughtSlides(studio, slides, from) {
  const here = deckFolder(studio);
  if (!from || !here || from === here) return slides;
  try {
    const result = await studio.api("/api/act", { file: studio.file, action: { do: "bring-slides", from, slides } });
    if (result?.missing?.length) {
      const named = result.missing.slice(0, 3).map((name) => `“${name}”`).join(", ");
      toast(`${result.missing.length === 1 ? "A file the slides name isn’t" : `${result.missing.length} files the slides name aren’t`} where they were copied from: ${named}${result.missing.length > 3 ? "…" : ""}`, { icon: "info", seconds: 6 });
    }
    return Array.isArray(result?.slides) && result.slides.length === slides.length ? result.slides : slides;
  } catch (error) {
    toast(`The slides are pasted, but not the files they name: ${error.message}`, { icon: "info", seconds: 6 });
    return slides;
  }
}

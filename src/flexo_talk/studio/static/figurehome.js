// Where a deck's figures are kept: in the deck, as the studio makes every one
// (flexo_talk.embedding). Embed Figure in Deck takes the figure file the chosen figure is kept in
// into the deck -- every slide that shows it, one figure still (the deck's `figures`, each slide
// naming it) -- and Embed All Figures in Deck every figure file the slides show; each is one step
// of the history. In a bundle the file then goes from the bundle, unless something else names it
// (back should the step be undone); in a folder it is its person's, and stays. Export Figure as
// File… writes the chosen figure as a figure file of its own -- saved where its person says,
// the deck keeping its own copy -- or, asked to, into the deck's folder (inside a bundle) for
// the deck to show from then on. Open in Figure Editor opens the chosen figure in a tab of its
// own (flexo.studio.embedded): its Source and layout tree, every edit made to the deck as it is
// made. Python-made figures stay references.

import { h, ui, dialog, toast, same } from "/static/studio/studio.js";

// `editor`: what this needs of the deck's editor -- studio, at() (the figure chosen: { slide,
// region, index }, or null), blockAt(at), render() (the inspector drawn again) and away(what)
// (true, and said, while the deck can't be changed: being presented).
export function figureHome(editor) {
  const { studio } = editor;
  const keptIn = (value) => (typeof value === "string" ? (value.startsWith("#") ? "deck" : value.includes(".py:") ? "python" : "file") : value && typeof value === "object" ? "inline" : null);
  const chosen = () => {
    const at = editor.at();
    const block = at ? editor.blockAt(at) : null;
    return block && "figure" in block ? { at, block, kept: keptIn(block.figure) } : null;
  };
  // Every figure block of the deck, with where it is.
  function figures() {
    const found = [];
    (studio.doc.slides || []).forEach((slide, number) => {
      if (!slide || typeof slide !== "object") return;
      const regions = [["body", slide.body], ["left", slide.left], ["right", slide.right], ...(Array.isArray(slide.columns) ? slide.columns.map((column, index) => [`columns.${index}`, column]) : [])];
      for (const [region, blocks] of regions) {
        (Array.isArray(blocks) ? blocks : []).forEach((block, index) => { if (block && typeof block === "object" && "figure" in block) found.push({ at: { slide: number, region, index }, block }); });
      }
    });
    return found;
  }
  const fileFigures = () => figures().filter(({ block }) => keptIn(block.figure) === "file");

  // An edit the studio makes of the deck (flexo_talk.embedding), one step -- made again on the
  // deck as it is now if it changed while the studio made it.
  async function act(action, label) {
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const sent = studio.doc;
      const result = await studio.api("/api/act", { file: studio.file, document: sent, action });
      if (!same(studio.doc, sent)) continue;
      if (!same(result.document, sent)) studio.change(() => result.document, { label });
      editor.render();
      return result;
    }
    throw new Error("The deck kept changing. Try again.");
  }

  async function embed(at = null) {
    if (editor.away(at ? "embed the figure" : "embed the figures")) return;
    try {
      const result = await act({ do: "embed", ...(at ? { at } : {}) }, at ? "Embed Figure in Deck" : "Embed All Figures in Deck");
      const left = result.skipped?.length ? ` ${result.skipped.join(" ")}` : "";
      // (In a bundle the files go from it, nothing else naming them; a folder's are its person's.)
      const one = (result.embedded ?? 1) === 1;
      const files = !result.embedded ? "" : studio.workspace.info?.bundle
        ? (one ? " Its file goes from the bundle." : " Their files go from the bundle.")
        : (one ? " Its file is left as it is." : " Their files are left as they are.");
      toast(`${result.said}.${files}${left}`, { icon: result.skipped?.length ? "info" : "check", seconds: left ? 8 : 5 });
    } catch (error) { toast(error.message, { kind: "error", icon: "error", seconds: 6 }); }
  }

  // A sheet, as a Mac's Export: the figure as a file of its own, saved where its person says
  // (the Mac's save panel, or the browser's download), the deck keeping its copy -- or, the
  // switch on, written into the deck's folder by the name given, the deck showing that file.
  function exportAsFile(at) {
    const block = at && editor.blockAt(at);
    const kept = keptIn(block?.figure);
    if (!block || !["inline", "deck"].includes(kept)) {
      toast(kept === "file" ? "This figure is kept in a file of its own already." : kept === "python" ? "This figure is made in Python: export it from its Python file." : "Choose a figure to export.", { icon: "info", seconds: 4 });
      return;
    }
    const id = kept === "deck" ? block.figure.slice(1) : String(block.figure?.figure?.id || "figure");
    const app = Boolean(window.pywebview?.api?.save_export);
    const bundle = studio.workspace.info?.bundle;
    let use = false;
    const name = ui.input({ value: `figures/${id.replace(/[^\w.-]+/g, "-")}.yaml`, mono: true });
    const problem = h("div.field-problem", { hidden: true });
    const say = (text) => { problem.hidden = !text; problem.textContent = text || ""; };
    const where = ui.field("Name", name, { hint: bundle ? "Kept inside the bundle, beside the deck" : "In the deck’s folder" });
    where.hidden = true;
    const hint = h("p.export-hint", {});
    const shared = kept === "deck" ? figures().filter(({ block: other }) => other.figure === block.figure).length : 1;
    const words = () => {
      hint.textContent = use
        ? `The deck shows the file instead of its own copy${shared > 1 ? `, on all ${shared} slides that show this figure` : ""}. Edits to the figure are made to the file.`
        : "A Flexo figure file of its own, in the deck’s theme, to open in Flexo or send. The deck keeps its own copy of the figure.";
      const button = [...document.querySelectorAll(".dialog-foot .btn.primary")].pop();
      if (button) button.querySelector(".btn-label").textContent = use || !app ? "Export" : "Next…";
    };
    const toggle = ui.toggle({ value: false, label: "Use the File in the Deck Instead", onChange: (on) => {
      use = on; where.hidden = !on; say(""); words();
      if (on) { name.focus(); const from = name.value.lastIndexOf("/") + 1; name.setSelectionRange(from, name.value.lastIndexOf(".") > from ? name.value.lastIndexOf(".") : name.value.length); }
    } });
    let busy = false;
    const go = async () => {
      if (busy) return;
      if (!use) {
        box.close();
        await studio.exportFiles(["yaml"], at);
        return;
      }
      busy = true;
      try {
        const result = await act({ do: "export-figure", at, name: name.value.trim(), use: true }, "Use Figure File");
        box.close();
        toast(result.said, { icon: "check", seconds: 6 });
      } catch (error) { say(error.message); name.focus(); } finally { busy = false; }
    };
    name.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); go(); } });
    const box = dialog({ title: "Export Figure as File", body: [hint, toggle, where, problem],
      actions: [{ label: "Cancel" }, { label: app ? "Next…" : "Export", kind: "primary", run: () => { go(); return false; } }] });
    words();
  }

  // The chosen figure in a tab of its own: one kept in the deck by its key (the deck's own by
  // its name, one written in its block by its id -- given one first if it has none, or one
  // another figure of the deck has too), one kept in a file of its own as that file.
  async function openInEditor(at) {
    const block = at && editor.blockAt(at);
    const kept = keptIn(block?.figure);
    if (kept === "python") { toast("This figure is made in Python. Edit it in its Python file.", { icon: "info", seconds: 4 }); return; }
    if (kept === "file") {
      const path = `${studio.folder()}${block.figure}`.split("/").reduce((parts, part) => (part === ".." ? parts.slice(0, -1) : part && part !== "." ? [...parts, part] : parts), []).join("/");
      studio.workspace.open(path).catch((error) => toast(`Couldn’t open “${block.figure}”: ${error.message}`, { kind: "error", icon: "error" }));
      return;
    }
    if (!kept) return;
    let key = kept === "deck" ? block.figure.slice(1) : block.figure?.figure?.id;
    const twins = kept === "inline" ? figures().filter(({ block: other }) => typeof other.figure === "object" && other.figure?.figure?.id === key) : [];
    if (kept === "inline" && (!key || twins.length > 1 || (studio.doc.figures && key in studio.doc.figures))) {
      key = `figure-${Date.now().toString(36)}`;
      studio.change((d) => {
        const slide = d.slides?.[at.slide];
        const blocks = at.region.startsWith("columns.") ? slide?.columns?.[Number(at.region.split(".")[1])] : slide?.[at.region];
        const figure = blocks?.[at.index]?.figure;
        if (figure && typeof figure === "object") figure.figure = { ...(figure.figure || {}), id: key };
      }, { label: "Name Figure" });
    }
    // (The studio has the deck as it is here before it is asked for the figure in it.)
    for (let wait = 0; wait < 60 && studio.pendingLocal; wait += 1) {
      await studio.push();
      if (studio.pendingLocal) await new Promise((done) => setTimeout(done, 50));
    }
    studio.workspace.open(`${studio.file}#${key}`).catch((error) => toast(`Couldn’t open the figure: ${error.message}`, { kind: "error", icon: "error" }));
  }

  // The palette's, and the Mac app's menus', by name.
  function commands() {
    const here = chosen(), files = fileFigures();
    return [
      ...(here && ["inline", "deck", "file"].includes(here.kept) ? [{ icon: "external", label: "Open in Figure Editor", hint: "The figure in a tab of its own: its source, its layout", run: () => openInEditor(here.at) }] : []),
      ...(here?.kept === "file" ? [{ icon: "figure", label: "Embed Figure in Deck", hint: `${here.block.figure} written into the deck`, run: () => embed(here.at) }] : []),
      ...(files.length ? [{ icon: "figure", label: "Embed All Figures in Deck", hint: `${files.length} figure${files.length === 1 ? "" : "s"} kept in files of their own`, run: () => embed() }] : []),
    ];
  }
  // The figure's right-click menu's.
  function menuItems(at) {
    const block = editor.blockAt(at), kept = keptIn(block?.figure);
    return [
      ...(["inline", "deck", "file"].includes(kept) ? [{ icon: "external", label: "Open in Figure Editor", run: () => openInEditor(at) }] : []),
      ...(kept === "file" ? [{ icon: "figure", label: "Embed in Deck", run: () => embed(at) }] : []),
    ];
  }
  // File › Export To's Figure as File…, while a figure kept in the deck is chosen.
  function exports() {
    const here = chosen();
    return here && ["inline", "deck"].includes(here.kept)
      ? [{ format: "figure-file", label: "Figure as File…", hint: "The chosen figure as a Flexo figure file of its own", run: () => exportAsFile(here.at) }] : [];
  }

  return { embed, exportAsFile, openInEditor, commands, menuItems, exports, keptIn, fileFigures };
}

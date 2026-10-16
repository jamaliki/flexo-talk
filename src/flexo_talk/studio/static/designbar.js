// The deck's Design bar: one low row under the toolbar of pop-up buttons, each naming what is
// in use -- Theme, Colours, Fonts, Sizes, Background, Slide Size -- and More (the look, the
// logos, the footer, Customise…). Theme opens a grid of this deck's title slide (else its
// first) drawn in each theme. Only in an open menu, and only a theme or a palette, is what the
// pointer is over shown on the slide as it would be, as PowerPoint does; chosen, it is one step
// in the history. It stays open as the slide is edited, as a ribbon's tab does: the toolbar's
// Design (⇧⌘D, View › Show Design) shows and hides it, and Format or Arrange pressed puts it
// away for the inspector's tab. What it needs of the editor (editor.js) comes in `host`.

import { h, clear, icon, ui, dialog, themesFor, themeName, suggestedFonts } from "/static/studio/studio.js";
import { ribbonBar, ribbonSep, pull, drop, closeDrop, dropOpen, redrawDrop, previewer, gallery } from "/static/studio/ribbon.js";
import { SLIDE_SIZES, SIZE_RANGE, slideSize, sized, gallerySlide, withVariant, applyVariant, hasVariant, keyOf, backgroundOf, BACKGROUNDS, fontChoices } from "/static/kinds/deck/designs.js";

if (!document.querySelector('link[href="/static/kinds/deck/designbar.css"]')) {
  document.head.append(h("link", { rel: "stylesheet", href: "/static/kinds/deck/designbar.css" }));
}

// The deck's style settings by the pull-down they are in (the catalogue's `style`).
const STYLE_COLOUR = ["title_role"];
const STYLE_TYPE = ["title_size", "subtitle_size", "body_size", "small_size", "figure_size", "line_height", "title_weight"];
const STYLE_LOOK = ["header", "opening", "sections", "edge", "numbers", "title_align", "align"];
const STYLE_SPACE = ["margin", "paragraph_gap", "indent", "column_gap", "block_gap", "title_gap"];
const ARROWS = [["triangle", "Triangle"], ["stealth", "Stealth"], ["latex", "LaTeX"], ["open", "Open"]];
// Shown open from one visit to the next, for every deck, as a ribbon's tab is.
const KEPT = "flexo-deck-design-bar";

export function designBar(host) {
  const { studio, catalog } = host;
  const doc = () => studio.doc || {};
  const deck = () => doc().deck || {};
  const node = ribbonBar("Design");
  let built = false, open = false;
  const edit = (mutate, options = {}) => studio.change((d) => { d.deck ||= {}; mutate(d.deck, d); if (!Object.keys(d.deck).length) delete d.deck; }, options);
  const setOption = (target, key, value, fallback) => {
    if (value === null || value === undefined || value === "" || value === fallback) delete target[key]; else target[key] = value;
  };
  // A design chosen: one step, named; what is shown of it drawn again. A choice from a menu of
  // them closes the menu (`close`), as a pop-up's does.
  const choose = (variant, label, { close = false } = {}) => {
    if (close) closeDrop(true);
    if (hasVariant(deck(), variant)) return;
    previews.hold();
    edit((d) => applyVariant(d, variant), { label });
    after();
  };
  const after = () => { host.render?.(); refresh(); };

  // -- the live preview: the slide shown, as the design pointed at would draw it --
  const variantKey = (variant) => keyOf(variant, host.index(), host.page()?.hash || "", deck());
  const previews = previewer({
    target: () => host.slideNode(),
    keyOf: variantKey,
    draw: async (variant) => (await ask(host.index(), [variant], true))[0],
  });
  const ask = async (slide, variants, placeholders = false) => {
    if (slide < 0 || !variants.length) return [];
    const found = await studio.api("/api/act", { file: studio.file, document: studio.doc, action: { do: "previews", slide, variants, placeholders } });
    return found?.previews || [];
  };
  // What the pointer is over in an open menu (Theme's, Colours'), shown so: `show(variant)` while
  // over it, none once left or the menu closes.
  const shows = (element, variant) => {
    element.addEventListener("pointerenter", () => previews.show(variant));
    element.addEventListener("focus", () => { if (element.matches(":focus-visible")) previews.show(variant); });
    return element;
  };
  const unshown = (element) => {
    element.addEventListener("pointerleave", () => previews.show(null));
    element.addEventListener("focusout", (event) => { if (!element.contains(event.relatedTarget)) previews.show(null); });
    return element;
  };

  // -- the themes --
  let cards = [];
  const themeOf = () => deck().theme || "paper";
  const themes = gallery({
    label: "Themes",
    name: (item) => themeName(item.card),
    current: () => themeOf(),
    aspect: () => slideSize(deck()).ratio,
    card: (item) => h("span.ribbon-card", { style: { background: item.card.canvas || "#fff", color: item.card.ink || "#222" } },
      h("span.theme-aa", { style: { fontFamily: item.card.font ? `"${item.card.font}", system-ui` : "" } }, "Aa"),
      h("span.theme-tones", {}, [...new Set((item.card.colours || []).map((colour) => String(colour).toLowerCase()))].slice(0, 4).map((colour) => h("span", { style: { background: colour } })))),
    // (What a theme's thumbnail shows: the gallery's slide, and the rest of the deck's design.)
    version: (item) => keyOf(item.value, gallerySlide(doc().slides), doc().slides?.[gallerySlide(doc().slides)], { ...deck(), theme: undefined }),
    thumbs: (items) => ask(gallerySlide(doc().slides), items.map((item) => ({ theme: item.value }))),
    pick: (item) => { if (item.card.problem) return; choose({ theme: item.value === "paper" ? null : item.value }, "Change Theme", { close: true }); },
    preview: (item) => previews.show(item && !item.card.problem ? { theme: item.value === "paper" ? null : item.value } : null),
  });
  const loadThemes = async () => {
    try { cards = await themesFor(studio, { fresh: true }); } catch { return; }
    // (One the deck names that the folder does not have, kept in sight as what is in use.)
    const named = cards.some((card) => card.value === themeOf()) ? [] : [{ value: themeOf(), title: themeOf(), source: "folder" }];
    themes.set([...named, ...cards].map((card) => ({ value: card.value, card })));
    themes.reveal();
    faces();
  };
  const unpreview = () => previews.show(null);
  const themePull = pull({ label: "Theme", title: "Theme", panel: () => [themes.node], className: "theme-pull",
    onOpen: () => { loadThemes(); requestAnimationFrame(() => themes.reveal()); }, onClose: unpreview });
  const cardOf = () => cards.find((card) => card.value === themeOf());
  // The theme's page in small, with its first colours: the Theme button's face.
  const chip = (card) => h("span.ribbon-chip", { style: { background: card?.canvas || "#fff" } },
    [...new Set((card?.colours || []).map((colour) => String(colour).toLowerCase()))].slice(0, 3).map((colour) => h("i", { style: { background: colour } })));

  // -- the pull-downs --
  const strip = (colours) => h("span.palette-strip", {}, (colours || []).slice(0, 5).map((colour) => h("span", { style: { background: colour } })));
  const paletteNow = () => (Array.isArray(deck().palette) ? "" : deck().palette || "default");
  const own = () => (studio.info?.own?.length ? studio.info.own : null);
  const colourSet = (colours) => [...colours].map((colour) => String(colour).toLowerCase()).sort().join();
  const ownName = () => own() && Object.keys(catalog.palettes || {}).find((name) => colourSet(catalog.palettes[name]) === colourSet(own()));
  const paletteName = (name) => (name === "default" ? ownName() || "Theme’s Own" : name || "Custom");
  const coloursOf = (name) => (name === "default" ? own() : name === paletteNow() && studio.info?.order?.length ? studio.info.order : catalog.palettes?.[name]);
  const colours = pull({ label: "Colours", title: "Colours", panel: () => coloursPanel(), onClose: unpreview });
  function coloursPanel() {
    const current = paletteNow();
    const names = [["default"], ...Object.keys(catalog.palettes || {}).filter((name) => name !== ownName()).map((name) => [name])];
    const list = unshown(h("div.palette-choices", { role: "group", "aria-label": "Palette" }, names.map(([name]) => {
      const variant = { palette: name === "default" ? null : name };
      return shows(h(`button.palette-choice${current === name ? ".on" : ""}`, { type: "button", "aria-pressed": String(current === name),
        onclick: () => choose(variant, "Change Palette", { close: true }) }, strip(coloursOf(name)), h("span", {}, paletteName(name))), variant);
    })));
    return [h("div.drop-title", {}, "Palette"), list, h("div.drop-title", {}, "Text"), h("div.drop-body", {}, styleRows(STYLE_COLOUR))];
  }

  const families = () => studio.info?.fonts || {};
  const fonts = pull({ label: "Fonts", title: "Fonts", panel: () => fontsPanel() });
  const fontPicks = () => fontChoices(catalog.fonts || [], suggestedFonts(catalog.fonts || []).filter((name) => name !== "Helvetica Neue" && name !== families().theme).slice(0, 6));
  const fontNow = () => {
    const d = deck();
    return fontPicks().find((choice) => hasVariant(d, choice.variant))?.value ?? null;
  };
  function fontsPanel() {
    const now = fontNow(), theme = families();
    const face = (name) => (name ? `"${name}", var(--font)` : "inherit");
    const list = h("div.drop-choices", { role: "group", "aria-label": "Fonts" }, fontPicks().map((choice) => {
      const title = choice.title ?? (theme.theme_title || theme.theme), body = choice.body ?? theme.theme;
      const name = choice.value ? (choice.title === choice.body ? choice.title : `${choice.title} and ${choice.body}`) : `Theme (${title === body ? body : `${title} and ${body}`})`;
      return h(`button.drop-choice${now === choice.value ? ".on" : ""}`, { type: "button", title: name, "aria-label": name, "aria-pressed": String(now === choice.value),
        onclick: () => choose(choice.variant, "Change Font", { close: true }) },
      h("span.drop-sample", { style: { fontFamily: face(title) } }, "Aa"),
      // (Titles' face over the words', each in itself; one face for both, named once.)
      h("span.drop-pair", {}, h("b", { style: { fontFamily: face(title) } }, choice.value ? title : "Theme"),
        !choice.value || title !== body ? h("span", { style: { fontFamily: face(body) } }, choice.value ? body : title === body ? body : `${title} · ${body}`) : null));
    }));
    const picker = (name, label, placeholder) => ui.field(label, ui.font({ value: deck()[name] || "", options: catalog.fonts || [], placeholder, key: `design.${name}`,
      onChange: (value) => { edit((d) => setOption(d, name, value), { label: "Change Font" }); after(); } }));
    const themes = (family) => (family ? `Theme’s (${family})` : "Same as Body");
    return [h("div.drop-title", {}, "Fonts"), list, h("div.drop-title", {}, "Custom"), h("div.drop-body", {},
      picker("font", "Body", theme.theme ? `Theme’s (${theme.theme})` : "Theme’s"), picker("title_font", "Titles", themes(theme.theme_title)), picker("figure_font", "Figures", themes(theme.theme_figure)))];
  }

  // The deck's own settings, as the catalogue names them, each with its Reset.
  const styleField = (name) => catalog.style?.find((field) => field.name === name);
  const lookOf = () => catalog.looks?.find((item) => item.name === (deck().look || "classic"));
  const keyTitle = (key) => String(key).replace(/_/g, " ").replace(/(^|\s)\w/g, (letter) => letter.toUpperCase());
  const choiceName = (name, choice) => styleField(name)?.labels?.[choice] || ({ start: "Left", middle: "Centre", end: "Right" })[choice] || keyTitle(choice);
  function styleRows(names) {
    const changes = deck().style || {};
    return (catalog.style || []).filter((field) => names.includes(field.name)).map((field) => {
      const fallback = lookOf()?.style?.[field.name] ?? field.default;
      const setStyle = (value) => { edit((d) => { d.style = { ...(d.style || {}) }; setOption(d.style, field.name, value); if (!Object.keys(d.style).length) delete d.style; }, { quiet: true, merge: `style-${field.name}` }); after(); };
      const key = `design.style.${field.name}`;
      let control;
      if (field.kind === "bool") control = ui.select({ value: changes[field.name] === undefined ? "" : String(changes[field.name]), key, options: [{ value: "", label: `Default (${fallback ? "On" : "Off"})` }, { value: "true", label: "On" }, { value: "false", label: "Off" }], onChange: (v) => setStyle(v === "" ? null : v === "true") });
      else if (field.kind === "choice") control = ui.select({ value: changes[field.name] ?? "", key, options: [{ value: "", label: `Default (${choiceName(field.name, fallback)})` }, ...field.choices.map((choice) => ({ value: choice, label: choiceName(field.name, choice) }))], onChange: (v) => setStyle(v || null) });
      else control = ui.number({ value: changes[field.name], placeholder: String(fallback ?? "Auto"), step: "any", unit: /,? in points$/i.test(field.note || "") ? "pt" : undefined, key, onChange: setStyle });
      const set = changes[field.name] !== undefined;
      const id = `design-style-${field.name}`;
      (control.matches?.("input, button") ? control : control.querySelector?.("input, button.select"))?.setAttribute("aria-labelledby", id);
      return h("div.style-row.drop-style", {}, h("span.name", { title: String(field.note || "").replace(/,? in points$/i, "") }, h(`span${set ? ".changed" : ""}`, { id }, field.label || keyTitle(field.name))), control,
        ui.button("", () => setStyle(null), { kind: "ghost", icon: "undo", small: true, title: "Reset", disabled: !set }));
    });
  }

  function lookPanel() {
    const now = deck().look || "classic";
    const tiles = host.tinted(h("div.drop-tiles", { role: "group", "aria-label": "Look" }, (catalog.looks || []).map((item) => {
      const variant = { look: item.name === "classic" ? null : item.name };
      return h(`button.drop-tile${item.name === now ? ".on" : ""}`, { type: "button", title: item.note || "", "aria-pressed": String(item.name === now),
        onclick: () => choose(variant, "Change Look") }, host.lookArt(item.name), h("span", {}, host.lookName(item)));
    })), studio.info?.palette);
    const heads = deck().conventions?.arrowheads || "theme";
    const arrows = ui.segmented({ value: heads, key: "design.arrowheads",
      options: [{ value: "theme", label: "Theme", title: "As the theme draws them" }, ...ARROWS.map(([value, title]) => ({ value, title, label: icon(`head-${value}`) }))],
      onChange: (value) => {
        edit((d) => {
          d.conventions = { ...(d.conventions || {}) };
          if (value === "theme") delete d.conventions.arrowheads; else d.conventions.arrowheads = value;
          if (!Object.keys(d.conventions).length) delete d.conventions;
        }, { label: "Change Arrowheads" });
        after();
      } });
    return [h("div.drop-title", {}, "Look"), tiles, h("div.drop-title", {}, "Slides"), h("div.drop-body", {}, styleRows(STYLE_LOOK)),
      h("div.drop-title", {}, "Arrowheads"), h("div.drop-body", {}, arrows)];
  }

  const sizes = pull({ label: "Sizes", title: "Sizes", panel: () => sizesPanel() });
  function sizesPanel() {
    return [h("div.drop-title", {}, "Text"), h("div.drop-body", {}, styleRows(STYLE_TYPE)), h("div.drop-title", {}, "Spacing"), h("div.drop-body", {}, styleRows(STYLE_SPACE))];
  }

  // The deck's background: the theme's page, none, a colour, a picture filling every slide.
  const background = pull({ label: "Background", title: "Background", panel: () => backgroundPanel() });
  const canvas = () => studio.info?.palette?.canvas || "#ffffff";
  function backgroundPanel() {
    const now = backgroundOf(deck());
    const tile = (variant, label, swatch, on) => h(`button.drop-tile${on ? ".on" : ""}`, { type: "button", title: label, "aria-pressed": String(on),
      onclick: () => choose(variant, "Change Background", { close: true }) }, swatch, h("span", {}, label));
    const swatch = (colour) => h("span.drop-swatch", { style: { background: colour } });
    const custom = h("input.drop-colour", { type: "color", value: now.kind === "colour" ? now.value : "#ffffff", "aria-label": "Custom Colour", title: "Custom Colour" });
    custom.addEventListener("change", () => choose({ background: custom.value.toLowerCase() }, "Change Background"));
    const named = BACKGROUNDS.some(([colour]) => colour === now.value);
    const tiles = h("div.drop-tiles", { role: "group", "aria-label": "Background" },
      tile({ background: null }, "Theme", swatch(now.kind === "theme" ? canvas() : studio.info?.palette?.canvas || canvas()), now.kind === "theme"),
      tile({ background: false }, "None", h("span.drop-swatch.none"), now.kind === "none"),
      BACKGROUNDS.map(([colour, label]) => tile({ background: colour }, label, swatch(colour), now.value === colour)),
      h(`label.drop-tile.custom${now.kind === "colour" && !named ? ".on" : ""}`, { title: "Custom Colour" }, h("span.drop-swatch", { style: { background: now.kind === "colour" && !named ? now.value : "conic-gradient(#e33, #ec3, #3c6, #3ae, #93e, #e33)" } }, custom), h("span", {}, "Custom")),
      h(`button.drop-tile${now.kind === "picture" ? ".on" : ""}`, { type: "button", title: now.kind === "picture" ? now.value : "Picture…", "aria-pressed": String(now.kind === "picture"),
        onclick: async () => { const path = await host.chooseFile({ title: "Background Picture", types: ["image"], action: "Choose" }); if (path) choose({ background: path }, "Change Background", { close: true }); } },
      h("span.drop-swatch.picture", { style: now.kind === "picture" ? { backgroundImage: `url("${studio.raw(now.value)}")` } : {} }, now.kind === "picture" ? null : icon("image")),
      h("span", {}, now.kind === "picture" ? now.value.split("/").pop() : "Picture…")));
    return [h("div.drop-title", {}, "Background"), tiles];
  }

  // The slides' size, by name or in points: one step, every slide drawn again at it.
  const size = pull({ label: "Slide Size", title: "Slide Size", panel: () => sizePanel() });
  function sizePanel() {
    const now = slideSize(deck());
    const set = (wanted, close = false) => {
      if (close) closeDrop(true);
      studio.change((d) => { d.deck = sized(d.deck, wanted); if (!Object.keys(d.deck).length) delete d.deck; }, { label: "Change Slide Size" });
      after();
    };
    const [least, most] = SIZE_RANGE;
    const field = (key, label) => ui.field(label, ui.number({ value: now[key], min: least, max: most, step: 1, unit: "pt", key: `design.size.${key}`,
      onChange: (value) => { if (value) set({ ...slideSize(deck()), [key]: value }); } }));
    return [h("div.drop-title", {}, "Slide Size"), h("div.drop-choices", { role: "group", "aria-label": "Slide Size" }, SLIDE_SIZES.map((each) =>
      h(`button.drop-choice${now.value === each.value ? ".on" : ""}`, { type: "button", "aria-pressed": String(now.value === each.value), onclick: () => set(each.value, true) },
        h("span.ribbon-ratio", { style: { width: `${Math.round(16 * each.width / each.height)}px` } }), h("span.drop-name", {}, each.label === each.value ? each.value : `${each.label} (${each.value})`)))),
    h("div.drop-title", {}, "Custom"), h("div.drop-body.drop-size", {}, field("width", "Width"), field("height", "Height"))];
  }

  // The deck's logos and its footer: the editor's own controls (editor.js's logosControls).
  const logosPanel = () => [h("div.drop-title", {}, "Logos"), h("div.drop-body.logos-section", {}, host.logos())];
  let footerRun = 0;
  function footerPanel() {
    const area = ui.markup({ value: deck().footer || "", placeholder: host.footerHint, colours: false, lines: true, key: "design.footer",
      onInput: (value) => edit((d) => setOption(d, "footer", value), { quiet: true, merge: `deck-footer-${footerRun}`, hold: true }) });
    area.addEventListener("focusin", () => { footerRun += 1; });
    return [h("div.drop-title", {}, "Footer"), h("div.drop-body", {}, area)];
  }

  // More: the look, the logos and the footer, each a panel of its own from here, and the
  // theme's file -- made from it (Customise…), or opened (Edit Theme).
  const more = pull({ label: "More", title: "More", panel: () => morePanel() });
  function morePanel() {
    const file = typeof deck().theme === "string" && /\.(ya?ml|json)$/i.test(deck().theme);
    const row = (glyph, label, run) => h("button.drop-choice.drop-command", { type: "button", onclick: run }, icon(glyph), h("span.drop-name", {}, label));
    const count = host.logoCount();
    return [h("div.drop-choices", { role: "group", "aria-label": "More" },
      row("palette", "Look", () => drop(more, lookPanel)),
      row("image", count ? `Logos (${count})` : "Logos", () => drop(more, logosPanel)),
      row("text", "Footer", () => drop(more, footerPanel)),
      h("div.drop-sep"),
      row(file ? "external" : "pencil", file ? "Edit Theme" : "Customise Theme…", () => {
        closeDrop();
        if (file) studio.workspace.open(studio.folder() + deck().theme); else host.customise();
      }))];
  }

  // -- drawn --
  // What each button shows: what is in use, named where it fits.
  const faces = () => {
    if (!built) return;
    const card = cardOf(), named = card ? themeName(card) : themeOf();
    themePull.show({ face: chip(card), text: named, title: `Theme: ${named}` });
    colours.show({ face: strip(coloursOf(paletteNow()) || []), text: "", title: `Colours: ${paletteName(paletteNow())}` });
    const type = families(), now = fontPicks().find((choice) => choice.value === fontNow());
    const title = now?.title || deck().title_font || type.title || type.theme;
    const body = now?.body || deck().font || type.body || type.theme;
    const face = (name) => ({ fontFamily: name ? `"${name}", var(--font)` : "" });
    fonts.show({ text: h("span.ribbon-font", {}, title && body && title !== body ? [h("b", { style: face(title) }, title), " ", h("span", { style: face(body) }, body)] : h("span", { style: face(title || body) }, title || body || "Theme’s")),
      title: `Fonts: ${title && body && title !== body ? `${title} and ${body}` : title || body || "Theme’s"}` });
    const bg = backgroundOf(deck());
    const bgName = bg.kind === "theme" ? "Theme’s" : bg.kind === "none" ? "None" : bg.kind === "picture" ? bg.value.split("/").pop() : BACKGROUNDS.find(([colour]) => colour === bg.value)?.[1] || "Custom";
    background.show({ face: h(`span.ribbon-chip${bg.kind === "none" ? ".none" : bg.kind === "picture" ? ".picture" : ""}`, { style: bg.kind === "colour" ? { background: bg.value } : bg.kind === "theme" ? { background: canvas() } : {} }, bg.kind === "picture" ? icon("image") : null),
      text: bgName, title: `Background: ${bgName}` });
    const now2 = slideSize(deck());
    const sizeName = now2.value === "custom" ? `${now2.width} × ${now2.height}` : now2.value;
    size.show({ face: h("span.ribbon-ratio", { style: { width: `${Math.max(9, Math.min(20, Math.round(11 * now2.ratio)))}px` } }), text: sizeName,
      title: `Slide Size: ${SLIDE_SIZES.find((each) => each.value === now2.value)?.label || "Custom"} (${now2.width} × ${now2.height} pt)` });
  };
  // The slides drawn at the deck's proportions, here and in the slide list (designbar.css).
  let ratio = null;
  const proportion = () => {
    const now = slideSize(deck()).ratio;
    if (now === ratio) return;
    ratio = now;
    host.root().style.setProperty("--slide-ratio", String(now));
    host.refit?.();
  };
  function build() {
    if (built) return;
    built = true;
    clear(node, themePull, colours, fonts, sizes, ribbonSep(), background, size, ribbonSep(), more);
    loadThemes();
  }
  let later = 0;
  function refresh() {
    proportion();
    if (!open) return;
    faces();
    // (Thumbnails drawn again a moment after the typing on their slide pauses, not at each key.)
    clearTimeout(later);
    later = setTimeout(() => themes.refresh(), 800);
    themes.mark();
    if (dropOpen()) redrawDrop();
  }
  studio.on("change", () => refresh());
  // ⇧⌘D, wherever the keys are in the deck (a field's too): before the slide's own keys, which
  // take ⌘D for Duplicate.
  document.addEventListener("keydown", (event) => {
    if (!studio.active || event.defaultPrevented || document.querySelector(".scrim, .present")) return;
    if (api.key(event)) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  studio.on("drawn", () => { previews.drawn(); if (open) { faces(); if (dropOpen()) redrawDrop(); } });

  function toggle(on = !open, { remember = true } = {}) {
    if (on === open) return open;
    open = on;
    if (on) build();
    node.hidden = !on;
    host.root().classList.toggle("designing", on);
    if (!on) { closeDrop(); previews.show(null); previews.drop(); }
    if (remember) { try { localStorage.setItem(KEPT, on ? "1" : "0"); } catch { /* a private window */ } }
    if (on) { refresh(); themes.refresh(); requestAnimationFrame(() => themes.reveal()); }
    host.shown?.(on);
    // (Told, so the Mac app's View menu names what it will do now: Hide Design.)
    studio.emit("status");
    return open;
  }

  // The deck's files' name when exported: asked for in a sheet, from the toolbar's Export menu.
  function fileName() {
    const input = ui.input({ value: deck().id || "", placeholder: "talk" });
    const said = h("div.export-hint");
    const say = () => { const stem = input.value.trim() || "talk"; said.textContent = `${stem}.pptx, ${stem}.pdf`; };
    input.addEventListener("input", say);
    say();
    const save = () => { edit((d) => setOption(d, "id", input.value.trim() || null), { label: "Change Export File Name" }); host.render?.(); };
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); save(); box.close(); } });
    const box = dialog({ title: "Export File Name", body: [ui.field("Name", input), said], actions: [{ label: "Cancel" }, { label: "Save", kind: "primary", run: save }] });
    setTimeout(() => { input.focus(); input.select(); }, 30);
  }

  const api = {
    node,
    get open() { return open; },
    toggle,
    // Put in the deck's frame, shown if it was left shown (or the deck was left on its old tab).
    start(wasDesign = false) {
      host.root().prepend(node);
      proportion();
      let kept = "0";
      try { kept = localStorage.getItem(KEPT) || "0"; } catch { /* a private window */ }
      if (kept === "1" || wasDesign) toggle(true, { remember: false });
    },
    // Show Design and Hide Design, by the toolbar's key: the palette's, the Mac app's View menu's.
    command: () => ({ icon: "palette", label: open ? "Hide Design" : "Show Design", keys: "⇧⌘D", run: () => toggle() }),
    fileName,
    // A key the bar takes: ⇧⌘D.
    key(event) {
      const mod = event.metaKey || event.ctrlKey;
      if (!mod || !event.shiftKey || event.altKey || event.code !== "KeyD") return false;
      toggle();
      return true;
    },
  };
  return api;
}

// A GIF on a slide (flexo.animated). Its panel says how it plays -- its frames and the
// seconds they take -- and gives the frame a PDF or a PNG shows of it (the picture's
// `still`, from 1), with Play and Pause: the studio's alone. Paused, the slide holds that
// frame, as paper will show it; presenting, and every export that can, plays it.

import { h, ui, stillHref } from "/static/studio/studio.js";
import { describeDrawing } from "/static/kinds/figure/drawing.js";

export const isGif = (path) => /\.gif$/i.test(String(path || "").trim());

// The pictures paused, by the id of what draws each on its slide.
const paused = new Set();
export const isPaused = (id) => paused.has(id);

// The GIFs `id` draws (a picture's own <image>, or those in it: cropped, a window on one).
function imagesOf(svg, id) {
  const drawn = id && svg?.querySelector(`[id="${CSS.escape(id)}"]`);
  if (!drawn) return [];
  return drawn.localName === "image" ? [drawn] : [...drawn.querySelectorAll("image")];
}

// A slide's drawing (`svg`, just put in the page), its paused pictures held still.
export function holdPaused(svg) {
  if (!svg || !paused.size) return;
  for (const id of paused) for (const image of imagesOf(svg, id)) hold(image, true);
}

function hold(image, still) {
  const href = image.getAttribute("href") || "";
  const playing = href.replace(/&still=\d*/g, "");
  const now = still ? stillHref(playing, Number(image.getAttribute("data-flexo-still")) || 1) : playing;
  if (now !== href) image.setAttribute("href", now);
}

// Plays the picture `id` draws on the slide (`svg`), or pauses it: whether it is paused now.
export function togglePaused(svg, id) {
  const still = !paused.has(id);
  if (still) paused.add(id);
  else paused.delete(id);
  for (const image of imagesOf(svg, id)) hold(image, still);
  return still;
}

// How a GIF plays, as its panel says it: "24 frames · 2.4 s" (or "1 frame", one that does not).
export function playedSaid(animation) {
  if (!animation) return "";
  if (animation.frames <= 1) return "1 frame";
  const seconds = animation.seconds >= 10 ? Math.round(animation.seconds) : Math.round(animation.seconds * 10) / 10;
  return `${animation.frames.toLocaleString()} frames · ${seconds.toLocaleString()} s`;
}

// The fields a GIF picture's panel adds, after its file: how it plays and Play or Pause, and
// the frame paper shows. `block`: the picture; `id`: what draws it on the slide; `svg()`: the
// slide's drawing; `write(still)`: the still frame chosen (null: the first); `redraw()`: the
// panel drawn again, once the studio has said how the GIF plays.
export function gifFields({ studio, block, id, svg, write, redraw }) {
  if (!isGif(block?.image)) return [];
  const entry = describeDrawing(studio, block.image);
  const animation = entry.value?.animation ?? null;
  if (!entry.value) entry.asked.then((value) => { if (value?.animation) redraw(); });
  const frames = animation?.frames || null;
  const play = () => {
    togglePaused(svg(), id);
    redraw();
  };
  const still = paused.has(id);
  return [
    ui.field("Animation", h("div.row", {},
      h("span.gif-played", { style: { flex: 1 } }, playedSaid(animation)),
      frames === null || frames > 1
        ? ui.button(still ? "Play" : "Pause", play, { small: true, kind: "ghost", icon: still ? "play" : "pause", title: still ? "Play on the Slide" : "Pause on the Slide" })
        : null)),
    ui.field("Still Frame", ui.number({ value: block.still ?? null, placeholder: "1", min: 1, max: frames ?? undefined, step: 1, start: 1, key: "block.still",
      onChange: (value) => write(value === null || Math.round(value) <= 1 ? null : Math.round(value)) }),
    { hint: "The frame a PDF or PNG shows" }),
  ];
}

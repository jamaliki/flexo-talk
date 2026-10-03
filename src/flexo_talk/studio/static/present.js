// Presenting a deck, as Keynote plays a slideshow. The audience sees the slides alone,
// full screen, and never the notes. The presenter view -- the slide, the next one, the
// notes, the time and the count -- is a second window when there is a second screen
// (the Mac app puts it full screen there; a browser opens a window), the two kept in
// step, and X swaps them; on one screen X shows it in place of the slides, and X again
// the slides. Keys: → Space Return PageDown go on, ← PageUp Backspace go back, Home and
// End, a slide's number then Return goes to it, B a black screen and W a white one (any
// key comes back), Esc ends. A click goes on. After the last slide a black screen says
// the show has ended, and a click ends it.
//
// The window the show is started from leads (`present`): it keeps where the show is and
// draws its own view. The second window (`follow`, presenter.html) draws the other view
// from what the leader sends, and sends back the keys pressed in it. They talk over a
// BroadcastChannel, or, in the Mac app, through the app.

const NEXT = new Set(["ArrowRight", "ArrowDown", "PageDown", " ", "Enter", "click"]);
const BACK = new Set(["ArrowLeft", "ArrowUp", "PageUp", "Backspace"]);
const PAGE = "/static/kinds/deck/presenter.html";

let showing = null;  // the show this window leads, while there is one

// Present `pages()` (each { svg, steps }) from slide `start`, with `slides()`'s notes;
// `done(index)` is told the slide the show ended on. A show already running is left be.
export function present({ pages, slides = () => [], start = 0, done = () => {} }) {
  if (showing || !pages().length) return;
  dress();
  const app = window.pywebview?.api || null;
  const id = Math.random().toString(36).slice(2, 10);
  const root = el("div", "present ss-root");
  const state = { index: 0, step: 1, blank: "", ended: false, swapped: false, typed: "", started: Date.now(), seq: 0 };
  let deck = null;
  let drawnFrom = [];
  let link = null;
  let popup = null;
  let paired = false;
  let full = "";  // "page" (the Fullscreen API) or "app" (the Mac window's), if this show entered it
  const hintUntil = Date.now() + 3000;

  // The slides as they are now: the deck redrawn as it is edited is shown as it comes.
  const current = () => {
    const now = [pages(), slides()];
    if (deck && now[0] === drawnFrom[0] && now[1] === drawnFrom[1]) return deck;
    drawnFrom = now;
    deck = { seq: (deck?.seq || 0) + 1, slides: now[0].map((page, index) => ({
      svg: page?.svg || "", steps: Math.max(1, page?.steps || 1), notes: String(now[1][index]?.notes || "") })) };
    if (paired) link?.send({ type: "deck", deck });
    return deck;
  };
  const show = () => {
    const { slides: all } = current();
    if (!all.length) { finish(); return; }
    if (state.index >= all.length) Object.assign(state, { index: all.length - 1, step: 1 });
    state.step = Math.min(state.step, all[state.index].steps);
    state.seq += 1;
    draw(root, state.swapped ? "presenter" : "audience", deck, state, {
      paired, press, hint: !paired && Date.now() < hintUntil ? "Press X for the presenter view · Esc to end" : "" });
    if (paired) link?.send({ type: "state", state: { ...state } });
  };
  const go = (index) => {
    Object.assign(state, { index: Math.max(0, Math.min(index, deck.slides.length - 1)), step: 1, ended: false });
    show();
  };
  const next = () => {
    const slide = deck.slides[state.index];
    if (state.ended) { finish(); return; }
    if (state.step < slide.steps) state.step += 1;
    else if (state.index < deck.slides.length - 1) Object.assign(state, { index: state.index + 1, step: 1 });
    else state.ended = true;
    show();
  };
  const back = () => {
    if (state.ended) state.ended = false;
    else if (state.step > 1) state.step -= 1;
    else if (state.index > 0) Object.assign(state, { index: state.index - 1, step: deck.slides[state.index - 1].steps });
    show();
  };
  // A key pressed in either window, or "click".
  function press(key) {
    if (!deck) return;
    if (/^[0-9]$/.test(key)) { state.typed = (state.typed + key).slice(-4); show(); return; }
    if (state.typed && ["Enter", "Backspace", "Escape"].includes(key)) {
      const typed = state.typed;
      state.typed = key === "Backspace" ? typed.slice(0, -1) : "";
      if (key === "Enter") go(Number(typed) - 1); else show();
      return;
    }
    if (key === "Escape") { finish(); return; }
    const letter = key.length === 1 ? key.toLowerCase() : "";
    if (letter === "b" || letter === "w") {
      const colour = letter === "b" ? "black" : "white";
      state.blank = state.blank === colour ? "" : colour;
      show();
    } else if (letter === "x") { state.swapped = !state.swapped; show(); }
    else if (state.blank) { state.blank = ""; show(); }
    else if (NEXT.has(key)) next();
    else if (BACK.has(key)) back();
    else if (key === "Home") go(0);
    else if (key === "End") go(deck.slides.length - 1);
  }

  // -- the second window --
  const receive = (message) => {
    if (message?.type === "hello") {
      paired = true;
      link.send({ type: "deck", deck: current() });
      link.send({ type: "state", state: { ...state } });
    } else if (message?.type === "key") press(message.key);
    else if (message?.type === "bye" && paired) {
      // Its window was closed: the slides are shown here again.
      paired = false;
      state.swapped = false;
      show();
    }
  };
  const pair = () => {
    const url = new URL(`${PAGE}?show=${id}${app?.present_open ? "&via=app" : ""}`, location.href).href;
    if (app?.present_open) {
      // The Mac app opens it full screen on another screen, if there is one, with the
      // slides, as Keynote does: this window shows the presenter view.
      link = viaApp(receive);
      Promise.resolve(app.present_open(url)).then((opened) => {
        if (!opened || showing !== handle) return;
        paired = true;
        state.swapped = true;
        show();
      }, () => {});
    } else if (window.screen?.isExtended && typeof BroadcastChannel === "function") {
      link = viaChannel(id, receive);
      popup = window.open(url, `flexo-presenter-${id}`, "popup,width=1120,height=720");
      paired = Boolean(popup);
    }
  };

  // -- full screen, and leaving it --
  const leftFullScreen = () => {
    if (full === "page" && document.fullscreenElement !== root) { full = ""; finish(); }
  };
  const appLeft = (event) => { if (full === "app" && event.detail === false) { full = ""; finish(); } };
  const enter = () => {
    if (document.fullscreenEnabled && root.requestFullscreen) {
      root.requestFullscreen().then(() => { full = "page"; }, () => {});
    } else if (app?.full_screen) {
      Promise.resolve(app.full_screen(true)).then((changed) => { if (changed) full = "app"; }, () => {});
    }
  };
  // A browser leaves full screen as a window opens, and asks a key or a click for each
  // try: with the presenter's window opened, the slides go full screen at the first key
  // or click here (that click does no more).
  const again = () => {
    if (full || document.fullscreenElement || !document.fullscreenEnabled || !root.requestFullscreen) return false;
    enter();
    return true;
  };

  // -- keys, clicks and the time --
  const keys = (event) => {
    event.stopPropagation();
    // The system's and the app's own keys pass (⌘↩ starts no second show).
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    event.preventDefault();
    if (event.repeat && !NEXT.has(event.key) && !BACK.has(event.key)) return;
    again();
    press(event.key);
  };
  const clicked = (event) => { if (again()) event.stopPropagation(); };
  let idle = 0;
  const moved = () => { root.classList.add("ss-pointer"); clearTimeout(idle); idle = setTimeout(() => root.classList.remove("ss-pointer"), 1500); };
  const timer = setInterval(() => {
    if (drawnFrom[0] !== pages() || drawnFrom[1] !== slides()) show();
    else tick(root, state);
  }, 500);

  function finish() {
    if (showing !== handle) return;
    showing = null;
    clearInterval(timer);
    clearTimeout(idle);
    window.removeEventListener("keydown", keys, true);
    document.removeEventListener("fullscreenchange", leftFullScreen);
    window.removeEventListener("flexo-full-screen", appLeft);
    link?.send({ type: "end" });
    link?.close();
    if (popup && !popup.closed) popup.close();
    app?.present_close?.();
    if (full === "page" && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (full === "app") app.full_screen(false);
    root.remove();
    done(Math.min(state.index, Math.max(0, (deck?.slides.length || 1) - 1)));
  }

  const handle = { finish, press };
  showing = handle;
  document.activeElement?.blur?.();
  state.index = Math.max(0, Math.min(start, pages().length - 1));
  root.addEventListener("mousemove", moved);
  root.addEventListener("click", clicked, true);
  window.addEventListener("keydown", keys, true);
  document.addEventListener("fullscreenchange", leftFullScreen);
  window.addEventListener("flexo-full-screen", appLeft);
  document.body.append(root);
  pair();
  if (!popup) enter();
  show();
  setTimeout(() => { if (showing === handle) show(); }, 3100);  // the hint goes
  return handle;
}

// The second window's page: the view the leader is not showing, from what it sends.
export function follow() {
  dress();
  const query = new URLSearchParams(location.search);
  const root = el("div", "present ss-root");
  let deck = null;
  let state = null;
  const link = query.get("via") === "app" ? viaApp(receive) : viaChannel(query.get("show"), receive);
  const press = (key) => link.send({ type: "key", key });
  function receive(message) {
    if (message?.type === "deck" && !(deck && message.deck.seq <= deck.seq)) deck = message.deck;
    else if (message?.type === "state" && !(state && message.state.seq <= state.seq)) state = message.state;
    else if (message?.type === "end") { link.close(); root.textContent = ""; window.close(); return; }
    else return;
    if (deck && state) draw(root, state.swapped ? "audience" : "presenter", deck, state, { paired: true, press });
  }
  let idle = 0;
  root.addEventListener("mousemove", () => { root.classList.add("ss-pointer"); clearTimeout(idle); idle = setTimeout(() => root.classList.remove("ss-pointer"), 1500); });
  window.addEventListener("keydown", (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    event.preventDefault();
    if (event.repeat && !NEXT.has(event.key) && !BACK.has(event.key)) return;
    press(event.key);
  });
  window.addEventListener("pagehide", () => link.send({ type: "bye" }));
  setInterval(() => { if (state) tick(root, state); }, 500);
  document.body.append(root);
  // Said until the leader answers, in case it was not listening yet.
  link.send({ type: "hello" });
  const hello = setInterval(() => { if (deck && state) clearInterval(hello); else link.send({ type: "hello" }); }, 1000);
}

// -- the two ways the windows talk --

function viaChannel(id, receive) {
  const channel = new BroadcastChannel(`flexo-present-${id}`);
  channel.onmessage = (event) => receive(event.data);
  return { send: (message) => channel.postMessage(message), close: () => channel.close() };
}

// The Mac app passes each message to the other window, which it gives to
// `window.flexoPresentReceive`. A window's calls to the app come a moment after its page.
function viaApp(receive) {
  window.flexoPresentReceive = receive;
  const ready = new Promise((done) => {
    const wait = () => (window.pywebview?.api?.present_send ? done() : setTimeout(wait, 50));
    wait();
  });
  return {
    send: (message) => ready.then(() => window.pywebview.api.present_send(message)).catch(() => {}),
    close: () => { if (window.flexoPresentReceive === receive) window.flexoPresentReceive = null; },
  };
}

// -- drawing --

function draw(root, role, deck, state, { paired, press, hint = "" }) {
  const slide = deck.slides[state.index];
  root.className = `present ss-root ss-${role}${state.blank ? ` ss-${state.blank}` : ""}${root.classList.contains("ss-pointer") ? " ss-pointer" : ""}`;
  root.textContent = "";
  const goto = state.typed ? el("div", "ss-goto", `Go to slide ${state.typed}`, el("small", "", "Return to go · Esc to cancel")) : null;
  if (role === "audience") {
    root.onclick = () => press("click");
    root.append(state.ended ? el("div", "ss-end", "End of slide show — click to exit") : frame(slide, state.step));
    if (!paired && goto) root.append(goto);
    if (hint) root.append(el("div", "ss-hint", hint));
    return;
  }
  root.onclick = null;
  const ahead = state.ended ? null
    : state.step < slide.steps ? [slide, state.step + 1]
      : state.index + 1 < deck.slides.length ? [deck.slides[state.index + 1], 1] : null;
  const shown = state.ended ? el("div", "ss-frame", el("div", "ss-over", "End of slide show")) : frame(slide, state.step);
  shown.onclick = () => press("click");
  shown.classList.add("ss-press");
  const notes = state.ended ? "" : slide.notes.trim();
  const blankWords = { black: "The audience sees a black screen. Press any key to show the slides.",
    white: "The audience sees a white screen. Press any key to show the slides." }[state.blank];
  root.append(...[
    el("div", "ss-bar",
      el("div", "ss-count", state.ended ? "End of slide show"
        : `Slide ${state.index + 1} of ${deck.slides.length}${slide.steps > 1 ? ` · Build ${state.step} of ${slide.steps}` : ""}`),
      el("div", "ss-elapsed", elapsed(state)),
      el("div", "ss-clock", clock())),
    el("div", "ss-main",
      el("div", "ss-current", el("div", "ss-label", "Current"), shown),
      el("div", "ss-side",
        el("div", "ss-label", "Next"),
        ahead ? frame(...ahead) : el("div", "ss-frame", el("div", "ss-over", state.ended ? "" : "End of slide show")),
        el("div", "ss-label", "Notes"),
        el("div", notes ? "ss-notes" : "ss-notes none", notes || "No notes"))),
    el("div", "ss-keys", ["→ Space Return: next", "←: previous", "a number, Return: go to that slide", "B: black",
      "W: white", paired ? "X: swap displays" : "X: show the slides", "Esc: end"].join("   ·   ")),
    blankWords ? el("div", "ss-status", blankWords) : null,
    goto].filter(Boolean));
}

// The clocks, kept going between draws.
function tick(root, state) {
  const shown = root.querySelector(".ss-elapsed");
  if (shown) shown.textContent = elapsed(state);
  const now = root.querySelector(".ss-clock");
  if (now) now.textContent = clock();
}

function elapsed(state) {
  const seconds = Math.max(0, Math.floor((Date.now() - state.started) / 1000));
  const [h, m, s] = [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60];
  return `${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${String(s).padStart(2, "0")}`;
}

function clock() {
  return new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// A slide at a step of its builds, fitted to the box it is put in.
function frame(slide, step) {
  const box = el("div", "ss-slide");
  const svg = stepped(slide?.svg || "", step, slide?.steps || 1);
  const size = svg.match(/viewBox\s*=\s*"\s*[-\d.e]+[\s,]+[-\d.e]+[\s,]+([\d.e]+)[\s,]+([\d.e]+)/);
  box.style.setProperty("--ratio", size && Number(size[2]) ? Number(size[1]) / Number(size[2]) : 16 / 9);
  box.innerHTML = svg;
  const drawing = box.querySelector("svg");
  if (drawing) { drawing.removeAttribute("width"); drawing.removeAttribute("height"); }
  return el("div", "ss-frame", box);
}

// What a slide shows at `step`: the items its lists reveal later, left out.
function stepped(svg, step, steps) {
  if (!svg || steps <= 1 || step >= steps) return svg.replace(/^<\?xml[^>]*>\s*/, "");
  const parsed = new DOMParser().parseFromString(svg, "image/svg+xml");
  parsed.querySelectorAll("[data-flexo-step]").forEach((item) => { if (Number(item.getAttribute("data-flexo-step")) > step) item.remove(); });
  return new XMLSerializer().serializeToString(parsed.documentElement);
}

function el(tag, className, ...children) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const child of children.flat()) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

// The show's own look, the same in both windows.
function dress() {
  if (document.getElementById("flexo-slideshow")) return;
  const style = document.createElement("style");
  style.id = "flexo-slideshow";
  style.textContent = `
.present.ss-root { position: fixed; inset: 0; z-index: 200; display: block; margin: 0; background: #000; color: #f2f2f2;
  font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", sans-serif; overflow: hidden;
  cursor: none; user-select: none; -webkit-user-select: none; }
.present.ss-root.ss-pointer, .present.ss-root.ss-presenter { cursor: default; }
.ss-root.ss-white { background: #fff; }
.ss-root.ss-black > .ss-frame, .ss-root.ss-white > .ss-frame { visibility: hidden; }
.ss-frame { container-type: size; display: grid; place-items: center; min-width: 0; min-height: 0; width: 100%; height: 100%; }
.ss-audience > .ss-frame { position: absolute; inset: 0; }
.ss-slide { width: min(100cqw, calc(100cqh * var(--ratio))); aspect-ratio: var(--ratio); background: #fff; line-height: 0; overflow: hidden; }
.ss-slide svg { display: block; width: 100%; height: 100%; text-rendering: geometricPrecision; }
.ss-slide [data-flexo-placeholder] { display: none; }
.ss-end { position: absolute; inset: 0; display: grid; place-items: center; color: #8c8c8c; font-size: 17px; }
/* A heads-up over the slide, as Keynote's: dark and solid enough to read on any slide. */
.ss-hint { position: absolute; left: 50%; bottom: 24px; transform: translateX(-50%); background: rgba(28,28,30,0.86);
  color: #eee; padding: 7px 14px; border-radius: 9px; font-size: 13px; pointer-events: none; white-space: nowrap;
  box-shadow: 0 4px 18px rgba(0,0,0,0.35); backdrop-filter: blur(8px); }
.present.ss-root.ss-presenter { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; gap: 14px; padding: 18px 22px 12px; background: #161616; }
.ss-bar { display: flex; align-items: baseline; gap: 24px; }
.ss-count { font-size: 19px; color: #e6e6e6; }
.ss-elapsed { margin-left: auto; font-size: 34px; font-weight: 500; font-variant-numeric: tabular-nums; }
.ss-clock { font-size: 19px; color: #9a9a9a; font-variant-numeric: tabular-nums; }
.ss-main { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 24px; min-height: 0; }
.ss-current { display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 8px; min-height: 0; }
.ss-side { display: grid; grid-template-rows: auto minmax(0, 0.9fr) auto minmax(0, 1.1fr); gap: 8px; min-height: 0; }
.ss-presenter .ss-frame { align-items: start; }
.ss-label { font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: #8d8d8d; }
.ss-press { cursor: pointer; }
.ss-over { width: 100%; height: 100%; display: grid; place-items: center; background: #000; outline: 1px solid #2c2c2c; color: #8c8c8c; font-size: 16px; }
.ss-notes { overflow: auto; font-size: 22px; line-height: 1.45; white-space: pre-wrap; color: #f4f4f4; user-select: text; -webkit-user-select: text; }
.ss-notes.none { color: #777; }
.ss-keys { font-size: 12px; color: #8a8a8a; }
.ss-status { position: absolute; top: 14px; left: 50%; transform: translateX(-50%); background: #8f1d16; color: #fff; padding: 6px 12px; border-radius: 8px; font-size: 14px; }
.ss-goto { position: absolute; left: 50%; bottom: 56px; transform: translateX(-50%); background: rgba(38,38,38,0.96); border: 1px solid #555;
  border-radius: 10px; padding: 10px 18px; font-size: 22px; color: #fff; text-align: center; }
.ss-goto small { display: block; font-size: 12px; color: #aaa; }
`;
  document.head.append(style);
}

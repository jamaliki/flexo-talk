// What a click does that can wait until what it chose is seen: done once the frame that shows
// the choice is painted -- the inspector's panel for a part of a figure chosen on the slide,
// say, built and laid out in a task of its own just after, not in the click's, where it kept
// the part's frame from the screen for as long as it took.
//
// `run` is owed at most once at a time: owed again while owed, it is still done once. It is
// done at once should it be wanted sooner (`now`: a key pressed meanwhile reaches it drawn),
// not at all should it be done meanwhile by other means (`drop`), and all the same a little
// later in a window that draws no frames (one hidden, or a page behind another).
export function owing(run, { late = 150 } = {}) {
  let owed = null;
  const go = (mine) => {
    if (owed !== mine) return;
    owed = null;
    clearTimeout(mine.late);
    run();
  };
  return {
    soon() {
      if (owed) return;
      const mine = (owed = {});
      // (Once the frame that shows the choice is on the screen -- and the one after it has
      // begun, so that nothing done here holds that frame up either: a frame callback runs as
      // its frame begins, the task after it once it is drawn.)
      requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(() => go(mine), 0)));
      mine.late = setTimeout(() => go(mine), late);
    },
    now() {
      if (owed) go(owed);
    },
    drop() {
      if (!owed) return;
      clearTimeout(owed.late);
      owed = null;
    },
    get owed() {
      return owed !== null;
    },
  };
}

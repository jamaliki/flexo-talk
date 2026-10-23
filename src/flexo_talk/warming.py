"""A slide's figures laid out ahead of the words typed over them.

Words typed over a figure on a slide that wrap onto another line leave the figure less room:
it is laid out again for it, from what was compiled for it (``flexo.boxfit.kept``). A figure
whose layout was found kept on disk -- every figure of a deck just opened -- was never compiled
in this session, and the first key that wraps waited on its compiling: on the owner's slide of
four proteins, 150 to 250 ms where a key took 20.

So each figure found laid out, as written, while its slide is changed is wished for
(``compose._wish``), and once a drawing of its slide is done and the studio has drawn nothing
for a moment (``QUIET``), it is laid out ahead (``compose.lay_out_ahead``), in that drawing's
own context: compiled as the next drawing would compile it, kept, and given up for any drawing
asked for meanwhile -- wished for again, to be laid out at the next quiet moment. Nothing it
does is seen: what its drawing remembers for its drafts is remembered only when the drawing
that asks for it finds it (``flexo.draft.ahead``).
"""

from __future__ import annotations

import threading
import time
from typing import Any

QUIET = 0.15
"""Seconds the studio has drawn nothing, its slide in focus the same, before its figures are
laid out ahead."""

_WANTED: list[tuple[Any, str] | None] = [None]
_LOCK = threading.Condition()
_RUNNER: list[threading.Thread] = []


def soon(kind: Any, slide: str) -> None:
    """``kind`` (a ``DeckKind``) has drawn with ``slide`` in focus: its figures wished for are
    laid out ahead once it is quiet."""

    with _LOCK:
        _WANTED[0] = (kind, slide)
        if not _RUNNER or not _RUNNER[0].is_alive():
            _RUNNER[:] = [threading.Thread(target=_running, name="figures laid out ahead", daemon=True)]
            _RUNNER[0].start()
        _LOCK.notify()


def _running() -> None:
    while True:
        with _LOCK:
            while _WANTED[0] is None:
                _LOCK.wait()
            wanted = _WANTED[0]
        time.sleep(QUIET)
        kind, slide = wanted
        with _LOCK:
            if _WANTED[0] is not wanted or kind._drawing:
                continue
            _WANTED[0] = None
        _lay_out(kind, slide)


def _lay_out(kind: Any, slide: str) -> None:
    from flexo.draft import GivenUp, given_up_when

    from flexo_talk import compose

    def busy() -> bool:
        return bool(kind._drawing) or _WANTED[0] is not None

    for key, wish in compose.wishes(slide):
        context, args, options = wish
        if busy():
            return
        try:
            context.run(_laid_out, given_up_when, busy, compose.lay_out_ahead, args, options)
        except GivenUp:
            return  # (wished for still: laid out at the next quiet moment)
        except Exception:  # (the drawing that asks for it says what is wrong with it)
            pass
        compose.wished(key, wish)


def _laid_out(given_up_when, busy, lay_out, args: tuple, options: dict) -> None:
    with given_up_when(busy):
        lay_out(args, options)

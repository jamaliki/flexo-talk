"""A deck's own Python, run in a process of its own.

The studio draws a deck's plots and Python-made figures here (see ``root``): a plot that
never returns is stopped after ``TIMEOUT`` seconds, one that crashes the interpreter (or
calls ``os._exit``) ends only this process, and neither holds up or takes down the app
around the studio. Each folder has its own worker, started when first needed, working in
that folder (so a plot's relative paths mean what its author meant), and leaving by
itself after ``IDLE`` seconds without work. ``flexo-talk`` on the command line runs a
person's own scripts in its own process, as before.

Requests and answers travel as pickles framed by their length, on the worker's standard
input and output; what a deck's Python prints goes to standard error.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import pickle
import select
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

TIMEOUT = 30.0
"""Seconds a plot or a figure may take."""
STARTUP = 45.0
"""Seconds more for a worker's first request, while it imports matplotlib and flexo."""
IDLE = 300.0
"""Seconds a worker waits for work before it leaves."""
COMMAND: list[str] | None = None
"""How to start a worker: this Python by default; an app bundled with its own sets it."""


def root() -> Path | None:
    """The folder whose worker runs a deck's Python now: the studio's folder, while it
    draws or exports (``None`` elsewhere, where the Python runs in this process)."""

    from flexo.studio import folder_root

    return folder_root.get()


# -- this side: asking a worker ---------------------------------------------------------


class Stopped(Exception):
    """The worker did not answer: it took too long, or its process ended."""


class Worker:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.process: subprocess.Popen[bytes] | None = None
        self.lock = threading.Lock()
        self.fresh = True

    def ask(self, request: dict[str, Any], seconds: float) -> dict[str, Any]:
        with self.lock:
            if self.process is None or self.process.poll() is not None:
                self._start()
            process = self.process
            assert process is not None and process.stdin is not None and process.stdout is not None
            wait = seconds + (STARTUP if self.fresh else 0.0)
            try:
                _send(process.stdin, request)
                answer = _receive(process.stdout.fileno(), time.monotonic() + wait)
            except TimeoutError:
                self.stop()
                raise Stopped(f"took longer than {seconds:g} s, and was stopped") from None
            except (EOFError, BrokenPipeError, OSError):
                try:
                    code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    code = -9
                self.stop()
                if code < 0:
                    raise Stopped(f"crashed the Python it ran in (signal {-code})") from None
                raise Stopped(f"quit the Python it ran in (exit code {code})") from None
            self.fresh = False
            return answer

    def _start(self) -> None:
        command = COMMAND or [sys.executable, "-m", "flexo_talk.worker"]
        environment = {**os.environ, "MPLBACKEND": "Agg", "PYTHONUNBUFFERED": "1"}
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=self.folder, env=environment
        )
        self.fresh = True

    def stop(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        if process.poll() is None:
            process.kill()
            with contextlib.suppress(Exception):
                process.wait(timeout=5)
        for stream in (process.stdin, process.stdout):
            with contextlib.suppress(Exception):
                stream.close()


_WORKERS: dict[Path, Worker] = {}
_WORKERS_LOCK = threading.Lock()


def ask(folder: Path, request: dict[str, Any], seconds: float | None = None) -> dict[str, Any]:
    """The answer of ``folder``'s worker to ``request``; ``Stopped`` if it gave none."""

    folder = folder.resolve()
    with _WORKERS_LOCK:
        worker = _WORKERS.get(folder)
        if worker is None:
            worker = _WORKERS[folder] = Worker(folder)
    return worker.ask(request, TIMEOUT if seconds is None else seconds)


class RemotePlot:
    """A plot a worker makes: drawn there at the size and in the face asked for."""

    def __init__(self, draw: Callable[[float, float, str, str, str, dict], tuple[str, list]]) -> None:
        self._draw = draw
        self.said: list[tuple[str, str]] = []
        """What the worker found to say of the plot (maths it could not read), once drawn."""

    def svg(self, width: float, height: float, family: str, identifier: str, *, maths: str, **options: Any) -> str:
        """The plot as ``plot_svg`` draws it; ``options`` (its ``inks``, ``faces``) are passed on as given."""

        svg, self.said = self._draw(width, height, family, identifier, maths, options)
        return svg


def deck_view(deck: Any) -> dict[str, Any]:
    """What a worker needs to stand in for ``deck`` in a plot function (see ``DeckView``)."""

    palette = deck.palette
    return {
        "theme": deck.theme,
        "palette_name": deck.palette_name,
        "font": deck.font,
        "palette": {"name": palette.name, "paints": dict(palette.paints), "tones": palette.tones,
                    "aliases": palette.aliases},
        "plot_style": deck.plot_style(),
    }


def stop(folder: Path) -> None:
    """Stop ``folder``'s worker, if it has one: the studio on it has closed."""

    with _WORKERS_LOCK:
        worker = _WORKERS.pop(folder.resolve(), None)
    if worker is not None:
        # Not waiting for its lock: a drawing it is busy with ends now, said as stopped.
        worker.stop()


@atexit.register
def stop_all() -> None:
    with _WORKERS_LOCK:
        workers = list(_WORKERS.values())
        _WORKERS.clear()
    for worker in workers:
        worker.stop()


def _send(stream: Any, message: object) -> None:
    data = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(struct.pack(">Q", len(data)) + data)
    stream.flush()


def _receive(fd: int, deadline: float) -> Any:
    size = struct.unpack(">Q", _exactly(fd, 8, deadline))[0]
    return pickle.loads(_exactly(fd, size, deadline))


def _exactly(fd: int, count: int, deadline: float | None) -> bytes:
    parts, left = [], count
    while left:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                raise TimeoutError
        chunk = os.read(fd, min(left, 1 << 20))
        if not chunk:
            raise EOFError
        parts.append(chunk)
        left -= len(chunk)
    return b"".join(parts)


# -- the other side: the worker ---------------------------------------------------------


class DeckView:
    """What a plot function is given as the deck, in a worker: the deck's theme, its
    palette (``deck.palette.get("tone-1-stroke")``), and its plotting look
    (``with deck.plotting():``)."""

    def __init__(self, data: dict[str, Any]) -> None:
        from flexo.style import Palette

        self.theme = data.get("theme")
        self.palette_name = data.get("palette_name")
        self.font = data.get("font")
        self.palette = Palette(**data["palette"]) if data.get("palette") else None
        self._style = data.get("plot_style") or {}

    def plot_style(self) -> dict[str, Any]:
        return dict(self._style)

    def plotting(self):
        import matplotlib

        from flexo_talk.compose import register_fonts_with_matplotlib

        register_fonts_with_matplotlib()
        return matplotlib.rc_context(self._style)

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            f"a plot is given the deck's theme, palette_name, font, palette, plot_style() and "
            f"plotting(); deck.{name} is not among them"
        )


def serve() -> int:
    """Answer requests on standard input until it closes, or no work comes for ``IDLE``."""

    requests = sys.stdin.buffer
    answers = os.fdopen(os.dup(1), "wb")
    # Whatever a deck's Python prints goes where the app logs, not among the answers.
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    os.environ["MPLBACKEND"] = "Agg"
    while True:
        if not select.select([requests.fileno()], [], [], IDLE)[0]:
            return 0
        try:
            request = _receive(requests.fileno(), None)
        except EOFError:
            return 0
        try:
            answer = _answer(request)
        except KeyboardInterrupt:
            raise
        except BaseException as error:  # SystemExit too: said, and the worker carries on
            answer = {"error": _said(error) + _line(error, request.get("file"))}
        _send(answers, answer)


def _answer(request: dict[str, Any]) -> dict[str, Any]:
    from flexo_talk.document import _takes_argument, import_file

    # A deck's Python runs beside its file, as it does when built on the command line there.
    file = Path(request["file"])
    if Path.cwd() != file.parent:
        os.chdir(file.parent)
    name = request["function"]
    if request["do"] == "plot":
        from flexo_talk.compose import plot_svg

        deck = DeckView(request.get("deck") or {})
        # The file is read inside the deck's plotting look too, as in ``document._plot``.
        with deck.plotting():
            function = _function(import_file(file), name, file)
            figure = function(deck) if _takes_argument(function) else function()
            if not hasattr(figure, "savefig"):
                return {"error": f"{name} did not return a matplotlib figure"}
            said: list[tuple[str, str]] = []
            svg = plot_svg(figure, request["width"], request["height"], request["family"],
                           request["identifier"], maths=request.get("maths", "Latin Modern Math"), said=said,
                           **(request.get("options") or {}))
            return {"svg": svg, "said": said}
    if request["do"] == "figure":
        import flexo
        from flexo.ir.semantic import FigureSpec
        from flexo.serialization import figure_to_document

        made = _function(import_file(file), name, file)()
        spec = made.spec if isinstance(made, flexo.Figure) else made
        if not isinstance(spec, FigureSpec):
            return {"error": f"{name} did not return a flexo figure"}
        return {"document": figure_to_document(spec)}
    return {"error": f"no such request: {request['do']}"}


class _Said(Exception):
    pass


def _function(module: object, name: str, file: Path) -> Callable[..., Any]:
    function = getattr(module, name, None)
    if not callable(function):
        raise _Said(f"{file.name} has no function {name}")
    return function


def _line(error: BaseException, file: str | None) -> str:
    """Where in the deck's own file it went wrong, the last place it passed through."""

    import traceback

    if file is None or isinstance(error, _Said):
        return ""
    lines = [frame.lineno for frame in traceback.extract_tb(error.__traceback__) if frame.filename == file]
    return f" (line {lines[-1]})" if lines else ""


def _said(error: BaseException) -> str:
    if isinstance(error, _Said):
        return str(error)
    if isinstance(error, SystemExit):
        return f"it called sys.exit({'' if error.code is None else repr(error.code)})"
    try:
        from flexo.studio.plain import explain

        return explain(error)
    except Exception:
        return str(error) or type(error).__name__


if __name__ == "__main__":
    sys.exit(serve())

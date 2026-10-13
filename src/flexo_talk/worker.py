"""A deck's own Python, run in processes of its own.

The studio draws a deck's plots and Python-made figures here (see ``root``): a plot that
never returns is stopped after ``TIMEOUT`` seconds, one that crashes the interpreter (or
calls ``os._exit``) ends only its process, and neither holds up or takes down the app
around the studio. A worker works in its folder (so a plot's relative paths mean what its
author meant) and leaves by itself after ``IDLE`` seconds without work -- or as soon as the
app that started it has gone, whatever a plot is doing then. ``flexo-talk`` on the command
line runs a person's own scripts in its own process, as before.

A figure's plots (``kind: plot``, ``flexo.plots``) are drawn here too, in a figure's own
file as on a slide: ``figure_plot`` is who flexo asks to run one apart.

A folder has a small pool of workers: at most ``MOST``. A request takes one that is free,
and a second is started only when the first is busy -- so one plot that never returns
holds up nothing else in its folder: the others draw meanwhile, in another worker, and it
is said to have been stopped when its own time is up. A pool, and not one process for each
plot: starting Python and importing matplotlib takes a second, and a worker that stays
answers the next plot in a few hundredths of one. A small one, and not a process for every
plot asked for at once: three is one for a deck's plot that hangs, one for a figure's, and
one that still draws; more wait their turn, which comes when a time is up. (The studio
draws a folder's documents one at a time; a drawing that waits for a worker gives up its
turn meanwhile -- ``flexo.studio.waiting`` -- or the other documents would wait with it,
however many workers were free.)

A plot's time is its own. A worker imports matplotlib and flexo as it starts and says when
it is ready (``READY``); only then is it asked, and only from then is the plot's time
counted. (Counted from the start of its process, the first plot asked of a worker was
given the time of the worker's start as well, whether or not it ever returned.) What a
worker's start costs -- matplotlib listing the computer's fonts the first time, for many
seconds -- is waited for (``STARTUP``) but never cut short: a request that gives up on a
worker still starting leaves it to finish, for the next one (``NotYet``), where stopping
it would have the next start from nothing.

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
"""Seconds a plot or a figure may take, from when a worker that is ready is asked for it."""
STARTUP = 120.0
"""Seconds a request waits for a worker to start: its Python, and matplotlib and flexo
imported (matplotlib may first list the computer's fonts)."""
IDLE = 300.0
"""Seconds a worker waits for work before it leaves."""
MOST = 3
"""How many workers a folder has at most."""
COMMAND: list[str] | None = None
"""How to start a worker: this Python by default; an app bundled with its own sets it."""
READY = "ready"
"""What a worker says first, once it has imported what a plot needs."""


def root() -> Path | None:
    """The folder whose workers run a deck's Python now: the studio's folder, while it
    draws or exports (``None`` elsewhere, where the Python runs in this process)."""

    from flexo.studio import folder_root

    return folder_root.get()


# -- this side: asking a worker ---------------------------------------------------------


class Stopped(Exception):
    """The worker did not answer: it took too long, or its process ended."""


class NotYet(Stopped):
    """The worker was not asked: it was still starting, or its folder has closed. Asked
    again, it may well answer."""


def duration(value: float) -> str:
    """A time limit as a message says it: ``3 seconds``, ``1 second``."""

    return f"{value:g} second{'' if value == 1 else 's'}"


class Worker:
    """One process, asked one thing at a time by whoever has taken it (``Workers``)."""

    def __init__(self, folder: Path) -> None:
        command = COMMAND or [sys.executable, "-m", "flexo_talk.worker"]
        environment = {**os.environ, "MPLBACKEND": "Agg", "PYTHONUNBUFFERED": "1"}
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=folder, env=environment
        )
        self.ready = False
        self.gone = False
        """Its process has ended, or been stopped: it answers no more."""
        self.left = 0.0
        """When it was last given back (``time.monotonic``)."""
        self.asking = threading.Lock()
        """Held by whoever is waiting on its answer: its pipes are theirs meanwhile."""

    def ask(
        self, request: dict[str, Any], seconds: float, started: Callable[[], None] | None = None
    ) -> dict[str, Any]:
        """Its answer to ``request``, given ``seconds`` from when it is ready and asked
        (``started`` is told when it first is)."""

        process = self.process
        assert process.stdin is not None and process.stdout is not None
        with self.asking:
            try:
                if not self.ready:
                    # Its start is not the plot's time, and is not cut short for it.
                    try:
                        said = _receive(process.stdout.fileno(), time.monotonic() + STARTUP)
                    except TimeoutError:
                        raise NotYet("has not been run yet: Python is still starting here.") from None
                    if said != READY:
                        raise EOFError
                    self.ready = True
                    if started is not None:
                        started()
                _send(process.stdin, request)
                return _receive(process.stdout.fileno(), time.monotonic() + seconds)
            except TimeoutError:
                self._end()
                raise Stopped(f"took longer than {duration(seconds)} and was stopped.") from None
            except (EOFError, BrokenPipeError, OSError):
                stopped = self.gone
                try:
                    code = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    code = -9
                self._end()
                if stopped:
                    raise NotYet("was stopped.") from None
                if code < 0:
                    raise Stopped(f"crashed (signal {-code}).") from None
                raise Stopped(f"quit unexpectedly (exit code {code}).") from None

    def alive(self) -> bool:
        return not self.gone and self.process.poll() is None

    def stop(self) -> None:
        """End its process now. Whoever is waiting on its answer sees it end, and closes
        its pipes: closed under them, their numbers could be another file's by the time
        they are read."""

        self.gone = True
        with contextlib.suppress(OSError):
            self.process.kill()
        if self.asking.acquire(blocking=False):
            try:
                self._end()
            finally:
                self.asking.release()

    def _end(self) -> None:
        """Its process ended, and its pipes closed (by whoever holds ``asking``)."""

        self.gone = True
        process = self.process
        if process.poll() is None:
            with contextlib.suppress(OSError):
                process.kill()
            with contextlib.suppress(Exception):
                process.wait(timeout=5)
        for stream in (process.stdin, process.stdout):
            with contextlib.suppress(Exception):
                stream.close()


class Workers:
    """A folder's workers: at most ``MOST``, each asked one thing at a time."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.all: list[Worker] = []
        """Every one running, busy or free."""
        self.free: list[Worker] = []
        """Those no one is asking, the one last asked last (and taken first: the others
        are left to go idle, and leave)."""
        self.changed = threading.Condition()
        self.closed = False

    def ask(self, request: dict[str, Any], seconds: float) -> dict[str, Any]:
        worker = self._taken()
        try:
            return worker.ask(request, seconds, self._started)
        finally:
            with self.changed:
                if self.closed or worker.gone:
                    worker.stop()
                    with contextlib.suppress(ValueError):
                        self.all.remove(worker)
                else:
                    worker.left = time.monotonic()
                    self.free.append(worker)
                self.changed.notify_all()

    def _taken(self) -> Worker:
        """A worker to ask: one that is free; else a new one, while there are fewer than
        ``MOST`` and none is still starting (a second started beside it would only do the
        same slow start over); else the first to be given back."""

        with self.changed:
            while not self.closed:
                while self.free:
                    worker = self.free.pop()
                    # (Not one about to leave of itself: asked as it left, it would be
                    # taken for a plot that ended its Python.)
                    if worker.alive() and time.monotonic() - worker.left < IDLE - 10:
                        return worker
                    worker.stop()
                    self.all.remove(worker)
                if len(self.all) < MOST and all(worker.ready for worker in self.all):
                    try:
                        worker = Worker(self.folder)
                    except OSError as error:
                        raise Stopped(f"could not be run ({error.strerror or error}).") from None
                    self.all.append(worker)
                    return worker
                self.changed.wait()
            raise NotYet("was stopped.")

    def _started(self) -> None:
        # (A worker is ready: whoever waited for its start may start another.)
        with self.changed:
            self.changed.notify_all()

    def stop(self) -> None:
        """Stop every one: what one is busy with ends now, said as stopped."""

        with self.changed:
            self.closed = True
            workers, self.free = list(self.all), []
            self.changed.notify_all()
        for worker in workers:
            worker.stop()


_WORKERS: dict[Path, Workers] = {}
_WORKERS_LOCK = threading.Lock()


def ask(folder: Path, request: dict[str, Any], seconds: float | None = None) -> dict[str, Any]:
    """The answer of one of ``folder``'s workers to ``request``; ``Stopped`` if it gave none."""

    folder = folder.resolve()
    with _WORKERS_LOCK:
        workers = _WORKERS.get(folder)
        if workers is None:
            workers = _WORKERS[folder] = Workers(folder)
    return workers.ask(request, TIMEOUT if seconds is None else seconds)


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


def figure_plot(asked: dict[str, Any]) -> dict[str, Any] | None:
    """A plot in a figure, drawn by a worker of the studio's folder (``flexo.plots.RUNNER``):
    what ``flexo.plots.run`` answers there -- or, of one that hung or took its worker down,
    what to say (and of one not run yet, that it is to be asked for again). ``None``
    outside the studio, where flexo runs it in this process."""

    from flexo.plots import STOPPED, WAITING

    folder = root()
    if folder is None:
        return None
    target = f"{asked['function']} in {Path(asked['file']).name}"
    try:
        answer = ask(folder, {"do": "figure-plot", **asked})
    except NotYet as waiting:
        return {"said": f"{target} {waiting}", "code": WAITING}
    except Stopped as stopped:
        return {"said": f"{target} {stopped}", "code": STOPPED}
    if "error" in answer:
        return {"said": f"{target} failed: {answer['error']}", "code": "plot.function.failed"}
    return answer


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
    """Stop ``folder``'s workers, if it has any: the studio on it has closed."""

    with _WORKERS_LOCK:
        workers = _WORKERS.pop(folder.resolve(), None)
    if workers is not None:
        # Not waiting for them: a drawing one is busy with ends now, said as stopped.
        workers.stop()


@atexit.register
def stop_all() -> None:
    with _WORKERS_LOCK:
        every = list(_WORKERS.values())
        _WORKERS.clear()
    for workers in every:
        workers.stop()


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
            f"A plot can use the deck's theme, palette_name, font, palette, plot_style() and plotting(), "
            f"but not deck.{name}."
        )


def serve() -> int:
    """Answer requests on standard input until it closes, or no work comes for ``IDLE``."""

    requests = sys.stdin.buffer
    answers = os.fdopen(os.dup(1), "wb")
    # Whatever a deck's Python prints goes where the app logs, not among the answers.
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    os.environ["MPLBACKEND"] = "Agg"
    _leave_with(os.getppid())
    _warm()
    _send(answers, READY)
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


def _leave_with(parent: int, every: float = 1.0) -> None:
    """Leave when the app that started this worker (the process ``parent``) has gone,
    whatever a plot is doing. A Mac app that quits ends at once, stopping no worker; one
    waiting for work sees its requests end, but one in a plot that never returns would
    run on for good."""

    def watch() -> None:
        while os.getppid() == parent:
            time.sleep(every)
        os._exit(0)

    threading.Thread(target=watch, name="leave-with-the-app", daemon=True).start()


def _warm() -> None:
    """What a plot needs, imported before one is asked for (``flexo.plots.warm``:
    matplotlib, which may first list the computer's fonts; and flexo's faces, for a deck's
    plot as for a figure's), so that none of it is counted as a plot's time. Whatever
    fails here is said when a plot is asked for."""

    with contextlib.suppress(Exception):
        import flexo.serialization  # noqa: F401
        from flexo.plots import warm

        import flexo_talk.document  # noqa: F401

        warm()
        import matplotlib  # noqa: F401

        from flexo_talk.compose import register_fonts_with_matplotlib

        register_fonts_with_matplotlib()


def _answer(request: dict[str, Any]) -> dict[str, Any]:
    from flexo_talk.document import _takes_argument, import_file

    # A deck's Python runs beside its file, as it does when built on the command line there.
    file = Path(request["file"])
    if Path.cwd() != file.parent:
        os.chdir(file.parent)
    name = request["function"]
    if request["do"] == "figure-plot":
        from flexo.plots import run

        # (In the look it was sent, the figure's; flexo's faces registered there.)
        return run(request)
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
        return f"sys.exit({'' if error.code is None else repr(error.code)}) was called"
    try:
        from flexo.studio.plain import explain

        return explain(error)
    except Exception:
        return str(error) or type(error).__name__


if __name__ == "__main__":
    sys.exit(serve())

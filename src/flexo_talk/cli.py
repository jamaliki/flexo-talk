"""``flexo-talk build deck.py`` -- build the deck a Python file or a deck document makes.

A Python file names its deck as a function that returns one (``deck.py:talk``,
or a function called ``talk`` by default) or as a module-level ``deck``; a
``.yaml`` or ``.json`` file is a deck document (see ``flexo_talk.document``).
``flexo-talk convert deck.py`` writes a Python deck as a document,
``flexo-talk studio deck.yaml`` opens one in the editor, and ``flexo-talk import talk.pptx``
makes a new deck of a PowerPoint or Keynote one (``flexo_talk.importing``).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import os
import sys
from pathlib import Path

from flexo_talk.deck import Deck
from flexo_talk.export import FORMATS


def load_deck(target: str, theme: str | None = None) -> Deck:
    path, _, name = target.partition(":")
    source = Path(path).resolve()
    if not source.exists():
        raise SystemExit(f"{path}: no such file")
    if source.is_dir():
        raise SystemExit(f"{path} is a folder. Name a deck.py file or a deck document inside it.")
    if source.suffix.lower() in {".yaml", ".yml", ".json"}:
        from flexo_talk.document import DeckDocumentError, read_deck

        try:
            return read_deck(source)
        except DeckDocumentError as error:
            raise SystemExit(f"{path}: {error}") from error
    spec = importlib.util.spec_from_file_location(source.stem, source)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot read {path}.")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(source.parent))
    spec.loader.exec_module(module)
    found = getattr(module, name or "talk", None) or getattr(module, "deck", None)
    if isinstance(found, Deck):
        return found
    if callable(found):
        return found(theme) if theme else found()
    raise SystemExit(f"{path} has no function {name or 'talk'!r} and no deck.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flexo-talk", description="Build slide decks written with flexo-talk.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build a deck: PPTX, PDF, and an SVG and PNG per slide")
    build.add_argument("deck", help="deck.py, or deck.py:function")
    build.add_argument("-o", "--output", default="build", help="directory to write into (default: build)")
    build.add_argument("--theme", help="pass a theme name to the deck function")
    build.add_argument("--formats", default=",".join(FORMATS), help=f"comma-separated: {', '.join(FORMATS)}")
    build.add_argument("--trust", action="store_true",
                       help="run the Python a bundle (.flexo) brings: only for a bundle you trust")
    convert = commands.add_parser("convert", help="write a Python deck as a deck document (YAML or JSON)")
    convert.add_argument("deck", help="deck.py, or deck.py:function")
    convert.add_argument("-o", "--output", help="the document to write (default: the deck's file, as .yaml)")
    convert.add_argument("--theme", help="pass a theme name to the deck function")
    studio = commands.add_parser("studio", help="open a deck document in flexo studio, the editor")
    studio.add_argument("deck", nargs="?", help="talk.flexo, a deck as one file, or talk.yaml, a deck in a folder "
                        "(either made if missing; a new name with no ending is a bundle)")
    studio.add_argument("--port", type=int, default=0, help="the port to serve on (default: any free one)")
    studio.add_argument("--no-browser", action="store_true", help="do not open a browser")
    imported = commands.add_parser("import", help="make a new deck of a PowerPoint (.pptx) or Keynote (.key) deck")
    imported.add_argument("deck", help="talk.pptx or talk.key (only read, never changed)")
    imported.add_argument("-o", "--output", help="the deck to make: talk.flexo, a bundle (default: the deck's name, "
                          "here), or a folder with --folder")
    imported.add_argument("--folder", action="store_true", help="make a folder holding the deck and its pictures")
    imported.add_argument("--force", action="store_true", help="replace what is at the output already")
    imported.add_argument("--quiet", action="store_true", help="say nothing as it goes")
    arguments = parser.parse_args(argv)
    if arguments.command == "import":
        from flexo_talk.importing.cli import run

        return run(arguments)
    if arguments.command == "studio":
        from flexo.studio.server import main as studio_main

        deck = arguments.deck
        if deck and not Path(deck).suffix and not Path(deck).exists():
            deck += ".flexo"  # a new deck is a bundle, one file (talk.yaml for one in a folder)
        options = [*([deck] if deck else []), "--port", str(arguments.port)]
        return studio_main([*options, *(["--no-browser"] if arguments.no_browser else [])], kind="deck")
    try:
        if arguments.command == "convert":
            return _convert(arguments)
        with _bundled(arguments) as target:
            deck = load_deck(target, arguments.theme)
            # A slide skipped (Keynote's Skip Slide) is left out, as the studio's export leaves it.
            deck.slides = [slide for slide in deck.slides if not (getattr(slide, "source", None) or {}).get("skip")]
            if not deck.slides:
                raise ValueError("Every slide is skipped: there is nothing to build.")
            result = deck.build(arguments.output, formats=tuple(arguments.formats.split(",")))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        if os.environ.get("FLEXO_TRACEBACK"):
            raise
        print(f"flexo-talk: {_said(error, arguments.deck)}", file=sys.stderr)
        print("(Set FLEXO_TRACEBACK=1 to show the full traceback.)", file=sys.stderr)
        return 1
    print(result.summary())
    return 0


@contextlib.contextmanager
def _bundled(arguments: argparse.Namespace):
    """The deck to build: as named, or a bundle's (``talk.flexo``), unpacked aside for the
    while, read there and nowhere else, its Python run only with ``--trust``."""

    if not arguments.deck.lower().endswith(".flexo"):
        yield arguments.deck
        return
    from flexo.bundle import Bundle, runs_python
    from flexo.confine import folder_root
    from flexo.studio import code_allowed

    source = Path(arguments.deck)
    with _aside(source) as aside:
        with Bundle(source) as opened:
            python = runs_python(opened)
            if python and not arguments.trust:
                raise ValueError(
                    f"{source.name} runs Python ({', '.join(python[:3])}). Build it with --trust if you trust "
                    "where it came from."
                )
            opened.extract(aside)
            _dated(Path(aside), opened)
            document = Path(aside) / opened.document
        root, allowed = folder_root.set(Path(aside).resolve()), code_allowed.set(bool(arguments.trust))
        try:
            yield str(document)
        finally:
            folder_root.reset(root)
            code_allowed.reset(allowed)


@contextlib.contextmanager
def _aside(source: Path):
    """Where a bundle is unpacked to be built: the same folder each time it is built (one for
    each place a bundle is, in flexo-talk's cache folder), so what was made for it before --
    its figures laid out, its molecules and pictures drawn, each kept by where its files are
    and when each was last changed -- is found again, not made afresh; taken away once it
    is built. A temporary folder while another build of it is under way, or where nothing is
    kept (``FLEXO_TALK_CACHE=0``)."""

    import hashlib
    import shutil
    import tempfile

    setting = os.environ.get("FLEXO_TALK_CACHE", "")
    if setting == "0":
        root = None
    elif setting:
        root = Path(setting)
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Caches/flexo-talk"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "flexo-talk"
    held = None
    if root is not None:
        try:
            import fcntl

            (root / "builds").mkdir(parents=True, exist_ok=True)
            place = root / "builds" / hashlib.sha256(str(source.resolve()).encode("utf-8")).hexdigest()[:16]
            held = open(place.with_suffix(".lock"), "a")  # noqa: SIM115 -- held for the build
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            shutil.rmtree(place, ignore_errors=True)
            place.mkdir()
        except (ImportError, OSError):
            if held is not None:
                held.close()
            held = None
    if held is None:
        with tempfile.TemporaryDirectory(prefix="flexo-bundle-") as aside:
            yield aside
        return
    try:
        yield str(place)
    finally:
        shutil.rmtree(place, ignore_errors=True)
        held.close()  # (and with it, the lock)


def _dated(folder: Path, opened) -> None:
    """Each file unpacked from a bundle dated as the bundle has it -- not as it was unpacked,
    a moment ago -- with its contents' checksum in the nanoseconds, the bundle keeping only
    the second (two apart): a file changed is told from the one before by the date, as a
    file in a folder is, and one not changed is found as it was by the next build."""

    import time

    for name in opened.names:
        info = opened.info(name)
        try:
            second = int(time.mktime((*info.date_time, 0, 0, -1)))
        except (OverflowError, ValueError):
            continue
        stamp = second * 1_000_000_000 + info.CRC % 1_000_000_000
        with contextlib.suppress(OSError):
            os.utime(folder.joinpath(*name.split("/")), ns=(stamp, stamp))


def _said(error: BaseException, target: str) -> str:
    """An error as one line: where in the deck's own code it was raised, if there, and
    what it says (with its kind, when the words are Python's rather than flexo's)."""

    import traceback

    from flexo.diagnostics import FlexoError

    words = str(error).strip() or type(error).__name__
    if isinstance(error, FlexoError):
        words = str(error).splitlines()[0]
    elif not isinstance(error, ValueError):
        words = f"{type(error).__name__}: {words}"
    folder = Path(target.partition(":")[0]).resolve().parent
    own = [
        frame for frame in traceback.extract_tb(error.__traceback__)
        if Path(frame.filename).resolve().is_relative_to(folder) and "site-packages" not in frame.filename
    ]
    if own:
        frame = own[-1]
        return f"{Path(frame.filename).name}, line {frame.lineno}, in {frame.name}: {words}"
    return words


def _convert(arguments: argparse.Namespace) -> int:
    """Write a Python deck as a document. Its plots are saved as SVG files beside
    it (named in the document as images), since a matplotlib figure has no document."""

    from flexo_talk.deck import made
    from flexo_talk.document import deck_document, save_document

    source = Path(arguments.deck.partition(":")[0]).resolve()
    target = Path(arguments.output or source.with_suffix(".yaml")).resolve()
    deck = load_deck(arguments.deck, arguments.theme)
    # Drawn first: each plot is saved as the deck draws it -- at the size of its place,
    # its words the deck's size, its maths set by flexo -- not as matplotlib saves it.
    deck.render()
    saved: list[Path] = []

    def plot(block, where: str) -> dict[str, object]:
        path = target.parent / f"{target.stem}-plot{len(saved) + 1}.svg"
        svg = block.drawn
        if not svg:
            from flexo.text import maths_family

            from flexo_talk.compose import plot_faces, plot_svg

            typography = deck.layout_style.typography
            width = deck.style.width - 2 * deck.style.margin
            svg = plot_svg(made(block.figure), width, width * 0.5, typography.family, path.stem,
                           maths=maths_family(typography), faces=plot_faces(typography))
        target.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8")
        saved.append(path)
        print(f"{where}: Saved the matplotlib plot as {path.name} and added it as an image.")
        # (Named beside the document, as every file is, below; as wide as the plot was given.)
        return {"image": str(path), **({"width": block.width} if block.width is not None else {})}

    document = deck_document(deck, plots=plot)
    _relocate(document, Path.cwd(), target.parent)
    print(save_document(document, target))
    return 0


_FILE_KEYS = ("image", "background", "picture", "theme", "palette")


def _relocate(data: object, origin: Path, destination: Path) -> None:
    """Rewrite the files a document names -- relative to where the deck ran, or whole
    paths -- relative to the document, so they are found beside it wherever it goes."""

    if isinstance(data, list):
        for item in data:
            _relocate(item, origin, destination)
        return
    if not isinstance(data, dict):
        return
    for key, value in list(data.items()):
        if key in _FILE_KEYS and isinstance(value, str) and not value.startswith("#"):
            # A theme or palette is a file only when it is named as one; else it is a name.
            if key not in {"theme", "palette"} or value.lower().endswith((".yaml", ".yml", ".json")):
                data[key] = _beside(value, origin, destination)
        elif key in {"gallery", "people"} and isinstance(value, list):
            data[key] = [_beside(item, origin, destination) if isinstance(item, str) else item for item in value]
            _relocate(data[key], origin, destination)
        elif key == "figure" and isinstance(value, dict):
            # A figure written in the deck names the pictures its parts draw as their sources.
            for node in value.get("nodes") or []:
                properties = node.get("properties") if isinstance(node, dict) else None
                if isinstance(properties, dict) and isinstance(properties.get("source"), str):
                    properties["source"] = _beside(properties["source"], origin, destination)
        elif isinstance(value, dict | list):
            _relocate(value, origin, destination)


def _beside(name: str, origin: Path, destination: Path) -> str:
    path = Path(name) if Path(name).is_absolute() else origin / name
    if not path.exists():
        return name
    try:
        return os.path.relpath(path, destination)
    except ValueError:  # on another drive: only the whole path reaches it
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())

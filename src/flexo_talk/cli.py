"""``flexo-talk build deck.py`` -- build the deck a Python file or a deck document makes.

A Python file names its deck as a function that returns one (``deck.py:talk``,
or a function called ``talk`` by default) or as a module-level ``deck``; a
``.yaml`` or ``.json`` file is a deck document (see ``flexo_talk.document``).
``flexo-talk convert deck.py`` writes a Python deck as a document, and
``flexo-talk studio deck.yaml`` opens one in the editor.
"""

from __future__ import annotations

import argparse
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
        raise SystemExit(f"{path} is a folder: name a deck.py or a deck document in it")
    if source.suffix.lower() in {".yaml", ".yml", ".json"}:
        from flexo_talk.document import DeckDocumentError, read_deck

        try:
            return read_deck(source)
        except DeckDocumentError as error:
            raise SystemExit(f"{path}: {error}") from error
    spec = importlib.util.spec_from_file_location(source.stem, source)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot read {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(source.parent))
    spec.loader.exec_module(module)
    found = getattr(module, name or "talk", None) or getattr(module, "deck", None)
    if isinstance(found, Deck):
        return found
    if callable(found):
        return found(theme) if theme else found()
    raise SystemExit(f"{path} has no function {name or 'talk'!r} and no deck")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flexo-talk", description="Build slide decks written with flexo-talk.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build a deck: PPTX, PDF, and an SVG and PNG per slide")
    build.add_argument("deck", help="deck.py, or deck.py:function")
    build.add_argument("-o", "--output", default="build", help="directory to write into (default: build)")
    build.add_argument("--theme", help="pass a theme name to the deck function")
    build.add_argument("--formats", default=",".join(FORMATS), help=f"comma-separated: {', '.join(FORMATS)}")
    convert = commands.add_parser("convert", help="write a Python deck as a deck document (YAML or JSON)")
    convert.add_argument("deck", help="deck.py, or deck.py:function")
    convert.add_argument("-o", "--output", help="the document to write (default: the deck's file, as .yaml)")
    convert.add_argument("--theme", help="pass a theme name to the deck function")
    studio = commands.add_parser("studio", help="open a deck document in flexo studio, the editor")
    studio.add_argument("deck", nargs="?", help="deck.yaml (made if missing)")
    studio.add_argument("--port", type=int, default=0, help="the port to serve on (default: any free one)")
    studio.add_argument("--no-browser", action="store_true", help="do not open a browser")
    arguments = parser.parse_args(argv)
    if arguments.command == "studio":
        from flexo.studio.server import main as studio_main

        options = [*([arguments.deck] if arguments.deck else []), "--port", str(arguments.port)]
        return studio_main([*options, *(["--no-browser"] if arguments.no_browser else [])], kind="deck")
    try:
        if arguments.command == "convert":
            return _convert(arguments)
        deck = load_deck(arguments.deck, arguments.theme)
        result = deck.build(arguments.output, formats=tuple(arguments.formats.split(",")))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        if os.environ.get("FLEXO_TRACEBACK"):
            raise
        print(f"flexo-talk: {_said(error, arguments.deck)}", file=sys.stderr)
        print("(FLEXO_TRACEBACK=1 shows the whole traceback)", file=sys.stderr)
        return 1
    print(result.summary())
    return 0


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
        print(f"{where}: a matplotlib plot, saved as {path.name} and placed as an image")
        return {"image": str(path)}  # named beside the document, as every file is, below

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
        elif key == "gallery" and isinstance(value, list):
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

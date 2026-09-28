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
import sys
from pathlib import Path

from flexo_talk.deck import Deck
from flexo_talk.export import FORMATS


def load_deck(target: str, theme: str | None = None) -> Deck:
    path, _, name = target.partition(":")
    source = Path(path).resolve()
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
    if arguments.command == "convert":
        return _convert(arguments)
    if arguments.command == "studio":
        from flexo.studio.server import main as studio_main

        options = [*([arguments.deck] if arguments.deck else []), "--port", str(arguments.port)]
        return studio_main([*options, *(["--no-browser"] if arguments.no_browser else [])], kind="deck")
    deck = load_deck(arguments.deck, arguments.theme)
    result = deck.build(arguments.output, formats=tuple(arguments.formats.split(",")))
    print(result.summary())
    return 0


def _convert(arguments: argparse.Namespace) -> int:
    """Write a Python deck as a document. Its plots are saved as SVG files beside
    it (named in the document as images), since a matplotlib figure has no document."""

    import os

    from flexo_talk.deck import made
    from flexo_talk.document import deck_document, save_document

    source = Path(arguments.deck.partition(":")[0]).resolve()
    target = Path(arguments.output or source.with_suffix(".yaml")).resolve()
    deck = load_deck(arguments.deck, arguments.theme)
    saved: list[Path] = []

    def plot(block, where: str) -> dict[str, object]:
        figure = made(block.figure)
        path = target.parent / f"{target.stem}-plot{len(saved) + 1}.svg"
        figure.savefig(path, format="svg", transparent=True, metadata={"Date": None})
        saved.append(path)
        print(f"{where}: a matplotlib plot, saved as {path.name} and placed as an image")
        return {"image": path.name}

    document = deck_document(deck, plots=plot)
    here = Path.cwd()
    for slide in document["slides"]:
        _relocate(slide, here, target.parent, os)
    print(save_document(document, target))
    return 0


_FILE_KEYS = ("image", "background", "picture")


def _relocate(data: object, origin: Path, destination: Path, os) -> None:
    """Rewrite file names written relative to where the deck ran so they are found
    beside the document."""

    if isinstance(data, list):
        for item in data:
            _relocate(item, origin, destination, os)
        return
    if not isinstance(data, dict):
        return
    for key, value in list(data.items()):
        if key in _FILE_KEYS and isinstance(value, str) and not value.startswith("#"):
            path = Path(value) if Path(value).is_absolute() else origin / value
            if path.exists():
                data[key] = os.path.relpath(path, destination)
        elif key == "gallery" and isinstance(value, list):
            data[key] = [
                os.path.relpath(origin / item, destination)
                if isinstance(item, str) and (origin / item).exists() else item
                for item in value
            ]
            _relocate(data[key], origin, destination, os)
        elif isinstance(value, dict | list) and key != "figure":
            _relocate(value, origin, destination, os)


if __name__ == "__main__":
    raise SystemExit(main())

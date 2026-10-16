"""Figures kept in the deck: a figure file's figure written into the deck, and a figure of the
deck's written out as a file of its own.

A deck's figures live in its document (``flexo_talk.document``): each written in its block, or
-- one shown on several slides -- once in the deck's ``figures``, named from each block as
``'#name'``. ``embed`` takes a figure file a slide shows into the deck (Embed Figure in Deck),
or every one its slides show (Embed All Figures in Deck): a file one slide shows is written in
that slide's block; one several show goes into the deck's ``figures`` and each of them names it,
so they stay one figure, each showing it as it did (its ``hide``, ``dim``, ``highlight`` and
``stages`` kept on its block). The files its parts draw (structures, pictures, data, a theme)
are named from the deck's folder rather than the file's. The files themselves are not touched
here: in a folder they are their person's, and in a bundle the studio takes away one no
document names any more (``flexo.studio.workspace.Workspace.release``).

``export`` writes a figure of the deck's as a figure file of its own -- its files named from
where the file is, in the deck's theme unless it names one -- and, if asked, has the deck show
the file in its place (every slide showing it, for one of the deck's ``figures``). Python-made
figures (``file.py:function``) are references, and stay so.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml

FIGURE_FILES = (".yaml", ".yml", ".json")
"""What a figure file of its own ends in."""
_PATTERN = re.compile(r"[*?\[]")


class EmbedError(ValueError):
    """A figure that can't be taken into the deck, or written out, as asked: said plainly."""


def places(document: Any) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Every figure block of a deck document, with where it is: ``({"slide", "region",
    "index"}, block)``, in the order the slides show them (a region named as the studio names
    it: ``body``, ``left``, ``right``, ``columns.N``)."""

    found: list[tuple[dict[str, Any], dict[str, Any]]] = []
    slides = document.get("slides") if isinstance(document, dict) else None
    for number, slide in enumerate(slides if isinstance(slides, list) else []):
        if not isinstance(slide, dict):
            continue
        regions = [(key, slide.get(key)) for key in ("body", "left", "right")]
        columns = slide.get("columns")
        regions += [(f"columns.{index}", column)
                    for index, column in enumerate(columns if isinstance(columns, list) else [])]
        for region, blocks in regions:
            for index, block in enumerate(blocks if isinstance(blocks, list) else []):
                if isinstance(block, dict) and "figure" in block:
                    found.append(({"slide": number, "region": region, "index": index}, block))
    return found


def is_file(value: object) -> bool:
    """Whether a block's ``figure`` names a figure file of its own (not the deck's own, by
    ``#name``; not Python)."""

    return isinstance(value, str) and bool(value.strip()) and not value.startswith("#") and ".py:" not in value


def file_figures(document: Any, base: Path) -> dict[Path, list[tuple[dict[str, Any], dict[str, Any]]]]:
    """The figure files a deck's slides show, each (as the computer has it, however it is
    named) with every block showing it."""

    found: dict[Path, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for at, block in places(document):
        if is_file(block["figure"]):
            found.setdefault((base / str(block["figure"])).resolve(), []).append((at, block))
    return found


def rebased(figure: dict[str, Any], origin: Path, destination: Path | None) -> dict[str, Any]:
    """A figure document with the files it names -- its theme and palette files, each part's
    picture, structure, map and plot (and the plot's data), the pictures among the shapes drawn
    over it -- named from ``destination`` rather than ``origin``: the very same files (with no
    ``destination``, by their whole paths). A name that is no file there (a PDB ID, a theme's
    name) is left as it is."""

    origin = origin.resolve()
    destination = destination.resolve() if destination is not None else None
    data = copy.deepcopy(figure)
    if origin == destination:
        return data

    def moved(name: object) -> object:
        if not isinstance(name, str) or not name.strip() or os.path.isabs(os.path.expanduser(name)):
            return name
        found = origin / name
        if not (found.exists() or (_PATTERN.search(name) and found.parent.exists())):
            return name
        if destination is None:
            return os.path.normpath(found)
        return Path(os.path.relpath(os.path.normpath(found), destination)).as_posix()

    settings = data.get("figure")
    if isinstance(settings, dict):
        for key in ("theme", "style", "palette"):
            if key in settings:
                settings[key] = moved(settings[key])
    for node in data.get("nodes") or []:
        properties = node.get("properties") if isinstance(node, dict) else None
        if not isinstance(properties, dict):
            continue
        for key in ("source", "density", "ss_from"):
            if key in properties:
                properties[key] = moved(properties[key])
        if node.get("kind") == "plot" and "data" in properties:
            value = properties["data"]
            if isinstance(value, list):
                properties["data"] = [moved(item) for item in value]
            elif isinstance(value, str):
                properties["data"] = ", ".join(str(moved(item.strip())) for item in value.split(",") if item.strip())
    data["shapes"] = _shapes(data["shapes"], moved) if isinstance(data.get("shapes"), list) else data.get("shapes")
    if data.get("shapes") is None:
        data.pop("shapes", None)
    return data


def _shapes(shapes: list, moved) -> list:
    out = []
    for shape in shapes:
        if isinstance(shape, dict) and shape.get("kind") == "group" and isinstance(shape.get("shapes"), list):
            shape = {**shape, "shapes": _shapes(shape["shapes"], moved)}
        elif isinstance(shape, dict) and shape.get("kind") == "picture" and "source" in shape:
            shape = {**shape, "source": moved(shape["source"])}
        out.append(shape)
    return out


def read_figure_file(path: Path, named: str) -> dict[str, Any]:
    """A figure file's figure, as data; what keeps it from being one said."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise EmbedError(f"Can\u2019t read “{named}”: {error.strerror or error}.") from None
    try:
        data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (ValueError, yaml.YAMLError):
        raise EmbedError(f"“{named}” doesn\u2019t read as a figure. Put it right first.") from None
    if not isinstance(data, dict) or not ("nodes" in data or "figure" in data):
        raise EmbedError(f"“{named}” isn\u2019t a figure.")
    return data


def _named(figures: dict[str, Any], data: dict[str, Any], stem: str) -> str:
    """A name for a figure among the deck's own: its id, else its file's name -- one the deck
    keeps already for the same figure, else one no other has."""

    own = data.get("figure") if isinstance(data.get("figure"), dict) else {}
    start = re.sub(r"[^\w.-]+", "-", str(own.get("id") or stem)).strip("-") or "figure"
    for name, figure in figures.items():
        if figure == data:
            return name
    name, count = start, 1
    while name in figures:
        count += 1
        name = f"{start}-{count}"
    return name


def embed(document: dict[str, Any], base: Path, at: dict[str, Any] | None = None) -> dict[str, Any]:
    """The figure file the block ``at`` shows -- or, with no ``at``, every figure file the
    deck's slides show -- written into the deck: answers ``{"document", "files", "slides",
    "said", "skipped"}``, the deck as it is then, the files taken in (named from ``base``, as
    the computer has them), how many slides show them, and what was done and left out, in a
    sentence each. The document given is left as it is."""

    changed = copy.deepcopy(document)
    uses = file_figures(changed, base)
    if at is not None:
        wanted = [
            path for path, blocks in uses.items()
            if any(where["slide"] == at.get("slide") and where["region"] == at.get("region")
                   and where["index"] == at.get("index") for where, _ in blocks)
        ]
        if not wanted:
            raise EmbedError("This figure isn\u2019t kept in a file of its own: it is in the deck already.")
    else:
        wanted = list(uses)
    root = base.resolve()
    taken: list[Path] = []
    slides: set[int] = set()
    skipped: list[str] = []
    for path in wanted:
        blocks = uses[path]
        named = str(blocks[0][1]["figure"])
        if path.suffix.lower() not in FIGURE_FILES or not path.is_relative_to(root):
            skipped.append(f"“{named}” is outside the deck\u2019s folder.")
            continue
        if not path.is_file():
            skipped.append(f"“{named}” isn\u2019t in the deck\u2019s folder.")
            continue
        try:
            data = rebased(read_figure_file(path, named), path.parent, root)
        except EmbedError as error:
            skipped.append(str(error))
            continue
        if len(blocks) == 1:
            blocks[0][1]["figure"] = data
        else:
            # Shown on several slides: kept once, each of them naming it, so it stays one figure.
            figures = changed.setdefault("figures", {})
            if not isinstance(figures, dict):
                raise EmbedError("The deck\u2019s figures aren\u2019t a mapping of names to figures. "
                                 "Put it right first.")
            name = _named(figures, data, path.stem)
            figures[name] = data
            for _, block in blocks:
                block["figure"] = f"#{name}"
        taken.append(path)
        slides.update(where["slide"] for where, _ in blocks)
    if at is not None and skipped:
        raise EmbedError(skipped[0])
    count = len(taken)
    said = (
        f"{'The figure' if count == 1 and at is not None else f'{count} figure' + ('s' if count != 1 else '')} "
        f"from {_files_named([path.name for path in taken])} {'is' if count == 1 else 'are'} in the deck now"
        + (f", on {len(slides)} slides" if len(slides) > 1 else "")
        if count else "No figure was put in the deck."
    )
    return {"document": changed, "files": taken, "slides": len(slides), "said": said, "skipped": skipped}


def _files_named(names: list[str], most: int = 3) -> str:
    quoted = [f"“{name}”" for name in names[:most]]
    if len(names) > most:
        return f"{', '.join(quoted)} and {len(names) - most} more"
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def figure_of(document: dict[str, Any], block: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """A figure block's figure, as the deck keeps it: the figure, and the name it has among the
    deck's own ``figures`` (None for one written in the block)."""

    value = block.get("figure")
    if isinstance(value, dict):
        return value, None
    if isinstance(value, str) and value.startswith("#"):
        figures = document.get("figures")
        found = figures.get(value[1:]) if isinstance(figures, dict) else None
        if isinstance(found, dict):
            return found, value[1:]
        raise EmbedError(f"The deck has no figure named “{value[1:]}”.")
    if isinstance(value, str) and ".py:" in value:
        raise EmbedError("This figure is made in Python: export it from its Python file.")
    raise EmbedError("This figure is kept in a file of its own already.")


def as_file(document: dict[str, Any], base: Path, figure: dict[str, Any], target: Path | None) -> dict[str, Any]:
    """A figure of the deck's as a figure file of its own at ``target`` has it: its files named
    from the file's folder (with no ``target``, by their whole paths), and drawn in the deck's
    theme (its palette, its figure font) unless it names its own."""

    folder = target.parent if target is not None else None
    data = rebased(figure, base, folder)
    settings = data.setdefault("figure", {})
    if not isinstance(settings, dict):
        settings = data["figure"] = {}
    deck = document.get("deck") if isinstance(document.get("deck"), dict) else {}
    look = {"style": deck.get("theme"), "palette": deck.get("palette"),
            "font": deck.get("figure_font") or deck.get("font")}
    beside = rebased({"figure": {key: value for key, value in look.items() if isinstance(value, str)}}, base,
                     folder)["figure"]
    for key, value in beside.items():
        if key not in settings and not (key == "style" and "theme" in settings) and value != "default":
            settings[key] = value
    # (Its id first, as a figure file is written.)
    data["figure"] = {"id": settings.pop("id"), **settings} if "id" in settings else settings
    return {"figure": data.pop("figure"), **data}


def figure_text(figure: dict[str, Any]) -> str:
    """A figure document as a figure file's words."""

    from flexo_talk.document import _Dumper

    # (As a deck is written: block style, words over several lines as literal blocks.)
    return yaml.dump(figure, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def export(
    document: dict[str, Any], base: Path, at: dict[str, Any], name: str, *, use: bool = False
) -> dict[str, Any]:
    """The figure the block ``at`` shows written as a figure file of its own, ``name`` (from
    ``base``, the deck's folder; ``.yaml`` if it ends in none of a figure file's endings) --
    never over another file. ``use``: the deck shows the file in its place from then on (every
    slide showing it, for one of the deck's own ``figures``), else it keeps its own copy.
    Answers ``{"document", "file", "said"}``: the deck then, the file's name as the deck would
    name it, and what was done."""

    figure, shared = figure_of(document, _block_at(document, at))
    name = name.strip().replace("\\", "/")
    if not name or name.endswith("/"):
        raise EmbedError("Enter a name for the figure\u2019s file.")
    if not name.lower().endswith(FIGURE_FILES):
        name += ".yaml"
    root = base.resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root) or target == root:
        raise EmbedError("A figure\u2019s file goes in the deck\u2019s folder.")
    if target.exists():
        raise EmbedError(f"“{name}” already exists. Choose a different name.")
    data = as_file(document, base, figure, target)
    json_file = target.suffix.lower() == ".json"
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n" if json_file else figure_text(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    named = target.relative_to(root).as_posix()
    changed = copy.deepcopy(document)
    if use and shared is not None:
        # One of the deck's own, shown on several slides: each of them shows the file instead.
        for _, other in places(changed):
            if other.get("figure") == f"#{shared}":
                other["figure"] = named
        changed["figures"].pop(shared, None)
        if not changed["figures"]:
            changed.pop("figures")
    elif use:
        _block_at(changed, at)["figure"] = named
    said = (f"The figure is in “{named}” now, and the deck shows that file." if use
            else f"The figure is written to “{named}”. The deck keeps its own copy.")
    return {"document": changed, "file": named, "said": said}


def _block_at(document: dict[str, Any], at: dict[str, Any]) -> dict[str, Any]:
    for where, block in places(document):
        if (where["slide"], where["region"], where["index"]) == (at.get("slide"), at.get("region"), at.get("index")):
            return block
    raise EmbedError("The selected object isn\u2019t a figure.")

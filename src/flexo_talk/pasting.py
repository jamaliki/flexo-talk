"""Slides pasted from another deck: the files they name brought along into this deck's folder.

A slide names its files from its deck's folder -- its pictures, galleries, people's
portraits, GIFs, figure files (with the files those name), plots' Python and data, the
pictures kept from drawings pasted in, its background. Copied in a deck of one folder and
pasted in a deck of another, it would name files that are not there, or worse, another file
of the same name. ``brought`` copies each into the deck's folder, as a bundle gathers them
(``flexo.bundle.followed``), and names them so:

- each where it was, by the name it had (``assets/red.png``), when that is free here or holds
  the very same file already -- so two slides naming one file bring it once;
- a file whose name here is another file's: beside it, numbered (``assets/shared-2.png``);
- a figure file, a plot's Python or a folder whose files clash so: all of them, laid out as
  they were, in a folder of their own named after the deck they came from
  (``assets/<folder>/figures/model.yaml``), so the names inside them still find each other;
- a file named outside its deck's folder (``../logo.png``) by its whole path, as it is there.

Files named by whole paths, PDB entries, and files not there are left as named.
"""

from __future__ import annotations

import filecmp
import os
import re
import shutil
from pathlib import Path
from typing import Any

from flexo import bundle

from flexo_talk.bundling import references

COPIED = "assets"
"""Where the files of a figure or a plot that clash here go: a folder of their own in here."""
NAMING = frozenset({
    "image", "picture", "gallery", "people", "figure", "plot", "source", "background",
    "density", "ss_from", "theme", "style", "palette", "data",
})
"""The keys a slide names files under (each, or each of a list of them): only these are renamed,
never a slide's words that happen to read as a file's name."""
_PAGE = re.compile(r"^(?P<whole>.+)#(?P<page>\d+)$")


def brought(slides: list[Any], source: str | Path, base: Path) -> dict[str, Any]:
    """``slides`` from the deck whose folder is ``source``, for the deck whose folder is
    ``base``: the files they name copied here, and the slides naming them as they are here.
    Answers ``{"slides", "files", "missing"}``: the slides, the files written (as the computer
    has them), and the names of files they name that are not there."""

    origin = Path(os.path.abspath(Path(source).expanduser()))
    here = base.resolve()
    if not isinstance(slides, list) or origin.resolve() == here:
        return {"slides": slides, "files": [], "missing": []}
    moves: dict[str, str] = {}
    written: list[Path] = []
    missing: list[str] = []
    seen: set[str] = set()
    for reference in references({"slides": slides}, origin):
        name = reference.name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        gathered = bundle.followed(reference, origin)
        files = {
            key: path for key, path in gathered.files.items()
            if not key.startswith(f"{bundle.OWN}/")
        }
        for left in gathered.left:
            if left.why == "missing" and left.name not in missing:
                missing.append(left.name)
        if not files:
            outside = _outside(name, reference.role, origin, gathered)
            if outside:
                moves[name] = outside
            continue
        own, page = _own(name, reference.role, origin)
        if all(_free(here / key, path) for key, path in files.items()):
            written += _copied(files, here)
            continue
        if len(files) == 1 and own in files and reference.role not in ("document", "python"):
            target = _numbered(here, own, files[own])
            written += _copied({target: files[own]}, here)
            moves[name] = target + page
            continue
        folder = _folder_for(here, origin, files)
        written += _copied({f"{folder}/{key}": path for key, path in files.items()}, here)
        if own is not None:
            moves[name] = f"{folder}/{own}{page}"
    renamed = _renamed(slides, moves) if moves else slides
    return {"slides": renamed, "files": written, "missing": missing}


def _own(name: str, role: str, origin: Path) -> tuple[str | None, str]:
    """The file a name stands for, by its name from ``origin`` (None for one outside it), and
    the page of it it names (``#2``: a PDF's second), if one."""

    page = ""
    path = Path(os.path.normpath(origin / Path(name).expanduser()))
    found = _PAGE.match(name)
    if role == "file" and found and not path.exists():
        whole = Path(os.path.normpath(origin / found["whole"]))
        if whole.is_file():
            path, page = whole, f"#{found['page']}"
    try:
        return path.relative_to(origin).as_posix(), page
    except ValueError:
        return None, page


def _outside(name: str, role: str, origin: Path, gathered: bundle.Gathered) -> str | None:
    """A name that climbs out of the deck's folder to a file there (``../logo.png``): its
    whole path, which finds it from any folder; else None."""

    if Path(name).expanduser().is_absolute() or not any(
        left.why == "outside" for left in gathered.left
    ):
        return None
    whole = Path(os.path.normpath(origin / name))
    return str(whole) if whole.exists() else None


def _free(target: Path, path: Path) -> bool:
    """Whether ``path`` may be put at ``target``: nothing is there, or the very same file."""

    if not target.exists():
        return True
    try:
        return target.is_file() and filecmp.cmp(target, path, shallow=False)
    except OSError:
        return False


def _numbered(here: Path, own: str, path: Path) -> str:
    """A name for a file whose own is another's here: beside it, ``-2``, ``-3``…, the first
    free or holding the very same file."""

    stem, suffix = os.path.splitext(own)
    count = 2
    while not _free(here / f"{stem}-{count}{suffix}", path):
        count += 1
    return f"{stem}-{count}{suffix}"


def _folder_for(here: Path, origin: Path, files: dict[str, Path]) -> str:
    """A folder of its own for files that clash here, named after the deck they came from:
    the first where each is free, or there already."""

    stem = re.sub(r"[^\w.-]+", "-", origin.name).strip("-.") or "pasted"
    count = 1
    while True:
        folder = f"{COPIED}/{stem}" if count == 1 else f"{COPIED}/{stem}-{count}"
        if all(_free(here / folder / key, path) for key, path in files.items()):
            return folder
        count += 1


def _copied(files: dict[str, Path], here: Path) -> list[Path]:
    """Each file put at its name here, unless it is there already: those written."""

    written = []
    for key, path in files.items():
        target = here.joinpath(*key.split("/"))
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        written.append(target)
    return written


def _renamed(value: Any, moves: dict[str, str], naming: bool = False) -> Any:
    """``value`` with each file it names that moved named as it is now (a plot's
    ``file.py:function`` keeping its function)."""

    if isinstance(value, dict):
        return {key: _renamed(item, moves, key in NAMING) for key, item in value.items()}
    if isinstance(value, list):
        return [_renamed(item, moves, naming) for item in value]
    if naming and isinstance(value, str):
        name = value.strip()
        if name in moves:
            return moves[name]
        file, mark, function = name.rpartition(":")
        if mark and file.endswith(".py") and file in moves:
            return f"{moves[file]}:{function}"
    return value


__all__ = ["brought"]

"""A Keynote deck brought into Flexo (``flexo_talk.importing.keynote``), read from its file with
no library but Python's: the deck made by script (``presentations.keynote``, its messages
written field by field, one named slide per case) comes across -- a title, words with a slant
and a script, lists and numbers, shapes, a crop, a group placed from its corner, a connection
glued to what it joins, equations written in TeX and in MathML, notes, a skipped slide -- and a
table it cannot bring is kept as its place. A Keynote package (a folder) reads as one file does,
and a damaged stream costs only what it held."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from presentations import keynote

from flexo_talk.importing import import_presentation, kind_of


@pytest.fixture(scope="module")
def imported(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Any, Path]:
    folder = tmp_path_factory.mktemp("key")
    source = keynote(folder / "talk.key")
    report = import_presentation(source, folder / "talk", folder=True)
    return yaml.safe_load((folder / "talk" / "talk.yaml").read_text(encoding="utf-8")), report, folder


def _slide(document: dict[str, Any], number: int) -> dict[str, Any]:
    return document["slides"][number - 1]


def test_a_keynote_deck_is_known_by_what_it_holds(imported) -> None:
    assert kind_of(imported[2] / "talk.key") == "keynote"


def test_its_slides_come_across_half_size_with_their_title_words_and_notes(imported) -> None:
    document, report, _ = imported
    assert report.slides == 8
    # Keynote's slide is 1920 by 1080 points: a Flexo deck's is 960 by 540, everything in proportion.
    assert document["deck"]["style"]["width"] == 960 and document["deck"]["style"]["height"] == 540
    first = _slide(document, 1)
    assert first["title"] == "A Keynote talk"
    assert first["body"][0]["text"] == "Plain *slanted* and x$^{2}$"
    assert first["body"][0]["size"] == 20
    assert first["notes"] == "Speak to the title."


def test_lists_keep_their_levels_and_numbers(imported) -> None:
    listed, numbered = _slide(imported[0], 2)["body"]
    assert listed["bullets"] == ["First", ["Under it"], "Second"]
    assert numbered["bullets"] == ["One", "Two"] and numbered["numbered"] is True
    # The second text box stands where it stood: 600 down of 1080 is 300 of 540.
    assert numbered["at"][1] == 302


def test_shapes_are_flexos_own_kinds_turned_as_keynote_turned_them(imported) -> None:
    slide = _slide(imported[0], 3)
    kinds = [shape["kind"] for shape in slide["shapes"]]
    assert kinds == ["rectangle", "rounded-rectangle", "arrow-right", "rectangle"]
    assert slide["shapes"][1]["corner"] == 10
    assert slide["shapes"][3]["rotate"] == 330  # 30 degrees anticlockwise
    assert slide["background"] == "#fdf6e3"


def test_a_picture_is_cropped_by_its_mask_and_a_group_placed_from_its_corner(imported) -> None:
    document, _, folder = imported
    slide = _slide(document, 4)
    picture = slide["body"][0]
    assert picture["crop"] == [0.05, 0, 0.4, 1]
    assert picture["at"] == [60, 50] and picture["width"] == 80
    assert (folder / "talk" / picture["image"]).is_file()
    group = slide["shapes"][0]
    assert group["kind"] == "group"
    assert [shape["at"] for shape in group["shapes"]] == [[400, 250], [500, 250]]


def test_a_connection_line_is_glued_to_what_it_joins(imported) -> None:
    shapes = _slide(imported[0], 5)["shapes"]
    arrow = shapes[0]  # (drawn first: under what it joins, as Keynote draws it)
    assert arrow["kind"] == "arrow" and arrow["end"] == "triangle"
    assert arrow["from"]["side"] == "right" and arrow["to"]["side"] == "left"
    assert {arrow["from"]["shape"], arrow["to"]["shape"]} == {shape["id"] for shape in shapes[1:]}


def test_equations_come_across_as_tex_from_tex_and_from_mathml(imported) -> None:
    body = _slide(imported[0], 6)["body"]
    assert [block["math"] for block in body] == [r"\frac{a}{b} = x^2", r"\sqrt{x}"]


def test_a_skipped_slide_stays_skipped_and_a_table_is_kept_as_its_place(imported) -> None:
    document, report, _ = imported
    assert _slide(document, 7)["skip"] is True
    placeholder = _slide(document, 8)["shapes"][0]
    assert placeholder["hide"] is True and placeholder["text"].startswith("TODO Table")
    assert [place.kind for place in report.placeholders] == ["Table"]


def test_the_deck_reads_and_draws(imported) -> None:
    from flexo_talk.compose import render_slide
    from flexo_talk.document import read_deck

    deck = read_deck(imported[2] / "talk" / "talk.yaml")
    for slide in deck.slides:
        assert "<svg" in render_slide(deck, slide).svg


def test_a_keynote_package_reads_as_its_one_file_does(tmp_path: Path) -> None:
    source = keynote(tmp_path / "talk.key")
    package = tmp_path / "package" / "talk.key"
    package.mkdir(parents=True)
    index = io.BytesIO()
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(index, "w") as inner:
        for name in archive.namelist():
            if name.startswith("Index/"):
                inner.writestr(name[len("Index/") :], archive.read(name))
            else:
                (package / name).parent.mkdir(parents=True, exist_ok=True)
                (package / name).write_bytes(archive.read(name))
    (package / "Index.zip").write_bytes(index.getvalue())
    assert kind_of(package) == "keynote"
    report = import_presentation(package, tmp_path / "out", folder=True)
    assert report.slides == 8
    shutil.rmtree(package)


def test_a_damaged_stream_costs_what_it_held_and_no_more(tmp_path: Path) -> None:
    source = keynote(tmp_path / "talk.key")
    damaged = tmp_path / "damaged.key"
    with zipfile.ZipFile(source) as archive, zipfile.ZipFile(damaged, "w") as copy:
        for name in archive.namelist():
            copy.writestr(name, b"\x00\x05\x00\x00junk" if name == "Index/Metadata.iwa" else archive.read(name))
    report = import_presentation(damaged, tmp_path / "out", folder=True)
    assert report.slides == 8
    assert any("could not be read" in note for note in report.notes)
    # (Its pictures' files were named there: the picture is kept as its place.)
    assert any(place.kind == "Picture" for place in report.placeholders)

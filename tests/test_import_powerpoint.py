"""A PowerPoint deck brought into Flexo (``flexo_talk.importing``): each case of the deck made by
script (``presentations.powerpoint``, one named slide each) where it stood -- titles as titles,
words, lists and their levels, bold, italic, scripts, colours and links, pictures with their
crops, Flexo's own shapes, connectors glued to what they join, tables, Office Math as TeX, notes,
a skipped slide -- and what cannot be brought across kept as its place, marked TODO, said in
the report; never a failed import. And a Flexo deck comes back from its own PowerPoint."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from presentations import powerpoint

from flexo_talk.importing import ImportFailed, import_presentation


@pytest.fixture(scope="module")
def imported(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], Any, Path]:
    folder = tmp_path_factory.mktemp("pptx")
    source = powerpoint(folder / "talk.pptx")
    report = import_presentation(source, folder / "talk", folder=True)
    deck = folder / "talk"
    return yaml.safe_load((deck / "talk.yaml").read_text(encoding="utf-8")), report, deck


def _slide(document: dict[str, Any], number: int) -> dict[str, Any]:
    return document["slides"][number - 1]


def _shapes(slide: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for shape in slide.get("shapes", []):
        out.append(shape)
        out.extend(shape.get("shapes", []))
    return out


def test_every_slide_comes_across_in_order_on_a_slide_its_size(imported) -> None:
    document, report, _ = imported
    assert report.slides == len(document["slides"]) == 12
    assert document["deck"]["style"]["width"] == 960 and document["deck"]["style"]["height"] == 540
    assert document["deck"]["theme"] == "theme.yaml"


def test_a_title_slide_is_its_words_where_they_stood(imported) -> None:
    slide = _slide(imported[0], 1)
    assert slide["layout"] == "blank"
    words = [block["text"] for block in slide["body"]]
    assert words[0].strip("*") == "Imported talk" and words[1] == "A subtitle"
    assert all(block["align"] == "middle" for block in slide["body"])


def test_a_title_is_the_slides_and_a_list_keeps_its_levels_and_its_words_look(imported) -> None:
    slide = _slide(imported[0], 2)
    assert slide["title"] == "Results"
    assert "layout" not in slide  # a content slide: the title drawn where the deck's are
    items = slide["body"][0]["bullets"]
    assert items[0] == "First point"
    assert items[1] == ["**Bold** and *italic*"]
    assert items[2] == "H$_{2}$O and x$^{2}$"
    assert "[Red words]{#c0392b}" in items[3]
    assert "[and a link](https://example.org/paper)" in items[3]
    assert slide["notes"] == "Say the results slowly."


def test_pictures_keep_their_crops_and_round_masks(imported) -> None:
    document, _, deck = imported
    cropped, round_picture = _slide(document, 3)["body"]
    assert cropped["crop"] == [0.25, 0, 0.5, 1]
    assert cropped["at"] == [100, 100] and cropped["width"] == 200
    assert round_picture["mask"] == "circle"
    assert (deck / cropped["image"]).is_file()


def test_shapes_are_flexos_own_kinds_or_their_outlines(imported) -> None:
    shapes = _shapes(_slide(imported[0], 4))
    kinds = [shape["kind"] for shape in shapes]
    assert kinds[:5] == ["rectangle", "rounded-rectangle", "ellipse", "arrow-right", "star"]
    box = shapes[0]
    assert box["fill"] == "#1a5d9b" and box["text"] == "Box"
    assert box["at"] == [60, 60] and box["size"] == [120, 80]
    assert kinds.count("path") == 2  # the hexagon, and the freeform
    assert any(shape.get("rotate") == 30 for shape in shapes)


def test_connectors_are_glued_to_the_shapes_they_join(imported) -> None:
    shapes = _shapes(_slide(imported[0], 5))
    arrow = next(shape for shape in shapes if shape["kind"] == "arrow")
    assert arrow["from"]["side"] == "right" and arrow["to"]["side"] == "left"
    names = {shape.get("id") for shape in shapes}
    assert arrow["from"]["shape"] in names and arrow["to"]["shape"] in names
    assert arrow["end"] == "triangle" and arrow["start"] == "none"
    assert any(shape["kind"] == "elbow" for shape in shapes)


def test_a_table_keeps_its_rows(imported) -> None:
    table = _slide(imported[0], 6)["body"][0]
    assert table["table"] == [["Model", "Loss", "Top-1"], ["A", "0.31", "76.1"], ["B", "0.27", "81.2"]]
    assert table["at"] == [100, 100] and table["width"] == 500


def test_office_math_comes_across_as_tex(imported) -> None:
    body = _slide(imported[0], 7)["body"]
    assert body[0]["math"] == r"\frac{a}{b}=x^{2}"
    assert body[1]["text"] == r"The rate $k=\alpha$ rises."


def test_a_skipped_slide_stays_skipped(imported) -> None:
    assert _slide(imported[0], 8)["skip"] is True


def test_what_cannot_come_across_is_kept_as_its_place_marked_todo_and_said(imported) -> None:
    document, report, _ = imported
    shapes = _slide(document, 9)["shapes"]
    assert len(shapes) == 2
    assert all(shape["hide"] is True and shape["text"].startswith("TODO") for shape in shapes)
    assert shapes[0]["at"] == [100, 100] and shapes[0]["size"] == [300, 200]
    assert {place.kind for place in report.placeholders} == {"Chart", "Picture"}
    assert "2 objects became placeholders:" in report.summary()


def test_a_group_is_one_of_flexos_groups(imported) -> None:
    group = _slide(imported[0], 10)["shapes"][0]
    assert group["kind"] == "group"
    assert [shape["kind"] for shape in group["shapes"]] == ["rectangle", "ellipse"]
    assert group["shapes"][0]["text"] == "One"


def test_smartart_is_the_shapes_powerpoint_drew_it_in(imported) -> None:
    group = _slide(imported[0], 12)["shapes"][0]
    assert [shape["kind"] for shape in group["shapes"]] == ["rounded-rectangle", "rounded-rectangle"]
    assert [shape["text"] for shape in group["shapes"]] == ["Step 1", "Step 2"]
    assert group["shapes"][1]["at"] == [300, 100]


def test_a_pdf_embedded_as_an_object_is_its_picture(imported) -> None:
    document, _, deck = imported
    picture = _slide(document, 11)["body"][0]
    assert picture["image"].endswith(".pdf")
    assert (deck / picture["image"]).read_bytes().startswith(b"%PDF-")


def test_the_deck_reads_and_draws_every_slide(imported) -> None:
    from flexo_talk.compose import render_slide
    from flexo_talk.document import read_deck

    _, _, deck = imported
    made = read_deck(deck / "talk.yaml")
    for slide in made.slides:
        assert "<svg" in render_slide(made, slide).svg


def test_a_bundle_holds_the_deck_and_its_pictures(tmp_path: Path) -> None:
    source = powerpoint(tmp_path / "talk.pptx")
    before = source.read_bytes()
    import_presentation(source, tmp_path / "Imported.flexo")
    assert source.read_bytes() == before  # (only ever read)
    with zipfile.ZipFile(tmp_path / "Imported.flexo") as bundle:
        names = bundle.namelist()
    assert "Imported.yaml" in names and "theme.yaml" in names
    assert any(name.startswith("assets/") and name.endswith(".png") for name in names)


def test_a_four_by_three_deck_keeps_its_size(tmp_path: Path) -> None:
    source = powerpoint(tmp_path / "square.pptx", width=720, height=540)
    import_presentation(source, tmp_path / "square", folder=True)
    document = yaml.safe_load((tmp_path / "square" / "square.yaml").read_text(encoding="utf-8"))
    assert document["deck"]["style"]["width"] == 720
    # Placed in the units a slide's shapes are: 960 across, whatever the slide's size.
    assert document["slides"][2]["body"][0]["at"] == [133.3, 133.3]


def test_a_damaged_slide_is_kept_empty_and_said_while_the_rest_comes_across(tmp_path: Path) -> None:
    source = powerpoint(tmp_path / "talk.pptx")
    damaged = tmp_path / "damaged.pptx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(damaged, "w") as copy:
        for item in original.infolist():
            data = original.read(item)
            copy.writestr(item, b"<p:sld not xml" if item.filename == "ppt/slides/slide2.xml" else data)
    report = import_presentation(damaged, tmp_path / "out", folder=True)
    document = yaml.safe_load((tmp_path / "out" / "out.yaml").read_text(encoding="utf-8"))
    assert len(document["slides"]) == 12
    assert document["slides"][1] == {"layout": "blank"}
    assert any(place.kind == "Slide" and place.slide == 2 for place in report.placeholders)


def test_a_file_that_is_no_deck_is_said_so(tmp_path: Path) -> None:
    junk = tmp_path / "notes.pptx"
    junk.write_bytes(b"not a zip at all")
    with pytest.raises(ImportFailed, match="not a PowerPoint"):
        import_presentation(junk, tmp_path / "out.flexo")
    old = tmp_path / "old.ppt"
    old.write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(ImportFailed, match=r"save it as \.pptx"):
        import_presentation(old, tmp_path / "out.flexo")


def test_a_flexo_deck_comes_back_from_its_own_powerpoint(tmp_path: Path) -> None:
    from flexo_talk.document import read_deck

    (tmp_path / "talk.yaml").write_text(
        "schema_version: 1\n"
        "deck: {id: talk, theme: paper}\n"
        "slides:\n"
        "- title: Why another figure tool?\n"
        "  body:\n"
        "  - bullets: [Figures take hours, [boxes drift out of line], '**Strong** words']\n"
        "  notes: Everyone has redrawn a figure.\n"
        "- title: Numbers\n"
        "  body:\n"
        "  - table: [[Model, Loss], [A, '0.31'], [B, '0.27']]\n"
        "  - math: \\frac{1}{N}\\sum_{i=1}^{N} x_i\n"
        "  shapes:\n"
        "  - {kind: rounded-rectangle, id: note, at: [600, 300], size: [200, 80], text: Pocket}\n"
        "  - {kind: arrow, from: [400, 420], to: {shape: note, side: left}}\n",
        encoding="utf-8",
    )
    original = read_deck(tmp_path / "talk.yaml")
    original.build(tmp_path / "built", formats=("pptx",))
    import_presentation(tmp_path / "built" / "talk.pptx", tmp_path / "back", folder=True)
    back = yaml.safe_load((tmp_path / "back" / "back.yaml").read_text(encoding="utf-8"))
    first, second = back["slides"]
    assert first["title"] == "Why another figure tool?"
    assert first["body"][0]["bullets"] == ["Figures take hours", ["boxes drift out of line"], "**Strong** words"]
    assert first["notes"] == "Everyone has redrawn a figure."
    assert second["title"] == "Numbers"
    table = next(block for block in second["body"] if "table" in block)
    assert table["table"] == [["Model", "Loss"], ["A", "0.31"], ["B", "0.27"]]
    maths = next(block for block in second["body"] if "math" in block)
    assert maths["math"].replace(" ", "") == r"\frac{1}{N}\sum_{i=1}^{N}x_{i}"
    shapes = _shapes(second)
    assert any(shape["kind"] == "rounded-rectangle" and shape.get("text") == "Pocket" for shape in shapes)
    # The deck's look comes too: its face and its titles' size and weight.
    style = back["deck"]["style"]
    assert style["title_size"] == 30 and style["title_weight"] == 700
    theme = yaml.safe_load((tmp_path / "back" / "theme.yaml").read_text(encoding="utf-8"))
    assert theme["theme"]["font"] == original.typography(20).family

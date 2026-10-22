"""People beside a slide's title: round portraits at the right end of its title, each with
their name small under it, read from the deck's document, drawn, bundled and exported."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
from flexo import bundle as B

from flexo_talk import Deck, compose
from flexo_talk.document import (
    DeckDocumentError,
    MissingFile,
    deck_document,
    deck_from_document,
    dump_document,
)
from flexo_talk.studio import DeckKind

TITLE = "Mechazyme builds a reaction-cycle motif"


def _portraits(folder: Path) -> list[str]:
    from PIL import Image

    (folder / "assets").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 300), (200, 120, 90)).save(folder / "assets" / "sam.jpeg")
    Image.new("RGB", (300, 420), (90, 140, 200)).save(folder / "assets" / "other.png")
    return ["assets/sam.jpeg", "assets/other.png"]


def _deck(folder: Path, people: object, **slide: object) -> dict:
    return {"schema_version": 1, "deck": {"id": "people"}, "slides": [
        {"title": TITLE, "people": people, "body": [{"text": "Words"}], **slide}]}


def _drawn(svg: str, pattern: str) -> list[ET.Element]:
    return [item for item in ET.fromstring(svg).iter() if re.fullmatch(pattern, item.get("id", ""))]


def _box(item: ET.Element) -> tuple[float, float, float, float]:
    return tuple(float(value) for value in item.get("data-flexo-box", "").split())  # type: ignore[return-value]


def test_people_are_read_as_pictures_and_names_and_written_back_as_given(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    people = [{"image": names[0], "name": "Sam Pellock"}, names[1]]
    deck = deck_from_document(_deck(tmp_path, people), tmp_path)
    slide = deck.slides[0]
    assert [person.image for person in slide.people] == [str(tmp_path / name) for name in names]
    assert [person.written for person in slide.people] == ["Sam Pellock", ""]
    assert deck_document(deck)["slides"][0]["people"] == people
    # Made in Python, written as its files are named there, their names beside them.
    made = Deck("made")
    with made.slide(TITLE) as each:
        each.person(tmp_path / names[0], "Sam Pellock").person(tmp_path / names[1])
        each.bullets("A point")
    assert deck_document(made)["slides"][0]["people"] == [
        {"image": str(tmp_path / names[0]), "name": "Sam Pellock"}, str(tmp_path / names[1])]
    assert "people:" in dump_document(deck_document(made))


@pytest.mark.parametrize("layout", ["content", "two-columns", "columns", "figure"])
def test_every_layout_with_a_title_over_its_objects_takes_people(tmp_path: Path, layout: str) -> None:
    names = _portraits(tmp_path)
    slide: dict = {"layout": layout, "title": TITLE, "people": names}
    slide |= {"two-columns": {"left": [{"text": "A"}], "right": [{"text": "B"}]},
              "columns": {"columns": [[{"text": "A"}], [{"text": "B"}]]}}.get(layout, {"body": [{"text": "A"}]})
    deck = deck_from_document({"deck": {}, "slides": [slide]}, tmp_path)
    svg = compose.render_slide(deck, deck.slides[0]).svg
    assert len(_drawn(svg, r"slide1\.person\d")) == 2


@pytest.mark.parametrize(("people", "where", "said"), [
    ("assets/sam.jpeg", "slides[0].people", "people must be a list of portraits, such as "
                                            "[{image: assets/sam.jpeg, name: Sam Pellock}]."),
    ([{"image": "assets/sam.jpeg", "title": "Dr"}], "slides[0].people[0]",
     "Unknown key title. Valid keys here: image, name"),
    ([{"name": "Sam"}], "slides[0].people[0]", "Each person is a picture file, or a mapping with image and name"),
    ([{"image": "assets/sam.jpeg", "name": ["Sam"]}], "slides[0].people[0].name", "name must be text, not a list"),
    (["assets/sam.gif"], "slides[0].people[0]",
     "A portrait must be a PNG, JPEG, SVG or PDF picture: sam.gif is none of these."),
    (["assets/nobody.png"], "slides[0].people[0]", "Cannot find assets/nobody.png"),
])
def test_people_said_wrong_are_said_where_they_are(tmp_path: Path, people: object, where: str, said: str) -> None:
    _portraits(tmp_path)
    (tmp_path / "assets" / "sam.gif").write_bytes(b"GIF89a")
    with pytest.raises(DeckDocumentError) as raised:
        deck_from_document(_deck(tmp_path, people), tmp_path)
    assert raised.value.where == where
    assert said in str(raised.value)


@pytest.mark.parametrize("layout", ["title", "section", "statement", "agenda", "blank"])
def test_a_slide_with_no_title_over_objects_refuses_people(tmp_path: Path, layout: str) -> None:
    names = _portraits(tmp_path)
    with pytest.raises(DeckDocumentError, match="has no title for people to stand beside") as raised:
        deck_from_document({"deck": {}, "slides": [{"layout": layout, "title": "A", "people": names}]}, tmp_path)
    assert raised.value.where == "slides[0].people"


def test_portraits_stand_round_at_the_right_end_of_the_title_which_wraps_short_of_them(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    people = [{"image": names[0], "name": "Sam Pellock"}, {"image": names[1], "name": "Ana Ruiz"}]
    long = "A title long enough to run the whole width of the slide when nothing stands beside it"
    plain = deck_from_document(_deck(tmp_path, None, title=long), tmp_path)
    deck = deck_from_document(_deck(tmp_path, people, title=long), tmp_path)
    style = deck.style
    svg = compose.render_slide(deck, deck.slides[0]).svg
    portraits = _drawn(svg, r"slide1\.person\d")
    # Each a circle filled with its picture: the square in its middle, drawn round.
    assert [item.tag.rsplit("}", 1)[-1] for item in portraits] == ["ellipse", "ellipse"]
    assert all(item.get("rx") == item.get("ry") for item in portraits)
    assert [item.get("aria-label") for item in portraits] == ["Sam Pellock", "Ana Ruiz"]
    boxes = [_box(item) for item in portraits]
    # About a line and a third of the title across, side by side, a small gap between them.
    size = boxes[0][2]
    line = compose._Canvas(deck, deck.slides[0]).measure(compose.inline("Hg"), style.title_size, None, title=True)
    assert size == pytest.approx(line.line_height * compose.PORTRAIT_SIZE)
    assert boxes[0][1] == boxes[1][1] and boxes[0][0] + size < boxes[1][0]
    # The row's right end on the slide's right margin (the last a portrait no narrower than
    # its name), and its middle on the title's.
    names_drawn = _drawn(svg, r"slide1\.person\d\.name")
    assert [item.get("text-anchor") for item in names_drawn] == ["middle", "middle"]
    assert boxes[-1][0] + size == pytest.approx(style.width - style.margin, abs=0.01)
    # The title wraps short of them, with room kept; without them, at the margin.
    title = _drawn(svg, r"slide1\.title")[0]
    wrap = float(title.get("data-flexo-wrap", "").split()[0])
    assert style.margin + wrap + compose.PEOPLE_ROOM <= min(box[0] for box in boxes) + 0.01
    before = _drawn(compose.render_slide(plain, plain.slides[0]).svg, r"slide1\.title")[0]
    assert float(before.get("data-flexo-wrap", "").split()[0]) == pytest.approx(style.width - 2 * style.margin)
    # The body starts below their names.
    body = _drawn(svg, r"slide1\.body")[0]
    assert _box(body)[1] >= max(float(item.get("y", 0)) for item in names_drawn)


def test_many_people_are_made_smaller_together_to_fit_their_share(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    few = deck_from_document(_deck(tmp_path, names), tmp_path)
    deck = deck_from_document(_deck(tmp_path, names * 4), tmp_path)
    svg = compose.render_slide(deck, deck.slides[0]).svg
    boxes = [_box(item) for item in _drawn(svg, r"slide1\.person\d+")]
    span = deck.style.width - 2 * deck.style.margin
    full = _box(_drawn(compose.render_slide(few, few.slides[0]).svg, r"slide1\.person0")[0])[2]
    assert len(boxes) == 8 and boxes[0][2] < full
    assert boxes[-1][0] + boxes[-1][2] - boxes[0][0] == pytest.approx(span * compose.PEOPLE_SHARE)


def test_a_missing_portrait_holds_its_place_while_editing_and_is_said(tmp_path: Path) -> None:
    from flexo.confine import folder_root

    names = _portraits(tmp_path)
    document = _deck(tmp_path, [names[0], {"image": "assets/gone.png", "name": "Gone"}])
    root = folder_root.set(tmp_path)
    try:
        drawing = DeckKind().draw(document, tmp_path, {})
    finally:
        folder_root.reset(root)
    svg = drawing.pages[0].svg
    assert 'id="slide1.person1"' in svg and "Missing" in svg
    said = [(message.text, message.where) for message in drawing.messages if message.severity == "error"]
    assert said == [("Can't find assets/gone.png in the deck's folder.", "slides[0].people[1]")]
    # Watched while missing, so the slide is drawn again once it is there.
    assert tmp_path / "assets" / "gone.png" in {Path(file) for file in drawing.files}
    with pytest.raises(MissingFile, match=r"Cannot find assets/gone\.png"):
        deck_from_document(document, tmp_path)


def test_a_bundle_carries_the_portraits(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    (tmp_path / "talk.yaml").write_text(dump_document(_deck(tmp_path, [{"image": names[0], "name": "Sam"}, names[1]])))
    gathered = B.gather(tmp_path / "talk.yaml")
    assert sorted(gathered.files) == ["assets/other.png", "assets/sam.jpeg", "talk.yaml"]
    named = {"slides": [{"people": ["a.png", {"image": "b.png"}]}]}
    names_in = [ref.name for ref in DeckKind().references(named, tmp_path)]
    assert names_in == ["a.png", "b.png"]


def test_the_powerpoint_crops_each_portrait_to_an_oval_and_the_pdf_draws_them(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    deck = deck_from_document(_deck(tmp_path, [{"image": names[0], "name": "Sam Pellock"}, names[1]]), tmp_path)
    result = deck.build(tmp_path / "out", formats=("pptx", "pdf"))
    slide = zipfile.ZipFile(result.pptx).read("ppt/slides/slide1.xml").decode()  # type: ignore[arg-type]
    pictures = re.findall(r"<p:pic>.*?</p:pic>", slide, re.S)
    assert len(pictures) == 2
    # A native picture cropped to its middle square (the rest there still), in an oval:
    # PowerPoint's Crop to Shape, Oval -- named, and described by the person's name.
    assert all('<a:prstGeom prst="ellipse">' in picture and 'name="Portrait"' in picture for picture in pictures)
    assert '<a:srcRect l="12500" t="0" r="12500" b="0"/>' in pictures[0] and 'descr="Sam Pellock"' in pictures[0]
    assert '<a:srcRect l="0" t="14286" r="0" b="14286"/>' in pictures[1]
    assert "Sam Pellock" in slide
    assert result.pdf is not None and result.pdf.read_bytes().count(b"/Subtype /Image") >= 2


PEOPLE_JS = """
const out = {};
const slide = { title: "A", people: ["a.png", { image: "b.png", name: "Bea" }] };
out.can = [canHavePeople({}), canHavePeople({ layout: "two-columns" }), canHavePeople({ layout: "title" })];
out.of = peopleOf(slide);
const added = structuredClone(slide);
out.at = addPeople(added, ["c.png", "d.png"], 1);
out.added = added.people;
const named = structuredClone(slide);
renamePerson(named, 0, "Al");
renamePerson(named, 1, " ");
out.named = named.people;
const moved = structuredClone(slide);
movePerson(moved, 0, 1);
out.moved = moved.people;
const removed = structuredClone(slide);
removePerson(removed, 0);
removePerson(removed, 0);
out.removed = "people" in removed;
const sized = structuredClone(slide);
out.sizedNone = peopleSize(sized);
out.changed = [setPeopleSize(sized, 101.4), setPeopleSize(sized, 101), setPeopleSize(sized, 900)];
out.sized = sized.people_size;
out.reset = [setPeopleSize(sized, null), "people_size" in sized];
setPeopleSize(sized, 80);
removePerson(sized, 0);
removePerson(sized, 0);
out.leftover = "people_size" in sized;
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_editor_adds_names_moves_and_removes_people_as_written() -> None:
    script = Path(__file__).parents[1] / "src/flexo_talk/studio/static/peoplelist.js"
    names = "canHavePeople, peopleOf, addPeople, removePerson, movePerson, renamePerson, peopleSize, setPeopleSize"
    code = f"import {{ {names} }} from {json.dumps(script.as_uri())};\n{PEOPLE_JS}"
    done = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
    found = json.loads(done.stdout)
    assert found["can"] == [True, True, False]
    assert found["of"] == [{"image": "a.png", "name": ""}, {"image": "b.png", "name": "Bea"}]
    assert found["at"] == 1 and found["added"] == ["a.png", "c.png", "d.png", {"image": "b.png", "name": "Bea"}]
    # A name written keeps the mapping; none, the file alone.
    assert found["named"] == [{"image": "a.png", "name": "Al"}, "b.png"]
    assert found["moved"] == [{"image": "b.png", "name": "Bea"}, "a.png"]
    assert found["removed"] is False
    # A size kept to a whole point within its range, a change said; none left, no size either.
    assert found["sizedNone"] is None and found["changed"] == [True, False, True] and found["sized"] == 160
    assert found["reset"] == [True, False] and found["leftover"] is False


def test_the_editor_offers_people_in_the_slide_s_inspector_and_the_palette() -> None:
    static = Path(__file__).parents[1] / "src/flexo_talk/studio/static"
    editor, people = (static / "editor.js").read_text("utf-8"), (static / "people.js").read_text("utf-8")
    assert 'h("div.section-title", {}, "People"), people.controls(slide)' in editor
    assert "people.commands()" in editor and "people.dropped(files, event)" in editor
    assert 'label: "Add Person to Title…"' in people and 'ui.button("Add Person…"' in people
    for label in ('"Add Person"', '"Remove Person"', '"Move Person"', '"Rename Person"'):
        assert label in people


def _portrait_boxes(deck: Deck) -> list[tuple[float, float, float, float]]:
    return [_box(item) for item in _drawn(compose.render_slide(deck, deck.slides[0]).svg, r"slide1\.person\d+")]


@pytest.mark.parametrize("look", ["classic", "band", "editorial"])
def test_portraits_are_nearly_two_lines_of_the_title_across_unless_the_slide_says(tmp_path: Path, look: str) -> None:
    names = _portraits(tmp_path)
    people = [{"image": names[0], "name": "Sam Pellock"}]
    document = _deck(tmp_path, people, subtitle="Designed in silico")
    document["deck"]["look"] = look
    deck = deck_from_document(document, tmp_path)
    line = compose._Canvas(deck, deck.slides[0]).measure(compose.inline("Hg"), deck.style.title_size, None, title=True)
    assert compose.PORTRAIT_SIZE >= 1.8
    (box,) = _portrait_boxes(deck)
    assert box[2] == pytest.approx(line.line_height * compose.PORTRAIT_SIZE)
    # The studio is told the default, to size them from and back to.
    svg = compose.render_slide(deck, deck.slides[0]).svg
    (drawn,) = _drawn(svg, r"slide1\.person0")
    assert float(drawn.get("data-flexo-default", "")) == pytest.approx(box[2], abs=0.01)
    # Their names readable: no smaller than before, no larger than the deck's small words.
    (name,) = _drawn(svg, r"slide1\.person0\.name")
    size = float(name.get("font-size", ""))
    assert deck.style.small_size * 0.78 <= size <= deck.style.small_size
    # Set, every portrait is that wide; within the room the title leaves them.
    document["slides"][0]["people_size"] = 100
    sized = deck_from_document(document, tmp_path)
    assert sized.slides[0].people_size == 100.0
    assert [box[2] for box in _portrait_boxes(sized)] == [pytest.approx(100.0)]


def test_people_size_is_read_checked_and_written_back_as_given(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    document = _deck(tmp_path, names, people_size=96)
    deck = deck_from_document(document, tmp_path)
    assert deck_document(deck)["slides"][0]["people_size"] == 96
    text = dump_document(deck_document(deck))
    assert "people_size: 96\n" in text
    from flexo_talk.document import parse_document

    again = deck_from_document(parse_document(text), tmp_path)
    assert again.slides[0].people_size == 96.0
    # Made in Python, as a document writes it; none, no key.
    made = Deck("made")
    with made.slide(TITLE) as each:
        each.person(tmp_path / names[0]).size_people(72.5)
    assert deck_document(made)["slides"][0]["people_size"] == 72.5
    made.slides[0].size_people(None)
    assert "people_size" not in deck_document(made)["slides"][0]
    # The agent's guide says it, its check says one wrong, and what it writes reads back.
    kind = DeckKind()
    assert "people_size: how wide each of the slide's portraits is, in points (24 to 160" in kind.guide()
    assert "people_size" in kind.catalog()["slide_keys"]["content"]
    assert kind.catalog()["people"]["sizes"] == [24.0, 160.0]
    written = {"schema_version": 1, **_deck(tmp_path, names, people_size=120)}
    assert kind.parse(kind.dump(written)) == written
    assert kind.check(_deck(tmp_path, names, people_size=500), tmp_path) == [
        "slides[0].people_size: people_size must be between 24 and 160, not 500."]


@pytest.mark.parametrize(("slide", "where", "said"), [
    ({"people_size": 500}, "slides[0].people_size", "people_size must be between 24 and 160, not 500."),
    ({"people_size": 10}, "slides[0].people_size", "people_size must be between 24 and 160, not 10."),
    ({"people_size": "big"}, "slides[0].people_size", "people_size must be a number, such as 96 (points), not 'big'."),
    ({"people_size": True}, "slides[0].people_size", "people_size must be a number, such as 96 (points), not True."),
    ({"layout": "section", "people_size": 80}, "slides[0].people_size",
     "A section slide has no title for people to stand beside"),
])
def test_a_people_size_said_wrong_is_said_under_its_key(tmp_path: Path, slide: dict, where: str, said: str) -> None:
    names = _portraits(tmp_path)
    document = _deck(tmp_path, names, **slide)
    if slide.get("layout") == "section":
        document["slides"][0].pop("body")
        document["slides"][0].pop("people")
    with pytest.raises(DeckDocumentError) as raised:
        deck_from_document(document, tmp_path)
    assert raised.value.where == where
    assert said in str(raised.value)


@pytest.mark.parametrize("look", ["classic", "band", "editorial"])
def test_large_portraits_keep_the_title_short_of_them_and_the_body_below(tmp_path: Path, look: str) -> None:
    names = _portraits(tmp_path)
    long = "A title long enough to run the whole width of the slide when nothing stands beside it"
    one = _deck(tmp_path, [{"image": names[0], "name": "Sam Pellock"}], title=long, people_size=160)
    one["deck"]["look"] = look
    deck = deck_from_document(one, tmp_path)
    style = deck.style
    svg = compose.render_slide(deck, deck.slides[0]).svg
    (box,) = [_box(item) for item in _drawn(svg, r"slide1\.person0")]
    assert box[2] == pytest.approx(160.0)
    # On the slide, no nearer its top than half its margin, its right end on the margin.
    assert box[1] >= style.margin * compose.PEOPLE_TOP - 0.01
    assert box[0] + box[2] == pytest.approx(style.width - style.margin, abs=0.01)
    # The title wraps short of it; the body starts below its name.
    title = _drawn(svg, r"slide1\.title")[0]
    assert style.margin + float(title.get("data-flexo-wrap", "").split()[0]) + compose.PEOPLE_ROOM <= box[0] + 0.01
    name = _drawn(svg, r"slide1\.person0\.name")[0]
    assert _box(_drawn(svg, r"slide1\.body")[0])[1] >= float(name.get("y", 0))
    # Three that large are made smaller together to keep to their share of the width.
    three = _deck(tmp_path, [names[0], names[1], names[0]], people_size=160)
    three["deck"]["look"] = look
    boxes = _portrait_boxes(deck_from_document(three, tmp_path))
    span = style.width - 2 * style.margin
    assert all(item[2] == pytest.approx(boxes[0][2]) for item in boxes) and boxes[0][2] < 160.0
    assert boxes[-1][0] + boxes[-1][2] - boxes[0][0] == pytest.approx(span * compose.PEOPLE_SHARE)


def test_the_powerpoint_draws_portraits_the_size_the_slide_sets(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    deck = deck_from_document(_deck(tmp_path, [{"image": names[0], "name": "Sam"}], people_size=110), tmp_path)
    result = deck.build(tmp_path / "out", formats=("pptx",))
    slide = zipfile.ZipFile(result.pptx).read("ppt/slides/slide1.xml").decode()  # type: ignore[arg-type]
    (picture,) = re.findall(r"<p:pic>.*?</p:pic>", slide, re.S)
    extent = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>', picture)
    assert extent and int(extent.group(1)) == int(extent.group(2)) == pytest.approx(110 * 12700, abs=2)


def test_the_editor_sizes_a_slide_s_portraits_in_its_inspector_and_by_a_corner() -> None:
    static = Path(__file__).parents[1] / "src/flexo_talk/studio/static"
    editor, people = (static / "editor.js").read_text("utf-8"), (static / "people.js").read_text("utf-8")
    portraits = (static / "portraits.js").read_text("utf-8")
    # Size, in the People section, as a logo's: points, Reset Size beside it once set.
    assert 'ui.field("Size"' in people and 'key: "people_size"' in people and 'ui.button("Reset Size"' in people
    for label in ('"Resize People"', '"Reset People Size"'):
        assert label in people and label in editor
    # On the slide: chosen, framed with a handle at each corner, drawn as it is dragged.
    assert "slidePortraits(people, {" in editor
    for hook in ("portraits.hover(event", "portraits.press(event)", "portraits.pick(event)", "portraits.context(event)",
                 "portraits.key(event)", "portraits?.place()", "portraits?.busy()", "portraits.commands()"):
        assert hook in editor, hook
    assert '"Reset People Size"' in portraits and "requestAnimationFrame(sizeDraw)" in portraits
    assert 'event.key !== "Escape"' in portraits


# -- placed freely: people_at --


def test_people_at_is_read_checked_and_written_back_as_given(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    document = _deck(tmp_path, names, people_at=[760, 400.5])
    deck = deck_from_document(document, tmp_path)
    assert deck.slides[0].people_at == (760.0, 400.5)
    assert deck_document(deck)["slides"][0]["people_at"] == [760, 400.5]
    text = dump_document(deck_document(deck))
    assert "people_at:\n  - 760\n  - 400.5\n" in text
    from flexo_talk.document import parse_document

    assert deck_from_document(parse_document(text), tmp_path).slides[0].people_at == (760.0, 400.5)
    # Made in Python, as a document writes it; put back, no key.
    made = Deck("made")
    with made.slide(TITLE) as each:
        each.person(tmp_path / names[0]).place_people((700, 420.25))
    assert deck_document(made)["slides"][0]["people_at"] == [700, 420.25]
    made.slides[0].place_people(None)
    assert "people_at" not in deck_document(made)["slides"][0]
    # The agent's guide says it, its catalogue lists it, its check says one wrong, and what it
    # writes reads back.
    kind = DeckKind()
    assert "people_at: [x, y], the row's top left on the slide, placed freely" in kind.guide()
    assert "people_at" in kind.catalog()["slide_keys"]["content"]
    written = {"schema_version": 1, **_deck(tmp_path, names, people_at=[760, 400])}
    assert kind.parse(kind.dump(written)) == written
    assert kind.check(_deck(tmp_path, names, people_at="corner"), tmp_path) == [
        "slides[0].people_at: people_at must be the people's top left on the slide, [x, y] in points from its "
        "top left (a slide is 960 across), such as [80, 120], not 'corner'."]


@pytest.mark.parametrize(("slide", "said"), [
    ({"people_at": "corner"}, "people_at must be the people's top left on the slide"),
    ({"people_at": [760]}, "such as [80, 120], not [760]."),
    ({"people_at": [760, True]}, "such as [80, 120], not [760, True]."),
    ({"people_at": [760, "low"]}, "such as [80, 120], not [760, 'low']."),
    ({"people_at": [20000, 0]}, "each within 10,000 of it, not [20000, 0]."),
    ({"layout": "section", "people_at": [10, 10]}, "A section slide has no title for people to stand beside"),
])
def test_a_people_at_said_wrong_is_said_under_its_key(tmp_path: Path, slide: dict, said: str) -> None:
    names = _portraits(tmp_path)
    document = _deck(tmp_path, names, **slide)
    if slide.get("layout") == "section":
        document["slides"][0].pop("body")
        document["slides"][0].pop("people")
    with pytest.raises(DeckDocumentError) as raised:
        deck_from_document(document, tmp_path)
    assert raised.value.where == "slides[0].people_at"
    assert said in str(raised.value)


def _layout(svg: str) -> dict:
    title = _drawn(svg, r"slide1\.title")[0]
    return {"wrap": float(title.get("data-flexo-wrap", "").split()[0]), "body": _box(_drawn(svg, r"slide1\.body")[0]),
            "band": [_box(item) for item in _drawn(svg, r"slide1\.band")]}


@pytest.mark.parametrize("look", ["classic", "band", "editorial"])
def test_people_placed_freely_stand_where_they_say_and_leave_the_header_alone(tmp_path: Path, look: str) -> None:
    names = _portraits(tmp_path)
    long = "A title long enough to run the whole width of the slide when nothing stands beside it"
    people = [{"image": names[0], "name": "Sam Pellock"}, {"image": names[1], "name": "Ana Ruiz"}]

    def drawn(**slide: object) -> str:
        document = _deck(tmp_path, people, title=long, **slide)
        document["deck"]["look"] = look
        deck = deck_from_document(document, tmp_path)
        return compose.render_slide(deck, deck.slides[0]).svg

    plain_document = _deck(tmp_path, None, title=long)
    plain_document["deck"]["look"] = look
    plain_deck = deck_from_document(plain_document, tmp_path)
    alone = _layout(compose.render_slide(plain_deck, plain_deck.slides[0]).svg)
    beside = _layout(drawn())
    moved_svg = drawn(people_size=96, people_at=[700, 380])
    moved = _layout(moved_svg)
    # Beside the title, it wraps short of them, and the header grows to hold them.
    assert beside["wrap"] < alone["wrap"]
    # Placed in the lower right: the title as wide, the body and band where they would be with no people.
    assert moved["wrap"] == pytest.approx(alone["wrap"])
    assert moved["body"][1] == pytest.approx(alone["body"][1])
    assert moved["band"] == alone["band"]
    # The row's top left where it says (a slide 960 across: its points); the second beside the first.
    boxes = [_box(item) for item in _drawn(moved_svg, r"slide1\.person\d")]
    row = [float(value) for value in _drawn(moved_svg, r"slide1\.person0")[0].get("data-flexo-row", "").split()]
    assert row[:2] == pytest.approx([700.0, 380.0])
    assert boxes[0][1] == pytest.approx(380.0) and boxes[0][2] == pytest.approx(96.0)
    assert 700.0 <= boxes[0][0] < boxes[1][0]
    # Drawn after the body, over it, as a placed object is.
    ids = [item.get("id", "") for item in ET.fromstring(moved_svg).iter()]
    assert ids.index("slide1.person0") > max(k for k, value in enumerate(ids) if value.startswith("slide1.body"))
    # Still beside the title's words, in the right half across from them, it wraps short of them.
    nudged = _layout(drawn(people_at=[700, 30]))
    assert nudged["wrap"] < alone["wrap"]
    assert 48 + nudged["wrap"] + compose.PEOPLE_ROOM <= 700.01


def test_the_powerpoint_puts_people_placed_freely_where_they_stand(tmp_path: Path) -> None:
    names = _portraits(tmp_path)
    deck = deck_from_document(_deck(tmp_path, [names[0], names[1]], people_size=80, people_at=[760, 420]), tmp_path)
    result = deck.build(tmp_path / "out", formats=("pptx",))
    slide = zipfile.ZipFile(result.pptx).read("ppt/slides/slide1.xml").decode()  # type: ignore[arg-type]
    pictures = re.findall(r"<p:pic>.*?</p:pic>", slide, re.S)
    offsets = [re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"/>', picture) for picture in pictures]
    assert len(offsets) == 2 and all(offsets)
    first, second = ((int(found.group(1)), int(found.group(2))) for found in offsets if found)
    assert first == (pytest.approx(760 * 12700, abs=2), pytest.approx(420 * 12700, abs=2))
    assert second[1] == first[1] and second[0] == pytest.approx((760 + 80 * (1 + compose.PORTRAIT_GAP)) * 12700, abs=2)


PEOPLE_AT_JS = """
const out = {};
const slide = { title: "A", people: ["a.png", "b.png"], people_size: 90 };
out.none = peopleAt(slide);
out.changed = [setPeopleAt(slide, [700.123, 40]), setPeopleAt(slide, [700.12, 40]), setPeopleAt(slide, [701, 40])];
out.at = slide.people_at;
out.read = peopleAt(slide);
out.back = [setPeopleAt(slide, null), "people_at" in slide, setPeopleAt(slide, null)];
setPeopleAt(slide, [10, 20]);
removePerson(slide, 0);
removePerson(slide, 0);
out.leftover = ["people_at" in slide, "people_size" in slide];
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_editor_places_people_and_puts_them_back_as_written() -> None:
    script = Path(__file__).parents[1] / "src/flexo_talk/studio/static/peoplelist.js"
    code = f"import {{ peopleAt, setPeopleAt, removePerson }} from {json.dumps(script.as_uri())};\n{PEOPLE_AT_JS}"
    done = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
    found = json.loads(done.stdout)
    assert found["none"] is None
    # To a hundredth, as an object's place is written; the same place again, no change.
    assert found["changed"] == [True, False, True] and found["at"] == [701, 40] and found["read"] == [701, 40]
    assert found["back"] == [True, False, False]
    # None left, no place for them either.
    assert found["leftover"] == [False, False]


def test_the_editor_moves_a_slide_s_people_on_it_and_puts_them_back() -> None:
    static = Path(__file__).parents[1] / "src/flexo_talk/studio/static"
    editor, people = (static / "editor.js").read_text("utf-8"), (static / "people.js").read_text("utf-8")
    portraits, placing = (static / "portraits.js").read_text("utf-8"), (static / "placing.js").read_text("utf-8")
    # Caught where an object would be: placing.js's carrier, given to the portraits.
    assert "carry: () => objects.carrier()" in editor and "function carrier()" in placing
    for label in ('"Move People"', '"Put People Back in Line"'):
        assert label in people
    assert 'label: "Put People Back in Line"' in portraits and "people.putBack()" in portraits
    # Drawn here as they are dragged, one frame at a time; Esc puts them back; placed, the arrows nudge them.
    assert "requestAnimationFrame(() => { if (moving === g)" in portraits
    assert 'event.key === "Escape"' in portraits and "moveCancel()" in portraits
    assert "nudge(event)" in portraits and "people-nudge-" in portraits

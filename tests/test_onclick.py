"""What a click shows anew (``flexo_talk.onclick``): an object, its parts, a figure's parts and a
slide's shapes hidden, dimmed, highlighted or shown again from a click on, held until a later
click changes them -- read and written back as written, checked, drawn as the slide is before its
first click, each step drawn as the slide would be were that how it is shown (a page of the PDF
each), and shown in place by the show, step after step, forward, back and on a jump."""

from __future__ import annotations

import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from flexo.showing import faint

from flexo_talk import Deck
from flexo_talk.compose import render_slide
from flexo_talk.document import DeckDocumentError, deck_document, deck_from_document
from flexo_talk.export import build_deck
from flexo_talk.onclick import at_step, click_of, nearly_click

STATIC = Path(__file__).parents[1] / "src" / "flexo_talk" / "studio" / "static"
DOM = Path(__file__).parent / "drawn_dom.mjs"
PAGE = "#ffffff"

FIGURE = {
    "figure": {"id": "sn2"},
    "nodes": [{"id": "nu", "label": "Nucleophile"}, {"id": "c", "label": "Carbon"}, {"id": "lg", "label": "Leaving"}],
    "groups": [{"id": "core", "children": ["c", "lg"], "label": "Substrate", "layout": {"kind": "row"}}],
    "edges": [{"from": "nu", "to": "c"}, {"from": "c", "to": "lg"}],
}
LIST = {"bullets": ["Attack", "Departure", "Inversion"]}


def deck_of(*slides: dict) -> dict:
    return {"schema_version": 1, "deck": {"id": "talk", "theme": "paper"}, "slides": list(slides)}


def rendered(document: dict, index: int = 0):
    deck = deck_from_document(document, ".")
    return render_slide(deck, deck.slides[index])


def drawn_as(root: ET.Element) -> dict[str, tuple]:
    """How each thing with an id is painted and shown: what a page of it shows."""

    keys = ("fill", "stroke", "visibility", "opacity", "data-flexo-show")
    found = {}
    for item in root.iter():
        ident = item.get("id")
        if not ident or ".arrow." in ident or ident.endswith(".dimmed"):
            continue  # (arrowheads' faint copies are named as they come)
        ends = tuple((item.get(end) or "").replace(".dimmed", "") for end in ("marker-start", "marker-end"))
        found[ident] = (*(item.get(key) for key in keys), *ends)
    return found


WALK = deck_of({
    "title": "SN2", "layout": "two-columns",
    "left": [{**LIST, "click 1": {"highlight": [1]}, "click 2": {"highlight": [2]}, "click 3": {}}],
    "right": [{"figure": FIGURE, "dim": ["lg"], "click 1": {"highlight": ["nu"]}, "click 2": {"hide": ["lg"]}}],
    "shapes": [{"kind": "ring", "at": [300, 220], "size": [120, 80], "hide": True, "click 2": {}}],
})


# -- the document --


def test_a_click_is_named_click_and_its_number() -> None:
    assert click_of("click 2") == 2 and click_of("click 0") is None and click_of("clicks") is None
    assert nearly_click("click2") and nearly_click("click 0") and nearly_click("Click_3") and not nearly_click("clip")


def test_what_a_click_shows_is_read_and_written_back_as_written() -> None:
    deck = deck_from_document(WALK, ".")
    slide = deck_document(deck)["slides"][0]
    assert slide["left"][0] == {**LIST, "click 1": {"highlight": [1]}, "click 2": {"highlight": [2]}, "click 3": {}}
    assert slide["right"][0]["dim"] == ["lg"] and slide["right"][0]["click 2"] == {"hide": ["lg"]}
    assert slide["shapes"][0]["click 2"] == {} and slide["shapes"][0]["hide"] is True


def test_python_says_it_as_a_document_does() -> None:
    with Deck("talk") as deck:
        slide = deck.slide("Steps")
        slide.bullets("One", "Two").show(highlight=[1], click=1).show(click=2)
    written = deck_document(deck)["slides"][0]["body"][0]
    assert written == {"bullets": ["One", "Two"], "click 1": {"highlight": [1]}, "click 2": {}}
    assert render_slide(deck, deck.slides[0]).steps == 3


@pytest.mark.parametrize(("block", "said"), [
    ({**LIST, "click2": {"dim": True}}, "click2 names no click: say click 2"),
    ({**LIST, "click 0": {"dim": True}}, "click 0 names no click"),
    ({**LIST, "click 1": "dim"}, "click 1 says how it is shown from that click on: a mapping"),
    ({**LIST, "click 1": {"dim": True, "size": 3}}, "with hide, dim and highlight alone, not size"),
    ({**LIST, "click 1": {"dim": ["x"]}}, "names a list\u2019s items by number"),
])
def test_what_a_click_cannot_say_is_said_where_it_is(block: dict, said: str) -> None:
    with pytest.raises(DeckDocumentError, match=said):
        deck_from_document(deck_of({"title": "S", "body": [block]}), ".")


def test_a_shape_says_it_as_an_object_does() -> None:
    bad = deck_of({"title": "S", "shapes": [{"kind": "ring", "at": [0, 0], "size": [9, 9], "click 1": {"dim": [1]}}]})
    with pytest.raises(DeckDocumentError, match="true or false"):
        deck_from_document(bad, ".")


# -- drawn --


def test_the_slide_has_a_step_for_each_click_it_names_after_its_builds() -> None:
    assert rendered(WALK).steps == 4
    built = deck_of({"title": "S", "body": [{"text": "a", "build": True}, {"text": "b", "build": True},
                                           {"text": "c", "click 1": {"dim": True}}]})
    # (Its first click both builds the first object in and dims the third.)
    made = rendered(built)
    assert made.steps == 3 and made.shows == {"slide1.body.2": ("shown", "dimmed", "dimmed")}


def test_its_drawing_is_the_slide_before_its_first_click() -> None:
    made = rendered(WALK)
    first = {**WALK, "slides": [{**WALK["slides"][0],
                                 "left": [LIST], "right": [{"figure": FIGURE, "dim": ["lg"]}],
                                 "shapes": [{"kind": "ring", "at": [300, 220], "size": [120, 80], "hide": True}]}]}
    plain = rendered(first)
    assert drawn_as(ET.fromstring(made.svg)) == drawn_as(ET.fromstring(plain.svg))


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_each_step_is_drawn_as_the_slide_would_be_were_that_how_it_is_shown(step: int) -> None:
    made = rendered(WALK)
    said = [
        ({}, {"dim": ["lg"]}, {"hide": True}),
        ({"highlight": [1]}, {"highlight": ["nu"]}, {"hide": True}),
        ({"highlight": [2]}, {"hide": ["lg"]}, {}),
        ({}, {"hide": ["lg"]}, {}),
    ][step - 1]
    alike = deck_of({**WALK["slides"][0], "left": [{**LIST, **said[0]}], "right": [{"figure": FIGURE, **said[1]}],
                     "shapes": [{"kind": "ring", "at": [300, 220], "size": [120, 80], **said[2]}]})
    assert drawn_as(ET.fromstring(made.at_step(step))) == drawn_as(ET.fromstring(rendered(alike).svg))


def test_a_figures_parts_shown_anew_carry_their_lines_their_group_and_its_box() -> None:
    made = rendered(WALK)
    # Carbon highlighted's other: its line to the leaving group faint with it, then gone with it.
    assert made.shows["slide1.right.0.edge.2.c-to-lg"] == ("dimmed", "dimmed", "hidden", "hidden")
    assert made.shows["slide1.right.0.c"] == ("shown", "dimmed", "shown", "shown")
    # The group's box and title faint with what it holds; the line to the nucleophile with it.
    assert made.shows["slide1.right.0.core.container"] == ("shown", "dimmed", "shown", "shown")
    assert made.shows["slide1.right.0.edge.1.nu-to-c"] == ("shown", "dimmed", "shown", "shown")
    assert "slide1.right.0.nu" not in made.shows


def test_what_is_faint_at_the_first_step_keeps_its_paints_as_they_are_plainly() -> None:
    root = ET.fromstring(rendered(WALK).svg)
    leaving = next(item for item in root.iter() if item.get("id") == "slide1.right.0.lg")
    body = next(item for item in leaving.iter() if item.get("data-flexo-was-fill"))
    assert body.get("fill") == faint(body.get("data-flexo-was-fill"), PAGE)
    at_step(root, 3)
    assert leaving.get("visibility") == "hidden" and body.get("fill") != faint(body.get("fill"), PAGE)
    assert not any(name.startswith("data-flexo-was-") for item in root.iter() for name in item.attrib)


def test_an_object_highlighted_on_a_click_draws_the_rest_of_the_slide_faint_then() -> None:
    made = rendered(deck_of({"title": "S", "body": [{"text": "a"}, {"text": "b", "click 1": {"highlight": True}}],
                             "shapes": [{"kind": "ring", "at": [0, 0], "size": [9, 9]}]}))
    assert made.shows == {"slide1.body.0": ("shown", "dimmed"), "slide1.shapes.0": ("shown", "dimmed")}


def test_the_pdf_has_a_page_for_each_step(tmp_path: Path) -> None:
    deck = deck_from_document(WALK, ".")
    made = build_deck(deck, tmp_path, ("pdf",))
    assert made.pdf.read_bytes().count(b"/Type /Page ") == 4
    handout = build_deck(deck, tmp_path / "handout", ("pdf",), handout=True)
    assert handout.pdf.read_bytes().count(b"/Type /Page ") == 1


# -- shown, step by step (stepping.js, run in Node) --




def _node(code: str) -> object:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (f"const S = await import({json.dumps((STATIC / 'stepping.js').as_uri())});\n"
              f"const {{ read, drawnAs }} = await import({json.dumps(DOM.as_uri())});\n{code}")
    done = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def test_the_show_shows_each_step_as_the_pdf_draws_it_whichever_way_it_goes() -> None:
    made = rendered(WALK)
    order = [2, 3, 4, 3, 1, 4, 2, 1, 3]
    seen = _node(f"""
      const svg = read({json.dumps(made.svg)});
      const seen = [];
      for (const step of {json.dumps(order)}) {{ S.showStep(svg, step); seen.push(drawnAs(svg)); }}
      console.log(JSON.stringify(seen));
    """)
    for step, shown in zip(order, seen, strict=True):
        expected = {ident: list(values) for ident, values in drawn_as(ET.fromstring(made.at_step(step))).items()}
        assert shown == expected, step


def test_what_builds_in_later_is_marked_so_and_the_edited_slide_has_it_all() -> None:
    built = rendered(deck_of({"title": "S", "body": [{"text": "a", "build": True}, {"text": "b", "build": True}]}))
    seen = _node(f"""
      const svg = read({json.dumps(built.svg)});
      const later = () => [...svg.walk()].filter((one) => one.hasAttribute("data-flexo-later")).map((one) => one.id);
      S.showStep(svg, 2); const two = later();
      S.showStep(svg, 1); const one = later();
      S.showStep(svg, 1, {{ builds: false }}); const edited = later();
      console.log(JSON.stringify({{ two, one, edited, faint: S.faint("#336699", "#ffffff") }}));
    """)
    assert seen == {"two": ["slide1.body.1"], "one": ["slide1.body.0", "slide1.body.1"], "edited": [],
                    "faint": faint("#336699", PAGE)}


# -- the PowerPoint --

_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def animations(xml: str) -> tuple[list, list[list]]:
    """A slide's animations, as PowerPoint plays them: those as it begins, and each click's --
    each ``(what, shape id, paragraphs, to)``."""

    root = ET.fromstring(xml)
    sequence = next(node for node in root.iter(f"{_P}cTn") if node.get("nodeType") == "mainSeq")
    start, clicks = [], []
    for step in sequence.find(f"{_P}childTnLst"):
        conditions = step.find(f"{_P}cTn/{_P}stCondLst")
        effects = []
        for effect in step.iter(f"{_P}cTn"):
            if effect.get("presetClass") is None:
                continue
            target = next(effect.iter(f"{_P}spTgt"))
            paragraph = target.find(f"{_P}txEl/{_P}pRg")
            to = next(effect.iter(f"{_P}strVal")).get("val")
            what = {"entr": "appear", "exit": "disappear", "emph": "fade"}[effect.get("presetClass")]
            effects.append((what, int(target.get("spid")), None if paragraph is None else int(paragraph.get("st")),
                            to if what == "fade" else None))
        begins = any(condition.get("evt") == "onBegin" for condition in conditions)
        (start if begins else clicks.append(effects) or []).extend(effects if begins else [])
    return start, clicks


def written(tmp_path: Path, document: dict) -> tuple[str, dict[str, int], list[tuple[str, int]]]:
    import zipfile

    made = build_deck(deck_from_document(document, tmp_path), tmp_path / "out", ("pptx",))
    xml = zipfile.ZipFile(made.pptx).read("ppt/slides/slide1.xml").decode()
    shapes = [(element.get("name"), int(element.get("id"))) for element in ET.fromstring(xml).iter(f"{_P}cNvPr")]
    return xml, dict(shapes), shapes


def test_each_step_is_a_click_of_the_powerpoint_its_faint_powerpoints_transparency(tmp_path: Path) -> None:
    xml, names, _ = written(tmp_path, deck_of({"title": "S", "body": [
        {**LIST, "click 1": {"highlight": [1]}, "click 2": {"highlight": [2]}, "click 3": {}},
        {"text": "Later", "hide": True, "click 2": {}},
        {"text": "Faint first", "dim": True, "click 1": {}}]}))
    start, clicks = animations(xml)
    listed = names["List “Attack Departure Inversion”"]
    later, first = names["Text “Later”"], names["Text “Faint first”"]
    # Faint as the slide begins, without waiting for a click: Transparency to flexo's faint.
    assert start == [("fade", first, None, "0.28")]
    assert len(clicks) == 3
    # The list's items faint and whole again by paragraph; the hidden words appear on click 2.
    assert ("fade", listed, 1, "0.28") in clicks[0] and ("fade", listed, 2, "0.28") in clicks[0]
    assert ("fade", first, None, "1") in clicks[0]
    assert ("fade", listed, 0, "0.28") in clicks[1] and ("fade", listed, 1, "1") in clicks[1]
    assert ("appear", later, None, None) in clicks[1]
    assert sorted(clicks[2]) == [("fade", listed, 0, "1"), ("fade", listed, 2, "1")]
    # Its first animation an Appear, the hidden words are not there before it.
    assert not any(effect[1] == later for effect in start + clicks[0])
    # Its paragraphs built as PowerPoint lists a list's.
    assert f'<p:bldP spid="{listed}" grpId="0" build="p"/>' in xml


def test_a_figures_parts_are_lifted_out_of_it_to_be_animated(tmp_path: Path) -> None:
    xml, names, _ = written(tmp_path, WALK)
    start, clicks = animations(xml)
    tree = next(ET.fromstring(xml).iter(f"{_P}spTree"))
    groups = [int(child.find(f"{_P}nvGrpSpPr/{_P}cNvPr").get("id")) for child in tree if child.tag == f"{_P}grpSp"
              and child.find(f"{_P}nvGrpSpPr/{_P}cNvPr").get("name") == "Group"]
    animated = {effect[1] for effect in start + [one for click in clicks for one in click]}
    # The leaving group's part and its line, faint from the start, then gone with the third click.
    faint_first = [effect[1] for effect in start if effect[1] in groups]
    assert faint_first and all(("disappear", spid, None, None) in clicks[1] for spid in faint_first)
    assert set(groups) <= animated
    # The ring hidden, appearing on the second click.
    assert ("appear", names["Highlight Ring"], None, None) in clicks[1]


def test_a_tables_rows_shown_anew_are_veiled_in_the_powerpoint(tmp_path: Path) -> None:
    xml, names, _ = written(tmp_path, deck_of({"title": "S", "body": [
        {"table": [["Step", "Barrier"], ["Attack", "12"], ["Leave", "9"]], "click 1": {"dim": [2]},
         "click 2": {"hide": ["3.2"]}}]}))
    start, clicks = animations(xml)
    faint_veil, hiding = names["Faint Veil over Row 2"], names["Veil over Row 3, Cell 2"]
    assert start == [] and [sorted(click) for click in clicks] == [
        [("appear", faint_veil, None, None)], [("appear", hiding, None, None), ("disappear", faint_veil, None, None)]]
    page = PAGE.lstrip("#").upper()
    assert f'<a:srgbClr val="{page}"><a:alpha val="72000"/></a:srgbClr>' in xml
    # Over the table, in the page's colour; the table's own words as they are.
    assert list(names).index("Table") < list(names).index("Faint Veil over Row 2")
    assert '<a:alpha val="0"/>' not in xml


def test_builds_and_steps_are_one_timeline(tmp_path: Path) -> None:
    xml, names, shapes = written(tmp_path, deck_of({"title": "S", "body": [
        {"text": "first", "build": True}, {"text": "second", "build": True},
        {"code": "a = 1\nb = 2", "click 1": {"highlight": [1]}, "click 3": {"dim": True}}]}))
    _, clicks = animations(xml)
    assert len(clicks) == 3
    assert clicks[0][0] == ("appear", names["Text “first”"], None, None)
    assert clicks[1] == [("appear", names["Text “second”"], None, None)]
    code = next(spid for name, spid in shapes if name.startswith("Code"))
    assert ("fade", code, None, "0.28") in clicks[2]
    assert xml.count('nodeType="clickEffect"') == 3


def test_what_is_faint_before_it_appears_is_made_faint_as_it_appears(tmp_path: Path) -> None:
    # (Its Appear first: PowerPoint has a paragraph or a shape whose first animation is its Appear
    # not there before it.)
    xml, _, shapes = written(tmp_path, deck_of({"title": "S", "body": [
        {"bullets": ["One", "Two", "Three"], "reveal": True, "dim": [2], "click 3": {}},
        {"text": "Built", "build": True, "dim": True, "click 2": {}},
        {"text": "Later", "build": True, "click 1": {"dim": True}}]}))
    start, clicks = animations(xml)
    listed = next(spid for name, spid in shapes if name.startswith("List"))
    built = next(spid for name, spid in shapes if name == "Text “Built”")
    later = next(spid for name, spid in shapes if name == "Text “Later”")
    assert start == []
    assert clicks[1][:2] == [("appear", listed, 1, None), ("fade", listed, 1, "0.28")]
    assert ("fade", listed, 1, "1") in clicks[2]
    # Faint as the slide begins, whole again from click 2, appearing on click 4: whole.
    assert clicks[3] == [("appear", built, None, None)]
    # Faint from click 1, appearing on click 5: faint as it appears.
    assert clicks[4] == [("appear", later, None, None), ("fade", later, None, "0.28")]
    assert not any(effect[1] in (built, later) for effect in [*start, *clicks[0], *clicks[1], *clicks[2]])

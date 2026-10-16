"""A deck's figures live in the deck (``flexo_talk.embedding``): written in a slide's block, or
-- one shown on several slides -- once in the deck's ``figures``, named ``'#name'``; a figure
file's figure embedded in the deck (one slide's, or every one), its files named from the deck's
folder, the file left alone; a figure of the deck's written out as a file of its own, and shown
from it when asked; and a deck bundled with its figure files written into it."""

from __future__ import annotations

import copy
import zipfile
from pathlib import Path

import pytest
import yaml
from flexo import bundle as B
from flexo.studio.figure_edit import EditError

from flexo_talk import embedding
from flexo_talk.compose import render_slide
from flexo_talk.document import DeckDocumentError, deck_from_document, dump_document, load_document, save_document
from flexo_talk.studio import DeckKind

SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8"/></svg>'
PIPELINE = {
    "figure": {"id": "pipeline"},
    "nodes": [{"id": "encoder", "label": "Encoder"}, {"id": "decoder", "label": "Decoder"}],
    "edges": [{"from": "encoder", "to": "decoder"}],
}
FIGURE_FILE = """\
# The pipeline, drawn once.
figure: {id: pipeline}
nodes:
- {id: encoder, label: Encoder}
- {id: logo, kind: image, properties: {source: ../pictures/logo.svg}}
edges:
- {from: encoder, to: logo}
"""


def _shared() -> dict:
    return {
        "schema_version": 1,
        "deck": {"id": "talk"},
        "slides": [
            {"title": "The pipeline", "body": [{"figure": "#pipeline"}]},
            {"title": "Where it fails", "body": [{"figure": "#pipeline", "dim": ["encoder"]}]},
        ],
        "figures": {"pipeline": copy.deepcopy(PIPELINE)},
    }


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A deck in a folder showing a figure file on two slides and another on one."""

    (tmp_path / "pictures").mkdir()
    (tmp_path / "pictures" / "logo.svg").write_text(SVG)
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "pipeline.yaml").write_text(FIGURE_FILE)
    (tmp_path / "figures" / "single.yaml").write_text("figure: {id: single}\nnodes:\n- {id: a, label: Alone}\n")
    document = {
        "schema_version": 1,
        "deck": {"id": "talk"},
        "slides": [
            {"title": "One", "body": [{"figure": "figures/pipeline.yaml"}]},
            {"title": "Two", "layout": "two-columns", "left": [{"text": "Words"}],
             "right": [{"figure": "figures/pipeline.yaml", "hide": ["logo"]}]},
            {"title": "Three", "body": [{"figure": "figures/single.yaml"}, {"figure": "made.py:figure"}]},
        ],
    }
    (tmp_path / "talk.yaml").write_text(dump_document(document))
    return tmp_path


def test_a_figure_kept_once_for_several_slides_is_drawn_on_each(tmp_path: Path) -> None:
    errors: list = []
    deck = deck_from_document(_shared(), tmp_path, errors=errors)
    assert not errors
    first, second = (render_slide(deck, slide).svg for slide in deck.slides)
    assert "slide1.body.0.encoder" in first and "slide2.body.0.encoder" in second
    # Shown on the second as its block says (its encoder dimmed), the figure as it is.
    assert deck.slides[1].regions["body"].blocks[0].figure.dimmed == ("encoder",)


def test_a_figure_named_that_the_deck_has_none_of_is_said_in_its_box(tmp_path: Path) -> None:
    document = _shared()
    document["slides"][0]["body"][0]["figure"] = "#nowhere"
    errors: list = []
    deck = deck_from_document(document, tmp_path, errors=errors)
    assert [error.where for error in errors] == ["slides[0].body[0] (figure)"]
    assert "no figure named “nowhere”" in errors[0].message and "#pipeline" in errors[0].message
    assert render_slide(deck, deck.slides[1]).svg  # the other slide draws as it is
    with pytest.raises(DeckDocumentError, match="figures must be a mapping"):
        deck_from_document({**_shared(), "figures": ["pipeline"]}, tmp_path)
    assert DeckKind().malformed({**_shared(), "figures": 3}) is not None


def test_a_decks_figures_are_written_after_its_slides_and_read_back(tmp_path: Path) -> None:
    text = dump_document({"figures": {"pipeline": PIPELINE}, **_shared()})
    assert text.index("slides:") < text.index("figures:")
    assert "figure: '#pipeline'" in text  # quoted: a bare # would start a comment
    save_document(_shared(), tmp_path / "talk.yaml")
    assert load_document(tmp_path / "talk.yaml") == _shared()


def test_a_figure_shown_on_several_slides_is_edited_once_where_the_deck_keeps_it(tmp_path: Path) -> None:
    kind, document = DeckKind(), _shared()
    at = {"slide": 1, "region": "body", "index": 0}
    read = kind.act(document, {"do": "figure", "at": at, "edit": {"do": "read"}}, tmp_path)
    assert read["model"]["figure"]["dim"] == ["encoder"]  # as this slide shows it
    rename = {"do": "update", "target": {"type": "node", "id": "decoder"}, "values": {"label": "Head"}}
    made = kind.act(document, {"do": "figure", "at": at, "edit": rename}, tmp_path)["document"]
    assert made["figures"]["pipeline"]["nodes"][1]["label"] == "Head"
    assert [block["body"][0]["figure"] for block in made["slides"]] == ["#pipeline", "#pipeline"]
    assert document == _shared()  # the one given is left alone
    # Shown apart on one slide: that slide's block says so, the figure is as it was.
    hide = {"do": "show", "ids": ["decoder"], "as": "hidden"}
    shown = kind.act(document, {"do": "figure", "at": {**at, "slide": 0}, "edit": hide}, tmp_path)["document"]
    assert shown["slides"][0]["body"][0] == {"figure": "#pipeline", "hide": ["decoder"]}
    assert shown["figures"] == _shared()["figures"]


def test_the_deck_says_which_figures_it_holds_for_a_tab_of_their_own() -> None:
    kind, document = DeckKind(), _shared()
    inline = {"figure": {"id": "here"}, "nodes": [{"id": "a", "label": "A"}]}
    document["slides"].append({"title": "Here", "body": [{"figure": inline}]})
    assert kind.figure_in(document, "pipeline") == PIPELINE
    assert kind.figure_in(document, "here") == inline
    assert kind.figure_in(document, "nowhere") is None
    changed = kind.with_figure(document, "here", {**inline, "nodes": [{"id": "b", "label": "B"}]})
    assert changed["slides"][2]["body"][0]["figure"]["nodes"] == [{"id": "b", "label": "B"}]
    assert document["slides"][2]["body"][0]["figure"] == inline
    assert kind.with_figure(document, "pipeline", PIPELINE)["figures"]["pipeline"] == PIPELINE
    assert kind.with_figure(document, "nowhere", PIPELINE) is None


def test_a_figure_file_is_embedded_in_the_deck_and_left_as_it_was(folder: Path) -> None:
    document = load_document(folder / "talk.yaml")
    at = {"slide": 2, "region": "body", "index": 0}
    result = DeckKind().act(document, {"do": "embed", "at": at}, folder)
    figure = result["document"]["slides"][2]["body"][0]["figure"]
    assert figure == {"figure": {"id": "single"}, "nodes": [{"id": "a", "label": "Alone"}]}
    assert result["released"] == [str(folder / "figures" / "single.yaml")] and result["embedded"] == 1
    assert result["document"]["slides"][2]["body"][1] == {"figure": "made.py:figure"}  # Python stays so
    assert (folder / "figures" / "single.yaml").exists()  # in a folder, the file is its person's
    assert result["document"]["slides"][0]["body"][0]["figure"] == "figures/pipeline.yaml"
    with pytest.raises(EditError, match="in the deck already"):
        DeckKind().act(result["document"], {"do": "embed", "at": at}, folder)


def test_every_figure_file_is_embedded_one_shown_twice_kept_once(folder: Path) -> None:
    before = (folder / "figures" / "pipeline.yaml").read_text()
    result = embedding.embed(load_document(folder / "talk.yaml"), folder)
    document = result["document"]
    assert sorted(path.name for path in result["files"]) == ["pipeline.yaml", "single.yaml"]
    assert document["slides"][0]["body"][0] == {"figure": "#pipeline"}
    assert document["slides"][1]["right"][0] == {"figure": "#pipeline", "hide": ["logo"]}  # shown as it was
    kept = document["figures"]["pipeline"]
    # Its picture named from the deck's folder now, not the file's.
    assert kept["nodes"][1]["properties"]["source"] == "pictures/logo.svg"
    assert (folder / "figures" / "pipeline.yaml").read_text() == before
    errors: list = []
    deck = deck_from_document(document, folder, errors=errors)
    assert not [error for error in errors if "made.py" not in str(error)]
    assert "slide2.right.0.encoder" in render_slide(deck, deck.slides[1]).svg
    assert result["said"] == "2 figures from “pipeline.yaml” and “single.yaml” are in the deck now, on 3 slides"
    # Nothing left to embed, the rest of the deck as it is.
    again = embedding.embed(document, folder)
    assert again["files"] == [] and again["document"] == document and again["said"] == "No figure was put in the deck."


def test_a_figure_file_that_is_not_there_is_left_named_and_said(folder: Path) -> None:
    document = load_document(folder / "talk.yaml")
    document["slides"][2]["body"][0]["figure"] = "figures/gone.yaml"
    result = embedding.embed(document, folder)
    assert result["document"]["slides"][2]["body"][0]["figure"] == "figures/gone.yaml"
    assert result["skipped"] == ["“figures/gone.yaml” isn\u2019t in the deck\u2019s folder."]


def test_a_figure_of_the_decks_is_exported_as_a_file_of_its_own(folder: Path) -> None:
    (folder / "assets").mkdir()
    (folder / "assets" / "mark.svg").write_text(SVG)
    figure = {"figure": {"id": "made"}, "nodes": [
        {"id": "mark", "kind": "image", "properties": {"source": "assets/mark.svg"}}, {"id": "b", "label": "B"}]}
    document = {"schema_version": 1, "deck": {"id": "talk", "theme": "dark"},
                "slides": [{"title": "Made", "body": [{"figure": figure}]}]}
    at = {"slide": 0, "region": "body", "index": 0}
    kept = DeckKind().act(document, {"do": "export-figure", "at": at, "name": "figures/made"}, folder)
    assert kept["written"] == "figures/made.yaml" and kept["document"] == document  # the deck keeps its copy
    written = yaml.safe_load((folder / "figures" / "made.yaml").read_text())
    assert written["figure"] == {"id": "made", "style": "dark"}  # in the deck's theme
    assert written["nodes"][0]["properties"]["source"] == "../assets/mark.svg"
    with pytest.raises(EditError, match="already exists"):
        DeckKind().act(document, {"do": "export-figure", "at": at, "name": "figures/made.yaml"}, folder)
    with pytest.raises(EditError, match="deck\u2019s folder"):
        DeckKind().act(document, {"do": "export-figure", "at": at, "name": "../outside.yaml"}, folder)
    # And shown from the file instead: the deck reads it, as any figure file.
    used = DeckKind().act(document, {"do": "export-figure", "at": at, "name": "figures/used", "use": True}, folder)
    assert used["document"]["slides"][0]["body"][0]["figure"] == "figures/used.yaml"
    assert used["released"] == [str(folder / "figures" / "used.yaml")]
    deck = deck_from_document(used["document"], folder)
    assert "slide1.body.0.mark" in render_slide(deck, deck.slides[0]).svg


def test_a_figure_shown_on_several_slides_is_shown_from_its_file_on_each(tmp_path: Path) -> None:
    at = {"slide": 1, "region": "body", "index": 0}
    made = embedding.export(_shared(), tmp_path, at, "pipeline.yaml", use=True)["document"]
    assert [slide["body"][0] for slide in made["slides"]] == [
        {"figure": "pipeline.yaml"}, {"figure": "pipeline.yaml", "dim": ["encoder"]}]
    assert "figures" not in made
    with pytest.raises(embedding.EmbedError, match="Python"):
        embedding.export({"slides": [{"body": [{"figure": "made.py:figure"}]}]}, tmp_path,
                         {"slide": 0, "region": "body", "index": 0}, "x.yaml")


def test_a_figure_exported_by_itself_is_written_as_the_deck_has_it(tmp_path: Path) -> None:
    written = DeckKind().export_part(_shared(), tmp_path, "talk", {"slide": 1, "region": "body", "index": 0}, ["yaml"])
    exported = yaml.safe_load(written[0].read_text())
    # As written, not as flexo fills it in: no root group, no ports, no ids for its lines.
    assert exported == {**PIPELINE, "figure": {"id": "pipeline"}}


def test_a_deck_is_bundled_with_its_figure_files_written_into_it(folder: Path) -> None:
    made = B.pack(folder / "talk.yaml")
    with zipfile.ZipFile(made.path) as opened:
        names = opened.namelist()
        bundled = yaml.safe_load(opened.read("talk.yaml"))
    assert "figures/pipeline.yaml" not in names and "figures/single.yaml" not in names
    assert "pictures/logo.svg" in names  # what the figure's parts draw, still
    assert bundled["slides"][0]["body"][0] == {"figure": "#pipeline"}
    assert bundled["figures"]["pipeline"]["nodes"][1]["properties"]["source"] == "pictures/logo.svg"
    assert load_document(folder / "talk.yaml")["slides"][0]["body"][0]["figure"] == "figures/pipeline.yaml"
    # Asked to, the files stay files.
    kept = B.pack(folder / "talk.yaml", folder / "kept.flexo", embed=False)
    with zipfile.ZipFile(kept.path) as opened:
        assert "figures/pipeline.yaml" in opened.namelist()


def test_the_guide_tells_agents_a_decks_figures_live_in_the_deck() -> None:
    guide = DeckKind().guide()
    assert "never as a figure file of its own unless the user asks" in guide and "'#name'" in guide


def test_an_edit_to_one_of_the_decks_figures_is_said_where_it_is_shown() -> None:
    before, after = _shared(), _shared()
    after["figures"]["pipeline"]["nodes"][0]["label"] = "Backbone"
    assert DeckKind().describe(before, after) == [
        {"text": "edited the figure “pipeline”", "where": {"page": 1, "label": "Slide 1"}}]


def test_the_structure_a_structure_is_coloured_by_is_found_and_moved_with_it(tmp_path: Path) -> None:
    """A diffusion frame coloured by the structure it ends as (``ss_from``): that file is
    found beside the deck, as the frame's own is, and named from wherever the figure goes."""

    from flexo_talk.document import _beside

    for name in ("t100.pdb", "t000.pdb"):
        (tmp_path / "frames").mkdir(exist_ok=True)
        (tmp_path / "frames" / name).write_text("END\n", encoding="utf-8")
    properties = {"source": "frames/t100.pdb", "ss_from": "frames/t000.pdb"}
    figure = {"figure": {"id": "run"}, "nodes": [{"id": "t100", "kind": "structure", "properties": properties}]}
    found = _beside(tmp_path, figure)["nodes"][0]["properties"]
    assert found["ss_from"] == str((tmp_path / "frames" / "t000.pdb").resolve())
    moved = embedding.rebased(figure, tmp_path, tmp_path / "figures")["nodes"][0]["properties"]
    assert moved == {"source": "../frames/t100.pdb", "ss_from": "../frames/t000.pdb"}

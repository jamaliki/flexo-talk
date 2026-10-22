"""A deck's pictures drawn into its slides -- an SVG drawn as a picture of its own, carrying its
faces; a photograph cut round in a gallery -- go to the studio's page by address, sent once, and
into every export, and every copy out of the page, as themselves: an export made after the
studio drew the deck is the export made without it, byte for byte."""

from __future__ import annotations

import base64
import hashlib
import re
import zipfile
from pathlib import Path

import pytest
import yaml

GRADED = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60" viewBox="0 0 200 60">'
    '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#eee"/>'
    '</linearGradient></defs><rect width="200" height="60" fill="url(#g)"/>'
    '<text x="10" y="45" font-size="40" font-family="Georgia" fill="#000">Words</text></svg>'
)

DECK = {
    "deck": {"id": "pictures"},
    "slides": [
        {
            "title": "Pictures",
            "layout": "two-columns",
            "left": [{"image": "graded.svg", "colours": {"#eeeeee": "#ff0000"}}],
            "right": [{"gallery": ["face.png"], "crop": "circle", "height": 120}],
        },
        {"title": "Words alone", "body": [{"text": "Nothing carried here."}]},
    ],
}

_DATA = re.compile(r'href="data:image/(png|jpeg|svg\+xml);base64,([^"]*)"')
_SUFFIX = {"png": "png", "jpeg": "jpg", "svg+xml": "svg"}


@pytest.fixture(autouse=True)
def _sessions(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from flexo.studio import inline_pictures

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path_factory.mktemp("run")))
    inline_pictures._KEPT.clear()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    import random

    from PIL import Image

    noise = random.Random(7)
    face = Image.frombytes("RGB", (240, 200), bytes(noise.randrange(256) for _ in range(240 * 200 * 3)))
    face.save(tmp_path / "face.png")
    (tmp_path / "graded.svg").write_text(GRADED, encoding="utf-8")
    (tmp_path / "talk.yaml").write_text(yaml.safe_dump(DECK, sort_keys=False), encoding="utf-8")
    return tmp_path


def _named(svg: str) -> str:
    """``svg`` with each picture it carries named as the studio names it for its page."""

    def name(found: re.Match[str]) -> str:
        from flexo.studio.inline_pictures import SMALLEST

        if len(found.group(2)) < SMALLEST:
            return found.group(0)
        digest = hashlib.sha256(found.group(2).encode("ascii")).hexdigest()[:32]
        return f'href="/api/picture?made={digest}.{_SUFFIX[found.group(1)]}&amp;token=T"'

    return re.sub(r"token=[^&\"]+", "token=T", _DATA.sub(name, svg))


def _drawn(workspace, document) -> list[dict]:
    pages: dict[str, dict] = {}
    for version in range(1, 40):
        result = workspace.draw("talk.yaml", document, version, {}, {"settle": True, "weigh": True})
        pages |= {page["id"]: page for page in result["pages"] if "svg" in page}
        if not result["unfinished"] and len(pages) == len(document["slides"]):
            return list(pages.values())
    raise AssertionError("never settled")


def _entries(pptx: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(pptx) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    dated = rb"<dcterms:(created|modified)[^>]*>[^<]*</dcterms:\1>"
    parts["docProps/core.xml"] = re.sub(dated, b"", parts["docProps/core.xml"])
    return parts


def test_a_slide_s_pictures_go_to_the_page_by_address_and_into_exports_as_themselves(folder: Path) -> None:
    from flexo.artwork import picture_link
    from flexo.studio import inline_pictures
    from flexo.studio.copying import copied
    from flexo.studio.workspace import Workspace
    from flexo.svg_resources import fonts_linked

    from flexo_talk.compose import PLACEHOLDERS, STANDING_ASIDE, render_slide
    from flexo_talk.document import deck_from_document
    from flexo_talk.studio import DeckKind, _presentable

    # The export the deck makes with no studio about.
    alone = DeckKind().export(DECK, folder, "talk", ["pptx", "svg"], into=folder / "alone")
    exported = {path.suffix: path for path in sorted(alone, reverse=True)}
    carried = exported[".svg"].read_text(encoding="utf-8")
    pictures = {found.group(1): found.group(2) for found in _DATA.finditer(carried)}
    assert set(pictures) == {"svg+xml", "png"}
    assert all(len(payload) >= inline_pictures.SMALLEST for payload in pictures.values())

    workspace = Workspace(folder)
    try:
        doc = workspace.open("talk.yaml")
        first, second = _drawn(workspace, doc.document)
        # The page is sent the slide with its two pictures named by address -- alike but for them.
        svg = first["svg"]
        links = re.findall(r'href="(/api/picture\?made=[^"]+)"', svg)
        assert len(links) == 2 and "data:image/svg+xml" not in svg and "data:image/png" not in svg
        assert all(f"token={workspace.token}" in link for link in links)
        assert "/api/picture" not in second["svg"]
        deck = deck_from_document(DECK, folder)
        # (Drawn as the studio draws for its page, but with nothing named by address.)
        placeholders, aside = PLACEHOLDERS.set(True), STANDING_ASIDE.set(True)
        try:
            with fonts_linked():
                assert picture_link.get() is None
                plain = render_slide(deck, deck.slides[0]).svg
        finally:
            PLACEHOLDERS.reset(placeholders)
            STANDING_ASIDE.reset(aside)
        assert _named(svg) == _named(_presentable(plain, deck, deck.slides[0]))
        # Each is the very picture the export carries, sent with its own type.
        for link in links:
            name = re.search(r"made=([^&]+)", link).group(1)
            data, kind = inline_pictures.found(name)
            assert base64.b64encode(data).decode("ascii") == pictures[kind.removeprefix("image/")]
        # Exported from the studio after it drew the deck for its page: the export made alone.
        made = doc.kind.export(doc.document, folder, "talk", ["pptx", "svg"], into=folder / "studio")
        again = {path.suffix: path for path in sorted(made, reverse=True)}
        assert _entries(again[".pptx"]) == _entries(exported[".pptx"])
        assert again[".svg"].read_text(encoding="utf-8") == carried
        # And drawn for the page again after the export, it is named by address still.
        redrawn = workspace.draw("talk.yaml", doc.document, 99, {}, {"settle": True})
        (page,) = [item for item in redrawn["pages"] if item["id"] == first["id"]]
        assert page.get("svg", svg) == svg

        # Copied out of the page -- the slide, or the picture alone -- it carries them as data.
        class Folder:
            def path(self, name: str) -> Path:
                return workspace.path(name)

        whole = copied(Folder(), svg).svg()
        assert "/api/picture" not in whole
        assert all(f"base64,{payload}" in whole for payload in pictures.values())
        alone_picture = copied(Folder(), svg, ["slide1.left.0"]).svg()
        assert f"data:image/svg+xml;base64,{pictures['svg+xml']}" in alone_picture
    finally:
        workspace.close()

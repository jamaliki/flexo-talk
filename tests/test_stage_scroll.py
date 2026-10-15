"""A slide zoomed in keeps where it is scrolled to as it is edited.

WebKit -- the Mac app's web view -- scrolls a size container (``container-type``) back to its
top each time what is in it is drawn again, and a slide is drawn again on every edit: zoomed
in, the view jumped up at each one. So the studio's stylesheets make nothing a size container:
what changes with the stage's width is told by its width (``fitStage``, a class).
"""

from __future__ import annotations

import re
from pathlib import Path

import flexo.studio
import pytest

SHEETS = sorted(
    [
        *(Path(__file__).parents[1] / "src" / "flexo_talk" / "studio" / "static").rglob("*.css"),
        *(Path(flexo.studio.__file__).parent / "static").rglob("*.css"),
    ]
)


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda sheet: sheet.name)
def test_no_stylesheet_of_the_studio_makes_a_size_container(sheet: Path) -> None:
    text = re.sub(r"/\*.*?\*/", "", sheet.read_text(encoding="utf-8"), flags=re.DOTALL)
    assert "container-type" not in text
    assert "@container" not in text


def test_a_narrow_stage_hides_the_words_under_the_slide_by_a_class() -> None:
    static = Path(__file__).parents[1] / "src" / "flexo_talk" / "studio" / "static"
    assert ".deck-stage.narrow .stage-hint" in (static / "editor.css").read_text(encoding="utf-8")
    assert 'stage.classList.toggle("narrow"' in (static / "editor.js").read_text(encoding="utf-8")

"""Tests lay figures out afresh: the figure cache goes to a scratch directory, and so do the
molecules and pictures flexo keeps drawn."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fresh_figure_cache(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEXO_TALK_CACHE", str(tmp_path_factory.mktemp("fits")))
    monkeypatch.setenv("FLEXO_STRUCTURE_CACHE", str(tmp_path_factory.mktemp("structures")))
    monkeypatch.setenv("FLEXO_PICTURE_CACHE", str(tmp_path_factory.mktemp("pictures")))

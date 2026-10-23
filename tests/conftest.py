"""Tests lay figures out afresh: the figure cache goes to a scratch directory, and so do the
molecules and pictures flexo keeps drawn and the noised structures' trajectories."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fresh_figure_cache(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEXO_TALK_CACHE", str(tmp_path_factory.mktemp("fits")))
    monkeypatch.setenv("FLEXO_STRUCTURE_CACHE", str(tmp_path_factory.mktemp("structures")))
    monkeypatch.setenv("FLEXO_PICTURE_CACHE", str(tmp_path_factory.mktemp("pictures")))
    monkeypatch.setenv("FLEXO_NOISE_CACHE", str(tmp_path_factory.mktemp("noise")))


@pytest.fixture(autouse=True)
def _nothing_laid_out_ahead(monkeypatch: pytest.MonkeyPatch) -> None:
    """Figures are not laid out ahead on a thread of their own while a test runs (what a test
    counts of them would be that thread's too): a test lays them out itself
    (flexo_talk.warming)."""

    from flexo_talk import warming

    monkeypatch.setattr(warming, "soon", lambda kind, slide: None)

"""Tests lay figures out afresh: the figure cache goes to a scratch directory."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fresh_figure_cache(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEXO_TALK_CACHE", str(tmp_path_factory.mktemp("fits")))

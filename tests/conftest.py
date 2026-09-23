"""Standard für alle Tests: DSS-Konfiguration (entspricht dem Verhalten vor dem Umzug)."""
from pathlib import Path

import pytest

from in_mcp import konfig, tools as t

BEISPIELE = Path(__file__).resolve().parents[1] / "beispiele"
DSS = konfig.laden(str(BEISPIELE / "instanz.dss.yaml"))
NEUTRAL = konfig.laden(str(BEISPIELE / "instanz.neutral.yaml"))


@pytest.fixture(autouse=True)
def dss_konfig(monkeypatch):
    monkeypatch.setattr(t, "K", DSS)
    if hasattr(t, "_LABEL_CACHE"):
        t._LABEL_CACHE.update(zeit=None, labels={})


@pytest.fixture
def neutral(monkeypatch):
    monkeypatch.setattr(t, "K", NEUTRAL)

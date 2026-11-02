"""H5 · GET /settings/effective — read-only default model + chunking."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.api.settings import read_effective_settings
from app.main import app
from app.schemas.settings import ChunkingOut, EffectiveSettings
from app.services import settings_service
from fastapi.testclient import TestClient


class ScriptedSession:
    """scalars(...).first() -> queued value."""

    def __init__(self, model: Any) -> None:
        self.model = model

    def scalars(self, *_a: object, **_k: object) -> SimpleNamespace:
        return SimpleNamespace(first=lambda: self.model)


def test_effective_settings_with_default_model() -> None:
    row = SimpleNamespace(
        id="m-1",
        name="Default",
        provider="openai",
        model_name="text-embedding-3-small",
        dimension=1536,
        is_default=True,
    )
    result = read_effective_settings(
        ScriptedSession(row), user=SimpleNamespace(tenant_id="t")
    )
    assert result.data.embedding_model is not None
    assert result.data.embedding_model.model_name == "text-embedding-3-small"
    assert result.data.embedding_model.dimension == 1536
    assert result.data.chunking.chunk_size > result.data.chunking.chunk_overlap >= 0


def test_effective_settings_without_model() -> None:
    result = read_effective_settings(
        ScriptedSession(None), user=SimpleNamespace(tenant_id="t")
    )
    assert result.data.embedding_model is None
    assert result.data.chunking.chunk_size == 512
    assert result.data.chunking.chunk_overlap == 50


def test_route_registered() -> None:
    client = TestClient(app)
    assert "/api/settings/effective" in client.get("/openapi.json").json()["paths"]


def test_service_shapes_response(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        settings_service,
        "select",
        lambda *a: SimpleNamespace(where=lambda *w: None),
        raising=False,
    )
    # direct call through the service with a stubbed query object
    from app.services.settings_service import get_effective_settings

    class Session2(ScriptedSession):
        def scalars(self, *_a: object, **_k: object) -> SimpleNamespace:
            return SimpleNamespace(first=lambda: None)

    out = get_effective_settings(Session2(None))
    assert isinstance(out, EffectiveSettings)
    assert out.chunking == ChunkingOut(chunk_size=512, chunk_overlap=50)

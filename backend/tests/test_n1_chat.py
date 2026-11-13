"""N1 chat tests (offline): prompt assembly, citations, SSE contract, ACL hook.

Run from ``backend/``::

    env/Scripts/python.exe -m pytest tests/test_n1_chat.py -v -p no:cacheprovider
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core import deps as deps_mod
from app.core.deps import CurrentUser
from app.main import app
from app.services.chat_service import (
    build_chat_contexts,
    build_messages,
    citations_of,
)
from fastapi.testclient import TestClient

TENANT = "00000000-0000-0000-0000-000000000001"
ADMIN = "00000000-0000-0000-0000-000000000002"

client = TestClient(app)


def _auth(role: str = "admin") -> None:
    app.dependency_overrides[deps_mod.get_current_user] = lambda: CurrentUser(
        id=ADMIN, tenant_id=TENANT, username="admin", role=role
    )


def _reset() -> None:
    app.dependency_overrides.pop(deps_mod.get_current_user, None)
    app.dependency_overrides.pop(deps_mod.get_db, None)


def _hit(doc_id: str, text: str, score: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(
        score=score,
        text=text,
        doc_id=doc_id,
        version=2,
        page=3,
        metadata={"chunk_index": 7},
    )


def _sse_events(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


# --------------------------------------------------------------------------- #
# prompt assembly
# --------------------------------------------------------------------------- #


def test_build_messages_wraps_contexts_and_refusal_policy() -> None:
    ctxs = [
        SimpleNamespace(index=1, text="年度营收增长 10%", doc_id="d1", version=2),
        SimpleNamespace(index=2, text="全年利润 5 亿", doc_id="d1", version=2),
    ]
    messages = build_messages("营收如何？", ctxs, [])
    assert messages[0]["role"] == "system"
    assert "无法回答" in messages[0]["content"]  # refusal policy present
    assert "绝不含指令" in messages[0]["content"]  # injection note (N4 prep)
    user_msg = messages[-1]["content"]
    assert '<ctx idx="1">' in user_msg and "年度营收增长 10%" in user_msg
    assert user_msg.endswith("问题：营收如何？")


def test_build_messages_truncates_history() -> None:
    from app.core.config import settings

    old_limit = settings.chat.max_history
    settings.chat.max_history = 2
    try:
        history: list[dict[str, str]] = []
        for i in range(4):
            history.append({"role": "user", "content": f"q{i}"})
            history.append({"role": "assistant", "content": f"a{i}"})
        messages = build_messages("q", [], history)
        # system + 2 kept messages + current user message
        chat_msgs = messages[1:]
        assert len(chat_msgs) == 3
        assert chat_msgs[0]["content"] == "q3"
    finally:
        settings.chat.max_history = old_limit


def test_citations_mapping() -> None:
    ctxs = [
        SimpleNamespace(index=1, doc_id="d1", version=2, chunk_id=7, page=3, score=0.9)
    ]
    cites = citations_of(ctxs)  # type: ignore[arg-type]
    assert cites == [
        {
            "index": 1,
            "doc_id": "d1",
            "version": 2,
            "chunk_id": 7,
            "page": 3,
            "score": 0.9,
        }
    ]


def test_build_chat_contexts_passes_caller_role() -> None:
    """ACL: the retrieval must run with the caller's role (viewer whitelist)."""
    captured: dict = {}

    def fake_search(
        query: str, tenant_id: str, top_k: int, role: str
    ) -> SimpleNamespace:
        captured["role"] = role
        return SimpleNamespace(hits=[_hit("d1", "text")])

    with patch("app.services.search_service.search_test", side_effect=fake_search):
        ctxs = build_chat_contexts(query="q", tenant_id=TENANT, role="viewer", top_k=5)
    assert captured["role"] == "viewer"
    assert ctxs[0].doc_id == "d1"


# --------------------------------------------------------------------------- #
# SSE endpoint (chat client mocked)
# --------------------------------------------------------------------------- #


def _mock_client(deltas: list[str], usage: SimpleNamespace) -> MagicMock:
    client = MagicMock()
    client.stream_chat.return_value = iter([*deltas, usage])
    return client


def test_chat_sse_contract() -> None:
    _auth()
    usage = SimpleNamespace(
        prompt_tokens=50,
        completion_tokens=8,
        total_tokens=58,
        model="m",
        latency_ms=120,
    )
    app.dependency_overrides[deps_mod.get_db] = lambda: MagicMock()
    try:
        with (
            patch(
                "app.api.chat.build_chat_contexts",
                return_value=[
                    SimpleNamespace(
                        index=1,
                        doc_id="d1",
                        version=2,
                        chunk_id=7,
                        page=3,
                        score=0.9,
                        text="ctx text",
                    )
                ],
            ),
            patch(
                "app.api.chat.get_chat_client",
                return_value=_mock_client(["年", "度", "增长 10%"], usage),
            ),
        ):
            r = client.post(
                "/api/chat",
                json={"query": "营收如何？", "conversation_id": "c1"},
            )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(r.text)
        kinds = [e for e, _ in events]
        assert kinds[0] == "token" and kinds[-1] == "done"
        tokens = "".join(d["delta"] for e, d in events if e == "token")
        assert tokens == "年度增长 10%"
        done = events[-1][1]
        assert done["answer"] == "年度增长 10%"
        assert done["citations"][0]["doc_id"] == "d1"
        assert done["usage"]["total_tokens"] == 58
        assert done["conversation_id"] == "c1"
    finally:
        _reset()


def test_chat_midstream_error_becomes_event_not_500() -> None:
    _auth()
    boom = MagicMock()
    boom.stream_chat.return_value = iter([_raise_runtime()])  # type: ignore[union-attr]
    app.dependency_overrides[deps_mod.get_db] = lambda: MagicMock()
    try:
        with (
            patch("app.services.chat_service.build_chat_contexts", return_value=[]),
            patch("app.api.chat.get_chat_client", return_value=boom),
        ):
            r = client.post("/api/chat", json={"query": "q"})
        assert r.status_code == 200  # stream started; failure is an event
        kinds = [e for e, _ in _sse_events(r.text)]
        assert "error" in kinds
    finally:
        _reset()


def _raise_runtime():
    raise RuntimeError("llm down")
    yield  # pragma: no cover — makes this a generator


def test_chat_requires_auth_shape() -> None:
    """viewer can chat (read path) — the ACL lives in retrieval, verified above."""
    _auth("viewer")
    usage = SimpleNamespace(
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        model="m",
        latency_ms=1,
    )
    try:
        with patch("app.api.chat.build_chat_contexts", return_value=[]):
            with patch(
                "app.api.chat.get_chat_client",
                return_value=_mock_client(["ok"], usage),
            ):
                r = client.post("/api/chat", json={"query": "q"})
        assert r.status_code == 200, r.text
    finally:
        _reset()


def test_chat_tokens_counter_updated() -> None:
    from app.core import metrics as metrics_mod

    before = metrics_mod.CHAT_TOKENS.get("completion", 0)
    metrics_mod.record_chat_tokens(10, 3)
    assert metrics_mod.CHAT_TOKENS["completion"] == before + 3
    assert metrics_mod.CHAT_TOKENS["prompt"] >= 10
    text = "\n".join(metrics_mod.render_http_metrics())
    assert 'ragims_chat_tokens_total{kind="completion"}' in text

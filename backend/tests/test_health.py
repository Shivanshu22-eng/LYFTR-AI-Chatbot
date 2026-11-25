"""
Tests for LYFTR AI Chatbot backend.
Covers: health, database, multi-key LiteLLM failover, caching,
        X-Simulate-Failure, key redaction, and API routes.
"""

import os
import sys
import pytest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set a test database path BEFORE importing app modules
TEST_DB = os.path.join(os.path.dirname(__file__), "test_lyftr.db")
os.environ["DATABASE_PATH"] = TEST_DB


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_test_db():
    """Remove test DB before and after each test."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    from app.database import init_db
    init_db()
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def _make_llm_response(content="Hello!", prompt_tokens=10, completion_tokens=5, cache_hit=False):
    """Build a mock LiteLLM response object."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        _hidden_params={"cache_hit": cache_hit},
    )


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert data["database"] == "sqlite"
        assert "keys_configured" in data
        assert "cache_enabled" in data

    def test_health_keys_count(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert isinstance(data["keys_configured"], int)

    def test_health_schema_allows_minimal_fields(self):
        from app.schemas import HealthResponse
        h = HealthResponse(status="ok", keys_configured=2, cache_enabled=True)
        assert h.status == "ok"
        assert h.keys_configured == 2
        assert h.cache_enabled is True


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class TestDatabase:
    def test_create_and_get_session(self):
        from app.database import create_session, get_session
        s = create_session(title="Test Session")
        assert s["title"] == "Test Session"
        fetched = get_session(s["id"])
        assert fetched is not None
        assert fetched["title"] == "Test Session"

    def test_get_sessions_ordered(self):
        from app.database import create_session, get_sessions
        create_session(title="First")
        create_session(title="Second")
        sessions = get_sessions()
        assert sessions[0]["title"] == "Second"

    def test_save_and_get_messages(self):
        from app.database import create_session, save_message, get_messages
        s = create_session()
        save_message(s["id"], "user", "Hello")
        save_message(
            s["id"], "assistant", "Hi there!",
            model="gemini/gemini-3.8-flash",
            resolution_source="LIVE_INFERENCE",
            latency_ms=123.4,
            input_tokens=10,
            output_tokens=20,
            key_id="key-1",
            fallback_attempts=0,
        )
        msgs = get_messages(s["id"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["key_id"] == "key-1"
        assert msgs[1]["fallback_attempts"] == 0
        assert msgs[1]["resolution_source"] == "LIVE_INFERENCE"

    def test_missing_session_returns_none(self):
        from app.database import get_session
        assert get_session("nonexistent-id") is None


# ---------------------------------------------------------------------------
# Chat service — key management & failover
# ---------------------------------------------------------------------------

class TestChatServiceKeys:
    def test_mask_key(self):
        from app.chat_service import _mask_key
        assert _mask_key("abcdefghij") == "...ghij"
        assert _mask_key("ab") == "***"

    def test_sanitize_error_redacts_keys(self):
        from app.chat_service import _sanitize_error
        keys = [{"key": "AIzaSySecretKey1", "key_id": "key-1"}]
        sanitized = _sanitize_error("Auth failed with AIzaSySecretKey1!", keys)
        assert "AIzaSySecretKey1" not in sanitized
        assert "[REDACTED:key-1]" in sanitized

    def test_is_retryable_429(self):
        from app.chat_service import _is_retryable
        assert _is_retryable(Exception("Error code: 429")) is True

    def test_is_retryable_quota(self):
        from app.chat_service import _is_retryable
        assert _is_retryable(Exception("Resource exhausted, quota exceeded")) is True

    def test_is_retryable_5xx(self):
        from app.chat_service import _is_retryable
        assert _is_retryable(Exception("Status: 500 Internal Server Error")) is True
        assert _is_retryable(Exception("Status: 503 Service Unavailable")) is True

    def test_is_retryable_normal_error(self):
        from app.chat_service import _is_retryable
        assert _is_retryable(Exception("Invalid argument")) is False

    def test_reload_multiple_keys(self, monkeypatch):
        from app import chat_service
        monkeypatch.setenv("LLM_API_KEYS", "gemini-secret-1,gemini-secret-2")
        keys = chat_service.reload_api_keys()
        assert len(keys) == 2
        assert keys[0]["key_id"] == "key-1"
        assert keys[1]["key_id"] == "key-2"

    @pytest.mark.asyncio
    async def test_failover_on_429_and_live_inference(self, monkeypatch):
        from app import chat_service
        monkeypatch.setenv("LLM_API_KEYS", "secret-key-one,secret-key-two")
        chat_service.reload_api_keys()

        calls = []

        async def fake_acompletion(**kwargs):
            calls.append(kwargs["api_key"])
            if len(calls) == 1:
                raise Exception("429 Too Many Requests: quota exceeded")
            return _make_llm_response("Recovered!", prompt_tokens=15, completion_tokens=7, cache_hit=False)

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            res = await chat_service.get_ai_response([{"role": "user", "content": "hi"}])

        assert res["content"] == "Recovered!"
        assert res["resolution_source"] == "LIVE_INFERENCE"
        assert res["key_id"] == "key-2"
        assert res["fallback_attempts"] == 1
        assert res["input_tokens"] == 15
        assert res["output_tokens"] == 7
        assert res["latency_ms"] >= 0
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_cache_hit_returns_llm_cache(self, monkeypatch):
        from app import chat_service
        monkeypatch.setenv("LLM_API_KEYS", "secret-key-one,secret-key-two")
        chat_service.reload_api_keys()

        with patch("litellm.acompletion", new_callable=AsyncMock) as mock_ac:
            mock_ac.return_value = _make_llm_response("Cached!", prompt_tokens=10, completion_tokens=4, cache_hit=True)
            res = await chat_service.get_ai_response([{"role": "user", "content": "hi"}])

        assert res["resolution_source"] == "LLM_CACHE"
        assert res["content"] == "Cached!"
        assert res["input_tokens"] == 10
        assert res["output_tokens"] == 4
        assert res["key_id"] is None
        assert res["fallback_attempts"] == 0

    @pytest.mark.asyncio
    async def test_simulate_failure_bypasses_cache_and_fails_over(self, monkeypatch):
        from app import chat_service
        monkeypatch.setenv("LLM_API_KEYS", "secret-key-one,secret-key-two")
        chat_service.reload_api_keys()

        captured_kwargs = {}

        async def fake_acompletion(**kwargs):
            captured_kwargs.update(kwargs)
            return _make_llm_response("Failover OK", prompt_tokens=8, completion_tokens=3, cache_hit=True)

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            res = await chat_service.get_ai_response(
                [{"role": "user", "content": "hi"}],
                simulate_failure="429",
            )

        assert captured_kwargs.get("cache") == {"no-cache": True}
        assert res["resolution_source"] == "LIVE_INFERENCE"
        assert res["key_id"] == "key-2"
        assert res["fallback_attempts"] == 1

    @pytest.mark.asyncio
    async def test_all_keys_fail_redacts_keys(self, monkeypatch):
        from app import chat_service
        monkeypatch.setenv("LLM_API_KEYS", "secret-key-alpha,secret-key-beta")
        chat_service.reload_api_keys()

        async def fake_acompletion(**kwargs):
            raise Exception(f"503 Service Unavailable for {kwargs['api_key']}")

        with patch("litellm.acompletion", side_effect=fake_acompletion):
            with pytest.raises(RuntimeError) as exc_info:
                await chat_service.get_ai_response([{"role": "user", "content": "hi"}])

        err_str = str(exc_info.value)
        assert "secret-key-alpha" not in err_str
        assert "secret-key-beta" not in err_str


# ---------------------------------------------------------------------------
# API routes — chat
# ---------------------------------------------------------------------------

class TestChatRoute:
    def test_chat_missing_session_id_rejected(self, client):
        """POST /chat without session_id must return HTTP 422."""
        resp = client.post("/chat", json={"message": "Hi"})
        assert resp.status_code == 422

    def test_chat_live_inference_response(self, client):
        """POST /chat with a valid session_id returns session_id, reply, metadata with resolution_source."""
        from app.database import create_session
        s = create_session(title="Live")
        with patch("app.main.get_ai_response", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = {
                "content": "Hello from AI!",
                "model": "gemini/gemini-3.8-flash",
                "resolution_source": "LIVE_INFERENCE",
                "latency_ms": 150.0,
                "input_tokens": 12,
                "output_tokens": 8,
                "key_id": "key-1",
                "fallback_attempts": 0,
            }
            resp = client.post("/chat", json={"message": "Hi", "session_id": s["id"]})
            assert resp.status_code == 200
            data = resp.json()
            assert data["session_id"] == s["id"]
            assert data["reply"] == "Hello from AI!"
            meta = data["metadata"]
            assert meta["resolution_source"] == "LIVE_INFERENCE"
            assert meta["model"] == "gemini/gemini-3.8-flash"
            assert meta["latency_ms"] == 150.0
            assert meta["input_tokens"] == 12
            assert meta["output_tokens"] == 8
            assert meta["key_id"] == "key-1"
            assert meta["fallback_attempts"] == 0

    def test_chat_with_existing_session(self, client):
        """POST /chat with a valid session_id should reuse it and return LLM_CACHE."""
        from app.database import create_session
        s = create_session(title="Existing")
        with patch("app.main.get_ai_response", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = {
                "content": "Response",
                "model": "gemini/gemini-3.8-flash",
                "resolution_source": "LLM_CACHE",
                "latency_ms": 5.0,
                "input_tokens": 10,
                "output_tokens": 5,
                "key_id": None,
                "fallback_attempts": 0,
            }
            resp = client.post("/chat", json={
                "message": "Hello",
                "session_id": s["id"],
            })
            assert resp.status_code == 200
            data = resp.json()
            assert data["session_id"] == s["id"]
            assert data["reply"] == "Response"
            assert data["metadata"]["resolution_source"] == "LLM_CACHE"
            assert data["metadata"]["key_id"] is None
            assert data["metadata"]["fallback_attempts"] == 0

    def test_chat_missing_session_404(self, client):
        resp = client.post("/chat", json={
            "message": "Hello",
            "session_id": "nonexistent",
        })
        assert resp.status_code == 404

    def test_chat_simulate_failure_header_requires_env(self, client, monkeypatch):
        """X-Simulate-Failure is ignored unless ENABLE_FAILURE_SIMULATION=true."""
        from app.database import create_session
        s = create_session(title="Sim Gate")
        monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "false")
        with patch("app.main.get_ai_response", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = {
                "content": "Normal reply",
                "model": "gemini/gemini-3.8-flash",
                "resolution_source": "LIVE_INFERENCE",
                "latency_ms": 10.0,
                "input_tokens": 5,
                "output_tokens": 5,
                "key_id": "key-1",
                "fallback_attempts": 0,
            }
            resp = client.post(
                "/chat",
                json={"message": "test", "session_id": s["id"]},
                headers={"X-Simulate-Failure": "all_keys_fail"},
            )
            assert resp.status_code == 200
            assert mock_ai.call_args.kwargs["simulate_failure"] is None

    def test_chat_simulate_failure_header(self, client, monkeypatch):
        """X-Simulate-Failure: all_keys_fail should return 503 when enabled and NOT store the message."""
        from app.database import create_session, get_messages
        monkeypatch.setenv("ENABLE_FAILURE_SIMULATION", "true")
        s = create_session(title="Fail Test")
        with patch("app.main.get_ai_response", new_callable=AsyncMock) as mock_ai:
            mock_ai.side_effect = RuntimeError("Simulated 503 Service Unavailable")
            resp = client.post(
                "/chat",
                json={"message": "should not be saved", "session_id": s["id"]},
                headers={"X-Simulate-Failure": "all_keys_fail"},
            )
            assert resp.status_code == 503
            assert mock_ai.call_args.kwargs["simulate_failure"] == "all_keys_fail"
        assert get_messages(s["id"]) == []

    def test_chat_empty_message_rejected(self, client):
        resp = client.post("/chat", json={"message": "", "session_id": "valid-session"})
        assert resp.status_code == 422

    def test_chat_whitespace_message_rejected(self, client):
        resp = client.post("/chat", json={"message": "   \n\t  ", "session_id": "valid-session"})
        assert resp.status_code == 422

    def test_chat_message_length_4000_after_trim(self, client):
        from app.database import create_session
        s = create_session(title="Len Test")
        with patch("app.main.get_ai_response", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = {
                "content": "OK",
                "model": "gemini/gemini-3.8-flash",
                "resolution_source": "LIVE_INFERENCE",
                "latency_ms": 10.0,
                "input_tokens": 5,
                "output_tokens": 2,
                "key_id": "key-1",
                "fallback_attempts": 0,
            }
            ok = client.post("/chat", json={"message": "  " + ("a" * 4000) + "  ", "session_id": s["id"]})
            assert ok.status_code == 200
        too_long = client.post("/chat", json={"message": "  " + ("a" * 4001) + "  ", "session_id": s["id"]})
        assert too_long.status_code == 422

    def test_chat_session_id_length_128(self, client):
        empty_sid = client.post("/chat", json={"message": "hi", "session_id": ""})
        assert empty_sid.status_code == 422
        too_long_sid = client.post("/chat", json={"message": "hi", "session_id": "s" * 129})
        assert too_long_sid.status_code == 422
        blank_sid = client.post("/chat", json={"message": "hi", "session_id": "   "})
        assert blank_sid.status_code == 422

    def test_chat_optional_system_prompt(self, client):
        from app.database import create_session
        s = create_session(title="System Prompt")
        captured = []

        async def fake_ai(messages, model=None, simulate_failure=None):
            captured.append(list(messages))
            return {
                "content": "Pirate ahoy!",
                "model": "gemini/gemini-3.8-flash",
                "resolution_source": "LIVE_INFERENCE",
                "latency_ms": 10.0,
                "input_tokens": 10,
                "output_tokens": 5,
                "key_id": "key-1",
                "fallback_attempts": 0,
            }

        with patch("app.main.get_ai_response", side_effect=fake_ai):
            resp = client.post(
                "/chat",
                json={"message": "Hello", "session_id": s["id"], "system_prompt": "Speak like a pirate."},
            )
            assert resp.status_code == 200
        assert captured[0][0] == {"role": "system", "content": "Speak like a pirate."}

    def test_multi_turn_conversation_history(self, client):
        """Second turn in same session passes full prior conversation history."""
        from app.database import create_session
        s = create_session(title="Multi-turn")
        captured_histories = []

        async def fake_ai(messages, model=None, simulate_failure=None):
            captured_histories.append(list(messages))
            return {
                "content": f"Reply {len(captured_histories)}",
                "model": "gemini/gemini-3.8-flash",
                "resolution_source": "LIVE_INFERENCE",
                "latency_ms": 50.0,
                "input_tokens": 10,
                "output_tokens": 5,
                "key_id": "key-1",
                "fallback_attempts": 0,
            }

        with patch("app.main.get_ai_response", side_effect=fake_ai):
            r1 = client.post("/chat", json={"message": "First question", "session_id": s["id"]})
            assert r1.status_code == 200
            sid = r1.json()["session_id"]

            r2 = client.post("/chat", json={"message": "Follow-up", "session_id": sid})
            assert r2.status_code == 200

        # Turn 2 history: system + user1 + assistant1 + user2
        assert len(captured_histories[1]) == 4
        assert captured_histories[1][1] == {"role": "user", "content": "First question"}
        assert captured_histories[1][2] == {"role": "assistant", "content": "Reply 1"}
        assert captured_histories[1][3] == {"role": "user", "content": "Follow-up"}

    def test_session_separation(self, client):
        """Messages in session A must not leak into session B."""
        from app.database import create_session
        s_a_obj = create_session(title="A")
        s_b_obj = create_session(title="B")
        with patch("app.main.get_ai_response", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = {
                "content": "Answer",
                "model": "gemini/gemini-3.8-flash",
                "resolution_source": "LIVE_INFERENCE",
                "latency_ms": 20.0,
                "input_tokens": 5,
                "output_tokens": 5,
                "key_id": "key-1",
                "fallback_attempts": 0,
            }
            s_a = client.post("/chat", json={"message": "Secret A", "session_id": s_a_obj["id"]}).json()["session_id"]
            s_b = client.post("/chat", json={"message": "Secret B", "session_id": s_b_obj["id"]}).json()["session_id"]

        assert s_a != s_b
        msgs_a = client.get(f"/sessions/{s_a}/messages").json()
        msgs_b = client.get(f"/sessions/{s_b}/messages").json()
        assert [m["content"] for m in msgs_a] == ["Secret A", "Answer"]
        assert [m["content"] for m in msgs_b] == ["Secret B", "Answer"]


# ---------------------------------------------------------------------------
# Sessions & messages routes
# ---------------------------------------------------------------------------

class TestSessionRoutes:
    def test_list_sessions_empty(self, client):
        resp = client.get("/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_session(self, client):
        resp = client.post("/sessions")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["title"] == "New Chat"

    def test_get_messages_404(self, client):
        resp = client.get("/sessions/fake-id/messages")
        assert resp.status_code == 404

    def test_get_messages_for_session(self, client):
        from app.database import create_session, save_message
        s = create_session()
        save_message(s["id"], "user", "Hello")
        save_message(
            s["id"], "assistant", "Hi",
            resolution_source="LIVE_INFERENCE", model="gemini/gemini-3.8-flash",
            latency_ms=100, input_tokens=5, output_tokens=3,
            key_id="key-1", fallback_attempts=0,
        )
        resp = client.get(f"/sessions/{s['id']}/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert len(msgs) == 2
        assert msgs[1]["meta"]["key_id"] == "key-1"
        assert msgs[1]["meta"]["resolution_source"] == "LIVE_INFERENCE"

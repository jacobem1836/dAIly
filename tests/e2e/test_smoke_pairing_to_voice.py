"""E2E smoke test: pairing → onboarding (Google OAuth) → voice token → agent greeting → approval.

Exercises the full new-user happy path against the full FastAPI app in a single
test function. External services are mocked at their HTTP/SDK boundaries.

Steps (test_full_user_onboarding_to_voice_connect):
  1. Send magic link (POST /auth/pair/send-link) — 204
  2. Extract pairing code from DB
  3. Complete pairing (POST /auth/pair/complete) — 200 with tokens
  4. Connect Google integration (GET /integrations/google/connect) — 200
  5. Simulate Google OAuth callback — 302 redirect
  6. Set briefing schedule (PUT /users/me/preferences) — 204
  7. Read integration status (GET /users/me/integrations) — 200, google=True
  8. Issue LiveKit token (POST /livekit/token) — 200 with JWT-shaped token
  9. Refresh access token (POST /auth/token/refresh) — 200 with new token

Steps (test_worker_agent_greeting_and_approval_round_trip):
  10. Simulate worker agent joining (LiveKit boundary faked) — greeting produced via
      DailyLLMBridge + real build_graph()
  11. Drive a draft-intent turn through the bridge — graph pauses at approval interrupt()
  12. Assert action has NOT executed yet (gate is genuine)
  13. Resume with Command(resume="confirm") — graph advances to execute
  14. Assert action was invoked exactly once and execute succeeded
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select

from daily.db.models import IntegrationToken, PairingCode, User


@pytest.mark.e2e
async def test_full_user_onboarding_to_voice_connect(client, mock_resend, mock_oauth_exchange, db_factory):
    """Full new-user flow: magic link → pairing → Google OAuth → prefs → voice token → refresh."""
    ac, fake_redis, db_factory = client

    # -------------------------------------------------------------------------
    # Step 1: Send magic link
    # -------------------------------------------------------------------------
    resp = await ac.post(
        "/auth/pair/send-link",
        json={"email": "newuser@test.com"},
    )
    assert resp.status_code == 204, resp.text

    # Assert mock_resend was called once with the correct email
    assert len(mock_resend) == 1, f"Expected 1 send_magic_link call, got {len(mock_resend)}"
    sent_email, sent_code = mock_resend[0]
    assert sent_email == "newuser@test.com"
    assert len(sent_code) == 6 and sent_code.isdigit(), f"Invalid code: {sent_code!r}"

    # -------------------------------------------------------------------------
    # Step 2: Extract pairing code from DB (the code was stored before email send)
    # -------------------------------------------------------------------------
    async with db_factory() as session:
        result = await session.execute(
            select(PairingCode).where(PairingCode.email == "newuser@test.com")
        )
        pairing_row = result.scalar_one()
    code = pairing_row.code
    assert len(code) == 6 and code.isdigit()

    # -------------------------------------------------------------------------
    # Step 3: Complete pairing
    # -------------------------------------------------------------------------
    resp = await ac.post(
        "/auth/pair/complete",
        json={"code": code, "device_name": "iPhone Test"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body, f"Missing access_token: {body}"
    assert "refresh_token" in body, f"Missing refresh_token: {body}"
    assert "expires_in" in body, f"Missing expires_in: {body}"

    access_token = body["access_token"]
    refresh_token = body["refresh_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # -------------------------------------------------------------------------
    # Step 4: Connect Google integration — get the authorize_url
    # -------------------------------------------------------------------------
    resp = await ac.get("/integrations/google/connect", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    connect_body = resp.json()
    assert "auth_url" in connect_body, f"Missing auth_url: {connect_body}"
    assert connect_body["auth_url"], "auth_url must be non-empty"

    # Extract the state from Redis (stored by the connect endpoint)
    state_keys = await fake_redis.keys("oauth_state:*")
    assert len(state_keys) == 1, f"Expected 1 oauth_state key, got {state_keys}"
    state = state_keys[0].decode().split("oauth_state:")[-1]

    # -------------------------------------------------------------------------
    # Step 5: Simulate Google OAuth callback
    # The mock_oauth_exchange fixture already patches Flow so fetch_token succeeds.
    # -------------------------------------------------------------------------
    resp = await ac.get(
        f"/integrations/google/callback?code=fake-auth-code&state={state}",
        follow_redirects=False,
    )
    # Callback returns a 302 redirect to the app deep link
    assert resp.status_code == 302, resp.text

    # Verify IntegrationToken was created for Google
    async with db_factory() as session:
        result = await session.execute(
            select(IntegrationToken).where(
                IntegrationToken.provider == "google"
            )
        )
        token_row = result.scalar_one_or_none()
    assert token_row is not None, "IntegrationToken for google not created"

    # -------------------------------------------------------------------------
    # Step 6: Set briefing schedule
    # -------------------------------------------------------------------------
    resp = await ac.put(
        "/users/me/preferences",
        json={"briefing_time": "07:30", "timezone": "Australia/Brisbane"},
        headers=auth_headers,
    )
    assert resp.status_code == 204, resp.text

    # -------------------------------------------------------------------------
    # Step 7: Read integration status
    # -------------------------------------------------------------------------
    resp = await ac.get("/users/me/integrations", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    status_body = resp.json()
    assert status_body["google"] is True, f"google should be True: {status_body}"

    # -------------------------------------------------------------------------
    # Step 8: Issue LiveKit token
    # -------------------------------------------------------------------------
    resp = await ac.post("/livekit/token", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    livekit_body = resp.json()
    assert "token" in livekit_body, f"Missing token field: {livekit_body}"
    token_parts = livekit_body["token"].split(".")
    assert len(token_parts) == 3, f"LiveKit token is not JWT-shaped (3 parts): {livekit_body['token']!r}"

    # -------------------------------------------------------------------------
    # Step 9: Refresh access token
    # -------------------------------------------------------------------------
    resp = await ac.post(
        "/auth/token/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200, resp.text
    refresh_body = resp.json()
    assert "access_token" in refresh_body, f"Missing access_token in refresh: {refresh_body}"
    # New token is valid JWT-shaped (may match original if issued within same second — that is acceptable)
    new_token_parts = refresh_body["access_token"].split(".")
    assert len(new_token_parts) == 3, f"Refreshed access_token is not JWT-shaped: {refresh_body['access_token']!r}"


# ---------------------------------------------------------------------------
# Helpers for greeting + approval round-trip test
# ---------------------------------------------------------------------------


def _mock_openai_respond_response(text: str = "Good morning! Here is your briefing.") -> MagicMock:
    """Return a canned OpenAI chat completion response for respond_node / astream_session.

    respond_node expects response_format=json_object output matching OrchestratorIntent.
    astream_session (streaming path for respond-intent) also calls OpenAI but with plain text.
    We patch AsyncOpenAI directly so both paths return predictable output.
    """
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "action": "answer",
        "narrative": text,
        "target_id": None,
    })
    return mock_resp


def _mock_openai_draft_response(
    body: str = "Hi Alice, yes I can make it. Best, User",
) -> MagicMock:
    """Return a canned OpenAI response for draft_node.

    draft_node expects a JSON object with recipient/subject/body/etc. fields.
    """
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "recipient": "alice@example.com",
        "subject": "Re: Meeting tomorrow",
        "body": body,
        "thread_id": "thread-abc-001",
        "message_id": "msg-abc-001",
        "event_title": None,
        "start_dt": None,
        "end_dt": None,
        "attendees": [],
    })
    return mock_resp


@pytest.mark.e2e
async def test_worker_agent_greeting_and_approval_round_trip():
    """Smoke test: worker agent greeting + one approval-interrupt round-trip.

    Mock boundary:
    - LiveKit / livekit-agents / VoicePipelineAgent: NOT instantiated. The test
      exercises DailyLLMBridge directly (the seam between livekit-agents and the
      orchestrator graph), bypassing the LiveKit room and STT/TTS pipeline entirely.
    - LLM model (OpenAI): AsyncOpenAI.chat.completions.create is patched at both
      the nodes module and the session module to return deterministic canned responses.
      All graph control flow and interrupt/resume logic runs against the REAL graph.
    - Email adapters: empty list (no real email account needed for this test).
    - Action executor: patched via _build_executor_for_type so no DB/API call is made.

    The orchestrator graph is REAL: build_graph() with MemorySaver, real interrupt()
    in approval_node, real Command(resume=...) in resume_approval().

    Negative gate assertion: action executor is NOT called before resume_approval().
    """
    from daily.actions.base import ActionDraft, ActionResult, ActionType
    from daily.orchestrator.graph import build_graph
    from daily.orchestrator.session import create_session_config
    from daily.worker.llm_bridge import DailyLLMBridge

    # -------------------------------------------------------------------
    # Step 10: Simulate worker agent joining — build real graph + bridge
    # -------------------------------------------------------------------
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    config = await create_session_config(user_id=999)

    briefing_narrative = "You have 3 emails. Alice asks about tomorrow's meeting."
    initial_state = {
        "briefing_narrative": briefing_narrative,
        "active_user_id": 999,
        "preferences": {"tone": "conversational", "briefing_length": "standard"},
        "email_context": [
            {
                "message_id": "msg-abc-001",
                "thread_id": "thread-abc-001",
                "subject": "Meeting tomorrow",
                "sender": "alice@example.com",
                "recipient": "user@example.com",
                "timestamp": "2026-06-19T08:00:00",
            }
        ],
    }

    bridge = DailyLLMBridge(graph=graph, config=config, initial_state=initial_state)

    # Track executor invocations for the negative-gate assertion.
    executor_call_count = 0

    # Build a mock executor whose execute() increments the counter.
    mock_executor = MagicMock()
    mock_executor.validate = AsyncMock(return_value=None)

    async def _counted_execute(draft: ActionDraft) -> ActionResult:
        nonlocal executor_call_count
        executor_call_count += 1
        return ActionResult(success=True, external_id="smoke-msg-001")

    mock_executor.execute = AsyncMock(side_effect=_counted_execute)

    # -------------------------------------------------------------------
    # OpenAI mock setup.
    # astream_session (streaming respond path) calls _get_openai_client() which
    # returns the module-level _openai_client. It uses stream=True, so we need
    # an async-iterable stream mock for that path.
    # respond_node (graph non-streaming fallback) calls AsyncOpenAI(api_key=...).
    # We patch both entry points to use the same mock client.
    # -------------------------------------------------------------------

    # Build a fake streaming chunk sequence that astream_session will iterate.
    async def _fake_stream_response(*args, **kwargs):
        """Return an async iterable of fake chunks for stream=True calls."""
        stream = kwargs.get("stream", False)
        if stream:
            # astream_session iterates chunk.choices[0].delta.content
            for text in ["Good morning! ", "Here is your briefing."]:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = text
                yield chunk
        else:
            # respond_node / draft_node use non-streaming create()
            # Return the current canned response stored on the mock
            yield  # This branch is not expected to be called via __aiter__

    # Non-streaming mock: handle both respond and draft paths.
    # We switch the return value between turns by resetting the side_effect.
    mock_llm_client = AsyncMock()

    # The streaming path is an async generator; we need create() to return an object
    # that can be used as "async for chunk in stream:". We make it return an async
    # generator directly when stream=True, or a regular mock when stream=False.
    async def _smart_create(*args, **kwargs):
        if kwargs.get("stream", False):
            # Return async iterable for astream_session
            async def _gen():
                for text in ["Good morning! ", "Here is your briefing."]:
                    chunk = MagicMock()
                    chunk.choices = [MagicMock()]
                    chunk.choices[0].delta.content = text
                    yield chunk
            return _gen()
        else:
            # Return a plain mock for respond_node / draft_node
            return mock_llm_client._current_response

    mock_llm_client.chat = MagicMock()
    mock_llm_client.chat.completions = MagicMock()
    mock_llm_client.chat.completions.create = _smart_create
    mock_llm_client._current_response = _mock_openai_respond_response()

    import daily.orchestrator.session as _session_module

    with (
        patch("daily.orchestrator.nodes.AsyncOpenAI", return_value=mock_llm_client),
        patch.object(_session_module, "_openai_client", mock_llm_client),
        patch("daily.orchestrator.nodes.get_email_adapters", return_value=[]),
        patch("daily.orchestrator.session.get_email_adapters", return_value=[]),
        patch(
            "daily.orchestrator.nodes._build_executor_for_type",
            new=AsyncMock(return_value=mock_executor),
        ),
    ):
        # -------------------------------------------------------------------
        # Step 10b: Greeting — first bridge turn with a respond-intent message.
        # Use a plain conversational message that doesn't trigger draft keywords.
        # "Good morning, brief me" → respond_node via route_intent → astream_session
        # (streaming path) yields tokens or falls back to run_session via respond_node.
        #
        # The greeting demonstrates that the real orchestrator graph routes the
        # first user turn through respond_node and the LLM bridge delivers output.
        # -------------------------------------------------------------------
        greeting_tokens: list[str] = []
        async for token in bridge.stream_response("Good morning, brief me"):
            greeting_tokens.append(token)

        greeting = "".join(greeting_tokens)
        assert greeting, (
            "Worker agent must produce a non-empty greeting on first bridge turn; got empty string. "
            "This means respond_node or astream_session failed to yield any content."
        )
        # Greeting came from the mocked LLM — verify it has content from our canned response.
        assert "morning" in greeting.lower() or "briefing" in greeting.lower(), (
            f"Greeting does not match canned LLM response pattern; got: {greeting!r}"
        )

        # -------------------------------------------------------------------
        # NEGATIVE GATE: executor has NOT been called yet — no action executed
        # before the approval interrupt.
        # -------------------------------------------------------------------
        assert executor_call_count == 0, (
            f"APPROVAL GATE FAILED: executor was called {executor_call_count} time(s) "
            "before the approval interrupt. The gate must block execution until resume."
        )

        # -------------------------------------------------------------------
        # Step 11: Drive a draft-intent turn — triggers draft_node → approval_node
        # → interrupt() pauses the graph.
        # Switch the canned response to the draft format for draft_node.
        # -------------------------------------------------------------------
        mock_llm_client._current_response = _mock_openai_draft_response()

        draft_tokens: list[str] = []
        async for token in bridge.stream_response("reply to Alice's email saying yes I can make it"):
            draft_tokens.append(token)

        draft_response = "".join(draft_tokens)

        # After a draft-intent turn, the graph should be paused at approval_node.
        # DailyLLMBridge sets pending_approval=True when it detects the interrupt.
        assert bridge.pending_approval, (
            f"Graph must be paused at approval_node after draft-intent turn. "
            f"bridge.pending_approval is False. Draft response was: {draft_response!r}"
        )

        # -------------------------------------------------------------------
        # Step 12: Negative gate — executor must NOT have fired before resume.
        # The approval interrupt() must genuinely block execution.
        # -------------------------------------------------------------------
        assert executor_call_count == 0, (
            f"APPROVAL GATE FAILED: executor was called {executor_call_count} time(s) "
            "before Command(resume='confirm'). The interrupt must block the execute node."
        )

        # -------------------------------------------------------------------
        # Step 13: Resume with confirm — graph advances through execute_node.
        # resume_approval() calls graph.ainvoke(Command(resume="confirm"), config).
        # -------------------------------------------------------------------
        resume_tokens: list[str] = []
        async for token in bridge.resume_approval("confirm"):
            resume_tokens.append(token)

        resume_response = "".join(resume_tokens)

        # -------------------------------------------------------------------
        # Step 14: Assert action executed exactly once and result was returned.
        # -------------------------------------------------------------------
        assert executor_call_count == 1, (
            f"Executor must be called exactly once after confirm resume; "
            f"called {executor_call_count} time(s). Resume response: {resume_response!r}"
        )
        assert resume_response, (
            "Bridge must yield a non-empty response after resume with confirm; got empty string."
        )
        # The execute_node returns "Done. Sent (ID: ...)" on success.
        assert "done" in resume_response.lower() or "sent" in resume_response.lower(), (
            f"Resume response after confirm should indicate success; got: {resume_response!r}"
        )

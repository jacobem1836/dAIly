"""Tests for the briefing pipeline orchestrator (pipeline.py)."""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from daily.profile.models import UserPreferences

import pytest
from fakeredis import FakeAsyncRedis

from daily.briefing.models import (
    BriefingContext,
    BriefingOutput,
    CalendarContext,
    RankedEmail,
    SlackContext,
)
from daily.integrations.models import EmailMetadata, MessageMetadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    return FakeAsyncRedis()


@pytest.fixture
def openai_client():
    """Mock AsyncOpenAI client with controlled response for both redactor and narrator."""
    client = MagicMock()

    # Mock completions.create for both GPT-4.1-mini (redactor) and GPT-4.1 (narrator)
    async def mock_create(**kwargs):
        model = kwargs.get("model", "")
        if "mini" in model:
            # Redactor response
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Redacted summary of email content."
            return response
        else:
            # Narrator response
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = (
                '{"narrative": "Good morning. You have important emails and meetings today."}'
            )
            return response

    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = mock_create
    return client


@pytest.fixture
def email_adapter():
    """Mock email adapter returning one email."""
    adapter = AsyncMock()
    meta = EmailMetadata(
        message_id="msg-001",
        thread_id="thread-001",
        subject="Important meeting",
        sender="boss@example.com",
        recipient="me@example.com",
        timestamp=datetime(2026, 4, 7, 8, 0, 0, tzinfo=timezone.utc),
        is_unread=True,
        labels=["INBOX", "UNREAD"],
    )

    from daily.integrations.models import EmailPage
    page = EmailPage(emails=[meta], next_page_token=None)
    adapter.list_emails = AsyncMock(return_value=page)
    adapter.get_email_body = AsyncMock(return_value="Please join the meeting at 9am.")
    return adapter


@pytest.fixture
def calendar_adapter():
    """Mock calendar adapter returning no events."""
    adapter = AsyncMock()
    adapter.list_events = AsyncMock(return_value=[])
    return adapter


@pytest.fixture
def message_adapter():
    """Mock message adapter returning no messages."""
    adapter = AsyncMock()
    from daily.integrations.models import MessagePage
    page = MessagePage(messages=[], next_cursor=None)
    adapter.list_messages = AsyncMock(return_value=page)
    return adapter


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline(fake_redis, openai_client, email_adapter, calendar_adapter, message_adapter):
    """run_briefing_pipeline produces a BriefingOutput and caches it in Redis."""
    from daily.briefing.pipeline import run_briefing_pipeline

    output = await run_briefing_pipeline(
        user_id=1,
        email_adapters=[email_adapter],
        calendar_adapters=[calendar_adapter],
        message_adapters=[message_adapter],
        vip_senders=frozenset(),
        user_email="me@example.com",
        top_n=5,
        redis=fake_redis,
        openai_client=openai_client,
    )

    assert isinstance(output, BriefingOutput)
    assert output.narrative
    assert output.version == 1

    # Verify it is cached in Redis under the correct key
    today = output.generated_at.date()
    keys = await fake_redis.keys(f"briefing:1:{today.isoformat()}")
    assert len(keys) == 1, f"Expected 1 cache key, found {len(keys)}"


@pytest.mark.asyncio
async def test_get_or_generate_cache_hit(fake_redis, openai_client):
    """Pre-populated cache returns result without calling pipeline. Verified under 0.1s (BRIEF-01)."""
    from daily.briefing.cache import cache_briefing
    from daily.briefing.pipeline import get_or_generate_briefing

    # Pre-populate cache
    cached_output = BriefingOutput(
        narrative="Pre-cached briefing narrative.",
        generated_at=datetime.now(tz=timezone.utc),
        version=1,
    )
    await cache_briefing(fake_redis, user_id=1, output=cached_output)

    # Time the cache hit
    start = time.monotonic()
    result = await get_or_generate_briefing(
        user_id=1,
        redis=fake_redis,
        generate_kwargs={},  # Should not be used on cache hit
    )
    elapsed = time.monotonic() - start

    assert result.narrative == cached_output.narrative
    # BRIEF-01 latency requirement: serving from cache under 0.1 seconds
    assert elapsed < 0.1, f"Cache hit took {elapsed:.3f}s, expected < 0.1s"


@pytest.mark.asyncio
async def test_get_or_generate_cache_miss(fake_redis, openai_client, email_adapter, calendar_adapter, message_adapter):
    """Empty Redis triggers on-demand run_briefing_pipeline call."""
    from daily.briefing.pipeline import get_or_generate_briefing

    generate_kwargs = {
        "email_adapters": [email_adapter],
        "calendar_adapters": [calendar_adapter],
        "message_adapters": [message_adapter],
        "vip_senders": frozenset(),
        "user_email": "me@example.com",
        "top_n": 5,
        "openai_client": openai_client,
    }

    result = await get_or_generate_briefing(
        user_id=1,
        redis=fake_redis,
        generate_kwargs=generate_kwargs,
    )

    assert isinstance(result, BriefingOutput)
    assert result.narrative

    # Also verify it was cached after generation
    today = result.generated_at.date()
    keys = await fake_redis.keys(f"briefing:1:{today.isoformat()}")
    assert len(keys) == 1


@pytest.mark.asyncio
async def test_pipeline_partial_source_failure(fake_redis, openai_client, calendar_adapter):
    """Pipeline completes when one adapter raises an exception (briefing always delivers)."""
    from daily.briefing.pipeline import run_briefing_pipeline
    from daily.integrations.models import EmailPage, MessagePage

    # Email adapter that raises
    bad_email_adapter = AsyncMock()
    bad_email_adapter.list_emails = AsyncMock(side_effect=RuntimeError("Gmail API down"))

    # Message adapter that returns empty
    ok_message_adapter = AsyncMock()
    ok_message_adapter.list_messages = AsyncMock(
        return_value=MessagePage(messages=[], next_cursor=None)
    )

    # Pipeline should still complete
    output = await run_briefing_pipeline(
        user_id=1,
        email_adapters=[bad_email_adapter],
        calendar_adapters=[calendar_adapter],
        message_adapters=[ok_message_adapter],
        vip_senders=frozenset(),
        user_email="me@example.com",
        top_n=5,
        redis=fake_redis,
        openai_client=openai_client,
    )

    assert isinstance(output, BriefingOutput)
    assert output.narrative  # briefing always delivers


@pytest.mark.asyncio
async def test_raw_bodies_passed_to_redactor(fake_redis, openai_client):
    """redact_emails receives actual raw bodies from context.raw_bodies, not empty dicts (SEC-02)."""
    from daily.briefing.pipeline import run_briefing_pipeline

    # Build a BriefingContext with known raw_bodies
    email_meta = EmailMetadata(
        message_id="msg-sec-test",
        thread_id="thread-sec",
        subject="Security test email",
        sender="sender@example.com",
        recipient="me@example.com",
        timestamp=datetime(2026, 4, 7, 8, 0, 0, tzinfo=timezone.utc),
        is_unread=True,
        labels=["INBOX", "UNREAD"],
    )
    ranked_email = RankedEmail(metadata=email_meta, score=10.0)
    context_with_bodies = BriefingContext(
        user_id=1,
        generated_at=datetime(2026, 4, 7, 5, 0, 0, tzinfo=timezone.utc),
        emails=[ranked_email],
        calendar=CalendarContext(events=[], conflicts=[]),
        slack=SlackContext(messages=[]),
        raw_bodies={"msg-sec-test": "Sensitive email body content here."},
    )

    captured_raw_bodies = {}

    async def mock_redact_emails(emails, raw_bodies, client):
        captured_raw_bodies.update(raw_bodies)
        for e in emails:
            e.summary = "Redacted summary"
        return emails

    with patch("daily.briefing.pipeline.build_context", return_value=context_with_bodies), \
         patch("daily.briefing.pipeline.redact_emails", side_effect=mock_redact_emails), \
         patch("daily.briefing.pipeline.generate_narrative", return_value=BriefingOutput(
             narrative="Test narrative",
             generated_at=datetime(2026, 4, 7, 5, 0, 0, tzinfo=timezone.utc),
             version=1,
         )):

        await run_briefing_pipeline(
            user_id=1,
            email_adapters=[],
            calendar_adapters=[],
            message_adapters=[],
            vip_senders=frozenset(),
            user_email="me@example.com",
            top_n=5,
            redis=fake_redis,
            openai_client=openai_client,
        )

    # Verify that raw bodies were passed to redact_emails (not empty dict)
    assert "msg-sec-test" in captured_raw_bodies, (
        "redact_emails was not called with context.raw_bodies — SEC-02 contract violated"
    )
    assert captured_raw_bodies["msg-sec-test"] == "Sensitive email body content here."


# ---------------------------------------------------------------------------
# PERS-01: Preference wiring tests (Phase 6 gap closure)
# ---------------------------------------------------------------------------


def _make_capturing_client():
    """Return (client, captured_narrator_calls) — client records all create() calls."""
    calls = []

    async def mock_create(**kwargs):
        calls.append(kwargs)
        model = kwargs.get("model", "")
        if "mini" in model:
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = "Redacted summary."
            return response
        else:
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message.content = '{"narrative": "Good morning."}'
            return response

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = mock_create
    return client, calls


@pytest.mark.asyncio
async def test_pipeline_forwards_preferences_to_narrator(
    fake_redis, email_adapter, calendar_adapter, message_adapter
):
    """run_briefing_pipeline with preferences passes tone/length to narrator system prompt."""
    from daily.briefing.pipeline import run_briefing_pipeline

    client, calls = _make_capturing_client()
    prefs = UserPreferences(tone="formal", briefing_length="concise")

    await run_briefing_pipeline(
        user_id=1,
        email_adapters=[email_adapter],
        calendar_adapters=[calendar_adapter],
        message_adapters=[message_adapter],
        vip_senders=frozenset(),
        user_email="me@example.com",
        top_n=5,
        redis=fake_redis,
        openai_client=client,
        preferences=prefs,
    )

    # Find the narrator call (non-mini model)
    narrator_calls = [c for c in calls if "mini" not in c.get("model", "")]
    assert narrator_calls, "No narrator LLM call was made"
    system_msg = next(
        (m for m in narrator_calls[0].get("messages", []) if m["role"] == "system"),
        None,
    )
    assert system_msg is not None, "No system message in narrator call"
    assert "formal" in system_msg["content"], "Tone 'formal' not found in narrator system prompt"
    assert "concise" in system_msg["content"], "Length 'concise' not found in narrator system prompt"


@pytest.mark.asyncio
async def test_pipeline_no_preferences_backward_compat(
    fake_redis, email_adapter, calendar_adapter, message_adapter
):
    """run_briefing_pipeline with preferences=None still works; no preference preamble in prompt."""
    from daily.briefing.pipeline import run_briefing_pipeline

    client, calls = _make_capturing_client()

    output = await run_briefing_pipeline(
        user_id=1,
        email_adapters=[email_adapter],
        calendar_adapters=[calendar_adapter],
        message_adapters=[message_adapter],
        vip_senders=frozenset(),
        user_email="me@example.com",
        top_n=5,
        redis=fake_redis,
        openai_client=client,
        # preferences omitted — should default to None
    )

    assert isinstance(output, BriefingOutput)
    assert output.narrative

    # Verify no preference preamble in the narrator system prompt
    narrator_calls = [c for c in calls if "mini" not in c.get("model", "")]
    assert narrator_calls, "No narrator LLM call was made"
    system_msg = next(
        (m for m in narrator_calls[0].get("messages", []) if m["role"] == "system"),
        None,
    )
    assert system_msg is not None
    assert not system_msg["content"].startswith("User preferences:"), (
        "Preference preamble found in system prompt when preferences=None"
    )


@pytest.mark.asyncio
async def test_build_pipeline_kwargs_includes_preferences():
    """_build_pipeline_kwargs returns a dict with a 'preferences' key loaded via load_profile."""
    from daily.briefing.scheduler import _build_pipeline_kwargs

    # Mock session that returns empty DB results
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_async_session = MagicMock(return_value=mock_cm)

    expected_prefs = UserPreferences(tone="casual")

    mock_settings = MagicMock()
    mock_settings.redis_url = "redis://localhost"
    mock_settings.openai_api_key = "test-key"
    mock_settings.vault_key = None
    mock_settings.briefing_email_top_n = 5

    import sys
    fake_adapter_modules = {
        "daily.integrations.google.adapter": MagicMock(),
        "daily.integrations.microsoft.adapter": MagicMock(),
        "daily.integrations.slack.adapter": MagicMock(),
        "daily.vault.crypto": MagicMock(),
    }
    with patch("daily.briefing.scheduler.async_session", mock_async_session), \
         patch("daily.briefing.scheduler.load_profile", AsyncMock(return_value=expected_prefs)), \
         patch.dict(sys.modules, fake_adapter_modules):
        result = await _build_pipeline_kwargs(user_id=1, settings=mock_settings)

    assert "preferences" in result, "Expected 'preferences' key in _build_pipeline_kwargs result"
    assert result["preferences"].tone == "casual", (
        f"Expected tone='casual', got '{result['preferences'].tone}'"
    )

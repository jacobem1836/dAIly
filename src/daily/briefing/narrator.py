"""
Narrator: LLM narrative generation for the daily briefing.

Consumes pre-summarised, pre-redacted BriefingContext from the redactor and
produces a spoken-English BriefingOutput via GPT-4.1.

D-06: Single flowing narrative — no bullet points, no headers.
D-07: Three-paragraph structure: emails -> calendar -> Slack.
D-08: If a section is empty, include a "Nothing notable" sentence.
D-11: Narrator LLM has NO tool calls, NO credentials -- structured intent only.
D-05: Preferences injected as system instruction preamble.
SEC-05: response_format=json_object constrains output; backend validates key.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from daily.briefing.models import BriefingContext, BriefingOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt (D-06 / D-07 / D-08)
# ---------------------------------------------------------------------------

NARRATOR_SYSTEM_PROMPT = (
    "You are a personal morning briefing assistant. Generate a briefing as a "
    "single flowing spoken-English narrative — continuous paragraphs written to "
    "be read aloud over text-to-speech. Never use bullet points, numbered lists, "
    "headers, or markdown formatting.\n\n"
    "Structure: three paragraphs in order:\n"
    "1. Critical emails (prioritised by importance score)\n"
    "2. Calendar events (upcoming schedule, note any conflicts)\n"
    "3. Slack activity (mentions, DMs from priority channels)\n\n"
    "If a section has no data, include one sentence: "
    "'Nothing notable in [source] today.'\n\n"
    "Target length: 225 to 300 words (90 to 120 seconds when read aloud). "
    "Limit total output to 300 words. Stop at 300 words even if all items are "
    "not covered. Do not exceed 300 words.\n\n"
    'Output MUST be valid JSON with exactly one key: {"narrative": "..."}'
)

# ---------------------------------------------------------------------------
# Preference preamble (D-05)
# ---------------------------------------------------------------------------

PREFERENCE_PREAMBLE = (
    "User preferences:\n"
    "- Tone: {tone}\n"
    "- Briefing length: {length}\n"
    "- Section order: {order}\n\n"
    "Adjust your narrative style accordingly. "
    "For 'concise' length, target 100-150 words. "
    "For 'standard' length, target 225-300 words. "
    "For 'detailed' length, target 350-450 words.\n\n"
)

# ---------------------------------------------------------------------------
# Fallback narrative (used when LLM fails twice)
# ---------------------------------------------------------------------------

FALLBACK_NARRATIVE = (
    "Your briefing could not be generated. Please check your data sources."
)


# ---------------------------------------------------------------------------
# Prompt builder (D-05)
# ---------------------------------------------------------------------------


def build_narrator_system_prompt(preferences: UserPreferences | None = None) -> str:
    """Build narrator system prompt with optional user preference preamble.

    Per D-05: Preferences injected as system instruction preamble.
    Returns the base NARRATOR_SYSTEM_PROMPT if no preferences provided.

    Args:
        preferences: Optional UserPreferences -- if None, returns base prompt unchanged.

    Returns:
        System prompt string with or without preference preamble prepended.
    """
    if preferences is None:
        return NARRATOR_SYSTEM_PROMPT
    preamble = PREFERENCE_PREAMBLE.format(
        tone=preferences.tone,
        length=preferences.briefing_length,
        order=", ".join(preferences.category_order),
    )
    return preamble + NARRATOR_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


async def generate_narrative(
    context: BriefingContext,
    client: AsyncOpenAI,
    preferences: UserPreferences | None = None,
) -> BriefingOutput:
    """Generate a spoken-English briefing narrative from pre-redacted context.

    Calls GPT-4.1 in JSON mode to produce a structured {"narrative": "..."}
    response. Validates the "narrative" key exists. On parse failure or wrong
    key, retries once. On second failure, returns FALLBACK_NARRATIVE.

    SEC-05: No tools= or function_call= parameters -- LLM is intent-only.
    D-11: LLM receives only pre-summarised metadata, never raw bodies or credentials.
    D-05: If preferences provided, prepends preference preamble to system prompt.

    Args:
        context: Pre-redacted briefing context.
        client: AsyncOpenAI client instance.
        preferences: Optional user preferences. If None, uses base system prompt
                     (backward compatible).
    """
    user_prompt = context.to_prompt_string()
    system_prompt = build_narrator_system_prompt(preferences)

    # Adjust max_tokens based on preferences (D-05)
    max_tokens = 650  # default (standard length)
    if preferences and preferences.briefing_length == "concise":
        max_tokens = 350
    elif preferences and preferences.briefing_length == "detailed":
        max_tokens = 900

    async def _call_llm() -> str:
        """Make one LLM call and return the raw response content."""
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
            # NOTE: No tools=, no function_call= -- SEC-05 / D-11
        )
        return response.choices[0].message.content

    def _extract_narrative(raw: str) -> str:
        """Parse JSON and extract 'narrative' key. Raises on failure."""
        parsed = json.loads(raw)
        if "narrative" not in parsed:
            raise ValueError(
                f"LLM returned JSON without 'narrative' key: {list(parsed.keys())}"
            )
        return parsed["narrative"]

    # First attempt
    try:
        raw = await _call_llm()
        narrative = _extract_narrative(raw)
    except (json.JSONDecodeError, ValueError) as first_error:
        logger.warning("Narrator first attempt failed: %s — retrying", first_error)
        # Retry once
        try:
            raw = await _call_llm()
            narrative = _extract_narrative(raw)
        except (json.JSONDecodeError, ValueError) as second_error:
            logger.error("Narrator retry also failed: %s — using fallback", second_error)
            narrative = FALLBACK_NARRATIVE

    return BriefingOutput(
        narrative=narrative,
        generated_at=context.generated_at,
        version=1,
    )

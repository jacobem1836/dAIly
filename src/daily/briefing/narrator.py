"""
Narrator: LLM narrative generation for the daily briefing.

Consumes pre-summarised, pre-redacted BriefingContext from the redactor and
produces a spoken-English BriefingOutput via GPT-4.1.

D-06: Single flowing narrative — no bullet points, no headers.
D-07: Three-paragraph structure: emails → calendar → Slack.
D-08: If a section is empty, include a "Nothing notable" sentence.
D-11: Narrator LLM has NO tool calls, NO credentials — structured intent only.
SEC-05: response_format=json_object constrains output; backend validates key.
"""

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
# Fallback narrative (used when LLM fails twice)
# ---------------------------------------------------------------------------

FALLBACK_NARRATIVE = (
    "Your briefing could not be generated. Please check your data sources."
)


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


async def generate_narrative(
    context: BriefingContext, client: AsyncOpenAI
) -> BriefingOutput:
    """Generate a spoken-English briefing narrative from pre-redacted context.

    Calls GPT-4.1 in JSON mode to produce a structured {"narrative": "..."}
    response. Validates the "narrative" key exists. On parse failure or wrong
    key, retries once. On second failure, returns FALLBACK_NARRATIVE.

    SEC-05: No tools= or function_call= parameters — LLM is intent-only.
    D-11: LLM receives only pre-summarised metadata, never raw bodies or credentials.
    """
    user_prompt = context.to_prompt_string()

    async def _call_llm() -> str:
        """Make one LLM call and return the raw response content."""
        response = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": NARRATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=650,
            # NOTE: No tools=, no function_call= — SEC-05 / D-11
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

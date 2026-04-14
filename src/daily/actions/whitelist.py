"""Contact whitelist validation for action recipients.

Enforces ACT-06 / T-04-04: Unknown recipients must be rejected before any
external API call is made. The caller provides the known_addresses set,
which is populated from email history via adapters.

This is a pure function — no I/O, no side effects.
"""


def check_recipient_whitelist(recipient: str, known_addresses: set[str]) -> None:
    """Validate that recipient is in the known contacts set.

    Case-insensitive comparison — "Alice@Example.COM" matches "alice@example.com".

    Args:
        recipient: Email address or Slack user ID to validate.
        known_addresses: Set of known contact addresses from email history.

    Raises:
        ValueError: If recipient is not found in known_addresses.
                    Message is user-displayable (safe for CLI output).
    """
    lowered_known = {a.lower() for a in known_addresses}
    if recipient.lower() not in lowered_known:
        raise ValueError(
            f"Recipient '{recipient}' is not in known contacts. "
            "Add them to your contacts or cancel."
        )

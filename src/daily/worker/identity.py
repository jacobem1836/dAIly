"""User-id extraction from LiveKit room names (session-{user_id}-{ts})."""
import re

_ROOM_RE = re.compile(r"^session-(\d+)-\d+$")


def parse_user_id_from_room(room_name: str) -> int | None:
    """Return user_id from a `session-{user_id}-{ts}` room name, or None."""
    if not room_name:
        return None
    m = _ROOM_RE.match(room_name)
    return int(m.group(1)) if m else None

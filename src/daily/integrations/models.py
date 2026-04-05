"""
Pydantic output models for integration adapters.

Privacy constraint (SEC-04/D-06): No body, raw_body, content, text, or
message_body fields. Adapters return metadata only — raw content is never
stored and never passed to the LLM layer.
"""

from datetime import datetime

from pydantic import BaseModel


class EmailMetadata(BaseModel):
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    timestamp: datetime
    is_unread: bool
    labels: list[str]
    # No body field — SEC-04/D-06


class EmailPage(BaseModel):
    emails: list[EmailMetadata]
    next_page_token: str | None


class CalendarEvent(BaseModel):
    event_id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str]
    location: str | None
    is_all_day: bool


class MessageMetadata(BaseModel):
    message_id: str
    channel_id: str
    sender_id: str
    timestamp: datetime
    is_mention: bool
    is_dm: bool
    # No text/body field — SEC-04/D-06


class MessagePage(BaseModel):
    messages: list[MessageMetadata]
    next_cursor: str | None

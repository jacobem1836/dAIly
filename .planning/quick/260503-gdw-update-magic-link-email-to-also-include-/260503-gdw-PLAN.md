---
phase: quick
task_id: 260503-gdw
description: Update magic link email to also include OTP code as plain text
type: execute
autonomous: true
files_modified:
  - src/daily/email/resend_client.py
  - tests/test_resend_client.py
---

<objective>
Add the OTP code (e.g., "123456") as a plain-text fallback in the magic link email body, so users who receive the email on a different device can enter the code manually instead of clicking the link.

Purpose: Improve accessibility for users with split devices (e.g., email on desktop, app on mobile)
Output: Updated email HTML containing both clickable magic link + plain-text code fallback
</objective>

<context>
Current email body:
```html
<p>Tap to sign in to dAIly: <a href="{magic_url}">Open dAIly</a></p>
<p>This link expires in 5 minutes.</p>
```

Required addition:
```html
<p>Or enter code manually: 123456</p>
```

Files to modify:
- `src/daily/email/resend_client.py` — Update `send_magic_link()` to add code text to HTML
- `tests/test_resend_client.py` — Add test verifying code appears in email body
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update magic link email to include OTP code as plain text</name>
  <files>src/daily/email/resend_client.py</files>
  <action>
Modify the `html_body` in `send_magic_link()` to add a third paragraph containing the plain-text OTP code.

Current (lines 23–27):
```python
html_body = (
    f'<p>Tap to sign in to dAIly: '
    f'<a href="{magic_url}">Open dAIly</a></p>'
    f'<p>This link expires in 5 minutes.</p>'
)
```

Update to:
```python
html_body = (
    f'<p>Tap to sign in to dAIly: '
    f'<a href="{magic_url}">Open dAIly</a></p>'
    f'<p>This link expires in 5 minutes.</p>'
    f'<p>Or enter code manually: {code}</p>'
)
```

This provides a fallback for users who cannot click the link.
  </action>
  <verify>
    <automated>pytest tests/test_resend_client.py::test_send_magic_link_body_contains_pair_url -xvs</automated>
  </verify>
  <done>
    - HTML body includes the code as plain text
    - Existing test still passes (magic link URL present)
    - Email still sends to Resend API
  </done>
</task>

<task type="auto">
  <name>Task 2: Add test verifying OTP code appears in email body</name>
  <files>tests/test_resend_client.py</files>
  <action>
Add a new test after `test_send_magic_link_body_contains_pair_url()` that verifies the plain-text code appears in the email body.

New test (insert after line 98):
```python
@pytest.mark.asyncio
async def test_send_magic_link_body_contains_code_fallback(monkeypatch):
    """Email HTML body contains the plain-text OTP code for manual entry."""
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, json):
            captured["json"] = json
            return FakeResponse()

    import daily.email.resend_client as rc
    monkeypatch.setattr(rc.httpx, "AsyncClient", lambda: FakeAsyncClient())

    settings = _make_settings()
    await rc.send_magic_link("user@example.com", "654321", settings=settings)

    html = captured["json"]["html"]
    assert "Or enter code manually: 654321" in html
```

This confirms the code fallback is rendered in the email.
  </action>
  <verify>
    <automated>pytest tests/test_resend_client.py::test_send_magic_link_body_contains_code_fallback -xvs</automated>
  </verify>
  <done>
    - New test created and passing
    - Test verifies both code value and message text are present
    - All four tests in the file pass
  </done>
</task>

</tasks>

<verification>
After both tasks complete:
```bash
pytest tests/test_resend_client.py -v
```

Expected result: All 5 tests pass (existing 4 + new 1):
- test_send_magic_link_posts_to_resend_with_auth ✓
- test_send_magic_link_body_contains_pair_url ✓
- test_send_magic_link_raises_on_non_200 ✓
- test_settings_exposes_resend_and_apple_fields ✓
- test_send_magic_link_body_contains_code_fallback ✓
</verification>

<success_criteria>
- Email HTML body now includes both magic link AND plain-text OTP code
- All existing tests still pass
- New test verifies code appears in email body
- No breaking changes to function signature or existing behavior
</success_criteria>

"""Resend email client for dAIly magic-link delivery (Phase 19, D-02)."""
import httpx

from daily.config import Settings


class ResendError(Exception):
    """Raised when the Resend API returns a non-200 response."""


async def send_magic_link(email: str, code: str, *, settings: Settings) -> None:
    """Send a magic-link email via the Resend HTTP API.

    Args:
        email: Recipient email address.
        code: The 6-digit pairing code embedded in the magic link.
        settings: Application settings (provides API key, from address, base URL).

    Raises:
        ResendError: If Resend returns a non-200 status code.
    """
    magic_url = f"{settings.magic_link_base_url}/pair?code={code}"
    html_body = (
        f'<p>Tap to sign in to dAIly: '
        f'<a href="{magic_url}">Open dAIly</a></p>'
        f'<p>This link expires in 5 minutes.</p>'
        f'<p>Or enter code manually: {code}</p>'
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": [email],
                "subject": "Sign in to dAIly",
                "html": html_body,
            },
        )

    if response.status_code != 200:
        raise ResendError(response.text)

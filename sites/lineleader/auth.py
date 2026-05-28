"""
sites/lineleader/auth.py
========================
LineLeader / ChildCareCRM authentication.

Strategy (ADR-003 — hybrid):
  - Playwright handles login ONLY (OAuth2 PKCE with server-generated CSRF tokens
    and cryptographic code challenges — cannot be replicated with raw requests)
  - We intercept the POST /api/v3/sso/login response to extract the Bearer JWT
  - Token is cached to browser_state/lineleader_token.json with expiry
  - On each run: load from cache if valid, re-login only when expired
  - 5-minute buffer before expiry prevents mid-session token death

Usage:
    from sites.lineleader.auth import get_bearer_token
    bearer_token = await get_bearer_token()
    # Returns e.g. "Bearer eyJ0eXAiOiJKV1Qi..."
"""

import json
import os
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional

from playwright.async_api import async_playwright, Page, Response

from config.settings import settings
from core.logger import get_logger

logger = get_logger(__name__)

# How many minutes before expiry to treat the token as stale
_TOKEN_BUFFER_MINUTES = 5


async def get_bearer_token() -> str:
    """
    Return a valid Bearer token string for the ChildCareCRM API.

    Loads from cache if still valid; otherwise launches Playwright to
    log in and capture a fresh token.

    Returns:
        Bearer token string, e.g. "Bearer eyJ0eXAiOiJKV1Qi..."

    Raises:
        EnvironmentError: if credentials are missing from .env
        RuntimeError: if login fails
    """
    settings.validate()

    cached = _load_cached_token()
    if cached:
        logger.info("Cached token is valid — skipping login")
        return cached

    logger.info("Starting fresh LineLeader login to obtain Bearer token")
    token = await _login_and_capture_token()
    return token


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cached_token() -> Optional[str]:
    """
    Load token from cache file if it exists and is still valid
    (with TOKEN_BUFFER_MINUTES buffer before expiry).
    """
    path = settings.LINELEADER_TOKEN_FILE
    if not os.path.exists(path):
        logger.debug("No cached token file found")
        return None

    try:
        with open(path, "r") as f:
            data = json.load(f)

        token_str: str = data["token"]
        expires_at = datetime.fromisoformat(data["expires_at"])
        buffer = timedelta(minutes=_TOKEN_BUFFER_MINUTES)

        if datetime.now(timezone.utc) < (expires_at - buffer):
            return token_str

        logger.info("Cached token has expired — will re-login")
        return None

    except Exception as e:
        logger.warning("Could not read cached token: %s", e)
        return None


def _save_token(token_str: str, expires_at: datetime) -> None:
    """Save token and expiry to cache file."""
    os.makedirs(os.path.dirname(settings.LINELEADER_TOKEN_FILE), exist_ok=True)
    data = {
        "token": token_str,
        "expires_at": expires_at.isoformat(),
    }
    with open(settings.LINELEADER_TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)
    logger.debug("Token saved to %s", settings.LINELEADER_TOKEN_FILE)


def _parse_jwt_expiry(token_str: str) -> datetime:
    """
    Parse the exp claim from a JWT to get the expiry datetime.
    token_str should be the raw JWT (without "Bearer " prefix).
    Falls back to 1 hour from now if parsing fails.
    """
    try:
        # JWT structure: header.payload.signature (base64url encoded)
        parts = token_str.split(".")
        if len(parts) != 3:
            raise ValueError("Not a valid JWT")

        # Add padding if needed
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp: int = payload["exp"]
        return datetime.fromtimestamp(exp, tz=timezone.utc)

    except Exception as e:
        logger.warning("Could not parse JWT expiry: %s — defaulting to 1 hour", e)
        return datetime.now(timezone.utc) + timedelta(hours=1)


# ── Playwright login ──────────────────────────────────────────────────────────

async def _login_and_capture_token() -> str:
    """
    Launch a headless browser, log in to LineLeader, and capture
    the Bearer token from the /api/v3/sso/login response.
    """
    captured: dict = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.BROWSER_HEADLESS)
        context = await browser.new_context()
        page = await context.new_page()

        async def _on_response(response: Response) -> None:
            if "api/v3/sso/login" in response.url and not captured:
                try:
                    body = await response.json()
                    raw_token: str = body.get("token") or body.get("access_token", "")
                    if raw_token:
                        bearer = f"Bearer {raw_token}"
                        expires_at = _parse_jwt_expiry(raw_token)
                        captured["token"] = bearer
                        captured["expires_at"] = expires_at
                        logger.debug(
                            "Intercepted sso/login response from: %s", response.url
                        )
                        logger.info(
                            "Bearer token captured — expires at %s",
                            expires_at.astimezone().strftime("%H:%M:%S"),
                        )
                except Exception as e:
                    logger.warning("Could not parse sso/login response: %s", e)

        page.on("response", _on_response)

        # Navigate to login page
        logger.info("Navigating to LineLeader login page")
        await page.goto(settings.LINELEADER_LOGIN_URL, timeout=settings.BROWSER_TIMEOUT_MS)

        # Wait for the login form to appear (JS-rendered — may take a moment after page load)
        await page.wait_for_selector("#username", timeout=settings.BROWSER_TIMEOUT_MS)

        # Fill credentials
        logger.debug("Filling in credentials")
        await page.fill("#username", settings.LINELEADER_USERNAME)
        await page.fill("#password", settings.LINELEADER_PASSWORD)

        # Submit
        logger.debug("Submitting login form")
        await page.click("button[type='submit']")

        # Wait for redirect to ChildCareCRM dashboard
        await page.wait_for_url("**/my.childcarecrm.com/**", timeout=settings.BROWSER_TIMEOUT_MS)
        logger.info("Login successful — landed on: %s", page.url)

        # After landing on the app, it calls sso/login to exchange the OAuth code
        # for a Bearer JWT. Wait for network to go idle so that call completes
        # before we close the browser.
        if not captured.get("token"):
            await page.wait_for_load_state("networkidle", timeout=settings.BROWSER_TIMEOUT_MS)

        await browser.close()

    if not captured.get("token"):
        raise RuntimeError(
            "Login appeared to succeed but Bearer token was not captured. "
            "The sso/login API response may have changed."
        )

    _save_token(captured["token"], captured["expires_at"])
    return captured["token"]

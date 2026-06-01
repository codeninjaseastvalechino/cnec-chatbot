"""
sites/mystudio/auth.py
======================
MyStudio authentication: Playwright login + 2FA (via Gmail IMAP) + token caching.

Pattern mirrors LineLeader (sites/lineleader/auth.py) but adds 2FA support via Gmail IMAP.
"""

import json
import base64
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from config.settings import settings
from core.logger import get_logger
from core.gmail_imap import get_2fa_code_from_gmail

logger = get_logger(__name__)

_TOKEN_BUFFER_MINUTES = 5


async def get_bearer_token() -> str:
    """
    Fetch MyStudio bearer token, using cache if available.

    Flow:
    1. Check cache (browser_state/mystudio_token.json)
    2. If valid (not expired + 5-min buffer), return cached token
    3. If not valid or missing:
       a. Call login_with_2fa()
       b. User enters 2FA code via Gmail IMAP extraction
       c. Cache token with expiry
       d. Return token

    Returns:
        Bearer token string (e.g., "Bearer eyJ0eXAi...")

    Raises:
        Exception: If login fails or 2FA timeout.
    """
    # Check cache
    if Path(settings.MYSTUDIO_TOKEN_FILE).exists():
        try:
            with open(settings.MYSTUDIO_TOKEN_FILE, "r") as f:
                cached = json.load(f)
                if not _is_token_stale(cached):
                    logger.info(
                        "Using cached MyStudio token",
                        extra={"module": "sites.mystudio.auth"},
                    )
                    return cached["token"]
                else:
                    logger.info(
                        "Cached MyStudio token has expired",
                        extra={"module": "sites.mystudio.auth"},
                    )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(
                "Failed to load cached token",
                extra={"module": "sites.mystudio.auth", "error": str(e)},
            )

    # Token missing or expired — login
    logger.info(
        "Logging in to MyStudio",
        extra={"module": "sites.mystudio.auth"},
    )
    token = await login_with_2fa()
    return token


async def login_with_2fa() -> str:
    """
    Login to MyStudio with 2FA via Gmail IMAP code extraction.

    Steps:
    1. Launch Playwright browser (headless)
    2. Navigate to MyStudio login
    3. Fill username + password
    4. Submit login form
    5. Wait for 2FA prompt
    6. Extract 2FA code from Gmail inbox
    7. Fill 2FA code field
    8. Submit 2FA form
    9. Wait for redirect to dashboard
    10. Intercept API response to extract Bearer token
    11. Cache token with expiry
    12. Return token

    Returns:
        Bearer token string

    Raises:
        Exception: If login fails, 2FA fails, or token not found.
    """
    logger.info(
        "Starting MyStudio login with 2FA",
        extra={"module": "sites.mystudio.auth"},
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.BROWSER_HEADLESS)
        context = await browser.new_context()
        page = await context.new_page()

        token = None
        token_event = asyncio.Event()

        async def on_response(response):
            nonlocal token
            # Listen for API responses that might contain the token
            # TODO: Confirm actual endpoint via Chrome DevTools live site inspection
            # Placeholder: listen for any response from /api/
            if "api" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    if "token" in data or "access_token" in data:
                        token = data.get("token") or data.get("access_token")
                        if token and not token.startswith("Bearer "):
                            token = f"Bearer {token}"
                        token_event.set()
                        logger.debug(
                            "Token intercepted from API response",
                            extra={"module": "sites.mystudio.auth"},
                        )
                except:
                    pass

        page.on("response", on_response)

        try:
            # Navigate to login
            await page.goto(settings.MYSTUDIO_LOGIN_URL, timeout=settings.BROWSER_TIMEOUT_MS)
            logger.debug(
                "Navigated to MyStudio login",
                extra={"module": "sites.mystudio.auth"},
            )

            # Wait for username field and fill credentials
            await page.wait_for_selector("#username", timeout=settings.BROWSER_TIMEOUT_MS)
            await page.fill("#username", settings.MYSTUDIO_USERNAME)
            await page.fill("#password", settings.MYSTUDIO_PASSWORD)
            logger.debug(
                "Credentials filled",
                extra={"module": "sites.mystudio.auth"},
            )

            # Submit login form
            await page.click("button[type='submit']")
            logger.debug(
                "Login form submitted",
                extra={"module": "sites.mystudio.auth"},
            )

            # Wait for 2FA prompt (this is a placeholder selector — needs live site inspection)
            await page.wait_for_selector(
                "#twofa-code-input, [name='2fa'], [placeholder*='code'], [placeholder*='Code']",
                timeout=settings.BROWSER_TIMEOUT_MS,
            )
            logger.info(
                "2FA prompt appeared",
                extra={"module": "sites.mystudio.auth"},
            )

            # Extract 2FA code from Gmail
            logger.info(
                "Extracting 2FA code from Gmail",
                extra={"module": "sites.mystudio.auth"},
            )
            code = get_2fa_code_from_gmail(
                gmail_address=settings.GMAIL_ADDRESS,
                gmail_app_password=settings.GMAIL_APP_PASSWORD,
                timeout_seconds=settings.GMAIL_2FA_TIMEOUT_SECONDS,
                poll_interval_seconds=settings.GMAIL_2FA_POLL_INTERVAL_SECONDS,
            )

            if not code:
                raise Exception("2FA code extraction timeout — no code found in Gmail")

            logger.info(
                "2FA code received",
                extra={"module": "sites.mystudio.auth", "code": code},
            )

            # Fill 2FA code (placeholder selectors — needs live site inspection)
            try:
                await page.fill("#twofa-code-input, [name='2fa']", code)
            except Exception as e:
                logger.warning(
                    "Could not auto-fill 2FA code, trying alternative approach",
                    extra={"module": "sites.mystudio.auth", "error": str(e)},
                )
                # If auto-fill fails, try clicking any visible input and typing
                inputs = await page.query_selector_all("input")
                if inputs:
                    await inputs[-1].fill(code)

            # Submit 2FA form
            await page.click("button[type='submit']")
            logger.debug(
                "2FA form submitted",
                extra={"module": "sites.mystudio.auth"},
            )

            # Wait for token or redirect
            try:
                await asyncio.wait_for(token_event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "Token not intercepted from API, checking cookie/storage",
                    extra={"module": "sites.mystudio.auth"},
                )
                # Fallback: try to get token from localStorage or cookies
                # (this is a placeholder — real implementation needs site inspection)

            # Wait for redirect to dashboard
            await page.wait_for_url(lambda url: "dashboard" in url or "schedule" in url, timeout=30000)
            logger.info(
                "Login successful, redirected to dashboard",
                extra={"module": "sites.mystudio.auth"},
            )

            if not token:
                raise Exception("Bearer token not found in API responses")

            # Cache token with expiry
            _cache_token(token)

            return token

        finally:
            await context.close()
            await browser.close()
            logger.debug(
                "Browser closed",
                extra={"module": "sites.mystudio.auth"},
            )


def _parse_jwt_expiry(token: str) -> Optional[datetime]:
    """
    Decode JWT exp claim and return expiry datetime.

    JWT format: header.payload.signature
    Payload is base64url-encoded JSON.

    Args:
        token: Bearer token (with or without "Bearer " prefix)

    Returns:
        Expiry datetime (UTC) or None if parsing fails
    """
    try:
        # Remove "Bearer " prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        # Split and extract payload
        parts = token.split(".")
        if len(parts) < 2:
            return None

        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        # Decode
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded)

        # Extract exp claim (unix timestamp)
        if "exp" not in data:
            logger.warning(
                "No exp claim in JWT",
                extra={"module": "sites.mystudio.auth"},
            )
            return None

        exp_timestamp = data["exp"]
        return datetime.utcfromtimestamp(exp_timestamp)

    except Exception as e:
        logger.warning(
            "Failed to parse JWT expiry",
            extra={"module": "sites.mystudio.auth", "error": str(e)},
        )
        return None


def _is_token_stale(cached_token: Dict[str, Any]) -> bool:
    """
    Check if cached token is stale (within 5-minute buffer of expiry).

    Args:
        cached_token: Dict with "token" and "expires_at" keys

    Returns:
        True if token is stale or expired, False if still valid
    """
    try:
        expires_at_str = cached_token.get("expires_at")
        if not expires_at_str:
            return True

        # Parse ISO datetime
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        now = datetime.utcnow()
        buffer = timedelta(minutes=_TOKEN_BUFFER_MINUTES)

        is_stale = now >= (expires_at - buffer)
        logger.debug(
            "Token staleness check",
            extra={
                "module": "sites.mystudio.auth",
                "expires_at": expires_at_str,
                "is_stale": is_stale,
            },
        )
        return is_stale

    except Exception as e:
        logger.warning(
            "Failed to check token staleness",
            extra={"module": "sites.mystudio.auth", "error": str(e)},
        )
        return True


def _cache_token(token: str) -> None:
    """
    Cache token to disk with expiry datetime.

    Args:
        token: Bearer token
    """
    # Parse expiry from JWT
    expiry = _parse_jwt_expiry(token)
    if not expiry:
        # Fallback to 1 hour if parsing fails
        expiry = datetime.utcnow() + timedelta(hours=1)
        logger.warning(
            "Could not parse JWT expiry, using 1-hour fallback",
            extra={"module": "sites.mystudio.auth"},
        )

    # Ensure token dir exists
    token_path = Path(settings.MYSTUDIO_TOKEN_FILE)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    # Cache
    cache_data = {
        "token": token,
        "expires_at": expiry.isoformat(),
        "cached_at": datetime.utcnow().isoformat(),
    }

    with open(token_path, "w") as f:
        json.dump(cache_data, f, indent=2)

    logger.info(
        "Token cached",
        extra={
            "module": "sites.mystudio.auth",
            "expires_at": cache_data["expires_at"],
        },
    )

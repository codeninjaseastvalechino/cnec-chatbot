"""
sites/lineleader/auth.py
========================
LineLeader / ChildCareCRM authentication — Playwright-free.

Strategy (replaces ADR-003 hybrid):
  Pure requests OAuth2 PKCE flow:
    1. GET /authorize  → PHPSESSID cookie
    2. GET /login      → server-rendered CSRF token
    3. POST /login     → credentials accepted, redirect chain begins
    4. Follow redirects to callback URL on my.childcarecrm.com → auth code
    5. POST /api/v3/sso/login with {code, code_verifier} → Bearer JWT

  Token is cached to browser_state/lineleader_token.json with expiry.
  On each run: load from cache if valid, re-login only when expired.
  5-minute buffer before expiry prevents mid-session token death.

Usage:
    from sites.lineleader.auth import get_bearer_token
    bearer_token = await get_bearer_token()
    # Returns e.g. "Bearer eyJ0eXAiOiJKV1Qi..."
"""

import hashlib
import json
import os
import re
import base64
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from config.settings import settings
from core.logger import get_logger

logger = get_logger(__name__)

_TOKEN_BUFFER_MINUTES = 5

_AUTHORIZE_URL = "https://login.lineleader.com/authorize"
_LOGIN_URL = "https://login.lineleader.com/login"
_SSO_LOGIN_URL = "https://live.childcarecrm.com/api/v3/sso/login"
_REDIRECT_URI = "https://my.childcarecrm.com/#/code"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:151.0) "
        "Gecko/20100101 Firefox/151.0"
    ),
}


async def get_bearer_token() -> str:
    """
    Return a valid Bearer token string for the ChildCareCRM API.

    Loads from cache if still valid; otherwise runs the OAuth2 PKCE login flow
    using pure requests (no browser required).

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

    logger.info("Starting fresh LineLeader login (Playwright-free PKCE flow)")
    return _login_and_capture_token()


# ── OAuth2 PKCE login ─────────────────────────────────────────────────────────

def _login_and_capture_token() -> str:
    """
    Run the full OAuth2 PKCE flow using requests, return a cached Bearer token.
    """
    session = requests.Session()
    session.headers.update(_HEADERS)

    # 1. Generate PKCE params
    raw_verifier = os.urandom(32)
    code_verifier = base64.urlsafe_b64encode(raw_verifier).rstrip(b"=").decode()
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    state = base64.urlsafe_b64encode(os.urandom(24)).rstrip(b"=").decode()

    # 2. GET authorize → sets PHPSESSID, redirects to login page
    auth_params = {
        "client_id": "enroll",
        "response_type": "code",
        "scope": "openid",
        "redirect_uri": _REDIRECT_URI,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    session.get(_AUTHORIZE_URL + "?" + urllib.parse.urlencode(auth_params))
    logger.debug("PHPSESSID obtained: %s", session.cookies.get("PHPSESSID"))

    # 3. GET login page → extract server-rendered CSRF token
    login_page = session.get(_LOGIN_URL + "?from=enroll")
    csrf_match = re.search(
        r'name="_csrf_token"\s+value="([^"]+)"', login_page.text
    )
    if not csrf_match:
        raise RuntimeError("Could not extract CSRF token from LineLeader login page")
    csrf_token = csrf_match.group(1)
    logger.debug("CSRF token extracted")

    # 4. POST credentials → triggers redirect chain ending at callback URL
    resp = session.post(
        _LOGIN_URL,
        data={
            "_csrf_token": csrf_token,
            "_username": settings.LINELEADER_USERNAME,
            "_password": settings.LINELEADER_PASSWORD,
        },
        allow_redirects=False,
    )

    auth_code = _follow_to_callback(session, resp)
    if not auth_code:
        raise RuntimeError(
            "Login appeared to succeed but auth code was not captured. "
            "Credentials may be wrong or the OAuth flow has changed."
        )
    logger.debug("Auth code captured")

    # 5. Exchange code + verifier for Bearer JWT
    token_resp = requests.post(
        _SSO_LOGIN_URL,
        json={"code": auth_code, "code_verifier": code_verifier},
        headers={"Content-Type": "application/json", "X-UI-Request": "true"},
    )
    if token_resp.status_code != 200:
        raise RuntimeError(
            f"sso/login token exchange failed: {token_resp.status_code} {token_resp.text[:200]}"
        )

    data = token_resp.json()
    raw_token = data.get("token") or data.get("access_token", "")
    if not raw_token:
        raise RuntimeError(f"No token in sso/login response: {data}")

    bearer = f"Bearer {raw_token}"
    expires_at = _parse_jwt_expiry(raw_token)
    _save_token(bearer, expires_at)
    logger.info(
        "Bearer token obtained — expires at %s",
        expires_at.astimezone().strftime("%H:%M:%S"),
    )
    return bearer


def _follow_to_callback(
    session: requests.Session, resp: requests.Response
) -> Optional[str]:
    """
    Follow the redirect chain after credential POST until we reach the
    my.childcarecrm.com callback URL. Returns the auth code or None.
    """
    for _ in range(8):
        location = resp.headers.get("location", "")
        if not location:
            break

        abs_location = (
            location
            if location.startswith("http")
            else "https://login.lineleader.com" + location
        )

        parsed = urllib.parse.urlparse(abs_location)
        if parsed.netloc == "my.childcarecrm.com":
            # Code is in query string or in the fragment after '?'
            qs = urllib.parse.parse_qs(parsed.query)
            if not qs.get("code") and "?" in parsed.fragment:
                qs = urllib.parse.parse_qs(parsed.fragment.split("?", 1)[1])
            codes = qs.get("code", [])
            return codes[0] if codes else None

        resp = session.get(abs_location, allow_redirects=False)

    return None


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _load_cached_token() -> Optional[str]:
    """Load token from cache if it exists and hasn't expired (with buffer)."""
    path = settings.LINELEADER_TOKEN_FILE
    if not os.path.exists(path):
        logger.debug("No cached token file found")
        return None

    try:
        with open(path) as f:
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
    with open(settings.LINELEADER_TOKEN_FILE, "w") as f:
        json.dump({"token": token_str, "expires_at": expires_at.isoformat()}, f, indent=2)
    logger.debug("Token saved to %s", settings.LINELEADER_TOKEN_FILE)


def _parse_jwt_expiry(token_str: str) -> datetime:
    """Parse exp claim from JWT. Falls back to 1 hour from now if parsing fails."""
    try:
        parts = token_str.split(".")
        if len(parts) != 3:
            raise ValueError("Not a valid JWT")
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except Exception as e:
        logger.warning("Could not parse JWT expiry: %s — defaulting to 1 hour", e)
        return datetime.now(timezone.utc) + timedelta(hours=1)

"""
sites/mystudio/auth.py
======================
MyStudio authentication: direct API login + manual OTP.

Auth is session-based (PHP cookies), not bearer tokens.
Uses direct requests (no Playwright) for login.
Cookies cached for 30 days (remember_me: true).
"""

import base64
import urllib.parse
import requests
import os
import json
from datetime import datetime
from typing import Dict, Optional

from config.settings import settings
from core.logger import get_logger

logger = get_logger(__name__)

BASE_URL = settings.MYSTUDIO_API_URL
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json; charset=UTF-8",
    "Referer": "https://cn.mystudio.io/v43/WebPortal/",
    "Origin": "https://cn.mystudio.io",
}


def _encode(value: str) -> str:
    """URL-encode then base64-encode — matches MyStudio's encoding."""
    return base64.b64encode(urllib.parse.quote(value, safe='').encode()).decode()


class MystudioOTPRequired(Exception):
    """Raised when MyStudio needs OTP and can't prompt interactively."""
    pass


# Holds the partial session while waiting for user to enter OTP
_pending_session: Optional[requests.Session] = None


def get_session() -> requests.Session:
    """
    Return an authenticated requests.Session with valid MyStudio cookies.

    If cookies are cached (30 days), returns immediately.
    If not, triggers OTP email and raises MystudioOTPRequired.
    Caller must catch MystudioOTPRequired and call complete_otp_login(otp) later.
    """
    cached = _load_cached_cookies()
    if cached:
        logger.info("Using cached MyStudio cookies (30-day cache)")
        return _build_session_from_cookies(cached)

    # No cache — start login flow (triggers OTP email)
    logger.info("No valid cached cookies — starting fresh login")
    _start_login()
    # _start_login always raises MystudioOTPRequired


def _start_login() -> None:
    """
    Step 1 of login: POST credentials → OTP email sent → raise MystudioOTPRequired.
    Stores partial session in _pending_session for complete_otp_login() to use.
    """
    global _pending_session

    session = requests.Session()
    session.headers.update(HEADERS)

    logger.info("Sending MyStudio credentials...")
    resp = session.post(f"{BASE_URL}/login", json={
        "email": settings.MYSTUDIO_USERNAME,
        "password": _encode(settings.MYSTUDIO_PASSWORD),
        "is_sso": "N",
        "push_device_id": "",
        "user_agent": HEADERS["User-Agent"],
        "from": "login_form",
    })
    data = resp.json()
    if data.get("status") != "Success":
        raise Exception(f"MyStudio login failed: {data.get('msg')}")

    logger.info("OTP email sent to %s", settings.MYSTUDIO_USERNAME)
    _pending_session = session
    raise MystudioOTPRequired(f"OTP sent to {settings.MYSTUDIO_USERNAME}")


def complete_otp_login(otp: str) -> requests.Session:
    """
    Step 2 of login: submit OTP, cache cookies, return authenticated session.
    Must be called after get_session() raised MystudioOTPRequired.
    """
    global _pending_session

    if _pending_session is None:
        raise Exception("No pending MyStudio login session. Try asking for the schedule again.")

    logger.info("Submitting OTP...")
    resp = _pending_session.post(f"{BASE_URL}/login", json={
        "email": settings.MYSTUDIO_USERNAME,
        "password": _encode(settings.MYSTUDIO_PASSWORD),
        "is_sso": "N",
        "push_device_id": "",
        "user_agent": HEADERS["User-Agent"],
        "otpCode": _encode(otp.strip()),
        "from": "otp_form",
        "remember_me": True,
    })
    data = resp.json()
    if data.get("status") != "Success":
        raise Exception(f"OTP incorrect: {data.get('msg')}")

    session = _pending_session
    _pending_session = None

    _save_cached_cookies(dict(session.cookies))
    logger.info("MyStudio login complete, cookies cached for 30 days")
    return session


def _load_cached_cookies() -> Optional[Dict[str, str]]:
    """Load cached cookies if file exists. Returns None if missing or expired."""
    cache_file = settings.MYSTUDIO_COOKIE_FILE
    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file) as f:
            data = json.load(f)
        cookies = data.get("cookies", {})
        logger.debug("Loaded cached cookies from %s", cache_file)
        return cookies
    except Exception as e:
        logger.warning("Failed to load cached cookies: %s", e)
        return None


def _save_cached_cookies(cookies: Dict[str, str]) -> None:
    """Save cookies to cache file."""
    cache_file = settings.MYSTUDIO_COOKIE_FILE
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    try:
        with open(cache_file, "w") as f:
            json.dump({
                "cookies": cookies,
                "saved_at": datetime.utcnow().isoformat(),
            }, f, indent=2)
        logger.info("Cached MyStudio cookies (keys: %s)", list(cookies.keys()))
    except Exception as e:
        logger.warning("Failed to save cached cookies: %s", e)


def _build_session_from_cookies(cookies: Dict[str, str]) -> requests.Session:
    """Build a requests.Session from a cookies dict."""
    session = requests.Session()
    session.headers.update(HEADERS)

    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".mystudio.io")

    logger.debug("Built session from cached cookies")
    return session

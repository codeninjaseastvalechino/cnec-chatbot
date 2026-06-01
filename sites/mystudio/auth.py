"""
sites/mystudio/auth.py
======================
MyStudio authentication: direct API login + manual OTP + cookie caching.

No Playwright needed — direct requests works for login.
Auth is session-based (PHP cookies), not bearer tokens.

Confirmed working pattern from mystudio_login_api.py (2026-06-01).
"""

import json
import base64
import urllib.parse
import requests
import os
from datetime import datetime
from typing import Optional, Dict, List

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
    """URL-encode then base64-encode — matches MyStudio's password/OTP encoding."""
    return base64.b64encode(urllib.parse.quote(value, safe='').encode()).decode()


def get_session() -> requests.Session:
    """
    Return an authenticated requests.Session with valid MyStudio cookies.

    Loads cached cookies if still valid (verifySession check).
    Falls back to full login with manual OTP if expired.
    """
    cached = _load_cached_cookies()
    if cached:
        session = _build_session(cached)
        if _verify_session(session):
            logger.info("Using cached MyStudio cookies")
            return session
        logger.info("Cached session invalid — re-logging in")

    session = _login()
    _save_cookie_cache(dict(session.cookies))
    return session


def _login() -> requests.Session:
    """
    Full login: credentials POST → OTP email → manual OTP entry → session.
    Mirrors mystudio_login_api.py exactly.
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1: POST credentials to trigger OTP email
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

    # Step 2: Manual OTP entry
    print("\n" + "=" * 60)
    print(f"MyStudio 2FA: Check {settings.MYSTUDIO_USERNAME} for the OTP code.")
    print("=" * 60)
    otp = input("Enter 6-digit OTP code: ").strip()

    # Step 3: Submit OTP with remember_me=True
    logger.info("Submitting OTP...")
    resp = session.post(f"{BASE_URL}/login", json={
        "email": settings.MYSTUDIO_USERNAME,
        "password": _encode(settings.MYSTUDIO_PASSWORD),
        "is_sso": "N",
        "push_device_id": "",
        "user_agent": HEADERS["User-Agent"],
        "otpCode": _encode(otp),
        "from": "otp_form",
        "remember_me": True,
    })
    data = resp.json()
    if data.get("status") != "Success":
        raise Exception(f"MyStudio OTP failed: {data.get('msg')}")

    logger.info("Logged in as: %s", settings.MYSTUDIO_USERNAME)
    return session


def _build_session(cookies: Dict) -> requests.Session:
    """Build a requests.Session from a cookie dict."""
    session = requests.Session()
    session.headers.update(HEADERS)
    for name, value in cookies.items():
        session.cookies.set(name, value, domain="cn.mystudio.io")
    return session


def _verify_session(session: requests.Session) -> bool:
    """Check if the session is still active."""
    try:
        resp = session.get(f"{BASE_URL}/verifySession", timeout=10)
        return resp.json().get("status") == "Success"
    except Exception as e:
        logger.warning("verifySession failed: %s", e)
        return False


def _load_cached_cookies() -> Optional[Dict]:
    """Load cookies from cache file. Returns None if missing or corrupt."""
    if not os.path.exists(settings.MYSTUDIO_COOKIE_FILE):
        return None
    try:
        with open(settings.MYSTUDIO_COOKIE_FILE) as f:
            return json.load(f).get("cookies")
    except Exception as e:
        logger.warning("Failed to load cached cookies: %s", e)
        return None


def _save_cookie_cache(cookies: Dict) -> None:
    """Save cookies dict to cache file."""
    os.makedirs(os.path.dirname(settings.MYSTUDIO_COOKIE_FILE), exist_ok=True)
    with open(settings.MYSTUDIO_COOKIE_FILE, "w") as f:
        json.dump({
            "cookies": cookies,
            "saved_at": datetime.utcnow().isoformat(),
        }, f, indent=2)
    logger.info("MyStudio cookies cached — keys: %s", list(cookies.keys()))


# Compatibility shim — MyStudio uses cookies, not bearer tokens
async def get_bearer_token() -> str:
    return "cookie-based"

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


def get_session() -> requests.Session:
    """
    Return an authenticated requests.Session with valid MyStudio cookies.

    Tries to load cached cookies first (30 days).
    Only does OTP login if cache is missing or expired.
    """
    # Try cached cookies first
    cached = _load_cached_cookies()
    if cached:
        logger.info("Using cached MyStudio cookies (30-day cache)")
        return _build_session_from_cookies(cached)

    # Cache miss — do full login with OTP
    logger.info("No valid cached cookies — doing fresh login")
    session = _login_with_otp()

    # Cache the cookies
    _save_cached_cookies(dict(session.cookies))
    return session


def _login_with_otp() -> requests.Session:
    """Do full login: credentials → OTP email → OTP entry → session."""
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
    otp = os.getenv("MYSTUDIO_OTP")
    if not otp:
        print("\n" + "=" * 60)
        print(f"MyStudio 2FA: Check {settings.MYSTUDIO_USERNAME} for OTP code.")
        print("=" * 60)
        otp = input("Enter 6-digit OTP code: ").strip()
    else:
        logger.info("Using OTP from environment variable")
        otp = otp.strip()

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

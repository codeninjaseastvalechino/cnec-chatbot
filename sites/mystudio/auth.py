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
import threading
from datetime import datetime
from typing import Dict, Optional

from requests.adapters import HTTPAdapter

from config.settings import settings
from core.logger import get_logger

logger = get_logger(__name__)

BASE_URL = settings.MYSTUDIO_API_URL
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://cn.mystudio.io/v43/WebPortal/",
    "Origin": "https://cn.mystudio.io",
}


def _encode(value: str) -> str:
    """URL-encode then base64-encode — matches MyStudio's encoding."""
    return base64.b64encode(urllib.parse.quote(value, safe='').encode()).decode()


class MystudioOTPRequired(Exception):
    """Raised when MyStudio needs OTP and can't prompt interactively.

    gmail_error: set to the error string if Gmail connection failed;
                 None if Gmail was not configured or timed out normally.
    """
    def __init__(self, message: str = "", gmail_error: Optional[str] = None):
        super().__init__(message)
        self.gmail_error = gmail_error


# Holds the partial session while waiting for user to enter OTP
_pending_session: Optional[requests.Session] = None

# Reused authenticated Session so MyStudio calls share one keep-alive connection
# instead of re-doing a TLS handshake per request. Guarded by _session_lock
# because Flask runs threaded=True and camp revenue fans calls out across threads.
# Reset by clear_cached_cookies() — every 401 re-auth path already calls that.
_cached_session: Optional[requests.Session] = None
_session_lock = threading.Lock()


def _new_session() -> requests.Session:
    """Build a fresh Session with MyStudio headers and a connection pool sized
    for our concurrent fan-out (camp revenue runs up to ~24 calls at once; the
    urllib3 default pool_maxsize=1 would discard the extras instead of reusing)."""
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=25)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_session() -> requests.Session:
    """
    Return an authenticated requests.Session with valid MyStudio cookies.

    Reuses a single Session across calls (keep-alive) so we don't re-handshake
    per request. If cookies are cached (30 days), returns immediately.
    If GMAIL_ADDRESS + GMAIL_APP_PASSWORD are configured, auto-fetches OTP.
    Otherwise triggers OTP email and raises MystudioOTPRequired for manual entry.
    """
    global _cached_session
    with _session_lock:
        if _cached_session is not None:
            return _cached_session

    cached = _load_cached_cookies()
    if cached:
        # DEBUG, not INFO: get_session() is called once per API request, so at
        # INFO this line spams the log dozens of times per revenue query.
        logger.debug("Using cached MyStudio cookies (30-day cache)")
        session = _build_session_from_cookies(cached)
        with _session_lock:
            # Another thread may have built one while we were loading — prefer
            # the first winner so all callers share the same connection pool.
            if _cached_session is None:
                _cached_session = session
            return _cached_session

    logger.info("No valid cached cookies — starting fresh login")
    return _start_login()


def _start_login() -> requests.Session:
    """
    Step 1 of login: POST credentials → OTP email sent.
    If Gmail credentials are configured, auto-fetches OTP and completes login.
    Otherwise raises MystudioOTPRequired for manual entry via chat UI.
    """
    global _pending_session

    session = _new_session()

    # Snapshot inbox before sending credentials so we only look at new emails
    inbox_uid_before_otp = _get_inbox_uid_snapshot()

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

    code, gmail_error = _try_auto_otp(inbox_uid_before_otp)
    if code:
        return complete_otp_login(code)

    raise MystudioOTPRequired(f"OTP sent to {settings.MYSTUDIO_USERNAME}", gmail_error=gmail_error)


def _get_inbox_uid_snapshot() -> int:
    """Get current max inbox UID before triggering OTP — used to filter out pre-existing emails."""
    if not settings.GMAIL_ADDRESS or not settings.GMAIL_APP_PASSWORD:
        return 0
    try:
        from core.gmail_imap import get_inbox_max_uid
        uid = get_inbox_max_uid(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
        logger.debug("Inbox UID snapshot: %d", uid)
        return uid
    except Exception:
        return 0


def _try_auto_otp(after_uid: int = 0) -> "tuple":
    """Try to auto-fetch the MyStudio OTP from Gmail.

    Returns (code, gmail_error):
      code        — the 6-digit string if found, else None
      gmail_error — error string if Gmail connection failed, else None
    """
    if not settings.GMAIL_ADDRESS or not settings.GMAIL_APP_PASSWORD:
        logger.debug("Gmail credentials not configured — skipping auto-OTP")
        return None, None

    logger.info("Auto-OTP: polling Gmail for MyStudio code (after UID %d)...", after_uid)
    try:
        from core.gmail_imap import get_2fa_code_from_gmail
        code = get_2fa_code_from_gmail(
            gmail_address=settings.GMAIL_ADDRESS,
            gmail_app_password=settings.GMAIL_APP_PASSWORD,
            timeout_seconds=settings.GMAIL_2FA_TIMEOUT_SECONDS,
            after_uid=after_uid,
        )
        if code:
            logger.info("Auto-OTP extracted successfully")
        else:
            logger.warning("Auto-OTP timed out — falling back to manual entry")
        return code, None
    except Exception as e:
        logger.warning("Auto-OTP failed (%s) — falling back to manual entry", e)
        return None, str(e)


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

    # The WebPortal sets c_u_id_{user_id}=<email> — our API login doesn't get it
    # automatically, so we inject it. Required by getFilterDetails.
    email_cookie = urllib.parse.quote(settings.MYSTUDIO_USERNAME, safe="")
    session.cookies.set(f"c_u_id_{settings.MYSTUDIO_USER_ID}", email_cookie, domain=".mystudio.io")

    _save_cached_cookies(dict(session.cookies))
    global _cached_session
    with _session_lock:
        _cached_session = session  # reuse the just-authenticated session going forward
    logger.info("MyStudio login complete, cookies cached for 30 days")
    return session


def verify_and_refresh_session() -> bool:
    """
    Proactively check whether cached MyStudio cookies are still valid.
    If the server-side session has expired (as happens daily), triggers
    auto-OTP re-authentication in the background before any user request hits a 401.

    Returns True if session is valid or was refreshed successfully.
    Returns False if no cache exists or re-auth failed (non-fatal — first real
    request will retry and prompt if needed).
    """
    cached = _load_cached_cookies()
    if not cached:
        logger.info("Proactive session check: no cache — will authenticate on first request")
        return False

    try:
        session = _build_session_from_cookies(cached)
        resp = session.get(
            f"{BASE_URL}/verifySession",
            params={"company_id": settings.MYSTUDIO_COMPANY_ID},
            timeout=10,
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get("status") == "Success":
                    logger.info("Proactive session check: cookies still valid")
                    return True
            except Exception:
                pass

        logger.info("Proactive session check: session expired — re-authenticating")
        clear_cached_cookies()
        _start_login()  # auto-OTP if Gmail configured; raises MystudioOTPRequired if it times out
        logger.info("Proactive session check: re-authentication successful")
        return True

    except MystudioOTPRequired:
        logger.warning("Proactive session check: auto-OTP timed out — manual OTP required on next MyStudio request")
        return False
    except Exception as e:
        logger.warning("Proactive session check failed: %s", e)
        return False


def clear_cached_cookies() -> None:
    """Delete the cookie cache file and drop the in-memory Session — forces a
    fresh login on the next get_session() call. This is the single invalidation
    hook every 401 re-auth path calls, so resetting the Session here keeps the
    keep-alive cache from serving a dead session after re-auth."""
    global _cached_session
    with _session_lock:
        _cached_session = None
    cache_file = settings.MYSTUDIO_COOKIE_FILE
    if os.path.exists(cache_file):
        os.remove(cache_file)
        logger.info("Cleared MyStudio cookie cache — fresh login required")


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
    session = _new_session()

    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".mystudio.io")

    logger.debug("Built session from cached cookies")
    return session

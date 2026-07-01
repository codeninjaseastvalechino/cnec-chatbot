"""
config/settings.py
==================
All configuration for the CNEC Chatbot.

All center-specific values live here, loaded from .env.
To deploy for another Code Ninjas center: update .env and the IDs below only.
No other files need changes (ADR-005).

Required .env keys:
    LINELEADER_USERNAME=venay.bhatia@codeninjas.com
    LINELEADER_PASSWORD=<password>
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── LineLeader / ChildCareCRM ─────────────────────────────────────────────
    # Navigate to the app — it redirects to login.lineleader.com/login?from=enroll
    # (going directly to login.lineleader.com redirects to the marketing site)
    LINELEADER_LOGIN_URL: str = "https://my.childcarecrm.com"
    CHILDCARECRM_BASE_URL: str = "https://my.childcarecrm.com"
    CHILDCARECRM_API_URL: str = "https://live.childcarecrm.com/api/v3"

    # Credentials — loaded from .env
    LINELEADER_USERNAME: str = os.getenv("LINELEADER_USERNAME", "")
    LINELEADER_PASSWORD: str = os.getenv("LINELEADER_PASSWORD", "")

    # Center-specific IDs (Code Ninjas Eastvale Chino)
    LINELEADER_ORG_ID: str = "101178"       # parent org
    LINELEADER_CENTER_ORG_ID: str = "101179" # center-level org (used for calendar API)
    LINELEADER_CENTER_ID: str = "102025"
    LINELEADER_STAFF_ID: str = "58347"

    # Token cache
    LINELEADER_TOKEN_FILE: str = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "browser_state",
        "lineleader_token.json",
    )

    # ── MyStudio (Site 1) ─────────────────────────────────────────────────────
    MYSTUDIO_PORTAL_URL: str = "https://cn.mystudio.io/v43/WebPortal/"
    MYSTUDIO_API_URL: str = "https://cn.mystudio.io/v43/Api/PortalApi"
    MYSTUDIO_API_V2_URL: str = "https://cn.mystudio.io/Api/v2"

    # Credentials — loaded from .env
    MYSTUDIO_USERNAME: str = os.getenv("MYSTUDIO_USERNAME", "")
    MYSTUDIO_PASSWORD: str = os.getenv("MYSTUDIO_PASSWORD", "")

    # Center-specific IDs — REQUIRED from .env (no default on purpose).
    # A hardcoded fallback would let a misconfigured center silently read/write
    # Eastvale Chino's data (company_id 578). Failing loud is the safe, multi-tenant
    # behavior (ADR-005). Eastvale's values: MYSTUDIO_COMPANY_ID=578, MYSTUDIO_USER_ID=9901
    MYSTUDIO_COMPANY_ID: str = os.getenv("MYSTUDIO_COMPANY_ID", "")
    MYSTUDIO_USER_ID: str = os.getenv("MYSTUDIO_USER_ID", "")

    # Cookie cache (session-based auth, not bearer token)
    MYSTUDIO_COOKIE_FILE: str = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "browser_state",
        "mystudio_cookies.json",
    )

    # ── Admin page ───────────────────────────────────────────────────────────
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "cnec-admin")

    # ── Web session / multi-user isolation ───────────────────────────────────
    # SECRET_KEY signs the Flask session cookie so each browser gets a tamper-proof
    # session id (used to scope conversation history per user). MUST be set in .env
    # for production — if empty, app.py falls back to an ephemeral key (sessions
    # reset on restart). Generate one with: python3 -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    # Idle minutes before a browser's conversation context is dropped and started
    # fresh. Code default is fine; override in .env only to tune.
    SESSION_IDLE_MINUTES: int = int(os.getenv("SESSION_IDLE_MINUTES", "30"))

    # ── Localization ─────────────────────────────────────────────────────────
    # Center timezone — anchors "today"/"now" in the assistant's system prompt.
    # Pinned here (not the host's TZ) so the date is correct regardless of where
    # the app is deployed. Override per center in .env.
    CENTER_TIMEZONE: str = os.getenv("CENTER_TIMEZONE", "America/Los_Angeles")

    # ── Gmail IMAP (2FA code extraction) ──────────────────────────────────────
    GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "").strip()
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "").strip()
    GMAIL_2FA_TIMEOUT_SECONDS: int = int(os.getenv("GMAIL_2FA_TIMEOUT_SECONDS", "120"))
    GMAIL_2FA_POLL_INTERVAL_SECONDS: int = 2

    # ── Camp pricing (used for revenue analysis) ─────────────────────────────
    CAMP_HALF_DAY_PRICE: float = 249.00   # AM / PM sessions
    CAMP_FULL_DAY_PRICE: float = 399.00   # Full day / All day sessions

    # Browser settings
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT_MS: int = 30000

    def validate(self) -> None:
        """Raise EnvironmentError if required credentials are missing."""
        missing = []
        if not self.LINELEADER_USERNAME:
            missing.append("LINELEADER_USERNAME")
        if not self.LINELEADER_PASSWORD:
            missing.append("LINELEADER_PASSWORD")
        if not self.MYSTUDIO_COMPANY_ID:
            missing.append("MYSTUDIO_COMPANY_ID")
        if not self.MYSTUDIO_USER_ID:
            missing.append("MYSTUDIO_USER_ID")
        if missing:
            raise EnvironmentError(
                f"Missing required .env keys: {', '.join(missing)}"
            )


settings = Settings()

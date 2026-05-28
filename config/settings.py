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
    LINELEADER_ORG_ID: str = "101178"
    LINELEADER_CENTER_ID: str = "102025"
    LINELEADER_STAFF_ID: str = "58347"

    # Token cache
    LINELEADER_TOKEN_FILE: str = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "browser_state",
        "lineleader_token.json",
    )

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
        if missing:
            raise EnvironmentError(
                f"Missing required .env keys: {', '.join(missing)}"
            )


settings = Settings()

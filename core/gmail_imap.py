"""
core/gmail_imap.py
==================
Gmail IMAP integration for extracting 2FA codes from inbox.

Used by MyStudio login to automatically retrieve 2FA codes sent via email.
"""

import imaplib
import re
import time
from typing import Optional
from datetime import datetime

from core.logger import get_logger

logger = get_logger(__name__)


def get_2fa_code_from_gmail(
    gmail_address: str,
    gmail_app_password: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 2,
) -> Optional[str]:
    """
    Poll Gmail inbox for the most recent 2FA code.

    Connects to Gmail IMAP, searches for unread emails, extracts 6-digit code
    from subject or body using regex. Polls every poll_interval_seconds until
    code found or timeout reached.

    Args:
        gmail_address: Gmail account email (e.g., "shared@gmail.com")
        gmail_app_password: 16-character Gmail app password (spaces ignored)
        timeout_seconds: Max wait for code (default 120)
        poll_interval_seconds: Check inbox every N seconds (default 2)

    Returns:
        6-digit code string (e.g., "123456") or None if timeout.

    Raises:
        Exception: If IMAP connection fails or authentication error.
    """
    logger.info(
        "Starting 2FA code extraction from Gmail",
        extra={
            "module": "core.gmail_imap",
            "gmail_address": gmail_address,
            "timeout_seconds": timeout_seconds,
        },
    )

    # Remove spaces from app password (Google allows spaces, but IMAP doesn't need them)
    cleaned_password = gmail_app_password.replace(" ", "")

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        try:
            # Connect to Gmail IMAP server
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(gmail_address, cleaned_password)
            logger.debug(
                "Connected to Gmail IMAP",
                extra={"module": "core.gmail_imap", "gmail_address": gmail_address},
            )

            # Select inbox and search for unread emails
            mail.select("INBOX")
            status, unread_ids = mail.search(None, "UNSEEN")

            if status == "OK" and unread_ids[0]:
                # Get the most recent unread email
                email_ids = unread_ids[0].split()
                if email_ids:
                    latest_email_id = email_ids[-1]

                    # Fetch the email
                    status, email_data = mail.fetch(latest_email_id, "(RFC822)")

                    if status == "OK":
                        email_body = email_data[0][1].decode("utf-8")

                        # Extract 6-digit code from email
                        code_match = re.search(r"\b[0-9]{6}\b", email_body)
                        if code_match:
                            code = code_match.group(0)
                            logger.info(
                                "2FA code extracted successfully",
                                extra={
                                    "module": "core.gmail_imap",
                                    "code": code,
                                },
                            )
                            mail.close()
                            mail.logout()
                            return code

            mail.close()
            mail.logout()

            # No code found yet, wait and retry
            elapsed = time.time() - start_time
            logger.debug(
                "No 2FA code found, retrying",
                extra={
                    "module": "core.gmail_imap",
                    "elapsed_seconds": int(elapsed),
                    "timeout_seconds": timeout_seconds,
                },
            )
            time.sleep(poll_interval_seconds)

        except imaplib.IMAP4.error as e:
            logger.error(
                "Gmail IMAP authentication failed",
                extra={"module": "core.gmail_imap", "error": str(e)},
            )
            raise
        except Exception as e:
            logger.error(
                "Error connecting to Gmail IMAP",
                extra={"module": "core.gmail_imap", "error": str(e)},
            )
            raise

    # Timeout reached
    elapsed = time.time() - start_time
    logger.warning(
        "2FA code extraction timeout — no code found",
        extra={
            "module": "core.gmail_imap",
            "elapsed_seconds": int(elapsed),
            "timeout_seconds": timeout_seconds,
        },
    )
    return None

"""
core/gmail_imap.py
==================
Gmail IMAP integration for extracting 2FA codes from inbox.

Used by MyStudio login to automatically retrieve 2FA codes sent via email.
"""

import email as email_lib
import imaplib
import re
import time
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


def get_inbox_max_uid(gmail_address: str, gmail_app_password: str) -> int:
    """
    Return the highest UID currently in the inbox.
    Call this BEFORE triggering the OTP email so we can ignore pre-existing messages.
    Returns 0 if inbox is empty or connection fails.
    """
    cleaned_password = gmail_app_password.replace(" ", "")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(gmail_address, cleaned_password)
        mail.select("INBOX")
        status, data = mail.uid("search", None, "ALL")
        mail.close()
        mail.logout()
        if status == "OK" and data[0]:
            uids = data[0].split()
            return int(uids[-1]) if uids else 0
        return 0
    except Exception as e:
        logger.warning("Could not get inbox max UID: %s", e)
        return 0


def get_2fa_code_from_gmail(
    gmail_address: str,
    gmail_app_password: str,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 3,
    after_uid: int = 0,
) -> Optional[str]:
    """
    Poll Gmail inbox for a new 2FA code that arrived after after_uid.

    Connects to Gmail IMAP, searches for unread emails with UID > after_uid,
    extracts 6-digit code via regex. Polls every poll_interval_seconds until
    code found or timeout reached.

    Args:
        gmail_address: Gmail account email
        gmail_app_password: 16-character Gmail app password (spaces ignored)
        timeout_seconds: Max wait for code (default 120)
        poll_interval_seconds: Check inbox every N seconds (default 3)
        after_uid: Only look at messages with UID > this value (0 = all unread)

    Returns:
        6-digit code string or None if timeout.
    """
    logger.info(
        "Starting 2FA code extraction from Gmail",
        extra={"gmail_address": gmail_address, "after_uid": after_uid},
    )

    cleaned_password = gmail_app_password.replace(" ", "")
    uid_filter = f"UID {after_uid + 1}:*" if after_uid > 0 else "ALL"
    start_time = time.time()

    # Short initial delay to give the OTP email time to arrive
    time.sleep(5)

    while time.time() - start_time < timeout_seconds:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            mail.login(gmail_address, cleaned_password)
            mail.select("INBOX")

            # Search for new unread messages only
            status, data = mail.uid("search", None, f"(UNSEEN {uid_filter})")

            if status == "OK" and data[0]:
                uids = data[0].split()
                if uids:
                    # Take the most recently arrived message
                    latest_uid = uids[-1]
                    status, email_data = mail.uid("fetch", latest_uid, "(RFC822)")

                    if status == "OK":
                        raw = email_data[0][1]
                        msg = email_lib.message_from_bytes(raw)
                        sender = msg.get("From", "unknown")
                        subject = msg.get("Subject", "unknown")

                        # Search plain text only — avoids false matches in CSS/HTML color codes
                        text_content = _extract_text(msg)
                        code_match = re.search(r"\b[0-9]{6}\b", text_content)
                        if code_match:
                            code = code_match.group(0)
                            logger.info(
                                "2FA code extracted: %s | From: %s | Subject: %s",
                                code, sender, subject,
                            )
                            mail.close()
                            mail.logout()
                            return code
                        else:
                            logger.debug(
                                "Email found but no 6-digit code in text | From: %s | Subject: %s",
                                sender, subject,
                            )

            mail.close()
            mail.logout()

            elapsed = time.time() - start_time
            logger.debug(
                "No 2FA code found yet, retrying",
                extra={"elapsed_seconds": int(elapsed)},
            )
            time.sleep(poll_interval_seconds)

        except imaplib.IMAP4.error as e:
            logger.error("Gmail IMAP authentication failed: %s", e)
            raise
        except Exception as e:
            logger.error("Error connecting to Gmail IMAP: %s", e)
            raise

    logger.warning(
        "2FA code extraction timeout — no code found",
        extra={"timeout_seconds": timeout_seconds},
    )
    return None


def _extract_text(msg) -> str:
    """Extract plain text from a MIME email message. Falls back to HTML with tags stripped."""
    text_parts = []
    html_parts = []

    for part in msg.walk():
        content_type = part.get_content_type()
        if content_type == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                text_parts.append(payload.decode(charset, errors="replace"))
        elif content_type == "text/html":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                html_parts.append(payload.decode(charset, errors="replace"))

    if text_parts:
        return "\n".join(text_parts)

    # Fall back to HTML with tags stripped
    if html_parts:
        html = "\n".join(html_parts)
        return re.sub(r"<[^>]+>", " ", html)

    return ""

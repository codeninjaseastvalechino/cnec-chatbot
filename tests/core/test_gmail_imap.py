"""Tests for core/gmail_imap.py — email text extraction."""
import email as email_lib
import pytest

from core.gmail_imap import _extract_text


def _make_msg(text=None, html=None):
    """Build a MIME email message with the given text and/or HTML parts."""
    if text and not html:
        msg = email_lib.message_from_string(
            f"Content-Type: text/plain\r\n\r\n{text}"
        )
    elif html and not text:
        msg = email_lib.message_from_string(
            f"Content-Type: text/html\r\n\r\n{html}"
        )
    else:
        # Multipart
        raw = (
            "Content-Type: multipart/alternative; boundary=boundary\r\n\r\n"
            "--boundary\r\n"
            f"Content-Type: text/plain\r\n\r\n{text}\r\n"
            "--boundary\r\n"
            f"Content-Type: text/html\r\n\r\n{html}\r\n"
            "--boundary--"
        )
        msg = email_lib.message_from_string(raw)
    return msg


# ---------------------------------------------------------------------------
# Plain text extraction
# ---------------------------------------------------------------------------

def test_extracts_plain_text():
    msg = _make_msg(text="Your code is 821543 please use it now.")
    assert _extract_text(msg) == "Your code is 821543 please use it now."


def test_prefers_plain_text_over_html():
    msg = _make_msg(
        text="Your code is 821543",
        html="<p>Your code is 000000</p>",
    )
    result = _extract_text(msg)
    assert "821543" in result
    assert "000000" not in result


# ---------------------------------------------------------------------------
# HTML fallback — the bug that caused 000000 to be extracted
# ---------------------------------------------------------------------------

def test_html_fallback_strips_tags():
    html = "<p>Your code is <b>821543</b></p>"
    msg = _make_msg(html=html)
    result = _extract_text(msg)
    assert "821543" in result
    assert "<p>" not in result
    assert "<b>" not in result


def test_html_fallback_excludes_css_color_codes():
    """CSS color codes like #000000 inside style attributes must not appear in extracted text."""
    html = (
        "<p style='color: #000000;'>Your verification code:</p>"
        "<p style='font-size: 25px;'>821543</p>"
        "<p style='color: #525252;'>This code expires in 15 min.</p>"
    )
    msg = _make_msg(html=html)
    result = _extract_text(msg)
    assert "821543" in result
    assert "000000" not in result
    assert "525252" not in result


def test_html_fallback_real_mystudio_email():
    """Regression test for the exact MyStudio OTP email format."""
    html = """<html>
        <body>
            <div>
                <p style='color: #000000;'>To continue logging in to your Codeninjas account,
                please verify your account with this access code:</p>
                <p style='font-size: 25px;'>821543</p>
                <p style='color: #525252;'>This code will expire in 15.0000 min.</p>
            </div>
        </body>
    </html>"""
    msg = _make_msg(html=html)
    result = _extract_text(msg)

    import re
    codes = re.findall(r"\b[0-9]{6}\b", result)
    assert codes == ["821543"], f"Expected only ['821543'], got {codes}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_message_returns_empty_string():
    msg = email_lib.message_from_string("Content-Type: text/plain\r\n\r\n")
    assert _extract_text(msg) == ""


def test_no_text_or_html_returns_empty_string():
    msg = email_lib.message_from_string(
        "Content-Type: application/octet-stream\r\n\r\nbinarydata"
    )
    assert _extract_text(msg) == ""

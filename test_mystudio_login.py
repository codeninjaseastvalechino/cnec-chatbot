#!/usr/bin/env python3
"""
MyStudio auto-OTP login test — no LineLeader, no Claude, no cost.

Tests the full auto-OTP flow:
  1. Clears cached cookies (forces fresh login)
  2. Calls get_session() — triggers OTP email + auto-extracts from Gmail
  3. Verifies the session works by fetching today's schedule

Run: python3 test_mystudio_login.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from sites.mystudio.auth import get_session, clear_cached_cookies, MystudioOTPRequired
from sites.mystudio.schedules import get_todays_appointments
from datetime import date, datetime


def main():
    print("=" * 60)
    print("  MyStudio Auto-OTP Login Test")
    print("=" * 60)

    print("\n[1] Clearing cached cookies to force fresh login...")
    clear_cached_cookies()
    print("    Done.")

    print("\n[2] Calling get_session() — will send OTP email and auto-extract from Gmail...")
    print("    (This takes ~10-15 seconds while polling Gmail)\n")

    try:
        session = get_session()
        print("    ✅ Login successful — cookies cached for 30 days")
    except MystudioOTPRequired:
        print("    ❌ Auto-OTP not available — check GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env")
        return
    except Exception as e:
        print(f"    ❌ Login failed: {e}")
        return

    print("\n[3] Verifying session by fetching today's schedule...")
    try:
        today = date.today().isoformat()
        appointments = get_todays_appointments()
        print(f"    ✅ Got {len(appointments)} appointment(s) for {today}")
        for appt in appointments[:3]:
            print(f"       • {appt.start_time} — {appt.student_name} ({appt.appointment_type})")
        if len(appointments) > 3:
            print(f"       ... and {len(appointments) - 3} more")
    except Exception as e:
        print(f"    ❌ Schedule fetch failed: {e}")
        return

    print("\n✅ All checks passed — auto-OTP is working.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Test script: MyStudio API flow using Playwright for login (extracts full cookie jar)
then requests for API calls.
"""

import requests
import json
import base64
import asyncio
import urllib.parse
from playwright.async_api import async_playwright

MYSTUDIO_BASE_URL = "https://cn.mystudio.io/v43/Api/PortalApi"
COMPANY_ID = "578"
EMAIL = "eastvalechinocodeninjas@gmail.com"
PASSWORD = base64.b64encode(urllib.parse.quote("CN@16357").encode()).decode()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://cn.mystudio.io/v43/WebPortal/",
}


async def login_with_playwright() -> dict:
    """
    Use Playwright to log in to MyStudio (headless=False so user can enter OTP).
    Returns the full browser cookie jar as a dict.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        login_url = f"{MYSTUDIO_BASE_URL}/login"

        # Navigate to portal first so fetch calls are same-origin and cookies are stored
        await page.goto("https://cn.mystudio.io/v43/WebPortal/", wait_until="domcontentloaded")

        # Step 1: Trigger OTP email
        print("[1/3] Triggering 2FA email via Playwright...")
        await page.evaluate(f"""async () => {{
            const resp = await fetch('{login_url}', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                credentials: 'include',
                body: JSON.stringify({{
                    email: '{EMAIL}',
                    password: '{PASSWORD}',
                    is_sso: 'N',
                    push_device_id: '',
                    user_agent: navigator.userAgent,
                    device_type: '',
                    from: 'login_form',
                    remember_me: false
                }})
            }});
            return await resp.json();
        }}""")

        # Step 2: Ask user for OTP
        print("\n      📧 Check eastvalechinocodeninjas@gmail.com for the 2FA code.")
        otp = input("      Enter OTP: ").strip()
        otp_encoded = base64.b64encode(otp.encode()).decode()

        # Step 3: Submit OTP via Playwright (browser has proper cookies/session)
        print(f"[2/3] Submitting OTP via Playwright...")
        result = await page.evaluate(f"""async () => {{
            const resp = await fetch('{login_url}', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                credentials: 'include',
                body: JSON.stringify({{
                    email: '{EMAIL}',
                    password: '{PASSWORD}',
                    is_sso: 'N',
                    push_device_id: '',
                    user_agent: navigator.userAgent,
                    device_type: '',
                    otpCode: '{otp_encoded}',
                    from: 'otp_form',
                    remember_me: true
                }})
            }});
            return await resp.json();
        }}""")

        if result.get("status") != "Success":
            print(f"❌ Login failed: {result.get('msg')}")
            await browser.close()
            return None

        print(f"      ✅ Logged in as: {result['msg'].get('user_email')}")

        # Extract all cookies from the browser context
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}
        print(f"      Cookies: {list(cookie_dict.keys())}")

        await browser.close()
        return cookie_dict


def make_session(cookies: dict) -> requests.Session:
    """Build a requests.Session with all browser cookies."""
    session = requests.Session()
    session.headers.update(HEADERS)
    for name, value in cookies.items():
        session.cookies.set(name, value, domain='cn.mystudio.io')
    return session


def get_schedule(session: requests.Session, selected_date: str):
    """GET class schedule details for a date."""
    print(f"\n[3/3] Fetching schedule for {selected_date}...")
    resp = session.get(f"{MYSTUDIO_BASE_URL}/getClassScheduledetails", params={
        "class_appointment_times_id": "",
        "class_scheduler_verion": "2",
        "company_id": COMPANY_ID,
        "selected_date": selected_date,
        "view_roster_flag": "N",
    })
    print(f"      Status: {resp.status_code}")
    data = resp.json()
    if data.get("status") != "Success":
        print(f"❌ Schedule failed: {data}")
        return None
    return data["msg"]


def get_students(session: requests.Session, timeslot_id: str, selected_date: str):
    """POST to get student roster for a timeslot."""
    resp = session.post(f"{MYSTUDIO_BASE_URL}/getClassdatatabledetails", data={
        "draw": "1",
        "company_id": COMPANY_ID,
        "class_appointment_times_id": timeslot_id,
        "selected_date": selected_date,
        "start": "0",
        "length": "100",
    }, headers={
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    })

    if resp.status_code != 200:
        print(f"      ❌ Students failed: {resp.status_code} | {resp.text[:200]}")
        return []
    return resp.json().get("data", [])


def main():
    print("=" * 70)
    print("MyStudio: Playwright Login → Schedule → Students per Timeslot")
    print("=" * 70)

    cookies = asyncio.run(login_with_playwright())
    if not cookies:
        return

    session = make_session(cookies)

    # Verify session
    verify = session.get(f"{MYSTUDIO_BASE_URL}/verifySession")
    print(f"      verifySession: {verify.text[:150]}")

    selected_date = "2026-06-01"
    schedule = get_schedule(session, selected_date)
    if not schedule:
        return

    print(f"\n{'=' * 70}")
    total_students = 0

    for day in schedule:
        print(f"\n📅 {day.get('date_view')}")
        for prog in day.get("c_details", []):
            title = prog.get("class_appointment_title")
            total_reg = prog.get("reg_count", 0)
            print(f"\n  🎮 {title}  ({total_reg} total enrolled)")

            for slot in prog.get("child_details", []):
                slot_id = slot.get("class_appointment_times_id")
                start = slot.get("start_time")
                cap = slot.get("capacity_value", 0)
                reg = slot.get("reg_count_time", 0)
                print(f"    ⏰ {start}  ({reg}/{cap})")

                students = get_students(session, slot_id, selected_date)
                if students:
                    for s in students:
                        name = s.get("Participant", "Unknown")
                        parent = s.get("Buyer", "")
                        rank = s.get("rank_status", "")
                        total_students += 1
                        print(f"       👤 {name} ({rank}) | Parent: {parent}")
                else:
                    print(f"       (no students)")

    print(f"\n{'=' * 70}")
    print(f"✅ Done — {total_students} students across all timeslots")


if __name__ == "__main__":
    main()

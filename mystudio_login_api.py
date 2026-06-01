#!/usr/bin/env python3
"""
MyStudio login test — confirms auth.py is working.

Run 1: triggers OTP, saves cookies.
Run 2+: auto-login, no OTP needed.

Usage:
    python3 mystudio_login_api.py
"""

from datetime import date
from sites.mystudio.auth import get_session, _verify_session

BASE_URL = "https://cn.mystudio.io/v43/Api/PortalApi"


def get_schedule(session, date_str: str):
    """Fetch class schedule for a date and print student roster."""
    print(f"\n{'='*60}")
    print(f"Schedule for {date_str}")
    print(f"{'='*60}")

    resp = session.get(f"{BASE_URL}/getClassScheduledetails", params={
        "class_appointment_times_id": "",
        "class_scheduler_verion": "2",
        "company_id": "578",
        "selected_date": date_str,
        "view_roster_flag": "N",
    })
    data = resp.json()
    if data.get("status") != "Success":
        print(f"❌ Schedule failed: {data}")
        return

    total_students = 0
    for day in data.get("msg", []):
        print(f"\n📅 {day.get('date_view')}")
        for prog in day.get("c_details", []):
            title = prog.get("class_appointment_title")
            print(f"\n  🎮 {title}")
            for slot in prog.get("child_details", []):
                slot_id = slot["class_appointment_times_id"]
                start = slot["start_time"]
                reg = slot.get("reg_count_time", 0)
                cap = slot.get("capacity_value", 0)
                if int(reg) == 0:
                    continue
                print(f"    ⏰ {start}  ({reg}/{cap})")

                students_resp = session.post(f"{BASE_URL}/getClassdatatabledetails", data={
                    "draw": "1",
                    "company_id": "578",
                    "class_appointment_times_id": slot_id,
                    "selected_date": date_str,
                    "start": "0",
                    "length": "100",
                }, headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                })
                students = students_resp.json().get("data", [])
                if students:
                    for s in students:
                        print(f"       👤 {s.get('Participant')} ({s.get('rank_status')}) | Parent: {s.get('Buyer')}")
                        total_students += 1
                else:
                    print(f"       RAW: {students_resp.status_code} | {students_resp.text[:200]}")

    print(f"\n✅ {total_students} students total")


if __name__ == "__main__":
    print("=" * 60)
    print("MyStudio Login Test (via auth.py)")
    print("=" * 60)

    session = get_session()
    print(f"  Cookies: {list(session.cookies.keys())}")

    get_schedule(session, date.today().strftime("%Y-%m-%d"))

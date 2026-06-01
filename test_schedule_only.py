#!/usr/bin/env python3
"""Test just getClassScheduledetails without roster."""

from datetime import date
from sites.mystudio.auth import get_session

BASE_URL = "https://cn.mystudio.io/v43/Api/PortalApi"

print("\n" + "="*60)
print("Testing getClassScheduledetails")
print("="*60 + "\n")

session = get_session()
print(f"✅ Logged in")
print(f"Cookies: {list(session.cookies.keys())}\n")

today = date.today().strftime("%Y-%m-%d")
print(f"Fetching schedule for {today}...\n")

resp = session.get(f"{BASE_URL}/getClassScheduledetails", params={
    "class_appointment_times_id": "",
    "class_scheduler_verion": "2",
    "company_id": "578",
    "selected_date": today,
    "view_roster_flag": "N",
})

print(f"Status: {resp.status_code}")
data = resp.json()

if data.get("status") == "Success":
    print(f"✅ Schedule loaded!\n")

    for day in data.get("msg", []):
        print(f"📅 {day.get('date_view')}")
        for prog in day.get("c_details", []):
            title = prog.get("class_appointment_title")
            print(f"  🎮 {title}")
            for slot in prog.get("child_details", []):
                slot_id = slot["class_appointment_times_id"]
                start = slot["start_time"]
                reg = slot.get("reg_count_time", 0)
                print(f"    ⏰ {start} — {reg} registered (ID: {slot_id})")
else:
    print(f"❌ Failed: {data}")

#!/usr/bin/env python3
"""
Direct MyStudio API test script — no Claude, no Flask, no cost.

Tests the 6 scenarios from the M3/M4 test plan:
  1. Find Veshant Bhatia
  2. Find Pranay Bhatia
  3. Find Venay Bhatia (parent name — expect 0 results)
  4. Reschedule Veshant June 15 → June 16 3pm (single)
  5. Reschedule Veshant from next date → following day, all future
  6. Cancel Veshant a future date, all future

Run: python3 test_mystudio.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from sites.mystudio.students import (
    find_student_by_name,
    get_student_details,
    get_student_upcoming_appointments,
    get_student_attendance_this_week,
)
from sites.mystudio.write import cancel_student_appointment, move_student_appointment


def sep(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def show_student(student, details=None):
    print(f"  Name:       {student.name}")
    print(f"  student_id: {student.student_id}  participant_id: {student.participant_id}")
    if details:
        p = details.get("participant_details", {})
        memberships = details.get("reg_details", {}).get("membership_details", [])
        active = [m for m in memberships if m.get("mem_status") == "Active"]
        print(f"  Parent:     {p.get('buyer_name')} | {p.get('student_mobile')}")
        print(f"  Belt:       {active[0].get('rank_status') if active else 'N/A'}")
        print(f"  Programs:   {', '.join(m.get('membership_category_title','') for m in active)}")


def show_appointments(upcoming):
    if not upcoming:
        print("  No upcoming sessions.")
        return
    for a in upcoming:
        print(f"  {a.start_time.strftime('%a %b %-d')} {a.time_display():>8}  "
              f"{a.appointment_type:<20}  "
              f"class_reg_id={a.id}  detail_id={a.registration_detail_id}  "
              f"times_id={a.class_appointment_times_id}")


def resolve_student(name):
    """Find student, auto-select by active memberships if duplicates."""
    students = find_student_by_name(name)
    if not students:
        return None, f"No student found matching '{name}'"
    if len(students) == 1:
        return students[0], None
    # Multiple — filter by active memberships
    active = []
    for s in students:
        d = get_student_details(s.student_id, s.participant_id)
        if d:
            memberships = d.get("reg_details", {}).get("membership_details", [])
            if any(m.get("mem_status") == "Active" for m in memberships):
                active.append(s)
    if len(active) == 1:
        return active[0], None
    if len(active) > 1:
        return None, f"Multiple active students named '{name}': " + ", ".join(s.name for s in active)
    return students[0], None


# ── Test 1: Find Veshant Bhatia ──────────────────────────────────────────────
sep("TEST 1 — Find Veshant Bhatia")
student, err = resolve_student("Veshant Bhatia")
if err:
    print(f"  ERROR: {err}")
else:
    details = get_student_details(student.student_id, student.participant_id)
    show_student(student, details)
    print(f"\n  Attendance this week: {get_student_attendance_this_week(student.student_id, student.participant_id)}")
    print("\n  Upcoming sessions (30 days):")
    upcoming = get_student_upcoming_appointments(student.student_id, student.participant_id, days_ahead=30)
    show_appointments(upcoming)


# ── Test 2: Find Pranay Bhatia ───────────────────────────────────────────────
sep("TEST 2 — Find Pranay Bhatia")
student2, err2 = resolve_student("Pranay Bhatia")
if err2:
    print(f"  ERROR: {err2}")
else:
    details2 = get_student_details(student2.student_id, student2.participant_id)
    show_student(student2, details2)
    print("\n  Upcoming sessions (30 days):")
    upcoming2 = get_student_upcoming_appointments(student2.student_id, student2.participant_id, days_ahead=30)
    show_appointments(upcoming2)


# ── Test 3: Find Venay Bhatia (parent name) ───────────────────────────────────
sep("TEST 3 — Find Venay Bhatia (expect: no results)")
results3 = find_student_by_name("Venay Bhatia")
if not results3:
    print("  ✓ Correctly returned 0 results (parent name, not student name)")
else:
    print(f"  Found {len(results3)} result(s):")
    for s in results3:
        print(f"    - {s.name} (participant_id={s.participant_id})")


# ── Tests 4-6 use Veshant — need upcoming session IDs ────────────────────────
sep("TESTS 4-6 SETUP — Veshant upcoming sessions")
veshant, _ = resolve_student("Veshant Bhatia")
upcoming_v = get_student_upcoming_appointments(veshant.student_id, veshant.participant_id, days_ahead=60)
show_appointments(upcoming_v)

if len(upcoming_v) < 2:
    print("\n  Not enough upcoming sessions for write tests — skipping 4-6.")
else:
    session_4 = upcoming_v[0]  # first upcoming
    session_5 = upcoming_v[1]  # second upcoming
    session_6 = upcoming_v[-1] # last upcoming

    # ── Test 4: Move session_4 to next day same time (single) ────────────────
    sep(f"TEST 4 — Move single session ({session_4.start_time.strftime('%b %-d')}) → next day same time")
    from datetime import timedelta
    new_date = session_4.start_time + timedelta(days=1)
    new_date_str = new_date.strftime("%Y-%m-%d")

    from sites.mystudio.students import get_available_slots
    slots = get_available_slots(new_date_str)
    target_time = session_4.time_display()
    target_slot = next(
        (s for s in slots
         if s["class_title"] == session_4.appointment_type
         and s["start_time"].lstrip("0") == target_time),
        None,
    )

    if not target_slot:
        available_times = [s["start_time"] for s in slots if s["class_title"] == session_4.appointment_type]
        print(f"  No {session_4.appointment_type} slot at {target_time} on {new_date_str}.")
        print(f"  Available: {available_times}")
        print("  Skipping test 4.")
    else:
        print(f"  Moving: {session_4.start_time.strftime('%a %b %-d')} {target_time}")
        print(f"  To:     {new_date.strftime('%a %b %-d')} {target_time}  (slot {target_slot['class_appointment_times_id']})")
        confirm = input("\n  Proceed? (yes/no): ").strip().lower()
        if confirm == "yes":
            ok, msg = move_student_appointment(
                student_id=veshant.student_id,
                participant_id=veshant.participant_id,
                class_reg_id=session_4.id,
                class_registration_detail_id=session_4.registration_detail_id,
                class_appointment_id=session_4.class_appointment_id,
                class_appointment_times_id=session_4.class_appointment_times_id,
                program_date=session_4.start_time.strftime("%Y-%m-%d"),
                new_class_appointment_times_id=target_slot["class_appointment_times_id"],
                new_program_date=new_date_str,
                move_all_future=False,
            )
            print(f"  {'✓' if ok else '✗'} {msg}")
        else:
            print("  Skipped.")

    # ── Test 5: Move session_5 all future ────────────────────────────────────
    sep(f"TEST 5 — Move all future from {session_5.start_time.strftime('%b %-d')} → next day same time")
    new_date5 = session_5.start_time + timedelta(days=1)
    new_date5_str = new_date5.strftime("%Y-%m-%d")
    slots5 = get_available_slots(new_date5_str)
    target_slot5 = next(
        (s for s in slots5
         if s["class_title"] == session_5.appointment_type
         and s["start_time"].lstrip("0") == session_5.time_display()),
        None,
    )

    if not target_slot5:
        available_times5 = [s["start_time"] for s in slots5 if s["class_title"] == session_5.appointment_type]
        print(f"  No slot at {session_5.time_display()} on {new_date5_str}.")
        print(f"  Available: {available_times5}")
        print("  Skipping test 5.")
    else:
        print(f"  Moving all future from: {session_5.start_time.strftime('%a %b %-d')} {session_5.time_display()}")
        print(f"  To:                     {new_date5.strftime('%a %b %-d')} {session_5.time_display()}")
        confirm5 = input("\n  Proceed? (yes/no): ").strip().lower()
        if confirm5 == "yes":
            ok5, msg5 = move_student_appointment(
                student_id=veshant.student_id,
                participant_id=veshant.participant_id,
                class_reg_id=session_5.id,
                class_registration_detail_id=session_5.registration_detail_id,
                class_appointment_id=session_5.class_appointment_id,
                class_appointment_times_id=session_5.class_appointment_times_id,
                program_date=session_5.start_time.strftime("%Y-%m-%d"),
                new_class_appointment_times_id=target_slot5["class_appointment_times_id"],
                new_program_date=new_date5_str,
                move_all_future=True,
            )
            print(f"  {'✓' if ok5 else '✗'} {msg5}")
        else:
            print("  Skipped.")

    # ── Test 6: Cancel session_6 all future ──────────────────────────────────
    sep(f"TEST 6 — Cancel all future from {session_6.start_time.strftime('%b %-d')}")
    print(f"  Session: {session_6.start_time.strftime('%a %b %-d')} {session_6.time_display()} — {session_6.appointment_type}")
    print(f"  Scope:   this session and all future recurring")
    confirm6 = input("\n  Proceed? (yes/no): ").strip().lower()
    if confirm6 == "yes":
        ok6, msg6 = cancel_student_appointment(
            student_id=veshant.student_id,
            participant_id=veshant.participant_id,
            class_reg_id=session_6.id,
            class_registration_detail_id=session_6.registration_detail_id,
            class_appointment_id=session_6.class_appointment_id,
            class_appointment_times_id=session_6.class_appointment_times_id,
            selected_date=session_6.start_time.strftime("%Y-%m-%d"),
            cancel_all_future=True,
        )
        print(f"  {'✓' if ok6 else '✗'} {msg6}")
    else:
        print("  Skipped.")

print("\n\nAll tests complete.")

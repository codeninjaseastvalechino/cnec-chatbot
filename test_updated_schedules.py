#!/usr/bin/env python3
"""
Test MyStudio with no caching (fresh login every time).

Usage:
  MYSTUDIO_OTP=123456 python3 test_updated_schedules.py

Provide the 6-digit OTP from your email as environment variable.
"""

import sys
from sites.mystudio.schedules import get_todays_appointments

print("\n" + "="*70)
print("Testing MyStudio with NO CACHE (Fresh Login)")
print("="*70 + "\n")

try:
    appointments = get_todays_appointments()

    print(f"\n✅ Successfully fetched appointments")
    print(f"Total appointments: {len(appointments)}\n")

    if appointments:
        # Group by time slot
        from collections import defaultdict
        by_time = defaultdict(list)
        for apt in appointments:
            key = (apt.start_time, apt.appointment_type)
            by_time[key].append(apt)

        # Print all time slots
        for (start_time, class_type), students in sorted(by_time.items()):
            print(f"⏰ {start_time.strftime('%I:%M %p')} — {class_type} ({len(students)} students)")
            for apt in students:
                print(f"   • {apt.student_name} ({apt.rank}) — Parent: {apt.parent_name}")
            print()
        print("✅ TEST PASSED - Students retrieved successfully!")
    else:
        print("No appointments found (this is OK if no classes scheduled today)")
        print("✅ TEST PASSED - No error occurred")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

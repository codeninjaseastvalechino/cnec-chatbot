"""
Export GBS tours and student appointments to Excel format.

Usage:
    from export_tours import create_excel_file, create_unified_excel_file
    excel_path = await create_excel_file(sessions)
    excel_path = await create_unified_excel_file(gbs_sessions, appointments)
"""

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from datetime import datetime
from pathlib import Path
from typing import List, Union
import asyncio


async def create_excel_file(sessions, filename=None):
    """
    Create an Excel file with GBS tours.

    Args:
        sessions: List of GBSSession objects
        filename: Optional custom filename (default: tours_YYYY-MM-DD.xlsx)

    Returns:
        Path to the created Excel file
    """
    if not sessions:
        raise ValueError("No tours to export")

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Tours"

    # Define styles
    header_fill = PatternFill(start_color="0052CC", end_color="0052CC", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Set column widths (Time, Parent, Children, Tour Type, Assigned To)
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 25
    ws.column_dimensions['D'].width = 15
    ws.column_dimensions['E'].width = 20

    # Add headers
    headers = ['Time', 'Parent', 'Children', 'Tour Type', 'Assigned To']
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = border

    # Add data rows
    for row_num, session in enumerate(sessions, 2):
        # Time
        time_cell = ws.cell(row=row_num, column=1)
        time_cell.value = session.time_display()
        time_cell.border = border
        time_cell.alignment = Alignment(horizontal="center")

        # Student (Guardian)
        student_cell = ws.cell(row=row_num, column=2)
        student_cell.value = session.student_name
        student_cell.border = border

        # Children
        children_cell = ws.cell(row=row_num, column=3)
        children_text = ", ".join(session.child_display) if session.child_display else "N/A"
        children_cell.value = children_text
        children_cell.border = border

        # Tour Type
        tour_type_cell = ws.cell(row=row_num, column=4)
        tour_type_cell.value = session.tour_type
        tour_type_cell.border = border
        tour_type_cell.alignment = Alignment(horizontal="center")

        # Assigned To
        assigned_cell = ws.cell(row=row_num, column=5)
        assigned_cell.value = session.assignee_name
        assigned_cell.border = border

    # Set row height for header
    ws.row_dimensions[1].height = 25

    # Add summary at bottom
    summary_row = len(sessions) + 3
    ws.cell(row=summary_row, column=1).value = f"Total Tours: {len(sessions)}"
    ws.cell(row=summary_row, column=1).font = Font(bold=True)

    gbs_count = sum(1 for s in sessions if s.tour_type == "GBS")
    jrgbs_count = sum(1 for s in sessions if s.tour_type == "JR GBS")
    ws.cell(row=summary_row + 1, column=1).value = f"GBS: {gbs_count} | JR GBS: {jrgbs_count}"

    # Save file
    if not filename:
        date_str = sessions[0].date_display() if sessions else datetime.now().strftime("%Y-%m-%d")
        filename = f"tours_{date_str.replace(' ', '_')}.xlsx"

    export_dir = Path("exports")
    export_dir.mkdir(exist_ok=True)

    filepath = export_dir / filename
    wb.save(filepath)

    return str(filepath)


async def create_unified_excel_file(gbs_sessions, appointments, filename=None):
    """
    Create an Excel file with unified schedule (GBS tours + student appointments).

    Creates a single merged, time-ordered schedule with columns:
    Time | Student | Type | Duration | Instructor/Staff | Location | Notes

    Args:
        gbs_sessions: List of GBSSession objects
        appointments: List of StudentAppointment objects
        filename: Optional custom filename (default: schedule_YYYY-MM-DD.xlsx)

    Returns:
        Path to the created Excel file
    """
    if not gbs_sessions and not appointments:
        raise ValueError("No sessions or appointments to export")

    # Merge and sort by time
    items = []

    for session in gbs_sessions:
        # For GBS: student = child name with age, parent = guardian name
        child_names = ", ".join(session.child_display) if session.child_display else ""
        items.append({
            "time": session.start_time,
            "student": child_names,
            "type": session.tour_type,
            "belt": "",
            "parent": session.student_name,  # guardian
        })

    for appt in appointments:
        items.append({
            "time": appt.start_time,
            "student": appt.student_name,
            "type": appt.appointment_type,
            "belt": appt.rank,
            "parent": getattr(appt, "parent_name", "") or "",
        })

    # Sort by time — strip timezone info so naive and aware datetimes can be compared
    items.sort(key=lambda x: x["time"].astimezone().replace(tzinfo=None) if x["time"].tzinfo else x["time"])

    # Create workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Schedule"

    # Define styles
    header_fill = PatternFill(start_color="0052CC", end_color="0052CC", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # Set column widths: Time | Student | Type | Belt | Parent
    ws.column_dimensions['A'].width = 12  # Time
    ws.column_dimensions['B'].width = 22  # Student
    ws.column_dimensions['C'].width = 18  # Type
    ws.column_dimensions['D'].width = 15  # Belt
    ws.column_dimensions['E'].width = 22  # Parent

    # Add headers
    headers = ['Time', 'Student', 'Type', 'Belt', 'Parent']
    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = border

    # Add data rows
    for row_num, item in enumerate(items, 2):
        t = item["time"]
        if t.tzinfo is not None:
            t = t.astimezone()  # Convert UTC → local for GBS sessions

        # Time
        ws.cell(row=row_num, column=1).value = t.strftime("%I:%M %p").lstrip("0")
        ws.cell(row=row_num, column=1).border = border
        ws.cell(row=row_num, column=1).alignment = Alignment(horizontal="center")

        # Student
        ws.cell(row=row_num, column=2).value = item["student"]
        ws.cell(row=row_num, column=2).border = border

        # Type
        ws.cell(row=row_num, column=3).value = item["type"]
        ws.cell(row=row_num, column=3).border = border
        ws.cell(row=row_num, column=3).alignment = Alignment(horizontal="center")

        # Belt
        ws.cell(row=row_num, column=4).value = item["belt"]
        ws.cell(row=row_num, column=4).border = border
        ws.cell(row=row_num, column=4).alignment = Alignment(horizontal="center")

        # Parent
        ws.cell(row=row_num, column=5).value = item["parent"]
        ws.cell(row=row_num, column=5).border = border

    # Set row height for header
    ws.row_dimensions[1].height = 25

    # Add summary at bottom
    summary_row = len(items) + 3
    ws.cell(row=summary_row, column=1).value = f"Total: {len(items)} items"
    ws.cell(row=summary_row, column=1).font = Font(bold=True)

    gbs_count = sum(1 for s in gbs_sessions)
    appt_count = sum(1 for a in appointments)
    ws.cell(row=summary_row + 1, column=1).value = f"GBS Tours: {gbs_count} | Appointments: {appt_count}"

    # Save file
    if not filename:
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"schedule_{date_str}.xlsx"

    export_dir = Path("exports")
    export_dir.mkdir(exist_ok=True)

    filepath = export_dir / filename
    wb.save(filepath)

    return str(filepath)

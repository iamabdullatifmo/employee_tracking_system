
import calendar
from datetime import date

from flask import Blueprint, render_template, request
from sqlalchemy import func

from extentions import db
from models import Employee, Attendance


employer_bp = Blueprint(
    "employer",
    __name__,
    url_prefix="/employer"
)


def working_days_in_month(year, month):
    """Count Monday-Friday workdays in the reporting period."""
    today = date.today()
    last_day = calendar.monthrange(year, month)[1]

    # For the current month, do not count future working days.
    if year == today.year and month == today.month:
        last_day = today.day

    # For future months, there are no elapsed workdays yet.
    if date(year, month, 1) > today:
        return 0

    return sum(
        1
        for day in range(1, last_day + 1)
        if date(year, month, day).weekday() < 5
    )


@employer_bp.route("/", methods=["GET"])
def dashboard():
    today = date.today()

    # Read selected month and year from the URL.
    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))

        if not 1 <= month <= 12:
            raise ValueError

        if not 2000 <= year <= 2100:
            raise ValueError

    except (TypeError, ValueError):
        year = today.year
        month = today.month

    first_day = date(year, month, 1)
    last_day_number = calendar.monthrange(year, month)[1]
    last_day = date(year, month, last_day_number)

    # Only report attendance up to today for the current month.
    report_end = min(last_day, today) if first_day <= today else None

    employees = Employee.query.order_by(Employee.emp_name.asc()).all()

    workdays = working_days_in_month(year, month)

    employee_reports = []
    employee_percentages = []

    # Retrieve all attendance records for the selected month.
    if report_end:
        attendance_records = (
            db.session.query(Attendance, Employee)
            .join(Employee, Attendance.employee_id == Employee.id)
            .filter(
                Attendance.attendance_date >= first_day,
                Attendance.attendance_date <= report_end
            )
            .order_by(
                Attendance.attendance_date.desc(),
                Attendance.check_in_at.desc()
            )
            .all()
        )
    else:
        attendance_records = []

    # Count present days for each employee.
    present_counts = dict(
        db.session.query(
            Attendance.employee_id,
            func.count(func.distinct(Attendance.attendance_date))
        )
        .filter(
            Attendance.attendance_date >= first_day,
            Attendance.attendance_date <= report_end
            if report_end
            else Attendance.attendance_date < first_day,
            func.lower(Attendance.status) == "present"
        )
        .group_by(Attendance.employee_id)
        .all()
    )

    for employee in employees:
        present_days = present_counts.get(employee.id, 0)

        if workdays > 0:
            percentage = min((present_days / workdays) * 100, 100.0)
        else:
            percentage = 0.0

        employee_reports.append({
            "employee": employee,
            "present_days": present_days,
            "working_days": workdays,
            "percentage": round(percentage, 2)
        })

        employee_percentages.append(percentage)

    # Average the individual employees' percentages.
    average_percentage = (
        sum(employee_percentages) / len(employee_percentages)
        if employee_percentages
        else 0.0
    )

    return render_template(
        "employer.html",
        employees=employees,
        employee_reports=employee_reports,
        attendance_records=attendance_records,
        selected_month=month,
        selected_year=year,
        month_name=calendar.month_name[month],
        working_days=workdays,
        average_percentage=round(average_percentage, 2),
        total_employees=len(employees)
    )

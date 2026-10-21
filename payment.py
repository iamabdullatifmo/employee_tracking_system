from flask import Blueprint, render_template, request
from datetime import date, time
import calendar

from models import Employee, Salary, Attendance
from extentions import db

payment_bp = Blueprint("payment", __name__, url_prefix="/employer/salaries")


@payment_bp.route("/")
def salary_punctuality():
    today = date.today()

    month = request.args.get("month", today.month, type=int)
    year = request.args.get("year", today.year, type=int)

    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        return "Invalid month or year", 400

    days_in_month = calendar.monthrange(year, month)[1]
    work_start = time(8, 30)

    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)

    # Count weekdays up to today, excluding future dates.
    working_dates = [
        date(year, month, day)
        for day in range(1, days_in_month + 1)
        if date(year, month, day).weekday() < 5
        and date(year, month, day) <= today
    ]

    total_working_days = len(working_dates)
    employee_reports = []

    employees = Employee.query.order_by(Employee.emp_name).all()

    for employee in employees:
        salary_record = (
    Salary.query
    .filter_by(emp_id=employee.id)
    .order_by(Salary.created_at.desc(), Salary.id.desc())
    .first()
)

        monthly_salary = (
            float(salary_record.salary)
            if salary_record and salary_record.salary is not None
            else 0.0
        )

        records = Attendance.query.filter(
            Attendance.employee_id == employee.id,
            Attendance.attendance_date >= month_start,
            Attendance.attendance_date <= month_end
        ).all()

        # Count each date only once, even if duplicate records exist.
        punctual_dates = {
            record.attendance_date
            for record in records
            if record.attendance_date in working_dates
            and record.check_in_at
            and record.check_in_at.time() <= work_start
        }

        punctual_days = len(punctual_dates)

        punctuality = (
            round(punctual_days / total_working_days * 100, 2)
            if total_working_days
            else 0.0
        )

        deduction = (
            round(monthly_salary * 0.07, 2)
            if total_working_days > 0 and punctuality < 80
            else 0.0
        )

        employee_reports.append({
            "employee": employee,
            "salary": monthly_salary,
            "punctual_days": punctual_days,
            "working_days": total_working_days,
            "punctuality": punctuality,
            "deduction": deduction,
            "net_salary": round(monthly_salary - deduction, 2)
        })

    return render_template(
        "payment.html",
        employee_reports=employee_reports,
        selected_month=month,
        selected_year=year
    )
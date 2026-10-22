
from flask import Blueprint, render_template, request, redirect, url_for, flash
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from extentions import db
from models import Employee, Salary
import math

edit_employee_bp = Blueprint(
    "edit_employee",
    __name__,
    url_prefix="/employees"
)


def get_employment_type(employee):
    """Support either spelling if the model still uses the older field name."""
    if hasattr(employee, "employment_type"):
        return employee.employment_type or ""
    return getattr(employee, "empoloyment_type", "") or ""


def set_employment_type(employee, value):
    """Set the employment type using the field defined by the model."""
    if hasattr(employee, "employment_type"):
        employee.employment_type = value
    elif hasattr(employee, "empoloyment_type"):
        employee.empoloyment_type = value


def get_salary_record(employee):
    """Find the salary record associated with an employee."""
    return (
        Salary.query
        .filter_by(emp_id=employee.id)
        .order_by(Salary.id.desc())
        .first()
    )


@edit_employee_bp.route("/", methods=["GET"])
def employee_list():
    employees = Employee.query.order_by(Employee.id.desc()).all()

    # Keep the salary record separate from the Employee model.
    salary_by_employee = {
        employee.id: get_salary_record(employee)
        for employee in employees
    }

    employment_type_by_id = {
        employee.id: get_employment_type(employee)
        for employee in employees
    }

    return render_template(
        "edit_employees.html",
        employees=employees,
        salary_by_employee=salary_by_employee,
        employment_type_by_id=employment_type_by_id
    )


@edit_employee_bp.route("/edit/<int:employee_id>", methods=["GET", "POST"])
def edit_employee(employee_id):
    employee = db.session.get(Employee, employee_id)

    if employee is None:
        flash("Employee not found.", "error")
        return redirect(url_for("edit_employee.employee_list"))

    salary_record = get_salary_record(employee)

    if request.method == "POST":
        emp_name = request.form.get("emp_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        post = request.form.get("post", "").strip()
        employment_type = request.form.get("employment_type", "").strip()
        salary_text = request.form.get("salary", "").strip()

        # Validate required fields.
        if not all([emp_name, email, post, employment_type, salary_text]):
            flash("Please complete all fields.", "error")
            return redirect(
                url_for("edit_employee.edit_employee",
                        employee_id=employee.id)
            )

        # Validate salary.
        try:
            salary_amount = float(salary_text)
        except (TypeError, ValueError):
            flash("Enter a valid salary amount.", "error")
            return redirect(
                url_for("edit_employee.edit_employee",
                        employee_id=employee.id)
            )

        if not math.isfinite(salary_amount) or salary_amount < 0:
            flash("Salary must be a valid, non-negative amount.", "error")
            return redirect(
                url_for("edit_employee.edit_employee",
                        employee_id=employee.id)
            )

        # Check whether another employee already uses this email.
        existing_employee = Employee.query.filter(
            Employee.email == email,
            Employee.id != employee.id
        ).first()

        if existing_employee:
            flash("That email address belongs to another employee.", "error")
            return redirect(
                url_for("edit_employee.edit_employee",
                        employee_id=employee.id)
            )

        try:
            employee.emp_name = emp_name
            employee.email = email
            employee.post = post
            set_employment_type(employee, employment_type)

            # Update the salary record, or create one if it doesn't exist.
            if salary_record is None:
                salary_record = Salary(
                    emp_id=employee.id,
                    emp_name=emp_name,
                    email=email,
                    salary=salary_amount,
                    emp_pic=getattr(employee, "emp_pic", None)
                )
                db.session.add(salary_record)
            else:
                salary_record.emp_name = emp_name
                salary_record.email = email
                salary_record.salary = salary_amount
                salary_record.emp_pic = getattr(
                    employee, "emp_pic", None
                )

            db.session.commit()
            flash("Employee details and salary updated successfully.", "success")
            return redirect(url_for("edit_employee.employee_list"))

        except IntegrityError:
            db.session.rollback()
            flash(
                "The update conflicts with an existing email or database constraint.",
                "error"
            )
        except SQLAlchemyError:
            db.session.rollback()
            flash("A database error occurred. No changes were saved.", "error")

        return redirect(
            url_for("edit_employee.edit_employee", employee_id=employee.id)
        )

    return render_template(
        "edit_employee_form.html",
        employee=employee,
        salary_record=salary_record,
        employment_type=get_employment_type(employee)
    )


@edit_employee_bp.route("/delete/<int:employee_id>", methods=["POST"])
def delete_employee(employee_id):
    employee = db.session.get(Employee, employee_id)

    if employee is None:
        flash("Employee not found.", "error")
        return redirect(url_for("edit_employee.employee_list"))

    try:
        # Delete salary records belonging to this employee first.
        Salary.query.filter_by(emp_id=employee.id).delete(
            synchronize_session=False
        )

        db.session.delete(employee)
        db.session.commit()

        flash("Employee and their salary records were deleted.", "success")

    except IntegrityError:
        db.session.rollback()
        flash(
            "This employee has related records, such as attendance or forum "
            "posts, that prevent deletion. Preserve those records or handle "
            "their relationships before deleting the employee.",
            "error"
        )
    except SQLAlchemyError:
        db.session.rollback()
        flash("A database error occurred. The employee was not deleted.", "error")

    return redirect(url_for("edit_employee.employee_list"))

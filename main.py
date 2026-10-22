import os
import math
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    request,
    url_for,
    flash,
    redirect,
    render_template
)

from extentions import db
from models import Employee, Salary

from empl_checker import attendance_bp
from employer import employer_bp
from forum import forum_bp
from payment import payment_bp
from edit_employee import edit_employee_bp

# Load configuration
config_path = Path(__file__).resolve().parent / "config.env"
load_dotenv(config_path)

# Create Flask application
app = Flask(__name__)

# Application configuration
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# Ensure required configuration exists
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is missing from config.env")

if not app.config["SQLALCHEMY_DATABASE_URI"]:
    raise RuntimeError("DATABASE_URL is missing from config.env")

# Initialize the shared database instance
db.init_app(app)

# Register attendance routes
app.register_blueprint(attendance_bp)
app.register_blueprint(employer_bp)
app.register_blueprint(forum_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(edit_employee_bp)


@app.route("/")
def index():
    return redirect(url_for("employer.dashboard"))


@app.route("/register", methods=["GET", "POST"])
def home():
    if request.method == "POST":

        emp_name = request.form.get("emp_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        post = request.form.get("post", "").strip()
        salary_input = request.form.get("salary", "").strip()
        employment_type = request.form.get(
            "employment_type", ""
        ).strip()

        # Validate required fields
        if not all([
            emp_name,
            email,
            post,
            salary_input,
            employment_type
        ]):
            flash("All fields are required.", "error")
            return redirect(url_for("home"))

        # Validate salary
        try:
            salary = float(salary_input)

            if not math.isfinite(salary) or salary <= 0:
                flash(
                    "Salary must be a valid number greater than zero.",
                    "error"
                )
                return redirect(url_for("home"))

        except ValueError:
            flash("Please enter a valid salary.", "error")
            return redirect(url_for("home"))

        # Register employee and salary
        try:
            emp = Employee(
                emp_name=emp_name,
                email=email,
                post=post,
                employment_type=employment_type
            )

            db.session.add(emp)

            # Generate employee ID before creating salary record
            db.session.flush()

            salary_record = Salary(
                emp_id=emp.id,
                salary=salary
            )

            db.session.add(salary_record)
            db.session.commit()

            flash(
                f"{emp_name} has been successfully enrolled!",
                "success"
            )

            return redirect(url_for("home"))

        except Exception:
            db.session.rollback()
            app.logger.exception("Employee enrolment failed")

            flash(
                "Unable to enrol employee. Please check the details "
                "and try again.",
                "error"
            )

            return redirect(url_for("home"))

    return render_template("main.html")


@app.route("/about")
def about():
    return "About page"

@app.route("/attendance-portal")
def attendance_portal():
    return render_template("empl_checker.html")


if __name__ == "__main__":
    app.run(debug=True,host="127.0.0.1",port=5000)

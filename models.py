from extentions import db
from datetime import datetime


class Employee(db.Model):
    __tablename__ = "employee"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    emp_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    emp_pic = db.Column(db.String(255))
    password = db.Column(db.String(255))
    post = db.Column(db.String(100), nullable=False)
    employment_type = db.Column(db.String(100), nullable=False)
    salary_details = db.relationship("Salary",backref="employee",lazy=True)
    profile_pic = db.Column(db.String(255))


class Salary(db.Model):
    __tablename__ = "salary"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    emp_id = db.Column(db.Integer,db.ForeignKey("employee.id"),nullable=False)
    salary = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CompanyLocation(db.Model):
    __tablename__ = "company_location"

    id = db.Column(db.Integer,primary_key=True,autoincrement=True)
    company_name = db.Column(db.String(150),nullable=False)
    latitude = db.Column(db.Numeric(10, 7),nullable=False)
    longitude = db.Column(db.Numeric(10, 7),nullable=False)
    allowed_radius_m = db.Column(db.Integer,nullable=False,default=100)
    created_at = db.Column( db.DateTime,default=datetime.utcnow,nullable=False)

class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer,primary_key=True, autoincrement=True)
    employee_id = db.Column(db.Integer,db.ForeignKey("employee.id", ondelete="CASCADE"),nullable=False)
    attendance_date = db.Column(db.Date,nullable=False)
    status = db.Column(db.String(20),nullable=False,default="Present")
    check_in_at = db.Column(db.DateTime,nullable=False,default=datetime.utcnow)
    latitude = db.Column(db.Numeric(10, 7),nullable=False)
    longitude = db.Column(db.Numeric(10, 7),nullable=False)
    distance_m = db.Column(db.Numeric(10, 2),nullable=False)

    __table_args__ = (db.UniqueConstraint("employee_id","attendance_date",name="uq_employee_attendance_date"),)


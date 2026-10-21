import json
import math
import os
import uuid
from datetime import date, datetime

from flask import Blueprint, request, session, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy.exc import SQLAlchemyError

from extentions import db
from models import Employee, CompanyLocation, Attendance


attendance_bp = Blueprint(
    "attendance",
    __name__,
    url_prefix="/attendance"
)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# Tune this threshold after testing with real employees.
FACE_MATCH_THRESHOLD = 0.50


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def json_error(message, status=400):
    return jsonify({
        "success": False,
        "message": message
    }), status


def parse_descriptor(value):
    """
    Validate a face-api.js face descriptor.
    face-api.js normally returns 128 numeric values.
    """
    if not isinstance(value, list) or len(value) != 128:
        return None

    try:
        descriptor = [float(v) for v in value]
    except (TypeError, ValueError):
        return None

    if not all(math.isfinite(v) for v in descriptor):
        return None

    return descriptor


def descriptor_distance(first, second):
    """Calculate Euclidean distance between two face descriptors."""
    return math.sqrt(
        sum((a - b) ** 2 for a, b in zip(first, second))
    )


def current_pending_employee():
    """
    Return the employee who passed password authentication
    but has not yet completed face authentication.
    """
    employee_id = session.get("pending_face_employee_id")

    if not employee_id:
        return None

    return db.session.get(Employee, employee_id)


# --------------------------------------------------
# 1. EMPLOYEE LOGIN
# --------------------------------------------------

@attendance_bp.route("/login", methods=["POST"])
def employee_login():
    data = request.get_json(silent=True) or {}

    employee_id = str(data.get("employee_id", "")).strip()
    full_name = str(data.get("full_name", "")).strip()

    if not employee_id or not full_name:
        return json_error(
            "Employee ID and full name are required."
        )

    try:
        employee_id = int(employee_id)
    except (ValueError, TypeError):
        return json_error("Enter a valid employee ID.")

    employee = db.session.get(Employee, employee_id)

    if (
        employee is None
        or (employee.emp_name or "").strip().casefold()
        != full_name.casefold()
    ):
        return json_error(
            "Employee ID or full name is incorrect.",
            401
        )

    # First-time users must create a password.
    if not employee.password:
        session.clear()
        session["pending_password_employee_id"] = employee.id

        return jsonify({
            "success": True,
            "needs_password_setup": True,
            "message": "Create your password to continue."
        })

    password = data.get("password", "")

    if not isinstance(password, str) or not password:
        return jsonify({
            "success": True,
            "needs_password": True,
            "message": "Enter your password."
        })

    try:
        valid_password = check_password_hash(
            employee.password,
            password
        )
    except (ValueError, TypeError):
        valid_password = False

    if not valid_password:
        return json_error(
            "Invalid employee ID, name or password.",
            401
        )

    # Password passed, but the employee is NOT fully signed in yet.
    session.clear()
    session["pending_face_employee_id"] = employee.id

    return jsonify({
        "success": True,
        "authenticated": False,
        "needs_face_auth": True,
        "face_enrolled": bool(employee.emp_pic),
        "message": (
            "Verify your face to finish signing in."
            if employee.emp_pic
            else "Enroll your face to finish signing in."
        ),
        "employee": {
            "id": employee.id,
            "name": employee.emp_name
        }
    })


# --------------------------------------------------
# 2. FIRST-TIME PASSWORD SETUP
# --------------------------------------------------

@attendance_bp.route("/setup-password", methods=["POST"])
def setup_password():
    pending_id = session.get("pending_password_employee_id")

    if not pending_id:
        return json_error(
            "Please verify your employee ID and name first.",
            401
        )

    data = request.get_json(silent=True) or {}

    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")

    if (
        not isinstance(password, str)
        or not isinstance(confirm_password, str)
    ):
        return json_error("Invalid password information.")

    if len(password) < 8:
        return json_error(
            "Password must be at least 8 characters long."
        )

    if password != confirm_password:
        return json_error("Passwords do not match.")

    try:
        employee = db.session.get(Employee, pending_id)

        if employee is None:
            session.clear()
            return json_error(
                "Employee account was not found.",
                404
            )

        # Prevent overwriting an existing password through setup.
        if employee.password:
            session.clear()
            return json_error(
                "A password already exists. Please sign in.",
                409
            )

        employee.password = generate_password_hash(password)
        db.session.commit()

        # Require face enrollment/verification after password setup.
        session.clear()
        session["pending_face_employee_id"] = employee.id

        return jsonify({
            "success": True,
            "authenticated": False,
            "needs_face_auth": True,
            "face_enrolled": bool(employee.emp_pic),
            "message": (
                "Password created. Now enroll or verify your face."
            ),
            "employee": {
                "id": employee.id,
                "name": employee.emp_name
            }
        })

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Password setup failed")

        return json_error(
            "Unable to save your password. Please try again.",
            500
        )


# --------------------------------------------------
# 3. CHECK FACE-ENROLLMENT STATUS
# --------------------------------------------------

@attendance_bp.route("/face-status", methods=["GET"])
def face_status():
    employee = current_pending_employee()

    if employee is None:
        return json_error(
            "Please complete password sign-in first.",
            401
        )

    return jsonify({
        "success": True,
        "enrolled": bool(employee.emp_pic),
        "employee": {
            "id": employee.id,
            "name": employee.emp_name
        }
    })


# --------------------------------------------------
# 4. FIRST-TIME FACE ENROLLMENT
# Employee.emp_pic stores the face descriptor JSON.
# --------------------------------------------------

@attendance_bp.route("/face-enroll", methods=["POST"])
def face_enroll():
    employee = current_pending_employee()

    if employee is None:
        return json_error(
            "Please complete password sign-in first.",
            401
        )

    if employee.emp_pic:
        return json_error(
            "A face is already enrolled. Use face verification instead.",
            409
        )

    data = request.get_json(silent=True) or {}

    descriptor = parse_descriptor(data.get("descriptor"))

    if descriptor is None:
        return json_error(
            "A valid face descriptor is required."
        )

    try:
        # Save the face descriptor, not a profile-picture path.
        employee.emp_pic = json.dumps(
            descriptor,
            separators=(",", ":")
        )

        db.session.commit()

        # Only now grant the authenticated session.
        session.pop("pending_face_employee_id", None)
        session.pop("pending_password_employee_id", None)
        session["employee_id"] = employee.id

        return jsonify({
            "success": True,
            "authenticated": True,
            "message": (
                "Face enrolled successfully. You are signed in."
            ),
            "employee": {
                "id": employee.id,
                "name": employee.emp_name
            }
        })

    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Face enrollment failed")

        return json_error(
            "Could not save face data. Please try again.",
            500
        )


# --------------------------------------------------
# 5. FACE VERIFICATION ON FUTURE SIGN-INS
# --------------------------------------------------

@attendance_bp.route("/face-verify", methods=["POST"])
def face_verify():
    employee = current_pending_employee()

    if employee is None:
        return json_error(
            "Please complete password sign-in first.",
            401
        )

    if not employee.emp_pic:
        return json_error(
            "No face is enrolled. Enroll your face first.",
            409
        )

    data = request.get_json(silent=True) or {}

    live_descriptor = parse_descriptor(
        data.get("descriptor")
    )

    if live_descriptor is None:
        return json_error(
            "A valid face descriptor is required."
        )

    try:
        saved_descriptor = json.loads(employee.emp_pic)
        saved_descriptor = parse_descriptor(saved_descriptor)

    except (TypeError, ValueError, json.JSONDecodeError):
        saved_descriptor = None

    if saved_descriptor is None:
        current_app.logger.error(
            "Invalid saved face descriptor for employee %s",
            employee.id
        )

        return json_error(
            "Saved face data is invalid. Contact an administrator.",
            500
        )

    distance = descriptor_distance(
        saved_descriptor,
        live_descriptor
    )

    if distance > FACE_MATCH_THRESHOLD:
        return json_error(
            "Face not recognized. Please try again.",
            401
        )

    # Face matched: complete authentication.
    session.pop("pending_face_employee_id", None)
    session.pop("pending_password_employee_id", None)
    session["employee_id"] = employee.id

    return jsonify({
        "success": True,
        "authenticated": True,
        "message": "Face verified. You are signed in.",
        "employee": {
            "id": employee.id,
            "name": employee.emp_name
        }
    })


# --------------------------------------------------
# 6. LOGOUT
# --------------------------------------------------

@attendance_bp.route("/logout", methods=["POST"])
def employee_logout():
    session.clear()

    return jsonify({
        "success": True,
        "message": "Logged out successfully."
    })


# --------------------------------------------------
# 7. GET CURRENT AUTHENTICATED EMPLOYEE
# --------------------------------------------------

@attendance_bp.route("/me", methods=["GET"])
def authenticated_employee():
    employee_id = session.get("employee_id")

    if not employee_id:
        return json_error(
            "Please sign in and verify your face first.",
            401
        )

    employee = db.session.get(Employee, employee_id)

    if employee is None:
        session.clear()
        return json_error(
            "Employee account not found.",
            401
        )

    return jsonify({
        "success": True,
        "employee": {
            "id": employee.id,
            "name": employee.emp_name,
            "profile_pic": employee.profile_pic
        }
    })


# --------------------------------------------------
# 8. UPLOAD PROFILE PICTURE
# IMPORTANT: This uses profile_pic, never emp_pic.
# --------------------------------------------------

@attendance_bp.route("/profile-picture", methods=["POST"])
def upload_profile_picture():
    employee_id = session.get("employee_id")

    if not employee_id:
        return json_error(
            "Sign in and verify your face first.",
            401
        )

    employee = db.session.get(Employee, employee_id)

    if employee is None:
        return json_error(
            "Employee account not found.",
            404
        )

    uploaded = request.files.get("profile_pic")

    if not uploaded or not uploaded.filename:
        return json_error("Choose a profile picture.")

    filename = secure_filename(uploaded.filename)

    extension = (
        filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return json_error(
            "Use JPG, JPEG, PNG or WEBP images."
        )

    upload_folder = os.path.join(
        current_app.static_folder,
        "uploads",
        "profiles"
    )

    os.makedirs(upload_folder, exist_ok=True)

    saved_name = (
        f"employee_{employee.id}_{uuid.uuid4().hex}.{extension}"
    )

    saved_path = os.path.join(
        upload_folder,
        saved_name
    )

    try:
        uploaded.save(saved_path)

        # Save the profile photo path separately.
        employee.profile_pic = (
            f"uploads/profiles/{saved_name}"
        )

        db.session.commit()

    except SQLAlchemyError:
        db.session.rollback()

        if os.path.exists(saved_path):
            os.remove(saved_path)

        current_app.logger.exception(
            "Profile picture upload failed"
        )

        return json_error(
            "Could not save profile picture.",
            500
        )

    return jsonify({
        "success": True,
        "message": "Profile picture updated.",
        "image_url": f"/static/{employee.profile_pic}"
    })


# --------------------------------------------------
# 9. GPS DISTANCE CALCULATION
# --------------------------------------------------

def calculate_distance(lat1, lon1, lat2, lon2):
    earth_radius = 6_371_000

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    a = max(0.0, min(1.0, a))

    return earth_radius * 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


# --------------------------------------------------
# 10. GPS ATTENDANCE CHECK-IN
# Only a fully authenticated employee can check in.
# --------------------------------------------------

@attendance_bp.route("/check-in", methods=["POST"])
def check_in():
    employee_id = session.get("employee_id")

    if not employee_id:
        return json_error(
            "Complete password sign-in and face verification first.",
            401
        )

    data = request.get_json(silent=True) or {}

    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))

        if not (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            raise ValueError

    except (TypeError, ValueError):
        return json_error(
            "Valid GPS coordinates are required."
        )

    try:
        employee = db.session.get(Employee, employee_id)

        if employee is None or not employee.password:
            session.clear()

            return json_error(
                "Please sign in again.",
                401
            )

        company = (
            CompanyLocation.query
            .order_by(CompanyLocation.id.asc())
            .first()
        )

        if company is None:
            return json_error(
                "Company location has not been configured.",
                503
            )

        distance = calculate_distance(
            latitude,
            longitude,
            company.latitude,
            company.longitude
        )

        if distance > company.allowed_radius_m:
            return jsonify({
                "success": False,
                "status": "Outside workplace",
                "distance_metres": round(distance, 2),
                "message": (
                    "You are outside the permitted workplace area."
                )
            }), 403

        today = date.today()

        existing = Attendance.query.filter_by(
            employee_id=employee.id,
            attendance_date=today
        ).first()

        if existing:
            return jsonify({
                "success": True,
                "status": existing.status,
                "message": (
                    "Your attendance has already been recorded today."
                )
            })

        attendance = Attendance(
            employee_id=employee.id,
            attendance_date=today,
            status="Present",
            check_in_at=datetime.now(),
            latitude=latitude,
            longitude=longitude,
            distance_m=round(distance, 2)
        )

        db.session.add(attendance)
        db.session.commit()

        return jsonify({
            "success": True,
            "status": "Present",
            "distance_metres": round(distance, 2),
            "message": (
                "GPS verified. You have been marked Present."
            )
        }), 201

    except SQLAlchemyError:
        db.session.rollback()

        current_app.logger.exception(
            "Attendance check-in failed"
        )

        return json_error(
            "A database error occurred. Please try again.",
            500
        )
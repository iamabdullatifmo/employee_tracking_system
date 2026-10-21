
import os
import uuid
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, current_app
)
from werkzeug.utils import secure_filename

from extentions import db
from models import Employee, ForumPost


forum_bp = Blueprint("forum", __name__, url_prefix="/forum")

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "m4a", "webm"}


def allowed_file(filename):
    if "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()
    return extension in IMAGE_EXTENSIONS | AUDIO_EXTENSIONS


def get_current_employee():
    employee_id = session.get("employee_id")

    if not employee_id:
        return None

    return db.session.get(Employee, employee_id)


@forum_bp.route("/", methods=["GET", "POST"])
def feed():
    employee = get_current_employee()

    if employee is None:
        flash("Please log in to access the employee forum.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        uploaded_file = request.files.get("media")
        media_path = None
        media_type = None

        if not message and (
            not uploaded_file or not uploaded_file.filename
        ):
            flash("Write a message or attach a picture/audio file.", "warning")
            return redirect(url_for("forum.feed"))

        if uploaded_file and uploaded_file.filename:
            original_name = secure_filename(uploaded_file.filename)

            if not original_name or not allowed_file(original_name):
                flash(
                    "Unsupported file. Upload an image or audio file.",
                    "danger"
                )
                return redirect(url_for("forum.feed"))

            extension = original_name.rsplit(".", 1)[1].lower()

            if extension in IMAGE_EXTENSIONS:
                media_type = "image"
            elif extension in AUDIO_EXTENSIONS:
                media_type = "audio"
            else:
                flash("Unsupported media type.", "danger")
                return redirect(url_for("forum.feed"))

            upload_folder = os.path.join(
                current_app.root_path,
                "static", "uploads", "forum"
            )
            os.makedirs(upload_folder, exist_ok=True)

            # Generate a unique filename rather than trusting the upload name.
            new_filename = f"{uuid.uuid4().hex}.{extension}"
            uploaded_file.save(os.path.join(upload_folder, new_filename))

            media_path = f"uploads/forum/{new_filename}"

        post = ForumPost(
            employee_id=employee.id,
            message=message,
            media_path=media_path,
            media_type=media_type,
        )

        try:
            db.session.add(post)
            db.session.commit()
            flash("Your post has been published.", "success")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not save forum post")
            flash("We couldn't publish your post. Please try again.", "danger")

        return redirect(url_for("forum.feed"))

    posts = ForumPost.query.order_by(ForumPost.created_at.desc()).all()

    return render_template(
        "forum.html",
        employee=employee,
        posts=posts
    )


@forum_bp.route("/delete/<int:post_id>", methods=["POST"])
def delete_post(post_id):
    employee = get_current_employee()

    if employee is None:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    post = db.session.get(ForumPost, post_id)

    if post is None:
        flash("Post not found.", "warning")
        return redirect(url_for("forum.feed"))

    # Employees can delete only their own posts.
    if post.employee_id != employee.id:
        flash("You cannot delete another employee's post.", "danger")
        return redirect(url_for("forum.feed"))

    # Remove the uploaded media file, if one exists.
    if post.media_path:
        media_file = os.path.join(
            current_app.root_path, "static", post.media_path
        )
        try:
            if os.path.isfile(media_file):
                os.remove(media_file)
        except OSError:
            current_app.logger.exception("Could not delete forum media")

    try:
        db.session.delete(post)
        db.session.commit()
        flash("Your post has been deleted.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not delete forum post")
        flash("Unable to delete the post right now.", "danger")

    return redirect(url_for("forum.feed"))

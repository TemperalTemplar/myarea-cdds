"""
Merit Badge Importer — CDDS route.
Accepts PDF or DOCX merit badge worksheet, parses it, creates Course + Modules.
"""
import os
import uuid as uuid_mod
from flask import (Blueprint, render_template, redirect, url_for,
                   session, flash, request, current_app)
from werkzeug.utils import secure_filename
from slugify import slugify
from ..models import Course, Module, User
from .. import db
from ..auth.oidc import login_required

merit_badge_bp = Blueprint("merit_badge", __name__, url_prefix="/merit-badge")

ALLOWED_EXT = {".pdf", ".docx", ".doc"}


@merit_badge_bp.route("/import", methods=["GET", "POST"])
@login_required
def import_worksheet():
    if request.method == "POST":
        f = request.files.get("worksheet")
        if not f or not f.filename:
            flash("No file selected.", "danger")
            return render_template("merit_badge/import.html")

        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            flash("Only PDF, DOCX, and DOC files are supported.", "danger")
            return render_template("merit_badge/import.html")

        # Save upload
        imports_dir = current_app.config["IMPORTS_DIR"]
        uid         = str(uuid_mod.uuid4())[:8]
        save_path   = os.path.join(imports_dir, f"{uid}_{secure_filename(f.filename)}")
        f.save(save_path)

        try:
            from ..utils.merit_badge_parser import parse_merit_badge_worksheet
            data   = parse_merit_badge_worksheet(save_path)
            user   = User.query.get(session["user_id"])
            course = _create_course(data, user)

            flash(
                f"'{course.title}' imported with {data['req_count']} requirements "
                f"(parsed by {data['parser_method']}). Review and publish when ready.",
                "success"
            )
            return redirect(url_for("courses.edit_course", slug=course.slug))

        except Exception as exc:
            flash(f"Import failed: {exc}", "danger")
            return render_template("merit_badge/import.html")

    return render_template("merit_badge/import.html")


def _create_course(data: dict, user: User) -> Course:
    """Create Course + Modules from parsed merit badge data."""

    # Unique slug
    slug = slugify(data["title"])
    base, n = slug, 1
    while Course.query.filter_by(slug=slug).first():
        slug = f"{base}-{n}"; n += 1

    course = Course(
        title       = data["title"],
        slug        = slug,
        description = data["description"],
        category    = data["category"],
        tags        = ",".join(data["tags"]),
        version     = data["version"],
        author_id   = user.id,
        is_published= False,
    )
    db.session.add(course)
    db.session.flush()

    for req in data["requirements"]:
        content = _format_requirement(req)
        module  = Module(
            course_id = course.id,
            title     = f"Requirement {req['number']}: {req['title']}",
            position  = int(req["number"]) if req["number"].isdigit() else len(data["requirements"]),
            content   = content,
        )
        db.session.add(module)

    db.session.commit()
    return course


def _format_requirement(req: dict) -> str:
    """Format a requirement as Markdown module content."""
    lines = [f"## Requirement {req['number']}", "", req["content"], ""]

    if req.get("sub_requirements"):
        for sub in req["sub_requirements"]:
            lines.append(f"### Part {sub['letter'].upper()}")
            lines.append(sub["content"])
            lines.append("")

    lines += [
        "---",
        "### Your Response",
        "_Record your notes, observations, and work here as you complete this requirement._",
        "",
        "### Counselor Notes",
        "_For counselor use only._",
    ]

    return "\n".join(lines)

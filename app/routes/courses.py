import os
from flask import (Blueprint, render_template, redirect, url_for,
                   session, flash, request, abort, send_file, current_app)
from slugify import slugify
from ..models import Course, Module, User
from .. import db
from ..auth.oidc import login_required
from ..utils.packager import build_package
from ..api.notifications import push

courses_bp = Blueprint("courses", __name__, url_prefix="/courses")


@courses_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_course():
    if request.method == "POST":
        title       = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category    = request.form.get("category", "").strip()
        tags        = request.form.get("tags", "").strip()
        license_txt = request.form.get("license", "").strip()

        if not title:
            flash("Title is required.", "danger")
            return render_template("courses/new.html")

        slug = slugify(title)
        # ensure unique slug
        base, n = slug, 1
        while Course.query.filter_by(slug=slug).first():
            slug = f"{base}-{n}"; n += 1

        user   = User.query.get(session["user_id"])
        course = Course(
            title=title, slug=slug, description=description,
            category=category, tags=tags, license=license_txt,
            author=user,
        )
        db.session.add(course)
        db.session.commit()
        flash("Course created.", "success")
        return redirect(url_for("courses.edit_course", slug=course.slug))

    return render_template("courses/new.html")


@courses_bp.route("/<slug>")
@login_required
def view_course(slug):
    course = Course.query.filter_by(slug=slug).first_or_404()
    return render_template("courses/view.html", course=course)


@courses_bp.route("/<slug>/edit", methods=["GET", "POST"])
@login_required
def edit_course(slug):
    course = Course.query.filter_by(slug=slug).first_or_404()
    user   = User.query.get(session["user_id"])

    if course.author_id != user.id and not user.is_admin:
        abort(403)

    if request.method == "POST":
        course.title       = request.form.get("title", course.title).strip()
        course.description = request.form.get("description", "").strip()
        course.category    = request.form.get("category", "").strip()
        course.tags        = request.form.get("tags", "").strip()
        course.license     = request.form.get("license", "").strip()
        course.version     = request.form.get("version", course.version).strip()
        db.session.commit()
        flash("Course updated.", "success")
        return redirect(url_for("courses.edit_course", slug=course.slug))

    return render_template("courses/edit.html", course=course)


@courses_bp.route("/<slug>/modules/add", methods=["POST"])
@login_required
def add_module(slug):
    course = Course.query.filter_by(slug=slug).first_or_404()
    user   = User.query.get(session["user_id"])

    if course.author_id != user.id and not user.is_admin:
        abort(403)

    title   = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()

    if not title:
        flash("Module title required.", "danger")
        return redirect(url_for("courses.edit_course", slug=slug))

    position = db.session.query(db.func.max(Module.position)).filter_by(
        course_id=course.id).scalar() or 0

    module = Module(course=course, title=title,
                    content=content, position=position + 1)
    db.session.add(module)
    db.session.commit()
    flash("Module added.", "success")
    return redirect(url_for("courses.edit_course", slug=slug))


@courses_bp.route("/<slug>/modules/<int:module_id>/edit", methods=["GET", "POST"])
@login_required
def edit_module(slug, module_id):
    course = Course.query.filter_by(slug=slug).first_or_404()
    module = Module.query.get_or_404(module_id)
    user   = User.query.get(session["user_id"])

    if course.author_id != user.id and not user.is_admin:
        abort(403)

    if request.method == "POST":
        module.title   = request.form.get("title", module.title).strip()
        module.content = request.form.get("content", "").strip()
        db.session.commit()
        flash("Module saved.", "success")
        return redirect(url_for("courses.edit_course", slug=slug))

    return render_template("courses/edit_module.html", course=course, module=module)


@courses_bp.route("/<slug>/publish", methods=["POST"])
@login_required
def publish_course(slug):
    course = Course.query.filter_by(slug=slug).first_or_404()
    user   = User.query.get(session["user_id"])

    if course.author_id != user.id and not user.is_admin:
        abort(403)

    if not course.modules.count() if hasattr(course.modules, 'count') else not course.modules:
        flash("Add at least one module before publishing.", "warning")
        return redirect(url_for("courses.edit_course", slug=slug))

    # Build the .cdpkg
    filename, sha256, size = build_package(course)
    course.package_file  = filename
    course.package_hash  = sha256
    course.package_size  = size
    course.is_published  = True
    db.session.commit()

    flash(f"Course published and packaged. SHA-256: {sha256[:16]}…", "success")
    return redirect(url_for("courses.view_course", slug=slug))


@courses_bp.route("/<slug>/download")
@login_required
def download_package(slug):
    """Direct download for admins/authors — not the federation endpoint."""
    course = Course.query.filter_by(slug=slug, is_published=True).first_or_404()
    user   = User.query.get(session["user_id"])

    if course.author_id != user.id and not user.is_admin:
        abort(403)

    pkg_path = os.path.join(current_app.config["PACKAGES_DIR"], course.package_file)
    if not os.path.exists(pkg_path):
        flash("Package file not found. Try republishing.", "danger")
        return redirect(url_for("courses.view_course", slug=slug))

    return send_file(pkg_path, as_attachment=True,
                     download_name=f"{course.slug}-{course.version}.cdpkg")

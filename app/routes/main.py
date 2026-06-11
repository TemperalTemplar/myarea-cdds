from flask import Blueprint, render_template, session, redirect, url_for
from ..models import Course
from ..auth.oidc import login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    courses = Course.query.filter_by(is_published=True).order_by(
        Course.updated_at.desc()).limit(12).all()
    return render_template("index.html", courses=courses)


@main_bp.route("/catalog")
@login_required
def catalog():
    q        = Course.query.filter_by(is_published=True)
    category = None
    courses  = q.order_by(Course.updated_at.desc()).all()
    categories = Course.query.with_entities(Course.category).distinct().all()
    categories = [c[0] for c in categories if c[0]]
    return render_template("catalog.html", courses=courses,
                           categories=categories, active_category=category)

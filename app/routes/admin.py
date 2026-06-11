from flask import (Blueprint, render_template, redirect, url_for,
                   session, flash, request)
from ..models import User, Course, FederationToken, IssueRecord
from .. import db
from ..auth.oidc import admin_required
from ..api.notifications import push

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@admin_required
def index():
    users   = User.query.order_by(User.created_at.desc()).all()
    courses = Course.query.order_by(Course.created_at.desc()).all()
    tokens  = FederationToken.query.order_by(FederationToken.created_at.desc()).all()
    issues  = IssueRecord.query.order_by(IssueRecord.issued_at.desc()).limit(20).all()
    return render_template("admin/index.html",
                           users=users, courses=courses,
                           tokens=tokens, issues=issues)


# ── Federation token management ───────────────────────────────────────────

@admin_bp.route("/tokens/new", methods=["GET", "POST"])
@admin_required
def new_token():
    if request.method == "POST":
        label      = request.form.get("label", "").strip()
        remote_url = request.form.get("remote_url", "").strip()
        remote_node= request.form.get("remote_node", "").strip()

        if not label:
            flash("Label is required.", "danger")
            return render_template("admin/new_token.html")

        user  = User.query.get(session["user_id"])
        token = FederationToken(
            label=label,
            remote_url=remote_url,
            remote_node=remote_node,
            created_by=user,
        )
        db.session.add(token)
        db.session.commit()

        flash(f"Token created: {token.token}", "success")
        return redirect(url_for("admin.index"))

    return render_template("admin/new_token.html")


@admin_bp.route("/tokens/<int:token_id>/revoke", methods=["POST"])
@admin_required
def revoke_token(token_id):
    token = FederationToken.query.get_or_404(token_id)
    token.is_active = False
    db.session.commit()
    flash(f"Token '{token.label}' revoked. Past pulls are unaffected.", "warning")
    return redirect(url_for("admin.index"))


@admin_bp.route("/tokens/<int:token_id>/restore", methods=["POST"])
@admin_required
def restore_token(token_id):
    token = FederationToken.query.get_or_404(token_id)
    token.is_active = True
    db.session.commit()
    flash(f"Token '{token.label}' restored.", "success")
    return redirect(url_for("admin.index"))


# ── User management ───────────────────────────────────────────────────────

@admin_bp.route("/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    # Prevent self-demotion
    if user.id == session["user_id"]:
        flash("Cannot change your own admin status.", "danger")
        return redirect(url_for("admin.index"))
    user.is_admin = not user.is_admin
    db.session.commit()
    state = "granted" if user.is_admin else "revoked"
    flash(f"Admin {state} for {user.username}.", "success")
    return redirect(url_for("admin.index"))

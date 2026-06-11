from datetime import datetime, timezone, timedelta
from flask import (Blueprint, render_template, redirect, url_for,
                   session, flash, request, current_app)
from app.models import Invite, InviteClaim, User
from app import db
from app.auth.oidc import login_required, admin_required

invites_bp = Blueprint("invites", __name__, url_prefix="/invites")


@invites_bp.route("/")
@admin_required
def index():
    invites = Invite.query.order_by(Invite.created_at.desc()).all()
    now     = datetime.now(timezone.utc)
    return render_template("invites/index.html", invites=invites, now=now)


@invites_bp.route("/new", methods=["GET", "POST"])
@admin_required
def new():
    if request.method == "POST":
        label      = request.form.get("label", "").strip()
        role       = request.form.get("role", "author")
        use_type   = request.form.get("use_type", "single")
        max_uses   = None
        expires_at = None

        if not label:
            flash("Label required.", "danger")
            return render_template("invites/new.html")

        if use_type == "single":
            max_uses = 1
        elif use_type == "multi":
            try:
                max_uses = int(request.form.get("max_uses", 0)) or None
            except ValueError:
                max_uses = None

        expire_days = request.form.get("expire_days", "").strip()
        if expire_days:
            try:
                expires_at = datetime.now(timezone.utc) + timedelta(days=int(expire_days))
            except ValueError:
                pass

        if role not in ("author", "admin"):
            role = "author"

        user   = User.query.get(session["user_id"])
        invite = Invite(label=label, role=role, max_uses=max_uses,
                        expires_at=expires_at, created_by_id=user.id)
        db.session.add(invite)
        db.session.commit()
        flash("Invite created.", "success")
        return redirect(url_for("invites.index"))

    return render_template("invites/new.html")


@invites_bp.route("/revoke/<int:invite_id>", methods=["POST"])
@admin_required
def revoke(invite_id):
    invite = Invite.query.get_or_404(invite_id)
    invite.is_active = False
    db.session.commit()
    flash(f"Invite '{invite.label}' revoked.", "warning")
    return redirect(url_for("invites.index"))


@invites_bp.route("/claim/<token>")
@login_required
def claim(token):
    invite = Invite.query.filter_by(token=token).first()
    user   = User.query.get(session["user_id"])

    if not invite:
        flash("Invalid invite link.", "danger")
        return redirect(url_for("main.index"))

    if not invite.is_valid():
        flash("This invite link has expired or is no longer valid.", "danger")
        return redirect(url_for("main.index"))

    already = InviteClaim.query.filter_by(
        invite_id=invite.id, user_id=user.id).first()
    if already:
        flash("You have already used this invite.", "info")
        return redirect(url_for("main.index"))

    # Apply role — CDDS uses is_admin boolean
    user.is_admin = (invite.role == "admin")
    invite.uses  += 1

    claim = InviteClaim(invite_id=invite.id, user_id=user.id)
    db.session.add(claim)
    db.session.commit()

    session["is_admin"] = user.is_admin
    flash(f"Welcome! Your role has been set to {invite.role}.", "success")
    return redirect(url_for("main.index"))


@invites_bp.route("/join/<token>")
def join(token):
    if "user_id" not in session:
        return redirect(url_for("auth.login", invite=token))
    return redirect(url_for("invites.claim", token=token))

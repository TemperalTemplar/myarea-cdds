from functools import wraps
from datetime import datetime, timezone
from flask import (Blueprint, redirect, url_for, session,
                   request, current_app, flash)
from authlib.integrations.flask_client import OAuth
from ..models import User
from .. import db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
oauth   = OAuth()


def init_oauth(app):
    oauth.init_app(app)
    oauth.register(
        name="authentik",
        client_id=app.config["OIDC_CLIENT_ID"],
        client_secret=app.config["OIDC_CLIENT_SECRET"],
        server_metadata_url=app.config["OIDC_DISCOVERY_URL"],
        client_kwargs={"scope": "openid email profile"},
    )


@auth_bp.record_once
def on_load(state):
    init_oauth(state.app)


@auth_bp.route("/login")
def login():
    invite_token = request.args.get("invite")
    if invite_token:
        session["pending_invite"] = invite_token
    return oauth.authentik.authorize_redirect(current_app.config["OIDC_REDIRECT_URI"])


@auth_bp.route("/oidc/callback")
def oidc_callback():
    token    = oauth.authentik.authorize_access_token()
    userinfo = token.get("userinfo") or oauth.authentik.userinfo()

    sub          = userinfo.get("sub", "")
    username     = userinfo.get("preferred_username") or userinfo.get("name", "unknown")
    email        = userinfo.get("email", "")
    display_name = userinfo.get("name", username)

    user = User.query.filter_by(authentik_sub=sub).first()
    is_new = user is None

    if not user:
        user = User(authentik_sub=sub, username=username,
                    email=email, display_name=display_name)
        db.session.add(user)
        db.session.flush()
    else:
        user.username     = username
        user.email        = email
        user.display_name = display_name
        user.last_seen    = datetime.now(timezone.utc)

    # ── First-run bootstrap ───────────────────────────────────────────────
    if is_new and User.query.filter_by(is_admin=True).count() == 0:
        user.is_admin = True
        db.session.commit()
        session["user_id"]  = user.id
        session["username"] = user.username
        session["is_admin"] = user.is_admin
        session["sub"]      = sub
        flash("Welcome! You are the first user — you have been made admin.", "success")
        return redirect(url_for("main.index"))

    db.session.commit()

    session["user_id"]  = user.id
    session["username"] = user.username
    session["is_admin"] = user.is_admin
    session["sub"]      = sub

    # ── Invite claim ──────────────────────────────────────────────────────
    pending = session.pop("pending_invite", None)
    if pending:
        return redirect(url_for("invites.claim", token=pending))

    return redirect(url_for("main.index"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(current_app.config["SITE_URL"])


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        if not session.get("is_admin"):
            flash("Admin access required.", "danger")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return decorated

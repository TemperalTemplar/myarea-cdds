"""
Federation API — updated with bell + email notifications on pull/handshake.
"""
import os
from datetime import datetime, timezone
from functools import wraps
from flask import (Blueprint, request, jsonify, send_file, current_app)
from ..models import FederationToken, Course, IssueRecord
from .. import db

federation_bp = Blueprint("federation", __name__, url_prefix="/federation")


def require_federation_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "authorization required"}), 401
        ft = FederationToken.query.filter_by(
            token=auth[7:].strip(), is_active=True).first()
        if not ft:
            return jsonify({"error": "invalid or revoked token"}), 401
        ft.last_used = datetime.now(timezone.utc)
        db.session.commit()
        request.federation_token = ft
        return f(*args, **kwargs)
    return decorated


@federation_bp.get("/catalog")
@require_federation_token
def catalog():
    courses = Course.query.filter_by(is_published=True, is_public=True).all()
    return jsonify({"node": current_app.config.get("NODE_NAME", ""),
                    "courses": [_course_meta(c) for c in courses]})


@federation_bp.get("/catalog/<string:course_uuid>")
@require_federation_token
def catalog_detail(course_uuid):
    c = Course.query.filter_by(uuid=course_uuid, is_published=True).first_or_404()
    return jsonify(_course_meta(c))


@federation_bp.get("/pull/<string:course_uuid>")
@require_federation_token
def pull_package(course_uuid):
    c = Course.query.filter_by(uuid=course_uuid, is_published=True).first_or_404()
    if not c.package_file:
        return jsonify({"error": "package not yet built"}), 404
    pkg_path = os.path.join(current_app.config["PACKAGES_DIR"], c.package_file)
    if not os.path.exists(pkg_path):
        return jsonify({"error": "package file missing"}), 404

    ft = request.federation_token
    record = IssueRecord(course_id=c.id, token_id=ft.id,
                         remote_label=ft.label, remote_url=ft.remote_url,
                         package_hash=c.package_hash)
    db.session.add(record)
    ft.pull_count += 1
    db.session.commit()

    site_url = current_app.config.get("SITE_URL", "")

    # Bell notification to author
    try:
        from ..api.notifications import push
        push(recipient_sub=c.author.authentik_sub, actor="system",
             notif_type="cdds_package_pulled",
             title=f"Course pulled: {c.title}",
             body=f"Pulled by {ft.label}",
             url=f"{site_url}/admin")
    except Exception:
        pass

    # Email author
    try:
        if c.author.email:
            from ..utils.mail import notify_package_pulled
            notify_package_pulled(c.author.email,
                                  c.author.display_name or c.author.username,
                                  c.title, ft.label, site_url)
    except Exception:
        pass

    return send_file(pkg_path, mimetype="application/zip",
                     as_attachment=True,
                     download_name=f"{c.slug}-{c.version}.cdpkg")


@federation_bp.post("/handshake")
def handshake():
    data = request.get_json(silent=True) or {}
    remote_url  = data.get("node_url", "").strip()
    remote_name = data.get("node_name", "").strip()
    message     = data.get("message", "").strip()

    import logging
    logging.getLogger(__name__).info(
        "Handshake from %s (%s): %s", remote_name, remote_url, message)

    # Bell all admins
    try:
        from ..models import User
        from ..api.notifications import push
        site_url = current_app.config.get("SITE_URL", "")
        for admin in User.query.filter_by(is_admin=True).all():
            push(recipient_sub=admin.authentik_sub, actor="system",
                 notif_type="cdds_handshake",
                 title=f"Federation request from {remote_name or remote_url}",
                 body=message[:120] or "A new node wants to connect.",
                 url=f"{site_url}/admin")
    except Exception:
        pass

    return jsonify({"ok": True,
                    "node": current_app.config.get("NODE_NAME", ""),
                    "site_url": current_app.config.get("SITE_URL", ""),
                    "message": "Handshake received. Admin will review."})


def _course_meta(c):
    return {"uuid": c.uuid, "title": c.title, "slug": c.slug,
            "description": c.description, "category": c.category,
            "tags": c.tag_list(), "version": c.version, "license": c.license,
            "author": c.author.display_name or c.author.username,
            "package_hash": c.package_hash, "package_size": c.package_size,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None}

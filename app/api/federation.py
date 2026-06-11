"""
Federation API — used by remote LMS nodes to browse and pull packages.

All endpoints require a valid federation token in the Authorization header:
    Authorization: Bearer <token>

Routes:
  GET  /federation/catalog          — list published courses
  GET  /federation/catalog/<uuid>   — single course metadata
  GET  /federation/pull/<uuid>      — download .cdpkg (increments pull_count)
  POST /federation/handshake        — initial introduction from a new LMS node
"""
import os
import hashlib
from datetime import datetime, timezone
from functools import wraps
from flask import (Blueprint, request, jsonify, send_file,
                   current_app, abort)
from ..models import FederationToken, Course, IssueRecord
from .. import db

federation_bp = Blueprint("federation", __name__, url_prefix="/federation")


def require_federation_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "authorization required"}), 401
        raw_token = auth[7:].strip()
        ft = FederationToken.query.filter_by(token=raw_token, is_active=True).first()
        if not ft:
            return jsonify({"error": "invalid or revoked token"}), 401
        # stamp last used
        ft.last_used = datetime.now(timezone.utc)
        db.session.commit()
        request.federation_token = ft
        return f(*args, **kwargs)
    return decorated


# ── GET /federation/catalog ──────────────────────────────────────────────
@federation_bp.get("/catalog")
@require_federation_token
def catalog():
    courses = Course.query.filter_by(is_published=True, is_public=True).all()
    return jsonify({
        "node":    current_app.config.get("NODE_NAME", ""),
        "courses": [_course_meta(c) for c in courses],
    })


# ── GET /federation/catalog/<uuid> ───────────────────────────────────────
@federation_bp.get("/catalog/<string:course_uuid>")
@require_federation_token
def catalog_detail(course_uuid):
    c = Course.query.filter_by(uuid=course_uuid, is_published=True).first_or_404()
    return jsonify(_course_meta(c))


# ── GET /federation/pull/<uuid> ──────────────────────────────────────────
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

    # Log the issue — immutable record, no recalls
    record = IssueRecord(
        course_id    = c.id,
        token_id     = ft.id,
        remote_label = ft.label,
        remote_url   = ft.remote_url,
        package_hash = c.package_hash,
    )
    db.session.add(record)
    ft.pull_count += 1
    db.session.commit()

    return send_file(
        pkg_path,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{c.slug}-{c.version}.cdpkg",
    )


# ── POST /federation/handshake ───────────────────────────────────────────
@federation_bp.post("/handshake")
def handshake():
    """
    A remote LMS introduces itself.  No token needed — this is the request
    for access.  The CDDS admin reviews and issues a token manually.
    Returns node identity so the LMS knows it reached the right place.
    """
    data        = request.get_json(silent=True) or {}
    remote_url  = data.get("node_url", "").strip()
    remote_name = data.get("node_name", "").strip()
    message     = data.get("message", "").strip()

    # Log it — admin will see it in the token management panel
    import logging
    logging.getLogger(__name__).info(
        "Federation handshake from %s (%s): %s",
        remote_name, remote_url, message
    )

    return jsonify({
        "ok":        True,
        "node":      current_app.config.get("NODE_NAME", ""),
        "site_url":  current_app.config.get("SITE_URL", ""),
        "message":   "Handshake received. The node admin will review your request and issue a token if approved.",
    })


# ── helpers ───────────────────────────────────────────────────────────────
def _course_meta(c: Course) -> dict:
    return {
        "uuid":         c.uuid,
        "title":        c.title,
        "slug":         c.slug,
        "description":  c.description,
        "category":     c.category,
        "tags":         c.tag_list(),
        "version":      c.version,
        "license":      c.license,
        "author":       c.author.display_name or c.author.username,
        "package_hash": c.package_hash,
        "package_size": c.package_size,
        "updated_at":   c.updated_at.isoformat() if c.updated_at else None,
    }

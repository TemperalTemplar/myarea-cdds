import uuid
from datetime import datetime, timezone
from . import db


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    authentik_sub = db.Column(db.String(256), unique=True, nullable=False, index=True)
    username      = db.Column(db.String(128), nullable=False)
    email         = db.Column(db.String(256), nullable=True)
    display_name  = db.Column(db.String(256), nullable=True)
    is_admin      = db.Column(db.Boolean, default=False, nullable=False)
    created_at    = db.Column(db.DateTime(timezone=True), default=utcnow)
    last_seen     = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    courses       = db.relationship("Course", back_populates="author", lazy="dynamic")
    tokens        = db.relationship("FederationToken", back_populates="created_by", lazy="dynamic")

    def __repr__(self):
        return f"<User {self.username}>"


class Course(db.Model):
    __tablename__ = "courses"

    id            = db.Column(db.Integer, primary_key=True)
    uuid          = db.Column(db.String(36), unique=True, nullable=False,
                              default=lambda: str(uuid.uuid4()))
    title         = db.Column(db.String(256), nullable=False)
    slug          = db.Column(db.String(256), unique=True, nullable=False, index=True)
    description   = db.Column(db.Text, nullable=True)
    category      = db.Column(db.String(128), nullable=True)
    tags          = db.Column(db.String(512), nullable=True)   # comma-separated
    version       = db.Column(db.String(32), default="1.0.0", nullable=False)
    license       = db.Column(db.String(256), nullable=True)   # optional, decorative
    is_published  = db.Column(db.Boolean, default=False, nullable=False)
    is_public     = db.Column(db.Boolean, default=True, nullable=False)
    package_file  = db.Column(db.String(512), nullable=True)   # path to .cdpkg
    package_hash  = db.Column(db.String(64), nullable=True)    # SHA-256 of package
    package_size  = db.Column(db.Integer, nullable=True)       # bytes
    author_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at    = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at    = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    author        = db.relationship("User", back_populates="courses")
    modules       = db.relationship("Module", back_populates="course",
                                    cascade="all, delete-orphan",
                                    order_by="Module.position")
    issues        = db.relationship("IssueRecord", back_populates="course", lazy="dynamic")

    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def __repr__(self):
        return f"<Course {self.slug} v{self.version}>"


class Module(db.Model):
    __tablename__ = "modules"

    id          = db.Column(db.Integer, primary_key=True)
    course_id   = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    title       = db.Column(db.String(256), nullable=False)
    position    = db.Column(db.Integer, default=0, nullable=False)
    content     = db.Column(db.Text, nullable=True)   # markdown / HTML
    created_at  = db.Column(db.DateTime(timezone=True), default=utcnow)

    course      = db.relationship("Course", back_populates="modules")

    def __repr__(self):
        return f"<Module {self.title}>"


class FederationToken(db.Model):
    """
    A token issued to a remote LMS node granting access to browse/pull
    this CDDS node's catalog.  Once issued, it is the LMS's to keep.
    The CDDS node can revoke to prevent FUTURE access; past pulls are permanent.
    """
    __tablename__ = "federation_tokens"

    id            = db.Column(db.Integer, primary_key=True)
    token         = db.Column(db.String(64), unique=True, nullable=False,
                              default=lambda: str(uuid.uuid4()).replace("-", "") +
                                             str(uuid.uuid4()).replace("-", ""))
    label         = db.Column(db.String(256), nullable=False)   # human name: "Grace Church LMS"
    remote_url    = db.Column(db.String(512), nullable=True)    # their LMS URL if known
    remote_node   = db.Column(db.String(256), nullable=True)    # their node identity
    is_active     = db.Column(db.Boolean, default=True, nullable=False)
    scope         = db.Column(db.String(64), default="catalog:read,package:pull")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at    = db.Column(db.DateTime(timezone=True), default=utcnow)
    last_used     = db.Column(db.DateTime(timezone=True), nullable=True)
    pull_count    = db.Column(db.Integer, default=0, nullable=False)

    created_by    = db.relationship("User", back_populates="tokens")

    def __repr__(self):
        return f"<FederationToken {self.label} active={self.is_active}>"


class IssueRecord(db.Model):
    """
    Immutable log of every package pull.
    Once a package is issued it belongs to the recipient — no recalls.
    """
    __tablename__ = "issue_records"

    id            = db.Column(db.Integer, primary_key=True)
    course_id     = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    token_id      = db.Column(db.Integer, db.ForeignKey("federation_tokens.id"), nullable=True)
    remote_label  = db.Column(db.String(256), nullable=True)
    remote_url    = db.Column(db.String(512), nullable=True)
    package_hash  = db.Column(db.String(64), nullable=True)
    issued_at     = db.Column(db.DateTime(timezone=True), default=utcnow)

    course        = db.relationship("Course", back_populates="issues")

    def __repr__(self):
        return f"<IssueRecord course={self.course_id} at={self.issued_at}>"

# ── Invite System ─────────────────────────────────────────────────────────

class Invite(db.Model):
    __tablename__ = "invites"

    id           = db.Column(db.Integer, primary_key=True)
    token        = db.Column(db.String(64), unique=True, nullable=False,
                             default=lambda: str(uuid.uuid4()).replace("-","") +
                                            str(uuid.uuid4()).replace("-","")[:8])
    label        = db.Column(db.String(256), nullable=False)
    # CDDS roles: author, admin
    role         = db.Column(db.String(32), default="author", nullable=False)
    max_uses     = db.Column(db.Integer, nullable=True)
    uses         = db.Column(db.Integer, default=0, nullable=False)
    expires_at   = db.Column(db.DateTime(timezone=True), nullable=True)
    is_active    = db.Column(db.Boolean, default=True, nullable=False)
    created_by_id= db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at   = db.Column(db.DateTime(timezone=True), default=utcnow)

    created_by   = db.relationship("User", foreign_keys=[created_by_id],
                                   backref=db.backref("invites_created", lazy="dynamic"))
    claims       = db.relationship("InviteClaim", back_populates="invite",
                                   cascade="all, delete-orphan", lazy="dynamic")

    def is_valid(self):
        from datetime import datetime, timezone
        if not self.is_active:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        if self.max_uses is not None and self.uses >= self.max_uses:
            return False
        return True

    def __repr__(self):
        return f"<Invite {self.label} role={self.role}>"


class InviteClaim(db.Model):
    __tablename__ = "invite_claims"

    id          = db.Column(db.Integer, primary_key=True)
    invite_id   = db.Column(db.Integer, db.ForeignKey("invites.id"), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    claimed_at  = db.Column(db.DateTime(timezone=True), default=utcnow)

    invite      = db.relationship("Invite", back_populates="claims")
    user        = db.relationship("User", backref=db.backref("invite_claims", lazy="dynamic"))

    def __repr__(self):
        return f"<InviteClaim invite={self.invite_id} user={self.user_id}>"

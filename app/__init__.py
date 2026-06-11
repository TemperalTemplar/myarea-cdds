import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # ── Core config ──────────────────────────────────────────────────────
    app.config["SECRET_KEY"]        = os.environ["SECRET_KEY"]
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["REDIS_URL"]         = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    app.config["SERVICE_API_KEY"]   = os.environ.get("SERVICE_API_KEY", "")
    app.config["MYAREA_AI_URL"]     = os.environ.get("MYAREA_AI_URL", "http://myarea-ai:8930")
    app.config["SITE_URL"]          = os.environ.get("SITE_URL", "https://cdds.wrds361.com")
    app.config["NODE_NAME"]         = os.environ.get("NODE_NAME", "cdds.wrds361.com")

    # ── OIDC config ───────────────────────────────────────────────────────
    app.config["OIDC_CLIENT_ID"]       = os.environ.get("OIDC_CLIENT_ID", "")
    app.config["OIDC_CLIENT_SECRET"]   = os.environ.get("OIDC_CLIENT_SECRET", "")
    app.config["OIDC_DISCOVERY_URL"]   = os.environ.get("OIDC_DISCOVERY_URL", "")
    app.config["OIDC_REDIRECT_URI"]    = os.environ.get("OIDC_REDIRECT_URI", "")

    # ── Package storage ───────────────────────────────────────────────────
    app.config["PACKAGES_DIR"] = os.path.join(os.path.dirname(app.root_path), "packages")
    os.makedirs(app.config["PACKAGES_DIR"], exist_ok=True)

    # ── Extensions ────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    # ── Blueprints ────────────────────────────────────────────────────────
    from .auth.oidc import auth_bp
    from .api.federation import federation_bp
    from .routes.main import main_bp
    from .routes.courses import courses_bp
    from .routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(federation_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(admin_bp)

    return app

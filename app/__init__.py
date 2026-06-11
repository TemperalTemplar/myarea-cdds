import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    app.config["SECRET_KEY"]        = os.environ["SECRET_KEY"]
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["REDIS_URL"]         = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    app.config["SERVICE_API_KEY"]   = os.environ.get("SERVICE_API_KEY", "")
    app.config["MYAREA_AI_URL"]     = os.environ.get("MYAREA_AI_URL", "http://myarea-ai:8930")
    app.config["SITE_URL"]          = os.environ.get("SITE_URL", "https://cdds.wrds361.com")
    app.config["NODE_NAME"]         = os.environ.get("NODE_NAME", "cdds.wrds361.com")
    app.config["SESSION_COOKIE_SECURE"]   = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

    # OIDC
    app.config["OIDC_CLIENT_ID"]       = os.environ.get("OIDC_CLIENT_ID", "")
    app.config["OIDC_CLIENT_SECRET"]   = os.environ.get("OIDC_CLIENT_SECRET", "")
    app.config["OIDC_DISCOVERY_URL"]   = os.environ.get("OIDC_DISCOVERY_URL", "")
    app.config["OIDC_REDIRECT_URI"]    = os.environ.get("OIDC_REDIRECT_URI", "")

    # SMTP / Mailcow
    app.config["SMTP_HOST"]     = os.environ.get("SMTP_HOST", "mail.wrds361.com")
    app.config["SMTP_PORT"]     = os.environ.get("SMTP_PORT", "587")
    app.config["SMTP_USER"]     = os.environ.get("SMTP_USER", "")
    app.config["SMTP_PASSWORD"] = os.environ.get("SMTP_PASSWORD", "")
    app.config["SMTP_FROM"]     = os.environ.get("SMTP_FROM", "")

    # Package storage
    app.config["PACKAGES_DIR"] = os.path.join(os.path.dirname(app.root_path), "packages")
    os.makedirs(app.config["PACKAGES_DIR"], exist_ok=True)

    # Import storage
    app.config["IMPORTS_DIR"] = os.path.join(os.path.dirname(app.root_path), "imports")
    os.makedirs(app.config["IMPORTS_DIR"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from .auth.oidc import auth_bp
    from .api.federation import federation_bp
    from .routes.main import main_bp
    from .routes.courses import courses_bp
    from .routes.admin import admin_bp
    from .routes.invites import invites_bp
    from .routes.importer import importer_bp
    from .routes.merit_badge import merit_badge_bp

    for bp in (auth_bp, federation_bp, main_bp,
               courses_bp, admin_bp, importer_bp, invites_bp, merit_badge_bp):
        app.register_blueprint(bp)

    return app

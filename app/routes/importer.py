"""
Course Importer — upload a zip of content and scaffold it as a CDDS course.
Accepted: .zip or .cdpkg containing .md, .txt, .html files + optional manifest.json
"""
import os, re, json, zipfile, uuid as uuid_mod
from flask import (Blueprint, render_template, redirect, url_for,
                   session, flash, request, current_app)
from slugify import slugify
from ..models import Course, Module, User
from .. import db
from ..auth.oidc import login_required

importer_bp = Blueprint("importer", __name__, url_prefix="/import")
ALLOWED_EXT = {".md", ".txt", ".html", ".htm"}


@importer_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        f = request.files.get("package")
        if not f or not f.filename:
            flash("No file selected.", "danger")
            return render_template("importer/index.html")

        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in (".zip", ".cdpkg"):
            flash("Only .zip and .cdpkg files are supported.", "danger")
            return render_template("importer/index.html")

        imports_dir = current_app.config["IMPORTS_DIR"]
        uid         = str(uuid_mod.uuid4())[:8]
        save_path   = os.path.join(imports_dir, f"{uid}_{f.filename}")
        f.save(save_path)

        try:
            user   = User.query.get(session["user_id"])
            course = _import_zip(save_path, user)
            flash(f"Course '{course.title}' imported as draft. Review and publish when ready.", "success")
            return redirect(url_for("courses.edit_course", slug=course.slug))
        except Exception as exc:
            flash(f"Import failed: {exc}", "danger")

    return render_template("importer/index.html")


def _import_zip(zip_path, user):
    with zipfile.ZipFile(zip_path, "r") as zf:
        names    = zf.namelist()
        manifest = {}
        if "manifest.json" in names:
            try:
                manifest = json.loads(zf.read("manifest.json"))
            except Exception:
                pass

        content_files = sorted([
            n for n in names
            if os.path.splitext(n)[1].lower() in ALLOWED_EXT
            and not n.startswith("__MACOSX")
            and not os.path.basename(n).startswith(".")
        ])

        if not content_files and not manifest.get("modules"):
            raise ValueError("No readable content files found in zip.")

        title = (manifest.get("title") or
                 _title_from_filename(os.path.basename(zip_path)) or
                 "Imported Course")

        slug = slugify(title)
        base, n = slug, 1
        while Course.query.filter_by(slug=slug).first():
            slug = f"{base}-{n}"; n += 1

        course = Course(
            title=title, slug=slug,
            description=manifest.get("description", ""),
            category=manifest.get("category", ""),
            tags=",".join(manifest.get("tags", [])),
            version=manifest.get("version", "1.0.0"),
            license=manifest.get("license", ""),
            author_id=user.id, is_published=False,
        )
        db.session.add(course)
        db.session.flush()

        if content_files:
            for pos, fname in enumerate(content_files, 1):
                raw = zf.read(fname).decode("utf-8", errors="replace")
                ext = os.path.splitext(fname)[1].lower()
                content = _strip_html(raw) if ext in (".html", ".htm") else raw
                db.session.add(Module(
                    course_id=course.id,
                    title=_title_from_filename(os.path.basename(fname)),
                    position=pos, content=content,
                ))
        elif manifest.get("modules"):
            for pos, m in enumerate(manifest["modules"], 1):
                db.session.add(Module(
                    course_id=course.id,
                    title=m.get("title", f"Module {pos}"),
                    position=pos, content=m.get("content", ""),
                ))

        db.session.commit()
        return course


def _title_from_filename(filename):
    name = os.path.splitext(filename)[0]
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(r"^\d+\s*", "", name)
    return name.strip().title() or "Module"


def _strip_html(html):
    clean = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL|re.IGNORECASE)
    clean = re.sub(r"<script[^>]*>.*?</script>", "", clean, flags=re.DOTALL|re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", "", clean)
    return re.sub(r"\n{3,}", "\n\n", clean).strip()

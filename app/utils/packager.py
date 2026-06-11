"""
.cdpkg builder — creates a signed zip package from a Course.

Format:
    <slug>-<version>.cdpkg   (zip file)
    ├── manifest.json         course metadata + hash chain
    ├── modules/
    │   ├── 01-<slug>.md
    │   └── ...
    └── signature.txt         SHA-256 of manifest.json (node identity)

The .cdpkg is the atomic unit of federation.  Once issued it belongs
to the recipient.  The signature lets the LMS verify the package was
not tampered with in transit — it is NOT a revocation mechanism.
"""
import os
import json
import hashlib
import zipfile
import tempfile
from datetime import timezone
from flask import current_app
from ..models import Course


def build_package(course: Course) -> tuple[str, str, int]:
    """
    Build a .cdpkg for the given course.
    Returns (filename, sha256_hex, size_bytes).
    Updates course.package_file, course.package_hash, course.package_size.
    """
    packages_dir = current_app.config["PACKAGES_DIR"]
    node_name    = current_app.config.get("NODE_NAME", "cdds.wrds361.com")

    filename = f"{course.slug}-{course.version}.cdpkg"
    out_path = os.path.join(packages_dir, filename)

    # Build manifest
    manifest = {
        "cdpkg_version": "1.0",
        "uuid":          course.uuid,
        "title":         course.title,
        "slug":          course.slug,
        "version":       course.version,
        "description":   course.description or "",
        "category":      course.category or "",
        "tags":          course.tag_list(),
        "license":       course.license or "",
        "author":        course.author.display_name or course.author.username,
        "origin_node":   node_name,
        "issued_at":     course.updated_at.replace(tzinfo=timezone.utc).isoformat()
                         if course.updated_at else "",
        "modules": [
            {
                "position": m.position,
                "title":    m.title,
                "file":     f"modules/{m.position:02d}-{_slugify(m.title)}.md",
            }
            for m in course.modules
        ],
    }

    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False)
    manifest_hash = hashlib.sha256(manifest_json.encode()).hexdigest()
    signature     = f"sha256:{manifest_hash}\nnode:{node_name}\n"

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_json)
        zf.writestr("signature.txt", signature)
        for m in course.modules:
            mod_filename = f"modules/{m.position:02d}-{_slugify(m.title)}.md"
            content      = f"# {m.title}\n\n{m.content or ''}"
            zf.writestr(mod_filename, content)

    size   = os.path.getsize(out_path)
    sha256 = _file_hash(out_path)

    return filename, sha256, size


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:64]

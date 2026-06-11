"""
CDDS mail utility — Mailcow SMTP, same pattern as LMS.
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body_html: str) -> bool:
    host     = current_app.config.get("SMTP_HOST", "")
    port     = int(current_app.config.get("SMTP_PORT", 587))
    user     = current_app.config.get("SMTP_USER", "")
    password = current_app.config.get("SMTP_PASSWORD", "")
    from_addr= current_app.config.get("SMTP_FROM", user)

    if not all([host, user, password]):
        logger.warning("SMTP not configured — skipping email to %s", to)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to
    msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(host, port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_addr, [to], msg.as_string())
        return True
    except Exception as exc:
        logger.error("Email failed to %s: %s", to, exc)
        return False


def notify_package_pulled(author_email, author_name, course_title,
                          remote_label, site_url) -> bool:
    subject = f"Your course was pulled: {course_title}"
    html = f"""
    <div style="font-family:monospace;background:#0d0f14;color:#e8eaf0;padding:24px;border-radius:8px;">
      <div style="font-size:20px;font-weight:700;color:#e63946;letter-spacing:3px;margin-bottom:16px;">CDDS</div>
      <p>Hi {author_name},</p>
      <p>Your course <strong>{course_title}</strong> was pulled by <strong>{remote_label}</strong>.</p>
      <p>Once issued the course belongs to the recipient permanently.</p>
      <p><a href="{site_url}/admin" style="color:#e63946;">View Issue Records</a></p>
      <p style="color:#4a5a7a;font-size:12px;">MyArea CDDS · {site_url}</p>
    </div>"""
    return send_email(author_email, subject, html)


def notify_token_issued(admin_email, admin_name, token_label, site_url) -> bool:
    subject = f"Federation token issued: {token_label}"
    html = f"""
    <div style="font-family:monospace;background:#0d0f14;color:#e8eaf0;padding:24px;border-radius:8px;">
      <div style="font-size:20px;font-weight:700;color:#e63946;letter-spacing:3px;margin-bottom:16px;">CDDS</div>
      <p>Hi {admin_name},</p>
      <p>A federation token was issued to <strong>{token_label}</strong>.</p>
      <p><a href="{site_url}/admin" style="color:#e63946;">Manage Tokens</a></p>
      <p style="color:#4a5a7a;font-size:12px;">MyArea CDDS · {site_url}</p>
    </div>"""
    return send_email(admin_email, subject, html)

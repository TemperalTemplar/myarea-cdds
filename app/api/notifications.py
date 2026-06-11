"""
Push a notification to the platform bell via myarea-ai.
Header: X-Service-Key (matches SERVICE_API_KEY across the ecosystem).
"""
import requests
import logging
from flask import current_app

logger = logging.getLogger(__name__)


def push(recipient_sub: str, actor: str, notif_type: str,
         title: str, body: str = "", url: str = "") -> bool:
    """
    Push a notification to a user's platform bell.

    recipient_sub : Authentik sub of the recipient
    actor         : username or "system" / "cdds"
    notif_type    : slug e.g. "cdds_token_approved", "cdds_package_ready"
    title         : short title shown in bell dropdown
    body          : optional longer text
    url           : optional link when bell item is clicked
    """
    ai_url = current_app.config.get("MYAREA_AI_URL", "http://myarea-ai:8930")
    key    = current_app.config.get("SERVICE_API_KEY", "")

    payload = {
        "recipient": recipient_sub,
        "actor":     actor,
        "type":      notif_type,
        "title":     title,
        "body":      body,
        "url":       url,
    }

    try:
        resp = requests.post(
            f"{ai_url}/api/notifications/push",
            json=payload,
            headers={"X-Service-Key": key},
            timeout=5,
        )
        if resp.status_code == 200:
            return True
        logger.warning("notif push failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("notif push exception: %s", exc)

    return False

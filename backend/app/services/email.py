"""Simple email sending for password reset. If SMTP is not configured, logs the link (dev)."""
import logging
import smtplib
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    """Send password reset email. If SMTP not configured, log the link only."""
    subject = "JobTracker – Reset your password"
    body = f"""You requested a password reset for JobTracker.

Click the link below to set a new password (valid for {settings.password_reset_expire_minutes} minutes):

{reset_link}

If you didn't request this, you can ignore this email.
"""
    if not settings.smtp_host:
        logger.info(
            "Password reset link (SMTP not configured): %s -> %s",
            to_email,
            reset_link,
        )
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(
                msg["From"],
                [to_email],
                msg.as_string(),
            )
        logger.info("Password reset email sent to %s", to_email)
    except Exception as e:
        logger.exception("Failed to send password reset email to %s: %s", to_email, e)
        raise

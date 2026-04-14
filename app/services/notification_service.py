"""
Notification Service — Email and Slack notifications for alerts and approvals.
"""
import logging
import aiohttp
import asyncio
from typing import Optional, List, Dict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications via email and Slack."""

    @staticmethod
    async def send_slack_message(
        channel: str,
        message: str,
        blocks: Optional[List[Dict]] = None,
        webhook_url: Optional[str] = None,
    ) -> bool:
        """
        Send message to Slack.

        Args:
            channel: Slack channel (e.g., '#alerts')
            message: Text message
            blocks: Optional blocks for rich formatting
            webhook_url: Slack webhook URL (uses config if None)

        Returns:
            True if successful
        """
        if not webhook_url:
            webhook_url = settings.SLACK_WEBHOOK_URL

        if not webhook_url:
            logger.warning("Slack webhook not configured")
            return False

        payload = {
            "channel": channel,
            "text": message,
        }
        if blocks:
            payload["blocks"] = blocks

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        logger.info(f"Slack notification sent to {channel}")
                        return True
                    else:
                        logger.error(f"Slack notification failed: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to send Slack message: {e}")
            return False

    @staticmethod
    def send_email(
        to: str,
        subject: str,
        html_body: str,
        from_addr: Optional[str] = None,
    ) -> bool:
        """
        Send email notification via SMTP.

        Requires SMTP_HOST to be configured in settings.
        Falls back to a warning log if SMTP is not configured.
        """
        smtp_host = getattr(settings, "SMTP_HOST", None)
        if not smtp_host:
            logger.warning(
                f"Email NOT sent (SMTP_HOST not configured): To={to} Subject={subject}"
            )
            return False

        from_addr = from_addr or getattr(settings, "SMTP_FROM", "noreply@nexuspm.local")
        smtp_port = getattr(settings, "SMTP_PORT", 587)
        smtp_user = getattr(settings, "SMTP_USER", None)
        smtp_pass = getattr(settings, "SMTP_PASSWORD", None)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.ehlo()
                if smtp_port != 25:
                    server.starttls()
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, [to], msg.as_string())
            logger.info(f"Email sent: To={to} Subject={subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False


# ── Module-level convenience wrapper (used by automation engine) ──────────────
def send_email_notification(to: str, subject: str, body: str) -> bool:
    """Synchronous wrapper around NotificationService.send_email for automation actions."""
    return NotificationService.send_email(to=to, subject=subject, html_body=body)


    @staticmethod
    async def notify_document_approval_pending(
        document_id: str,
        document_title: str,
        requester_name: str,
        approver_email: str,
        approver_name: str,
    ) -> bool:
        """Send notification when document requires approval."""
        message = f"Document '{document_title}' uploaded by {requester_name} requires your approval"

        # Try Slack first
        if settings.SLACK_WEBHOOK_URL:
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Document Approval Required*\n{message}",
                    },
                },
            ]
            await NotificationService.send_slack_message(
                "#documents",
                message,
                blocks=blocks,
            )

        # Also send email
        NotificationService.send_email(
            approver_email,
            f"Document Approval: {document_title}",
            f"<p>{message}</p><p>Please review and approve this document.</p>",
        )

        return True

    @staticmethod
    async def notify_overload_alert(
        user_name: str,
        user_email: str,
        load_pct: float,
        week: str,
    ) -> bool:
        """Send notification when resource is overloaded."""
        message = f"⚠️  {user_name} is overloaded at {load_pct:.0f}% for week {week}"

        # Slack
        if settings.SLACK_WEBHOOK_URL:
            await NotificationService.send_slack_message(
                "#resource-alerts",
                message,
            )

        # Email
        NotificationService.send_email(
            user_email,
            "Resource Overload Alert",
            f"<p>You are overloaded at {load_pct:.0f}% capacity for week {week}.</p><p>Please review your workload.</p>",
        )

        return True

    @staticmethod
    async def notify_missing_imputation(
        user_name: str,
        user_email: str,
        date_missing: str,
        expected_hours: float,
    ) -> bool:
        """Send notification for missing imputation."""
        message = f"Missing imputation for {user_name} on {date_missing} (expected {expected_hours}h)"

        # Slack
        if settings.SLACK_WEBHOOK_URL:
            await NotificationService.send_slack_message(
                "#time-tracking",
                message,
            )

        # Email
        NotificationService.send_email(
            user_email,
            "Missing Time Entry",
            f"<p>You haven't logged your work for {date_missing}.</p><p>Expected hours: {expected_hours}</p>",
        )

        return True

    @staticmethod
    async def notify_skill_gap(
        project_name: str,
        required_skill: str,
        available_users: int,
    ) -> bool:
        """Send notification for skill gaps in projects."""
        message = f"Skill gap in {project_name}: {required_skill} needed. {available_users} users available."

        # Slack
        if settings.SLACK_WEBHOOK_URL:
            await NotificationService.send_slack_message(
                "#resource-alerts",
                message,
            )

        return True


# Async wrapper for backward compatibility
def send_notification_sync(notification_type: str, **kwargs) -> bool:
    """
    Synchronous wrapper for sending notifications.

    Used for non-async contexts.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if notification_type == "document_approval":
        return loop.run_until_complete(
            NotificationService.notify_document_approval_pending(**kwargs)
        )
    elif notification_type == "overload":
        return loop.run_until_complete(
            NotificationService.notify_overload_alert(**kwargs)
        )
    elif notification_type == "missing_imputation":
        return loop.run_until_complete(
            NotificationService.notify_missing_imputation(**kwargs)
        )
    elif notification_type == "skill_gap":
        return loop.run_until_complete(
            NotificationService.notify_skill_gap(**kwargs)
        )

    return False


# Singleton instance
notification_service = NotificationService()

"""Real email channel — goes through Django's own mail backend.

Not simulated: django.core.mail.send_mail is a genuine send, it just lands on
whatever EMAIL_BACKEND is configured. Dev defaults to the console backend (the
message is printed to the runserver log, nothing external is required); setting
EMAIL_HOST/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD in .env and EMAIL_BACKEND=
django.core.mail.backends.smtp.EmailBackend turns this into real SMTP delivery
(SendGrid, Gmail, etc.) with no code change here.
"""

from __future__ import annotations

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from ..models import Notification
from .base import NotificationChannel

_SUBJECTS = {
    Notification.Kind.PACKAGING_VIDEO: "Here's your Burk.pk packaging video — order {ref}",
    Notification.Kind.SHIPMENT_TRACKING: "Your Burk.pk order {ref} is on its way",
    Notification.Kind.REVIEW_REQUEST: "How was your Burk.pk order {ref}?",
}


def _render(notification: Notification) -> tuple[str, str]:
    """(subject, body) for one notification, from its kind + payload."""
    order = notification.order
    subject = _SUBJECTS[notification.kind].format(ref=order.reference)
    payload = notification.payload

    if notification.kind == Notification.Kind.PACKAGING_VIDEO:
        body = (
            f"Hi {order.customer_name or 'there'},\n\n"
            f"Your order {order.reference} has just been packed. Here is a "
            f"recording of your item(s) being packaged so you can see exactly "
            f"what went into the box:\n\n{payload.get('video_url', '')}\n\n"
            f"— Burk.pk"
        )
    elif notification.kind == Notification.Kind.SHIPMENT_TRACKING:
        body = (
            f"Hi {order.customer_name or 'there'},\n\n"
            f"Your order {order.reference} has been booked with "
            f"{payload.get('courier_display', payload.get('courier', ''))}.\n"
            f"Tracking number: {payload.get('tracking_number', '')}\n\n"
            f"— Burk.pk"
        )
    else:  # REVIEW_REQUEST
        body = (
            f"Hi {order.customer_name or 'there'},\n\n"
            f"Your order {order.reference} was delivered. We'd love to hear "
            f"what you thought:\n\n{payload.get('review_link', '')}\n\n"
            f"— Burk.pk"
        )
    return subject, body


class EmailChannel(NotificationChannel):
    name = "email"

    def send(self, notification: Notification) -> dict:
        if not notification.recipient:
            raise ValueError("Order has no customer_email on file.")
        subject, body = _render(notification)
        message = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[notification.recipient],
        )
        sent = message.send(fail_silently=False)
        return {"backend": settings.EMAIL_BACKEND, "accepted": bool(sent)}

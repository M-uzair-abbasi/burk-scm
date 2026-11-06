import hashlib
import hmac
import json

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Notification, NotificationDeliveryEvent
from .services import NotificationWebhookConflict, process_delivery_receipt


@csrf_exempt
@require_POST
def notification_webhook(request, channel):
    """Signature-authenticated, replay-safe notification delivery ingress."""
    if channel not in Notification.Channel.values:
        return JsonResponse({"detail": "Unknown notification channel."}, status=404)
    if len(request.body) > settings.NOTIFICATION_WEBHOOK_MAX_BYTES:
        return JsonResponse({"detail": "Webhook payload is too large."}, status=413)
    secret = settings.NOTIFICATION_WEBHOOK_SECRETS.get(channel, "")
    if not secret:
        return JsonResponse({"detail": "Webhook is not configured."}, status=503)
    supplied = request.headers.get("X-Notification-Signature", "")
    expected = "sha256=" + hmac.new(
        secret.encode(), request.body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        return JsonResponse({"detail": "Invalid webhook signature."}, status=403)
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({"detail": "Invalid JSON payload."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"detail": "Webhook payload must be an object."}, status=400)
    try:
        event, replayed = process_delivery_receipt(
            channel, payload, raw_body=request.body
        )
    except NotificationWebhookConflict as exc:
        return JsonResponse({"detail": str(exc)}, status=409)
    except DjangoValidationError as exc:
        detail = exc.messages[0] if exc.messages else str(exc)
        return JsonResponse({"detail": detail}, status=400)

    response_status = (
        422
        if event.outcome == NotificationDeliveryEvent.Outcome.REJECTED
        else 200
    )
    return JsonResponse(
        {
            "event_id": event.provider_event_id,
            "outcome": event.outcome,
            "error_code": event.error_code or None,
            "replayed": replayed,
        },
        status=response_status,
    )

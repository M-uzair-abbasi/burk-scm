import hashlib
import hmac
import json

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsManager

from .models import Courier, CourierWebhookEvent, Shipment
from .serializers import ShipmentSerializer
from .services import (
    CourierWebhookConflict,
    advance_shipment,
    process_courier_webhook,
)


@csrf_exempt
@require_POST
def courier_webhook(request, courier):
    """Signature-authenticated, replay-safe courier status ingress."""
    if courier not in Courier.values:
        return JsonResponse({"detail": "Unknown courier."}, status=404)
    if len(request.body) > settings.COURIER_WEBHOOK_MAX_BYTES:
        return JsonResponse({"detail": "Webhook payload is too large."}, status=413)
    secret = settings.COURIER_WEBHOOK_SECRETS.get(courier, "")
    if not secret:
        return JsonResponse({"detail": "Webhook is not configured."}, status=503)
    supplied = request.headers.get("X-Courier-Signature", "")
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
        event, replayed = process_courier_webhook(
            courier, payload, raw_body=request.body
        )
    except CourierWebhookConflict as exc:
        return JsonResponse({"detail": str(exc)}, status=409)
    except DjangoValidationError as exc:
        detail = exc.messages[0] if exc.messages else str(exc)
        return JsonResponse({"detail": detail}, status=400)

    response_status = (
        422
        if event.outcome == CourierWebhookEvent.Outcome.REJECTED
        else 200
    )
    return JsonResponse(
        {
            "event_id": event.provider_event_id,
            "outcome": event.outcome,
            "mapped_status": event.mapped_status or None,
            "error_code": event.error_code or None,
            "replayed": replayed,
        },
        status=response_status,
    )


class ShipmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read the shipment queue plus a demo "advance" action standing in for a
    real courier webhook (booking is durably queued at pack-complete and handled
    by the worker, not through this API)."""

    permission_classes = [IsAuthenticated]
    queryset = Shipment.objects.select_related("order").prefetch_related("events")
    serializer_class = ShipmentSerializer

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def advance(self, request, pk=None):
        if not settings.DEMO_ACTIONS_ENABLED:
            raise NotFound()
        shipment = self.get_object()
        target = request.data.get("status", "")
        try:
            # A real courier webhook has no logged-in "user" — this simulate
            # action stands in for that webhook, so it doesn't pass one either.
            advance_shipment(shipment, target)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages[0] if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        shipment.refresh_from_db()
        return Response(ShipmentSerializer(shipment).data)

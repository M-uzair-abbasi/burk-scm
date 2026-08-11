from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Shipment
from .serializers import ShipmentSerializer
from .services import advance_shipment


class ShipmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read the shipment queue plus a demo "advance" action standing in for a
    real courier webhook (booking itself happens automatically at pack-complete,
    not through this API — see fulfillment.views.PackingViewSet.complete)."""

    permission_classes = [IsAuthenticated]
    queryset = Shipment.objects.select_related("order").prefetch_related("events")
    serializer_class = ShipmentSerializer

    @action(detail=True, methods=["post"])
    def advance(self, request, pk=None):
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

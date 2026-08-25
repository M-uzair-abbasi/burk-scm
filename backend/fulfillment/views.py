from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from logistics.services import enqueue_shipment_booking
from orders.models import SalesOrder, SalesOrderLine
from surveillance.services import seal_recording, start_recording

from .models import PackingSession
from .serializers import PackScanSerializer, QueueOrderSerializer, session_detail
from .services import (
    cancel_packing,
    complete_packing,
    confirm_line_manual,
    packing_queue,
    record_scan,
    start_packing,
)


def _bad(exc: DjangoValidationError) -> Response:
    return Response(
        {"detail": exc.messages[0] if exc.messages else str(exc)},
        status=status.HTTP_400_BAD_REQUEST,
    )


class PackingViewSet(viewsets.GenericViewSet):
    """The packing station: start a pack, scan items, confirm/complete/cancel.

    IsAuthenticated — operators run the floor. Scans and completion are validated
    server-side through fulfillment.services; the client's instant flash/beep is
    a UX layer on top of this authoritative log.
    """

    permission_classes = [IsAuthenticated]
    queryset = PackingSession.objects.all()

    def get_queryset(self):
        queryset = PackingSession.objects.select_related("order", "operator")
        if self.request.user.is_manager:
            return queryset
        return queryset.filter(operator=self.request.user)

    def get_object(self) -> PackingSession:
        return get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])

    def _detail(self, session):
        return session_detail(
            session,
            include_operational_errors=self.request.user.is_manager,
        )

    @action(detail=False, methods=["get"])
    def queue(self, request):
        return Response(QueueOrderSerializer(packing_queue(), many=True).data)

    def create(self, request):
        order = get_object_or_404(SalesOrder, pk=request.data.get("order"))
        active = order.packing_sessions.filter(
            status=PackingSession.Status.IN_PROGRESS
        ).first()
        if (
            active is not None
            and active.operator_id != request.user.id
            and not request.user.is_manager
        ):
            return Response(
                {"detail": "This order is already assigned to another operator."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            session = start_packing(order, user=request.user)
        except DjangoValidationError as exc:
            return _bad(exc)
        start_recording(session, user=request.user)
        return Response(self._detail(session), status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        return Response(self._detail(self.get_object()))

    @action(detail=True, methods=["post"])
    def scan(self, request, pk=None):
        session = self.get_object()
        try:
            scan = record_scan(
                session, request.data.get("barcode", ""), user=request.user
            )
        except DjangoValidationError as exc:
            return _bad(exc)
        return Response(
            {"scan": PackScanSerializer(scan).data, "session": self._detail(session)}
        )

    @action(detail=True, methods=["post"], url_path="confirm-line")
    def confirm_line(self, request, pk=None):
        session = self.get_object()
        line = get_object_or_404(SalesOrderLine, pk=request.data.get("line"))
        try:
            confirm_line_manual(session, line, user=request.user)
        except DjangoValidationError as exc:
            return _bad(exc)
        return Response(self._detail(session))

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        session = self.get_object()
        try:
            # Packing state, stock movements, and both downstream durable jobs
            # commit as one database unit. No external adapter runs here.
            with transaction.atomic():
                complete_packing(session, user=request.user)
                session.refresh_from_db()
                seal_recording(session, user=request.user)
                enqueue_shipment_booking(session.order)
        except DjangoValidationError as exc:
            return _bad(exc)
        session.refresh_from_db()
        return Response(self._detail(session))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        session = self.get_object()
        try:
            cancel_packing(session)
        except DjangoValidationError as exc:
            return _bad(exc)
        session.refresh_from_db()
        return Response(self._detail(session))

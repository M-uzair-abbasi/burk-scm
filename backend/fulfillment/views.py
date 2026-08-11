from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from logistics.services import book_shipment
from orders.models import SalesOrder, SalesOrderLine
from surveillance.services import capture_and_dispatch

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

    def get_object(self) -> PackingSession:
        return get_object_or_404(PackingSession, pk=self.kwargs["pk"])

    @action(detail=False, methods=["get"])
    def queue(self, request):
        return Response(QueueOrderSerializer(packing_queue(), many=True).data)

    def create(self, request):
        order = get_object_or_404(SalesOrder, pk=request.data.get("order"))
        try:
            session = start_packing(order, user=request.user)
        except DjangoValidationError as exc:
            return _bad(exc)
        return Response(session_detail(session), status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        return Response(session_detail(self.get_object()))

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
            {"scan": PackScanSerializer(scan).data, "session": session_detail(session)}
        )

    @action(detail=True, methods=["post"], url_path="confirm-line")
    def confirm_line(self, request, pk=None):
        session = self.get_object()
        line = get_object_or_404(SalesOrderLine, pk=request.data.get("line"))
        try:
            confirm_line_manual(session, line, user=request.user)
        except DjangoValidationError as exc:
            return _bad(exc)
        return Response(session_detail(session))

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        session = self.get_object()
        try:
            complete_packing(session, user=request.user)
        except DjangoValidationError as exc:
            return _bad(exc)
        session.refresh_from_db()
        # Module 4: record + compress + email/WhatsApp the packaging video. Never
        # lets a camera/ffmpeg/dispatch failure fail the pack itself — the order
        # is already sealed by this point; capture_and_dispatch degrades to a
        # FAILED PackagingRecording on error rather than raising.
        capture_and_dispatch(session, user=request.user)
        # Module 5: instant airway-bill booking, right after packing — no
        # manual data entry. Same never-fail-the-pack guarantee as above.
        try:
            book_shipment(session.order, user=request.user)
        except DjangoValidationError:
            pass
        return Response(session_detail(session))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        session = self.get_object()
        try:
            cancel_packing(session)
        except DjangoValidationError as exc:
            return _bad(exc)
        session.refresh_from_db()
        return Response(session_detail(session))

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.permissions import IsManagerOrReadOnly

from .models import PurchaseOrder
from .serializers import (
    PurchaseOrderSerializer,
    PurchaseOrderWriteSerializer,
    ReceiveSerializer,
    ReorderSerializer,
)
from .services import create_po, create_reorder_po, receive_po, submit_po


def _is_true(value) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """Purchase orders. Reads for everyone signed in; writes are manager-only.

    Exposes list/retrieve/create plus reorder/submit/receive actions. PUT/PATCH/
    DELETE are intentionally absent: a PO progresses through explicit status
    transitions, it is not free-form edited.
    """

    permission_classes = [IsManagerOrReadOnly]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = (
            PurchaseOrder.objects.select_related("supplier", "created_by")
            .prefetch_related("lines__product")
        )
        params = self.request.query_params
        status_param = params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        supplier = params.get("supplier")
        if supplier:
            qs = qs.filter(supplier_id=supplier)
        if _is_true(params.get("open")):
            qs = qs.filter(
                status__in=[
                    PurchaseOrder.Status.DRAFT,
                    PurchaseOrder.Status.SUBMITTED,
                    PurchaseOrder.Status.PARTIALLY_RECEIVED,
                ]
            )
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return PurchaseOrderWriteSerializer
        return PurchaseOrderSerializer

    def create(self, request, *args, **kwargs):
        write = PurchaseOrderWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        data = write.validated_data
        po = create_po(
            supplier=data["supplier"],
            user=request.user,
            expected_date=data.get("expected_date"),
            notes=data.get("notes", ""),
            lines=data["lines"],
        )
        return Response(
            PurchaseOrderSerializer(po).data, status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        """Draft a PO to replenish one product from its preferred supplier."""
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            po = create_reorder_po(
                product=data["product"],
                user=request.user,
                quantity=data.get("quantity"),
                supplier=data.get("supplier"),
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages[0] if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            PurchaseOrderSerializer(po).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        po = self.get_object()
        try:
            submit_po(po)
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages[0] if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(PurchaseOrderSerializer(po).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        po = self.get_object()
        serializer = ReceiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            receive_po(
                po,
                receipts=serializer.validated_data.get("receipts"),
                user=request.user,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": exc.messages[0] if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        po.refresh_from_db()
        return Response(PurchaseOrderSerializer(po).data)

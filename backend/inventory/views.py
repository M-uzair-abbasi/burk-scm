from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from common.permissions import IsManagerOrReadOnly

from .models import Category, Product, StockMovement
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    StockMovementCreateSerializer,
    StockMovementSerializer,
)
from .services import record_movement


def _is_true(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "yes", "on"}


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsManagerOrReadOnly]


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsManagerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["sku", "name", "barcode"]
    ordering_fields = ["sku", "name", "quantity_on_hand", "safety_stock", "created_at"]

    def get_queryset(self):
        qs = Product.objects.select_related("category")
        params = self.request.query_params

        if _is_true(params.get("low_stock")):
            qs = qs.low_stock()
        if _is_true(params.get("out_of_stock")):
            qs = qs.out_of_stock()

        category = params.get("category")
        if category:
            qs = qs.filter(category_id=category)

        is_active = params.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=_is_true(is_active))

        return qs


class StockMovementViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Append-only ledger endpoint: list and create only.

    No update/delete routes by design — a mistake is corrected by posting an
    opposing movement, never by editing history. Operators may record
    movements (that is their job on the floor), so this is IsAuthenticated,
    not manager-only.
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = StockMovement.objects.select_related("product", "created_by")
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return StockMovementCreateSerializer
        return StockMovementSerializer

    def create(self, request, *args, **kwargs):
        write = StockMovementCreateSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        data = write.validated_data
        try:
            movement = record_movement(
                product=data["product"],
                quantity_delta=data["quantity_delta"],
                reason=data["reason"],
                note=data.get("note", ""),
                allow_negative=data.get("allow_negative", False),
                user=request.user,
            )
        except DjangoValidationError as exc:
            # Oversell guard / zero delta surface as a clean 400, not a 500.
            return Response(
                {"detail": exc.messages[0] if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        read = StockMovementSerializer(movement)
        return Response(read.data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    """Top-of-dashboard counters. One round trip for the whole header row."""
    from purchasing.models import PurchaseOrder

    open_statuses = [
        PurchaseOrder.Status.DRAFT,
        PurchaseOrder.Status.SUBMITTED,
        PurchaseOrder.Status.PARTIALLY_RECEIVED,
    ]
    return Response(
        {
            "total_skus": Product.objects.active().count(),
            "low_stock_count": Product.objects.low_stock().count(),
            "out_of_stock_count": Product.objects.out_of_stock().count(),
            "open_po_count": PurchaseOrder.objects.filter(
                status__in=open_statuses
            ).count(),
        }
    )

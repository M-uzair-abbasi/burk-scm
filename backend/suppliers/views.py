from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from common.permissions import IsManagerOrReadOnly

from .models import Supplier, SupplierPriceTier, SupplierProduct
from .serializers import (
    SupplierPriceTierSerializer,
    SupplierProductSerializer,
    SupplierSerializer,
)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsManagerOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name", "city", "contact_person"]
    ordering_fields = ["name", "code", "default_lead_time_days"]


class SupplierProductViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierProductSerializer
    permission_classes = [IsManagerOrReadOnly]

    def get_queryset(self):
        qs = SupplierProduct.objects.select_related("supplier", "product").prefetch_related(
            "price_tiers"
        )
        params = self.request.query_params
        product = params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        supplier = params.get("supplier")
        if supplier:
            qs = qs.filter(supplier_id=supplier)
        return qs

    @action(detail=True, methods=["get"])
    def price(self, request, pk=None):
        """Resolve the tier unit price for a given quantity.

        GET /api/supplier-products/{id}/price/?quantity=N
        Returns null when the quantity is below every tier's minimum, which
        the caller must handle rather than assuming a price exists.
        """
        supplier_product = self.get_object()
        try:
            quantity = int(request.query_params.get("quantity", 0))
        except (TypeError, ValueError):
            quantity = 0
        unit_price = supplier_product.unit_price_for(quantity)
        return Response(
            {
                "quantity": quantity,
                "unit_price": unit_price,
                "lead_time_days": supplier_product.effective_lead_time_days,
            }
        )


class SupplierPriceTierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierPriceTierSerializer
    permission_classes = [IsManagerOrReadOnly]

    def get_queryset(self):
        qs = SupplierPriceTier.objects.all()
        supplier_product = self.request.query_params.get("supplier_product")
        if supplier_product:
            qs = qs.filter(supplier_product_id=supplier_product)
        return qs

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("suppliers", views.SupplierViewSet, basename="supplier")
router.register(
    "supplier-products", views.SupplierProductViewSet, basename="supplierproduct"
)
router.register("price-tiers", views.SupplierPriceTierViewSet, basename="pricetier")

urlpatterns = [
    path("", include(router.urls)),
]

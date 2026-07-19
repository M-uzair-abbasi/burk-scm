from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("purchase-orders", views.PurchaseOrderViewSet, basename="purchaseorder")

urlpatterns = [
    path("", include(router.urls)),
]

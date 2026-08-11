from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("shipments", views.ShipmentViewSet, basename="shipment")

urlpatterns = [
    path("", include(router.urls)),
]

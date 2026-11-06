from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("shipments", views.ShipmentViewSet, basename="shipment")

urlpatterns = [
    path("courier-webhooks/<str:courier>/", views.courier_webhook, name="courier-webhook"),
    path("", include(router.urls)),
]

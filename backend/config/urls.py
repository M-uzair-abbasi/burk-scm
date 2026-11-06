"""Root URL configuration for Burk.pk SCM-OVS."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("common.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("suppliers.urls")),
    path("api/", include("purchasing.urls")),
    path("api/", include("orders.urls")),
    path("api/", include("fulfillment.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("logistics.urls")),
    path("api/", include("surveillance.urls")),
]

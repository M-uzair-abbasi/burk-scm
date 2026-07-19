"""Root URL configuration for Burk.pk SCM-OVS.

Everything the frontend calls lives under /api/, which is what Next's
rewrites proxy forwards. /admin/ is served directly by Django.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("suppliers.urls")),
    path("api/", include("purchasing.urls")),
]

"""Root URL configuration for Burk.pk SCM-OVS.

Everything the frontend calls lives under /api/, which is what Next's
rewrites proxy forwards. /admin/ is served directly by Django. /media/ (Module 4
packaging-video clips) is served directly in DEBUG; a real deployment would hand
that off to nginx/S3 instead.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("suppliers.urls")),
    path("api/", include("purchasing.urls")),
    path("api/", include("orders.urls")),
    path("api/", include("fulfillment.urls")),
    path("api/", include("logistics.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

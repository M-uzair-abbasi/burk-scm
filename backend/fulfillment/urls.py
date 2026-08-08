from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("packing", views.PackingViewSet, basename="packing")

urlpatterns = [
    path("", include(router.urls)),
]

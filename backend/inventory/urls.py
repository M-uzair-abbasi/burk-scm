from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="product")
router.register("categories", views.CategoryViewSet, basename="category")
router.register("stock-movements", views.StockMovementViewSet, basename="stockmovement")

urlpatterns = [
    path("dashboard/summary/", views.dashboard_summary, name="dashboard-summary"),
    path("", include(router.urls)),
]

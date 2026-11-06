from django.urls import path

from .views import health, health_details, metrics

urlpatterns = [
    path("health/", health, name="operational-health"),
    path("health/details/", health_details, name="operational-health-details"),
    path("metrics/", metrics, name="operational-metrics"),
]

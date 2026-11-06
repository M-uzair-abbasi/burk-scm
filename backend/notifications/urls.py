from django.urls import path

from . import views

urlpatterns = [
    path(
        "notification-webhooks/<str:channel>/",
        views.notification_webhook,
        name="notification-webhook",
    ),
]

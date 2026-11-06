from django.urls import path

from .views import recording_video

urlpatterns = [
    path(
        "recordings/<int:pk>/video/",
        recording_video,
        name="recording-video",
    ),
]

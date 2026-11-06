from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .health import operational_health
from .metrics import operational_metrics
from .permissions import IsManager


@require_GET
def health(request):
    report = operational_health()
    public_report = {"ok": report["ok"], "checked_at": report["checked_at"]}
    return JsonResponse(public_report, status=200 if report["ok"] else 503)


@api_view(["GET"])
@permission_classes([IsManager])
def health_details(request):
    report = operational_health()
    return Response(report, status=200 if report["ok"] else 503)


@api_view(["GET"])
@permission_classes([IsManager])
def metrics(request):
    return Response(operational_metrics())

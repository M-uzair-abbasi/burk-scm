from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Channel, SalesOrder, SyncRun
from .serializers import (
    SalesOrderDetailSerializer,
    SalesOrderListSerializer,
    SyncRunSerializer,
)
from .services import queue_integrity, sync_all


def build_summary() -> dict:
    """Everything the queue header needs in one round trip: per-channel and
    per-status counts, the last sync per channel, and the live KPI-3 integrity
    block (dropped / duplicated / unique)."""
    by_channel = {}
    for value, label in Channel.choices:
        last = (
            SyncRun.objects.filter(channel=value)
            .order_by("-started_at", "-id")
            .first()
        )
        by_channel[value] = {
            "label": label,
            "count": SalesOrder.objects.filter(channel=value).count(),
            "last_sync": last.started_at if last else None,
            "last_run": SyncRunSerializer(last).data if last else None,
        }
    by_status = {
        value: SalesOrder.objects.filter(status=value).count()
        for value, _ in SalesOrder.Status.choices
    }
    return {
        "total_orders": SalesOrder.objects.count(),
        "by_channel": by_channel,
        "by_status": by_status,
        "integrity": queue_integrity(),
        "recent_runs": SyncRunSerializer(
            SyncRun.objects.all().order_by("-started_at", "-id")[:10], many=True
        ).data,
    }


class SalesOrderViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Unified customer-order queue: read-only list/retrieve plus sync/summary.

    Orders are pulled from channels, never authored here, so there is no
    create/update/delete. IsAuthenticated (not manager-gated): operators work the
    queue on the floor.
    """

    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "external_id", "customer_name", "customer_phone"]
    ordering_fields = ["placed_at", "ingested_at", "total", "reference"]

    def get_queryset(self):
        qs = SalesOrder.objects.prefetch_related("lines__product")
        params = self.request.query_params
        channel = params.get("channel")
        if channel:
            qs = qs.filter(channel=channel)
        status_param = params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return SalesOrderDetailSerializer
        return SalesOrderListSerializer

    @action(detail=False, methods=["post"])
    def sync(self, request):
        """'Sync now' — pull every channel feed into the queue and return the runs."""
        runs = sync_all(user=request.user)
        return Response(
            {
                "runs": SyncRunSerializer(runs, many=True).data,
                "summary": build_summary(),
            }
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(build_summary())

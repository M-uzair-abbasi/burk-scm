import os
import shutil
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from logistics.couriers import get_carrier
from notifications.services import DEFAULT_CHANNELS
from notifications.channels import get_channel
from notifications.reviews import get_review_link_provider
from operations.models import WorkItem, WorkerHeartbeat
from orders.connectors import CONNECTORS, get_connector
from surveillance.camera import get_camera


def _database_health():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 - health must report, not crash
        return {"ok": False, "error_class": exc.__class__.__name__}


def _worker_health(now):
    heartbeat = WorkerHeartbeat.objects.order_by("-last_seen_at").first()
    if heartbeat is None:
        return {"ok": False, "detail": "No worker heartbeat.", "age_seconds": None}
    age = max(0.0, (now - heartbeat.last_seen_at).total_seconds())
    return {
        "ok": age <= settings.WORKER_HEARTBEAT_MAX_AGE_SECONDS,
        "name": heartbeat.name,
        "age_seconds": round(age, 2),
        "last_claimed": heartbeat.last_claimed,
        "last_succeeded": heartbeat.last_succeeded,
        "last_failed": heartbeat.last_failed,
    }


def _backlog_health(now):
    due_filter = Q(
        status__in=[WorkItem.Status.PENDING, WorkItem.Status.RETRY],
        available_at__lte=now,
    ) | Q(
        status=WorkItem.Status.PROCESSING,
        lease_expires_at__lte=now,
    )
    due = WorkItem.objects.filter(due_filter)
    oldest = due.order_by("available_at").first()
    age = max(0.0, (now - oldest.available_at).total_seconds()) if oldest else 0.0
    failed = WorkItem.objects.filter(status=WorkItem.Status.FAILED).count()
    return {
        "ok": age <= settings.WORK_QUEUE_MAX_DUE_AGE_SECONDS and failed == 0,
        "due": due.count(),
        "oldest_due_age_seconds": round(age, 2),
        "failed": failed,
        "processing": WorkItem.objects.filter(
            status=WorkItem.Status.PROCESSING,
            lease_expires_at__gt=now,
        ).count(),
    }


def _media_health():
    root = Path(settings.MEDIA_ROOT)
    exists = root.exists() and root.is_dir()
    writable = exists and os.access(root, os.W_OK)
    free = shutil.disk_usage(root).free if exists else 0
    policy_ok = (
        settings.PACKAGING_COMPRESSED_RETENTION_SECONDS
        >= settings.PACKAGING_LINK_TTL_SECONDS
    )
    return {
        "ok": bool(
            exists
            and writable
            and free >= settings.MEDIA_MIN_FREE_BYTES
            and policy_ok
        ),
        "exists": exists,
        "writable": writable,
        "free_bytes": free,
        "retention_policy_ok": policy_ok,
    }


def _adapter_result(name, factory, *, configured_mode="unknown"):
    try:
        adapter = factory()
        result = adapter.health()
        return {"name": name, **result}
    except Exception as exc:  # noqa: BLE001 - readiness captures adapter outage
        return {
            "name": name,
            "ok": False,
            "mode": configured_mode,
            "error_class": exc.__class__.__name__,
        }


def _adapters_health():
    camera_backend = settings.PACKAGING_CAMERA_BACKEND
    courier_backend = settings.COURIER_BACKEND
    whatsapp_backend = settings.WHATSAPP_BACKEND
    review_backend = settings.REVIEW_LINK_BACKEND
    simulated_email_backends = {
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
    }
    details = [
        _adapter_result(
            "camera",
            get_camera,
            configured_mode=(
                "simulated" if camera_backend == "simulated" else "live"
            ),
        ),
        _adapter_result(
            "courier",
            get_carrier,
            configured_mode=(
                "simulated" if courier_backend == "simulated" else "live"
            ),
        ),
    ]
    details.extend(
        _adapter_result(
            f"notification.{name}",
            lambda channel=name: get_channel(channel),
            configured_mode=(
                (
                    "simulated"
                    if settings.EMAIL_BACKEND in simulated_email_backends
                    else "live"
                )
                if name == "email"
                else ("simulated" if whatsapp_backend == "simulated" else "live")
            ),
        )
        for name in DEFAULT_CHANNELS
    )
    details.extend(
        _adapter_result(
            f"orders.{name}",
            lambda channel=name: get_connector(channel),
            configured_mode=(
                "simulated"
                if settings.ORDER_CONNECTOR_BACKENDS.get(name) == "fixture"
                else "live"
            ),
        )
        for name in CONNECTORS
    )
    details.append(
        _adapter_result(
            "review",
            get_review_link_provider,
            configured_mode=(
                "simulated" if review_backend == "simulated" else "live"
            ),
        )
    )
    all_available = all(item.get("ok", False) for item in details)
    live_required = settings.REQUIRE_LIVE_INTEGRATIONS
    all_live = all(item.get("mode") == "live" for item in details)
    return {
        "ok": all_available and (not live_required or all_live),
        "live_required": live_required,
        "all_live": all_live,
        "details": details,
    }


def operational_health(*, now=None) -> dict:
    now = now or timezone.now()
    components = {
        "app": {"ok": True},
        "database": _database_health(),
        "worker": _worker_health(now),
        "backlog": _backlog_health(now),
        "media": _media_health(),
        "adapters": _adapters_health(),
    }
    return {
        "ok": all(component["ok"] for component in components.values()),
        "checked_at": now,
        "components": components,
    }

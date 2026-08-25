from django.db import migrations


def backfill_notification_jobs(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    WorkItem = apps.get_model("operations", "WorkItem")

    active_statuses = ("scheduled", "processing", "retrying")
    for notification in Notification.objects.filter(
        status__in=active_statuses
    ).iterator():
        available_at = (
            notification.next_attempt_at
            or notification.scheduled_for
            or notification.created_at
        )
        WorkItem.objects.get_or_create(
            key=f"send_notification:{notification.pk}",
            defaults={
                "kind": "send_notification",
                "payload": {"notification_id": notification.pk},
                "available_at": available_at,
                "max_attempts": 5,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0003_delivery_receipts"),
        ("operations", "0002_workitem_correlation_id"),
    ]

    operations = [
        migrations.RunPython(backfill_notification_jobs, migrations.RunPython.noop)
    ]


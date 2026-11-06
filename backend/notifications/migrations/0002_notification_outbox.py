from django.db import migrations, models


def populate_outbox_fields(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    for notification in Notification.objects.all().iterator():
        notification.idempotency_key = f"legacy:{notification.pk}"
        notification.acknowledged_at = notification.sent_at
        notification.attempt_count = 1 if notification.status in {"sent", "failed"} else 0
        notification.save(
            update_fields=[
                "idempotency_key",
                "acknowledged_at",
                "attempt_count",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="notification",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=96, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="acknowledged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="attempt_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="notification",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="notification",
            name="provider_message_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="notification",
            name="terminal_error_class",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AlterField(
            model_name="notification",
            name="status",
            field=models.CharField(
                choices=[
                    ("scheduled", "Scheduled"),
                    ("processing", "Processing"),
                    ("retrying", "Retrying"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="scheduled",
                max_length=16,
            ),
        ),
        migrations.RunPython(populate_outbox_fields, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="notification",
            name="idempotency_key",
            field=models.CharField(max_length=96, unique=True),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["status", "next_attempt_at"],
                name="notification_retry_due_idx",
            ),
        ),
    ]

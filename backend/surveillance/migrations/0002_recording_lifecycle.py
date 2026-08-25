from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("surveillance", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="packagingrecording",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("recording", "Recording"),
                    ("queued", "Queued for processing"),
                    ("processing", "Processing"),
                    ("retrying", "Retrying"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="packagingrecording",
            name="sealed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="camera_name",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="capture_handle",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="capture_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="capture_stopped_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="compressed_checksum",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="processing_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="raw_checksum",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="terminal_error_class",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]

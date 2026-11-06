from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("surveillance", "0002_recording_lifecycle")]

    operations = [
        migrations.AddField(
            model_name="packagingrecording",
            name="customer_link_token",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="customer_link_issued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

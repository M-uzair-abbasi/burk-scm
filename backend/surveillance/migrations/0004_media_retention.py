from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("surveillance", "0003_customer_link_token")]

    operations = [
        migrations.AddField(
            model_name="packagingrecording",
            name="raw_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="packagingrecording",
            name="compressed_deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

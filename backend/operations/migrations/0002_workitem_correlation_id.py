from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="workitem",
            name="correlation_id",
            field=models.CharField(blank=True, db_index=True, max_length=128),
        )
    ]

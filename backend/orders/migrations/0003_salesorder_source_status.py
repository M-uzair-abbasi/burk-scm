from django.db import migrations, models


def copy_existing_status(apps, schema_editor):
    SalesOrder = apps.get_model("orders", "SalesOrder")
    for order in SalesOrder.objects.only("id", "status").iterator():
        SalesOrder.objects.filter(pk=order.pk).update(source_status=order.status)


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_salesorderline_quantity_positive"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesorder",
            name="source_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("confirmed", "Confirmed"),
                    ("packed", "Packed"),
                    ("shipped", "Shipped"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                    ("returned", "Returned"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
        migrations.RunPython(
            copy_existing_status,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="salesorderline",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gt", 0)),
                name="sales_order_line_qty_positive",
            ),
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion


def populate_lead_time_snapshots(apps, schema_editor):
    PurchaseOrderLine = apps.get_model("purchasing", "PurchaseOrderLine")
    for line in PurchaseOrderLine.objects.select_related(
        "purchase_order__supplier"
    ).iterator():
        line.effective_lead_time_days = (
            line.purchase_order.supplier.default_lead_time_days
        )
        line.save(update_fields=["effective_lead_time_days"])


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0001_initial"),
        ("suppliers", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaseorderline",
            name="supplier_product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="purchase_order_lines",
                to="suppliers.supplierproduct",
            ),
        ),
        migrations.AddField(
            model_name="purchaseorderline",
            name="effective_lead_time_days",
            field=models.PositiveSmallIntegerField(null=True),
        ),
        migrations.AddField(
            model_name="purchaseorderline",
            name="price_tier_min_quantity",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(
            populate_lead_time_snapshots,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="purchaseorderline",
            name="effective_lead_time_days",
            field=models.PositiveSmallIntegerField(),
        ),
    ]

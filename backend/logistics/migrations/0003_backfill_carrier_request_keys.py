from django.db import migrations, models


def backfill_request_keys(apps, schema_editor):
    Shipment = apps.get_model("logistics", "Shipment")
    for shipment in Shipment.objects.select_related("order").iterator():
        order = shipment.order
        key = f"burk-shipment-order-{order.pk}"
        shipment.request_idempotency_key = key
        if not shipment.booking_request:
            shipment.booking_request = {
                "order_id": order.pk,
                "order_reference": order.reference,
                "external_order_id": order.external_id,
                "recipient_name": order.customer_name,
                "phone": order.customer_phone,
                "address_line1": (
                    order.shipping_address_line1 or order.shipping_address
                ),
                "address_line2": order.shipping_address_line2,
                "city": order.shipping_city,
                "province": order.shipping_province,
                "postal_code": order.shipping_postal_code,
                "country": order.shipping_country or "PK",
                "item_count": order.item_count,
                "currency": order.currency,
                "declared_value": format(order.total, "f"),
                "cod_amount": format(order.cod_amount, "f"),
                "payment_mode": order.payment_mode,
                "service_type": order.shipping_service_type,
                "pickup_account": order.pickup_account,
                "customer_instructions": order.customer_instructions,
                "weight_kg": format(order.parcel_weight_kg, "f"),
                "length_cm": format(order.parcel_length_cm, "f"),
                "width_cm": format(order.parcel_width_cm, "f"),
                "height_cm": format(order.parcel_height_cm, "f"),
                "idempotency_key": key,
            }
        shipment.save(
            update_fields=["request_idempotency_key", "booking_request"]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_carrier_shipping_contract"),
        ("logistics", "0002_carrier_shipping_contract"),
    ]

    operations = [
        migrations.RunPython(backfill_request_keys, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="shipment",
            name="request_idempotency_key",
            field=models.CharField(max_length=255, unique=True),
        ),
    ]

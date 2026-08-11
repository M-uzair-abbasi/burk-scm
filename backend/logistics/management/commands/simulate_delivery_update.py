"""Simulate a courier status webhook — for live demos, standing in for the real
Leopard/TCS/Trax/M&P delivery-status callback (mirrors simulate_new_order for
channel feeds). Advancing to `delivered` triggers Module 6's review reminder.
"""

from django.core.management.base import BaseCommand, CommandError

from logistics.models import Shipment
from logistics.services import advance_shipment
from orders.models import SalesOrder


class Command(BaseCommand):
    help = "Advance a shipment's status as if a courier webhook fired (in_transit or delivered)."

    def add_arguments(self, parser):
        parser.add_argument("order_reference", help="SalesOrder.reference, e.g. SO-00001")
        parser.add_argument(
            "--status",
            choices=[Shipment.Status.IN_TRANSIT, Shipment.Status.DELIVERED],
            default=Shipment.Status.IN_TRANSIT,
        )

    def handle(self, *args, **options):
        try:
            order = SalesOrder.objects.get(reference=options["order_reference"])
        except SalesOrder.DoesNotExist:
            raise CommandError(f"No order with reference {options['order_reference']!r}.")
        shipment = getattr(order, "shipment", None)
        if shipment is None:
            raise CommandError(f"{order.reference} has no shipment booked yet.")

        event = advance_shipment(shipment, options["status"])
        self.stdout.write(
            self.style.SUCCESS(
                f"{shipment.tracking_number} -> {event.get_status_display()} "
                f"(order {order.reference})."
            )
        )
        if options["status"] == Shipment.Status.DELIVERED:
            self.stdout.write(
                "Review reminder scheduled — run `dispatch_scheduled_notifications` "
                "after the delay to send it."
            )

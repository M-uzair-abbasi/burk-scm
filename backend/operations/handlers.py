"""Background-work handler registry.

Feature apps register handlers lazily here through explicit imports in
`get_handler`, avoiding model-import cycles during Django startup.
"""


def get_handler(kind: str):
    if kind == "send_notification":
        from notifications.services import process_notification_work

        return process_notification_work
    if kind == "process_packaging_recording":
        from surveillance.services import process_recording_work

        return process_recording_work
    if kind == "book_shipment":
        from logistics.services import process_shipment_booking_work

        return process_shipment_booking_work
    raise ValueError(f"No work handler is registered for {kind!r}.")

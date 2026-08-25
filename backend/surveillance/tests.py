"""Module 4 recording lifecycle and durable processing tests."""

import tempfile
from datetime import timedelta
from hashlib import sha256
from io import StringIO
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from fulfillment.services import complete_packing, record_scan, start_packing
from inventory.models import Product, StockMovement
from inventory.services import record_movement
from notifications.models import Notification
from operations.models import WorkItem
from operations.services import process_due
from orders.models import SalesOrder, SalesOrderLine
from surveillance.camera.base import CaptureHandle
from surveillance.models import PackagingRecording
from surveillance.signing import customer_video_url
from surveillance.services import (
    PROCESS_RECORDING_KIND,
    cleanup_packaging_media,
    seal_recording,
    start_recording,
)


def make_product(sku, barcode, stock=10):
    product = Product.objects.create(sku=sku, name=sku, barcode=barcode)
    record_movement(
        product=product,
        quantity_delta=stock,
        reason=StockMovement.Reason.INITIAL,
    )
    return product


def make_order(ref="SO-V0001", lines=None):
    lines = lines or []
    order = SalesOrder.objects.create(
        channel="burk",
        external_id=ref,
        reference=ref,
        status="pending",
        customer_name="Video Buyer",
        customer_email="video.buyer@example.invalid",
        customer_phone="+923001230001",
        shipping_address="12 Test Street, Lahore",
        shipping_address_line1="12 Test Street",
        shipping_city="Lahore",
        shipping_province="Punjab",
        shipping_country="PK",
        item_count=sum(qty for _product, qty in lines),
    )
    for product, qty in lines:
        SalesOrderLine.objects.create(
            order=order,
            sku=product.sku,
            product=product,
            product_name=product.sku,
            quantity=qty,
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00") * qty,
        )
    return order


def active_recording_session(ref="SO-V0001"):
    product = make_product(f"BRK-{ref}", f"55{Product.objects.count():05d}")
    order = make_order(ref=ref, lines=[(product, 1)])
    session = start_packing(order)
    start_recording(session)
    return session, product


class RecordingLifecycleTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)

    def test_start_recording_marks_capture_active_without_running_ffmpeg(self):
        product = make_product("BRK-START", "5551001")
        session = start_packing(make_order("SO-V-START", [(product, 1)]))
        camera = Mock()
        camera.name = "test-camera"
        camera.start.return_value = CaptureHandle(token="capture-1")

        with (
            patch("surveillance.services.get_camera", return_value=camera),
            patch("surveillance.services._compress") as compress,
        ):
            recording = start_recording(session)

        camera.start.assert_called_once()
        compress.assert_not_called()
        self.assertEqual(recording.status, PackagingRecording.Status.RECORDING)
        self.assertIsNotNone(recording.capture_started_at)
        self.assertIsNone(recording.sealed_at)
        self.assertEqual(recording.capture_handle["token"], "capture-1")
        self.assertNotEqual(recording.raw_path, recording.compressed_path)

    def test_seal_is_idempotent_and_only_enqueues_processing(self):
        session, _ = active_recording_session("SO-V-SEAL")
        record_scan(session, session.order.lines.get().product.barcode)
        complete_packing(session)
        session.refresh_from_db()

        with (
            patch("surveillance.services._compress") as compress,
            patch("surveillance.services.dispatch_notification") as dispatch,
        ):
            first = seal_recording(session)
            second = seal_recording(session)

        compress.assert_not_called()
        dispatch.assert_not_called()
        self.assertEqual(first.id, second.id)
        first.refresh_from_db()
        self.assertEqual(first.status, PackagingRecording.Status.QUEUED)
        self.assertEqual(first.sealed_at, session.completed_at)
        self.assertIsNotNone(first.capture_stopped_at)
        self.assertEqual(
            WorkItem.objects.filter(kind=PROCESS_RECORDING_KIND).count(), 1
        )

    def test_worker_stops_capture_compresses_and_enqueues_notifications(self):
        session, _ = active_recording_session("SO-V-WORKER")
        record_scan(session, session.order.lines.get().product.barcode)
        complete_packing(session)
        session.refresh_from_db()
        recording = seal_recording(session)

        process_due(limit=1, worker_name="recording-test")

        recording.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.READY)
        self.assertGreater(recording.raw_size_bytes, 0)
        self.assertGreater(recording.compressed_size_bytes, 0)
        self.assertLess(recording.compressed_size_bytes, recording.raw_size_bytes)
        self.assertTrue(recording.raw_checksum)
        self.assertTrue(recording.compressed_checksum)
        self.assertEqual(recording.processing_attempts, 1)
        self.assertEqual(
            Notification.objects.filter(
                order=session.order,
                kind=Notification.Kind.PACKAGING_VIDEO,
            ).count(),
            2,
        )
        self.assertEqual(
            WorkItem.objects.filter(kind="send_notification").count(), 2
        )

    def test_failed_compression_retries_without_second_stock_decrement(self):
        session, product = active_recording_session("SO-V-RETRY")
        barcode = session.order.lines.get().product.barcode
        record_scan(session, barcode)
        complete_packing(session)
        session.refresh_from_db()
        recording = seal_recording(session)

        from surveillance.services import _compress as real_compress

        with patch(
            "surveillance.services._compress",
            side_effect=RuntimeError("ffmpeg temporarily unavailable"),
        ):
            process_due(limit=1)

        recording.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.RETRYING)
        self.assertEqual(recording.processing_attempts, 1)

        WorkItem.objects.filter(kind=PROCESS_RECORDING_KIND).update(
            available_at=timezone.now()
        )
        with patch("surveillance.services._compress", side_effect=real_compress):
            process_due(limit=1)

        recording.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.READY)
        self.assertEqual(recording.processing_attempts, 2)
        self.assertEqual(product.quantity_on_hand, 9)
        self.assertEqual(
            product.movements.filter(reason=StockMovement.Reason.SALE).count(), 1
        )
        self.assertEqual(
            Notification.objects.filter(
                order=session.order,
                kind=Notification.Kind.PACKAGING_VIDEO,
            ).count(),
            2,
        )

    @override_settings(PACKAGING_PROCESS_MAX_ATTEMPTS=1)
    def test_terminal_processing_failure_remains_visible(self):
        session, _ = active_recording_session("SO-V-TERMINAL")
        record_scan(session, session.order.lines.get().product.barcode)
        complete_packing(session)
        session.refresh_from_db()
        recording = seal_recording(session)

        with patch(
            "surveillance.services._compress", side_effect=RuntimeError("bad media")
        ):
            process_due(limit=1)

        recording.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.FAILED)
        self.assertEqual(recording.processing_attempts, 1)
        self.assertEqual(recording.terminal_error_class, "RuntimeError")
        self.assertIn("bad media", recording.error)

    def test_notification_enqueue_retry_reuses_the_issued_customer_token(self):
        session, _ = active_recording_session("SO-V-LINK-RETRY")
        record_scan(session, session.order.lines.get().product.barcode)
        complete_packing(session)
        session.refresh_from_db()
        recording = seal_recording(session)

        with patch(
            "surveillance.services.dispatch_notification",
            side_effect=RuntimeError("outbox temporarily unavailable"),
        ):
            process_due(limit=1)

        recording.refresh_from_db()
        issued_token = recording.customer_link_token
        self.assertTrue(issued_token)
        WorkItem.objects.filter(kind=PROCESS_RECORDING_KIND).update(
            available_at=timezone.now()
        )
        process_due(limit=1)

        recording.refresh_from_db()
        notification = Notification.objects.filter(
            order=session.order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            channel=Notification.Channel.EMAIL,
        ).get()
        self.assertEqual(recording.status, PackagingRecording.Status.READY)
        self.assertEqual(recording.customer_link_token, issued_token)
        parsed = urlsplit(notification.payload["video_url"])
        self.assertEqual(parse_qs(parsed.query)["token"], [issued_token])


class PackingRecordingCompositionTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)
        self.user = get_user_model().objects.create_user(
            username="video-operator", password="password"
        )
        self.product = make_product("BRK-API-VIDEO", "5552001")
        self.order = make_order("SO-V-API", [(self.product, 1)])
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_api_start_begins_capture_and_complete_only_queues_work(self):
        start_response = self.client.post(
            "/api/packing/", {"order": self.order.id}, format="json"
        )
        self.assertEqual(start_response.status_code, 201)
        session_id = start_response.data["id"]
        recording = PackagingRecording.objects.get(session_id=session_id)
        self.assertEqual(recording.status, PackagingRecording.Status.RECORDING)

        scan_response = self.client.post(
            f"/api/packing/{session_id}/scan/",
            {"barcode": self.product.barcode},
            format="json",
        )
        self.assertEqual(scan_response.status_code, 200)

        with (
            patch("surveillance.services._compress") as compress,
            patch("notifications.services.get_channel") as get_channel,
            patch("logistics.services.get_carrier") as get_carrier,
        ):
            complete_response = self.client.post(
                f"/api/packing/{session_id}/complete/", {}, format="json"
            )

        self.assertEqual(complete_response.status_code, 200)
        compress.assert_not_called()
        get_channel.assert_not_called()
        get_carrier.assert_not_called()
        recording.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.QUEUED)
        self.assertEqual(
            WorkItem.objects.filter(kind=PROCESS_RECORDING_KIND).count(), 1
        )
        self.assertEqual(
            WorkItem.objects.filter(kind="book_shipment").count(), 1
        )

    def test_job_enqueue_failure_rolls_back_pack_and_stock(self):
        start_response = self.client.post(
            "/api/packing/", {"order": self.order.id}, format="json"
        )
        session_id = start_response.data["id"]
        self.client.post(
            f"/api/packing/{session_id}/scan/",
            {"barcode": self.product.barcode},
            format="json",
        )

        with (
            patch(
                "fulfillment.views.enqueue_shipment_booking",
                side_effect=RuntimeError("work queue unavailable"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.client.post(
                f"/api/packing/{session_id}/complete/", {}, format="json"
            )

        self.product.refresh_from_db()
        session = self.order.packing_sessions.get(pk=session_id)
        self.order.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, 10)
        self.assertEqual(session.status, "in_progress")
        self.assertEqual(self.order.status, SalesOrder.Status.PENDING)
        self.assertFalse(WorkItem.objects.exists())


@override_settings(PUBLIC_APP_ORIGIN="https://scm.example.test")
class MediaAuthorizationTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)

        User = get_user_model()
        self.owner = User.objects.create_user(
            username="media-owner", password="password"
        )
        self.other = User.objects.create_user(
            username="media-other", password="password"
        )
        self.manager = User.objects.create_user(
            username="media-manager", password="password", role=User.Role.MANAGER
        )
        product = make_product("BRK-MEDIA", "5553001")
        self.order = make_order("SO-V-MEDIA", [(product, 1)])
        session = start_packing(self.order, user=self.owner)
        content = b"safe-compressed-video-bytes"
        relative = "packaging_videos/compressed/secure-test.mp4"
        absolute = Path(self._tmp.name, relative)
        absolute.parent.mkdir(parents=True)
        absolute.write_bytes(content)
        self.content = content
        self.recording = PackagingRecording.objects.create(
            session=session,
            status=PackagingRecording.Status.READY,
            compressed_path=relative,
            compressed_size_bytes=len(content),
            compressed_checksum=sha256(content).hexdigest(),
            sealed_at=timezone.now(),
            compressed_at=timezone.now(),
        )
        self.path = f"/api/recordings/{self.recording.id}/video/"

    @staticmethod
    def _local_path(url):
        parsed = urlsplit(url)
        return parsed.path + (f"?{parsed.query}" if parsed.query else "")

    @staticmethod
    def _body(response):
        return b"".join(response.streaming_content)

    def test_anonymous_without_token_is_denied(self):
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 403)

    def test_bad_and_expired_customer_tokens_are_denied(self):
        bad = self.client.get(f"{self.path}?token=not-a-valid-signature")
        self.assertEqual(bad.status_code, 403)

        with patch("django.core.signing.time.time", return_value=1_000):
            url = customer_video_url(self.recording)
        with (
            override_settings(PACKAGING_LINK_TTL_SECONDS=60),
            patch("django.core.signing.time.time", return_value=1_061),
        ):
            expired = self.client.get(self._local_path(url))
        self.assertEqual(expired.status_code, 403)

    def test_valid_customer_token_streams_only_the_compressed_file(self):
        response = self.client.get(
            self._local_path(customer_video_url(self.recording))
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "video/mp4")
        self.assertEqual(self._body(response), self.content)

    def test_owner_and_manager_can_stream_without_customer_token(self):
        for user in (self.owner, self.manager):
            self.client.force_login(user)
            response = self.client.get(self.path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self._body(response), self.content)
            self.client.logout()

    def test_non_owner_operator_is_denied(self):
        self.client.force_login(self.other)
        response = self.client.get(self.path)
        self.assertEqual(response.status_code, 403)

    def test_staff_order_api_never_leaks_the_customer_bearer_token(self):
        from notifications.services import dispatch

        signed_url = customer_video_url(self.recording)
        dispatch(
            self.order,
            kind=Notification.Kind.PACKAGING_VIDEO,
            reference_event_at=self.recording.sealed_at,
            event_key="media-redaction-test",
            payload={"video_url": signed_url},
        )
        self.client.force_login(self.other)

        response = self.client.get(f"/api/orders/{self.order.id}/")

        self.assertEqual(response.status_code, 200)
        exposed = response.json()["notifications"][0]["payload"]["video_url"]
        self.assertEqual(exposed, self.path)
        self.assertNotIn("token=", response.content.decode())

    def test_range_request_is_supported_for_video_playback(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.path, HTTP_RANGE="bytes=5-14")
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response["Content-Range"], f"bytes 5-14/{len(self.content)}")
        self.assertEqual(self._body(response), self.content[5:15])

    def test_raw_and_old_static_media_paths_are_never_routed(self):
        self.client.force_login(self.manager)
        self.assertEqual(
            self.client.get(f"/api/recordings/{self.recording.id}/raw/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/media/{self.recording.compressed_path}").status_code,
            404,
        )

    def test_tampered_compressed_file_is_not_streamed(self):
        absolute = Path(self._tmp.name, self.recording.compressed_path)
        absolute.write_bytes(b"tampered")
        self.client.force_login(self.owner)

        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 404)

    def test_symlinked_compressed_file_is_never_streamed_even_within_media_root(self):
        absolute = Path(self._tmp.name, self.recording.compressed_path)
        target = Path(self._tmp.name, "private-target.mp4")
        target.write_bytes(self.content)
        absolute.unlink()
        absolute.symlink_to(target)
        self.client.force_login(self.owner)

        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 404)


@override_settings(
    PACKAGING_RAW_RETENTION_SECONDS=100,
    PACKAGING_COMPRESSED_RETENTION_SECONDS=1_000,
    PACKAGING_LINK_TTL_SECONDS=900,
)
class MediaRetentionTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.media_root = Path(self._tmp.name, "media")
        self.media_root.mkdir()
        self._override = override_settings(MEDIA_ROOT=self.media_root)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)

        product = make_product("BRK-RETENTION", "5554001")
        order = make_order("SO-V-RETENTION", [(product, 1)])
        session = start_packing(order)
        self.now = timezone.now()
        self.raw_path = "packaging_videos/raw/retention.mp4"
        self.compressed_path = "packaging_videos/compressed/retention.mp4"
        for relative, content in (
            (self.raw_path, b"raw-video"),
            (self.compressed_path, b"compressed-video"),
        ):
            absolute = self.media_root / relative
            absolute.parent.mkdir(parents=True, exist_ok=True)
            absolute.write_bytes(content)
        self.unrelated = self.media_root / "unrelated.txt"
        self.unrelated.write_text("do not delete")
        self.recording = PackagingRecording.objects.create(
            session=session,
            status=PackagingRecording.Status.READY,
            raw_path=self.raw_path,
            compressed_path=self.compressed_path,
            sealed_at=self.now - timedelta(seconds=500),
            captured_at=self.now - timedelta(seconds=500),
            compressed_at=self.now - timedelta(seconds=500),
        )

    def test_dry_run_reports_due_raw_without_deleting_or_marking(self):
        report = cleanup_packaging_media(now=self.now, dry_run=True)

        self.recording.refresh_from_db()
        self.assertEqual(report["raw_due"], 1)
        self.assertEqual(report["compressed_due"], 0)
        self.assertTrue((self.media_root / self.raw_path).exists())
        self.assertIsNone(self.recording.raw_deleted_at)

    def test_cleanup_deletes_only_due_file_and_retains_audit_row(self):
        report = cleanup_packaging_media(now=self.now)

        self.recording.refresh_from_db()
        self.assertEqual(report["deleted"], 1)
        self.assertFalse((self.media_root / self.raw_path).exists())
        self.assertTrue((self.media_root / self.compressed_path).exists())
        self.assertTrue(self.unrelated.exists())
        self.assertIsNotNone(self.recording.raw_deleted_at)
        self.assertIsNone(self.recording.compressed_deleted_at)
        self.assertTrue(PackagingRecording.objects.filter(pk=self.recording.pk).exists())

    def test_compressed_cleanup_and_repeated_run_are_idempotent(self):
        PackagingRecording.objects.filter(pk=self.recording.pk).update(
            compressed_at=self.now - timedelta(seconds=2_000)
        )

        first = cleanup_packaging_media(now=self.now)
        second = cleanup_packaging_media(now=self.now)

        self.recording.refresh_from_db()
        self.assertEqual(first["deleted"], 2)
        self.assertEqual(second["deleted"], 0)
        self.assertIsNotNone(self.recording.raw_deleted_at)
        self.assertIsNotNone(self.recording.compressed_deleted_at)
        self.assertTrue(self.unrelated.exists())

    def test_traversal_path_is_reported_and_never_deleted(self):
        outside = Path(self._tmp.name, "outside.mp4")
        outside.write_bytes(b"outside")
        PackagingRecording.objects.filter(pk=self.recording.pk).update(
            raw_path="../outside.mp4"
        )

        report = cleanup_packaging_media(now=self.now)

        self.recording.refresh_from_db()
        self.assertTrue(outside.exists())
        self.assertEqual(report["unsafe"], 1)
        self.assertIsNone(self.recording.raw_deleted_at)

    def test_symlink_cannot_escape_or_redirect_cleanup(self):
        target = self.media_root / "unrelated-target.mp4"
        target.write_bytes(b"preserve")
        link = self.media_root / "packaging_videos/raw/link.mp4"
        link.symlink_to(target)
        PackagingRecording.objects.filter(pk=self.recording.pk).update(
            raw_path="packaging_videos/raw/link.mp4"
        )

        report = cleanup_packaging_media(now=self.now)

        self.assertTrue(target.exists())
        self.assertTrue(link.is_symlink())
        self.assertEqual(report["unsafe"], 1)

    def test_check_mode_fails_on_backlog_then_passes_after_cleanup(self):
        with self.assertRaises(SystemExit) as raised:
            call_command("cleanup_packaging_media", "--check", stdout=StringIO())
        self.assertEqual(raised.exception.code, 1)
        self.assertTrue((self.media_root / self.raw_path).exists())

        cleanup_packaging_media(now=timezone.now())

        call_command("cleanup_packaging_media", "--check", stdout=StringIO())

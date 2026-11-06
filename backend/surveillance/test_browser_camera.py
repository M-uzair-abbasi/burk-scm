"""Tests for the browser-camera adapter and the upload it depends on.

Unlike the simulated/hardware adapters, this one never generates its own clip
-- it only ever looks at whatever the packer's browser has already uploaded.
These tests prove both halves: the adapter's stop()/recover() wait-and-probe
behavior, and the full pipeline once a real upload has landed.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from fulfillment.models import PackingSession
from fulfillment.services import complete_packing, record_scan, start_packing
from inventory.models import Product, StockMovement
from inventory.services import record_movement
from notifications.models import Notification
from operations.services import process_due
from orders.models import SalesOrder, SalesOrderLine
from surveillance.camera.base import CaptureHandle
from surveillance.camera.browser import BrowserCameraAdapter
from surveillance.ffmpeg import detect_container, run_ffmpeg
from surveillance.models import PackagingRecording
from surveillance.services import save_uploaded_recording, seal_recording, start_recording

LIVE_SETTINGS = dict(PACKAGING_CAMERA_BACKEND="browser")


def make_product(sku, barcode, stock=10):
    product = Product.objects.create(sku=sku, name=sku, barcode=barcode)
    record_movement(
        product=product,
        quantity_delta=stock,
        reason=StockMovement.Reason.INITIAL,
    )
    return product


def make_order(ref, lines):
    order = SalesOrder.objects.create(
        channel="burk",
        external_id=ref,
        reference=ref,
        status="pending",
        customer_name="Browser Buyer",
        customer_email="browser.buyer@example.invalid",
        customer_phone="+923001230099",
        shipping_address="1 Test Street, Lahore",
        shipping_address_line1="1 Test Street",
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


def write_real_clip(path: str, duration_seconds: float = 2.0) -> None:
    """A genuinely decodable short clip -- ffprobe needs real media, not bytes."""
    run_ffmpeg(
        [
            "-f", "lavfi",
            "-i", f"testsrc2=size=320x240:rate=15:duration={duration_seconds}",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            "-an",
            path,
        ]
    )


@override_settings(**LIVE_SETTINGS)
class BrowserCameraAdapterTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.adapter = BrowserCameraAdapter()
        self.product = make_product("BRK-BROWSER-ADAPTER", "5560001")
        self.order = make_order("SO-BROWSER-ADAPTER", [(self.product, 1)])
        self.session = start_packing(self.order)

    def test_health_is_always_ok_with_no_network_call(self):
        self.assertEqual(
            self.adapter.health(),
            {"ok": True, "mode": "live", "adapter": "browser"},
        )

    def test_start_returns_a_handle_without_touching_the_filesystem(self):
        out_path = str(Path(self._tmp.name) / "never-created.mp4")
        handle = self.adapter.start(self.session, out_path)

        self.assertIsInstance(handle, CaptureHandle)
        self.assertIn(str(self.session.pk), handle.token)
        self.assertFalse(Path(out_path).exists())

    def test_stop_raises_a_retryable_error_when_nothing_has_been_uploaded_yet(self):
        out_path = str(Path(self._tmp.name) / "missing.mp4")

        with self.assertRaisesMessage(
            RuntimeError, "has not been uploaded for this pack yet"
        ):
            self.adapter.stop(self.session, out_path, CaptureHandle(token="t"))

    def test_stop_probes_duration_once_the_upload_has_landed(self):
        out_path = str(Path(self._tmp.name) / "uploaded.mp4")
        write_real_clip(out_path, duration_seconds=2.0)

        result = self.adapter.stop(self.session, out_path, CaptureHandle(token="t"))

        self.assertAlmostEqual(result.duration_seconds, 2.0, delta=0.2)

    def test_recover_behaves_like_stop(self):
        out_path = str(Path(self._tmp.name) / "recovered.mp4")
        write_real_clip(out_path, duration_seconds=1.0)

        result = self.adapter.recover(self.session, out_path)

        self.assertAlmostEqual(result.duration_seconds, 1.0, delta=0.2)


@override_settings(**LIVE_SETTINGS)
class SaveUploadedRecordingTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)
        self.product = make_product("BRK-BROWSER-SAVE", "5560002")
        self.order = make_order("SO-BROWSER-SAVE", [(self.product, 1)])

    def test_rejects_upload_when_recording_was_never_started(self):
        session = start_packing(self.order)

        class _Upload:
            size = 4

            def chunks(self):
                yield b"test"

        with self.assertRaises(ValidationError):
            save_uploaded_recording(session, _Upload())

    def test_a_late_upload_after_sealing_is_still_accepted_before_processing(self):
        """Sealing alone isn't the cutoff -- the worker retries a sealed pack
        with no upload yet, so a late upload has to still be able to rescue
        it. See test_sealing_before_the_upload_lands_retries_until_it_does
        in BrowserRecordingEndToEndTests for the full worker-side proof."""
        session = start_packing(self.order)
        start_recording(session)
        record_scan(session, self.product.barcode)
        complete_packing(session)
        session.refresh_from_db()
        seal_recording(session)
        session.refresh_from_db()  # drop the pre-seal cached .recording

        class _Upload:
            size = 4

            def read(self, n=-1):
                data = b"\x1a\x45\xdf\xa3"
                return data[:n] if n >= 0 else data

            def seek(self, _offset):
                pass

            def chunks(self):
                yield b"\x1a\x45\xdf\xa3"

        recording = save_uploaded_recording(session, _Upload())
        self.assertTrue(recording.raw_checksum)

    def test_rejects_upload_once_the_recording_has_already_been_processed(self):
        session = start_packing(self.order)
        start_recording(session)
        record_scan(session, self.product.barcode)
        complete_packing(session)
        session.refresh_from_db()
        seal_recording(session)
        session.refresh_from_db()
        # Simulate the worker having already consumed a version of this clip.
        session.recording.duration_seconds = 3.0
        session.recording.save(update_fields=["duration_seconds"])

        class _Upload:
            size = 4

            def chunks(self):
                yield b"test"

        with self.assertRaises(ValidationError):
            save_uploaded_recording(session, _Upload())

    def test_rejects_an_upload_that_is_not_actually_a_video(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        session = start_packing(self.order)
        start_recording(session)
        not_a_video = SimpleUploadedFile(
            "clip.webm", b"nothing but plain text here", content_type="video/webm"
        )

        with self.assertRaises(ValidationError):
            save_uploaded_recording(session, not_a_video)

        raw_abs = Path(self._tmp.name) / getattr(session, "recording").raw_path
        self.assertFalse(raw_abs.exists())

    def test_locked_recheck_catches_processing_that_finished_during_the_write(self):
        """A caller holding a Python object fetched before the worker
        processed this recording (e.g. a slow upload request) must not be
        able to use that staleness to overwrite already-trusted evidence --
        the lock inside save_uploaded_recording has to re-read the real
        current state, not trust what the caller's object says."""
        session = start_packing(self.order)
        start_recording(session)
        # Stands in for a second, concurrent request that fetched its own
        # copy of the session (and cached its .recording) before anyone else
        # processed this recording.
        stale_session = PackingSession.objects.get(pk=session.pk)
        self.assertIsNone(stale_session.recording.duration_seconds)  # cache it

        # The recording gets processed for real in the DB while that
        # request's (slow) upload write is still in flight.
        session.recording.duration_seconds = 2.5
        session.recording.raw_checksum = "deadbeef"
        session.recording.save(update_fields=["duration_seconds", "raw_checksum"])

        class _Upload:
            size = 4

            def read(self, n=-1):
                data = b"\x1a\x45\xdf\xa3"
                return data[:n] if n >= 0 else data

            def seek(self, _offset):
                pass

            def chunks(self):
                yield b"\x1a\x45\xdf\xa3"

        with self.assertRaises(ValidationError):
            save_uploaded_recording(stale_session, _Upload())

        # Nothing got left behind from the rejected write.
        self.assertEqual(list(Path(self._tmp.name).glob("**/*.part-*")), [])


class DetectContainerTests(TestCase):
    """ffmpeg/ffprobe must never be left to auto-detect an untrusted file's
    format -- that's the mechanism behind known ffmpeg SSRF/local-file-read
    bugs. detect_container() pins the format from real magic bytes instead."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def test_detects_a_real_mp4_clip(self):
        path = str(Path(self._tmp.name) / "clip.mp4")
        write_real_clip(path, duration_seconds=0.5)

        self.assertEqual(detect_container(path), "mp4")

    def test_rejects_a_file_with_no_recognizable_header(self):
        path = Path(self._tmp.name) / "not-a-video.bin"
        path.write_bytes(b"concat:/etc/passwd|http://169.254.169.254/latest/meta-data/")

        with self.assertRaises(RuntimeError):
            detect_container(str(path))


@override_settings(**LIVE_SETTINGS)
class BrowserRecordingEndToEndTests(TestCase):
    """The full chain: browser upload -> seal -> worker -> customer notification."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._tmp.name)
        self._override.enable()
        self.addCleanup(self._override.disable)
        self.addCleanup(self._tmp.cleanup)

    def test_uploaded_clip_is_compressed_and_dispatched(self):
        product = make_product("BRK-BROWSER-E2E", "5560003")
        order = make_order("SO-BROWSER-E2E", [(product, 1)])
        session = start_packing(order)
        recording = start_recording(session)
        self.assertEqual(recording.status, PackagingRecording.Status.RECORDING)

        class _Upload:
            def __init__(self, path):
                self._path = path
                self.size = Path(path).stat().st_size

            def read(self, n=-1):
                with open(self._path, "rb") as stream:
                    return stream.read(n)

            def seek(self, _offset):
                pass

            def chunks(self):
                with open(self._path, "rb") as stream:
                    yield stream.read()

        raw_clip = Path(self._tmp.name) / "scratch-upload.mp4"
        write_real_clip(str(raw_clip), duration_seconds=1.5)
        save_uploaded_recording(session, _Upload(str(raw_clip)))

        record_scan(session, product.barcode)
        complete_packing(session)
        session.refresh_from_db()
        seal_recording(session)

        process_due(limit=1, worker_name="browser-recording-test")

        recording.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.READY)
        self.assertAlmostEqual(recording.duration_seconds, 1.5, delta=0.2)
        self.assertGreater(recording.compressed_size_bytes, 0)
        self.assertTrue(recording.compressed_checksum)
        self.assertEqual(
            Notification.objects.filter(
                order=order, kind=Notification.Kind.PACKAGING_VIDEO
            ).count(),
            2,
        )

    def test_sealing_before_the_upload_lands_retries_until_it_does(self):
        product = make_product("BRK-BROWSER-RACE", "5560004")
        order = make_order("SO-BROWSER-RACE", [(product, 1)])
        session = start_packing(order)
        recording = start_recording(session)

        record_scan(session, product.barcode)
        complete_packing(session)
        session.refresh_from_db()
        seal_recording(session)

        # No upload has happened yet -- the worker must back off, not fail.
        process_due(limit=1, worker_name="browser-race-test")
        recording.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.RETRYING)

        class _Upload:
            def __init__(self, path):
                self._path = path
                self.size = Path(path).stat().st_size

            def read(self, n=-1):
                with open(self._path, "rb") as stream:
                    return stream.read(n)

            def seek(self, _offset):
                pass

            def chunks(self):
                with open(self._path, "rb") as stream:
                    yield stream.read()

        raw_clip = Path(self._tmp.name) / "late-upload.mp4"
        write_real_clip(str(raw_clip), duration_seconds=1.0)
        save_uploaded_recording(session, _Upload(str(raw_clip)))

        from operations.models import WorkItem

        WorkItem.objects.filter(kind="process_packaging_recording").update(
            available_at=timezone.now()
        )
        process_due(limit=1, worker_name="browser-race-test")

        recording.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.READY)

    def test_worker_refuses_a_raw_file_that_no_longer_matches_its_upload_checksum(self):
        """If the file at raw_path changed after save_uploaded_recording
        checksummed it -- the actual scenario the locked recheck is meant to
        close off, caught here one layer deeper in case that ever regresses
        -- the worker must refuse to treat it as trustworthy evidence rather
        than silently compressing and dispatching whatever is there."""
        product = make_product("BRK-BROWSER-TAMPER", "5560005")
        order = make_order("SO-BROWSER-TAMPER", [(product, 1)])
        session = start_packing(order)
        recording = start_recording(session)

        class _Upload:
            def __init__(self, path):
                self._path = path
                self.size = Path(path).stat().st_size

            def read(self, n=-1):
                with open(self._path, "rb") as stream:
                    return stream.read(n)

            def seek(self, _offset):
                pass

            def chunks(self):
                with open(self._path, "rb") as stream:
                    yield stream.read()

        raw_clip = Path(self._tmp.name) / "uploaded.mp4"
        write_real_clip(str(raw_clip), duration_seconds=1.0)
        save_uploaded_recording(session, _Upload(str(raw_clip)))

        record_scan(session, product.barcode)
        complete_packing(session)
        session.refresh_from_db()
        seal_recording(session)

        # Tamper with the raw file in place, after the checksum was already
        # recorded at upload time but before the worker has read it.
        recording.refresh_from_db()
        raw_abs = Path(self._tmp.name) / recording.raw_path
        write_real_clip(str(raw_abs), duration_seconds=9.0)

        process_due(limit=1, worker_name="browser-tamper-test")

        recording.refresh_from_db()
        self.assertEqual(recording.status, PackagingRecording.Status.FAILED)
        self.assertIn("changed after upload", recording.error)
        self.assertEqual(
            Notification.objects.filter(
                order=order, kind=Notification.Kind.PACKAGING_VIDEO
            ).count(),
            0,
        )

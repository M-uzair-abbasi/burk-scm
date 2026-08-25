from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from django.core.management import call_command
from django.core.management.base import CommandError

from common.correlation import correlation_id
from .models import WorkItem, WorkerHeartbeat
from .services import claim_due, enqueue, process_due


class WorkQueueTests(TestCase):
    def test_enqueue_is_idempotent_by_business_key(self):
        first = enqueue("example", "order:1", {"order_id": 1})
        second = enqueue("example", "order:1", {"order_id": 1})

        self.assertEqual(first.id, second.id)
        self.assertEqual(WorkItem.objects.count(), 1)

    def test_enqueue_carries_originating_request_correlation_id(self):
        token = correlation_id.set("request-correlation-123")
        try:
            item = enqueue("example", "correlated", {})
        finally:
            correlation_id.reset(token)

        self.assertEqual(item.correlation_id, "request-correlation-123")

    def test_expired_processing_lease_is_reclaimed(self):
        item = enqueue("example", "expired", {})
        WorkItem.objects.filter(pk=item.pk).update(
            status=WorkItem.Status.PROCESSING,
            attempts=1,
            lease_expires_at=timezone.now() - timedelta(seconds=1),
        )

        claimed = claim_due(limit=1)

        self.assertEqual([row.id for row in claimed], [item.id])
        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.Status.PROCESSING)
        self.assertEqual(item.attempts, 2)
        self.assertGreater(item.lease_expires_at, timezone.now())

    def test_retryable_failure_uses_backoff_then_succeeds(self):
        item = enqueue("example", "retry", {}, max_attempts=3)
        failing = Mock(side_effect=RuntimeError("temporary outage"))

        with patch("operations.services.get_handler", return_value=failing):
            process_due(limit=1)

        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.Status.RETRY)
        self.assertEqual(item.attempts, 1)
        self.assertIn("temporary outage", item.last_error)
        self.assertGreater(item.available_at, timezone.now())

        WorkItem.objects.filter(pk=item.pk).update(available_at=timezone.now())
        succeeding = Mock()
        with patch("operations.services.get_handler", return_value=succeeding):
            process_due(limit=1)

        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.Status.SUCCEEDED)
        self.assertEqual(item.attempts, 2)
        self.assertIsNotNone(item.completed_at)
        succeeding.assert_called_once()

    def test_last_attempt_becomes_terminal_failure(self):
        item = enqueue("example", "terminal", {}, max_attempts=1)

        with patch(
            "operations.services.get_handler",
            return_value=Mock(side_effect=RuntimeError("permanent failure")),
        ):
            process_due(limit=1)

        item.refresh_from_db()
        self.assertEqual(item.status, WorkItem.Status.FAILED)
        self.assertEqual(item.attempts, 1)
        self.assertIsNotNone(item.completed_at)

    def test_worker_run_updates_heartbeat_counts(self):
        enqueue("example", "heartbeat", {})

        with patch("operations.services.get_handler", return_value=Mock()):
            process_due(limit=5, worker_name="test-worker")

        heartbeat = WorkerHeartbeat.objects.get(name="test-worker")
        self.assertEqual(heartbeat.last_claimed, 1)
        self.assertEqual(heartbeat.last_succeeded, 1)
        self.assertEqual(heartbeat.last_failed, 0)

    def test_batch_leases_each_item_only_when_it_is_ready_to_execute(self):
        first = enqueue("example", "batch-first", {})
        second = enqueue("example", "batch-second", {})
        observed_second_status = []

        def handler(item):
            if item.pk == first.pk:
                observed_second_status.append(
                    WorkItem.objects.get(pk=second.pk).status
                )

        with patch("operations.services.get_handler", return_value=handler):
            process_due(limit=2, worker_name="batch-test")

        self.assertEqual(observed_second_status, [WorkItem.Status.PENDING])
        self.assertEqual(
            list(
                WorkItem.objects.order_by("id").values_list("status", flat=True)
            ),
            [WorkItem.Status.SUCCEEDED, WorkItem.Status.SUCCEEDED],
        )

    def test_run_worker_once_returns_after_one_batch(self):
        enqueue("example", "command-once", {})
        with patch("operations.services.get_handler", return_value=Mock()):
            call_command("run_worker", "--once", "--limit", "1")

        self.assertEqual(
            WorkItem.objects.get(key="example:command-once").status,
            WorkItem.Status.SUCCEEDED,
        )

    def test_worker_heartbeat_command_accepts_fresh_and_rejects_stale(self):
        heartbeat = WorkerHeartbeat.objects.create(name="container-worker")
        call_command(
            "check_worker_heartbeat",
            "--worker-name",
            "container-worker",
            "--max-age",
            "30",
        )

        WorkerHeartbeat.objects.filter(pk=heartbeat.pk).update(
            last_seen_at=timezone.now() - timedelta(minutes=5)
        )
        with self.assertRaises(CommandError):
            call_command(
                "check_worker_heartbeat",
                "--worker-name",
                "container-worker",
                "--max-age",
                "30",
            )


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL skip_locked")
class ConcurrentClaimTests(TransactionTestCase):
    reset_sequences = True

    def test_two_workers_never_claim_the_same_item(self):
        item = enqueue("example", "one-claim", {})
        barrier = Barrier(2)

        def claim_once(_):
            try:
                barrier.wait(timeout=10)
                return [row.id for row in claim_due(limit=1)]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim_once, range(2)))

        claimed_ids = [item_id for batch in results for item_id in batch]
        self.assertEqual(claimed_ids, [item.id])
